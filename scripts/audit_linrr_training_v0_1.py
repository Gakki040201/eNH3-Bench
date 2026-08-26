#!/usr/bin/env python
"""Audit LiNRR Training Dataset v0.1 accounting and grouped Ridge behavior."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.linrr_v01_audit import (  # noqa: E402
    audit_auto_resolved_records,
    build_tier_c_terminal_status,
    classify_ridge_cause,
    numeric_unit_audit,
    packet_record_ids,
    ridge_oof_diagnostics,
    validate_terminal_statuses,
)
from enh3bench.training_rescue import load_records_csv  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--work-root", type=Path, default=Path(r"F:\eNH3_Bench_Work"))
    result.add_argument("--replace", action="store_true", help="Replace only existing v0.1 Model_Audit diagnostics.")
    return result


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(rows: list[dict], path: Path) -> None:
    fields = sorted({field for row in rows for field in row}) if rows else ["EMPTY"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value for field, value in row.items()})


def _metric_index(metrics: list[dict]) -> dict[tuple[str, str], dict]:
    return {(row["feature_family"], row["model"]): row for row in metrics if row.get("tier_scope") == "A+B"}


def _recreated_metrics(oof: list[dict]) -> dict[str, dict[str, float]]:
    from enh3bench.linrr_predictor import _metrics
    output = {}
    for family in sorted({row["feature_family"] for row in oof}):
        rows = [row for row in oof if row["feature_family"] == family]
        output[family] = _metrics([row["observed_fe"] for row in rows], [row["predicted_fe"] for row in rows])
    return output


def _report(payload: dict) -> str:
    counts = payload["tier_c_terminal_counts"]
    metrics = payload["model_metrics"]
    largest = payload["ten_largest_ridge_errors"]
    lines = [
        "# LiNRR Training Dataset v0.1 correctness and model audit", "",
        "## Terminal-state accounting", "",
        "The prior `119 human-review-required` value was an implementation/accounting bug: every original Tier-C record was blanket-marked for review, while the 31 auto-resolved rows were newly created structured records rather than transitions of those original record IDs.", "",
        f"- Original Tier-C records: {payload['original_tier_c_count']}",
        *[f"- {status}: {count}" for status, count in counts.items()],
        f"- Unresolved human review: {payload['unresolved_human_review_count']}",
        f"- Review packets retained: {payload['review_packets_total']} paper packets covering {payload['review_packet_record_count']} original records", "",
        "## Auto-resolved scientific audit", "",
        f"- Audited structured auto-resolved rows: {payload['auto_resolved_count']}",
        f"- Rows retaining eligibility: {payload['auto_resolved_eligible_count']}",
        f"- Rows failing the audit: {payload['auto_resolved_audit_failures']}", "",
        "## Ridge diagnosis", "",
        f"- Root-cause classification: **{payload['ridge_root_cause']}**",
        f"- Processed matrices finite: {payload['preprocessing_audit']['processed_numeric_and_full_matrix_all_finite']}",
        f"- Paper leakage: {payload['preprocessing_audit']['group_leakage']}",
        f"- Maximum absolute normalized feature: {payload['preprocessing_audit']['maximum_absolute_normalized_feature']:.6g}",
        "- Numeric pipeline: median imputation, missing indicators, StandardScaler.",
        "- Categorical pipeline: explicit `__MISSING__`, OneHotEncoder(handle_unknown=ignore).", "",
        "The pipeline reproduces the stored unconstrained OOF metrics and contains no non-finite processed values or paper leakage. However, proton-donor concentration mixes molar and volume-percent values in one numeric feature, and sparse group-held-out folds produce extreme standardized extrapolation. A source charge of 700 C was incorrectly represented as 700 deg C, while a 300 h value comes from a cited prior study; both require source-level review and were not silently repaired. Thus the instability has mixed data-unit, extraction, and small-data extrapolation causes; predictions were not clipped.", "",
        "## Predictive conclusion", "",
        f"- DATA SUFFICIENCY GATE: **{payload['data_sufficiency_gate']}**",
        f"- PREDICTIVE PERFORMANCE: **{payload['predictive_performance']}**",
        "- DummyRegressor is the reference baseline.",
        f"- MODEL_R Dummy MAE/RMSE/R2: {metrics['MODEL_R|DummyRegressor']['mae']:.6g} / {metrics['MODEL_R|DummyRegressor']['rmse']:.6g} / {metrics['MODEL_R|DummyRegressor']['r2']:.6g}",
        f"- MODEL_R Ridge MAE/RMSE/R2: {metrics['MODEL_R|Ridge']['mae']:.6g} / {metrics['MODEL_R|Ridge']['rmse']:.6g} / {metrics['MODEL_R|Ridge']['r2']:.6g}",
        f"- MODEL_R Random Forest MAE/RMSE/R2: {metrics['MODEL_R|RandomForestRegressor']['mae']:.6g} / {metrics['MODEL_R|RandomForestRegressor']['rmse']:.6g} / {metrics['MODEL_R|RandomForestRegressor']['r2']:.6g}",
        "- Random Forest remains worse than Dummy on grouped out-of-paper MAE and RMSE. The current dataset does not demonstrate useful out-of-paper predictive performance.", "",
        "## Ten largest unconstrained Ridge OOF errors", "",
        "| Features | Record | Paper | Fold | Observed | Predicted | Absolute error |", "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in largest:
        lines.append(f"| {row['feature_family']} | {row['record_id']} | {row['paper_group']} | {row['fold']} | {row['observed_fe']:.6g} | {row['predicted_fe']:.6g} | {row['absolute_error']:.6g} |")
    lines.extend(["", "The data-sufficiency PASS means only that fitting was permitted by the preregistered row/group threshold. It is not a scientific model PASS and does not establish prospective predictive validity.", ""])
    return "\n".join(lines)


def main() -> int:
    args = parser().parse_args()
    work = args.work_root.resolve()
    v0 = work / "02_Data" / "Experiment_Records" / "LiNRR_Training_v0"
    v1 = work / "02_Data" / "Experiment_Records" / "LiNRR_Training_v0_1"
    report_root = work / "04_Exports" / "Reports" / "LiNRR_Training_v0_1"
    model = work / "02_Data" / "Modeling" / "LiNRR_Shadow_v0_1"
    output = report_root / "Model_Audit"
    if output.exists() and not args.replace:
        raise FileExistsError(f"Refusing to overwrite model audit output: {output}")

    original = load_records_csv(v0 / "all_candidate_records.csv")
    original_tier_c = [row for row in original if row.get("eligibility_tier") == "TIER_C"]
    final_records = _jsonl(v1 / "all_candidate_records.jsonl")
    final_by_id = {str(row["record_id"]): row for row in final_records}
    duplicates = _csv(v1 / "duplicate_resolution.csv")
    duplicate_by_id = {str(row["record_id"]): row for row in duplicates}
    packet_ids = packet_record_ids(report_root / "review_packets")
    terminal = build_tier_c_terminal_status(original_tier_c, final_by_id, duplicate_by_id, packet_ids)
    terminal_counts = validate_terminal_statuses(terminal, expected_count=119)

    manifests_list = _jsonl(v0 / "paper_asset_manifest.jsonl")
    manifests = {str(row["bundle_id"]): row for row in manifests_list}
    auto_records = [row for row in final_records if row.get("extraction_status") == "AUTO_RESOLVED_STRUCTURED_TABLE"]
    auto_audit = audit_auto_resolved_records(auto_records, manifests, set(duplicate_by_id))

    eligible = _jsonl(v1 / "model_eligible_records.jsonl")
    oof, folds, preprocessing = ridge_oof_diagnostics(eligible)
    units = numeric_unit_audit(eligible)
    cause = classify_ridge_cause(preprocessing, units, oof)
    stored_payload = json.loads((model / "model_metrics.json").read_text(encoding="utf-8"))
    stored = _metric_index(stored_payload["metrics"])
    recreated = _recreated_metrics(oof)
    ridge_metrics_match = all(
        math.isclose(float(recreated[family][metric]), float(stored[(family, "Ridge")][metric]), rel_tol=1e-9, abs_tol=1e-9)
        for family in recreated for metric in ("mae", "rmse", "r2")
    )
    metric_payload = {f"{family}|{name}": {key: value for key, value in row.items() if key in {"mae", "rmse", "r2"}} for (family, name), row in stored.items()}
    dummy = stored[("MODEL_R", "DummyRegressor")]
    forest = stored[("MODEL_R", "RandomForestRegressor")]
    predictive = "FAIL" if forest["mae"] >= dummy["mae"] or forest["rmse"] >= dummy["rmse"] else "PASS"
    largest = sorted(oof, key=lambda row: float(row["absolute_error"]), reverse=True)[:10]
    unresolved = terminal_counts["HUMAN_REVIEW_REQUIRED"]
    payload = {
        "audit_schema_version": "linrr_v0_1_correctness_audit_v1",
        "original_tier_c_count": len(original_tier_c),
        "tier_c_terminal_counts": terminal_counts,
        "terminal_state_invariant_pass": sum(terminal_counts.values()) == 119 and len({row["record_id"] for row in terminal}) == 119,
        "unresolved_human_review_count": unresolved,
        "review_packets_total": len(list((report_root / "review_packets").glob("*.md"))),
        "review_packet_record_count": sum(bool(row["review_packet_retained"]) for row in terminal),
        "auto_resolved_count": len(auto_records),
        "auto_resolved_eligible_count": sum(bool(row.get("model_eligible_fe")) for row in auto_records),
        "auto_resolved_audit_failures": sum(not row["audit_pass"] for row in auto_audit),
        "ridge_root_cause": cause,
        "ridge_metrics_reproduced_exactly": ridge_metrics_match,
        "recreated_ridge_metrics": recreated,
        "preprocessing_audit": preprocessing,
        "unit_audit": units,
        "ten_largest_ridge_errors": largest,
        "model_metrics": metric_payload,
        "data_sufficiency_gate": "PASS" if stored_payload["gate"]["passed"] else "FAIL",
        "predictive_performance": predictive,
    }
    if not payload["terminal_state_invariant_pass"]:
        raise AssertionError("Tier-C terminal-state invariant failed")
    if payload["auto_resolved_audit_failures"]:
        raise AssertionError("One or more auto-resolved records failed scientific provenance audit")
    if not preprocessing["processed_numeric_and_full_matrix_all_finite"] or preprocessing["group_leakage"]:
        raise AssertionError("Ridge preprocessing finite/leakage invariant failed")
    if not ridge_metrics_match:
        raise AssertionError("Recreated Ridge OOF metrics do not match stored metrics")

    output.mkdir(parents=True, exist_ok=args.replace)
    _write_csv(terminal, output / "tier_c_terminal_status.csv")
    _write_csv(auto_audit, output / "auto_resolved_audit.csv")
    _write_csv(oof, output / "ridge_oof_diagnostics.csv")
    _write_csv(folds, output / "ridge_fold_diagnostics.csv")
    (output / "model_audit.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "MODEL_AUDIT_REPORT.md").write_text(_report(payload), encoding="utf-8")
    print(json.dumps({"output": str(output), "terminal_counts": terminal_counts, "unresolved_human_review_count": unresolved, "auto_resolved_audit_failures": payload["auto_resolved_audit_failures"], "ridge_root_cause": cause, "largest_ridge_error": largest[0], "data_sufficiency_gate": payload["data_sufficiency_gate"], "predictive_performance": predictive}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
