"""Merge human review sheet decisions into reviewed gold JSONL records."""

from __future__ import annotations

from dataclasses import fields
from typing import Any

from enh3bench.schema import EvidenceRecord


SCHEMA_FIELDS = [field.name for field in fields(EvidenceRecord)]


def merge_reviewed_gold(
    drafts: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge accepted human review rows into schema-compatible gold records."""

    draft_by_id = {str(draft.get("evidence_id", "")): draft for draft in drafts}
    reviewed: list[dict[str, Any]] = []

    for row in review_rows:
        evidence_id = str(row.get("evidence_id", "")).strip()
        decision = str(row.get("human_decision", "")).strip().casefold()
        include_in_gold = _truthy(row.get("include_in_gold"))
        if decision == "reject":
            continue
        if decision != "accept" and not include_in_gold:
            continue
        draft = draft_by_id.get(evidence_id)
        if draft is None:
            continue
        gold = {field: draft.get(field) for field in SCHEMA_FIELDS}
        reliability_override = str(row.get("reliability_override", "")).strip()
        if reliability_override:
            gold["reliability_label"] = reliability_override
        correction_notes = str(row.get("correction_notes", "")).strip()
        if correction_notes:
            gold["gold_notes"] = _append_note(gold.get("gold_notes"), correction_notes)
        reviewed.append(gold)

    return reviewed


def _truthy(value: Any) -> bool:
    return str(value).strip().casefold() in {"true", "yes", "y", "1", "include"}


def _append_note(existing: Any, correction_notes: str) -> str:
    if existing is None or str(existing).strip() == "":
        return correction_notes
    return f"{str(existing).strip()} Correction notes: {correction_notes}"
