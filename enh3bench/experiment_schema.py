"""Schema helpers for lab-constrained experiment routes and results."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any


ROUTE_TYPES = (
    "validation_gap_closure",
    "electrolyte_window",
    "interphase_resistance",
    "flow_wetting",
    "HOR_proton_economy",
    "product_state_accounting",
    "contamination_control",
    "stability_failure",
    "process_boundary_probe",
)

VARIABLE_TYPES = (
    "electrolyte",
    "water_content",
    "lithium_salt",
    "proton_donor",
    "current_density",
    "potential",
    "gas_flow",
    "liquid_flow",
    "pressure",
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
    "product_state_split",
    "electrolyte_color",
    "photo_before_after",
    "failure_mode",
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
)

RESULT_STATUS_LABELS = ("success", "partial", "failed", "invalid", "inconclusive")

ROUTE_REQUIRED_FIELDS = (
    "route_id",
    "run_name",
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
        "validation": "validation_gap_closure",
        "validation_gap": "validation_gap_closure",
        "electrolyte": "electrolyte_window",
        "interphase": "interphase_resistance",
        "resistance": "interphase_resistance",
        "flow": "flow_wetting",
        "gde": "flow_wetting",
        "hor": "HOR_proton_economy",
        "hor_proton_economy": "HOR_proton_economy",
        "product_state": "product_state_accounting",
        "contamination": "contamination_control",
        "stability": "stability_failure",
        "process": "process_boundary_probe",
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
        "full_cell_voltage": "",
        "anode_potential": "",
        "cathode_potential": "",
        "runtime_hours": "",
        "water_content": "",
        "EIS_summary": "",
        "gas_phase_NH3": "",
        "liquid_NH4": "",
        "nitrate": "",
        "nitrite": "",
        "NOx": "",
        "H2_observation": "",
        "product_state_split": "",
        "electrolyte_color": "",
        "photo_record": "",
        "failure_mode": "",
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
