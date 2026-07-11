"""Rule-based lab-constrained experiment route planner."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
import re
from pathlib import Path
from typing import Any

from enh3bench.experiment_schema import (
    CONTROL_LABELS,
    EXECUTION_STAGES,
    MEASUREMENT_LABELS,
    ROUTE_STAGE_MAP,
    ROUTE_TYPES,
    validate_experiment_route,
    EXPERIMENT_SCHEMA_VERSION,
    EXECUTION_UNIT,
    utc_now,
)
from enh3bench.lab_profile import (
    capability_available,
    feasible_controls,
    feasible_measurements,
    infeasible_controls,
    infeasible_measurements,
    measurement_feasibility_status,
    missing_capabilities_for_controls,
    missing_capabilities_for_measurements,
)
from enh3bench.ledger_router import load_jsonl
from enh3bench.llm_clients.base import sanitize_model_name_for_path
from enh3bench.reaction_profiles import (
    experimental_demonstration_allowed,
    get_reaction_profile,
    infer_reaction_family_detailed,
    normalize_reaction_family,
    profile_hidden_taxes,
    profile_route_types,
)


_VARIABLE_SCREENING_ROUTES = {
    "water_content_window",
    "proton_donor_window",
    "salt_solvent_window",
    "operating_field_matrix",
    "electrolyte_window",
    "interphase_resistance",
    "flow_wetting",
    "HOR_proton_economy",
    "outlet_product_split",
}

_OPTIONAL_MEASUREMENTS_BY_ROUTE = {
    "baseline_repeatability": {"OCV", "pump_speed", "water_content_mid", "failure_mode"},
    "validation_gap_closure": {"SSC_soak_solution_NH4", "gas_line_status", "liquid_line_status"},
    "electrolyte_window": {"electrolyte_color"},
    "water_content_window": {"electrolyte_color"},
    "proton_donor_window": {"electrolyte_color"},
    "salt_solvent_window": {"electrolyte_color"},
    "interphase_resistance": {
        "SSC_photo_before",
        "SSC_photo_after",
        "PtAuSSC_photo_before",
        "PtAuSSC_photo_after",
        "failure_mode",
        "electrolyte_color",
    },
    "flow_wetting": {"leak_status", "back_suction_status", "pump_status", "failure_mode"},
    "HOR_proton_economy": {"H2_observation"},
    "postmortem_failure_analysis": {"electrolyte_color", "operator_failure_note"},
}


def load_boundary_inputs(run_name: str, model: str | None = None) -> dict[str, Any]:
    """Load BoundaryLedger, hidden-tax, optional LLM, and human-audit inputs."""

    boundary_dir = Path("data") / "boundary_ledger" / run_name
    llm_dir = Path("data") / "llm_verification" / run_name
    inputs: dict[str, Any] = {
        "run_name": run_name,
        "claim_rights": load_jsonl(boundary_dir / "claim_rights_ledger.jsonl"),
        "hidden_tax": load_jsonl(boundary_dir / "hidden_tax_ledger.jsonl"),
        "llm_verified": [],
        "human_audit": load_jsonl(Path("data") / "human_audit" / run_name / "reviewed_audit_records.jsonl"),
    }
    if model:
        inputs["llm_verified"] = load_jsonl(llm_dir / sanitize_model_name_for_path(model) / "llm_verified_claims.jsonl")
    elif llm_dir.exists():
        records: list[dict[str, Any]] = []
        for model_dir in sorted(path for path in llm_dir.iterdir() if path.is_dir()):
            records.extend(load_jsonl(model_dir / "llm_verified_claims.jsonl"))
        inputs["llm_verified"] = records
    return inputs


def merge_planning_records(boundary_inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge planning signals by evidence/span identity."""

    hidden_by_key = _index(boundary_inputs.get("hidden_tax") or [])
    llm_by_key = _index(boundary_inputs.get("llm_verified") or [])
    human_by_key = _index(boundary_inputs.get("human_audit") or [])
    merged: list[dict[str, Any]] = []
    for claim in boundary_inputs.get("claim_rights") or []:
        row = dict(claim)
        key = _record_key(row)
        hidden = hidden_by_key.get(key, {})
        llm = llm_by_key.get(key, {})
        human = human_by_key.get(key, {})
        family = _record_reaction_family(row, hidden)
        profile = get_reaction_profile(family)
        family_meta = _reaction_family_metadata(row, hidden)
        row["reaction_family"] = family
        row.update(family_meta)
        row["reaction_profile_name"] = profile["reaction_family"]
        row["reaction_profile"] = _reaction_profile_summary(profile)
        row["detected_taxes"] = hidden.get("detected_taxes") or row.get("detected_taxes") or row.get("hidden_tax") or []
        row["hidden_tax_record"] = hidden
        row["llm_record"] = llm
        row["human_audit_record"] = human
        row["human_experiment_decision"] = human.get("human_experiment_decision") or ""
        row["human_review_status"] = human.get("human_review_status") or ""
        row["llm_more_permissive"] = bool(llm.get("llm_more_permissive") or row.get("llm_more_permissive"))
        row["llm_more_conservative"] = bool(llm.get("llm_more_conservative") or row.get("llm_more_conservative"))
        row["llm_audit_flags"] = llm.get("llm_audit_flags") or row.get("llm_audit_flags") or []
        row["trusted_llm_maximum_supported_boundary"] = llm.get("trusted_llm_maximum_supported_boundary") or ""
        merged.append(row)
    return merged


