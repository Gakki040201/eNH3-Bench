"""Lab capability profiles for closed-loop eNH3 experiment planning."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


LAB_PROFILE_VERSION = "0.1"

TOP_LEVEL_FIELDS = (
    "profile_id",
    "institution",
    "group_name",
    "contact_optional",
    "profile_version",
    "created_at_utc",
    "updated_at_utc",
)

SECTION_DEFAULTS: dict[str, dict[str, Any]] = {
    "reactor_capabilities": {
        "available_reactors": [],
        "can_do_batch_cell": True,
        "can_do_flow_cell": False,
        "can_do_GDE": False,
        "can_do_SSC": False,
        "can_do_HOR_coupling": False,
        "max_active_area_cm2": None,
        "max_runtime_hours": None,
        "pressure_control_available": False,
        "gas_flow_control_available": False,
        "liquid_flow_control_available": False,
    },
    "electrochemistry": {
        "potentiostat_available": False,
        "can_record_full_cell_voltage": False,
        "can_record_anode_cathode_potential": False,
        "EIS_available": False,
        "CV_available": False,
        "chronoamperometry_available": False,
        "temperature_control_available": False,
    },
    "materials": {
        "cathodes_available": [],
        "anodes_available": [],
        "catalysts_available": [],
        "membranes_or_separators_available": [],
        "GDE_materials_available": [],
    },
    "electrolyte_chemistry": {
        "solvents_available": [],
        "lithium_salts_available": [],
        "proton_donors_available": [],
        "additives_available": [],
        "can_measure_water_content": False,
        "Karl_Fischer_available": False,
        "glovebox_available": False,
        "drying_capability": False,
    },
    "gases": {
        "N2_available": False,
        "Ar_available": False,
        "H2_available": False,
        "isotopic_15N2_available": False,
        "gas_purification_available": False,
        "NOx_scrubber_available": False,
        "gas_impurity_testing_available": False,
    },
    "analytics": {
        "ion_chromatography_available": False,
        "UV_vis_available": False,
        "NMR_available": False,
        "ammonia_gas_capture_available": False,
        "liquid_NH4_quantification_available": False,
        "nitrate_nitrite_quantification_available": False,
        "NOx_quantification_available": False,
        "H2_quantification_available": False,
        "product_state_accounting_available": False,
    },
    "controls": {
        "can_do_Ar_blank": False,
        "can_do_N2_free_blank": False,
        "can_do_15N_control": False,
        "can_do_NOx_screening": False,
        "can_do_background_NH3_control": False,
        "can_do_H2_off_control": False,
        "can_do_HOR_off_control": False,
        "can_do_electrolyte_blank": False,
    },
    "sop_capabilities": {
        "has_Li_NRR_SOP": False,
        "glovebox_transfer_SOP": False,
        "Li_salt_drying_SOP": False,
        "DG_drying_SOP": False,
        "reference_electrode_SOP": False,
        "gas_liquid_line_SOP": False,
        "SSC_preparation_SOP": False,
        "PtAuSSC_preparation_SOP": False,
        "Karl_Fischer_SOP": False,
        "IC_sampling_SOP": False,
        "post_experiment_report_SOP": False,
        "failure_diagnosis_SOP": False,
    },
    "constraints": {
        "max_parallel_experiments": None,
        "max_conditions_per_week": None,
        "budget_level": "unknown",
        "safety_constraints": [],
        "unavailable_operations": [],
        "notes": "",
    },
}

CONTROL_CAPABILITY_KEYS = {
    "15N2 isotope validation": ("can_do_15N_control", "isotopic_15N2_available"),
    "Ar blank": ("can_do_Ar_blank", "Ar_available"),
    "N2-free blank": ("can_do_N2_free_blank", "Ar_available"),
    "NOx/nitrate/nitrite screening": ("can_do_NOx_screening", "nitrate_nitrite_quantification_available"),
    "background NH3 control": ("can_do_background_NH3_control", "liquid_NH4_quantification_available"),
    "electrolyte blank": ("can_do_electrolyte_blank",),
    "H2-off control": ("can_do_H2_off_control", "H2_available"),
    "HOR-off control": ("can_do_HOR_off_control", "can_do_HOR_coupling"),
    "gas/liquid product accounting": ("product_state_accounting_available",),
    "wetting/flooding diagnosis": ("can_do_flow_cell",),
    "voltage/current/runtime reporting": ("potentiostat_available", "can_record_full_cell_voltage"),
    "solvent inventory/recycle reporting": ("can_measure_water_content",),
    "primary body text pairing": (),
    "electrolyte resistance before/after": ("EIS_available",),
    "SSC/PtAuSSC before-after photos": ("SSC_preparation_SOP", "PtAuSSC_preparation_SOP"),
    "three water-content measurements": ("can_measure_water_content", "Karl_Fischer_available", "Karl_Fischer_SOP"),
    "HCl trap accounting": ("ammonia_gas_capture_available", "liquid_NH4_quantification_available"),
    "SSC soak solution accounting": ("liquid_NH4_quantification_available",),
    "gas-line blank": ("gas_liquid_line_SOP",),
    "liquid-line blank": ("gas_liquid_line_SOP",),
}


def default_ustc_linnr_profile(profile_template: str = "conservative") -> dict[str, Any]:
    """Return an editable USTC Li-NRR profile template."""

    now = _utc_now()
    profile: dict[str, Any] = {
        "profile_id": "ustc_linnr_profile",
        "institution": "USTC",
        "group_name": "Li-NRR group",
        "contact_optional": "",
        "profile_version": LAB_PROFILE_VERSION,
        "created_at_utc": now,
        "updated_at_utc": now,
    }
    for section, defaults in SECTION_DEFAULTS.items():
        profile[section] = json.loads(json.dumps(defaults))
    profile["allowed_reaction_families"] = ["LiNRR"]
    profile["reaction_family_demonstrations"] = {"LiNRR": True}
    if str(profile_template or "").casefold() in {"ustc-linnr-realistic", "ustc_linnr_realistic", "realistic"}:
        _apply_ustc_linnr_realistic_defaults(profile)
    return profile


def ustc_linnr_realistic_profile() -> dict[str, Any]:
    """Return the realistic USTC Li-NRR SOP-grounded profile template."""

    return default_ustc_linnr_profile(profile_template="ustc-linnr-realistic")


def _apply_ustc_linnr_realistic_defaults(profile: dict[str, Any]) -> None:
    profile["reactor_capabilities"].update(
        {
            "available_reactors": ["Li-NRR flow cell", "SSC/PtAuSSC cell"],
            "can_do_flow_cell": True,
            "can_do_SSC": True,
            "can_do_HOR_coupling": True,
            "gas_flow_control_available": True,
            "liquid_flow_control_available": True,
        }
    )
    profile["electrochemistry"].update(
        {
            "potentiostat_available": True,
            "can_record_full_cell_voltage": True,
            "EIS_available": True,
            "chronoamperometry_available": True,
        }
    )
    profile["electrolyte_chemistry"].update(
        {
            "solvents_available": ["DG", "THF"],
            "lithium_salts_available": ["Li salt editable"],
            "proton_donors_available": ["editable"],
            "can_measure_water_content": True,
            "Karl_Fischer_available": True,
            "glovebox_available": True,
            "drying_capability": True,
        }
    )
    profile["gases"].update(
        {
            "N2_available": True,
            "Ar_available": True,
            "H2_available": True,
            "isotopic_15N2_available": False,
        }
    )
    profile["analytics"].update(
        {
            "ion_chromatography_available": True,
            "ammonia_gas_capture_available": True,
            "liquid_NH4_quantification_available": True,
            "nitrate_nitrite_quantification_available": True,
            "NOx_quantification_available": True,
            "product_state_accounting_available": True,
        }
    )
    profile["controls"].update(
        {
            "can_do_Ar_blank": True,
            "can_do_N2_free_blank": True,
            "can_do_15N_control": False,
            "can_do_NOx_screening": True,
            "can_do_background_NH3_control": True,
            "can_do_H2_off_control": True,
            "can_do_HOR_off_control": True,
            "can_do_electrolyte_blank": True,
        }
    )
    profile["sop_capabilities"].update({key: True for key in profile["sop_capabilities"]})
    profile["constraints"].update(
        {
            "budget_level": "unknown",
            "safety_constraints": ["Route cards are planning artifacts; local Li handling, gas handling, and electrolyte SOPs govern execution."],
            "notes": "Editable realistic USTC Li-NRR demonstration template; 15N2 remains false until explicitly available.",
        }
    )


def load_lab_profile(path: str | Path) -> dict[str, Any]:
    """Load a JSON or YAML lab profile."""

    input_path = Path(path)
    text = input_path.read_text(encoding="utf-8")
    yaml_module = _yaml_module()
    if input_path.suffix.lower() in {".yaml", ".yml"} and yaml_module is not None:
        data = yaml_module.safe_load(text)
    else:
        data = json.loads(text)
    return data if isinstance(data, dict) else {}


def save_lab_profile(profile: dict[str, Any], path: str | Path) -> None:
    """Write a JSON or YAML lab profile, falling back to JSON when PyYAML is absent."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    profile = dict(profile)
    profile["updated_at_utc"] = profile.get("updated_at_utc") or _utc_now()
    yaml_module = _yaml_module()
    if output_path.suffix.lower() in {".yaml", ".yml"} and yaml_module is not None:
        text = yaml_module.safe_dump(profile, sort_keys=False, allow_unicode=True)
    else:
        text = json.dumps(profile, ensure_ascii=True, indent=2, sort_keys=True)
    output_path.write_text(text, encoding="utf-8", newline="\n")


