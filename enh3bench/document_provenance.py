"""Document-provenance extraction and export helpers for BoundaryLedger."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from enh3bench.ledger_router import load_jsonl
from enh3bench.front_matter import strip_conversion_front_matter
from enh3bench.provenance_rules import infer_provenance_from_text
from enh3bench.section_context import attach_section_context_to_records


def load_docling_json(path: str | Path) -> dict[str, Any]:
    """Load a Docling JSON export, returning an empty dict on malformed input."""

    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {"items": data}


def extract_provenance_from_docling_json(
    docling_json: dict[str, Any],
    paper_id: str | None = None,
) -> list[dict[str, Any]]:
    """Extract provenance records from common Docling-like JSON layouts."""

    records: list[dict[str, Any]] = []
    document_id = _first_text(docling_json, "document_id", "doc_id", "name", "filename")
    paper_id = paper_id or _first_text(docling_json, "paper_id") or document_id
    items = _candidate_items(docling_json)
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        text = _item_text(item)
        if not text:
            continue
        section = _item_section(item)
        block_type = _item_block_type(item)
        page = _item_page(item)
        raw = attach_section_context_to_records(
            [
                {
                    **dict(item),
                    "source_text": text,
                    "section": section,
                    "block_type": block_type,
                }
            ]
        )[0]
        if block_type:
            raw.setdefault("block_type", block_type)
        inferred = infer_provenance_from_text(text, section, raw)
        source_span_id = _first_text(item, "source_span_id", "span_id", "self_ref", "id") or f"{paper_id}_D{index:04d}"
        evidence_id = _first_text(item, "evidence_id") or f"E_{source_span_id}"
        records.append(
            {
                "provenance_id": f"PV_{source_span_id}",
                "paper_id": paper_id or "",
                "document_id": document_id or _first_text(item, "document_id", "doc_id"),
                "source_span_id": source_span_id,
                "evidence_id": evidence_id,
                "source_text": text,
                "section": section,
                "section_heading": raw.get("section_heading") or "",
                "section_path": raw.get("section_path") or [],
                "section_level": raw.get("section_level") or 0,
                "section_type": raw.get("section_type") or "unknown",
                "section_start_offset": raw.get("section_start_offset"),
                "section_end_offset": raw.get("section_end_offset"),
                "section_confidence": raw.get("section_confidence") or "low",
                "section_signals": raw.get("section_signals") or [],
                "page": page,
                "block_type": block_type,
                "provenance_type": inferred["provenance_type"],
                "provenance_confidence": inferred["confidence"],
                "provenance_confidence_rationale": inferred.get("provenance_confidence_rationale", []),
                "provenance_signals": inferred["signals"],
                "is_primary_admissible": inferred["is_primary_admissible"],
                "is_secondary_or_context": inferred["is_secondary_or_context"],
                "is_reject_or_low_trust": inferred["is_reject_or_low_trust"],
                "raw_record": raw,
            }
        )
    return records


def infer_provenance_for_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a ProvenanceRecord-like dict for a source span or evidence bundle."""

    source_text = _source_text(record)
    section_record = attach_section_context_to_records([record])[0]
    section = _first_text(section_record, "section_heading", "source_section", "section")
    isolation = strip_conversion_front_matter(source_text)
    inference_text = source_text
    metadata_isolation_signals: list[str] = []
    if (isolation.get("metadata_removed") or isolation.get("repository_cover_removed")) and str(isolation.get("body_text") or "").strip():
        inference_text = str(isolation.get("body_text") or "")
        metadata_isolation_signals = ["metadata_isolation_applied", *list(isolation.get("signals") or [])]
    inferred = infer_provenance_from_text(inference_text, section, section_record)
    source_span_id = _first_text(record, "source_span_id", "span_id", "id")
    evidence_id = _first_text(record, "evidence_id")
    return {
        "provenance_id": _provenance_id(record, source_span_id, evidence_id),
        "run_name": _first_text(record, "run_name"),
        "paper_id": _first_text(record, "paper_id"),
        "document_id": _first_text(record, "document_id"),
        "source_span_id": source_span_id,
        "evidence_id": evidence_id,
        "source_text": inference_text,
        "raw_source_text": source_text if inference_text != source_text else "",
        "section": section,
        "section_heading": section_record.get("section_heading") or "",
        "section_path": section_record.get("section_path") or [],
        "section_level": section_record.get("section_level") or 0,
        "section_type": section_record.get("section_type") or "unknown",
        "section_start_offset": section_record.get("section_start_offset"),
        "section_end_offset": section_record.get("section_end_offset"),
        "section_confidence": section_record.get("section_confidence") or "low",
        "section_signals": section_record.get("section_signals") or [],
        "page": record.get("page") or record.get("page_no") or record.get("page_number"),
        "block_type": _first_text(record, "block_type", "label", "docling_label"),
        "provenance_type": inferred["provenance_type"],
        "provenance_confidence": inferred["confidence"],
        "provenance_confidence_rationale": inferred.get("provenance_confidence_rationale", []),
        "provenance_signals": [*metadata_isolation_signals, *inferred["signals"]],
        "metadata_isolation_signals": metadata_isolation_signals,
        "metadata_removed": bool(isolation.get("metadata_removed")),
        "repository_cover_removed": bool(isolation.get("repository_cover_removed")),
        "is_primary_admissible": inferred["is_primary_admissible"],
        "is_secondary_or_context": inferred["is_secondary_or_context"],
        "is_reject_or_low_trust": inferred["is_reject_or_low_trust"],
        "raw_record": dict(section_record),
    }


