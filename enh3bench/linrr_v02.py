"""Unit-safe, source-semantic LiNRR Training Dataset v0.2 helpers.

This is an independent profile.  It does not alter the v0/v0.1 schemas or
their historical runtime artifacts.
"""

from __future__ import annotations

import hashlib
import math
import re
from copy import deepcopy
from typing import Any


SCHEMA_VERSION = "linrr_experiment_record_v0_2"
AUDITED_NUMERIC_FIELDS = [
    "temperature_C", "total_charge_C", "duration_h", "current_density_mA_cm2",
    "pressure_bar", "gas_flow_sccm", "liquid_flow_mL_min", "electrode_area_cm2",
    "lithium_salt_concentration_mol_L", "proton_donor_concentration_mol_L",
    "proton_donor_concentration_vol_percent", "proton_donor_concentration_wt_percent",
    "proton_donor_concentration_ppm", "water_content_mol_L", "water_content_vol_percent",
    "water_content_wt_percent", "water_content_ppm",
]

R0_CATEGORICAL = ["lithium_salt", "solvent", "proton_donor", "electrode_material", "cell_type"]
R0_NUMERIC = [
    "lithium_salt_concentration_mol_L", "proton_donor_concentration_mol_L",
    "current_density_mA_cm2", "total_charge_C", "duration_h", "temperature_C",
    "pressure_bar", "gas_flow_sccm", "liquid_flow_mL_min", "electrode_area_cm2",
]
R1_NUMERIC = [*R0_NUMERIC, "proton_donor_concentration_vol_percent"]
RI_CATEGORICAL = [
    *R0_CATEGORICAL, "interface_sei_characterization_present", "interface_lif_reported",
    "interface_n_containing_sei_reported", "electrolyte_architecture",
]

# Deterministic target-level adjudications from exact v0.1 anchors.  The
# historical candidates remain in all_candidate_records; only training use is
# corrected.  These are intentionally record-specific rather than broad limits.
TARGET_EXCLUSIONS: dict[str, tuple[str, str]] = {
    "REC_1387ea661888f196": ("CITED_PRIOR_STUDY", "The target sentence says 'have first reported 18% FE' and cites prior work; it is not a current-paper experiment."),
    "REC_1754eb59f869c0b4": ("UNCERTAINTY_TERM", "0.67% is the uncertainty in 3.94 ± 0.67% FE, not a distinct FE target."),
    "REC_3a54aa00f1eeacf1": ("UNCERTAINTY_TERM", "1% is the uncertainty in 61 ± 1% FE, not a distinct FE target."),
    "REC_3aa0057919f4511f": ("UNCERTAINTY_TERM", "5.1% is the uncertainty in 65.8 ± 5.1% FE, not a distinct FE target."),
    "REC_3b598368e1e6a362": ("WRONG_TARGET_ANALYTE", "The source explicitly assigns 23% faradaic efficiency to H2 production, not NH3."),
    "REC_50061c3613a77d71": ("UNCERTAINTY_TERM", "1% is the uncertainty in 61 ± 1% ammonia FE, not a distinct FE target."),
    "REC_69c6b323aef4e6aa": ("INVALIDATED_N2_SIGNAL", "The <1% value is an argon control and cannot be a positive N2-to-NH3 training target."),
    "REC_7495c9299f925607": ("UNCERTAINTY_TERM", "3% is the uncertainty in the author result 72 ± 3%; the nearby 700 C is passed charge."),
    "REC_805a0c932e54c01c": ("UNCERTAINTY_TERM", "2.5% is the uncertainty in 73.6 ± 2.5% FE, not a distinct FE target."),
    "REC_841fcde66a15c34f": ("CITED_PRIOR_STUDY", "The source attributes 71% FE to Li et al. in a literature discussion."),
    "REC_b8a3f0fcbb4dab93": ("CITED_PRIOR_STUDY", "The source attributes 300 h and 64% FE to a recent prior study before introducing the current work."),
    "REC_d281a0288e625dc1": ("UNCERTAINTY_TERM", "3% is the uncertainty in 61.7 ± 3% FE, not a distinct FE target."),
}

