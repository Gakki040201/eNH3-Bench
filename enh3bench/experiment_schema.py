"""Schema helpers for lab-constrained experiment routes and results."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any


ROUTE_TYPES = (
    "baseline_repeatability",
    "validation_gap_closure",
    "electrolyte_window",
    "water_content_window",
    "proton_donor_window",
    "salt_solvent_window",
    "operating_field_matrix",
    "interphase_resistance",
    "flow_wetting",
    "HOR_proton_economy",
    "outlet_product_split",
    "product_state_accounting",
    "contamination_control",
    "stability_failure",
    "process_boundary_probe",
    "postmortem_failure_analysis",
)

VARIABLE_TYPES = (
    "baseline_condition",
    "electrolyte",
    "water_content",
    "water_ppm",
    "lithium_salt",
    "donor_identity",
    "donor_concentration",
    "Li_salt_concentration",
    "solvent_drying_state",
    "proton_donor",
    "current_density",
    "potential",
    "pump_speed",
    "N2_flow",
    "H2_flow",
    "Ar_flow",
    "gas_flow",
    "liquid_flow",
    "pressure",
    "active_area",
    "SSC_state",
    "PtAuSSC_state",
    "sampling_timepoint",
    "HOR_on_off",
    "GDE_wetting",
    "reactor_geometry",
    "runtime",
    "capture_route",
    "control_experiment",
)

ROUTE_PRIORITY_LABELS = (
    "priority_experiment",
    "control_required",
    "do_after_controls",
    "defer_until_capability_available",
    "discard_as_secondary",
    "insufficient_evidence",
    "needs_human_review",
)

MEASUREMENT_LABELS = (
    "FE",
    "NH3_yield",
    "current_density",
    "OCV",
    "pump_speed",
    "full_cell_voltage",
    "anode_potential",
    "cathode_potential",
    "runtime",
    "EIS",
    "CV",
    "water_content",
    "gas_phase_NH3",
    "liquid_NH4",
    "nitrate",
    "nitrite",
    "NOx",
    "gas_phase_NOx",
    "feed_gas_impurity",
    "H2",
    "H2_observation",
    "product_state_split",
    "electrolyte_color",
    "photo_before_after",
    "failure_mode",
    "electrolyte_resistance_before",
    "electrolyte_resistance_after",
    "SSC_photo_before",
    "SSC_photo_after",
    "PtAuSSC_photo_before",
    "PtAuSSC_photo_after",
    "IC_NH4",
    "HCl_trap_NH4",
    "SSC_soak_solution_NH4",
    "water_content_before",
    "water_content_mid",
    "water_content_after",
    "gas_line_status",
    "liquid_line_status",
    "leak_status",
    "back_suction_status",
    "pump_status",
    "operator_failure_note",
)

CONTROL_LABELS = (
    "15N2 isotope validation",
    "Ar blank",
    "N2-free blank",
    "NOx/nitrate/nitrite screening",
    "background NH3 control",
    "electrolyte blank",
    "H2-off control",
    "HOR-off control",
    "gas/liquid product accounting",
    "wetting/flooding diagnosis",
    "voltage/current/runtime reporting",
    "solvent inventory/recycle reporting",
    "primary body text pairing",
    "electrolyte resistance before/after",
    "SSC/PtAuSSC before-after photos",
    "three water-content measurements",
    "HCl trap accounting",
    "SSC soak solution accounting",
    "gas-line blank",
    "liquid-line blank",
)

RESULT_STATUS_LABELS = ("success", "partial", "failed", "invalid", "inconclusive")

EXPERIMENT_SCHEMA_VERSION = "1.1"
EXECUTION_UNIT = "route_condition_replicate"

EXECUTION_STAGES = (
    "baseline_establishment",
    "admission_and_contamination",
    "electrolyte_operating_window",
    "interphase_flow_product_state",
    "hor_and_process_probe",
    "failure_triggered_postmortem",
)

STAGE_GATE_STATUSES = (
    "pending",
    "actionable",
    "blocked",
    "waived",
    "completed",
    "event_triggered",
    "non_executable",
)

ROUTE_STAGE_MAP = {
    "baseline_repeatability": 0,
    "validation_gap_closure": 1,
    "contamination_control": 1,
    "electrolyte_window": 2,
    "water_content_window": 2,
    "proton_donor_window": 2,
    "salt_solvent_window": 2,
    "operating_field_matrix": 2,
    "interphase_resistance": 3,
    "flow_wetting": 3,
    "outlet_product_split": 3,
    "product_state_accounting": 3,
    "stability_failure": 3,
    "HOR_proton_economy": 4,
    "process_boundary_probe": 4,
    "postmortem_failure_analysis": 5,
}

RESULT_IDENTITY_FIELDS = (
    "execution_id",
    "condition_id",
    "condition_label",
    "condition_values_json",
    "replicate_id",
    "replicate_index",
    "independent_replicate",
    "assembly_id",
    "cell_build_id",
    "electrolyte_batch_id",
    "electrode_batch_id",
    "gas_batch_id",
    "experiment_start_utc",
    "experiment_end_utc",
    "timepoint_id",
    "technical_repeat_id",
)

ROUTE_REQUIRED_FIELDS = (
    "schema_version",
    "route_id",
    "run_name",
    "reaction_family",
    "reaction_profile",
    "lab_demonstration_allowed",
    "route_type",
    "execution_stage",
    "stage_rank",
    "within_stage_score",
    "stage_gate_status",
    "prerequisite_route_ids",
    "blocked_by_route_ids",
    "route_family_id",
    "parent_route_id",
    "child_route_ids",
    "is_route_group",
    "mutually_exclusive_route_ids",
    "shared_evidence_group",
    "execution_order_reason",
    "default_replicate_count",
    "minimum_valid_replicates",
    "replicate_type",
    "independent_assembly_required",
    "execution_unit",
    "priority_label",
    "priority_score",
    "hypothesis",
    "literature_rationale",
    "boundary_gap_targeted",
    "hidden_tax_targeted",
    "variable_type",
    "experimental_matrix",
    "fixed_conditions",
    "required_controls",
    "feasible_controls",
    "infeasible_controls",
    "mandatory_measurements",
    "optional_measurements",
    "feasible_measurements",
    "infeasible_measurements",
    "measurement_capability_warnings",
    "measurement_feasibility_status",
    "alternative_measurement_plan",
    "boundary_not_closed_due_to_unavailable_measurements",
    "required_measurements",
    "success_criteria",
    "failure_criteria",
    "stopping_rules",
    "expected_outcomes",
    "failure_diagnosis_tree",
    "SOP_anchor_points",
    "minimum_report_fields",
    "boundary_upgrade_if_successful",
    "boundary_not_closed_even_if_successful",
    "required_raw_records_to_save",
    "lab_capability_warnings",
    "safety_notes",
    "estimated_difficulty",
    "estimated_cost_level",
    "estimated_time_level",
    "human_review_required",
    "llm_used",
    "llm_model",
    "llm_rationale",
    "created_at_utc",
)


def normalize_route_label(value: str) -> str:
    """Normalize route labels to canonical route types when possible."""

    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold()).strip("_")
    aliases = {
        "baseline": "baseline_repeatability",
        "repeatability": "baseline_repeatability",
        "validation": "validation_gap_closure",
        "validation_gap": "validation_gap_closure",
        "electrolyte": "electrolyte_window",
        "water": "water_content_window",
        "water_content": "water_content_window",
        "donor": "proton_donor_window",
        "proton_donor": "proton_donor_window",
        "salt_solvent": "salt_solvent_window",
        "operating_field": "operating_field_matrix",
        "interphase": "interphase_resistance",
        "resistance": "interphase_resistance",
        "flow": "flow_wetting",
        "gde": "flow_wetting",
        "hor": "HOR_proton_economy",
        "hor_proton_economy": "HOR_proton_economy",
        "outlet": "outlet_product_split",
        "outlet_product": "outlet_product_split",
        "product_state": "product_state_accounting",
        "contamination": "contamination_control",
        "stability": "stability_failure",
        "process": "process_boundary_probe",
        "postmortem": "postmortem_failure_analysis",
        "failure_analysis": "postmortem_failure_analysis",
    }
    candidate = aliases.get(text, str(value or "").strip())
    return candidate if candidate in ROUTE_TYPES else "validation_gap_closure"


def normalize_measurement_list(value: Any) -> list[str]:
    return [item for item in _normalize_multi(value) if item in MEASUREMENT_LABELS]


def normalize_control_list(value: Any) -> list[str]:
    return [item for item in _normalize_multi(value) if item in CONTROL_LABELS]


def validate_experiment_route(route: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate a structured experiment route."""

    errors: list[str] = []
    if not isinstance(route, dict):
        return False, ["route must be a dict"]
    for field in ROUTE_REQUIRED_FIELDS:
        if field not in route:
            errors.append(f"missing field: {field}")
    if str(route.get("route_type") or "") not in ROUTE_TYPES:
        errors.append(f"invalid route_type: {route.get('route_type')}")
    stage_rank = route.get("stage_rank")
    try:
        stage_rank = int(stage_rank)
    except (TypeError, ValueError):
        errors.append("stage_rank must be an integer")
        stage_rank = -1
    if stage_rank not in range(len(EXECUTION_STAGES)):
        errors.append(f"invalid stage_rank: {route.get('stage_rank')}")
    elif str(route.get("execution_stage") or "") != EXECUTION_STAGES[stage_rank]:
        errors.append("execution_stage does not match stage_rank")
    if str(route.get("stage_gate_status") or "") not in STAGE_GATE_STATUSES:
        errors.append(f"invalid stage_gate_status: {route.get('stage_gate_status')}")
    try:
        float(route.get("within_stage_score"))
    except (TypeError, ValueError):
        errors.append("within_stage_score must be numeric")
    if not isinstance(route.get("is_route_group"), bool):
        errors.append("is_route_group must be bool")
    if str(route.get("priority_label") or "") not in ROUTE_PRIORITY_LABELS:
        errors.append(f"invalid priority_label: {route.get('priority_label')}")
    try:
        int(route.get("priority_score"))
    except (TypeError, ValueError):
        errors.append("priority_score must be an integer")
    for field in ("default_replicate_count", "minimum_valid_replicates"):
        try:
            if int(route.get(field)) < 1:
                errors.append(f"{field} must be at least 1")
        except (TypeError, ValueError):
            errors.append(f"{field} must be an integer")
    if str(route.get("execution_unit") or "") != EXECUTION_UNIT:
        errors.append(f"execution_unit must be {EXECUTION_UNIT}")
    if str(route.get("variable_type") or "") not in VARIABLE_TYPES:
        errors.append(f"invalid variable_type: {route.get('variable_type')}")
    for control in _normalize_multi(route.get("required_controls")):
        if control not in CONTROL_LABELS:
            errors.append(f"invalid required_control: {control}")
    for measurement in _normalize_multi(route.get("required_measurements")):
        if measurement not in MEASUREMENT_LABELS:
            errors.append(f"invalid required_measurement: {measurement}")
    if str(route.get("measurement_feasibility_status") or "") not in {"feasible", "partial", "infeasible"}:
        errors.append(f"invalid measurement_feasibility_status: {route.get('measurement_feasibility_status')}")
    for field in (
        "source_basis_ids",
        "linked_paper_ids",
        "linked_source_span_ids",
        "required_controls",
        "prerequisite_route_ids",
        "blocked_by_route_ids",
        "child_route_ids",
        "mutually_exclusive_route_ids",
        "mandatory_measurements",
        "optional_measurements",
        "feasible_measurements",
        "infeasible_measurements",
        "measurement_capability_warnings",
        "alternative_measurement_plan",
        "boundary_not_closed_due_to_unavailable_measurements",
        "required_measurements",
    ):
        if field in route and not isinstance(route.get(field), list):
            errors.append(f"{field} must be list")
    return not errors, errors


