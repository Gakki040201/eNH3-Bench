"""Schema helpers for eNH3-BoundaryBench task records."""

from __future__ import annotations

import json
import re
from typing import Any


BENCHMARK_TASKS = (
    "source_span_classification",
    "validation_gate_extraction",
    "claim_rights_boundary_classification",
    "hidden_tax_detection",
    "required_control_prediction",
    "experiment_decision_ranking",
)

SOURCE_SPAN_LABELS = (
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

BOUNDARY_LABELS = (
    "unsupported_or_secondary",
    "product_admissibility",
    "cell_metric",
    "reactor_legibility",
    "process_partial",
    "plant_facing_insufficient",
)

VALIDATION_GATE_FIELDS = (
    "isotope_15N",
    "blank_control",
    "NOx_control",
    "contamination_control",
    "quantification_method",
)

VALIDATION_GATE_LABELS = (
    "explicit",
    "missing",
    "unclear",
    "secondary_only",
    "not_applicable",
)

HIDDEN_TAX_LABELS = (
    "solvent_management_tax",
    "resistance_or_renewal_tax",
    "wetting_outlet_capture_tax",
    "hydrogen_logistics_tax",
    "contamination_tax",
    "measurement_matrix_tax",
)

REQUIRED_CONTROL_LABELS = (
    "15N2 isotope validation",
    "Ar/N2-free blank",
    "NOx/nitrate/nitrite screening",
    "contamination/background NH3 control",
    "H2-off/HOR-off control",
    "gas/liquid product accounting",
    "wetting/flooding diagnosis",
    "voltage/current/runtime reporting",
    "product capture accounting",
    "solvent inventory/recycle reporting",
    "isotope/product-state crosscheck",
    "primary body text pairing",
)

EXPERIMENT_DECISION_LABELS = (
    "priority_experiment",
    "control_required",
    "discard_as_secondary",
    "negative_warning",
    "protocol_reference",
    "insufficient_evidence",
    "needs_second_reviewer",
)

COMMON_TASK_FIELDS = (
    "schema_version",
    "migration_warnings",
    "benchmark_id",
    "task_name",
    "run_name",
    "paper_id",
    "document_id",
    "doi",
    "source_span_id",
    "evidence_id",
    "source_text",
    "source_section",
    "provenance_type",
    "provenance_confidence",
    "provenance_confidence_rationale",
    "section_heading",
    "section_path",
    "section_type",
    "section_confidence",
    "reaction_family",
    "reaction_family_confidence",
    "reaction_family_signals",
    "reaction_family_scope",
    "paper_level_reaction_family",
    "reaction_family_conflict",
    "rule_text_class",
    "rule_maximum_supported_boundary",
    "support_hint_boundary",
    "paired_body_required",
    "caption_context_only",
    "rule_admissibility_status",
    "llm_model",
    "llm_maximum_supported_boundary",
    "trusted_llm_maximum_supported_boundary",
    "llm_more_permissive",
    "llm_more_conservative",
    "rule_needs_human_review",
    "llm_needs_human_review",
    "overall_needs_human_review",
    "review_priority_band",
    "review_trigger_flags",
    "needs_human_review",
    "human_reviewer_id",
    "human_notes",
)

TASK_SPECIFIC_FIELDS = {
    "source_span_classification": ("gold_text_class",),
    "validation_gate_extraction": (
        "rule_validation_isotope_15N",
        "rule_validation_blank_control",
        "rule_validation_NOx_control",
        "rule_validation_contamination_control",
        "rule_validation_quantification_method",
        "gold_isotope_15N",
        "gold_blank_control",
        "gold_NOx_control",
        "gold_contamination_control",
        "gold_quantification_method",
    ),
    "claim_rights_boundary_classification": (
        "gold_maximum_supported_boundary",
        "gold_admissibility_status",
    ),
    "hidden_tax_detection": (
        "detected_taxes",
        "hidden_tax",
        "llm_hidden_tax",
        "gold_hidden_tax",
    ),
    "required_control_prediction": (
        "missing_boundary_fields",
        "required_controls",
        "llm_required_controls",
        "gold_required_controls",
    ),
    "experiment_decision_ranking": (
        "rule_claim_type",
        "overclaim_risk_flags",
        "required_controls",
        "human_maximum_supported_boundary",
        "human_admissibility_status",
        "gold_experiment_decision",
        "gold_priority_binary",
    ),
}


def normalize_label(value: str, allowed: list[str] | tuple[str, ...], default: str | None = None) -> str:
    """Normalize a scalar label, applying default only to blank values."""

    text = str(value or "").strip()
    if not text and default is not None:
        return default
    return text


def normalize_multi_label(value: Any) -> list[str]:
    """Normalize CSV, JSON, or Python list labels into a deduped list."""

    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return _dedupe(_normalize_item(item) for item in value)
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
            return normalize_multi_label(parsed)
    parts = re.split(r"[;,|]", text)
    if len(parts) == 1:
        return _dedupe([_strip_outer_quotes(text)])
    return _dedupe(_strip_outer_quotes(part) for part in parts)


def validate_task_record(task_name: str, record: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate task-specific gold labels."""

    errors: list[str] = []
    if task_name not in BENCHMARK_TASKS:
        errors.append(f"unknown task_name: {task_name}")
        return False, errors
    if str(record.get("task_name") or "") != task_name:
        errors.append(f"record task_name does not match {task_name}")
    if not str(record.get("benchmark_id") or "").strip():
        errors.append("missing benchmark_id")

    if task_name == "source_span_classification":
        _validate_label(record, "gold_text_class", SOURCE_SPAN_LABELS, errors)
    elif task_name == "validation_gate_extraction":
        for field in VALIDATION_GATE_FIELDS:
            _validate_label(record, f"gold_{field}", VALIDATION_GATE_LABELS, errors)
    elif task_name == "claim_rights_boundary_classification":
        _validate_label(record, "gold_maximum_supported_boundary", BOUNDARY_LABELS, errors)
        if not str(record.get("gold_admissibility_status") or "").strip():
            errors.append("missing gold_admissibility_status")
    elif task_name == "hidden_tax_detection":
        _validate_multi(record, "gold_hidden_tax", HIDDEN_TAX_LABELS, errors)
    elif task_name == "required_control_prediction":
        _validate_multi(record, "gold_required_controls", REQUIRED_CONTROL_LABELS, errors)
    elif task_name == "experiment_decision_ranking":
        _validate_label(record, "gold_experiment_decision", EXPERIMENT_DECISION_LABELS, errors)
        if str(record.get("gold_priority_binary")) not in {"0", "1"} and record.get("gold_priority_binary") not in {0, 1}:
            errors.append("gold_priority_binary must be 0 or 1")

    return not errors, errors


def task_output_fields(task_name: str) -> list[str]:
    """Return stable output fields for a task."""

    if task_name not in BENCHMARK_TASKS:
        return list(COMMON_TASK_FIELDS)
    fields = list(COMMON_TASK_FIELDS)
    fields.extend(field for field in TASK_SPECIFIC_FIELDS[task_name] if field not in fields)
    return fields


def benchmark_record_id(record: dict[str, Any], task_name: str) -> str:
    """Create a stable benchmark record id for a source task row."""

    for key in ("audit_id", "evidence_id", "source_span_id", "span_id", "claim_id"):
        value = str(record.get(key) or "").strip()
        if value:
            return _sanitize_id(f"BB_{task_name}_{value}")
    return _sanitize_id(f"BB_{task_name}_TODO")


def _validate_label(record: dict[str, Any], field: str, allowed: tuple[str, ...], errors: list[str]) -> None:
    value = str(record.get(field) or "").strip()
    if value not in allowed:
        errors.append(f"invalid {field}: {record.get(field)}")


def _validate_multi(record: dict[str, Any], field: str, allowed: tuple[str, ...], errors: list[str]) -> None:
    for value in normalize_multi_label(record.get(field)):
        if value not in allowed:
            errors.append(f"invalid {field}: {value}")


def _normalize_item(item: Any) -> str:
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


def _sanitize_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "BB_TODO"
