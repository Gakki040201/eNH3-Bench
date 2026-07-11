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
        "liquid_nitrate_nitrite_IC_available": False,
        "gas_phase_NOx_quantification_available": False,
        "feed_gas_impurity_testing_available": False,
        "gas_phase_NH3_capture_available": False,
        "liquid_NH4_quantification_available": False,
        "H2_quantification_available": False,
        "water_content_quantification_available": False,
        "image_recording_available": False,
        "electrical_resistance_measurement_available": False,
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
    "NOx/nitrate/nitrite screening": ("can_do_NOx_screening", "liquid_nitrate_nitrite_IC_available"),
    "background NH3 control": ("can_do_background_NH3_control", "liquid_NH4_quantification_available"),
    "electrolyte blank": ("can_do_electrolyte_blank",),
    "H2-off control": ("can_do_H2_off_control", "H2_available"),
    "HOR-off control": ("can_do_HOR_off_control", "can_do_HOR_coupling"),
    "gas/liquid product accounting": ("gas_phase_NH3_capture_available", "liquid_NH4_quantification_available"),
    "wetting/flooding diagnosis": ("can_do_flow_cell",),
    "voltage/current/runtime reporting": ("potentiostat_available", "can_record_full_cell_voltage"),
    "solvent inventory/recycle reporting": ("can_measure_water_content",),
    "primary body text pairing": (),
    "electrolyte resistance before/after": ("electrical_resistance_measurement_available",),
    "SSC/PtAuSSC before-after photos": ("image_recording_available",),
    "three water-content measurements": ("water_content_quantification_available", "Karl_Fischer_available", "Karl_Fischer_SOP"),
    "HCl trap accounting": ("gas_phase_NH3_capture_available", "liquid_NH4_quantification_available"),
    "SSC soak solution accounting": ("liquid_NH4_quantification_available",),
    "gas-line blank": ("gas_liquid_line_SOP",),
    "liquid-line blank": ("gas_liquid_line_SOP",),
}

