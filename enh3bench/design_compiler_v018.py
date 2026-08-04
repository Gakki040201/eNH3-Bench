"""Deterministic, model-independent M018 A2A evidence-to-design contracts."""

from __future__ import annotations

from collections import Counter
import csv
import hashlib
from html import escape
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator


DESIGN_PROBLEM_SCHEMA_VERSION = "0.18-design-problem.1"
DESIGN_CARD_SCHEMA_VERSION = "0.18-design-card.1"
CRITIC_RESULT_SCHEMA_VERSION = "0.18-critic-result.1"
SIMULATION_JOB_SCHEMA_VERSION = "0.18-simulation-job.1"

REACTION_FAMILIES = ("LiNRR", "eNRR", "NO3RR", "NO2RR", "NORR", "mixed", "unclear")
DESIGN_DOMAINS = (
    "electrolyte",
    "electrode_current_collector",
    "electrochemical_operation",
    "reactor_chamber",
    "process_product_handling",
)
DESIGN_CLASSES = (
    "electrolyte", "electrode", "current_collector", "reactor_geometry", "flow_field", "integrated_system",
)
CRITIC_TYPES = (
    "evidence_critic", "chemistry_critic", "electrochemical_critic", "engineering_critic",
    "safety_capability_critic",
)
SIMULATION_TYPES = ("surrogate", "COMSOL", "DFT", "MD", "no_simulation", "human_required")
GATE_TYPES = (
    "GATE_SIMULATION_EXPENSIVE",
    "GATE_EXPERIMENT_SAFETY",
    "GATE_EXPERIMENT_EXECUTION",
    "GATE_RESULT_ACCEPTANCE",
    "GATE_MODEL_UPDATE",
)

SCHEMA_FILENAMES = {
    "design_problem": "v018_design_problem.schema.json",
    "design_card": "v018_design_card.schema.json",
    "critic_result": "v018_critic_result.schema.json",
    "simulation_job": "v018_simulation_job.schema.json",
}

UNIT_ALLOWLIST = {
    "1", "%", "ppm", "mol L^-1", "mmol L^-1", "umol L^-1", "mg L^-1", "ug L^-1",
    "mL", "L", "S m^-1", "mS cm^-1", "mPa s", "cm2", "m2", "nm", "um", "mm", "cm", "m",
    "mA cm^-2", "A cm^-2", "mA", "A", "V", "C", "s", "min", "h", "K", "degC", "Pa", "kPa",
    "bar", "mL min^-1", "L min^-1", "mg h^-1", "ug h^-1", "mmol h^-1", "kWh kg^-1", "USD",
}

VARIABLE_DEFINITIONS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "electrolyte": (
        ("salt_identity", "string", "1"),
        ("salt_concentration", "number", "mol L^-1"),
        ("solvent_identity", "string", "1"),
        ("solvent_fraction", "number", "%"),
        ("proton_donor_identity", "string", "1"),
        ("proton_donor_concentration", "number", "mol L^-1"),
        ("water_content_ppm", "number", "ppm"),
        ("additive_identity", "string", "1"),
        ("additive_concentration", "number", "mol L^-1"),
        ("electrolyte_volume", "number", "mL"),
        ("conductivity", "number", "S m^-1"),
        ("viscosity", "number", "mPa s"),
    ),
    "electrode_current_collector": (
        ("substrate_material", "string", "1"),
        ("catalyst_or_deposit", "string", "1"),
        ("surface_area", "number", "cm2"),
        ("geometric_area", "number", "cm2"),
        ("roughness", "number", "1"),
        ("porosity", "number", "%"),
        ("thickness", "number", "um"),
        ("pore_size", "number", "um"),
        ("pretreatment", "string", "1"),
        ("coating_method", "string", "1"),
        ("current_collector_geometry", "string", "1"),
    ),
    "electrochemical_operation": (
        ("current_density", "number", "mA cm^-2"),
        ("current", "number", "mA"),
        ("potential", "number", "V"),
        ("cell_voltage", "number", "V"),
        ("charge_passed", "number", "C"),
        ("operation_time", "number", "h"),
        ("pulse_program", "string", "1"),
        ("temperature", "number", "degC"),
        ("pressure", "number", "bar"),
        ("gas_composition", "string", "1"),
        ("gas_flow_rate", "number", "mL min^-1"),
        ("liquid_flow_rate", "number", "mL min^-1"),
    ),
    "reactor_chamber": (
        ("cell_type", "string", "1"),
        ("chamber_volume", "number", "mL"),
        ("electrode_gap", "number", "mm"),
        ("channel_pattern", "string", "1"),
        ("channel_width", "number", "mm"),
        ("channel_height", "number", "mm"),
        ("channel_depth", "number", "mm"),
        ("channel_length", "number", "mm"),
        ("inlet_count", "integer", "1"),
        ("outlet_count", "integer", "1"),
        ("manifold_geometry", "string", "1"),
        ("membrane_type", "string", "1"),
        ("membrane_area", "number", "cm2"),
        ("separator_thickness", "number", "um"),
        ("headspace_volume", "number", "mL"),
        ("reactor_pressure_rating", "number", "bar"),
    ),
    "process_product_handling": (
        ("ammonia_capture_method", "string", "1"),
        ("electrolyte_recycle", "boolean", "1"),
        ("gas_recycle", "boolean", "1"),
        ("sampling_interval", "number", "min"),
        ("product_separation", "string", "1"),
        ("water_management", "string", "1"),
        ("pressure_control", "string", "1"),
    ),
}

OBJECTIVE_DEFINITIONS: tuple[tuple[str, str, str, str], ...] = (
    ("faradaic_efficiency_nh3", "maximize", "%", "quantified NH3 and charge accounting"),
    ("nh3_production_rate", "maximize", "mg h^-1", "quantified NH3 production"),
    ("nh3_concentration", "maximize", "mg L^-1", "validated product analysis"),
    ("energy_efficiency", "maximize", "%", "energy and product accounting"),
    ("cell_voltage", "minimize", "V", "electrochemical measurement"),
    ("stability", "maximize", "h", "time-series experiment"),
    ("selectivity", "maximize", "%", "product analysis"),
    ("replicate_success_rate", "maximize", "%", "replicate outcome audit"),
    ("mass_transfer_uniformity", "maximize", "%", "simulation or spatial measurement"),
    ("current_distribution_uniformity", "maximize", "%", "simulation or spatial measurement"),
    ("pressure_drop", "minimize", "Pa", "flow simulation or measurement"),
    ("electrolyte_inventory", "minimize", "mL", "configured design accounting"),
    ("manufacturability", "maximize", "1", "engineering review"),
    ("experimental_cost", "minimize", "USD", "configured cost accounting"),
    ("simulation_cost", "minimize", "USD", "configured compute accounting"),
    ("safety_risk", "minimize", "1", "safety review"),
    ("information_gain", "maximize", "1", "experimental-design analysis"),
)

FORBIDDEN_KEYS = {
    "api_key", "apikey", "authorization", "chain_of_thought", "cookie", "credential", "credentials",
    "hidden_label", "hidden_labels", "hostname", "machine_hostname", "model_reasoning", "password",
    "reasoning", "secret", "token", "username", "windows_username",
}
FORBIDDEN_SEGMENTS = {"authorization", "credential", "credentials", "password", "secret", "token"}
ABSOLUTE_PATH_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|/|\\\\)")
SECRET_VALUE_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    re.compile(r"\b(?:sk|ghp|github_pat)-?[A-Za-z0-9_]{16,}\b"),
)

