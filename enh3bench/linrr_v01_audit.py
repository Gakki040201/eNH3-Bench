"""Narrow correctness audit for LiNRR Training Dataset v0.1.

This module does not change admission decisions or fit alternative models.  It
audits original Tier-C terminal accounting, deterministic structured rescues,
and the existing unconstrained grouped Ridge predictions.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from .linrr_predictor import (
    CATEGORICAL_R,
    NUMERIC_R,
    _matrix,
    _metrics,
    _pipeline,
    assert_no_group_leakage,
    available_interface_proxies,
    grouped_fold_indices,
    paper_group,
)
from .training_ingest import read_asset_blocks, sha256_file
from .training_rescue import read_structured_tables


TERMINAL_STATUSES = (
    "AUTO_RESOLVED",
    "HUMAN_REVIEW_REQUIRED",
    "MERGED_DUPLICATE",
    "REJECTED",
    "REMAINS_TIER_C",
)


def _list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return [text]
    return [str(item) for item in parsed] if isinstance(parsed, list) else [str(parsed)]


def build_tier_c_terminal_status(
    original_tier_c: list[dict[str, Any]],
    final_by_id: dict[str, dict[str, Any]],
    duplicate_by_id: dict[str, dict[str, Any]],
    packet_record_ids: set[str],
) -> list[dict[str, Any]]:
    """Assign exactly one terminal state to each original Tier-C record ID."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for original in original_tier_c:
        record_id = str(original.get("record_id") or "")
        if not record_id or record_id in seen:
            raise AssertionError(f"Duplicate or empty original Tier-C record_id: {record_id!r}")
        seen.add(record_id)
        final = final_by_id.get(record_id)
        if final is None:
            status, reason = "REJECTED", "Original Tier-C record is absent from the final v0.1 candidate table."
            canonical = None
        elif record_id in duplicate_by_id:
            status, reason = "MERGED_DUPLICATE", "Same-paper same-condition same-FE record was merged into its canonical record."
            canonical = duplicate_by_id[record_id].get("canonical_record_id")
        elif bool(final.get("model_eligible_fe")) and final.get("eligibility_tier") in {"TIER_A", "TIER_B"}:
            status, reason = "AUTO_RESOLVED", "This original Tier-C record itself passed all deterministic admission gates."
            canonical = record_id
        elif final.get("eligibility_tier") == "EXCLUDED":
            status, reason = "REJECTED", "Final deterministic classification excludes this candidate from LiNRR target admission."
            canonical = None
        else:
            flags = set(_list(original.get("ambiguity_flags")))
            unresolved_conflict = final.get("source_conflict_classification") == "TRUE_UNRESOLVED_CONFLICT"
            judgment_reasons = []
            if "TARGET_OWNERSHIP_UNCLEAR" in flags:
                judgment_reasons.append("target ownership remains unclear")
            if unresolved_conflict:
                judgment_reasons.append("source conflict remains unresolved")
            if "POSSIBLE_DUPLICATE_ROW" in flags:
                judgment_reasons.append("possible duplicate was not deterministically merged")
            if judgment_reasons:
                status = "HUMAN_REVIEW_REQUIRED"
                reason = "; ".join(judgment_reasons) + "."
            else:
                status = "REMAINS_TIER_C"
                failures = _list(final.get("missing_required_fields")) or _list(original.get("missing_required_fields"))
                reason = "Deterministic evidence remains insufficient for admission" + (f" ({', '.join(failures)})" if failures else "") + "; no unresolved semantic adjudication flag remains."
            canonical = None
        rows.append({
            "record_id": record_id,
            "original_tier": "TIER_C",
            "terminal_status": status,
            "final_tier": final.get("eligibility_tier") if final else "ABSENT",
            "model_eligible_fe": bool(final and final.get("model_eligible_fe")),
            "resolution_reason": reason,
            "canonical_record_id": canonical,
            "requires_human_review": status == "HUMAN_REVIEW_REQUIRED",
            "review_packet_retained": record_id in packet_record_ids,
        })
    validate_terminal_statuses(rows, expected_count=len(original_tier_c))
    return rows