MEASUREMENT_CAPABILITY_KEYS: dict[str, tuple[tuple[str, ...], ...]] = {
    "FE": (
        ("potentiostat_available", "liquid_NH4_quantification_available"),
        ("potentiostat_available", "gas_phase_NH3_capture_available"),
    ),
    "NH3_yield": (("liquid_NH4_quantification_available",), ("gas_phase_NH3_capture_available",)),
    "current_density": (("potentiostat_available",),),
    "OCV": (("potentiostat_available",),),
    "full_cell_voltage": (("can_record_full_cell_voltage",),),
    "anode_potential": (("can_record_anode_cathode_potential",),),
    "cathode_potential": (("can_record_anode_cathode_potential",),),
    "runtime": (("potentiostat_available",),),
    "EIS": (("EIS_available",),),
    "water_content": (("water_content_quantification_available",), ("Karl_Fischer_available",)),
    "water_content_before": (("water_content_quantification_available",), ("Karl_Fischer_available",)),
    "water_content_mid": (("water_content_quantification_available",), ("Karl_Fischer_available",)),
    "water_content_after": (("water_content_quantification_available",), ("Karl_Fischer_available",)),
    "nitrate": (("liquid_nitrate_nitrite_IC_available",),),
    "nitrite": (("liquid_nitrate_nitrite_IC_available",),),
    "NOx": (("gas_phase_NOx_quantification_available",),),
    "gas_phase_NOx": (("gas_phase_NOx_quantification_available",),),
    "feed_gas_impurity": (("feed_gas_impurity_testing_available",),),
    "H2": (("H2_quantification_available",),),
    "gas_phase_NH3": (("gas_phase_NH3_capture_available",),),
    "liquid_NH4": (("liquid_NH4_quantification_available",),),
    "IC_NH4": (("liquid_NH4_quantification_available",),),
    "HCl_trap_NH4": (("gas_phase_NH3_capture_available", "liquid_NH4_quantification_available"),),
    "SSC_soak_solution_NH4": (("liquid_NH4_quantification_available",),),
    "product_state_split": (("gas_phase_NH3_capture_available", "liquid_NH4_quantification_available"),),
    "photo_before_after": (("image_recording_available",),),
    "SSC_photo_before": (("image_recording_available",),),
    "SSC_photo_after": (("image_recording_available",),),
    "PtAuSSC_photo_before": (("image_recording_available",),),
    "PtAuSSC_photo_after": (("image_recording_available",),),
    "electrolyte_resistance_before": (("electrical_resistance_measurement_available",),),
    "electrolyte_resistance_after": (("electrical_resistance_measurement_available",),),
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
            "liquid_nitrate_nitrite_IC_available": True,
            "gas_phase_NOx_quantification_available": False,
            "feed_gas_impurity_testing_available": False,
            "gas_phase_NH3_capture_available": True,
            "liquid_NH4_quantification_available": True,
            "H2_quantification_available": False,
            "water_content_quantification_available": True,
            "image_recording_available": True,
            "electrical_resistance_measurement_available": True,
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
    if not isinstance(data, dict):
        return {}
    migrated, warnings = migrate_lab_profile(data)
    if warnings:
        migrated["migration_warnings"] = warnings
    return migrated


def migrate_lab_profile(profile: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Add split analytics fields to a legacy profile without granting ambiguous capabilities."""

    migrated = json.loads(json.dumps(profile))
    warnings: list[str] = []
    analytics = migrated.setdefault("analytics", {})
    electrolyte = migrated.get("electrolyte_chemistry") or {}

    if "liquid_nitrate_nitrite_IC_available" not in analytics:
        if "nitrate_nitrite_quantification_available" in analytics:
            analytics["liquid_nitrate_nitrite_IC_available"] = bool(analytics.get("nitrate_nitrite_quantification_available"))
            warnings.append(
                "legacy analytics.nitrate_nitrite_quantification_available migrated to liquid_nitrate_nitrite_IC_available"
            )
        else:
            analytics["liquid_nitrate_nitrite_IC_available"] = False
    if "NOx_quantification_available" in analytics:
        warnings.append(
            "legacy analytics.NOx_quantification_available is ambiguous and was not used to enable gas-phase NOx quantification"
        )
    analytics.setdefault("gas_phase_NOx_quantification_available", False)
    analytics.setdefault("feed_gas_impurity_testing_available", False)
    if "gas_phase_NH3_capture_available" not in analytics:
        analytics["gas_phase_NH3_capture_available"] = bool(analytics.get("ammonia_gas_capture_available", False))
        if "ammonia_gas_capture_available" in analytics:
            warnings.append("legacy analytics.ammonia_gas_capture_available migrated to gas_phase_NH3_capture_available")
    analytics.setdefault("liquid_NH4_quantification_available", False)
    analytics.setdefault("H2_quantification_available", False)
    analytics.setdefault(
        "water_content_quantification_available",
        bool(electrolyte.get("can_measure_water_content") or electrolyte.get("Karl_Fischer_available")),
    )
    analytics.setdefault("image_recording_available", False)
    analytics.setdefault("electrical_resistance_measurement_available", False)
    return migrated, _dedupe(warnings)


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
        "migration_warnings": profile.get("migration_warnings") or [],
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
    if found is None and capability_key == "liquid_nitrate_nitrite_IC_available":
        found = _find_key(profile, "nitrate_nitrite_quantification_available")
    if found is None and capability_key == "gas_phase_NH3_capture_available":
        found = _find_key(profile, "ammonia_gas_capture_available")
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


def missing_capabilities_for_measurements(profile: dict[str, Any], measurements: list[str]) -> list[str]:
    """Return the smallest missing capability set for each requested measurement."""

    missing: list[str] = []
    for measurement in measurements:
        alternatives = MEASUREMENT_CAPABILITY_KEYS.get(str(measurement), ())
        if not alternatives or any(all(capability_available(profile, key) for key in option) for option in alternatives):
            continue
        option_missing = min(
            ([key for key in option if not capability_available(profile, key)] for option in alternatives),
            key=lambda values: (len(values), values),
        )
        for key in option_missing:
            if key not in missing:
                missing.append(key)
    return missing


def feasible_measurements(profile: dict[str, Any], measurements: list[str]) -> list[str]:
    """Return measurements with at least one fully available capability path."""

    feasible: list[str] = []
    for measurement in measurements:
        alternatives = MEASUREMENT_CAPABILITY_KEYS.get(str(measurement), ())
        if not alternatives or any(all(capability_available(profile, key) for key in option) for option in alternatives):
            feasible.append(str(measurement))
    return feasible


def infeasible_measurements(profile: dict[str, Any], measurements: list[str]) -> list[str]:
    """Return measurements for which no capability path is available."""

    feasible = set(feasible_measurements(profile, measurements))
    return [str(measurement) for measurement in measurements if str(measurement) not in feasible]


def measurement_feasibility_status(
    profile: dict[str, Any], mandatory: list[str], optional: list[str] | None = None
) -> str:
    """Return feasible, partial, or infeasible for a measurement plan."""

    if infeasible_measurements(profile, mandatory):
        return "infeasible"
    if infeasible_measurements(profile, optional or []):
        return "partial"
    return "feasible"


def _find_key(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for item in value.values():
            found = _find_key(item, key)
            if found is not None:
                return found
    return None


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item).strip()))


def _yaml_module() -> Any | None:
    try:
        import yaml  # type: ignore[import-not-found]
    except ImportError:
        return None
    return yaml


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