MISSING_INPUT_SPECS = (
    ("linnr_specific_paper_coverage", "evidence", "LiNRR-specific paper coverage", "candidate_generation"),
    ("si_coverage", "evidence", "SI coverage", "candidate_generation"),
    ("electrolyte_composition_coverage", "chemistry", "electrolyte composition coverage", "candidate_generation"),
    ("water_content_coverage", "chemistry", "water-content coverage", "candidate_generation"),
    ("proton_donor_coverage", "chemistry", "proton-donor coverage", "candidate_generation"),
    ("current_density_coverage", "electrochemical", "current-density coverage", "candidate_generation"),
    ("charge_coverage", "electrochemical", "charge coverage", "candidate_generation"),
    ("electrode_area_coverage", "engineering", "electrode-area coverage", "candidate_generation"),
    ("reactor_dimension_coverage", "engineering", "reactor-dimension coverage", "simulation_routing"),
    ("flow_rate_coverage", "engineering", "flow-rate coverage", "simulation_routing"),
    ("pressure_coverage", "engineering", "pressure coverage", "candidate_generation"),
    ("temperature_coverage", "engineering", "temperature coverage", "candidate_generation"),
    ("quantification_controls", "controls", "quantification controls", "experiment_execution"),
    ("isotope_controls", "controls", "isotope controls", "experiment_execution"),
    ("laboratory_reagent_availability", "capability", "laboratory reagent availability", "candidate_generation"),
    ("instrument_availability", "capability", "instrument availability", "experiment_execution"),
    ("comsol_base_model_availability", "simulation", "COMSOL base-model availability", "COMSOL_routing"),
    ("dft_structure_availability", "simulation", "DFT structure availability", "DFT_routing"),
    ("md_force_field_availability", "simulation", "MD force-field availability", "MD_routing"),
)


def stable_id(prefix: str, *identity_parts: Any) -> str:
    """Return a formatting-, host-, path-, and timestamp-independent stable ID."""

    payload = json.dumps(identity_parts, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24].upper()}"


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")


def content_sha256(value: Mapping[str, Any]) -> str:
    payload = {key: child for key, child in value.items() if key != "content_hash"}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def with_content_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    rendered = dict(value)
    rendered["content_hash"] = content_sha256(rendered)
    return rendered


def _schema_root() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas"