DUPLICATE_EXCLUSIONS = {
    "REC_df403f4b38138aea": ("REC_bbb0980b4961c515", "Main-text summary and SI experiment repeat the same solid-electrolyte FE≈10% experiment; retain the more specific 18 h SI anchor."),
}


def stable_v02_id(v01_record_id: str) -> str:
    return "REC02_" + hashlib.sha256(v01_record_id.encode("utf-8")).hexdigest()[:16]


def parse_charge_temperature(text: str) -> dict[str, Any]:
    """Parse only context-safe charge and temperature expressions.

    A bare number followed by C is charge.  Celsius without a degree marker is
    accepted only when a temperature/heating keyword directly establishes its
    semantics.
    """
    clean = " ".join(str(text or "").replace("−", "-").split())
    temp_patterns = [
        r"(?P<value>-?\d+(?:\.\d+)?)\s*(?:°\s*C|℃|deg(?:ree)?s?\s*C)\b",
        r"(?:temperature(?:\s+of|\s*=|\s+was|\s+at)?|heated\s+to|heating\s+at)\s*[:=]?\s*(?P<value>-?\d+(?:\.\d+)?)\s*C\b",
    ]
    charge_patterns = [
        r"(?:after\s+passing|passing|passed|total\s+passed|total\s+charge(?:\s+passed)?|charge(?:\s+of|\s*=|\s+was)?)\s*(?:a\s+charge\s+of\s*)?(?P<value>\d+(?:\.\d+)?)\s*C\b",
    ]
    temperature = None
    temperature_raw = None
    for pattern in temp_patterns:
        match = re.search(pattern, clean, re.I)
        if match:
            temperature = float(match.group("value")); temperature_raw = match.group(0); break
    charge_matches: list[tuple[int, float, str]] = []
    for priority, pattern in enumerate(charge_patterns):
        for match in re.finditer(pattern, clean, re.I):
            prefix = clean[max(0, match.start() - 2):match.start()]
            if "°" in prefix or re.search(r"(?:temperature|heated|heating)\s*$", clean[max(0, match.start()-30):match.start()], re.I):
                continue
            charge_matches.append((priority, float(match.group("value")), match.group(0)))
    charge_matches.sort(key=lambda item: item[0])
    charge = charge_matches[0][1] if charge_matches else None
    charge_raw = charge_matches[0][2] if charge_matches else None
    return {
        "temperature_C": temperature, "temperature_raw_value": temperature,
        "temperature_raw_unit": "°C" if temperature is not None else None,
        "temperature_source_expression": temperature_raw,
        "total_charge_C": charge, "total_charge_raw_value": charge,
        "total_charge_raw_unit": "C" if charge is not None else None,
        "total_charge_source_expression": charge_raw,
    }


def normalize_concentration(value: Any, unit: Any) -> dict[str, float | None]:
    output = {
        "mol_L": None, "mM": None, "vol_percent": None, "wt_percent": None, "ppm": None,
    }
    if value in (None, "") or unit in (None, ""):
        return output
    number = float(value)
    token = re.sub(r"\s+", "", str(unit)).casefold().replace("%v/v", "vol%").replace("v/v%", "vol%")
    if token in {"m", "mol/l", "moll-1", "mol·l-1"}:
        output["mol_L"] = number
    elif token == "mm":
        output["mM"] = number
        output["mol_L"] = number / 1000.0
    elif token in {"vol%", "vol.%", "volume%"}:
        output["vol_percent"] = number
    elif token in {"wt%", "wt.%", "weight%"}:
        output["wt_percent"] = number
    elif token == "ppm":
        output["ppm"] = number
    return output


