"""Stable, content-derived identity for source spans used by context outputs."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from typing import Any


LEGACY_ORDER_PATTERN = re.compile(r"_S(\d+)$", re.IGNORECASE)


def normalize_span_text(text: Any) -> str:
    """Normalize Unicode and whitespace without changing semantic casing."""

    normalized = unicodedata.normalize("NFKC", str(text or "")).replace("\u00a0", " ")
    return " ".join(normalized.split())


def normalize_section_path(section_path: Any) -> str:
    """Normalize section paths from list, JSON-list, or scalar representations."""

    value = section_path
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                value = parsed
    parts = value if isinstance(value, (list, tuple)) else [value]
    normalized = [normalize_span_text(part).casefold() for part in parts if normalize_span_text(part)]
    return " / ".join(normalized)


def parse_legacy_span_order(source_span_id: Any) -> int | None:
    """Parse the terminal _S### order from a legacy span ID."""

    match = LEGACY_ORDER_PATTERN.search(str(source_span_id or "").strip())
    return int(match.group(1)) if match else None


def build_stable_span_uid(record: dict[str, Any]) -> str:
    """Build a deterministic UID from paper, normalized section path, and text hash."""

    paper_id = normalize_span_text(record.get("paper_id"))
    section_path = normalize_section_path(
        record.get("section_path") or record.get("section_heading") or record.get("source_section")
    )
    source_text = normalize_span_text(
        record.get("source_text") or record.get("source_span") or record.get("text") or record.get("raw_source_text")
    )
    text_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    canonical = json.dumps(
        {"paper_id": paper_id, "section_path": section_path, "source_text_sha256": text_sha256},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "SPAN_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def attach_span_identity(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return copied records with context-only identity and ordering metadata."""

    attached: list[dict[str, Any]] = []
    by_paper: dict[str, list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    for input_order, original in enumerate(records):
        record = dict(original)
        legacy_span_id = str(record.get("source_span_id") or record.get("span_id") or "").strip()
        explicit_order = _coerce_order(record.get("span_order"))
        parsed_order = parse_legacy_span_order(legacy_span_id)
        warnings = _list_values(record.get("span_identity_warnings"))
        if explicit_order is None and parsed_order is None:
            warnings.append("legacy_span_order_unparseable")
        record["legacy_span_id"] = legacy_span_id
        record["stable_span_uid"] = build_stable_span_uid(record)
        record["span_order"] = explicit_order if explicit_order is not None else parsed_order
        record["span_identity_warnings"] = _dedupe(warnings)
        record["_context_input_order"] = input_order
        attached.append(record)
        by_paper[str(record.get("paper_id") or "")].append((input_order, record))

    for paper_records in by_paper.values():
        ordered = sorted(paper_records, key=lambda item: _identity_sort_key(item[1], item[0]))
        section_counts: dict[str, int] = defaultdict(int)
        total = len(ordered)
        for _, record in ordered:
            section = normalize_section_path(
                record.get("section_path") or record.get("section_heading") or record.get("source_section")
            )
            section_counts[section] += 1
            record["section_span_order"] = section_counts[section]
            record["document_span_count"] = total

    for record in attached:
        record.pop("_context_input_order", None)
    return attached


def _identity_sort_key(record: dict[str, Any], input_order: int) -> tuple[int, int]:
    order = _coerce_order(record.get("span_order"))
    return (order if order is not None else 10**12, input_order)


def _coerce_order(value: Any) -> int | None:
    if isinstance(value, bool) or value is None or str(value).strip() == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _list_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value or "").strip() else []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
