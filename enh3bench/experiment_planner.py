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
    MEASUREMENT_LABELS,
    ROUTE_TYPES,
    validate_experiment_route,
    utc_now,
)
from enh3bench.lab_profile import (
    capability_available,
    feasible_controls,
    infeasible_controls,
    missing_capabilities_for_controls,
)
from enh3bench.ledger_router import load_jsonl
from enh3bench.llm_clients.base import sanitize_model_name_for_path
from enh3bench.reaction_profiles import (
    experimental_demonstration_allowed,
    get_reaction_profile,
    infer_reaction_family_from_text,
    normalize_reaction_family,
    profile_hidden_taxes,
    profile_route_types,
)


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
        row["reaction_family"] = family
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
                route_type = "product_state_accounting" if "product state" in normalized else "electrolyte_window"
            if "capture" in normalized:
                route_type = "product_state_accounting"
            gaps.append({**base, "gap_type": f"missing {missing}", "route_type_hint": _profile_route_hint(family, route_type)})

        for tax in _list_values(record.get("detected_taxes")):
            if family != "unclear" and tax not in profile_hidden_taxes(family):
                continue
            route_type = _route_for_hidden_tax(tax)
            gaps.append({**base, "gap_type": tax, "route_type_hint": _profile_route_hint(family, route_type), "hidden_tax": tax})

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
    return gaps


def propose_rule_based_routes(
    actionable_gaps: list[dict[str, Any]],
    lab_profile: dict[str, Any],
    run_name: str,
    reaction_family: str | None = None,
    include_families: list[str] | None = None,
    lab_demo_only: bool = False,
) -> list[dict[str, Any]]:
    """Generate deterministic route cards from actionable gaps and lab profile."""

    filtered_gaps = _filter_gaps_by_reaction_family(actionable_gaps, lab_profile, reaction_family, include_families, lab_demo_only)
    by_route: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for gap in filtered_gaps:
        route_type = str(gap.get("route_type_hint") or "validation_gap_closure")
        if route_type in ROUTE_TYPES:
            by_route[(str(gap.get("reaction_family") or "unclear"), route_type)].append(gap)

    routes: list[dict[str, Any]] = []
    route_specs = [
        ("validation_gap_closure", "Validation-gate closure panel", "control_experiment", ["15N2 isotope validation", "Ar blank", "N2-free blank", "NOx/nitrate/nitrite screening", "background NH3 control"], ["NH3_yield", "nitrate", "nitrite", "NOx", "product_state_split"], "missing validation gates"),
        ("electrolyte_window", "Electrolyte water/proton donor window", "water_content", ["electrolyte blank", "Ar blank", "NOx/nitrate/nitrite screening"], ["FE", "NH3_yield", "full_cell_voltage", "EIS", "water_content", "electrolyte_color"], "solvent_management_tax"),
        ("interphase_resistance", "Interphase resistance and renewal diagnostic", "runtime", ["Ar blank", "voltage/current/runtime reporting"], ["EIS", "full_cell_voltage", "FE", "NH3_yield", "failure_mode", "photo_before_after"], "resistance_or_renewal_tax"),
        ("flow_wetting", "Flow/GDE wetting and outlet product-state map", "gas_flow", ["gas/liquid product accounting", "wetting/flooding diagnosis", "Ar blank"], ["gas_phase_NH3", "liquid_NH4", "product_state_split", "full_cell_voltage", "failure_mode"], "wetting_outlet_capture_tax"),
        ("HOR_proton_economy", "HOR on/off proton-economy boundary test", "HOR_on_off", ["H2-off control", "HOR-off control", "voltage/current/runtime reporting"], ["full_cell_voltage", "anode_potential", "cathode_potential", "NH3_yield", "H2"], "hydrogen_logistics_tax"),
        ("product_state_accounting", "Gas/liquid ammonia accounting and capture boundary", "capture_route", ["gas/liquid product accounting", "solvent inventory/recycle reporting"], ["gas_phase_NH3", "liquid_NH4", "product_state_split", "water_content"], "product_state/capture gap"),
        ("contamination_control", "NOx/background ammonia contamination stress test", "control_experiment", ["NOx/nitrate/nitrite screening", "background NH3 control", "Ar blank", "N2-free blank", "electrolyte blank"], ["nitrate", "nitrite", "NOx", "liquid_NH4"], "contamination_tax"),
        ("stability_failure", "Runtime stability and first-failure boundary test", "runtime", ["voltage/current/runtime reporting", "Ar blank"], ["runtime", "full_cell_voltage", "FE", "NH3_yield", "EIS", "failure_mode"], "stability/failure disclosure gap"),
        ("process_boundary_probe", "Process-boundary accounting probe", "capture_route", ["gas/liquid product accounting", "solvent inventory/recycle reporting", "voltage/current/runtime reporting"], ["product_state_split", "full_cell_voltage", "water_content", "gas_phase_NH3", "liquid_NH4"], "process boundary overclaim risk"),
    ]
    route_spec_by_type = {route_type: spec for route_type, *spec in route_specs}
    for family, route_type in sorted(by_route):
        spec = route_spec_by_type.get(route_type)
        if not spec:
            continue
        title, variable_type, controls, measurements, target = spec
        routes.append(_build_route(run_name, family, route_type, title, variable_type, controls, measurements, target, by_route[(family, route_type)], lab_profile))
    return rank_routes(routes)


