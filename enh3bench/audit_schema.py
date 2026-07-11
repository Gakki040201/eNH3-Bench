"""Human audit label schema for eNH3-BoundaryLedger."""

from __future__ import annotations

import json
import re
from typing import Any


HUMAN_TEXT_CLASSES = (
    "primary_performance",
    "primary_performance_with_validation",
    "protocol_guideline",
    "review_table",
    "figure_caption",
    "reference_list",
    "contamination_detection_evidence",
    "contamination_reassignment_evidence",
    "computational_screening",
    "background_context",
    "unknown",
)

HUMAN_BOUNDARIES = (
    "unsupported_or_secondary",
    "product_admissibility",
    "cell_metric",
    "reactor_legibility",
    "process_partial",
    "plant_facing_insufficient",
)

HUMAN_ADMISSIBILITY_STATUSES = (
    "accept",
    "accept_with_controls",
    "metric_only_or_validation_incomplete",
    "secondary_only",
    "context_only_caption",
    "protocol_only",
    "negative_evidence",
    "computational_only",
    "reject",
    "reject_or_low_trust_provenance",
    "unclear_needs_second_reviewer",
)

HUMAN_EXPERIMENT_DECISIONS = (
    "priority_experiment",
    "control_required",
    "discard_as_secondary",
    "negative_warning",
    "protocol_reference",
    "insufficient_evidence",
    "needs_second_reviewer",
)

HUMAN_HIDDEN_TAX_TYPES = (
    "solvent_management_tax",
    "resistance_or_renewal_tax",
    "wetting_outlet_capture_tax",
    "hydrogen_logistics_tax",
    "contamination_tax",
    "measurement_matrix_tax",
)

VALIDATION_GATE_LABELS = (
    "explicit",
    "missing",
    "unclear",
    "secondary_only",
    "not_applicable",
)

HUMAN_REVIEW_STATUSES = ("unreviewed", "reviewed", "needs_second_reviewer", "excluded")

REVIEW_PRIORITY_BANDS = ("none", "low", "medium", "high", "critical")

REVIEW_REQUIREMENT_FIELDS = (
    "rule_needs_human_review",
    "llm_needs_human_review",
    "overall_needs_human_review",
    "review_priority_band",
    "review_trigger_flags",
)

NEEDS_HUMAN_REVIEW_ALIAS_NOTE = (
    "needs_human_review is a deprecated compatibility alias for overall_needs_human_review."
)

HUMAN_FIELDS = (
    "human_reviewer_id",
    "human_review_status",
    "human_text_class",
    "human_maximum_supported_boundary",
    "human_admissibility_status",
    "human_required_controls",
    "human_hidden_tax",
    "human_experiment_decision",
    "human_validation_isotope_15N",
    "human_validation_blank_control",
    "human_validation_NOx_control",
    "human_validation_contamination_control",
    "human_validation_quantification_method",
    "human_notes",
)

CORE_REVIEW_FIELDS = (
    "human_text_class",
    "human_maximum_supported_boundary",
    "human_admissibility_status",
    "human_experiment_decision",
)

VALIDATION_FIELDS = (
    "human_validation_isotope_15N",
    "human_validation_blank_control",
    "human_validation_NOx_control",
    "human_validation_contamination_control",
    "human_validation_quantification_method",
)


def normalize_list_field(value: Any) -> list[str]:
    """Normalize editable CSV/JSON list values into a string list."""

    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return _dedupe(_normalize_list_item(item) for item in value)
    if isinstance(value, dict):
        return [json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)] if value else []

    text = str(value).strip()
    if not text or text.casefold() in {"none", "null", "nan", "n/a", "na", "[]"}:
        return []

    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return normalize_list_field(parsed)

    parts = re.split(r"[;,|]", text)
    if len(parts) == 1:
        return _dedupe([_strip_outer_quotes(text)])
    return _dedupe(_strip_outer_quotes(part) for part in parts)


def empty_human_fields_template() -> dict[str, str]:
    """Return blank human-review fields for audit sheet export."""

    fields = {field: "" for field in HUMAN_FIELDS}
    fields["human_review_status"] = "unreviewed"
    return fields


def is_reviewed_record(record: dict[str, Any]) -> bool:
    """Return True only when the record is explicitly reviewed and complete."""

    status = _clean_label(record.get("human_review_status"))
    if status != "reviewed":
        return False
    return all(_has_value(record.get(field)) for field in CORE_REVIEW_FIELDS)


def validate_human_label_record(record: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate human labels without coercing invalid values."""

    errors: list[str] = []
    status = _clean_label(record.get("human_review_status"))
    if not status:
        status = "unreviewed"
    if status not in HUMAN_REVIEW_STATUSES:
        errors.append(f"invalid human_review_status: {record.get('human_review_status')}")

    _validate_choice(record, "human_text_class", HUMAN_TEXT_CLASSES, errors)
    _validate_choice(record, "human_maximum_supported_boundary", HUMAN_BOUNDARIES, errors)
    _validate_choice(record, "human_admissibility_status", HUMAN_ADMISSIBILITY_STATUSES, errors)
    _validate_choice(record, "human_experiment_decision", HUMAN_EXPERIMENT_DECISIONS, errors)

    for field in VALIDATION_FIELDS:
        _validate_choice(record, field, VALIDATION_GATE_LABELS, errors)

    for tax in normalize_list_field(record.get("human_hidden_tax")):
        if tax not in HUMAN_HIDDEN_TAX_TYPES:
            errors.append(f"invalid human_hidden_tax: {tax}")

    if status == "reviewed":
        for field in CORE_REVIEW_FIELDS:
            if not _has_value(record.get(field)):
                errors.append(f"reviewed record missing required field: {field}")

    return not errors, errors


def _validate_choice(record: dict[str, Any], field: str, choices: tuple[str, ...], errors: list[str]) -> None:
    value = _clean_label(record.get(field))
    if value and value not in choices:
        errors.append(f"invalid {field}: {record.get(field)}")


def _has_value(value: Any) -> bool:
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return bool(str(value or "").strip())


def _clean_label(value: Any) -> str:
    return str(value or "").strip()


def _normalize_list_item(item: Any) -> str:
    if item is None:
        return ""
    if isinstance(item, dict):
        for key in ("text", "content", "value"):
            value = item.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return json.dumps(item, ensure_ascii=True, sort_keys=True, default=str)
    return _strip_outer_quotes(str(item))


def _strip_outer_quotes(value: str) -> str:
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1].strip()
    return text


def _dedupe(items: Any) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped
