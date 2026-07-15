"""Ordered Markdown source ledger and verified evidence-anchor coordinates."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from enh3bench.document_loader import load_markdown_documents
from enh3bench.section_context import extract_markdown_section_blocks
from enh3bench.span_identity import normalize_section_path, normalize_span_text


@dataclass
class OrderedSourceLedger:
    documents_by_id: dict[str, dict[str, Any]]
    documents_by_paper: dict[str, list[dict[str, Any]]]
    sections_by_document: dict[str, list[dict[str, Any]]]
    paragraphs_by_document: dict[str, list[dict[str, Any]]]
    paragraphs_by_uid: dict[str, dict[str, Any]]
    warnings: list[str]


def build_ordered_source_ledger(markdown_dir: str | Path) -> OrderedSourceLedger:
    """Load Markdown once and preserve its physical section and paragraph order."""

    root = Path(markdown_dir)
    documents_by_id: dict[str, dict[str, Any]] = {}
    documents_by_paper: dict[str, list[dict[str, Any]]] = defaultdict(list)
    sections_by_document: dict[str, list[dict[str, Any]]] = {}
    paragraphs_by_document: dict[str, list[dict[str, Any]]] = {}
    paragraphs_by_uid: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for loaded in load_markdown_documents(root):
        document_id = str(loaded.get("document_id") or "").strip()
        paper_id = document_id
        if not document_id or document_id in documents_by_id:
            raise ValueError(f"duplicate or missing document_id: {document_id}")
        body = str(loaded.get("text") or "")
        body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        raw_sections = list(loaded.get("section_blocks") or extract_markdown_section_blocks(body))
        sections = _build_section_nodes(raw_sections, paper_id, document_id, body_sha, len(body))
        paragraphs = _build_paragraph_nodes(body, paper_id, document_id, body_sha, sections)
        path = Path(str(loaded.get("path") or root / f"{document_id}.md"))
        try:
            document_ref = path.resolve().relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            document_ref = (root / path.name).as_posix()
        document = {
            "paper_id": paper_id,
            "document_id": document_id,
            "document_ref": document_ref,
            "document_body_sha256": body_sha,
            "document_character_count": len(body),
            "section_count": len(sections),
            "paragraph_count": len(paragraphs),
            "full_body_text": body,
            "front_matter_signals": list(loaded.get("front_matter_signals") or []),
        }
        documents_by_id[document_id] = document
        documents_by_paper[paper_id].append(document)
        sections_by_document[document_id] = sections
        paragraphs_by_document[document_id] = paragraphs
        for paragraph in paragraphs:
            uid = str(paragraph["paragraph_uid"])
            if uid in paragraphs_by_uid:
                raise ValueError(f"duplicate paragraph_uid: {uid}")
            paragraphs_by_uid[uid] = paragraph
        if not body:
            warnings.append(f"empty_document_body:{document_id}")
    return OrderedSourceLedger(
        documents_by_id=documents_by_id,
        documents_by_paper=dict(documents_by_paper),
        sections_by_document=sections_by_document,
        paragraphs_by_document=paragraphs_by_document,
        paragraphs_by_uid=paragraphs_by_uid,
        warnings=warnings,
    )


def attach_source_coordinates_to_spans(
    records: list[dict[str, Any]], source_ledger: OrderedSourceLedger
) -> list[dict[str, Any]]:
    """Attach verified source coordinates without mutating source records or guessing ambiguous matches."""

    attached: list[dict[str, Any]] = []
    resolved_by_paragraph: dict[str, list[tuple[int, int, int, dict[str, Any]]]] = defaultdict(list)
    for input_index, original in enumerate(records):
        record = dict(original)
        paper_id = str(record.get("paper_id") or "").strip()
        document = _resolve_document(record, source_ledger)
        warnings = _list_values(record.get("source_mapping_warnings"))
        mapping = _unresolved_mapping("unresolved", warnings or ["document_unresolved"])
        if document is not None and paper_id == str(document.get("paper_id") or ""):
            mapping = _map_span(record, document, source_ledger)
        record.update(mapping)
        record["legacy_span_id"] = str(
            record.get("source_span_id") or record.get("span_id") or record.get("legacy_span_id") or ""
        )
        record["document_body_sha256"] = str(document.get("document_body_sha256") if document else "")
        record["document_ref"] = str(document.get("document_ref") if document else "")
        record["source_locator"] = None
        record["source_order_key"] = None
        attached.append(record)
        paragraph_uid = str(record.get("paragraph_uid") or "")
        if paragraph_uid:
            resolved_by_paragraph[paragraph_uid].append((
                int(record["verified_source_start_offset"]),
                int(record["verified_source_end_offset"]),
                input_index,
                record,
            ))

    for paragraph_uid, grouped in resolved_by_paragraph.items():
        paragraph = source_ledger.paragraphs_by_uid[paragraph_uid]
        for anchor_index, (_start, _end, _input_index, record) in enumerate(
            sorted(grouped, key=lambda item: (item[0], item[1], item[2])), start=1
        ):
            record["anchor_index_in_paragraph"] = anchor_index
            record["source_locator"] = f"{paragraph['source_locator']}::ANCHOR{anchor_index:02d}"
            record["source_order_key"] = _source_order_key(
                paragraph.get("outline_index_path") or [],
                int(paragraph["paragraph_index_in_section"]),
                anchor_index,
            )
    return attached


def sort_spans_by_source_order(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return copies sorted only by verified physical source coordinates."""

    return sorted(
        (dict(record) for record in records),
        key=lambda record: (
            str(record.get("paper_id") or ""),
            _sort_offset(record.get("verified_source_start_offset"), record.get("source_start_offset")),
            _sort_offset(record.get("verified_source_end_offset"), record.get("source_end_offset")),
            int(record.get("_source_input_order") or 0),
        ),
    )