def source_role(record: dict[str, Any]) -> str:
    rid = str(record.get("v01_record_id") or record.get("record_id") or "")
    if rid in TARGET_EXCLUSIONS and TARGET_EXCLUSIONS[rid][0] == "CITED_PRIOR_STUDY":
        return "CITED_PRIOR_STUDY"
    if rid in TARGET_EXCLUSIONS:
        return "AMBIGUOUS"
    return classify_context_role(
        str(record.get("source_text_excerpt") or ""),
        str(record.get("source_locator") or ""),
        str(record.get("evidence_authority") or ""),
    )


def classify_context_role(text: str, locator: str = "", authority: str = "") -> str:
    lower = text.casefold()
    if re.search(r"\b(?:review|perspective)\b", lower) and not re.search(r"\b(?:our|we|this work)\b", lower):
        return "REVIEW_OR_BACKGROUND"
    if re.search(r"\b(?:previous(?:ly)?|prior|earlier|recent) (?:work|study|studies)\b|\breported by\b|\baccording to\b", lower) and not re.search(r"\b(?:in this work|here we|our experiment|we measured|we achieved)\b", lower):
        return "CITED_PRIOR_STUDY"
    if "structured" in authority or str(locator).startswith("Table"):
        return "AUTHOR_SI_TABLE"
    if "source data" in lower:
        return "AUTHOR_SOURCE_DATA"
    if re.search(r"\b(?:in this work|our findings|we achieved|we engineered|we found)\b", lower):
        return "AUTHOR_RESULT"
    if re.search(r"\b(?:experimental|methods?|was prepared|were performed)\b", lower):
        return "AUTHOR_METHOD"
    if re.search(r"\b(?:we|our|this experiment)\b", lower):
        return "AUTHOR_EXPERIMENT"
    return "AMBIGUOUS"


def context_can_supply_training(role: str) -> bool:
    return role in {"AUTHOR_EXPERIMENT", "AUTHOR_METHOD", "AUTHOR_RESULT", "AUTHOR_SI_TABLE", "AUTHOR_SOURCE_DATA"}


def apply_unit_safe_fields(record: dict[str, Any]) -> dict[str, Any]:
    row = deepcopy(record)
    raw_value = row.get("proton_donor_concentration_raw_value")
    if raw_value is None:
        raw_value = row.get("proton_donor_concentration_value")
    raw_unit = row.get("proton_donor_concentration_raw_unit") or row.get("proton_donor_concentration_unit")
    donor = normalize_concentration(raw_value, raw_unit)
    for family, value in donor.items():
        row[f"proton_donor_concentration_{family}"] = value
    water_raw = row.get("water_content_raw_value") if row.get("water_content_raw_value") is not None else row.get("water_content_value")
    water = normalize_concentration(water_raw, row.get("water_content_raw_unit") or row.get("water_content_unit"))
    for family, value in water.items():
        row[f"water_content_{family}"] = value
    additive_raw = row.get("additive_concentration_raw_value") if row.get("additive_concentration_raw_value") is not None else row.get("additive_concentration_value")
    additive = normalize_concentration(additive_raw, row.get("additive_concentration_raw_unit") or row.get("additive_concentration_unit"))
    for family, value in additive.items():
        row[f"additive_concentration_{family}"] = value
    # The legacy universal donor column is retained only as historical raw
    # lineage and is never a v0.2 predictive feature.
    row["proton_donor_concentration_value"] = None
    row["water_content_value"] = None
    row["additive_concentration_value"] = None
    return row


