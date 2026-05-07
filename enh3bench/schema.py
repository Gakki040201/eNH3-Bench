"""Gold evidence schema for eNH3-Bench.

The schema intentionally uses only Python standard-library dataclasses. It is
small enough to support manual annotation, rule-based baselines, and local
evaluation without introducing validation frameworks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Mapping


ARTICLE_TYPES = {
    "primary_research",
    "review",
    "perspective",
    "protocol",
    "reassessment",
    "preprint",
    "unknown",
}

SOURCE_SECTIONS = {
    "abstract",
    "results",
    "methods",
    "supplementary",
    "table",
    "figure_caption",
    "review_table",
    "unknown",
}

REACTION_FAMILIES = {
    "eNRR",
    "LiNRR",
    "NO3RR",
    "NO2RR",
    "NORR",
    "mixed",
    "unclear",
}

NITROGEN_SOURCES = {
    "N2",
    "15N2",
    "NO3-",
    "NO2-",
    "NO",
    "NOx",
    "catalyst_impurity",
    "unknown",
}

ISOTOPE_VALIDATION_VALUES = {"yes", "no", "unclear", "not_applicable"}
CONTROL_VALUES = {"yes", "no", "unclear"}
RELIABILITY_LABELS = {"A", "B", "C", "D", "Reject"}
EVIDENCE_TYPES = {
    "primary_claim",
    "control_experiment",
    "negative_result",
    "reassessment",
    "review_summary",
}


@dataclass(slots=True)
class PaperRecord:
    """Paper-level metadata used to organize evidence records."""

    paper_id: str
    title: str
    doi: str | None
    year: int | None
    journal: str | None
    article_type: str
    open_access: bool | None
    source_file: str | None
    notes: str | None


@dataclass(slots=True)
class EvidenceRecord:
    """One evidence-grounded ammonia synthesis claim or validation statement."""

    evidence_id: str
    paper_id: str
    source_span: str
    source_section: str
    reaction_family: str
    nitrogen_source: str
    catalyst: str | None
    catalyst_class: str | None
    electrolyte: str | None
    reactor_type: str | None
    membrane: str | None
    potential_value: float | None
    potential_unit: str | None
    potential_reference: str | None
    current_density_mA_cm2: float | None
    faradaic_efficiency_percent: float | None
    nh3_yield_value: float | None
    nh3_yield_unit: str | None
    nh3_yield_normalized_value: float | None
    nh3_yield_normalized_unit: str | None
    energy_efficiency_percent: float | None
    stability_hours: float | None
    detection_method: str | None
    isotope_validation: str
    blank_control: str
    contamination_control: str
    nox_screening: str
    reliability_label: str
    evidence_type: str
    gold_notes: str | None


def validate_paper_record(record: PaperRecord) -> list[str]:
    """Return validation errors and warnings for a paper record."""

    messages: list[str] = []
    _require_non_empty(messages, "paper_id", record.paper_id)
    _check_allowed(messages, "article_type", record.article_type, ARTICLE_TYPES)
    return messages


def validate_evidence_record(record: EvidenceRecord) -> list[str]:
    """Return validation errors and warnings for an evidence record."""

    messages: list[str] = []
    _require_non_empty(messages, "evidence_id", record.evidence_id)
    _require_non_empty(messages, "paper_id", record.paper_id)
    _require_non_empty(messages, "source_span", record.source_span)
    _check_allowed(messages, "source_section", record.source_section, SOURCE_SECTIONS)
    _check_allowed(messages, "reaction_family", record.reaction_family, REACTION_FAMILIES)
    _check_allowed(messages, "nitrogen_source", record.nitrogen_source, NITROGEN_SOURCES)
    _check_allowed(
        messages,
        "isotope_validation",
        record.isotope_validation,
        ISOTOPE_VALIDATION_VALUES,
    )
    _check_allowed(messages, "blank_control", record.blank_control, CONTROL_VALUES)
    _check_allowed(
        messages,
        "contamination_control",
        record.contamination_control,
        CONTROL_VALUES,
    )
    _check_allowed(messages, "nox_screening", record.nox_screening, CONTROL_VALUES)
    _check_allowed(messages, "reliability_label", record.reliability_label, RELIABILITY_LABELS)
    _check_allowed(messages, "evidence_type", record.evidence_type, EVIDENCE_TYPES)

    if record.reliability_label == "A" and record.isotope_validation != "yes":
        messages.append(
            "warning: reliability_label A usually requires isotope_validation=yes"
        )
    if record.evidence_type == "review_summary" and record.reliability_label == "A":
        messages.append(
            "warning: review_summary evidence should not normally receive reliability_label A"
        )

    return messages


def evidence_to_dict(record: EvidenceRecord) -> dict[str, Any]:
    """Convert an evidence dataclass to a JSON-serializable dictionary."""

    return asdict(record)


def paper_to_dict(record: PaperRecord) -> dict[str, Any]:
    """Convert a paper dataclass to a JSON-serializable dictionary."""

    return asdict(record)


def evidence_from_dict(data: Mapping[str, Any]) -> EvidenceRecord:
    """Build an EvidenceRecord from a dictionary, ignoring unknown keys."""

    return _from_dict(EvidenceRecord, data)


def paper_from_dict(data: Mapping[str, Any]) -> PaperRecord:
    """Build a PaperRecord from a dictionary, ignoring unknown keys."""

    return _from_dict(PaperRecord, data)


def _from_dict(record_type: type[PaperRecord] | type[EvidenceRecord], data: Mapping[str, Any]):
    names = {field.name for field in fields(record_type)}
    kwargs = {name: data[name] for name in names if name in data}
    return record_type(**kwargs)


def _require_non_empty(messages: list[str], field_name: str, value: str | None) -> None:
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