def attach_provenance_to_records(
    records: list[dict[str, Any]],
    markdown_by_document: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Attach provenance fields to each record, inferring missing provenance."""

    attached: list[dict[str, Any]] = []
    sectioned = attach_section_context_to_records(records, markdown_by_document)
    for record in sectioned:
        item = dict(record)
        provenance = infer_provenance_for_record(item)
        _copy_provenance_fields(item, provenance)
        attached.append(item)
    return attached


def export_provenance_records(
    records: list[dict[str, Any]],
    run_name: str,
    output_dir: str | Path = "data/provenance",
) -> dict[str, Any]:
    """Write source-span provenance records as JSONL and CSV."""

    run_dir = Path(output_dir) / run_name
    jsonl_path = run_dir / "source_span_provenance.jsonl"
    csv_path = run_dir / "source_span_provenance.csv"
    tagged = []
    for record in records:
        item = dict(record)
        item.setdefault("run_name", run_name)
        tagged.append(item)
    _write_jsonl(tagged, jsonl_path)
    _write_csv(tagged, csv_path)
    return {
        "run_name": run_name,
        "count": len(tagged),
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
    }


def summarize_provenance(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Return counts by provenance type and admissibility class."""

    types = Counter(str(record.get("provenance_type") or "unknown") for record in records)
    section_types = Counter(str(record.get("section_type") or "unknown") for record in records)
    body_confidence = Counter(
        str(record.get("provenance_confidence") or "low")
        for record in records
        if str(record.get("provenance_type") or "unknown") == "body"
    )
    recognized_section_count = sum(1 for record in records if str(record.get("section_type") or "unknown") != "unknown")
    unsectioned_body_count = sum(
        1
        for record in records
        if str(record.get("provenance_type") or "unknown") == "body"
        and str(record.get("section_type") or "unknown") == "unknown"
    )
    return {
        "total": len(records),
        "provenance_type_counts": dict(sorted(types.items())),
        "section_type_counts": dict(sorted(section_types.items())),
        "body_confidence_counts": dict(sorted(body_confidence.items())),
        "recognized_section_count": recognized_section_count,
        "recognized_section_coverage": (recognized_section_count / len(records)) if records else 0.0,
        "unsectioned_body_count": unsectioned_body_count,
        "primary_admissible_count": sum(1 for record in records if bool(record.get("is_primary_admissible"))),
        "secondary_or_context_count": sum(1 for record in records if bool(record.get("is_secondary_or_context"))),
        "reject_or_low_trust_count": sum(1 for record in records if bool(record.get("is_reject_or_low_trust"))),
    }


def attach_existing_or_infer(
    records: list[dict[str, Any]],
    provenance_records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Attach provenance records by span/evidence key, falling back to inference."""

    provenance_records = provenance_records or []
    index = _provenance_index(provenance_records)
    attached: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        match = _lookup_provenance(item, index)
        if match is None:
            match = infer_provenance_for_record(item)
        _copy_provenance_fields(item, match)
        attached.append(item)
    return attached


def load_provenance_records(run_name: str, base_dir: str | Path = "data/provenance") -> list[dict[str, Any]]:
    return load_jsonl(Path(base_dir) / run_name / "source_span_provenance.jsonl")


def _candidate_items(docling_json: dict[str, Any]) -> list[Any]:
    candidates: list[Any] = []
    for key in ("texts", "items", "children", "body", "blocks", "pages", "furniture", "groups"):
        value = docling_json.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    document = docling_json.get("document")
    if isinstance(document, dict):
        candidates.extend(_candidate_items(document))
    return _flatten_items(candidates)


def _flatten_items(items: list[Any]) -> list[Any]:
    flattened: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            flattened.append(item)
            for key in ("children", "items", "blocks", "texts"):
                child = item.get(key)
                if isinstance(child, list):
                    flattened.extend(_flatten_items(child))
        else:
            flattened.append(item)
    return flattened


def _item_text(item: dict[str, Any]) -> str:
    for key in ("text", "orig", "content", "caption", "label_text"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    data = item.get("data")
    if isinstance(data, dict):
        for key in ("text", "content"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _item_section(item: dict[str, Any]) -> str:
    for key in ("section", "section_title", "heading", "parent", "hierarchy"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list) and value:
            return " > ".join(str(part) for part in value if str(part).strip())
        if isinstance(value, dict):
            text = _first_text(value, "section", "title", "name")
            if text:
                return text
    return ""


def _item_block_type(item: dict[str, Any]) -> str:
    return _first_text(item, "label", "block_type", "type", "docling_label")


def _item_page(item: dict[str, Any]) -> Any:
    for key in ("page", "page_no", "page_number"):
        if item.get(key) is not None:
            return item.get(key)
    provenance = item.get("prov") or item.get("provenance")
    if isinstance(provenance, list) and provenance:
        first = provenance[0]
        if isinstance(first, dict):
            return first.get("page_no") or first.get("page") or first.get("page_number")
    if isinstance(provenance, dict):
        return provenance.get("page_no") or provenance.get("page") or provenance.get("page_number")
    return None


def _source_text(record: dict[str, Any]) -> str:
    for key in ("source_text", "source_span", "text"):
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _provenance_id(record: dict[str, Any], source_span_id: str, evidence_id: str) -> str:
    if source_span_id:
        return f"PV_{source_span_id}"
    if evidence_id:
        return f"PV_{evidence_id}"
    paper_id = _first_text(record, "paper_id")
    if paper_id:
        return f"PV_{paper_id}"
    return "PV_TODO"


def _copy_provenance_fields(target: dict[str, Any], provenance: dict[str, Any]) -> None:
    for key in (
        "provenance_id",
        "provenance_type",
        "provenance_confidence",
        "provenance_confidence_rationale",
        "provenance_signals",
        "section_heading",
        "section_path",
        "section_level",
        "section_type",
        "section_start_offset",
        "section_end_offset",
        "section_confidence",
        "section_signals",
        "is_primary_admissible",
        "is_secondary_or_context",
        "is_reject_or_low_trust",
        "page",
        "block_type",
        "metadata_isolation_signals",
        "metadata_removed",
        "repository_cover_removed",
    ):
        if key in provenance:
            target[key] = provenance[key]
    if not target.get("source_span_id") and provenance.get("source_span_id"):
        target["source_span_id"] = provenance["source_span_id"]


def _provenance_index(records: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        for key_name in ("source_span_id", "span_id", "evidence_id"):
            key_value = str(record.get(key_name) or "").strip()
            if key_value:
                index[(key_name, key_value)] = record
        paper_id = str(record.get("paper_id") or "").strip()
        source_span_id = str(record.get("source_span_id") or record.get("span_id") or "").strip()
        if paper_id and source_span_id:
            index[("paper_span", f"{paper_id}:{source_span_id}")] = record
    return index


def _lookup_provenance(record: dict[str, Any], index: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any] | None:
    for key_name in ("source_span_id", "span_id", "evidence_id"):
        key_value = str(record.get(key_name) or "").strip()
        if key_value and (key_name, key_value) in index:
            return index[(key_name, key_value)]
    paper_id = str(record.get("paper_id") or "").strip()
    source_span_id = str(record.get("source_span_id") or record.get("span_id") or "").strip()
    if paper_id and source_span_id:
        return index.get(("paper_span", f"{paper_id}:{source_span_id}"))
    return None


def _first_text(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, default=str, separators=(",", ":")))
            handle.write("\n")


def _write_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _fieldnames(records)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: _csv_value(record.get(field)) for field in fieldnames})


def _fieldnames(records: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "provenance_id",
        "run_name",
        "paper_id",
        "document_id",
        "source_span_id",
        "evidence_id",
        "source_text",
        "section",
        "section_heading",
        "section_path",
        "section_level",
        "section_type",
        "section_start_offset",
        "section_end_offset",
        "section_confidence",
        "section_signals",
        "page",
        "block_type",
        "provenance_type",
        "provenance_confidence",
        "provenance_confidence_rationale",
        "provenance_signals",
        "is_primary_admissible",
        "is_secondary_or_context",
        "is_reject_or_low_trust",
        "raw_record",
    ]
    names: set[str] = set(preferred)
    for record in records:
        names.update(record)
    ordered = [name for name in preferred if name in names]
    ordered.extend(sorted(name for name in names if name not in set(ordered)))
    return ordered


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return str(value)
