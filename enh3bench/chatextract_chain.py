"""eNH3-localized ChatExtract-style prompt chain scaffolding.

The functions in this module only build prompts or run an offline rule fallback.
They do not call model APIs.
"""

from __future__ import annotations

from typing import Any

from enh3bench.extractbench_schema import validate_extractbench_record
from enh3bench.field_grounding import ground_record, summarize_grounding
from enh3bench.rule_baseline import run_rule_extraction


def build_relevance_prompt(source_span: str) -> str:
    """Build a prompt that asks whether a span contains eNH3 evidence."""

    return "\n".join(
        [
            "You are checking one source span for electrochemical ammonia synthesis evidence.",
            "Return JSON with keys: decision, reason.",
            "decision must be one of: yes, no, unclear.",
            "Evidence may involve eNRR, LiNRR, NO3RR, NO2RR, NORR, NH3 yield, FE, EE,",
            "isotope validation, blank controls, contamination controls, or NOx screening.",
            "Do not infer missing claims.",
            "",
            "SOURCE SPAN:",
            source_span,
        ]
    )


def build_extraction_prompt(source_span: str) -> str:
    """Build a prompt for structured eNH3 field extraction."""

    return "\n".join(
        [
            "Extract an eNH3-ExtractBench record from the source span.",
            "Return one JSON object only. Use null for unstated numeric or free-text fields.",
            "Use 'unclear' or 'unknown' for unstated categorical fields.",
            "Do not infer validation controls from the absence of contamination discussion.",
            "Distinguish review summaries from primary evidence in notes.",
            "Fields: record_id, paper_id, source_span, method_name, reaction_family,",
            "nitrogen_source, catalyst, electrolyte, reactor_type, potential, FE_percent,",
            "EE_percent, NH3_yield, NH3_yield_unit, stability, isotope_validation,",
            "blank_control, contamination_control, nox_screening, detection_method,",
            "reliability_label, extraction_confidence, source_grounding_status, notes.",
            "",
            "SOURCE SPAN:",
            source_span,
        ]
    )


def build_verification_prompt(source_span: str, extracted_record: dict[str, Any]) -> str:
    """Build a field-grounding verification prompt."""

    return "\n".join(
        [
            "Verify whether each extracted field is explicitly supported by the source span.",
            "Return JSON with one item per field: field, value, grounding_status, evidence_snippet, risk_flag.",
            "grounding_status must be explicit, missing, inferred, or unclear.",
            "Downgrade unsupported validation yes fields to unclear in your comments.",
            "",
            "SOURCE SPAN:",
            source_span,
            "",
            "EXTRACTED RECORD:",
            _compact_json_like(extracted_record),
        ]
    )


def build_reliability_prompt(source_span: str, extracted_record: dict[str, Any]) -> str:
    """Build a reliability-label prompt for human or future model review."""

    return "\n".join(
        [
            "Assign an eNH3 reliability label: A, B, C, D, or Reject.",
            "Base the label only on the source span and extracted fields.",
            "Consider explicit 15N/isotope validation, blank controls, contamination/NOx controls,",
            "source grounding, and whether the span is primary evidence or a review summary.",
            "Do not give A to unsupported review summaries or claims without explicit isotope evidence.",
            "",
            "SOURCE SPAN:",
            source_span,
            "",
            "EXTRACTED RECORD:",
            _compact_json_like(extracted_record),
        ]
    )


def run_rule_chatextract(source_span: str | dict[str, Any]) -> dict[str, Any]:
    """Run a local rule fallback and return an ExtractBench-like record."""

    span_record = _span_record(source_span)
    draft = run_rule_extraction(span_record)
    record = _from_evidence_dict(draft, "enh3_chatextract_rule")
    grounding = ground_record(draft)
    summary = summarize_grounding(grounding)
    record["source_grounding_status"] = _overall_grounding(summary)
    record["extraction_confidence"] = _confidence(record, summary)
    warnings = validate_extractbench_record(record)
    if warnings:
        existing_notes = record.get("notes") or ""
        record["notes"] = (existing_notes + " Validation messages: " + "; ".join(warnings)).strip()
    return record


def _span_record(source_span: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(source_span, dict):
        return {
            "span_id": source_span.get("span_id") or source_span.get("record_id") or "S_RULE",
            "paper_id": source_span.get("paper_id", "UNKNOWN"),
            "source_section": source_span.get("source_section", "unknown"),
            "text": source_span.get("text") or source_span.get("source_span") or "",
        }
    return {
        "span_id": "S_RULE",
        "paper_id": "UNKNOWN",
        "source_section": "unknown",
        "text": source_span,
    }


def _from_evidence_dict(draft: dict[str, Any], method_name: str) -> dict[str, Any]:
    return {
        "record_id": str(draft.get("evidence_id", "E_RULE")),
        "paper_id": str(draft.get("paper_id", "UNKNOWN")),
        "source_span": str(draft.get("source_span", "")),
        "method_name": method_name,
        "reaction_family": draft.get("reaction_family", "unclear"),
        "nitrogen_source": draft.get("nitrogen_source", "unknown"),
        "catalyst": draft.get("catalyst"),
        "electrolyte": draft.get("electrolyte"),
        "reactor_type": draft.get("reactor_type"),
        "potential": draft.get("potential_value"),
        "FE_percent": draft.get("faradaic_efficiency_percent"),
        "EE_percent": draft.get("energy_efficiency_percent"),
        "NH3_yield": draft.get("nh3_yield_value"),
        "NH3_yield_unit": draft.get("nh3_yield_unit"),
        "stability": draft.get("stability_hours"),
        "isotope_validation": draft.get("isotope_validation", "unclear"),
        "blank_control": draft.get("blank_control", "unclear"),
        "contamination_control": draft.get("contamination_control", "unclear"),
        "nox_screening": draft.get("nox_screening", "unclear"),
        "detection_method": draft.get("detection_method"),
        "reliability_label": draft.get("reliability_label", "D"),
        "extraction_confidence": "unclear",
        "source_grounding_status": "unclear",
        "notes": "Offline ChatExtract-style rule fallback; requires human verification.",
    }


def _overall_grounding(summary: dict[str, int]) -> str:
    explicit = int(summary.get("explicit", 0))
    risk_flags = int(summary.get("risk_flags", 0))
    if risk_flags:
        return "mixed"
    if explicit:
        return "explicit"
    return "unclear"


def _confidence(record: dict[str, Any], summary: dict[str, int]) -> str:
    strong_fields = 0
    for field in ("reaction_family", "nitrogen_source"):
        if record.get(field) not in {"unclear", "unknown", None, ""}:
            strong_fields += 1
    for field in ("FE_percent", "EE_percent", "NH3_yield", "potential", "stability"):
        if record.get(field) is not None:
            strong_fields += 1
    for field in ("isotope_validation", "blank_control", "contamination_control", "nox_screening"):
        if record.get(field) == "yes":
            strong_fields += 1
    if strong_fields >= 4 and summary.get("risk_flags", 0) == 0:
        return "high"
    if strong_fields >= 2:
        return "medium"
    return "low"


def _compact_json_like(data: dict[str, Any]) -> str:
    parts = [f'  "{key}": {value!r}' for key, value in sorted(data.items())]
    return "{\n" + ",\n".join(parts) + "\n}"