def validate_terminal_statuses(rows: list[dict[str, Any]], expected_count: int) -> dict[str, int]:
    ids = [str(row.get("record_id") or "") for row in rows]
    if len(rows) != expected_count:
        raise AssertionError(f"Terminal rows {len(rows)} != original Tier-C count {expected_count}")
    if len(set(ids)) != len(ids):
        raise AssertionError("An original Tier-C record_id appears in more than one terminal state")
    invalid = sorted({str(row.get("terminal_status")) for row in rows} - set(TERMINAL_STATUSES))
    if invalid:
        raise AssertionError(f"Invalid terminal states: {invalid}")
    counts = Counter(str(row["terminal_status"]) for row in rows)
    if sum(counts.values()) != expected_count:
        raise AssertionError("Mutually-exclusive Tier-C terminal counts do not sum to the original count")
    return {status: counts.get(status, 0) for status in TERMINAL_STATUSES}


def packet_record_ids(packet_dir: str | Path) -> set[str]:
    output: set[str] = set()
    for path in Path(packet_dir).glob("*.md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        output.update(re.findall(r"^## Candidate\s+(\S+)\s*$", text, re.M))
    return output


def _structured_locator_exists(path: Path, source_table: str, locator: str) -> bool:
    for table in read_structured_tables(path):
        if table.name != source_table:
            continue
        row_match = re.search(r":row:(\d+)$", locator)
        col_match = re.search(r":column:(\d+)$", locator)
        if row_match:
            return 1 <= int(row_match.group(1)) <= len(table.rows)
        if col_match:
            return bool(table.rows) and 1 <= int(col_match.group(1)) <= max(len(row) for row in table.rows)
    return False


def audit_auto_resolved_records(
    records: list[dict[str, Any]], manifests: dict[str, dict[str, Any]], duplicate_ids: set[str]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in records:
        manifest = manifests.get(str(row.get("source_bundle_id")))
        assets = {str(asset.get("relative_path")): asset for asset in (manifest or {}).get("assets", [])}
        asset = assets.get(str(row.get("source_filename")))
        path = Path(str(asset.get("absolute_path"))) if asset else None
        asset_exists = bool(path and path.is_file())
        asset_hash_match = bool(asset_exists and row.get("source_file_sha256") == sha256_file(path))
        locator_exists = bool(asset_exists and _structured_locator_exists(path, str(row.get("source_table")), str(row.get("source_locator"))))
        inherited_asset_name = row.get("condition_inherited_from_asset")
        inherited_asset = assets.get(str(inherited_asset_name)) if inherited_asset_name else None
        inherited_path = Path(str(inherited_asset.get("absolute_path"))) if inherited_asset else None
        inherited_locator = row.get("condition_inherited_from_locator")
        inherited_locator_exists = True
        if inherited_asset_name:
            inherited_locator_exists = False
            if inherited_path and inherited_path.is_file():
                try:
                    inherited_locator_exists = str(inherited_locator) in {str(block.get("locator")) for block in read_asset_blocks(inherited_path)}
                except Exception:
                    inherited_locator_exists = False
        same_paper_inheritance = not inherited_asset_name or inherited_asset is not None
        flags = set(_list(row.get("ambiguity_flags")))
        ownership_valid = (
            "TARGET_OWNERSHIP_UNCLEAR" not in flags
            and bool(row.get("ownership_support_locator"))
            and row.get("evidence_owner_id") == (row.get("paper_id") or row.get("provisional_bundle_id"))
        )
        electrolyte_gate = bool(row.get("lithium_salt") and row.get("solvent"))
        conflict_clear = "SOURCE_CONFLICT" not in flags and row.get("source_conflict_classification") != "TRUE_UNRESOLVED_CONFLICT"
        duplicate_clear = row.get("record_id") not in duplicate_ids and "POSSIBLE_DUPLICATE_ROW" not in flags and row.get("review_status") != "MERGED_DUPLICATE"
        checks = {
            "source_asset_exists": asset_exists,
            "source_asset_hash_match": asset_hash_match,
            "source_locator_exists": locator_exists,
            "same_paper_inheritance": same_paper_inheritance,
            "inherited_locator_exists": inherited_locator_exists,
            "fe_ownership_valid": ownership_valid,
            "electrolyte_gate_satisfied": electrolyte_gate,
            "source_conflict_clear": conflict_clear,
            "duplicate_clear": duplicate_clear,
            "model_eligible_fe": bool(row.get("model_eligible_fe")),
        }
        output.append({
            "record_id": row.get("record_id"), "paper_id": row.get("paper_id"),
            "source_asset": row.get("source_filename"), "source_locator": row.get("source_locator"),
            "condition_value_origin": row.get("condition_value_origin"),
            "condition_inherited_from_asset": inherited_asset_name,
            "condition_inherited_from_locator": inherited_locator,
            **checks, "audit_pass": all(checks.values()),
            "audit_issues": [name for name, passed in checks.items() if not passed],
        })
    return output


def ridge_oof_diagnostics(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    import numpy as np

    usable = sorted((row for row in records if row.get("fe_nh3_percent") is not None), key=lambda row: str(row["record_id"]))
    groups = [paper_group(row) for row in usable]
    folds = grouped_fold_indices(groups)
    assert_no_group_leakage(groups, folds)
    interface = available_interface_proxies(usable)
    families = {"MODEL_R": list(CATEGORICAL_R)}
    if interface:
        families["MODEL_RI"] = list(CATEGORICAL_R) + interface
    y = [float(row["fe_nh3_percent"]) for row in usable]
    oof_rows: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    all_finite = True
    maximum_abs_normalized = 0.0
    for family, categorical in families.items():
        fields = [*NUMERIC_R, *categorical]
        X = _matrix(usable, fields)
        for fold_i, (train, test) in enumerate(folds):
            pipeline = _pipeline("Ridge", categorical, list(NUMERIC_R))
            pipeline.fit([X[index] for index in train], [y[index] for index in train])
            test_matrix = [X[index] for index in test]
            predictions = [float(value) for value in pipeline.predict(test_matrix)]
            preprocess = pipeline.named_steps["preprocess"]
            numeric_pipe = preprocess.named_transformers_["numeric"]
            raw_numeric = np.asarray([[usable[index].get(field) for field in NUMERIC_R] for index in test], dtype=object)
            normalized = np.asarray(numeric_pipe.transform(raw_numeric), dtype=float)
            full_processed = np.asarray(preprocess.transform(test_matrix), dtype=float)
            all_finite = all_finite and bool(np.isfinite(normalized).all() and np.isfinite(full_processed).all() and np.isfinite(predictions).all())
            indicator_features = list(getattr(numeric_pipe.named_steps["impute"].indicator_, "features_", []))
            normalized_names = [f"normalized_{field}" for field in NUMERIC_R] + [f"normalized_missing_indicator_{NUMERIC_R[int(index)]}" for index in indicator_features]
            maximum_abs_normalized = max(maximum_abs_normalized, float(np.max(np.abs(normalized))) if normalized.size else 0.0)
            train_targets = [y[index] for index in train]
            test_targets = [y[index] for index in test]
            for local_i, index in enumerate(test):
                diagnostic = {
                    "feature_family": family, "record_id": usable[index]["record_id"], "paper_group": groups[index], "fold": fold_i,
                    "observed_fe": y[index], "predicted_fe": predictions[local_i], "absolute_error": abs(y[index] - predictions[local_i]),
                    "training_target_min": min(train_targets), "training_target_max": max(train_targets),
                    "test_target_min": min(test_targets), "test_target_max": max(test_targets),
                }
                diagnostic.update({f"raw_{field}": usable[index].get(field) for field in NUMERIC_R})
                diagnostic.update({name: float(normalized[local_i, col_i]) for col_i, name in enumerate(normalized_names)})
                oof_rows.append(diagnostic)
            score = _metrics(test_targets, predictions)
            train_mean = float(np.mean(train_targets))
            fold_rows.append({
                "feature_family": family, "fold": fold_i, "train_rows": len(train), "test_rows": len(test),
                "train_groups": sorted({groups[index] for index in train}), "test_groups": sorted({groups[index] for index in test}),
                "target_train_min": min(train_targets), "target_train_max": max(train_targets), "target_train_mean": train_mean,
                "target_train_std": float(np.std(train_targets, ddof=0)), "prediction_min": min(predictions),
                "prediction_max": max(predictions), "prediction_mean": float(np.mean(predictions)), **score,
            })
    return oof_rows, fold_rows, {
        "group_leakage": False,
        "processed_numeric_and_full_matrix_all_finite": all_finite,
        "maximum_absolute_normalized_feature": maximum_abs_normalized,
        "interface_proxies": interface,
        "numeric_preprocessing": {"imputation": "median", "missing_indicators": True, "scaling": "StandardScaler"},
        "categorical_preprocessing": {"missing_value": "__MISSING__", "encoder": "OneHotEncoder", "handle_unknown": "ignore"},
    }


def numeric_unit_audit(records: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    sentinels = {-1.0, 999.0, 9999.0}
    nonfinite = []
    sentinel_hits = []
    for row in records:
        for field in NUMERIC_R:
            value = row.get(field)
            if value is None:
                continue
            number = float(value)
            if not math.isfinite(number):
                nonfinite.append({"record_id": row.get("record_id"), "field": field, "value": value})
            if number in sentinels:
                sentinel_hits.append({"record_id": row.get("record_id"), "field": field, "value": value})
    donor_units = sorted({str(row.get("proton_donor_concentration_unit") or row.get("proton_donor_concentration_raw_unit") or "").strip() for row in records if row.get("proton_donor_concentration_value") is not None})
    donor_families = {_unit_family(unit) for unit in donor_units if unit}
    if len(donor_families) > 1:
        issues.append({"type": "INCOMPATIBLE_UNIT_MIX", "field": "proton_donor_concentration_value", "units": donor_units, "unit_families": sorted(donor_families)})
    water_units = sorted({str(row.get("water_content_unit") or row.get("water_content_raw_unit") or "").strip() for row in records if row.get("water_content_value") is not None})
    water_families = {_unit_family(unit) for unit in water_units if unit}
    if len(water_families) > 1:
        issues.append({"type": "INCOMPATIBLE_UNIT_MIX", "field": "water_content_value", "units": water_units, "unit_families": sorted(water_families)})
    conversion_issues, conversion_checks = _conversion_issues(records)
    issues.extend(conversion_issues)
    suspicious_ranges = []
    for row in records:
        if row.get("temperature_C") is not None and abs(float(row["temperature_C"])) > 100:
            suspicious_ranges.append({"record_id": row.get("record_id"), "field": "temperature_C", "value": row["temperature_C"]})
        if row.get("duration_h") is not None and float(row["duration_h"]) > 200:
            suspicious_ranges.append({"record_id": row.get("record_id"), "field": "duration_h", "value": row["duration_h"]})
    if suspicious_ranges:
        issues.append({"type": "SCIENTIFIC_RANGE_REVIEW_REQUIRED", "values": suspicious_ranges})
    feature_set = set(NUMERIC_R)
    raw_duplicates = sorted(field for field in feature_set if "raw" in field)
    return {
        "issues": issues,
        "nonfinite_raw_numeric_values": nonfinite,
        "sentinel_hits": sentinel_hits,
        "proton_donor_units": donor_units,
        "water_units": water_units,
        "raw_and_normalized_duplicate_features": raw_duplicates,
        "only_canonical_numeric_features_enter_model": not raw_duplicates,
        "normalization_checks": conversion_checks,
    }


def _unit_family(unit: str) -> str:
    key = re.sub(r"\s+", "", unit).casefold()
    if key in {"m", "mm", "mol/l", "moll-1"}:
        return "molar_concentration"
    if key in {"vol%", "wt%", "%"}:
        return "fraction_or_percent"
    if key == "ppm":
        return "parts_per_million"
    return key


def _conversion_issues(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    issues = []
    checked = Counter()
    unsupported = []
    checks = (
        ("current_density_raw_value", "current_density_raw_unit", "current_density_mA_cm2", {"a/cm2": 1000.0, "acm-2": 1000.0, "ma/cm2": 1.0, "macm-2": 1.0}),
        ("duration_raw_value", "duration_raw_unit", "duration_h", {"min": 1 / 60, "mins": 1 / 60, "minute": 1 / 60, "minutes": 1 / 60, "h": 1.0, "hour": 1.0, "hours": 1.0}),
        ("pressure_raw_value", "pressure_raw_unit", "pressure_bar", {"kpa": 0.01, "atm": 1.01325, "bar": 1.0}),
        ("lithium_salt_concentration_raw_value", "lithium_salt_concentration_raw_unit", "lithium_salt_concentration_mol_L", {"m": 1.0, "mol/l": 1.0, "mm": 0.001}),
    )
    for row in records:
        for raw_field, unit_field, normalized_field, factors in checks:
            raw, normalized = row.get(raw_field), row.get(normalized_field)
            unit = re.sub(r"\s+", "", str(row.get(unit_field) or "")).replace("−", "-").replace("^", "").replace("·", "").casefold()
            if raw is None or normalized is None:
                continue
            if normalized_field == "current_density_mA_cm2" and unit == "ma" and row.get("electrode_area_cm2"):
                expected = float(raw) / float(row["electrode_area_cm2"])
            elif unit in factors:
                expected = float(raw) * factors[unit]
            else:
                unsupported.append({"record_id": row.get("record_id"), "field": normalized_field, "raw_unit": row.get(unit_field)})
                issues.append({"type": "UNSUPPORTED_UNIT_WITH_NORMALIZED_VALUE", "record_id": row.get("record_id"), "field": normalized_field, "raw_unit": row.get(unit_field), "normalized_value": normalized})
                continue
            checked[normalized_field] += 1
            if not math.isclose(float(normalized), expected, rel_tol=1e-6, abs_tol=1e-9):
                issues.append({"type": "NORMALIZATION_MISMATCH", "record_id": row.get("record_id"), "field": normalized_field, "raw_value": raw, "raw_unit": row.get(unit_field), "normalized_value": normalized, "expected": expected})
    return issues, {"checked_by_field": dict(checked), "unsupported_units": unsupported, "mismatch_count": sum(issue["type"] == "NORMALIZATION_MISMATCH" for issue in issues)}


def classify_ridge_cause(preprocessing: dict[str, Any], unit_audit: dict[str, Any], oof_rows: list[dict[str, Any]]) -> str:
    pipeline_bug = not preprocessing.get("processed_numeric_and_full_matrix_all_finite") or preprocessing.get("group_leakage")
    data_unit_bug = any(issue.get("type") in {"INCOMPATIBLE_UNIT_MIX", "NORMALIZATION_MISMATCH"} for issue in unit_audit.get("issues", []))
    extreme = any(abs(float(row["predicted_fe"])) > 200 for row in oof_rows) and float(preprocessing.get("maximum_absolute_normalized_feature") or 0) > 5
    if sum((pipeline_bug, data_unit_bug, extreme)) > 1:
        return "MIXED_CAUSES"
    if pipeline_bug:
        return "PIPELINE_BUG"
    if data_unit_bug:
        return "DATA_UNIT_BUG"
    if extreme:
        return "EXTREME_EXTRAPOLATION_WITH_VALID_PIPELINE"
    return "SMALL_DATA_LINEAR_MODEL_FAILURE"