def empty_experiment_result_template(
    route: dict[str, Any],
    condition: dict[str, Any] | None = None,
    replicate_index: int = 1,
) -> dict[str, Any]:
    """Return an editable empty result template row for a route."""

    route_id = str(route.get("route_id") or "TODO")
    condition = dict(condition or _first_condition(route))
    condition_id = _identifier(condition.get("condition_id") or "baseline")
    replicate_index = max(1, int(replicate_index or 1))
    replicate_id = f"rep_{replicate_index:02d}"
    execution_id = f"EXEC_{route_id}_{condition_id}_{replicate_id}"
    return {
        "schema_version": str(route.get("schema_version") or EXPERIMENT_SCHEMA_VERSION),
        "execution_unit": str(route.get("execution_unit") or EXECUTION_UNIT),
        "execution_id": execution_id,
        "experiment_id": f"EXP_{route_id}_{condition_id}_{replicate_id}",
        "route_id": route_id if route_id != "TODO" else "",
        "run_name": str(route.get("run_name") or ""),
        "date": "",
        "operator": "",
        "condition_id": condition_id,
        "condition_label": str(condition.get("condition_label") or condition.get("label") or condition_id),
        "condition_values_json": json.dumps(condition, ensure_ascii=True, sort_keys=True),
        "experimental_matrix_value": str(condition.get("planned_value") or condition.get("value") or ""),
        "replicate_id": replicate_id,
        "replicate_index": replicate_index,
        "independent_replicate": str(route.get("replicate_type") or "independent") == "independent",
        "replicate_type": str(route.get("replicate_type") or "independent"),
        "independent_assembly_required": bool(route.get("independent_assembly_required")),
        "assembly_id": "",
        "cell_build_id": "",
        "electrolyte_batch_id": "",
        "electrode_batch_id": "",
        "gas_batch_id": "",
        "experiment_start_utc": "",
        "experiment_end_utc": "",
        "timepoint_id": "",
        "technical_repeat_id": "",
        "FE": "",
        "NH3_yield": "",
        "current_density": "",
        "OCV": "",
        "pump_speed": "",
        "full_cell_voltage": "",
        "anode_potential": "",
        "cathode_potential": "",
        "runtime_hours": "",
        "water_content": "",
        "water_content_before": "",
        "water_content_mid": "",
        "water_content_after": "",
        "EIS_summary": "",
        "electrolyte_resistance_before": "",
        "electrolyte_resistance_after": "",
        "gas_phase_NH3": "",
        "liquid_NH4": "",
        "IC_NH4": "",
        "HCl_trap_NH4": "",
        "SSC_soak_solution_NH4": "",
        "nitrate": "",
        "nitrite": "",
        "NOx": "",
        "gas_phase_NOx": "",
        "feed_gas_impurity": "",
        "H2_observation": "",
        "product_state_split": "",
        "electrolyte_color": "",
        "photo_record": "",
        "SSC_photo_before": "",
        "SSC_photo_after": "",
        "PtAuSSC_photo_before": "",
        "PtAuSSC_photo_after": "",
        "gas_line_status": "",
        "liquid_line_status": "",
        "leak_status": "",
        "back_suction_status": "",
        "pump_status": "",
        "failure_mode": "",
        "SOP_deviation": "",
        "operator_failure_note": "",
        "controls_completed": "",
        "controls_failed": "",
        "required_controls": json.dumps(route.get("required_controls") or [], ensure_ascii=True),
        "required_measurements": json.dumps(route.get("required_measurements") or [], ensure_ascii=True),
        "success_status": "",
        "invalid_reason": "",
        "notes": "",
    }