def sort_spans_by_priority(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return copies sorted by explicit priority without changing source coordinates."""

    return sorted(
        (dict(record) for record in records),
        key=lambda record: (
            int(record.get("candidate_priority_rank") or 10**12),
            -float(record.get("candidate_score") or 0),
            _sort_offset(record.get("verified_source_start_offset"), record.get("source_start_offset")),
        ),
    )


def summarize_source_ledger(
    source_ledger: OrderedSourceLedger,
    spans: list[dict[str, Any]],
    *,
    original_span_ids: list[str] | None = None,
) -> dict[str, Any]:
    documents = list(source_ledger.documents_by_id.values())
    sections = [section for values in source_ledger.sections_by_document.values() for section in values]
    paragraphs = [paragraph for values in source_ledger.paragraphs_by_document.values() for paragraph in values]
    verified = [record for record in spans if record.get("source_mapping_confidence") == "high"]
    locators = [str(record.get("source_locator")) for record in spans if record.get("source_locator")]
    source_violations = 0
    overlap_violations = 0
    for document_id, document_paragraphs in source_ledger.paragraphs_by_document.items():
        for previous, current in zip(document_paragraphs, document_paragraphs[1:]):
            if int(current["source_start_offset"]) < int(previous["source_start_offset"]):
                source_violations += 1
            if int(current["source_start_offset"]) < int(previous["source_end_offset"]):
                overlap_violations += 1
    original_ids = original_span_ids or [str(record.get("source_span_id") or "") for record in spans]
    current_ids = [str(record.get("source_span_id") or "") for record in spans]
    original_id_set = {value for value in original_ids if value}
    current_id_set = {value for value in current_ids if value}
    missing_ids = original_id_set - current_id_set
    extra_ids = current_id_set - original_id_set
    spans_per_section = Counter(str(record.get("section_uid") or "unresolved") for record in spans)
    return {
        "document_count": len(documents),
        "section_count": len(sections),
        "paragraph_count": len(paragraphs),
        "span_count": len(spans),
        "verified_span_mapping_count": len(verified),
        "unresolved_span_mapping_count": sum(record.get("source_mapping_method") == "unresolved" for record in spans),
        "multiple_exact_match_count": sum("multiple_exact_matches" in (record.get("source_mapping_warnings") or []) for record in spans),
        "source_locator_coverage": round(len(locators) / len(spans), 6) if spans else 0.0,
        "duplicate_source_locator_count": len(locators) - len(set(locators)),
        "source_order_violation_count": source_violations,
        "offset_overlap_violation_count": overlap_violations,
        "section_type_distribution": dict(sorted(Counter(str(section.get("section_type") or "unknown") for section in sections).items())),
        "document_region_distribution": dict(sorted(Counter(str(section.get("document_region") or "unknown") for section in sections).items())),
        "paragraphs_per_document_distribution": _count_distribution([int(document["paragraph_count"]) for document in documents]),
        "spans_per_section_distribution": _count_distribution(list(spans_per_section.values())),
        "legacy_source_span_id_count": len([value for value in original_ids if value]),
        "source_span_id_missing_count": len(missing_ids),
        "source_span_id_extra_count": len(extra_ids),
        "source_span_id_changed_count": len(missing_ids) + len(extra_ids),
    }


def export_source_ledger(
    source_ledger: OrderedSourceLedger,
    spans: list[dict[str, Any]],
    run_name: str,
    output_dir: str | Path = "data/source_ledgers",
    *,
    original_span_ids: list[str] | None = None,
) -> dict[str, Any]:
    run_dir = Path(output_dir)
    if run_dir.name != run_name:
        run_dir = run_dir / run_name
    document_path = run_dir / "document_ledger.jsonl"
    section_path = run_dir / "section_ledger.jsonl"
    paragraph_path = run_dir / "paragraph_ledger.jsonl"
    span_path = run_dir / "span_source_coordinates.jsonl"
    summary_path = run_dir / "source_ledger_summary.json"
    documents = [{key: value for key, value in document.items() if key != "full_body_text"} for document in source_ledger.documents_by_id.values()]
    sections = [section for values in source_ledger.sections_by_document.values() for section in values]
    paragraphs = [paragraph for values in source_ledger.paragraphs_by_document.values() for paragraph in values]
    summary = summarize_source_ledger(source_ledger, spans, original_span_ids=original_span_ids)
    span_exports = [_span_export_record(record) for record in spans]
    for path, records in ((document_path, documents), (section_path, sections), (paragraph_path, paragraphs), (span_path, span_exports)):
        _write_jsonl(records, path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "document_ledger": str(document_path), "section_ledger": str(section_path),
        "paragraph_ledger": str(paragraph_path), "span_source_coordinates": str(span_path),
        "summary": str(summary_path), "summary_data": summary,
    }


def _build_section_nodes(
    raw_sections: list[dict[str, Any]], paper_id: str, document_id: str, body_sha: str, body_length: int
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    outline_stack: list[tuple[int, int]] = []
    sibling_counts: dict[tuple[int, ...], int] = defaultdict(int)
    body_index = 0
    for source_index, raw in enumerate(sorted(raw_sections, key=lambda item: int(item.get("section_start_offset") or 0)), start=1):
        start = int(raw.get("section_start_offset") or 0)
        end_value = raw.get("section_end_offset")
        end = body_length if end_value is None else int(end_value)
        heading = str(raw.get("section_heading") or "")
        normalized_heading = normalize_span_text(heading).casefold()
        section_type = str(raw.get("section_type") or "unknown")
        level = int(raw.get("section_level") or 0)
        region = _document_region(section_type, normalized_heading, bool(heading))
        outline_path: list[int] = []
        if heading and region not in {"title", "abstract"}:
            while outline_stack and outline_stack[-1][0] >= level:
                outline_stack.pop()
            parent_path = tuple(value for _heading_level, value in outline_stack)
            sibling_counts[parent_path] += 1
            ordinal = sibling_counts[parent_path]
            outline_stack.append((level, ordinal))
            outline_path = [value for _heading_level, value in outline_stack]
        if region == "main_body":
            body_index += 1
            current_body_index: int | None = body_index
        else:
            current_body_index = None
        uid = _uid("SEC", {
            "paper_id": paper_id, "document_id": document_id, "document_body_sha256": body_sha,
            "section_start_offset": start, "section_end_offset": end, "normalized_heading": normalized_heading,
        })
        nodes.append({
            "section_uid": uid, "paper_id": paper_id, "document_id": document_id,
            "source_section_index": source_index, "body_section_index": current_body_index,
            "heading_text": heading, "normalized_heading": normalized_heading,
            "section_path": list(raw.get("section_path") or []),
            "section_type": section_type, "section_level": level,
            "outline_index_path": outline_path, "outline_label": ".".join(map(str, outline_path)),
            "section_start_offset": start, "section_end_offset": end,
            "parent_section_uid": None, "previous_section_uid": None, "next_section_uid": None,
            "document_region": region,
        })
    by_outline = {tuple(node["outline_index_path"]): node["section_uid"] for node in nodes if node["outline_index_path"]}
    for index, node in enumerate(nodes):
        path = tuple(node["outline_index_path"])
        node["parent_section_uid"] = by_outline.get(path[:-1]) if len(path) > 1 else None
        node["previous_section_uid"] = nodes[index - 1]["section_uid"] if index else None
        node["next_section_uid"] = nodes[index + 1]["section_uid"] if index + 1 < len(nodes) else None
    return nodes


def _build_paragraph_nodes(
    body: str, paper_id: str, document_id: str, body_sha: str, sections: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    section_counts: Counter[str] = Counter()
    for global_index, match in enumerate(re.finditer(r"\S(?:.*?)(?=\n\s*\n+|\Z)", body, flags=re.DOTALL), start=1):
        raw = match.group(0)
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        start = match.start() + leading
        end = match.start() + trailing
        text = body[start:end]
        section = _section_for_offset(sections, start) or _unknown_section(document_id, paper_id, len(nodes) + 1, len(body))
        section_uid = str(section["section_uid"])
        section_counts[section_uid] += 1
        text_sha = hashlib.sha256(normalize_span_text(text).encode("utf-8")).hexdigest()
        uid = _uid("PAR", {
            "paper_id": paper_id, "document_id": document_id, "document_body_sha256": body_sha,
            "source_start_offset": start, "source_end_offset": end, "normalized_text_sha256": text_sha,
        })
        outline = list(section.get("outline_index_path") or [])
        paragraph_index = section_counts[section_uid]
        nodes.append({
            "paragraph_uid": uid, "paper_id": paper_id, "document_id": document_id,
            "section_uid": section_uid, "paragraph_global_index": global_index,
            "paragraph_index_in_section": paragraph_index, "source_start_offset": start,
            "source_end_offset": end, "text": text, "normalized_text_sha256": text_sha,
            "section_outline_label": str(section.get("outline_label") or ""),
            "outline_index_path": outline, "section_heading": str(section.get("heading_text") or ""),
            "section_path": list(section.get("section_path") or []),
            "section_type": str(section.get("section_type") or "unknown"),
            "document_region": str(section.get("document_region") or "unknown"),
            "previous_paragraph_uid": None, "next_paragraph_uid": None,
            "document_relative_position": _ratio(start, len(body)),
            "section_relative_position": _ratio(
                start - int(section.get("section_start_offset") or 0),
                int(section.get("section_end_offset") or len(body)) - int(section.get("section_start_offset") or 0),
            ),
            "source_locator": _paragraph_locator(paper_id, section, paragraph_index),
            "source_order_key": _source_order_key(outline, paragraph_index, 0),
        })
    for index, node in enumerate(nodes):
        node["previous_paragraph_uid"] = nodes[index - 1]["paragraph_uid"] if index else None
        node["next_paragraph_uid"] = nodes[index + 1]["paragraph_uid"] if index + 1 < len(nodes) else None
    return nodes


def _map_span(record: dict[str, Any], document: dict[str, Any], ledger: OrderedSourceLedger) -> dict[str, Any]:
    body = str(document["full_body_text"])
    document_id = str(document["document_id"])
    source_text = str(record.get("source_text") or record.get("text") or "")
    normalized_source = normalize_span_text(source_text)
    warnings: list[str] = []
    start = _offset(record.get("source_start_offset"))
    end = _offset(record.get("source_end_offset"))
    if start is not None or end is not None:
        if start is not None and end is not None and 0 <= start < end <= len(body):
            match = normalize_span_text(body[start:end]) == normalized_source
            if match:
                return _resolved_mapping("explicit_verified", "high", start, end, document_id, ledger, True, warnings, [])
            warnings.append("offset_text_mismatch")
        else:
            warnings.append("invalid_offset_pair")

    section_candidates = _candidate_sections(record, ledger.sections_by_document.get(document_id, []))
    section_matches: list[tuple[int, int]] = []
    for section in section_candidates:
        section_matches.extend(_normalized_matches(
            body, source_text, int(section["section_start_offset"]), int(section["section_end_offset"])
        ))
    section_matches = _unique_offsets(section_matches)
    if len(section_matches) == 1:
        a, b = section_matches[0]
        return _resolved_mapping("section_constrained_exact", "medium", a, b, document_id, ledger, True, warnings, section_matches)
    if len(section_matches) > 1:
        return _unresolved_mapping("unresolved", [*warnings, "multiple_exact_matches"], section_matches)
    matches = _unique_offsets(_normalized_matches(body, source_text, 0, len(body)))
    if len(matches) == 1:
        a, b = matches[0]
        return _resolved_mapping("document_exact", "medium", a, b, document_id, ledger, True, warnings, matches)
    if len(matches) > 1:
        return _unresolved_mapping("unresolved", [*warnings, "multiple_exact_matches"], matches)
    return _unresolved_mapping("unresolved", [*warnings, "exact_text_not_found"])


def _resolved_mapping(
    method: str, confidence: str, start: int, end: int, document_id: str,
    ledger: OrderedSourceLedger, text_match: bool, warnings: list[str], candidates: list[tuple[int, int]],
) -> dict[str, Any]:
    paragraph = next((item for item in ledger.paragraphs_by_document.get(document_id, []) if int(item["source_start_offset"]) <= start < int(item["source_end_offset"])), None)
    section = next((item for item in ledger.sections_by_document.get(document_id, []) if int(item["section_start_offset"]) <= start < int(item["section_end_offset"])), None)
    return {
        "source_mapping_method": method, "source_mapping_confidence": confidence,
        "source_mapping_warnings": _dedupe(warnings), "offset_text_match": text_match,
        "verified_source_start_offset": start, "verified_source_end_offset": end,
        "paragraph_uid": paragraph.get("paragraph_uid") if paragraph else None,
        "section_uid": section.get("section_uid") if section else None,
        "parent_section_uid": section.get("parent_section_uid") if section else None,
        "paragraph_global_index": paragraph.get("paragraph_global_index") if paragraph else None,
        "paragraph_index_in_section": paragraph.get("paragraph_index_in_section") if paragraph else None,
        "section_outline_label": section.get("outline_label") if section else "",
        "section_heading": section.get("heading_text") if section else "",
        "section_type": section.get("section_type") if section else "unknown",
        "document_region": section.get("document_region") if section else "unknown",
        "document_relative_position": paragraph.get("document_relative_position") if paragraph else None,
        "section_relative_position": paragraph.get("section_relative_position") if paragraph else None,
        "candidate_offsets": [{"start_offset": a, "end_offset": b} for a, b in candidates],
    }


def _unresolved_mapping(method: str, warnings: list[str], candidates: list[tuple[int, int]] | None = None) -> dict[str, Any]:
    return {
        "source_mapping_method": method, "source_mapping_confidence": "unresolved",
        "source_mapping_warnings": _dedupe(warnings), "offset_text_match": False,
        "verified_source_start_offset": None, "verified_source_end_offset": None,
        "paragraph_uid": None, "section_uid": None, "parent_section_uid": None, "paragraph_global_index": None,
        "paragraph_index_in_section": None, "section_outline_label": "", "section_heading": "",
        "section_type": "unknown", "document_region": "unknown",
        "document_relative_position": None, "section_relative_position": None,
        "candidate_offsets": [{"start_offset": a, "end_offset": b} for a, b in (candidates or [])],
    }


def _resolve_document(record: dict[str, Any], ledger: OrderedSourceLedger) -> dict[str, Any] | None:
    document_id = str(record.get("document_id") or "").strip()
    paper_id = str(record.get("paper_id") or "").strip()
    if document_id in ledger.documents_by_id:
        document = ledger.documents_by_id[document_id]
        return document if not paper_id or paper_id == document.get("paper_id") else None
    matches = ledger.documents_by_paper.get(paper_id, [])
    return matches[0] if len(matches) == 1 else None


def _candidate_sections(record: dict[str, Any], sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    start = _offset(record.get("section_start_offset")); end = _offset(record.get("section_end_offset"))
    if start is not None and end is not None:
        exact = [item for item in sections if int(item["section_start_offset"]) == start and int(item["section_end_offset"]) == end]
        if exact: return exact
    heading = normalize_span_text(record.get("section_heading") or "").casefold()
    if heading:
        return [item for item in sections if item.get("normalized_heading") == heading]
    path = normalize_section_path(record.get("section_path"))
    if path:
        final_heading = path.split(" / ")[-1]
        return [item for item in sections if item.get("normalized_heading") == final_heading]
    return []


def _normalized_matches(body: str, source_text: str, start: int, end: int) -> list[tuple[int, int]]:
    tokens = normalize_span_text(source_text).split()
    if not tokens: return []
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    return [(start + match.start(), start + match.end()) for match in re.finditer(pattern, body[start:end])]


def _document_region(section_type: str, normalized_heading: str, has_heading: bool) -> str:
    if section_type == "title": return "title"
    if section_type == "abstract" or normalized_heading == "abstract": return "abstract"
    if section_type == "references" or normalized_heading in {"references", "bibliography"}: return "references"
    if section_type == "supplementary": return "supplementary"
    return "main_body" if has_heading else "unknown"


def _section_for_offset(sections: list[dict[str, Any]], offset: int) -> dict[str, Any] | None:
    return next((section for section in sections if int(section["section_start_offset"]) <= offset < int(section["section_end_offset"])), None)


def _paragraph_locator(paper_id: str, section: dict[str, Any], paragraph_index: int) -> str:
    outline = list(section.get("outline_index_path") or [])
    if outline:
        section_part = "SEC" + ".".join(f"{value:03d}" for value in outline)
    else:
        section_part = f"SECUNK{int(section.get('source_section_index') or 0):03d}"
    return f"{paper_id}::{section_part}::PAR{paragraph_index:03d}"


def _source_order_key(outline: list[int], paragraph_index: int, anchor_index: int) -> str:
    section_components = list(outline[:2])
    while len(section_components) < 2: section_components.append(0)
    return ".".join(f"{value:06d}" for value in [*section_components, paragraph_index, anchor_index])


def _unknown_section(document_id: str, paper_id: str, index: int, body_length: int) -> dict[str, Any]:
    return {"section_uid": f"{document_id}_UNKNOWN", "paper_id": paper_id, "source_section_index": index,
            "section_start_offset": 0, "section_end_offset": body_length, "outline_index_path": [],
            "outline_label": "", "heading_text": "", "section_type": "unknown", "document_region": "unknown"}


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0: return 0.0
    return round(max(0.0, min(1.0, numerator / denominator)), 8)


def _uid(prefix: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _offset(value: Any) -> int | None:
    if value is None or isinstance(value, bool) or str(value).strip() == "": return None
    try: number = int(value)
    except (TypeError, ValueError): return None
    return number if number >= 0 else None


def _sort_offset(primary: Any, fallback: Any) -> int:
    return _offset(primary) if _offset(primary) is not None else (_offset(fallback) if _offset(fallback) is not None else 10**18)


def _unique_offsets(values: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return list(dict.fromkeys(values))


def _count_distribution(values: list[int]) -> dict[str, int]:
    return {str(key): value for key, value in sorted(Counter(values).items())}


def _list_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)): return [str(item) for item in value if str(item)]
    return [str(value)] if str(value or "") else []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


def _write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n")


def _span_export_record(record: dict[str, Any]) -> dict[str, Any]:
    excluded = {"raw_record", "provenance", "extracted_fields", "reaction_profile"}
    return {key: value for key, value in record.items() if key not in excluded}
