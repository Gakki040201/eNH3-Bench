"""NERRE-style JSON extraction scaffold for eNH3 evidence records.

This module builds prompts, parses JSON output, validates the local schema, and
offers a no-API rule fallback. It does not run any model.
"""

from __future__ import annotations

import json
from typing import Any

from enh3bench.chatextract_chain import run_rule_chatextract
from enh3bench.extractbench_schema import record_from_dict, validate_extractbench_record


def build_nerre_json_prompt(source_span: str) -> str:
    """Build a structured JSON extraction prompt for a sentence or paragraph."""

    return "\n".join(
        [
            "Extract structured eNH3 evidence from the source span.",
            "Return JSON only. The JSON must be either one object or an array of objects.",
            "Each object must use the eNH3-ExtractBench fields:",
            "record_id, paper_id, source_span, method_name, reaction_family, nitrogen_source,",
            "catalyst, electrolyte, reactor_type, potential, FE_percent, EE_percent, NH3_yield,",
            "NH3_yield_unit, stability, isotope_validation, blank_control, contamination_control,",
            "nox_screening, detection_method, reliability_label, extraction_confidence,",
            "source_grounding_status, notes.",
            "Use null for unstated values. Do not invent missing validation controls.",
            "",
            "SOURCE SPAN:",
            source_span,
        ]
    )


def parse_model_json_output(text: str) -> list[dict[str, Any]]:
    """Parse a model-style JSON object or array from text."""

    payload = _extract_json_payload(text)
    data = json.loads(payload)
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return data
    raise ValueError("JSON output must be an object or an array of objects")


def validate_nerre_json_record(record: dict[str, Any]) -> list[str]:
    """Validate one parsed NERRE-style eNH3 record."""

    return validate_extractbench_record(record_from_dict(record))


def run_rule_nerre_style(source_span: str | dict[str, Any]) -> dict[str, Any]:
    """Run an offline rule fallback in the NERRE-style output format."""

    record = run_rule_chatextract(source_span)
    record["method_name"] = "enh3_nerre_rule"
    notes = record.get("notes") or ""
    record["notes"] = (notes + " NERRE-style JSON scaffold; no model call.").strip()
    return record


def _extract_json_payload(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return stripped

    object_start = stripped.find("{")
    array_start = stripped.find("[")
    starts = [index for index in (object_start, array_start) if index >= 0]
    if not starts:
        raise ValueError("No JSON object or array found")
    start = min(starts)
    opener = stripped[start]
    closer = "}" if opener == "{" else "]"
    end = stripped.rfind(closer)
    if end < start:
        raise ValueError("JSON payload is incomplete")
    return stripped[start : end + 1]
