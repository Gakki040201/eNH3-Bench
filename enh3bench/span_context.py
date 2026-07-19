"""Paper-scoped span ordering and context queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from enh3bench.span_identity import attach_span_identity, normalize_section_path, parse_legacy_span_order


LOW_TRUST_PROVENANCE = {"reference", "bibliography", "figure_caption", "scheme_caption", "review_table"}
LOW_TRUST_TEXT_CLASSES = {"reference_list", "figure_caption", "review_table", "background_context"}


@dataclass(frozen=True)
class DocumentSpanIndex:
    records_by_id: dict[str, dict[str, Any]]
    paper_records: dict[str, list[dict[str, Any]]]
    positions: dict[str, int]
    warnings: list[str]


def build_document_span_index(records: list[dict[str, Any]]) -> DocumentSpanIndex:
    """Build an immutable-by-convention paper-scoped lookup over copied records."""

    explicit_orders = [_coerce_order(record.get("span_order")) for record in records]
    attached = attach_span_identity(records)
    by_id: dict[str, dict[str, Any]] = {}
    by_paper_with_keys: dict[str, list[tuple[tuple[int, int, int], dict[str, Any]]]] = {}
    warnings: list[str] = []

    for input_order, record in enumerate(attached):
        span_id = str(record.get("legacy_span_id") or "").strip()
        if not span_id:
            raise ValueError(f"source_span_id is required for context index at input position {input_order}")
        if span_id in by_id:
            raise ValueError(f"duplicate source_span_id: {span_id}")
        paper_id = str(record.get("paper_id") or "").strip()
        if not paper_id:
            raise ValueError(f"paper_id is required for context span: {span_id}")
        parsed_order = parse_legacy_span_order(span_id)
        explicit_order = explicit_orders[input_order]
        if explicit_order is not None:
            sort_key = (0, explicit_order, input_order)
        elif parsed_order is not None:
            sort_key = (1, parsed_order, input_order)
        else:
            sort_key = (2, input_order, input_order)
            warning = f"span_order_fallback_to_input:{span_id}"
            warnings.append(warning)
            record["span_identity_warnings"] = _dedupe(
                [*record.get("span_identity_warnings", []), warning]
            )
        by_id[span_id] = record
        by_paper_with_keys.setdefault(paper_id, []).append((sort_key, record))

    paper_records: dict[str, list[dict[str, Any]]] = {}
    positions: dict[str, int] = {}
    for paper_id, keyed_records in by_paper_with_keys.items():
        ordered = [record for _, record in sorted(keyed_records, key=lambda item: item[0])]
        paper_records[paper_id] = ordered
        for position, record in enumerate(ordered):
            positions[str(record["legacy_span_id"])] = position
    return DocumentSpanIndex(by_id, paper_records, positions, warnings)


def get_previous_spans(index: DocumentSpanIndex, target_span_id: str, count: int = 1) -> list[dict[str, Any]]:
    target, paper_records, position = _target_context(index, target_span_id)
    start = max(0, position - max(0, int(count)))
    candidates = paper_records[start:position]
    return [_context_record(candidate, target, position, index.positions[target_span_id], "previous", index) for candidate in candidates]


def get_next_spans(index: DocumentSpanIndex, target_span_id: str, count: int = 1) -> list[dict[str, Any]]:
    target, paper_records, position = _target_context(index, target_span_id)
    candidates = paper_records[position + 1 : position + 1 + max(0, int(count))]
    return [_context_record(candidate, target, position, index.positions[target_span_id], "next", index) for candidate in candidates]


def get_adjacent_spans(
    index: DocumentSpanIndex, target_span_id: str, before: int = 1, after: int = 1
) -> list[dict[str, Any]]:
    return [
        *get_previous_spans(index, target_span_id, before),
        *get_next_spans(index, target_span_id, after),
    ]


def get_same_section_spans(
    index: DocumentSpanIndex, target_span_id: str, maximum: int = 4
) -> list[dict[str, Any]]:
    target, paper_records, position = _target_context(index, target_span_id)
    section = _section_key(target)
    if not section:
        return []
    candidates = [record for record in paper_records if record["legacy_span_id"] != target_span_id and _section_key(record) == section]
    candidates.sort(key=lambda record: (abs(index.positions[str(record["legacy_span_id"])] - position), index.positions[str(record["legacy_span_id"])]))
    return [
        _context_record(record, target, position, index.positions[target_span_id], "same_section", index)
        for record in candidates[: max(0, int(maximum))]
    ]


def get_paper_spans(index: DocumentSpanIndex, paper_id: str) -> list[dict[str, Any]]:
    records = index.paper_records.get(str(paper_id), [])
    return [_context_record(record, record, index.positions[str(record["legacy_span_id"])], index.positions[str(record["legacy_span_id"])], "same_paper", index) for record in records]


def validate_no_cross_paper_links(context: Any) -> bool:
    """Raise when any nested linked/context record differs from the target paper."""

    if isinstance(context, dict):
        target_paper = str(context.get("paper_id") or context.get("target_paper_id") or "")
        linked = list(_nested_span_records(context))
    elif isinstance(context, list):
        linked = [item for item in context if isinstance(item, dict)]
        papers = {str(item.get("paper_id") or "") for item in linked if str(item.get("paper_id") or "")}
        if len(papers) > 1:
            raise ValueError(f"cross-paper context detected: {sorted(papers)}")
        return True
    else:
        return True
    for record in linked:
        paper_id = str(record.get("paper_id") or "")
        if target_paper and paper_id and paper_id != target_paper:
            raise ValueError(f"cross-paper context detected: target={target_paper}, linked={paper_id}")
    return True


def _target_context(
    index: DocumentSpanIndex, target_span_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    if target_span_id not in index.records_by_id:
        raise KeyError(f"target span not found: {target_span_id}")
    target = index.records_by_id[target_span_id]
    paper_id = str(target["paper_id"])
    return target, index.paper_records[paper_id], index.positions[target_span_id]


def _context_record(
    record: dict[str, Any],
    target: dict[str, Any],
    target_position: int,
    _unused_target_position: int,
    relationship: str,
    index: DocumentSpanIndex,
) -> dict[str, Any]:
    span_id = str(record["legacy_span_id"])
    position = index.positions[span_id]
    provenance = str(record.get("provenance_type") or "unknown")
    text_class = str(record.get("text_class") or "unknown")
    return {
        "span_id": span_id,
        "stable_span_uid": str(record.get("stable_span_uid") or ""),
        "paper_id": str(record.get("paper_id") or ""),
        "span_order": record.get("span_order"),
        "section_path": record.get("section_path") or [],
        "section_heading": str(record.get("section_heading") or ""),
        "text_class": text_class,
        "provenance_type": provenance,
        "source_text": str(record.get("source_text") or record.get("text") or ""),
        "distance_from_target": position - target_position,
        "relationship": relationship,
        "context_only": provenance in LOW_TRUST_PROVENANCE or text_class in LOW_TRUST_TEXT_CLASSES,
    }


def _section_key(record: dict[str, Any]) -> str:
    return normalize_section_path(record.get("section_path") or record.get("section_heading") or record.get("source_section"))


def _nested_span_records(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if "span_id" in value and "paper_id" in value:
            yield value
        for nested in value.values():
            yield from _nested_span_records(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _nested_span_records(item)


def _coerce_order(value: Any) -> int | None:
    if isinstance(value, bool) or value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))
