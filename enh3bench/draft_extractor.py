"""Draft evidence extraction from candidate spans."""

from __future__ import annotations

from typing import Any

from enh3bench.rule_baseline import run_rule_extraction


def draft_evidence_from_span(span: dict[str, Any]) -> dict[str, Any]:
    """Create a machine draft EvidenceRecord-like dictionary from one span."""

    draft = run_rule_extraction(span)
    span_id = str(span.get("span_id", "")).strip()
    draft["span_id"] = span_id
    draft["evidence_id"] = _evidence_id_from_span_id(span_id)
    draft["source_span"] = str(span.get("text", "")).strip()
    draft["source_section"] = str(span.get("source_section", "unknown")).strip() or "unknown"
    draft["machine_notes"] = "Machine draft; requires human verification."
    draft["draft_confidence"] = _draft_confidence(draft)
    return draft


def _evidence_id_from_span_id(span_id: str) -> str:
    if span_id.startswith("S") and len(span_id) > 1:
        return f"E{span_id[1:]}"
    if span_id:
        return f"E_{span_id}"
    return "E_TODO"


def _draft_confidence(draft: dict[str, Any]) -> str:
    family_found = draft.get("reaction_family") not in {None, "", "unclear"}
    strong_fields = [
        draft.get("nitrogen_source") not in {None, "", "unknown"},
        draft.get("faradaic_efficiency_percent") is not None,
        draft.get("nh3_yield_value") is not None,
        draft.get("potential_value") is not None,
        draft.get("current_density_mA_cm2") is not None,
        draft.get("stability_hours") is not None,
        draft.get("detection_method") is not None,
        draft.get("isotope_validation") == "yes",
        draft.get("blank_control") == "yes",
        draft.get("contamination_control") == "yes",
        draft.get("nox_screening") == "yes",
    ]
    strong_count = sum(1 for present in strong_fields if present)
    if family_found and strong_count >= 3:
        return "high"
    if family_found and strong_count >= 1:
        return "medium"
    return "low"