def rebuild_record(record: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    row = apply_unit_safe_fields(record)
    old_id = str(record["record_id"])
    row["schema_version"] = SCHEMA_VERSION
    row["v01_record_id"] = old_id
    row["v02_record_id"] = stable_v02_id(old_id)
    row["record_id"] = row["v02_record_id"]
    row["source_context_role"] = source_role({**record, "v01_record_id": old_id})
    row["experiment_binding_id"] = f"{row.get('paper_id') or row.get('provisional_bundle_id')}::{row.get('source_asset_id')}::{row.get('source_locator')}"
    if row.get("condition_value_origin") == "INHERITED_SAME_PAPER_SERIES":
        row["experiment_binding_class"] = "DETERMINISTIC_SAME_PAPER_INHERITANCE"
    else:
        row["experiment_binding_class"] = "SAME_TABLE_ROW" if str(row.get("source_locator") or "").startswith("Table") else "SAME_FIGURE_CONDITION"
    corrections: list[dict[str, Any]] = []
    excerpt = str(record.get("source_text_excerpt") or "")
    parsed = parse_charge_temperature(excerpt)
    old_temp = record.get("temperature_C")
    old_charge = record.get("total_charge_C")
    # Record-level exact repair for the 16% experiment: its sentence says 30 C;
    # the earlier 20 C method value belongs to the general protocol.
    if old_id == "REC_f04b55d1f3bc6b21":
        parsed.update(total_charge_C=30.0, total_charge_raw_value=30.0, total_charge_raw_unit="C", total_charge_source_expression="increasing the total passed charge to 30 C")
    for field, old, new, raw_unit in [
        ("temperature_C", old_temp, parsed["temperature_C"], "°C"),
        ("total_charge_C", old_charge, parsed["total_charge_C"], "C"),
    ]:
        if record.get("model_eligible_fe") and not old_id.startswith("REC01_") and old != new and (old is not None or new is not None):
            row[field] = new
            prefix = "temperature" if field == "temperature_C" else "total_charge"
            row[f"{prefix}_raw_value"] = parsed[f"{prefix}_raw_value"]
            row[f"{prefix}_raw_unit"] = parsed[f"{prefix}_raw_unit"]
            corrections.append(_correction(record, field, old, new, parsed[f"{prefix}_raw_unit"], "CONFIRMED_NULL" if new is None else "CONFIRMED_CORRECTION", "Context-safe charge/temperature grammar; bare C is coulomb charge, not Celsius."))
    if old_id == "REC_f04b55d1f3bc6b21" and row.get("duration_h") is not None:
        old_duration = row["duration_h"]
        row["duration_h"] = None
        row["duration_raw_value"] = None
        row["duration_raw_unit"] = None
        corrections.append(_correction(record, "duration_h", old_duration, None, None, "CONFIRMED_NULL", "The 5 min value describes a potential-cycling step, not the total duration of the 30 C experiment reporting 16% FE."))
    # Correct the structured LHCE caption: 1 M belongs to LiTFSI and 1 vol% to EtOH.
    if old_id.startswith("REC01_") and record.get("paper_id") == "P0048":
        no_etoh = "without EtOH" in excerpt
        new_vol = None if no_etoh else 1.0
        if row.get("proton_donor_concentration_mol_L") is not None or row.get("proton_donor_concentration_vol_percent") != new_vol:
            row["proton_donor_concentration_mol_L"] = None
            row["proton_donor_concentration_vol_percent"] = new_vol
            row["proton_donor_concentration_raw_value"] = new_vol
            row["proton_donor_concentration_raw_unit"] = "vol%" if new_vol is not None else None
            if no_etoh:
                row["proton_donor"] = None
            corrections.append(_correction(record, "proton_donor_concentration", record.get("proton_donor_concentration_value"), new_vol, "vol%" if new_vol is not None else None, "CONFIRMED_NULL" if no_etoh else "CONFIRMED_CORRECTION", "Table caption distinguishes 1 M LiTFSI from 1 vol% EtOH; without-EtOH rows contain no donor."))
    elif record.get("model_eligible_fe") and record.get("proton_donor_concentration_value") is not None:
        family_values = {
            "mol/L": row.get("proton_donor_concentration_mol_L"),
            "vol%": row.get("proton_donor_concentration_vol_percent"),
            "wt%": row.get("proton_donor_concentration_wt_percent"),
            "ppm": row.get("proton_donor_concentration_ppm"),
        }
        corrected_unit, corrected_value = next(((unit, value) for unit, value in family_values.items() if value is not None), (None, None))
        corrections.append(_correction(record, "proton_donor_concentration_value", record.get("proton_donor_concentration_value"), corrected_value, corrected_unit, "CONFIRMED_CORRECTION" if corrected_value is not None else "AMBIGUOUS_REVIEW_REQUIRED", "Legacy universal concentration was replaced by a unit-family-specific field; no incompatible-family conversion was performed."))
    if old_id in TARGET_EXCLUSIONS:
        semantic, reason = TARGET_EXCLUSIONS[old_id]
        row["model_eligible_fe"] = False
        row["eligibility_tier"] = "TIER_C"
        row["review_status"] = "SOURCE_SEMANTIC_EXCLUDED"
        row["source_semantic_exclusion"] = semantic
        row["experiment_binding_class"] = "AMBIGUOUS_BINDING"
        corrections.append(_correction(record, "fe_nh3_percent", record.get("fe_nh3_percent"), None, "%", "CONFIRMED_NULL", reason))
    elif old_id in DUPLICATE_EXCLUSIONS:
        canonical, reason = DUPLICATE_EXCLUSIONS[old_id]
        row["model_eligible_fe"] = False
        row["review_status"] = "MERGED_DUPLICATE"
        row["canonical_v01_record_id"] = canonical
        row["canonical_record_id"] = stable_v02_id(canonical)
        corrections.append(_correction(record, "model_eligible_fe", True, False, None, "CONFIRMED_CORRECTION", reason))
    elif record.get("model_eligible_fe"):
        row["model_eligible_fe"] = True
        row["review_status"] = "MODEL_ELIGIBLE_FE"
    return row, corrections


def _correction(record: dict[str, Any], field: str, old: Any, new: Any, unit: Any, status: str, reason: str) -> dict[str, Any]:
    inherited = field.startswith("proton_donor_concentration") and record.get("condition_inherited_from_excerpt")
    return {
        "record_id": stable_v02_id(str(record["record_id"])),
        "paper_group": record.get("paper_id") or record.get("provisional_bundle_id") or record.get("source_bundle_id"),
        "field": field, "v01_value": old,
        "v01_raw_value": record.get(field.replace("_C", "_raw_value"), old),
        "v01_raw_unit": record.get(field.replace("_C", "_raw_unit")),
        "source_asset": record.get("condition_inherited_from_absolute_path") if inherited else record.get("source_filename"),
        "source_locator": record.get("condition_inherited_from_locator") if inherited else record.get("source_locator"),
        "source_excerpt": record.get("condition_inherited_from_excerpt") if inherited else record.get("source_text_excerpt"), "semantic_class": "SOURCE_SEMANTIC_REPAIR",
        "corrected_value": new, "corrected_unit": unit, "correction_status": status,
        "correction_reason": reason, "deterministic": True, "requires_human_review": False,
    }


def assert_unit_safe_feature_schema(schema: dict[str, Any]) -> None:
    forbidden = {"proton_donor_concentration_value", "water_content_value", "additive_concentration_value"}
    for family in schema.values():
        if not isinstance(family, dict):
            continue
        overlap = forbidden & set(family.get("numeric", []))
        if overlap:
            raise AssertionError(f"Ambiguous concentration feature(s): {sorted(overlap)}")


def validate_finite_matrix(matrix: Any) -> None:
    import numpy as np
    values = matrix.toarray() if hasattr(matrix, "toarray") else np.asarray(matrix)
    if not np.isfinite(values).all():
        raise AssertionError("Processed feature matrix contains non-finite values")


def no_cross_paper_binding(records: list[dict[str, Any]]) -> None:
    for row in records:
        owner = str(row.get("paper_id") or row.get("provisional_bundle_id") or row.get("source_bundle_id"))
        binding = str(row.get("experiment_binding_id") or "")
        if not binding.startswith(owner + "::"):
            raise AssertionError(f"Cross-paper or malformed experiment binding: {row.get('record_id')}")


def deterministic_hash(records: list[dict[str, Any]]) -> str:
    import json
    payload = json.dumps(sorted(records, key=lambda r: str(r["record_id"])), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