def validate_lab_profile(profile: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate required profile fields and section shapes."""

    errors: list[str] = []
    if not isinstance(profile, dict):
        return False, ["profile must be a dict"]
    for field in TOP_LEVEL_FIELDS:
        if field not in profile:
            errors.append(f"missing top-level field: {field}")
    if str(profile.get("profile_version") or "") != LAB_PROFILE_VERSION:
        errors.append(f"profile_version must be {LAB_PROFILE_VERSION}")
    for section, defaults in SECTION_DEFAULTS.items():
        value = profile.get(section)
        if not isinstance(value, dict):
            errors.append(f"missing or invalid section: {section}")
            continue
        for key, default in defaults.items():
            if key not in value:
                errors.append(f"missing {section}.{key}")
                continue
            if isinstance(default, bool) and not isinstance(value.get(key), bool):
                errors.append(f"{section}.{key} must be bool")
            elif isinstance(default, list) and not isinstance(value.get(key), list):
                errors.append(f"{section}.{key} must be list")
    budget = str((profile.get("constraints") or {}).get("budget_level") or "")
    if budget not in {"low", "medium", "high", "unknown"}:
        errors.append("constraints.budget_level must be low|medium|high|unknown")
    return not errors, errors


def summarize_lab_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Summarize route-relevant capabilities."""

    controls = list(CONTROL_CAPABILITY_KEYS)
    return {
        "profile_id": profile.get("profile_id") or "",
        "profile_version": profile.get("profile_version") or "",
        "available_reactors": (profile.get("reactor_capabilities") or {}).get("available_reactors") or [],
        "budget_level": (profile.get("constraints") or {}).get("budget_level") or "unknown",
        "feasible_controls": feasible_controls(profile, controls),
        "infeasible_controls": infeasible_controls(profile, controls),
        "can_do_flow_cell": capability_available(profile, "can_do_flow_cell"),
        "can_do_HOR_coupling": capability_available(profile, "can_do_HOR_coupling"),
        "isotopic_15N2_available": capability_available(profile, "isotopic_15N2_available"),
        "product_state_accounting_available": capability_available(profile, "product_state_accounting_available"),
        "has_Li_NRR_SOP": capability_available(profile, "has_Li_NRR_SOP"),
        "Karl_Fischer_SOP": capability_available(profile, "Karl_Fischer_SOP"),
        "IC_sampling_SOP": capability_available(profile, "IC_sampling_SOP"),
    }


def capability_available(profile: dict[str, Any], capability_key: str) -> bool:
    """Return True when a capability key is present and true anywhere in the profile."""

    found = _find_key(profile, capability_key)
    if found is None:
        return False
    if isinstance(found, bool):
        return found
    if isinstance(found, (int, float)):
        return found > 0
    if isinstance(found, (list, tuple, set, dict)):
        return bool(found)
    return str(found or "").strip().casefold() in {"true", "yes", "available", "1"}


def missing_capabilities_for_controls(profile: dict[str, Any], controls: list[str]) -> list[str]:
    """Return capability keys missing for the requested controls."""

    missing: list[str] = []
    for control in controls:
        keys = CONTROL_CAPABILITY_KEYS.get(str(control), ())
        for key in keys:
            if not capability_available(profile, key) and key not in missing:
                missing.append(key)
    return missing


def feasible_controls(profile: dict[str, Any], controls: list[str]) -> list[str]:
    """Return controls whose mapped capabilities are available."""

    feasible: list[str] = []
    for control in controls:
        keys = CONTROL_CAPABILITY_KEYS.get(str(control), ())
        if not keys or all(capability_available(profile, key) for key in keys):
            feasible.append(str(control))
    return feasible


def infeasible_controls(profile: dict[str, Any], controls: list[str]) -> list[str]:
    """Return controls whose mapped capabilities are unavailable."""

    feasible = set(feasible_controls(profile, controls))
    return [str(control) for control in controls if str(control) not in feasible]


def _find_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for item in value.values():
            found = _find_key(item, key)
            if found is not None:
                return found
    return None


def _yaml_module() -> Any | None:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        return None
    return yaml


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