def expand_route_execution_rows(
    route: dict[str, Any],
    baseline_replicates: int = 3,
    default_replicates: int = 1,
    expand_matrix: bool = True,
) -> list[dict[str, Any]]:
    """Expand one route into editable condition-by-independent-replicate rows."""

    route_type = str(route.get("route_type") or "")
    conditions = [dict(item) for item in route.get("experimental_matrix") or [] if isinstance(item, dict)]
    if route_type == "baseline_repeatability":
        conditions = [_canonical_baseline_condition(route)]
        replicate_count = max(1, int(baseline_replicates or 3))
    else:
        conditions = conditions or [_canonical_baseline_condition(route)]
        replicate_count = max(
            1,
            int(route.get("default_replicate_count") or 1),
            int(default_replicates or 1),
        )
    if not expand_matrix:
        conditions = conditions[:1]

    return [
        empty_experiment_result_template(route, condition=condition, replicate_index=replicate_index)
        for condition in conditions
        for replicate_index in range(1, replicate_count + 1)
    ]


def expand_routes_to_result_rows(
    routes: list[dict[str, Any]],
    baseline_replicates: int = 3,
    default_replicates: int = 1,
    expand_matrix: bool = True,
) -> list[dict[str, Any]]:
    """Expand routes while keeping baseline repeatability rows first."""

    ordered = sorted(routes, key=lambda route: str(route.get("route_type") or "") != "baseline_repeatability")
    rows: list[dict[str, Any]] = []
    for route in ordered:
        if bool(route.get("is_route_group")) or str(route.get("stage_gate_status") or "") == "non_executable":
            continue
        rows.extend(
            expand_route_execution_rows(
                route,
                baseline_replicates=baseline_replicates,
                default_replicates=default_replicates,
                expand_matrix=expand_matrix,
            )
        )
    return rows


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _first_condition(route: dict[str, Any]) -> dict[str, Any]:
    matrix = route.get("experimental_matrix") or []
    if matrix and isinstance(matrix[0], dict):
        return dict(matrix[0])
    return _canonical_baseline_condition(route)


def _canonical_baseline_condition(route: dict[str, Any]) -> dict[str, Any]:
    for condition in route.get("experimental_matrix") or []:
        if isinstance(condition, dict) and str(condition.get("condition_id") or "").casefold() == "baseline":
            result = dict(condition)
            result["condition_id"] = "baseline"
            result.setdefault("condition_label", "Baseline")
            return result
    return {
        "condition_id": "baseline",
        "condition_label": "Baseline",
        "variable_type": str(route.get("variable_type") or "baseline_condition"),
        "planned_value": "current lab baseline",
    }


def _identifier(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip()).strip("_")
    return text or "baseline"


def _normalize_multi(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return _dedupe(str(item).strip() for item in value)
    if isinstance(value, dict):
        return [json.dumps(value, ensure_ascii=True, sort_keys=True)] if value else []
    text = str(value).strip()
    if not text or text.casefold() in {"none", "null", "nan", "n/a", "na", "[]"}:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return _normalize_multi(parsed)
    return _dedupe(part.strip().strip("'\"") for part in re.split(r"[;,|]", text) if part.strip())


def _dedupe(items: Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output