def identify_actionable_gaps(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Identify route-planning gaps from merged BoundaryLedger records."""

    gaps: list[dict[str, Any]] = []
    for record in records:
        base = _gap_base(record)
        family = str(base.get("reaction_family") or "unclear")
        gates = record.get("validation_gates") if isinstance(record.get("validation_gates"), dict) else {}
        for gate, gap_type in _validation_gap_specs(family):
            if str(gates.get(gate) or "").casefold() not in {"yes", "explicit", "true", "present"}:
                gaps.append({**base, "gap_type": gap_type, "route_type_hint": _profile_route_hint(family, "validation_gap_closure")})

        missing_fields = _list_values(record.get("missing_boundary_fields"))
        for missing in missing_fields:
            normalized = str(missing).casefold()
            route_type = "validation_gap_closure"
            if any(token in normalized for token in ["voltage", "current", "runtime", "product state"]):
                route_type = "outlet_product_split" if family == "LiNRR" and "product state" in normalized else "product_state_accounting" if "product state" in normalized else "operating_field_matrix"
            if "capture" in normalized:
                route_type = "outlet_product_split" if family == "LiNRR" else "product_state_accounting"
            gaps.append({**base, "gap_type": f"missing {missing}", "route_type_hint": _profile_route_hint(family, route_type)})

        for tax in _list_values(record.get("detected_taxes")):
            if family != "unclear" and tax not in profile_hidden_taxes(family):
                continue
            route_type = _route_for_hidden_tax(tax)
            gaps.append({**base, "gap_type": tax, "route_type_hint": _profile_route_hint(family, route_type), "hidden_tax": tax})
            if family == "LiNRR" and tax == "solvent_management_tax":
                for extra_route in ("water_content_window", "proton_donor_window", "salt_solvent_window"):
                    gaps.append({**base, "gap_type": f"{tax} via {extra_route}", "route_type_hint": extra_route, "hidden_tax": tax})

        flags = _list_values(record.get("overclaim_risk_flags")) + _list_values(record.get("llm_audit_flags"))
        if record.get("text_class_provenance_conflict") or "text_class_provenance_conflict" in flags:
            gaps.append({**base, "gap_type": "provenance conflict", "route_type_hint": "validation_gap_closure"})
        if record.get("llm_more_permissive") or "llm_more_permissive_than_rule" in flags:
            gaps.append({**base, "gap_type": "LLM more permissive", "route_type_hint": "validation_gap_closure", "llm_disagreement": True})
        if any("overclaim" in flag or "plant_facing" in flag for flag in flags):
            gaps.append(
                {
                    **base,
                    "gap_type": "process/reaction boundary overclaim risk",
                    "route_type_hint": _profile_route_hint(family, "process_boundary_probe"),
                }
            )

        text = _record_text(record)
        if (family == "unclear" or "interphase_resistance" in profile_route_types(family)) and _contains_any(
            text, ["sei", "interphase", "resistance", "impedance", "renewal"]
        ):
            gaps.append({**base, "gap_type": "interphase/resistance term", "route_type_hint": "interphase_resistance"})
        if (family == "unclear" or "flow_wetting" in profile_route_types(family)) and _contains_any(
            text, ["flow", "gde", "ssc", "outlet", "wetting", "flooding"]
        ):
            gaps.append({**base, "gap_type": "flow/GDE/wetting term", "route_type_hint": "flow_wetting"})
        if (family == "unclear" or "HOR_proton_economy" in profile_route_types(family)) and _contains_any(
            text, [" hor", "hydrogen oxidation", "h2", "proton economy"]
        ):
            gaps.append({**base, "gap_type": "HOR/proton economy term", "route_type_hint": "HOR_proton_economy"})
        if family == "LiNRR" and _contains_any(
            text,
            ["failure_mode", "failure mode", "electrolyte color", "leak", "back suction", "pump failure", "low fe", "too low", "high resistance"],
        ):
            gaps.append({**base, "gap_type": "postmortem/failure signal", "route_type_hint": "postmortem_failure_analysis"})
    return gaps


def propose_rule_based_routes(
    actionable_gaps: list[dict[str, Any]],
    lab_profile: dict[str, Any],
    run_name: str,
    reaction_family: str | None = None,
    include_families: list[str] | None = None,
    lab_demo_only: bool = False,
    require_baseline_first: bool = False,
    include_sop_fields: bool = True,
    respect_stage_gates: bool = True,
) -> list[dict[str, Any]]:
    """Generate deterministic route cards from actionable gaps and lab profile."""

    filtered_gaps = _filter_gaps_by_reaction_family(actionable_gaps, lab_profile, reaction_family, include_families, lab_demo_only)
    if (
        require_baseline_first
        and _baseline_family_enabled(lab_profile, reaction_family, include_families, lab_demo_only)
        and (filtered_gaps or not actionable_gaps)
    ):
        filtered_gaps.append(_baseline_gap(run_name))
    by_route: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for gap in filtered_gaps:
        route_type = str(gap.get("route_type_hint") or "validation_gap_closure")
        if route_type in ROUTE_TYPES:
            by_route[(str(gap.get("reaction_family") or "unclear"), route_type)].append(gap)
    _expand_electrolyte_route_hierarchy(by_route)

    routes: list[dict[str, Any]] = []
    route_specs = [
        ("baseline_repeatability", "Li-NRR baseline repeatability check", "baseline_condition", ["three water-content measurements", "electrolyte resistance before/after", "SSC/PtAuSSC before-after photos", "voltage/current/runtime reporting"], ["FE", "NH3_yield", "OCV", "pump_speed", "full_cell_voltage", "current_density", "water_content_before", "water_content_mid", "water_content_after", "electrolyte_resistance_before", "electrolyte_resistance_after", "IC_NH4", "failure_mode"], "baseline reproducibility before variable screening"),
        ("validation_gap_closure", "Validation-gate closure panel", "control_experiment", ["15N2 isotope validation", "Ar blank", "N2-free blank", "NOx/nitrate/nitrite screening", "background NH3 control"], ["NH3_yield", "nitrate", "nitrite", "gas_phase_NOx", "feed_gas_impurity", "product_state_split", "IC_NH4", "HCl_trap_NH4", "SSC_soak_solution_NH4", "gas_line_status", "liquid_line_status"], "missing validation gates"),
        ("electrolyte_window", "Electrolyte water/proton donor window", "water_content", ["electrolyte blank", "Ar blank", "NOx/nitrate/nitrite screening"], ["FE", "NH3_yield", "full_cell_voltage", "EIS", "water_content", "electrolyte_color"], "solvent_management_tax"),
        ("water_content_window", "Li-NRR water-content window", "water_ppm", ["three water-content measurements", "electrolyte blank", "Ar blank", "NOx/nitrate/nitrite screening"], ["FE", "NH3_yield", "full_cell_voltage", "EIS", "water_content_before", "water_content_mid", "water_content_after", "electrolyte_color", "IC_NH4"], "solvent_management_tax and water/proton ambiguity"),
        ("proton_donor_window", "Li-NRR proton-donor identity/concentration window", "donor_identity", ["electrolyte blank", "Ar blank", "NOx/nitrate/nitrite screening", "three water-content measurements"], ["FE", "NH3_yield", "full_cell_voltage", "EIS", "water_content_before", "water_content_mid", "water_content_after", "electrolyte_color", "IC_NH4"], "proton donor ambiguity"),
        ("salt_solvent_window", "Li salt and solvent drying-state window", "Li_salt_concentration", ["three water-content measurements", "electrolyte blank", "Ar blank", "NOx/nitrate/nitrite screening"], ["FE", "NH3_yield", "full_cell_voltage", "EIS", "water_content_before", "water_content_after", "electrolyte_color", "IC_NH4"], "Li salt/solvent boundary sensitivity"),
        ("operating_field_matrix", "Operating-field voltage/current/runtime matrix", "potential", ["voltage/current/runtime reporting", "electrolyte resistance before/after"], ["FE", "NH3_yield", "full_cell_voltage", "current_density", "runtime", "EIS", "electrolyte_resistance_before", "electrolyte_resistance_after"], "operating-field disclosure gap"),
        ("interphase_resistance", "Interphase resistance and renewal diagnostic", "runtime", ["Ar blank", "voltage/current/runtime reporting", "electrolyte resistance before/after", "SSC/PtAuSSC before-after photos"], ["EIS", "full_cell_voltage", "FE", "NH3_yield", "electrolyte_resistance_before", "electrolyte_resistance_after", "SSC_photo_before", "SSC_photo_after", "PtAuSSC_photo_before", "PtAuSSC_photo_after", "failure_mode", "electrolyte_color"], "resistance_or_renewal_tax"),
        ("flow_wetting", "Flow/GDE wetting and outlet product-state map", "pump_speed", ["gas/liquid product accounting", "wetting/flooding diagnosis", "gas-line blank", "liquid-line blank"], ["gas_phase_NH3", "liquid_NH4", "product_state_split", "leak_status", "back_suction_status", "pump_status", "full_cell_voltage", "failure_mode"], "wetting_outlet_capture_tax"),
        ("HOR_proton_economy", "HOR on/off proton-economy boundary test", "H2_flow", ["H2-off control", "HOR-off control", "voltage/current/runtime reporting"], ["full_cell_voltage", "anode_potential", "cathode_potential", "FE", "NH3_yield", "H2", "H2_observation", "product_state_split"], "hydrogen_logistics_tax"),
        ("outlet_product_split", "Gas/liquid/trap/SSC ammonia product split", "capture_route", ["HCl trap accounting", "gas/liquid product accounting", "SSC soak solution accounting"], ["gas_phase_NH3", "liquid_NH4", "HCl_trap_NH4", "SSC_soak_solution_NH4", "product_state_split"], "outlet product-state accounting gap"),
        ("product_state_accounting", "Gas/liquid ammonia accounting and capture boundary", "capture_route", ["gas/liquid product accounting", "solvent inventory/recycle reporting"], ["gas_phase_NH3", "liquid_NH4", "product_state_split", "water_content"], "product_state/capture gap"),
        ("contamination_control", "NOx/background ammonia contamination stress test", "control_experiment", ["NOx/nitrate/nitrite screening", "background NH3 control", "Ar blank", "N2-free blank", "electrolyte blank"], ["nitrate", "nitrite", "gas_phase_NOx", "feed_gas_impurity", "liquid_NH4"], "contamination_tax"),
        ("stability_failure", "Runtime stability and first-failure boundary test", "runtime", ["voltage/current/runtime reporting", "Ar blank"], ["runtime", "full_cell_voltage", "FE", "NH3_yield", "EIS", "failure_mode"], "stability/failure disclosure gap"),
        ("process_boundary_probe", "Process-boundary accounting probe", "capture_route", ["gas/liquid product accounting", "solvent inventory/recycle reporting", "voltage/current/runtime reporting"], ["product_state_split", "full_cell_voltage", "water_content", "gas_phase_NH3", "liquid_NH4"], "process boundary overclaim risk"),
        ("postmortem_failure_analysis", "Postmortem failure and operator-note analysis", "sampling_timepoint", ["electrolyte resistance before/after", "SSC/PtAuSSC before-after photos"], ["failure_mode", "electrolyte_color", "SSC_photo_before", "SSC_photo_after", "PtAuSSC_photo_before", "PtAuSSC_photo_after", "electrolyte_resistance_before", "electrolyte_resistance_after", "operator_failure_note"], "failure-mode diagnosis"),
    ]
    route_spec_by_type = {route_type: spec for route_type, *spec in route_specs}
    for family, route_type in sorted(by_route):
        spec = route_spec_by_type.get(route_type)
        if not spec:
            continue
        title, variable_type, controls, measurements, target = spec
        routes.append(
            _build_route(
                run_name,
                family,
                route_type,
                title,
                variable_type,
                controls,
                measurements,
                target,
                by_route[(family, route_type)],
                lab_profile,
                include_sop_fields=include_sop_fields,
            )
        )
    routes = _finalize_route_hierarchy(routes)
    routes = apply_stage_gates(routes, _gate_context_from_records(filtered_gaps), respect_stage_gates=respect_stage_gates)
    return rank_routes(routes)


def rank_routes(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort routes by gate status, stage, priority band, and within-stage score."""

    return sorted(routes, key=_route_sort_key)


def filter_routes(
    routes: list[dict[str, Any]],
    min_score: int | None = None,
    priority_only: bool = False,
    include_blocked_routes: bool = True,
    only_actionable_routes: bool = False,
) -> list[dict[str, Any]]:
    """Filter route list for CLI output."""

    filtered = list(routes)
    if min_score is not None:
        filtered = [route for route in filtered if int(route.get("priority_score") or 0) >= min_score]
    if priority_only:
        filtered = [
            route
            for route in filtered
            if not route.get("is_route_group")
            and route.get("priority_label") in {"priority_experiment", "control_required"}
        ]
    if only_actionable_routes:
        filtered = [route for route in filtered if _is_actionable_route(route)]
    elif not include_blocked_routes:
        filtered = [route for route in filtered if str(route.get("stage_gate_status") or "") != "blocked"]
    return filtered


def apply_stage_gates(
    routes: list[dict[str, Any]],
    gate_context: dict[str, Any] | None = None,
    respect_stage_gates: bool = True,
) -> list[dict[str, Any]]:
    """Attach prerequisites and current stage-gate status to each route."""

    context = dict(gate_context or {})
    completed = set(_list_values(context.get("completed_route_ids")))
    waived_ranks = {int(value) for value in context.get("waived_stage_ranks") or [] if str(value).isdigit()}
    waive_all = bool(context.get("human_stage_gate_waiver"))
    documented_failure = bool(context.get("documented_failure"))
    route_types = _route_ids_by_type(routes)

    if context.get("baseline_satisfied"):
        completed.update(route_types.get("baseline_repeatability") or _expected_ids(routes, "baseline_repeatability"))
    if context.get("admission_controls_satisfied"):
        for route_type in ("validation_gap_closure", "contamination_control"):
            completed.update(route_types.get(route_type) or _expected_ids(routes, route_type))
    if context.get("stage_2_satisfied"):
        for route_type in (
            "water_content_window",
            "proton_donor_window",
            "salt_solvent_window",
            "operating_field_matrix",
        ):
            completed.update(route_types.get(route_type) or [])
    if context.get("product_accounting_satisfied"):
        completed.update(route_types.get("product_state_accounting") or _expected_ids(routes, "product_state_accounting"))

    output: list[dict[str, Any]] = []
    for original in routes:
        route = dict(original)
        stage_rank = int(route.get("stage_rank") if route.get("stage_rank") is not None else ROUTE_STAGE_MAP.get(str(route.get("route_type") or ""), 5))
        route["stage_rank"] = stage_rank
        route["execution_stage"] = EXECUTION_STAGES[stage_rank]
        prerequisites = _route_prerequisites(route, routes)
        route["prerequisite_route_ids"] = prerequisites
        unresolved = [route_id for route_id in prerequisites if route_id not in completed]
        route_id = str(route.get("route_id") or "")
        capability_blocked = str(route.get("priority_label") or "") == "defer_until_capability_available"

        if bool(route.get("is_route_group")):
            route["stage_gate_status"] = "non_executable"
            route["blocked_by_route_ids"] = []
            route["execution_order_reason"] = "Summary parent route; execute one or more child routes instead."
        elif route_id in completed:
            route["stage_gate_status"] = "completed"
            route["blocked_by_route_ids"] = []
            route["execution_order_reason"] = "Route gate is satisfied by a completed execution record."
        elif capability_blocked:
            route["stage_gate_status"] = "blocked"
            route["blocked_by_route_ids"] = unresolved
            route["execution_order_reason"] = "Blocked by unavailable mandatory controls or measurements."
        elif stage_rank == 5 and documented_failure:
            route["stage_gate_status"] = "event_triggered"
            route["blocked_by_route_ids"] = []
            route["execution_order_reason"] = "Documented failure triggered immediate postmortem eligibility."
        elif not respect_stage_gates:
            route["stage_gate_status"] = "actionable"
            route["blocked_by_route_ids"] = []
            route["execution_order_reason"] = "Stage prerequisites were not enforced by request."
        elif stage_rank == 5:
            route["stage_gate_status"] = "blocked"
            route["blocked_by_route_ids"] = unresolved
            route["execution_order_reason"] = "Postmortem route requires a documented failure trigger."
        elif unresolved and not (waive_all or stage_rank in waived_ranks):
            route["stage_gate_status"] = "blocked"
            route["blocked_by_route_ids"] = unresolved
            route["execution_order_reason"] = f"Stage {stage_rank} waits for prerequisite routes."
        elif unresolved:
            route["stage_gate_status"] = "waived"
            route["blocked_by_route_ids"] = []
            route["execution_order_reason"] = "Prerequisite gate explicitly waived by human review."
        else:
            route["stage_gate_status"] = "actionable"
            route["blocked_by_route_ids"] = []
            route["execution_order_reason"] = f"Stage {stage_rank} prerequisites are satisfied."
        output.append(route)
    return output


def next_actionable_route(routes: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the first executable route under stage-aware ordering."""

    return next((route for route in rank_routes(routes) if _is_actionable_route(route)), None)


def _expand_electrolyte_route_hierarchy(
    by_route: dict[tuple[str, str], list[dict[str, Any]]]
) -> None:
    child_types = ("water_content_window", "proton_donor_window", "salt_solvent_window")
    families = {family for family, route_type in by_route if route_type in {"electrolyte_window", *child_types}}
    for family in families:
        generic = list(by_route.get((family, "electrolyte_window"), []))
        existing_children = [gap for route_type in child_types for gap in by_route.get((family, route_type), [])]
        if not generic and not existing_children:
            continue
        parent_gaps = _dedupe_gap_records([*generic, *existing_children])
        by_route[(family, "electrolyte_window")] = parent_gaps
        if generic:
            for route_type in child_types:
                by_route[(family, route_type)] = _dedupe_gap_records(
                    [*by_route.get((family, route_type), []), *generic]
                )


def _finalize_route_hierarchy(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    route_by_id = {str(route.get("route_id") or ""): route for route in routes}
    group_members: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for route in routes:
        group_members[str(route.get("shared_evidence_group") or "")].append(route)

    for route in routes:
        if route.get("is_route_group"):
            child_order = {route_type: index for index, route_type in enumerate(
                ("water_content_window", "proton_donor_window", "salt_solvent_window")
            )}
            children = [
                candidate
                for candidate in routes
                if str(candidate.get("parent_route_id") or "") == str(route.get("route_id") or "")
            ]
            route["child_route_ids"] = [
                str(candidate.get("route_id") or "")
                for candidate in sorted(children, key=lambda item: child_order.get(str(item.get("route_type") or ""), 99))
            ]
            route["within_stage_score"] = 0
            route["execution_order_reason"] = "Non-executable electrolyte summary parent."
        elif route.get("parent_route_id") and str(route.get("parent_route_id")) not in route_by_id:
            route["parent_route_id"] = ""

    for members in group_members.values():
        children = [member for member in members if member.get("parent_route_id")]
        if len(children) <= 1:
            continue
        divisor = len(children)
        for child in children:
            child["within_stage_score"] = round(int(child.get("priority_score") or 0) / divisor, 3)
            child["execution_order_reason"] = (
                "Within-stage score shares a common evidence bonus across electrolyte child routes."
            )
    return routes


def _route_prerequisites(
    route: dict[str, Any],
    all_routes: list[dict[str, Any]],
) -> list[str]:
    stage_rank = int(route.get("stage_rank") or 0)
    baseline = _matching_route_ids(all_routes, route, "baseline_repeatability") or [
        _expected_route_id(route, "baseline_repeatability")
    ]
    if stage_rank == 0:
        return []
    if stage_rank == 1:
        return _dedupe(baseline)
    if stage_rank == 2:
        admission = [
            *(
                _matching_route_ids(all_routes, route, "validation_gap_closure")
                or [_expected_route_id(route, "validation_gap_closure")]
            ),
            *(
                _matching_route_ids(all_routes, route, "contamination_control")
                or [_expected_route_id(route, "contamination_control")]
            ),
        ]
        return _dedupe([*baseline, *admission])
    if stage_rank == 3:
        stage_two = [
            route_id
            for candidate in all_routes
            if int(candidate.get("stage_rank") or -1) == 2
            and not candidate.get("is_route_group")
            and _same_route_scope(candidate, route)
            for route_id in [str(candidate.get("route_id") or "")]
        ]
        return _dedupe([*baseline, *stage_two])
    if stage_rank == 4:
        product = _matching_route_ids(all_routes, route, "product_state_accounting") or [
            _expected_route_id(route, "product_state_accounting")
        ]
        return _dedupe([*baseline, *product])
    stability = _matching_route_ids(all_routes, route, "stability_failure") or [
        _expected_route_id(route, "stability_failure")
    ]
    return _dedupe(stability)


def _gate_context_from_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    completed = _dedupe(
        route_id
        for record in records
        for route_id in _list_values(record.get("completed_route_ids"))
    )
    return {
        "completed_route_ids": completed,
        "baseline_satisfied": any(
            _truthy(record.get("baseline_complete"))
            or _truthy(record.get("baseline_gate_satisfied"))
            or _truthy(record.get("baseline_gate_waived_by_human"))
            for record in records
        ),
        "admission_controls_satisfied": any(_truthy(record.get("admission_controls_satisfied")) for record in records),
        "stage_2_satisfied": any(_truthy(record.get("stage_2_satisfied")) for record in records),
        "product_accounting_satisfied": any(_truthy(record.get("product_accounting_satisfied")) for record in records),
        "documented_failure": any(
            _truthy(record.get("documented_failure"))
            or _truthy(record.get("failure_triggered"))
            or str(record.get("success_status") or "") in {"failed", "invalid"}
            for record in records
        ),
        "human_stage_gate_waiver": any(
            _truthy(record.get("human_stage_gate_waiver")) or _truthy(record.get("stage_gate_waived"))
            for record in records
        ),
        "waived_stage_ranks": _dedupe(
            rank
            for record in records
            for rank in _list_values(record.get("waived_stage_ranks"))
        ),
    }


def _route_ids_by_type(routes: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for route in routes:
        result[str(route.get("route_type") or "")].append(str(route.get("route_id") or ""))
    return result


def _matching_route_ids(
    routes: list[dict[str, Any]], route: dict[str, Any], route_type: str
) -> list[str]:
    return [
        str(candidate.get("route_id") or "")
        for candidate in routes
        if str(candidate.get("route_type") or "") == route_type and _same_route_scope(candidate, route)
    ]


def _same_route_scope(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        str(left.get("run_name") or "") == str(right.get("run_name") or "")
        and str(left.get("reaction_family") or "unclear") == str(right.get("reaction_family") or "unclear")
    )


def _expected_ids(routes: list[dict[str, Any]], route_type: str) -> list[str]:
    identities = {
        (str(route.get("run_name") or "run"), str(route.get("reaction_family") or "unclear"))
        for route in routes
    }
    return [_route_id(run_name, family, route_type) for run_name, family in sorted(identities)]


def _expected_route_id(route: dict[str, Any], route_type: str) -> str:
    return _route_id(
        str(route.get("run_name") or "run"),
        str(route.get("reaction_family") or "unclear"),
        route_type,
    )


def _route_sort_key(route: dict[str, Any]) -> tuple[Any, ...]:
    status_rank = {
        "actionable": 0,
        "event_triggered": 0,
        "waived": 0,
        "completed": 1,
        "blocked": 2,
        "pending": 2,
        "non_executable": 3,
    }.get(str(route.get("stage_gate_status") or "pending"), 2)
    priority_rank = {
        "priority_experiment": 0,
        "control_required": 1,
        "do_after_controls": 2,
        "needs_human_review": 3,
        "defer_until_capability_available": 4,
        "insufficient_evidence": 5,
        "discard_as_secondary": 6,
    }.get(str(route.get("priority_label") or ""), 7)
    stage_rank = int(route.get("stage_rank") if route.get("stage_rank") is not None else ROUTE_STAGE_MAP.get(str(route.get("route_type") or ""), 5))
    within_stage_score = float(route.get("within_stage_score") if route.get("within_stage_score") is not None else route.get("priority_score") or 0)
    return (status_rank, stage_rank, priority_rank, -within_stage_score, str(route.get("route_id") or ""))


def _is_actionable_route(route: dict[str, Any]) -> bool:
    return (
        not bool(route.get("is_route_group"))
        and str(route.get("stage_gate_status") or "") in {"actionable", "event_triggered", "waived"}
    )


def _dedupe_gap_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        key = json.dumps(record, ensure_ascii=True, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        output.append(record)
    return output


def _route_id(run_name: str, family: str, route_type: str) -> str:
    return f"ER_{_sanitize_id(run_name)}_{_sanitize_id(family)}_{route_type}"


def export_experiment_routes(
    routes: list[dict[str, Any]],
    run_name: str,
    output_dir: str | Path = "data/experiment_routes",
) -> dict[str, Any]:
    """Export ranked experiment routes as JSONL, CSV, and a summary JSON."""

    run_dir = Path(output_dir) / run_name
    jsonl_path = run_dir / "ranked_experiment_routes.jsonl"
    csv_path = run_dir / "ranked_experiment_routes.csv"
    summary_path = run_dir / "route_generation_summary.json"
    _write_jsonl(routes, jsonl_path)
    _write_csv(routes, csv_path)
    summary = {
        "run_name": run_name,
        "routes_generated": len(routes),
        "priority_routes": sum(
            1 for route in routes if not route.get("is_route_group") and route.get("priority_label") == "priority_experiment"
        ),
        "deferred_routes": sum(
            1
            for route in routes
            if not route.get("is_route_group") and route.get("priority_label") == "defer_until_capability_available"
        ),
        "executable_routes": sum(1 for route in routes if not route.get("is_route_group")),
        "route_groups": sum(1 for route in routes if route.get("is_route_group")),
        "route_type_counts": dict(Counter(str(route.get("route_type") or "") for route in routes)),
        "reaction_family_counts": dict(Counter(str(route.get("reaction_family") or "unclear") for route in routes)),
        "lab_demonstration_allowed_routes": sum(1 for route in routes if bool(route.get("lab_demonstration_allowed"))),
        "measurement_feasibility_counts": dict(
            Counter(str(route.get("measurement_feasibility_status") or "unknown") for route in routes)
        ),
        "routes_with_infeasible_measurements": sum(1 for route in routes if route.get("infeasible_measurements")),
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    return {**summary, "summary_json": str(summary_path)}


def _build_route(
    run_name: str,
    reaction_family: str,
    route_type: str,
    title: str,
    variable_type: str,
    controls: list[str],
    measurements: list[str],
    target: str,
    gaps: list[dict[str, Any]],
    lab_profile: dict[str, Any],
    include_sop_fields: bool = True,
) -> dict[str, Any]:
    family = normalize_reaction_family(reaction_family)
    profile = get_reaction_profile(family)
    family_meta = _route_reaction_family_metadata(gaps)
    source_ids = _dedupe(gap.get("source_basis_id") for gap in gaps)
    paper_ids = _dedupe(gap.get("paper_id") for gap in gaps)
    span_ids = _dedupe(gap.get("source_span_id") for gap in gaps)
    hidden_taxes = _dedupe(gap.get("hidden_tax") or gap.get("gap_type") for gap in gaps if str(gap.get("hidden_tax") or gap.get("gap_type") or "").endswith("_tax"))
    primary_count = sum(1 for gap in gaps if gap.get("primary_evidence"))
    secondary_count = len(gaps) - primary_count
    feasible = feasible_controls(lab_profile, controls)
    infeasible = infeasible_controls(lab_profile, controls)
    required_measurements = [measurement for measurement in measurements if measurement in MEASUREMENT_LABELS]
    mandatory_measurements, optional_measurements = _split_measurements(route_type, required_measurements)
    feasible_measurement_list = feasible_measurements(lab_profile, required_measurements)
    infeasible_measurement_list = infeasible_measurements(lab_profile, required_measurements)
    infeasible_mandatory = infeasible_measurements(lab_profile, mandatory_measurements)
    infeasible_optional = infeasible_measurements(lab_profile, optional_measurements)
    measurement_status = measurement_feasibility_status(lab_profile, mandatory_measurements, optional_measurements)
    missing_control_capabilities = missing_capabilities_for_controls(lab_profile, controls)
    missing_measurement_capabilities = missing_capabilities_for_measurements(lab_profile, required_measurements)
    missing_capabilities = _dedupe([*missing_control_capabilities, *missing_measurement_capabilities])
    capability_warnings = [f"missing control capability: {item}" for item in missing_control_capabilities]
    measurement_warnings = [
        *[f"mandatory measurement unavailable: {item}" for item in infeasible_mandatory],
        *[f"optional measurement unavailable: {item}" for item in infeasible_optional],
        *[f"missing measurement capability: {item}" for item in missing_measurement_capabilities],
    ]
    capability_warnings.extend(measurement_warnings)
    alternative_measurement_plan = _dedupe(
        item
        for gap in gaps
        for item in _list_values(gap.get("alternative_measurement_plan"))
    )
    boundary_not_closed_measurements = [
        f"{measurement} remains unavailable and cannot close the targeted measurement boundary"
        for measurement in infeasible_measurement_list
    ]
    if infeasible_mandatory and alternative_measurement_plan:
        measurement_status = "partial"
    score = _route_score(route_type, gaps, lab_profile, controls, missing_capabilities, primary_count, secondary_count)
    critical_missing = _critical_missing(route_type, missing_capabilities)
    priority_label = _priority_label(route_type, score, critical_missing, infeasible, primary_count, secondary_count, gaps)
    if infeasible_mandatory:
        priority_label = "do_after_controls" if alternative_measurement_plan else "defer_until_capability_available"
    lab_allowed = experimental_demonstration_allowed(family, lab_profile)
    if not lab_allowed and family != "unclear":
        priority_label = "defer_until_capability_available"
        capability_warnings.append(f"reaction family not in current lab demonstration scope: {family}")
    human_review_required = priority_label == "needs_human_review" or any(gap.get("llm_disagreement") for gap in gaps)
    route_id = _route_id(run_name, family, route_type)
    stage_rank = ROUTE_STAGE_MAP[route_type]
    route_family_id = "electrolyte_operating_window" if route_type in {
        "electrolyte_window",
        "water_content_window",
        "proton_donor_window",
        "salt_solvent_window",
    } else route_type
    is_route_group = route_type == "electrolyte_window"
    parent_route_id = _route_id(run_name, family, "electrolyte_window") if route_type in {
        "water_content_window",
        "proton_donor_window",
        "salt_solvent_window",
    } else ""
    shared_evidence_group = (
        f"SEG_{_sanitize_id(run_name)}_{_sanitize_id(family)}_electrolyte_operating_window"
        if route_family_id == "electrolyte_operating_window"
        else f"SEG_{_sanitize_id(run_name)}_{_sanitize_id(family)}_{_sanitize_id(route_type)}"
    )
    route = {
        "schema_version": EXPERIMENT_SCHEMA_VERSION,
        "route_id": route_id,
        "run_name": run_name,
        "source_basis_ids": source_ids,
        "linked_paper_ids": paper_ids,
        "linked_source_span_ids": span_ids,
        "reaction_family": family,
        **family_meta,
        "reaction_profile_name": profile["reaction_family"],
        "reaction_profile": _reaction_profile_summary(profile),
        "lab_demonstration_allowed": lab_allowed,
        "route_type": route_type,
        "execution_stage": EXECUTION_STAGES[stage_rank],
        "stage_rank": stage_rank,
        "within_stage_score": score,
        "stage_gate_status": "pending",
        "prerequisite_route_ids": [],
        "blocked_by_route_ids": [],
        "route_family_id": route_family_id,
        "parent_route_id": parent_route_id,
        "child_route_ids": [],
        "is_route_group": is_route_group,
        "mutually_exclusive_route_ids": [],
        "shared_evidence_group": shared_evidence_group,
        "execution_order_reason": "Stage gate evaluation pending.",
        "default_replicate_count": 3 if route_type == "baseline_repeatability" else 1,
        "minimum_valid_replicates": 3 if route_type == "baseline_repeatability" else 1,
        "replicate_type": "independent",
        "independent_assembly_required": route_type == "baseline_repeatability",
        "execution_unit": EXECUTION_UNIT,
        "priority_label": priority_label,
        "priority_score": score,
        "hypothesis": _hypothesis(title, target),
        "literature_rationale": _rationale(route_type, gaps),
        "boundary_gap_targeted": _dedupe(gap.get("gap_type") for gap in gaps),
        "hidden_tax_targeted": hidden_taxes,
        "variable_type": variable_type,
        "experimental_matrix": _experimental_matrix(variable_type, route_type),
        "fixed_conditions": _fixed_conditions(lab_profile),
        "required_controls": [control for control in controls if control in CONTROL_LABELS],
        "feasible_controls": feasible,
        "infeasible_controls": infeasible,
        "mandatory_measurements": mandatory_measurements,
        "optional_measurements": optional_measurements,
        "feasible_measurements": feasible_measurement_list,
        "infeasible_measurements": infeasible_measurement_list,
        "measurement_capability_warnings": measurement_warnings,
        "measurement_feasibility_status": measurement_status,
        "alternative_measurement_plan": alternative_measurement_plan,
        "boundary_not_closed_due_to_unavailable_measurements": boundary_not_closed_measurements,
        "required_measurements": required_measurements,
        "success_criteria": _success_criteria(route_type),
        "failure_criteria": _failure_criteria(route_type),
        "stopping_rules": ["Stop route interpretation if mandatory controls fail.", "Do not upgrade claim boundary from invalid or incomplete controls."],
        "expected_outcomes": _expected_outcomes(route_type),
        "failure_diagnosis_tree": _failure_tree(route_type),
        "SOP_anchor_points": _sop_anchor_points(route_type) if include_sop_fields else [],
        "minimum_report_fields": _minimum_report_fields(route_type) if include_sop_fields else [],
        "boundary_upgrade_if_successful": _boundary_upgrade_if_successful(route_type),
        "boundary_not_closed_even_if_successful": _boundary_not_closed_even_if_successful(route_type),
        "required_raw_records_to_save": _required_raw_records_to_save(route_type) if include_sop_fields else [],
        "lab_capability_warnings": capability_warnings,
        "safety_notes": _safety_notes(lab_profile),
        "estimated_difficulty": _difficulty(route_type, missing_capabilities),
        "estimated_cost_level": _cost_level(lab_profile, route_type),
        "estimated_time_level": _time_level(route_type),
        "human_review_required": human_review_required,
        "llm_used": False,
        "llm_model": "",
        "llm_rationale": "",
        "created_at_utc": utc_now(),
    }
    valid, errors = validate_experiment_route(route)
    if not valid:
        route["schema_errors"] = errors
    return route


def _route_score(
    route_type: str,
    gaps: list[dict[str, Any]],
    profile: dict[str, Any],
    controls: list[str],
    missing_capabilities: list[str],
    primary_count: int,
    secondary_count: int,
) -> int:
    score = 0
    if route_type == "baseline_repeatability":
        score += 55
    if route_type == "validation_gap_closure":
        score += 30
    if route_type in {"water_content_window", "proton_donor_window", "salt_solvent_window"} and capability_available(profile, "can_measure_water_content"):
        score += 20
    if route_type == "flow_wetting" and capability_available(profile, "can_do_flow_cell") and capability_available(profile, "product_state_accounting_available"):
        score += 20
    if route_type == "HOR_proton_economy" and capability_available(profile, "can_do_HOR_coupling") and capability_available(profile, "H2_available"):
        score += 20
    hidden_tax_counts = Counter(gap.get("hidden_tax") for gap in gaps if gap.get("hidden_tax"))
    if hidden_tax_counts:
        score += 25 + min(15, 3 * max(hidden_tax_counts.values()))
    if not missing_capabilities:
        score += 20
    if any(gap.get("llm_disagreement") for gap in gaps):
        score += 15
    if any(str(gap.get("human_experiment_decision") or "") == "priority_experiment" for gap in gaps):
        score += 15
    if primary_count:
        score += 10
    if missing_capabilities:
        score -= 30
    if primary_count == 0:
        score -= 20
    if secondary_count > primary_count:
        score -= 15
    if len(infeasible_controls(profile, controls)) >= 3:
        score -= 10
    if _blocked_by_safety(profile, route_type):
        score -= 10
    return max(0, min(100, score))


def _priority_label(
    route_type: str,
    score: int,
    critical_missing: bool,
    infeasible: list[str],
    primary_count: int,
    secondary_count: int,
    gaps: list[dict[str, Any]],
) -> str:
    if route_type == "baseline_repeatability" and not critical_missing:
        return "priority_experiment" if score >= 55 else "do_after_controls"
    if any(gap.get("llm_disagreement") or str(gap.get("gap_type")) == "provenance conflict" for gap in gaps):
        if score >= 35:
            return "needs_human_review"
    if critical_missing:
        return "defer_until_capability_available"
    if primary_count == 0 and secondary_count:
        return "discard_as_secondary"
    if primary_count == 0:
        return "insufficient_evidence"
    if route_type in _VARIABLE_SCREENING_ROUTES and not _baseline_or_human_ready(gaps):
        return "do_after_controls" if score >= 35 else "insufficient_evidence"
    if score >= 60 and not critical_missing:
        return "priority_experiment"
    if score >= 45 and infeasible:
        return "control_required"
    if score >= 35:
        return "do_after_controls"
    return "insufficient_evidence"


def _critical_missing(route_type: str, missing_capabilities: list[str]) -> bool:
    critical_by_route = {
        "baseline_repeatability": {"potentiostat_available", "can_record_full_cell_voltage", "can_measure_water_content"},
        "validation_gap_closure": {"can_do_15N_control", "isotopic_15N2_available", "can_do_NOx_screening"},
        "water_content_window": {"can_measure_water_content", "Karl_Fischer_available"},
        "proton_donor_window": {"can_measure_water_content", "Karl_Fischer_available"},
        "salt_solvent_window": {"can_measure_water_content", "Karl_Fischer_available"},
        "flow_wetting": {"can_do_flow_cell", "product_state_accounting_available"},
        "HOR_proton_economy": {"can_do_HOR_coupling", "H2_available"},
        "outlet_product_split": {"product_state_accounting_available"},
        "product_state_accounting": {"product_state_accounting_available"},
        "contamination_control": {"can_do_NOx_screening"},
    }
    return bool(set(missing_capabilities) & critical_by_route.get(route_type, set()))


def _baseline_family_enabled(
    lab_profile: dict[str, Any],
    reaction_family: str | None,
    include_families: list[str] | None,
    lab_demo_only: bool,
) -> bool:
    families = _family_filter(reaction_family or "LiNRR", include_families)
    if "LiNRR" not in families:
        return False
    return not lab_demo_only or experimental_demonstration_allowed("LiNRR", lab_profile)


def _baseline_gap(run_name: str) -> dict[str, Any]:
    return {
        "source_basis_id": f"BASELINE_{run_name}",
        "paper_id": "",
        "source_span_id": "",
        "evidence_id": "",
        "provenance_type": "lab_profile",
        "reaction_family": "LiNRR",
        "reaction_profile_name": "LiNRR",
        "lab_demonstration_allowed": True,
        "primary_evidence": True,
        "human_experiment_decision": "",
        "gap_type": "baseline repeatability required",
        "route_type_hint": "baseline_repeatability",
        "baseline_required": True,
    }


def _baseline_or_human_ready(gaps: list[dict[str, Any]]) -> bool:
    return any(
        gap.get("baseline_complete")
        or str(gap.get("human_experiment_decision") or "") in {"priority_experiment", "human_reviewed", "approved"}
        for gap in gaps
    )


def _filter_gaps_by_reaction_family(
    gaps: list[dict[str, Any]],
    lab_profile: dict[str, Any],
    reaction_family: str | None,
    include_families: list[str] | None,
    lab_demo_only: bool,
) -> list[dict[str, Any]]:
    families = _family_filter(reaction_family, include_families)
    filtered: list[dict[str, Any]] = []
    for gap in gaps:
        family = normalize_reaction_family(str(gap.get("reaction_family") or "unclear"))
        if families and family not in families:
            continue
        if lab_demo_only and not experimental_demonstration_allowed(family, lab_profile):
            continue
        filtered.append(gap)
    return filtered


def _family_filter(reaction_family: str | None, include_families: list[str] | None) -> set[str]:
    values = include_families if include_families is not None else ([reaction_family] if reaction_family else [])
    return {normalize_reaction_family(str(value)) for value in values if str(value or "").strip()}


def _gap_base(record: dict[str, Any]) -> dict[str, Any]:
    provenance_type = str(record.get("provenance_type") or "")
    primary = bool(record.get("is_primary_admissible")) and provenance_type not in {"review_table", "figure_caption", "scheme_caption"}
    family = _record_reaction_family(record)
    profile = get_reaction_profile(family)
    family_meta = _reaction_family_metadata(record)
    return {
        "source_basis_id": record.get("claim_id") or record.get("evidence_id") or record.get("source_span_id") or "",
        "paper_id": record.get("paper_id") or "",
        "source_span_id": record.get("source_span_id") or record.get("span_id") or "",
        "evidence_id": record.get("evidence_id") or "",
        "provenance_type": provenance_type,
        "reaction_family": family,
        **family_meta,
        "reaction_profile_name": profile["reaction_family"],
        "lab_demonstration_allowed": experimental_demonstration_allowed(family),
        "primary_evidence": primary,
        "human_experiment_decision": record.get("human_experiment_decision") or "",
    }


def _record_reaction_family(record: dict[str, Any], fallback_record: dict[str, Any] | None = None) -> str:
    for candidate in (record, fallback_record or {}):
        family = str(candidate.get("reaction_family") or "").strip()
        if family:
            return normalize_reaction_family(family)
    return infer_reaction_family_detailed(text=_record_text(record) or _record_text(fallback_record or {}))["reaction_family"]


def _reaction_family_metadata(record: dict[str, Any], fallback_record: dict[str, Any] | None = None) -> dict[str, Any]:
    source = record if record.get("reaction_family_confidence") or record.get("reaction_family_scope") else fallback_record or {}
    if not source:
        detailed = infer_reaction_family_detailed(text=_record_text(record) or _record_text(fallback_record or {}))
        return {
            "reaction_family_confidence": detailed["reaction_family_confidence"],
            "reaction_family_scores": detailed["reaction_family_scores"],
            "reaction_family_signals": detailed["reaction_family_signals"],
            "reaction_family_scope": detailed["reaction_family_scope"],
            "paper_level_reaction_family": "unclear",
            "reaction_family_conflict": detailed["reaction_family_conflict"],
        }
    return {
        "reaction_family_confidence": str(source.get("reaction_family_confidence") or "unclear"),
        "reaction_family_scores": source.get("reaction_family_scores") or {},
        "reaction_family_signals": source.get("reaction_family_signals") or [],
        "reaction_family_scope": str(source.get("reaction_family_scope") or "fallback"),
        "paper_level_reaction_family": str(source.get("paper_level_reaction_family") or "unclear"),
        "reaction_family_conflict": bool(source.get("reaction_family_conflict")),
    }


def _route_reaction_family_metadata(gaps: list[dict[str, Any]]) -> dict[str, Any]:
    confidences = [str(gap.get("reaction_family_confidence") or "") for gap in gaps]
    confidence = "high" if "high" in confidences else "medium" if "medium" in confidences else "low" if "low" in confidences else "unclear"
    scopes = _dedupe(gap.get("reaction_family_scope") for gap in gaps)
    paper_families = _dedupe(gap.get("paper_level_reaction_family") for gap in gaps)
    signals: list[str] = []
    scores: dict[str, int] = {}
    for gap in gaps:
        signals.extend(_list_values(gap.get("reaction_family_signals")))
        gap_scores = gap.get("reaction_family_scores")
        if isinstance(gap_scores, dict):
            for key, value in gap_scores.items():
                try:
                    scores[str(key)] = max(scores.get(str(key), 0), int(value))
                except (TypeError, ValueError):
                    continue
    return {
        "reaction_family_confidence": confidence,
        "reaction_family_scores": scores,
        "reaction_family_signals": _dedupe(signals),
        "reaction_family_scope": ";".join(scopes) if scopes else "fallback",
        "paper_level_reaction_family": paper_families[0] if len(paper_families) == 1 else "mixed" if len(paper_families) > 1 else "unclear",
        "reaction_family_conflict": any(bool(gap.get("reaction_family_conflict")) for gap in gaps),
    }


def _reaction_profile_summary(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "reaction_family": profile["reaction_family"],
        "nitrogen_source": profile["nitrogen_source"],
        "family_route_types": profile["family_route_types"],
        "family_hidden_taxes": profile["family_hidden_taxes"],
        "experimental_demonstration_allowed": profile["experimental_demonstration_allowed"],
    }


def _validation_gap_specs(family: str) -> tuple[tuple[str, str], ...]:
    normalized = normalize_reaction_family(family)
    common = (
        ("blank_control", "missing blank_control"),
        ("contamination_control", "missing contamination_control"),
    )
    if normalized in {"eNRR", "LiNRR"}:
        return (("isotope_15N", "missing isotope_15N"), *common, ("nox_control", "missing nox_control"))
    if normalized in {"NO3RR", "NO2RR", "NORR"}:
        return common
    return common


def _profile_route_hint(family: str, route_type: str) -> str:
    normalized = normalize_reaction_family(family)
    if normalized == "unclear":
        return route_type
    if route_type in profile_route_types(normalized):
        return route_type
    return "validation_gap_closure"


def _route_for_hidden_tax(tax: str) -> str:
    return {
        "solvent_management_tax": "electrolyte_window",
        "resistance_or_renewal_tax": "interphase_resistance",
        "wetting_outlet_capture_tax": "flow_wetting",
        "hydrogen_logistics_tax": "HOR_proton_economy",
        "contamination_tax": "contamination_control",
        "measurement_matrix_tax": "validation_gap_closure",
    }.get(str(tax), "validation_gap_closure")


def _record_key(record: dict[str, Any]) -> str:
    for key in ("evidence_id", "source_span_id", "span_id", "claim_id", "tax_record_id"):
        value = str(record.get(key) or "").strip()
        if value:
            return re.sub(r"^(?:CR_|HT_)", "", value)
    return ""


def _index(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        key = _record_key(record)
        if key and key not in indexed:
            indexed[key] = record
    return indexed


def _list_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [json.dumps(value, ensure_ascii=True, sort_keys=True)] if value else []
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return _list_values(parsed)
    return [part.strip() for part in re.split(r"[;,|]", text) if part.strip()]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"true", "1", "yes", "y"}


def _split_measurements(route_type: str, measurements: list[str]) -> tuple[list[str], list[str]]:
    optional_set = _OPTIONAL_MEASUREMENTS_BY_ROUTE.get(route_type, set())
    optional = [measurement for measurement in measurements if measurement in optional_set]
    mandatory = [measurement for measurement in measurements if measurement not in optional_set]
    return mandatory, optional


def _record_text(record: dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", str(record.get("source_text") or record.get("source_span") or record.get("text") or "").casefold())


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _hypothesis(title: str, target: str) -> str:
    return f"{title} will determine whether the literature gap is caused by {target} rather than a complete admissible boundary."


def _rationale(route_type: str, gaps: list[dict[str, Any]]) -> str:
    counts = Counter(str(gap.get("gap_type") or "") for gap in gaps)
    top = ", ".join(f"{key} ({count})" for key, count in counts.most_common(5))
    return f"Route {route_type} was generated from {len(gaps)} BoundaryLedger gap signals: {top}."


def _experimental_matrix(variable_type: str, route_type: str = "") -> list[dict[str, str]]:
    baseline = {
        "condition_id": "baseline",
        "condition_label": "Baseline",
        "variable_type": variable_type,
        "planned_value": "current lab baseline",
    }
    if route_type == "baseline_repeatability":
        return [baseline]
    return [
        baseline,
        {
            "condition_id": "stress_or_control",
            "condition_label": "Stress or control",
            "variable_type": variable_type,
            "planned_value": "single controlled perturbation",
        },
    ]


def _fixed_conditions(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "reactors_available": (profile.get("reactor_capabilities") or {}).get("available_reactors") or [],
        "max_runtime_hours": (profile.get("reactor_capabilities") or {}).get("max_runtime_hours"),
        "budget_level": (profile.get("constraints") or {}).get("budget_level") or "unknown",
    }


def _success_criteria(route_type: str) -> list[str]:
    return [
        "All mandatory controls complete without invalidating contamination or background signal.",
        f"The route produces interpretable measurements for {route_type}.",
        "BoundaryLedger can be updated with explicit measured fields rather than inferred claims.",
    ]


def _failure_criteria(route_type: str) -> list[str]:
    return [
        "Mandatory controls fail or are missing.",
        "Required measurements are missing or internally inconsistent.",
        f"The planned {route_type} variable cannot be isolated under the current lab profile.",
    ]


def _expected_outcomes(route_type: str) -> list[str]:
    return [
        "success: controls pass and required measurements close the targeted boundary gap",
        "partial: controls pass but only some measurements are interpretable",
        "failed: route reveals a hidden tax or operational limit",
        "invalid: mandatory controls fail",
    ]


def _failure_tree(route_type: str) -> list[str]:
    return [
        "If controls fail, classify result as invalid and repeat controls before interpreting performance.",
        "If NH3 appears in blanks, diagnose contamination/background before changing materials.",
        f"If {route_type} measurements drift with runtime, treat stability/failure mode as the next route target.",
    ]


def _sop_anchor_points(route_type: str) -> list[str]:
    common = [
        "glovebox and dry electrolyte handling",
        "cell assembly",
        "electrochemical test",
        "sampling and IC",
        "final experiment report",
    ]
    route_specific = {
        "baseline_repeatability": ["Li salt/DG drying", "water-content test", "common failure diagnosis"],
        "validation_gap_closure": ["gas/liquid/electrode assembly", "sampling and IC"],
        "water_content_window": ["Li salt/DG drying", "water-content test"],
        "proton_donor_window": ["Li salt/DG drying", "water-content test"],
        "salt_solvent_window": ["Li salt/DG drying", "water-content test"],
        "interphase_resistance": ["SSC/PtAuSSC preparation", "common failure diagnosis"],
        "flow_wetting": ["gas/liquid/electrode assembly", "common failure diagnosis"],
        "HOR_proton_economy": ["gas/liquid/electrode assembly", "common failure diagnosis"],
        "outlet_product_split": ["gas/liquid/electrode assembly", "sampling and IC"],
        "postmortem_failure_analysis": ["common failure diagnosis", "final experiment report"],
    }
    return _dedupe([*common, *route_specific.get(route_type, [])])


def _minimum_report_fields(route_type: str) -> list[str]:
    base = ["date", "operator", "condition_id", "FE", "NH3_yield", "full_cell_voltage", "runtime_hours", "controls_completed"]
    extra = {
        "baseline_repeatability": [
            "OCV",
            "pump_speed",
            "water_content_before",
            "water_content_mid",
            "water_content_after",
            "electrolyte_resistance_before",
            "electrolyte_resistance_after",
            "IC_NH4",
        ],
        "water_content_window": ["water_content_before", "water_content_mid", "water_content_after", "IC_NH4"],
        "proton_donor_window": ["water_content_before", "water_content_mid", "water_content_after", "electrolyte_color"],
        "salt_solvent_window": ["water_content_before", "water_content_after", "electrolyte_color"],
        "interphase_resistance": ["EIS_summary", "electrolyte_resistance_before", "electrolyte_resistance_after", "failure_mode"],
        "flow_wetting": ["gas_phase_NH3", "liquid_NH4", "leak_status", "back_suction_status", "pump_status"],
        "HOR_proton_economy": ["H2_observation", "anode_potential", "cathode_potential", "product_state_split"],
        "outlet_product_split": ["gas_phase_NH3", "liquid_NH4", "HCl_trap_NH4", "SSC_soak_solution_NH4"],
        "postmortem_failure_analysis": ["failure_mode", "operator_failure_note", "SOP_deviation"],
    }
    return _dedupe([*base, *extra.get(route_type, [])])


def _boundary_upgrade_if_successful(route_type: str) -> list[str]:
    if route_type in {"baseline_repeatability", "operating_field_matrix"}:
        return ["Can strengthen cell_metric repeatability and measurement-matrix support only."]
    if route_type in {"validation_gap_closure", "contamination_control"}:
        return ["Can strengthen product_admissibility when mandatory validation controls pass."]
    if route_type in {"flow_wetting", "HOR_proton_economy", "outlet_product_split"}:
        return ["Can support reactor_legibility for the measured LiNRR system if controls pass."]
    if route_type in {"water_content_window", "proton_donor_window", "salt_solvent_window", "interphase_resistance"}:
        return ["Can support measured cell/reactor boundary fields for the tested LiNRR operating window."]
    return ["Can update only the targeted measured BoundaryLedger fields."]


def _boundary_not_closed_even_if_successful(route_type: str) -> list[str]:
    return [
        "Does not establish plant/process readiness.",
        "Does not generalize beyond the tested LiNRR setup.",
        "Does not override missing primary literature evidence or failed mandatory controls.",
    ]


def _required_raw_records_to_save(route_type: str) -> list[str]:
    records = ["raw current/voltage trace", "IC/calibration files", "completed route result template", "operator notes"]
    route_specific = {
        "baseline_repeatability": ["Karl Fischer readings before/mid/after", "SSC/PtAuSSC before-after photos"],
        "water_content_window": ["Karl Fischer readings before/mid/after"],
        "proton_donor_window": ["donor identity/concentration sheet", "Karl Fischer readings"],
        "salt_solvent_window": ["Li salt/solvent drying log", "Karl Fischer readings"],
        "interphase_resistance": ["EIS files before/after", "SSC/PtAuSSC before-after photos"],
        "flow_wetting": ["gas/liquid line status log", "pump/leak/back-suction notes"],
        "HOR_proton_economy": ["H2/HOR on-off log", "anode/cathode potential trace"],
        "outlet_product_split": ["HCl trap IC files", "SSC soak solution IC files"],
        "postmortem_failure_analysis": ["failure photos", "post-experiment report", "SOP deviation note"],
    }
    return _dedupe([*records, *route_specific.get(route_type, [])])


def _safety_notes(profile: dict[str, Any]) -> list[str]:
    constraints = profile.get("constraints") if isinstance(profile.get("constraints"), dict) else {}
    notes = [str(item) for item in constraints.get("safety_constraints") or []]
    if not notes:
        notes.append("Use only approved local SOPs; this route card is not a wet-lab protocol.")
    return notes


def _difficulty(route_type: str, missing_capabilities: list[str]) -> str:
    if missing_capabilities:
        return "high"
    if route_type in {"flow_wetting", "HOR_proton_economy", "product_state_accounting"}:
        return "medium"
    return "low"


def _cost_level(profile: dict[str, Any], route_type: str) -> str:
    budget = str((profile.get("constraints") or {}).get("budget_level") or "unknown")
    if route_type in {"HOR_proton_economy", "flow_wetting"} and budget == "low":
        return "medium"
    return budget


def _time_level(route_type: str) -> str:
    if route_type in {"stability_failure", "flow_wetting", "interphase_resistance"}:
        return "medium"
    return "short"


def _blocked_by_safety(profile: dict[str, Any], route_type: str) -> bool:
    constraints = profile.get("constraints") if isinstance(profile.get("constraints"), dict) else {}
    unavailable = " ".join(str(item).casefold() for item in constraints.get("unavailable_operations") or [])
    return route_type.casefold() in unavailable or any(token in unavailable for token in route_type.casefold().split("_"))


def _sanitize_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("_") or "run"


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, default=str, separators=(",", ":")))
            handle.write("\n")


def _write_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _fieldnames(records)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: _csv_value(record.get(field)) for field in fieldnames})


def _fieldnames(records: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "route_id",
        "run_name",
        "reaction_family",
        "reaction_family_confidence",
        "reaction_family_scope",
        "paper_level_reaction_family",
        "reaction_family_conflict",
        "reaction_family_signals",
        "reaction_family_scores",
        "reaction_profile_name",
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
        "priority_label",
        "priority_score",
        "hypothesis",
        "literature_rationale",
        "boundary_gap_targeted",
        "hidden_tax_targeted",
        "variable_type",
        "required_controls",
        "feasible_controls",
        "infeasible_controls",
        "required_measurements",
        "mandatory_measurements",
        "optional_measurements",
        "feasible_measurements",
        "infeasible_measurements",
        "measurement_feasibility_status",
        "alternative_measurement_plan",
        "boundary_not_closed_due_to_unavailable_measurements",
        "SOP_anchor_points",
        "minimum_report_fields",
        "boundary_upgrade_if_successful",
        "boundary_not_closed_even_if_successful",
        "required_raw_records_to_save",
        "human_review_required",
        "llm_used",
        "llm_model",
    ]
    names = set(preferred)
    for record in records:
        names.update(record)
    ordered = [name for name in preferred if name in names]
    ordered.extend(sorted(name for name in names if name not in set(ordered)))
    return ordered


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple, set)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return str(value)