def load_schema(kind: str, schema_root: str | Path | None = None) -> dict[str, Any]:
    if kind not in SCHEMA_FILENAMES:
        raise ValueError(f"unknown schema kind: {kind}")
    root = Path(schema_root) if schema_root is not None else _schema_root()
    schema = json.loads((root / SCHEMA_FILENAMES[kind]).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return schema


def _schema_errors(value: Any, kind: str, schema_root: str | Path | None = None) -> list[str]:
    validator = Draft202012Validator(load_schema(kind, schema_root), format_checker=Draft202012Validator.FORMAT_CHECKER)
    errors: list[str] = []
    for issue in sorted(validator.iter_errors(value), key=lambda item: (list(item.absolute_path), item.message)):
        path = "$" + "".join(f"[{part}]" if isinstance(part, int) else f".{part}" for part in issue.absolute_path)
        errors.append(f"{path}: {issue.message}")
    return errors


def _scan_forbidden(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            if normalized in FORBIDDEN_KEYS or set(normalized.split("_")) & FORBIDDEN_SEGMENTS:
                errors.append(f"forbidden field at {path}.{key}")
            _scan_forbidden(child, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden(child, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        if ABSOLUTE_PATH_RE.match(value):
            errors.append(f"absolute path is forbidden at {path}")
        if any(pattern.search(value) for pattern in SECRET_VALUE_PATTERNS):
            errors.append(f"possible secret value at {path}")


def is_safe_relative_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        return False
    pure = PurePosixPath(value)
    return not (
        value.startswith("/") or value.startswith("//") or re.match(r"^[A-Za-z]:", value)
        or pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts)
    )


def _unit_errors(records: Iterable[Mapping[str, Any]], prefix: str) -> list[str]:
    errors: list[str] = []
    for index, record in enumerate(records):
        unit = record.get("unit")
        if unit is not None and unit not in UNIT_ALLOWLIST:
            errors.append(f"{prefix}[{index}].unit is not in the explicit unit allowlist: {unit}")
    return errors


def _duplicates(values: Iterable[str]) -> list[str]:
    counts = Counter(values)
    return sorted(key for key, count in counts.items() if key and count > 1)


def validate_design_problem(problem: Any, *, schema_root: str | Path | None = None) -> dict[str, Any]:
    errors = _schema_errors(problem, "design_problem", schema_root)
    _scan_forbidden(problem, "$", errors)
    if not isinstance(problem, dict):
        return _validation_result(DESIGN_PROBLEM_SCHEMA_VERSION, "", errors)

    variables = [item for item in problem.get("decision_variables", []) if isinstance(item, dict)]
    objectives = [item for item in problem.get("objectives", []) if isinstance(item, dict)]
    hard = [item for item in problem.get("hard_constraints", []) if isinstance(item, dict)]
    soft = [item for item in problem.get("soft_constraints", []) if isinstance(item, dict)]
    duplicate_variable_ids = _duplicates(str(item.get("variable_id") or "") for item in variables)
    if duplicate_variable_ids:
        errors.append(f"duplicate variable IDs: {duplicate_variable_ids}")
    duplicate_names = _duplicates(str(item.get("name") or "") for item in variables)
    if duplicate_names:
        errors.append(f"duplicate variable names: {duplicate_names}")
    duplicate_objectives = _duplicates(str(item.get("objective_id") or "") for item in objectives)
    if duplicate_objectives:
        errors.append(f"duplicate objective IDs: {duplicate_objectives}")
    errors.extend(_unit_errors(variables, "decision_variables"))
    errors.extend(_unit_errors(objectives, "objectives"))

    variable_ids = {str(item.get("variable_id") or "") for item in variables}
    for index, variable in enumerate(variables):
        source_status = variable.get("source_status")
        nominal = variable.get("nominal_value")
        refs = variable.get("evidence_refs") or []
        if source_status == "reported" and (nominal is None or not refs):
            errors.append(f"decision_variables[{index}] reported values require a nominal value and evidence_refs")
        if source_status in {"derived", "assumed"} and nominal is None:
            errors.append(f"decision_variables[{index}] {source_status} value must be explicit")
        if source_status in {"unknown", "not_applicable"} and nominal is not None:
            errors.append(f"decision_variables[{index}] {source_status} value must not invent a nominal value")
        bounds = variable.get("numeric_bounds")
        allowed = variable.get("allowed_values")
        data_type = variable.get("data_type")
        if bounds is not None:
            if data_type not in {"number", "integer"}:
                errors.append(f"decision_variables[{index}] numeric_bounds require numeric data_type")
            minimum, maximum = bounds.get("minimum"), bounds.get("maximum")
            if minimum is not None and maximum is not None and minimum > maximum:
                errors.append(f"decision_variables[{index}] numeric bounds are inverted")
            if nominal is not None and isinstance(nominal, (int, float)) and not isinstance(nominal, bool):
                if minimum is not None and nominal < minimum:
                    errors.append(f"decision_variables[{index}] nominal value is below minimum")
                if maximum is not None and nominal > maximum:
                    errors.append(f"decision_variables[{index}] nominal value is above maximum")
        if allowed is not None and nominal is not None and nominal not in allowed:
            errors.append(f"decision_variables[{index}] nominal value is outside allowed_values")
        if data_type in {"number", "integer"} and allowed is not None and any(isinstance(item, str) for item in allowed):
            errors.append(f"decision_variables[{index}] numeric variable has categorical string values")
        expected_variable_id = stable_id(
            "DV18", DESIGN_PROBLEM_SCHEMA_VERSION, variable.get("domain"), variable.get("name")
        )
        if variable.get("variable_id") != expected_variable_id:
            errors.append(f"decision_variables[{index}].variable_id is not deterministic; expected {expected_variable_id}")

    for index, objective in enumerate(objectives):
        expected_objective_id = stable_id("OBJ18", DESIGN_PROBLEM_SCHEMA_VERSION, objective.get("name"))
        if objective.get("objective_id") != expected_objective_id:
            errors.append(f"objectives[{index}].objective_id is not deterministic; expected {expected_objective_id}")

    for label, records, expected in (("hard_constraints", hard, "hard"), ("soft_constraints", soft, "soft")):
        for index, record in enumerate(records):
            if record.get("constraint_type") != expected:
                errors.append(f"{label}[{index}] must declare constraint_type={expected}")
            unknown = sorted(set(record.get("affected_variables") or []) - variable_ids)
            if unknown:
                errors.append(f"{label}[{index}] references unknown variables: {unknown}")
            expected_constraint_id = stable_id(
                "CON18", DESIGN_PROBLEM_SCHEMA_VERSION, expected, record.get("name"), record.get("expression")
            )
            if record.get("constraint_id") != expected_constraint_id:
                errors.append(f"{label}[{index}].constraint_id is not deterministic; expected {expected_constraint_id}")

    reaction_family = problem.get("reaction_family")
    direct = 0
    for index, ref in enumerate(problem.get("evidence_package_refs") or []):
        if not isinstance(ref, dict):
            continue
        role = ref.get("cross_family_role")
        coverage = ref.get("reaction_family_coverage") or []
        if role == "direct_design_evidence":
            direct += 1
            if reaction_family not in coverage:
                errors.append(f"evidence_package_refs[{index}] cross-family package cannot be direct design evidence")
        if ref.get("review_status") == "machine_drafted" and role == "direct_design_evidence":
            # Allowed as input, but it remains visibly unaccepted and cannot be promoted.
            pass
    if reaction_family == "LiNRR" and direct > 1:
        errors.append("the frozen pilot contains only one LiNRR-labelled package; direct evidence count cannot exceed one")

    for index, failure in enumerate(problem.get("known_failure_modes") or []):
        if not isinstance(failure, dict):
            continue
        expected_failure_id = stable_id(
            "CON18", DESIGN_PROBLEM_SCHEMA_VERSION, "failure_mode", failure.get("description"), failure.get("detection_method")
        )
        if failure.get("failure_mode_id") != expected_failure_id:
            errors.append(f"known_failure_modes[{index}].failure_mode_id is not deterministic; expected {expected_failure_id}")

    gates = [item for item in problem.get("human_gate_policy", []) if isinstance(item, dict)]
    if set(item.get("gate_type") for item in gates) != set(GATE_TYPES):
        errors.append("human_gate_policy must define exactly the five critical A2A gate types")
    if problem.get("provenance", {}).get("generated_by") == "deterministic_compiler":
        for index, gate in enumerate(gates):
            expected_gate_id = stable_id("HG18", DESIGN_PROBLEM_SCHEMA_VERSION, gate.get("gate_type"))
            if gate.get("gate_id") != expected_gate_id:
                errors.append(f"human_gate_policy[{index}].gate_id is not deterministic; expected {expected_gate_id}")
            if gate.get("status") not in {"pending", "not_triggered"}:
                errors.append(f"human_gate_policy[{index}] deterministic compiler cannot fabricate approval status")
            if any(gate.get(field) is not None for field in ("decision", "decision_timestamp", "decision_provenance")):
                errors.append(f"human_gate_policy[{index}] deterministic compiler cannot fabricate a decision")

    expected_id = stable_id(
        "DP18", DESIGN_PROBLEM_SCHEMA_VERSION, problem.get("reaction_family"), problem.get("scientific_objective")
    )
    if problem.get("design_problem_id") != expected_id:
        errors.append(f"design_problem_id is not deterministic; expected {expected_id}")
    if problem.get("content_hash") != content_sha256(problem):
        errors.append("content_hash mismatch")
    return _validation_result(DESIGN_PROBLEM_SCHEMA_VERSION, problem.get("design_problem_id"), errors)


def validate_design_card(card: Any, *, schema_root: str | Path | None = None) -> dict[str, Any]:
    errors = _schema_errors(card, "design_card", schema_root)
    _scan_forbidden(card, "$", errors)
    if not isinstance(card, dict):
        return _validation_result(DESIGN_CARD_SCHEMA_VERSION, "", errors)
    assignments = [item for item in card.get("decision_variables", []) if isinstance(item, dict)]
    fixed = [item for item in card.get("fixed_conditions", []) if isinstance(item, dict)]
    duplicate_ids = _duplicates(str(item.get("variable_id") or "") for item in [*assignments, *fixed])
    if duplicate_ids:
        errors.append(f"duplicate variable assignments: {duplicate_ids}")
    errors.extend(_unit_errors([*assignments, *fixed], "variables"))
    if card.get("artifact_label") == "NON_SCIENTIFIC_FIXTURE":
        if card.get("provenance", {}).get("generated_by") != "synthetic_fixture":
            errors.append("NON_SCIENTIFIC_FIXTURE cards require synthetic_fixture provenance")
    if card.get("artifact_label") == "EXECUTABLE_DESIGN":
        if not card.get("falsification_criteria"):
            errors.append("executable card requires a falsification criterion")
        for index, assignment in enumerate(assignments):
            if assignment.get("required") and (
                assignment.get("value") is None or assignment.get("source_status") in {"unknown", "not_applicable"}
            ):
                errors.append(f"executable card required variable is unspecified at decision_variables[{index}]")
        for index, constraint in enumerate(card.get("constraints") or []):
            if isinstance(constraint, dict) and constraint.get("constraint_type") == "hard" and constraint.get("status") != "pass":
                errors.append(f"executable card hard constraint did not pass at constraints[{index}]")
        safety_gates = [gate for gate in card.get("human_gates") or [] if gate.get("gate_type") == "GATE_EXPERIMENT_SAFETY"]
        if not safety_gates or any(gate.get("status") == "rejected" for gate in safety_gates):
            errors.append("executable card safety gate is absent or failed")
        if not card.get("required_controls"):
            errors.append("executable card requires controls")
        if not card.get("required_measurements"):
            errors.append("executable card requires measurements")
    expected_id = stable_id(
        "DES18", DESIGN_CARD_SCHEMA_VERSION, card.get("design_class"), card.get("reaction_family"), card.get("hypothesis")
    )
    if card.get("design_id") != expected_id:
        errors.append(f"design_id is not deterministic; expected {expected_id}")
    if card.get("content_hash") != content_sha256(card):
        errors.append("content_hash mismatch")
    return _validation_result(DESIGN_CARD_SCHEMA_VERSION, card.get("design_id"), errors)


def validate_critic_result(result: Any, *, schema_root: str | Path | None = None) -> dict[str, Any]:
    errors = _schema_errors(result, "critic_result", schema_root)
    _scan_forbidden(result, "$", errors)
    if not isinstance(result, dict):
        return _validation_result(CRITIC_RESULT_SCHEMA_VERSION, "", errors)
    verdict = result.get("verdict")
    blocking = result.get("blocking")
    if verdict == "fail" and blocking is not True:
        errors.append("fail critic verdict must be blocking")
    if verdict in {"pass", "warning", "not_evaluated"} and blocking is not False:
        errors.append(f"{verdict} critic verdict must not be blocking")
    expected_id = stable_id(
        "CRIT18", CRITIC_RESULT_SCHEMA_VERSION, result.get("critic_type"), result.get("design_id"),
        result.get("finding_code"), result.get("affected_variables"),
    )
    if result.get("critic_result_id") != expected_id:
        errors.append(f"critic_result_id is not deterministic; expected {expected_id}")
    return _validation_result(CRITIC_RESULT_SCHEMA_VERSION, result.get("critic_result_id"), errors)


def validate_simulation_job(job: Any, *, schema_root: str | Path | None = None) -> dict[str, Any]:
    errors = _schema_errors(job, "simulation_job", schema_root)
    _scan_forbidden(job, "$", errors)
    if not isinstance(job, dict):
        return _validation_result(SIMULATION_JOB_SCHEMA_VERSION, "", errors)
    simulation_type = job.get("simulation_type")
    if simulation_type in {"COMSOL", "DFT", "MD"} and job.get("human_gate_required") is not True:
        errors.append(f"{simulation_type} job must require the expensive-simulation human gate")
    if job.get("status") in {"approved", "completed"} and job.get("provenance", {}).get("generated_by") == "deterministic_compiler":
        errors.append("deterministic compiler cannot approve or complete simulation jobs")
    expected_id = stable_id(
        "SIM18", SIMULATION_JOB_SCHEMA_VERSION, job.get("design_id"), job.get("simulation_type"),
        job.get("simulation_target"), job.get("scientific_question"),
    )
    if job.get("simulation_job_id") != expected_id:
        errors.append(f"simulation_job_id is not deterministic; expected {expected_id}")
    return _validation_result(SIMULATION_JOB_SCHEMA_VERSION, job.get("simulation_job_id"), errors)


def _validation_result(schema_version: str, artifact_id: Any, errors: Sequence[str]) -> dict[str, Any]:
    unique = sorted(set(errors))
    return {
        "schema_version": schema_version,
        "artifact_id": str(artifact_id or ""),
        "result": "FAIL" if unique else "PASS",
        "error_count": len(unique),
        "errors": unique,
    }


def human_gate(gate_type: str) -> dict[str, Any]:
    if gate_type not in GATE_TYPES:
        raise ValueError(f"unknown human gate: {gate_type}")
    details = {
        "GATE_SIMULATION_EXPENSIVE": (
            "before a high-cost COMSOL, DFT, or MD job", ["complete simulation inputs", "cost estimate", "scientific question"], "simulation_lead",
        ),
        "GATE_EXPERIMENT_SAFETY": (
            "before a wet-lab instruction is accepted", ["hazard assessment", "capability assessment", "waste plan"], "laboratory_safety_approver",
        ),
        "GATE_EXPERIMENT_EXECUTION": (
            "before an experiment is started", ["approved design card", "controls", "measurements", "operator readiness"], "laboratory_lead",
        ),
        "GATE_RESULT_ACCEPTANCE": (
            "before new results enter the learning loop", ["raw data", "controls", "provenance", "quality review"], "result_reviewer",
        ),
        "GATE_MODEL_UPDATE": (
            "before a newly fitted model becomes active", ["training manifest", "validation report", "versioned model card"], "model_governance_approver",
        ),
    }
    trigger, required, role = details[gate_type]
    return {
        "gate_id": stable_id("HG18", DESIGN_PROBLEM_SCHEMA_VERSION, gate_type),
        "gate_type": gate_type,
        "trigger": trigger,
        "required_information": required,
        "approver_role": role,
        "status": "pending",
        "decision": None,
        "decision_timestamp": None,
        "decision_provenance": None,
    }


def unknown_uncertainty(notes: str | None = None) -> dict[str, Any]:
    return {"method": "not_available", "lower": None, "upper": None, "notes": notes}


def build_variable(domain: str, name: str, data_type: str, unit: str) -> dict[str, Any]:
    return {
        "variable_id": stable_id("DV18", DESIGN_PROBLEM_SCHEMA_VERSION, domain, name),
        "domain": domain,
        "name": name,
        "data_type": data_type,
        "unit": unit,
        "allowed_values": None,
        "numeric_bounds": None,
        "nominal_value": None,
        "controllability": "unknown",
        "measurement_method": None,
        "source_status": "unknown",
        "evidence_refs": [],
        "uncertainty": unknown_uncertainty("No real candidate value is generated in A2A."),
        "cost_class": "unknown",
        "safety_class": "unknown",
    }


def _objective(name: str, direction: str, unit: str, source: str) -> dict[str, Any]:
    return {
        "objective_id": stable_id("OBJ18", DESIGN_PROBLEM_SCHEMA_VERSION, name),
        "name": name,
        "direction": direction,
        "unit": unit,
        "measurement_or_simulation_source": source,
        "target": None,
        "acceptable_threshold": None,
        "weight": None,
        "hard_or_soft": "soft",
        "uncertainty_method": "not configured; must be supplied before candidate evaluation",
    }


def _constraint(kind: str, name: str, expression: str, operator: str, value: Any) -> dict[str, Any]:
    return {
        "constraint_id": stable_id("CON18", DESIGN_PROBLEM_SCHEMA_VERSION, kind, name, expression),
        "constraint_type": kind,
        "name": name,
        "expression": expression,
        "affected_variables": [],
        "operator": operator,
        "value": value,
        "unit": None,
        "source_status": "configured",
        "evidence_refs": [],
        "uncertainty": {"method": "configured", "lower": None, "upper": None, "notes": "A2A contract policy."},
    }


def _failure_mode(name: str, description: str, detection: str, blocking: bool = True) -> dict[str, Any]:
    return {
        "failure_mode_id": stable_id("CON18", DESIGN_PROBLEM_SCHEMA_VERSION, "failure_mode", description, detection),
        "description": description,
        "detection_method": detection,
        "blocking": blocking,
        "source_status": "configured",
        "evidence_refs": [],
    }


def _laboratory_capabilities() -> list[dict[str, Any]]:
    source = "enh3bench/lab_profile.py"
    return [
        _capability("laboratory_reagent_availability", "reagent", "unknown", None, source),
        _capability("instrument_availability", "instrument", "unknown", None, source),
        _capability("quantification_controls", "control", "unavailable", False, source),
        _capability("isotope_controls", "control", "unavailable", False, source),
        _capability("COMSOL_base_model", "simulation", "unknown", None, source),
        _capability("DFT_structure", "simulation", "unknown", None, source),
        _capability("MD_force_field_strategy", "simulation", "unknown", None, source),
        _capability("flow_cell", "reactor", "unavailable", False, source),
        _capability("LiNRR_SOP", "safety", "unavailable", False, source),
    ]


def _capability(name: str, category: str, availability: str, value: Any, source_ref: str) -> dict[str, Any]:
    return {
        "capability_name": name,
        "category": category,
        "availability": availability,
        "configured_value": value,
        "unit": None,
        "source_status": "configured" if availability != "unknown" else "unknown",
        "source_ref": source_ref,
        "notes": "Fail-closed capability state; no availability is inferred.",
    }


def load_a1_index(a1_runtime_root: str | Path) -> list[dict[str, Any]]:
    root = Path(a1_runtime_root)
    path = root / "reports" / "v018_a1_package_index.json"
    index = json.loads(path.read_text(encoding="utf-8"))
    if index.get("schema_version") != "0.18-evidence-package.1" or not isinstance(index.get("packages"), list):
        raise ValueError("invalid A1 package index")
    rows = index["packages"]
    if len(rows) != 12 or any(row.get("validation_result") != "PASS" for row in rows):
        raise ValueError("A1 package index must contain exactly 12 passing packages")
    return rows


def build_linnr_design_problem(a1_runtime_root: str | Path, code_commit: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-f0-9]{40}", code_commit):
        raise ValueError("code_commit must be a lowercase 40-character Git SHA")
    index_rows = load_a1_index(a1_runtime_root)
    variables = [
        build_variable(domain, name, data_type, unit)
        for domain in DESIGN_DOMAINS
        for name, data_type, unit in VARIABLE_DEFINITIONS[domain]
    ]
    evidence_refs: list[dict[str, Any]] = []
    for row in index_rows:
        coverage = list(row["reaction_family_coverage"])
        if "LiNRR" in coverage:
            role = "direct_design_evidence"
        elif any(family in {"eNRR", "NO3RR", "NO2RR", "NORR"} for family in coverage):
            role = "validation_pattern"
        else:
            role = "methodological_context"
        evidence_refs.append({
            "paper_id": row["paper_id"],
            "package_id": row["package_id"],
            "package_path": row["package_path"],
            "reaction_family_coverage": coverage,
            "cross_family_role": role,
            "review_status": row["review_status"],
            "content_sha256": row["content_sha256"],
            "evidence_link_count": row["evidence_link_count"],
        })
    objective_text = (
        "Compile a machine-readable LiNRR closed-loop discovery design space while preserving missing inputs, "
        "evidence status, critical human gates, and separate multi-objective definitions; do not generate or rank candidates."
    )
    problem = {
        "schema_version": DESIGN_PROBLEM_SCHEMA_VERSION,
        "design_problem_id": stable_id("DP18", DESIGN_PROBLEM_SCHEMA_VERSION, "LiNRR", objective_text),
        "reaction_family": "LiNRR",
        "scientific_objective": objective_text,
        "design_domains": list(DESIGN_DOMAINS),
        "decision_variables": variables,
        "objectives": [_objective(*definition) for definition in OBJECTIVE_DEFINITIONS],
        "hard_constraints": [
            _constraint("hard", "no_candidate_generation", "A2A must not generate or rank scientific candidate values", "policy", True),
            _constraint("hard", "facts_require_status", "Scientific facts must be reported or explicitly configured; derived and assumed values remain labelled", "policy", True),
            _constraint("hard", "same_family_direct_evidence", "Only same-family packages may have direct_design_evidence role", "policy", True),
            _constraint("hard", "critical_human_gates", "Expensive simulation, safety, execution, result acceptance, and model updates require human gates", "policy", True),
        ],
        "soft_constraints": [
            _constraint("soft", "resolve_missing_inputs", "Missing-input inventory should be resolved before real candidate generation", "policy", True),
            _constraint("soft", "preserve_multi_objective", "Objectives remain separate and are not collapsed into a fabricated aggregate score", "policy", True),
        ],
        "laboratory_capabilities": _laboratory_capabilities(),
        "evidence_package_refs": evidence_refs,
        "known_failure_modes": [
            _failure_mode("insufficient_linnr_coverage", "A single LiNRR-labelled pilot package is insufficient for a LiNRR training corpus.", "Count same-family package references."),
            _failure_mode("missing_exact_inputs", "Missing composition, operation, geometry, or control inputs can make a design non-executable.", "Run deterministic missing-input and critic checks."),
            _failure_mode("context_promoted_to_support", "Context-only or cross-family evidence must not become primary positive support.", "Check explicit cross-family roles and support roles."),
            _failure_mode("fabricated_approval", "A deterministic compiler must not create a human approval.", "Require null decisions and pending gate states."),
        ],
        "simulation_capabilities": list(SIMULATION_TYPES),
        "human_gate_policy": [human_gate(gate_type) for gate_type in GATE_TYPES],
        "provenance": {
            "generated_by": "deterministic_compiler",
            "generation_method": "v018_a2a_offline_design_problem_compiler",
            "source_refs": ["reports/v018_a1_package_index.json", "enh3bench/lab_profile.py"],
            "code_commit": code_commit,
            "parent_ids": [row["package_id"] for row in index_rows],
        },
    }
    return with_content_hash(problem)


def _p0797_measurement_status(a1_runtime_root: str | Path) -> dict[str, str]:
    path = Path(a1_runtime_root) / "packages" / "P0797" / "evidence_package.json"
    package = json.loads(path.read_text(encoding="utf-8"))
    statuses: dict[str, str] = {}
    for experiment in package.get("experiment_records") or []:
        for name, record in (experiment.get("measurements") or {}).items():
            status = str(record.get("status") or "unknown")
            previous = statuses.get(name)
            if previous != "reported" or status == "reported":
                statuses[name] = status
    supplementary = [
        record.get("availability_status") for record in package.get("source_documents") or []
        if record.get("document_type") == "supplementary"
    ]
    statuses["supplementary"] = supplementary[0] if supplementary else "not_reported"
    statuses["direct_linnr_package_count"] = "1"
    return statuses


def missing_input_inventory(problem: Mapping[str, Any], a1_runtime_root: str | Path) -> list[dict[str, str]]:
    statuses = _p0797_measurement_status(a1_runtime_root)
    reported_map = {
        "electrolyte_composition_coverage": "electrolyte",
        "current_density_coverage": "current_density_ma_cm2",
        "pressure_coverage": "pressure",
        "temperature_coverage": "temperature",
        "quantification_controls": "blank_control",
        "isotope_controls": "isotope_validation",
    }
    capability_map = {
        "laboratory_reagent_availability": "laboratory_reagent_availability",
        "instrument_availability": "instrument_availability",
        "comsol_base_model_availability": "COMSOL_base_model",
        "dft_structure_availability": "DFT_structure",
        "md_force_field_availability": "MD_force_field_strategy",
    }
    capabilities = {item["capability_name"]: item for item in problem["laboratory_capabilities"]}
    rows: list[dict[str, str]] = []
    for input_id, category, label, required_before in MISSING_INPUT_SPECS:
        status = "missing"
        observed = "not_reported"
        if input_id == "linnr_specific_paper_coverage":
            status, observed = "insufficient", "1 LiNRR-labelled package of 12; not a sufficient training corpus"
        elif input_id == "si_coverage":
            observed = statuses.get("supplementary", "not_reported")
        elif input_id in reported_map:
            observed = statuses.get(reported_map[input_id], "not_reported")
            if observed == "reported":
                status = "reported"
            if input_id in {"quantification_controls", "isotope_controls"} and observed == "reported":
                status, observed = "insufficient", "reported as unclear"
        elif input_id in capability_map:
            capability = capabilities[capability_map[input_id]]
            observed = capability["availability"]
            if observed == "available":
                status = "configured"
        rows.append({
            "input_id": input_id,
            "category": category,
            "label": label,
            "status": status,
            "observed_state": observed,
            "required_before": required_before,
            "recommended_resolution": "Supply an exact reported or explicitly configured value with provenance; do not infer it.",
        })
    return rows


def design_space_inventory(problem: Mapping[str, Any], missing_rows: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    role_counts = Counter(ref["cross_family_role"] for ref in problem["evidence_package_refs"])
    domain_counts = Counter(variable["domain"] for variable in problem["decision_variables"])
    status_counts = Counter(row["status"] for row in missing_rows)
    inventory = {
        "schema_version": "0.18-design-space-inventory.1",
        "design_problem_id": problem["design_problem_id"],
        "reaction_family": problem["reaction_family"],
        "design_domain_counts": dict(sorted(domain_counts.items())),
        "decision_variable_count": len(problem["decision_variables"]),
        "objective_count": len(problem["objectives"]),
        "aggregate_score_present": False,
        "evidence_package_count": len(problem["evidence_package_refs"]),
        "evidence_role_counts": dict(sorted(role_counts.items())),
        "direct_linnr_package_count": role_counts.get("direct_design_evidence", 0),
        "linnr_training_corpus_sufficient": False,
        "missing_input_status_counts": dict(sorted(status_counts.items())),
        "candidate_count": 0,
        "recommendation_count": 0,
        "simulator_runs": {"COMSOL": 0, "DFT": 0, "MD": 0},
        "notice": "Contract and offline inventory only; no scientific candidate or Top-11 recommendation was generated.",
    }
    return with_content_hash(inventory)


def render_inventory_html(inventory: Mapping[str, Any], missing_rows: Sequence[Mapping[str, str]]) -> str:
    rows = "".join(
        "<tr>" + "".join(f"<td>{escape(str(row[key]))}</td>" for key in ("label", "status", "observed_state", "required_before")) + "</tr>"
        for row in missing_rows
    )
    role_items = "".join(
        f"<li>{escape(role)}: {count}</li>" for role, count in sorted(inventory["evidence_role_counts"].items())
    )
    return (
        "<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>M018 A2A LiNRR design-space inventory</title><style>"
        "body{font-family:system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#172033}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd3df;padding:.45rem;text-align:left}"
        "th{background:#eef2f8}.notice{padding:1rem;background:#fff4cc;border-left:4px solid #b87900}"
        "code{background:#eef2f8;padding:.1rem .25rem}</style></head><body>"
        "<h1>M018 A2A LiNRR design-space inventory</h1>"
        f"<p class=\"notice\">{escape(inventory['notice'])}</p>"
        f"<p>Design problem: <code>{escape(inventory['design_problem_id'])}</code></p>"
        f"<p>Variables: {inventory['decision_variable_count']}; objectives: {inventory['objective_count']}; "
        f"candidate count: {inventory['candidate_count']}; recommendations: {inventory['recommendation_count']}.</p>"
        f"<p>LiNRR-labelled pilot packages: {inventory['direct_linnr_package_count']} of {inventory['evidence_package_count']}. "
        "This is not a sufficient LiNRR training corpus.</p>"
        f"<h2>Evidence roles</h2><ul>{role_items}</ul>"
        "<h2>Missing-input audit</h2><table><thead><tr><th>Input</th><th>Status</th><th>Observed state</th>"
        f"<th>Required before</th></tr></thead><tbody>{rows}</tbody></table>"
        "</body></html>\n"
    )


def ensure_external_runtime(runtime_root: str | Path, repository_root: str | Path) -> Path:
    runtime = Path(runtime_root).resolve()
    repository = Path(repository_root).resolve()
    if runtime == repository or repository in runtime.parents:
        raise ValueError("design-compiler runtime must remain outside the repository")
    return runtime


def write_runtime_outputs(
    runtime_root: str | Path,
    repository_root: str | Path,
    a1_runtime_root: str | Path,
    code_commit: str,
    *,
    clean: bool = False,
) -> dict[str, Any]:
    runtime = ensure_external_runtime(runtime_root, repository_root)
    problem = build_linnr_design_problem(a1_runtime_root, code_commit)
    validation = validate_design_problem(problem)
    if validation["result"] != "PASS":
        raise ValueError(f"compiled design problem failed validation: {validation['errors']}")
    missing_rows = missing_input_inventory(problem, a1_runtime_root)
    inventory = design_space_inventory(problem, missing_rows)
    html = render_inventory_html(inventory, missing_rows)

    owned = (
        Path("problems/linnr_discovery_problem.json"),
        Path("reports/linnr_design_space_inventory.json"),
        Path("reports/linnr_design_space_inventory.html"),
        Path("reports/linnr_missing_inputs.csv"),
    )
    if not clean and any((runtime / path).exists() for path in owned):
        raise FileExistsError("A2A outputs already exist; pass --clean to replace only named A2A artifacts")
    runtime.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v018_a2a_stage_", dir=runtime.parent) as name:
        stage = Path(name)
        for directory in ("inputs", "problems", "cards", "critics", "simulations", "reports", "logs"):
            (stage / directory).mkdir(parents=True, exist_ok=True)
        _write_json(stage / owned[0], problem)
        _write_json(stage / owned[1], inventory)
        (stage / owned[2]).write_text(html, encoding="utf-8", newline="\n")
        _write_missing_csv(stage / owned[3], missing_rows)
        reread = json.loads((stage / owned[0]).read_text(encoding="utf-8"))
        if validate_design_problem(reread)["result"] != "PASS":
            raise ValueError("staged design problem failed read-back validation")
        runtime.mkdir(parents=True, exist_ok=True)
        for directory in ("inputs", "problems", "cards", "critics", "simulations", "reports", "logs"):
            (runtime / directory).mkdir(parents=True, exist_ok=True)
        for relative in owned:
            target = runtime / relative
            if clean and target.exists():
                target.unlink()
            shutil.copyfile(stage / relative, target)
    return {
        "result": "PASS",
        "design_problem_id": problem["design_problem_id"],
        "content_hash": problem["content_hash"],
        "decision_variable_count": len(problem["decision_variables"]),
        "objective_count": len(problem["objectives"]),
        "missing_input_count": len(missing_rows),
        "candidate_count": 0,
        "recommendation_count": 0,
        "simulator_runs": {"COMSOL": 0, "DFT": 0, "MD": 0},
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _write_missing_csv(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    fields = ("input_id", "category", "label", "status", "observed_state", "required_before", "recommended_resolution")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def compare_output_trees(left: str | Path, right: str | Path) -> dict[str, Any]:
    left_root, right_root = Path(left), Path(right)
    left_files = {path.relative_to(left_root).as_posix(): path for path in left_root.rglob("*") if path.is_file()}
    right_files = {path.relative_to(right_root).as_posix(): path for path in right_root.rglob("*") if path.is_file()}
    differences: list[str] = []
    if set(left_files) != set(right_files):
        differences.append("file sets differ")
    for relative in sorted(set(left_files) & set(right_files)):
        if left_files[relative].read_bytes() != right_files[relative].read_bytes():
            differences.append(relative)
    return {"result": "PASS" if not differences else "FAIL", "differences": differences}


def make_critic_result(
    critic_type: str,
    design_id: str,
    verdict: str,
    severity: str,
    finding_code: str,
    finding_text: str,
    recommended_resolution: str,
    *,
    affected_variables: Sequence[str] = (),
    evidence_refs: Sequence[str] = (),
    uncertainty: str = "low",
    code_commit: str = "0" * 40,
) -> dict[str, Any]:
    result = {
        "schema_version": CRITIC_RESULT_SCHEMA_VERSION,
        "critic_result_id": stable_id(
            "CRIT18", CRITIC_RESULT_SCHEMA_VERSION, critic_type, design_id, finding_code, list(affected_variables)
        ),
        "critic_type": critic_type,
        "design_id": design_id,
        "verdict": verdict,
        "severity": severity,
        "finding_code": finding_code,
        "finding_text": finding_text,
        "affected_variables": list(affected_variables),
        "evidence_refs": list(evidence_refs),
        "recommended_resolution": recommended_resolution,
        "uncertainty": uncertainty,
        "blocking": verdict == "fail",
        "provenance": {
            "generated_by": "deterministic_compiler",
            "generation_method": "v018_a2a_rule_critic",
            "source_refs": ["enh3bench/design_compiler_v018.py"],
            "code_commit": code_commit,
            "parent_ids": [design_id],
        },
    }
    return result


def deterministic_critics(
    card: Mapping[str, Any],
    *,
    problem: Mapping[str, Any] | None = None,
    simulation_jobs: Sequence[Mapping[str, Any]] = (),
    code_commit: str = "0" * 40,
) -> list[dict[str, Any]]:
    assignments = {
        item["name"]: item for item in [*(card.get("decision_variables") or []), *(card.get("fixed_conditions") or [])]
        if isinstance(item, dict) and item.get("name")
    }
    results: list[dict[str, Any]] = []

    def specified(name: str) -> bool:
        item = assignments.get(name)
        return bool(item and item.get("value") is not None and item.get("source_status") not in {"unknown", "not_applicable"})

    def add(critic: str, verdict: str, severity: str, code: str, text: str, resolution: str, names: Sequence[str] = (), refs: Sequence[str] = ()) -> None:
        ids = [assignments[name]["variable_id"] for name in names if name in assignments]
        results.append(make_critic_result(
            critic, card["design_id"], verdict, severity, code, text, resolution,
            affected_variables=ids, evidence_refs=refs, code_commit=code_commit,
        ))

    if card.get("reaction_family") == "LiNRR" and not specified("water_content_ppm"):
        add("chemistry_critic", "warning", "high", "LINRR_WATER_CONTENT_UNKNOWN", "Water content is unknown for a water-sensitive LiNRR design.", "Specify a measured water-content value and method.", ("water_content_ppm",))
    if specified("proton_donor_identity") and not specified("proton_donor_concentration"):
        add("chemistry_critic", "fail", "high", "PROTON_DONOR_CONCENTRATION_MISSING", "A proton donor is specified without its concentration.", "Specify the proton-donor concentration with units.", ("proton_donor_identity", "proton_donor_concentration"))
    if specified("current_density") and not (specified("geometric_area") or specified("surface_area")):
        add("electrochemical_critic", "fail", "high", "CURRENT_DENSITY_AREA_MISSING", "Current density is specified without electrode area.", "Specify geometric or active surface area.", ("current_density", "geometric_area", "surface_area"))
    if (specified("gas_flow_rate") or specified("liquid_flow_rate")) and not any(
        specified(name) for name in ("chamber_volume", "channel_width", "channel_height", "channel_depth", "channel_length")
    ):
        add("engineering_critic", "fail", "high", "FLOW_GEOMETRY_MISSING", "Flow rate is specified without channel or chamber dimensions.", "Specify chamber volume or complete channel dimensions.", ("gas_flow_rate", "liquid_flow_rate"))
    if specified("pressure") and not specified("reactor_pressure_rating"):
        add("safety_capability_critic", "fail", "critical", "PRESSURE_RATING_MISSING", "Pressure is specified without a compatible reactor pressure rating.", "Provide the reactor rating and verify compatibility.", ("pressure", "reactor_pressure_rating"))
    if any(str(ref).startswith("CTX:") for ref in card.get("evidence_for") or []):
        refs = [str(ref) for ref in card.get("evidence_for") or [] if str(ref).startswith("CTX:")]
        add("evidence_critic", "warning", "high", "CONTEXT_ONLY_SUPPORT", "A proposed positive support reference is context-only evidence.", "Replace it with same-paper primary support or keep it non-supporting.", refs=refs)
    objective_names = {item.get("name") for item in card.get("objectives") or [] if isinstance(item, dict)}
    controls = " ".join(card.get("required_controls") or []).casefold()
    if objective_names & {"faradaic_efficiency_nh3", "nh3_production_rate", "nh3_concentration"}:
        if "blank" not in controls or "quant" not in controls:
            add("evidence_critic", "fail", "critical", "NH3_CONTROLS_MISSING", "An ammonia performance target lacks explicit quantification and blank controls.", "List quantification, contamination, and blank controls.")
    if problem is not None:
        unavailable = {
            item["capability_name"] for item in problem.get("laboratory_capabilities") or []
            if item.get("availability") == "unavailable"
        }
        requested = set(card.get("required_controls") or []) | set(card.get("required_measurements") or [])
        violated = sorted(unavailable & requested)
        if violated:
            add("safety_capability_critic", "fail", "high", "LAB_CAPABILITY_VIOLATION", f"Unavailable laboratory capabilities were requested: {', '.join(violated)}.", "Change the design or explicitly configure the missing capabilities.")
        definitions = {
            item.get("name"): item for item in problem.get("decision_variables") or [] if isinstance(item, dict)
        }
        outside: list[str] = []
        for name, item in assignments.items():
            bounds = (definitions.get(name) or {}).get("numeric_bounds")
            value = item.get("value")
            if not isinstance(bounds, dict) or not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            minimum, maximum = bounds.get("minimum"), bounds.get("maximum")
            if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
                outside.append(name)
        if outside:
            add("engineering_critic", "fail", "high", "INCOMPATIBLE_VARIABLE_RANGE", f"Configured values fall outside the design-problem ranges: {', '.join(sorted(outside))}.", "Reconcile card values with configured variable ranges.", sorted(outside))
    for job in simulation_jobs:
        simulation_type = job.get("simulation_type")
        inputs = {item.get("name"): item for item in job.get("required_inputs") or [] if isinstance(item, dict)}
        if simulation_type == "COMSOL" and (not job.get("boundary_conditions") or not any(name in inputs for name in ("geometry", "mesh_geometry"))):
            add("engineering_critic", "fail", "high", "COMSOL_INPUTS_INCOMPLETE", "A COMSOL job lacks geometry or boundary conditions.", "Supply geometry and boundary conditions before routing.")
        if simulation_type == "DFT" and inputs.get("chemical_structure", {}).get("status") != "specified":
            add("chemistry_critic", "fail", "high", "DFT_STRUCTURE_MISSING", "A DFT job lacks a chemical structure.", "Supply a versioned chemical structure.")
        if simulation_type == "MD" and inputs.get("force_field_strategy", {}).get("status") != "specified":
            add("chemistry_critic", "fail", "high", "MD_FORCE_FIELD_MISSING", "An MD job lacks a force-field strategy.", "Supply and review a force-field strategy.")
    if not results:
        add("evidence_critic", "pass", "info", "DETERMINISTIC_CHECKS_PASS", "No configured deterministic critic rule fired.", "No action required.")
    return results


def make_simulation_job(
    design_id: str,
    simulation_type: str,
    simulation_target: str,
    scientific_question: str,
    *,
    required_inputs: Sequence[Mapping[str, Any]],
    boundary_conditions: Sequence[Mapping[str, Any]],
    expected_outputs: Sequence[str],
    fidelity: str = "screening",
    estimated_cost: str = "unknown",
    code_commit: str = "0" * 40,
) -> dict[str, Any]:
    if simulation_type not in SIMULATION_TYPES:
        raise ValueError(f"unsupported simulation type: {simulation_type}")
    completeness = "complete" if all(item.get("status") in {"specified", "not_applicable"} for item in required_inputs) else "incomplete"
    job_id = stable_id(
        "SIM18", SIMULATION_JOB_SCHEMA_VERSION, design_id, simulation_type, simulation_target, scientific_question
    )
    return {
        "schema_version": SIMULATION_JOB_SCHEMA_VERSION,
        "simulation_job_id": job_id,
        "design_id": design_id,
        "simulation_type": simulation_type,
        "simulation_target": simulation_target,
        "scientific_question": scientific_question,
        "required_inputs": [dict(item) for item in required_inputs],
        "input_completeness": completeness,
        "boundary_conditions": [dict(item) for item in boundary_conditions],
        "expected_outputs": list(expected_outputs),
        "fidelity": fidelity,
        "estimated_cost": estimated_cost,
        "dependency_jobs": [],
        "status": "draft" if completeness == "complete" else "blocked",
        "human_gate_required": simulation_type in {"COMSOL", "DFT", "MD"},
        "provenance": {
            "generated_by": "deterministic_compiler",
            "generation_method": "v018_a2a_simulation_router",
            "source_refs": ["enh3bench/design_compiler_v018.py"],
            "code_commit": code_commit,
            "parent_ids": [design_id],
        },
    }


def route_simulation(design_id: str, scientific_question: str, target: str, *, code_commit: str = "0" * 40) -> dict[str, Any]:
    comsol = {"fluid_flow", "species_transport", "current_distribution", "pressure_drop", "residence_time", "concentration_uniformity", "gas_liquid_transport", "thermal_distribution"}
    dft = {"adsorption", "activation_barriers", "surface_intermediates", "electronic_structure", "interfacial_reaction_energetics"}
    md = {"solvation_structure", "ion_pairing", "proton_donor_environment", "electrolyte_transport", "interfacial_organization", "SEI_precursor_environment"}
    simulation_type = "COMSOL" if target in comsol else "DFT" if target in dft else "MD" if target in md else "human_required"
    required_names = {
        "COMSOL": ("geometry", "material_properties"),
        "DFT": ("chemical_structure", "calculation_strategy"),
        "MD": ("chemical_structure", "force_field_strategy"),
        "human_required": ("routing_decision",),
    }[simulation_type]
    required_inputs = [
        {"name": name, "status": "missing", "value": None, "unit": None, "source_ref": None}
        for name in required_names
    ]
    boundaries = [] if simulation_type != "human_required" else [
        {"name": "routing_scope", "status": "unknown", "value": None, "unit": None}
    ]
    return make_simulation_job(
        design_id, simulation_type, target if simulation_type != "human_required" else "not_applicable",
        scientific_question, required_inputs=required_inputs, boundary_conditions=boundaries,
        expected_outputs=[target], estimated_cost="high" if simulation_type in {"COMSOL", "DFT", "MD"} else "unknown",
        code_commit=code_commit,
    )


def make_fixture_card(*, code_commit: str = "0" * 40) -> dict[str, Any]:
    """Build a deliberately non-scientific card for contract and critic tests."""

    hypothesis = "Synthetic fixture hypothesis for schema validation only; it is not a scientific recommendation."
    design_id = stable_id("DES18", DESIGN_CARD_SCHEMA_VERSION, "integrated_system", "LiNRR", hypothesis)
    assignments = []
    for domain, name, data_type, unit, value, status, required in (
        ("electrolyte", "water_content_ppm", "number", "ppm", None, "unknown", True),
        ("electrolyte", "proton_donor_identity", "string", "1", "FIXTURE_DONOR", "assumed", True),
        ("electrolyte", "proton_donor_concentration", "number", "mol L^-1", None, "unknown", True),
        ("electrochemical_operation", "current_density", "number", "mA cm^-2", 1.0, "assumed", True),
    ):
        assignments.append({
            "variable_id": stable_id("DV18", DESIGN_PROBLEM_SCHEMA_VERSION, domain, name),
            "name": name,
            "value": value,
            "unit": unit,
            "source_status": status,
            "required": required,
            "evidence_refs": ["FIXTURE:SYNTHETIC"] if status == "assumed" else [],
            "uncertainty": unknown_uncertainty("Synthetic fixture value; not scientific."),
        })
    objective = _objective(*OBJECTIVE_DEFINITIONS[0])
    card = {
        "schema_version": DESIGN_CARD_SCHEMA_VERSION,
        "design_id": design_id,
        "design_version": "0.1",
        "artifact_label": "NON_SCIENTIFIC_FIXTURE",
        "design_class": "integrated_system",
        "reaction_family": "LiNRR",
        "hypothesis": hypothesis,
        "falsification_criteria": ["Synthetic fixture criterion: reject if the configured boolean fixture check is false."],
        "evidence_for": ["FIXTURE:SYNTHETIC"],
        "evidence_against": [],
        "decision_variables": assignments,
        "fixed_conditions": [],
        "objectives": [{
            "objective_id": objective["objective_id"],
            "name": objective["name"],
            "direction": objective["direction"],
            "unit": objective["unit"],
            "target": None,
            "acceptable_threshold": None,
            "weight": None,
            "hard_or_soft": "soft",
        }],
        "constraints": [{
            "constraint_id": stable_id("CON18", DESIGN_CARD_SCHEMA_VERSION, "fixture_only"),
            "constraint_type": "hard",
            "status": "pass",
            "details": "The artifact is explicitly labelled NON_SCIENTIFIC_FIXTURE.",
        }],
        "required_controls": ["synthetic quantification control", "synthetic blank control"],
        "required_measurements": ["synthetic fixture measurement"],
        "simulation_plan": [],
        "predictions": [],
        "uncertainties": [{
            "subject": "all fixture values",
            "description": "Values are synthetic and have no scientific meaning.",
            "level": "unknown",
            "resolution": "Never use fixture values as a recommendation.",
        }],
        "domain_of_applicability": ["schema and deterministic rule tests only"],
        "laboratory_readiness": {"status": "incomplete", "missing_items": ["all real laboratory inputs"]},
        "simulation_readiness": {"status": "incomplete", "missing_items": ["all real simulation inputs"]},
        "manufacturing_readiness": {"status": "incomplete", "missing_items": ["all real manufacturing inputs"]},
        "human_gates": [human_gate(gate_type) for gate_type in GATE_TYPES],
        "provenance": {
            "generated_by": "synthetic_fixture",
            "generation_method": "v018_a2a_non_scientific_fixture",
            "source_refs": ["tests/fixtures/v018_design_compiler/README.md"],
            "code_commit": code_commit,
            "parent_ids": [],
        },
    }
    return with_content_hash(card)