def rank_routes(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort routes by score and stable route id."""

    return sorted(routes, key=lambda route: (-int(route.get("priority_score") or 0), str(route.get("route_id") or "")))


def filter_routes(routes: list[dict[str, Any]], min_score: int | None = None, priority_only: bool = False) -> list[dict[str, Any]]:
    """Filter route list for CLI output."""

    filtered = list(routes)
    if min_score is not None:
        filtered = [route for route in filtered if int(route.get("priority_score") or 0) >= min_score]
    if priority_only:
        filtered = [route for route in filtered if route.get("priority_label") in {"priority_experiment", "control_required"}]
    return filtered


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
        "priority_routes": sum(1 for route in routes if route.get("priority_label") == "priority_experiment"),
        "deferred_routes": sum(1 for route in routes if route.get("priority_label") == "defer_until_capability_available"),
        "route_type_counts": dict(Counter(str(route.get("route_type") or "") for route in routes)),
        "reaction_family_counts": dict(Counter(str(route.get("reaction_family") or "unclear") for route in routes)),
        "lab_demonstration_allowed_routes": sum(1 for route in routes if bool(route.get("lab_demonstration_allowed"))),
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
) -> dict[str, Any]:
    family = normalize_reaction_family(reaction_family)
    profile = get_reaction_profile(family)
    source_ids = _dedupe(gap.get("source_basis_id") for gap in gaps)
    paper_ids = _dedupe(gap.get("paper_id") for gap in gaps)
    span_ids = _dedupe(gap.get("source_span_id") for gap in gaps)
    hidden_taxes = _dedupe(gap.get("hidden_tax") or gap.get("gap_type") for gap in gaps if str(gap.get("hidden_tax") or gap.get("gap_type") or "").endswith("_tax"))
    primary_count = sum(1 for gap in gaps if gap.get("primary_evidence"))
    secondary_count = len(gaps) - primary_count
    feasible = feasible_controls(lab_profile, controls)
    infeasible = infeasible_controls(lab_profile, controls)
    missing_capabilities = missing_capabilities_for_controls(lab_profile, controls)
    capability_warnings = [f"missing capability: {item}" for item in missing_capabilities]
    score = _route_score(route_type, gaps, lab_profile, controls, missing_capabilities, primary_count, secondary_count)
    critical_missing = _critical_missing(route_type, missing_capabilities)
    priority_label = _priority_label(score, critical_missing, infeasible, primary_count, secondary_count, gaps)
    lab_allowed = experimental_demonstration_allowed(family, lab_profile)
    if not lab_allowed and family != "unclear":
        priority_label = "defer_until_capability_available"
        capability_warnings.append(f"reaction family not in current lab demonstration scope: {family}")
    human_review_required = priority_label == "needs_human_review" or any(gap.get("llm_disagreement") for gap in gaps)
    route = {
        "route_id": f"ER_{_sanitize_id(run_name)}_{_sanitize_id(family)}_{route_type}",
        "run_name": run_name,
        "source_basis_ids": source_ids,
        "linked_paper_ids": paper_ids,
        "linked_source_span_ids": span_ids,
        "reaction_family": family,
        "reaction_profile_name": profile["reaction_family"],
        "reaction_profile": _reaction_profile_summary(profile),
        "lab_demonstration_allowed": lab_allowed,
        "route_type": route_type,
        "priority_label": priority_label,
        "priority_score": score,
        "hypothesis": _hypothesis(title, target),
        "literature_rationale": _rationale(route_type, gaps),
        "boundary_gap_targeted": _dedupe(gap.get("gap_type") for gap in gaps),
        "hidden_tax_targeted": hidden_taxes,
        "variable_type": variable_type,
        "experimental_matrix": _experimental_matrix(variable_type),
        "fixed_conditions": _fixed_conditions(lab_profile),
        "required_controls": [control for control in controls if control in CONTROL_LABELS],
        "feasible_controls": feasible,
        "infeasible_controls": infeasible,
        "required_measurements": [measurement for measurement in measurements if measurement in MEASUREMENT_LABELS],
        "success_criteria": _success_criteria(route_type),
        "failure_criteria": _failure_criteria(route_type),
        "stopping_rules": ["Stop route interpretation if mandatory controls fail.", "Do not upgrade claim boundary from invalid or incomplete controls."],
        "expected_outcomes": _expected_outcomes(route_type),
        "failure_diagnosis_tree": _failure_tree(route_type),
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
    if route_type == "validation_gap_closure":
        score += 30
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
    score: int,
    critical_missing: bool,
    infeasible: list[str],
    primary_count: int,
    secondary_count: int,
    gaps: list[dict[str, Any]],
) -> str:
    if any(gap.get("llm_disagreement") or str(gap.get("gap_type")) == "provenance conflict" for gap in gaps):
        if score >= 35:
            return "needs_human_review"
    if critical_missing:
        return "defer_until_capability_available"
    if primary_count == 0 and secondary_count:
        return "discard_as_secondary"
    if primary_count == 0:
        return "insufficient_evidence"
    if score >= 60 and not critical_missing:
        return "priority_experiment"
    if score >= 45 and infeasible:
        return "control_required"
    if score >= 35:
        return "do_after_controls"
    return "insufficient_evidence"


def _critical_missing(route_type: str, missing_capabilities: list[str]) -> bool:
    critical_by_route = {
        "validation_gap_closure": {"can_do_15N_control", "isotopic_15N2_available", "can_do_NOx_screening"},
        "flow_wetting": {"can_do_flow_cell", "product_state_accounting_available"},
        "HOR_proton_economy": {"can_do_HOR_coupling", "H2_available"},
        "product_state_accounting": {"product_state_accounting_available"},
        "contamination_control": {"can_do_NOx_screening"},
    }
    return bool(set(missing_capabilities) & critical_by_route.get(route_type, set()))


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
    return {
        "source_basis_id": record.get("claim_id") or record.get("evidence_id") or record.get("source_span_id") or "",
        "paper_id": record.get("paper_id") or "",
        "source_span_id": record.get("source_span_id") or record.get("span_id") or "",
        "evidence_id": record.get("evidence_id") or "",
        "provenance_type": provenance_type,
        "reaction_family": family,
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
    return infer_reaction_family_from_text(_record_text(record) or _record_text(fallback_record or {}))


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


def _experimental_matrix(variable_type: str) -> list[dict[str, str]]:
    return [
        {"condition_id": "baseline", "variable_type": variable_type, "planned_value": "current lab baseline"},
        {"condition_id": "stress_or_control", "variable_type": variable_type, "planned_value": "single controlled perturbation"},
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
        "reaction_profile_name",
        "lab_demonstration_allowed",
        "route_type",
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
