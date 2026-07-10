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

ROUTE_REQUIRED_FIELDS = (
    "route_id",
    "run_name",
    "reaction_family",
    "reaction_profile",
    "lab_demonstration_allowed",
    "route_type",
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
    if str(route.get("priority_label") or "") not in ROUTE_PRIORITY_LABELS:
        errors.append(f"invalid priority_label: {route.get('priority_label')}")
    try:
        int(route.get("priority_score"))
    except (TypeError, ValueError):
        errors.append("priority_score must be an integer")
    if str(route.get("variable_type") or "") not in VARIABLE_TYPES:
        errors.append(f"invalid variable_type: {route.get('variable_type')}")
    for control in _normalize_multi(route.get("required_controls")):
        if control not in CONTROL_LABELS:
            errors.append(f"invalid required_control: {control}")
    for measurement in _normalize_multi(route.get("required_measurements")):
        if measurement not in MEASUREMENT_LABELS:
            errors.append(f"invalid required_measurement: {measurement}")
    for field in ("source_basis_ids", "linked_paper_ids", "linked_source_span_ids", "required_controls", "required_measurements"):
        if field in route and not isinstance(route.get(field), list):
            errors.append(f"{field} must be list")
    return not errors, errors


def empty_experiment_result_template(route: dict[str, Any]) -> dict[str, Any]:
    """Return an editable empty result template row for a route."""

    return {
        "experiment_id": f"EXP_{route.get('route_id') or 'TODO'}",
        "route_id": str(route.get("route_id") or ""),
        "run_name": str(route.get("run_name") or ""),
        "date": "",
        "operator": "",
        "condition_id": "",
        "experimental_matrix_value": "",
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


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
