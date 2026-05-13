"""Unified records for eNH3-ExtractBench method comparison.

This module is intentionally lightweight. It localizes structured extraction
ideas into an eNH3-specific record format without depending on external model
or extraction frameworks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Mapping

from enh3bench.schema import (
    CONTROL_VALUES,
    ISOTOPE_VALIDATION_VALUES,
    NITROGEN_SOURCES,
    REACTION_FAMILIES,
    RELIABILITY_LABELS,
)


GROUNDING_STATUSES = {"explicit", "missing", "inferred", "unclear", "mixed"}
EXTRACTION_CONFIDENCE_VALUES = {"high", "medium", "low", "unclear"}


@dataclass(slots=True)
class ExtractBenchRecord:
    """One method output for an eNH3 evidence span."""

    record_id: str
    paper_id: str
    source_span: str
    method_name: str
    reaction_family: str
    nitrogen_source: str
    catalyst: str | None
    electrolyte: str | None
    reactor_type: str | None
    potential: float | None
    FE_percent: float | None
    EE_percent: float | None
    NH3_yield: float | None
    NH3_yield_unit: str | None
    stability: float | None
    isotope_validation: str
    blank_control: str
    contamination_control: str
    nox_screening: str
    detection_method: str | None
    reliability_label: str
    extraction_confidence: str
    source_grounding_status: str
    notes: str | None


def record_to_dict(record: ExtractBenchRecord) -> dict[str, Any]:
    """Convert an ExtractBenchRecord to a JSON-serializable dictionary."""

    return asdict(record)


def record_from_dict(data: Mapping[str, Any]) -> ExtractBenchRecord:
    """Build an ExtractBenchRecord from a dictionary, ignoring unknown keys."""

    names = {field.name for field in fields(ExtractBenchRecord)}
    kwargs = {name: data.get(name) for name in names}
    return ExtractBenchRecord(**kwargs)


def validate_extractbench_record(record: ExtractBenchRecord | Mapping[str, Any]) -> list[str]:
    """Return validation messages for one ExtractBench record."""

    if not isinstance(record, ExtractBenchRecord):
        record = record_from_dict(record)

    messages: list[str] = []
    _require_non_empty(messages, "record_id", record.record_id)
    _require_non_empty(messages, "paper_id", record.paper_id)
    _require_non_empty(messages, "source_span", record.source_span)
    _require_non_empty(messages, "method_name", record.method_name)
    _check_allowed(messages, "reaction_family", record.reaction_family, REACTION_FAMILIES)
    _check_allowed(messages, "nitrogen_source", record.nitrogen_source, NITROGEN_SOURCES)
    _check_allowed(
        messages,
        "isotope_validation",
        record.isotope_validation,
        ISOTOPE_VALIDATION_VALUES,
    )
    _check_allowed(messages, "blank_control", record.blank_control, CONTROL_VALUES)
    _check_allowed(messages, "contamination_control", record.contamination_control, CONTROL_VALUES)
    _check_allowed(messages, "nox_screening", record.nox_screening, CONTROL_VALUES)
    _check_allowed(messages, "reliability_label", record.reliability_label, RELIABILITY_LABELS)
    _check_allowed(
        messages,
        "extraction_confidence",
        record.extraction_confidence,
        EXTRACTION_CONFIDENCE_VALUES,
    )
    _check_allowed(
        messages,
        "source_grounding_status",
        record.source_grounding_status,
        GROUNDING_STATUSES,
    )

    if record.reliability_label == "A" and record.isotope_validation != "yes":
        messages.append("warning: reliability_label A usually requires isotope_validation=yes")
    if record.isotope_validation == "yes" and record.source_grounding_status in {"missing", "inferred"}:
        messages.append("warning: isotope_validation=yes should be explicitly source grounded")
    return messages


def _require_non_empty(messages: list[str], field_name: str, value: Any) -> None:
    if value is None or not str(value).strip():
        messages.append(f"error: {field_name} is required")


def _check_allowed(
    messages: list[str],
    field_name: str,
    value: str,
    allowed_values: set[str],
) -> None:
    if value not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        messages.append(f"error: {field_name} must be one of: {allowed}")
