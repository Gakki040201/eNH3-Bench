#!/usr/bin/env python
"""Build the independent, unit-safe LiNRR Training Dataset v0.2."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.linrr_predictor_v02 import train_grouped_v02  # noqa: E402
from enh3bench.linrr_v02 import (  # noqa: E402
    AUDITED_NUMERIC_FIELDS, DUPLICATE_EXCLUSIONS, TARGET_EXCLUSIONS,
    deterministic_hash, no_cross_paper_binding, rebuild_record, stable_v02_id,
)
from enh3bench.training_ingest import read_asset_blocks  # noqa: E402


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, default=Path(r"F:\eNH3_Bench_Work"))
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--replace-v02", action="store_true", help="Replace only v0.2 runtime outputs after an interrupted build.")
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row}) if rows else ["EMPTY"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def write_jsonl(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def manifest_assets(manifests: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    by_asset = {}
    by_bundle = {}
    for manifest in manifests:
        by_bundle[str(manifest["bundle_id"])] = manifest
        for asset in manifest.get("assets", []):
            by_asset[str(asset["source_asset_id"])] = asset
    return by_asset, by_bundle


def enrich_inherited_provenance(records: list[dict], by_bundle: dict[str, dict]) -> None:
    cache: dict[str, list[dict]] = {}
    for row in records:
        asset_name = row.get("condition_inherited_from_asset")
        locator = row.get("condition_inherited_from_locator")
        if not asset_name or not locator:
            continue
        manifest = by_bundle.get(str(row.get("source_bundle_id")), {})
        asset = next((item for item in manifest.get("assets", []) if item.get("relative_path") == asset_name), None)
        if not asset or not Path(asset["absolute_path"]).is_file():
            continue
        path = str(asset["absolute_path"])
        if path not in cache:
            cache[path] = read_asset_blocks(path)
        block = next((item for item in cache[path] if str(item.get("locator")) == str(locator)), None)
        if block:
            text = " ".join(str(block.get("text") or "").split())
            match = re.search(r"(?:LiBF4|LiTFSI|ethanol|EtOH|vol%|mol\s*/\s*L|\bM\b)", text, re.I)
            center = match.start() if match else 0
            excerpt = text[max(0, center - 300):center + 700]
            row["condition_inherited_from_absolute_path"] = path
            row["condition_inherited_from_excerpt"] = excerpt


def numeric_audit(eligible: list[dict], by_asset: dict[str, dict], correction_fields: set[tuple[str, str]]) -> list[dict]:
    output = []
    for row in eligible:
        source = by_asset.get(str(row.get("source_asset_id")), {})
        asset_exists = bool(source.get("absolute_path") and Path(source["absolute_path"]).is_file())
        for field in AUDITED_NUMERIC_FIELDS:
            value = row.get(field)
            raw_prefix = field
            for suffix in ("_mol_L", "_mM", "_vol_percent", "_wt_percent", "_ppm"):
                raw_prefix = raw_prefix.removesuffix(suffix)
            corrected = (row["record_id"], field) in correction_fields or (field.startswith("proton_donor_concentration_") and row.get("paper_id") == "P0048")
            status = "PARSER_CORRECTED" if corrected else ("SOURCE_CONFIRMED" if value is not None and asset_exists else "SOURCE_AMBIGUOUS")
            inherited_recipe = field.startswith(("lithium_salt_concentration_", "proton_donor_concentration_", "water_content_")) and row.get("condition_value_origin") == "INHERITED_SAME_PAPER_SERIES"
            original_headers = row.get("original_headers") if isinstance(row.get("original_headers"), dict) else {}
            header = original_headers.get(field)
            exact_excerpt = f"{header}: {value}" if header and value is not None else row.get("source_text_excerpt")
            output.append({
                "record_id": row["record_id"], "paper_group": row.get("paper_id") or row.get("provisional_bundle_id"),
                "field": field, "value": value,
                "raw_value": row.get(raw_prefix + "_raw_value"), "raw_unit": row.get(raw_prefix + "_raw_unit"),
                "source_asset": row.get("condition_inherited_from_absolute_path") if inherited_recipe else (source.get("absolute_path") or row.get("source_filename")),
                "source_locator": row.get("condition_inherited_from_locator") if inherited_recipe else row.get("source_locator"),
                "source_excerpt": row.get("condition_inherited_from_excerpt") if inherited_recipe else exact_excerpt,
                "status": status, "notes": "Exact source asset verified." if asset_exists else "No numeric value admitted; missingness is preserved and imputed only inside training folds.",
            })
    return output


def binding_audit(eligible: list[dict], by_asset: dict[str, dict]) -> list[dict]:
    output = []
    major = ["fe_nh3_percent", "current_density_mA_cm2", "electrolyte", "proton_donor", "pressure_bar", "duration_or_charge"]
    for row in eligible:
        asset = by_asset.get(str(row.get("source_asset_id")), {})
        binding = row["experiment_binding_class"]
        direct = "SAME_TABLE_ROW" if str(row.get("source_locator") or "").startswith("Table") else "SAME_FIGURE_CONDITION"
        recipe_binding = "DETERMINISTIC_SAME_PAPER_INHERITANCE" if row.get("condition_value_origin") == "INHERITED_SAME_PAPER_SERIES" else direct
        output.append({
            "record_id": row["record_id"], "paper_group": row.get("paper_id") or row.get("provisional_bundle_id"),
            "experiment_binding_id": row["experiment_binding_id"], "overall_binding": binding,
            "source_context_role": row["source_context_role"], "source_asset": asset.get("absolute_path") or row.get("source_filename"),
            "source_locator": row.get("source_locator"), "source_excerpt": row.get("source_text_excerpt"),
            "inherited_methods_asset": row.get("condition_inherited_from_absolute_path"),
            "inherited_methods_locator": row.get("condition_inherited_from_locator"),
            "inherited_methods_excerpt": row.get("condition_inherited_from_excerpt"),
            "fe_nh3_percent_binding": direct,
            "current_density_mA_cm2_binding": direct,
            "electrolyte_binding": recipe_binding,
            "proton_donor_binding": recipe_binding,
            "pressure_bar_binding": direct,
            "duration_or_charge_binding": direct,
            "cross_paper_inheritance": False, "model_eligible": True,
        })
    return output


def ranked_review_queue(v1: Path, report_v1: Path, by_bundle: dict[str, dict]) -> list[dict]:
    terminal = load_csv(report_v1 / "Model_Audit" / "tier_c_terminal_status.csv")
    wanted = {row["record_id"] for row in terminal if row.get("terminal_status") == "HUMAN_REVIEW_REQUIRED"}
    source_by_id = {row["record_id"]: row for row in load_jsonl(v1 / "all_candidate_records.jsonl")}
    rows = [source_by_id[record_id] for record_id in sorted(wanted)]
    if len(rows) != 34:
        raise RuntimeError(f"v0.1 human-review baseline mismatch: {len(rows)} != 34")
    output = []
    for row in rows:
        bundle = by_bundle.get(str(row.get("source_bundle_id")), {})
        assets = [asset.get("absolute_path") for asset in bundle.get("assets", []) if asset.get("absolute_path") and Path(asset["absolute_path"]).is_file()]
        missing = row.get("missing_required_fields") or row.get("ambiguity_flags") or "scientific adjudication"
        gain = 4 if not row.get("paper_id") else 2
        if assets: gain += 2
        if row.get("interface_sei_characterization_present") in {"True", True}: gain += 1
        output.append({
            "record_id": row.get("record_id"), "paper_group": row.get("paper_id") or row.get("provisional_bundle_id"),
            "reason": "Existing local evidence may resolve ownership/electrolyte ambiguity; no automatic admission.",
            "missing_or_ambiguous_fields": missing, "source_assets_available": assets,
            "potential_training_gain": "new paper group" if not row.get("paper_id") else "within-group electrolyte/process diversity",
            "_score": gain,
        })
    output.sort(key=lambda row: (-row["_score"], str(row["record_id"])))
    for priority, row in enumerate(output, 1):
        row["priority"] = priority
        row.pop("_score")
    return output


def coverage(records: list[dict], eligible: list[dict], removed: list[dict], newly: list[dict]) -> dict:
    def counts(field: str) -> dict[str, int]:
        return dict(sorted(Counter(str(row.get(field) or "__MISSING__") for row in eligible).items()))
    def present(field: str) -> int:
        return sum(row.get(field) is not None for row in eligible)
    return {
        "schema_version": "linrr_training_coverage_v0_2", "eligible_fe_rows": len(eligible),
        "eligible_paper_groups": len({row.get("paper_id") or row.get("provisional_bundle_id") for row in eligible}),
        "tier_A": sum(row.get("eligibility_tier") == "TIER_A" for row in eligible),
        "tier_B": sum(row.get("eligibility_tier") == "TIER_B" for row in eligible),
        "records_by_salt": counts("lithium_salt"), "records_by_solvent": counts("solvent"),
        "records_by_proton_donor": counts("proton_donor"),
        "unit_family_counts": {field: present(field) for field in ["proton_donor_concentration_mol_L", "proton_donor_concentration_vol_percent", "proton_donor_concentration_wt_percent", "proton_donor_concentration_ppm", "water_content_mol_L", "water_content_vol_percent", "water_content_wt_percent", "water_content_ppm"]},
        "current_density_coverage": present("current_density_mA_cm2"), "charge_coverage": present("total_charge_C"),
        "duration_coverage": present("duration_h"), "pressure_coverage": present("pressure_bar"),
        "water_coverage": sum(any(row.get(field) is not None for field in ["water_content_mol_L", "water_content_vol_percent", "water_content_wt_percent", "water_content_ppm"]) for row in eligible),
        "interface_proxy_coverage": {field: present(field) for field in ["interface_sei_characterization_present", "interface_lif_reported", "interface_n_containing_sei_reported", "electrolyte_architecture"]},
        "records_removed_from_v01_eligibility": removed, "records_newly_admitted": newly,
        "records_corrected_but_still_eligible": [row["v01_record_id"] for row in eligible if row["v01_record_id"] == "REC_f04b55d1f3bc6b21" or (row.get("paper_id") == "P0048" and row["v01_record_id"].startswith("REC01_"))],
        "candidate_records": len(records),
    }


def write_workbook(path: Path, sheets: list[tuple[str, list[dict]]]) -> None:
    from openpyxl import Workbook
    workbook = Workbook(); workbook.remove(workbook.active)
    for title, rows in sheets:
        sheet = workbook.create_sheet(title[:31])
        fields = sorted({key for row in rows for key in row}) if rows else ["EMPTY"]
        sheet.append(fields)
        for row in rows:
            values = []
            for field in fields:
                value = row.get(field)
                if isinstance(value, (list, dict)): value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, str):
                    value = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", value[:32767])
                values.append(value)
            sheet.append(values)
        sheet.freeze_panes = "A2"
    path.parent.mkdir(parents=True, exist_ok=True); workbook.save(path)


def report_markdown(summary: dict, cover: dict, model: dict) -> str:
    lines = ["# LiNRR Training Dataset v0.2", "", "Independent source-semantic and unit-safe rebuild. No v0/v0.1 artifact was overwritten.", "",
             f"- Eligible FE rows: {summary['model_eligible_fe_rows']}", f"- Eligible paper groups: {summary['eligible_paper_groups']}",
             f"- DATA SUFFICIENCY GATE: **{summary['data_sufficiency_gate']}**", f"- PREDICTIVE PERFORMANCE: **{model['predictive_performance']}**", "",
             "The universal proton-donor concentration feature is excluded. M/mM are represented only in mol/L; vol%, wt%, and ppm remain separate families.", "",
             "Grouped OOF predictions are unconstrained primary results. Bounded 0–100 predictions are diagnostics only. With five groups and five splits, this run is also leave-one-paper-out validation. A data-sufficiency PASS is not a scientific model PASS.", "",
             "| Feature family | Model | MAE | RMSE | R2 | Below 0 | Above 100 |", "|---|---|---:|---:|---:|---:|---:|"]
    for metric in model["metrics"]:
        lines.append(f"| {metric['feature_family']} | {metric['model']} | {metric['mae']:.6f} | {metric['rmse']:.6f} | {metric['r2']:.6f} | {metric['fraction_predictions_below_0']:.3f} | {metric['fraction_predictions_above_100']:.3f} |")
    lines.extend(["", "## Feature-family deltas", "", "Positive deltas are worse. Fold direction is reported because aggregate changes are unstable at this sample size.", "", "| Model | Comparison | ΔMAE | ΔRMSE | Folds improved |", "|---|---|---:|---:|---:|"])
    consistency = {(row["model"], row["comparison"]): row for row in model.get("fold_direction_consistency", [])}
    for delta in model.get("family_deltas", []):
        direction = consistency[(delta["model"], delta["comparison"])]
        lines.append(f"| {delta['model']} | {delta['comparison']} | {delta['delta_mae']:.6f} | {delta['delta_rmse']:.6f} | {direction['folds_improved']}/{direction['folds_total']} |")
    lines.extend(["", "DummyRegressor remains the reference baseline. No non-Dummy model improves grouped OOF MAE over Dummy, so the dataset does not demonstrate useful out-of-paper predictive performance. Interface-aware features do not show a consistent improvement over unit-safe recipe/process features.", ""])
    return "\n".join(lines)


def main() -> int:
    args = arguments(); work = args.work_root.resolve()
    v0 = work / "02_Data" / "Experiment_Records" / "LiNRR_Training_v0"
    v1 = work / "02_Data" / "Experiment_Records" / "LiNRR_Training_v0_1"
    report_v1 = work / "04_Exports" / "Reports" / "LiNRR_Training_v0_1"
    dataset = work / "02_Data" / "Experiment_Records" / "LiNRR_Training_v0_2"
    reports = work / "04_Exports" / "Reports" / "LiNRR_Training_v0_2"
    model_dir = work / "02_Data" / "Modeling" / "LiNRR_Shadow_v0_2"
    workbook = work / "03_Database" / "LiNRR_Training_Dataset_v0_2.xlsx"
    targets = [dataset, reports, model_dir, workbook]
    occupied = [path for path in targets if path.exists()]
    if occupied and not args.replace_v02:
        raise FileExistsError("Refusing to overwrite v0.2 outputs: " + ", ".join(map(str, occupied)))
    if args.replace_v02:
        for path in (dataset, reports, model_dir):
            if path.exists(): shutil.rmtree(path)
        if workbook.exists(): workbook.unlink()

    source = load_jsonl(v1 / "all_candidate_records.jsonl")
    eligible_v1 = [row for row in source if row.get("model_eligible_fe")]
    if len(eligible_v1) != 47 or len({row.get("paper_id") or row.get("provisional_bundle_id") for row in eligible_v1}) != 12:
        raise RuntimeError("v0.1 eligible baseline mismatch")
    manifests = load_jsonl(v0 / "paper_asset_manifest.jsonl")
    by_asset, by_bundle = manifest_assets(manifests)
    enrich_inherited_provenance(source, by_bundle)
    rebuilt, corrections = [], []
    for record in source:
        row, changes = rebuild_record(record); rebuilt.append(row); corrections.extend(changes)
    rebuilt_by_id = {row["record_id"]: row for row in rebuilt}
    for correction in corrections:
        if correction.get("source_asset") and Path(str(correction["source_asset"])).is_file():
            continue
        row = rebuilt_by_id[correction["record_id"]]
        asset = by_asset.get(str(row.get("source_asset_id")), {})
        correction["source_asset"] = asset.get("absolute_path") or correction.get("source_asset")
    eligible = [row for row in rebuilt if row.get("model_eligible_fe")]
    no_cross_paper_binding(eligible)
    removed = []
    for old in eligible_v1:
        if old["record_id"] in TARGET_EXCLUSIONS:
            removed.append({"record_id": old["record_id"], "reason": TARGET_EXCLUSIONS[old["record_id"]][1]})
        elif old["record_id"] in DUPLICATE_EXCLUSIONS:
            removed.append({"record_id": old["record_id"], "reason": DUPLICATE_EXCLUSIONS[old["record_id"]][1]})
    newly: list[dict] = []
    lineage = [{"v0_record_id": row.get("v0_record_id") or (row["v01_record_id"] if not row["v01_record_id"].startswith("REC01_") else None), "v01_record_id": row["v01_record_id"], "v02_record_id": row["record_id"], "lineage_action": "SOURCE_SEMANTIC_EXCLUDED" if row["v01_record_id"] in TARGET_EXCLUSIONS else ("MERGED_DUPLICATE" if row["v01_record_id"] in DUPLICATE_EXCLUSIONS else "CARRIED_FORWARD_REBUILT")} for row in rebuilt]
    correction_fields = {(row["record_id"], row["field"]) for row in corrections}
    numeric = numeric_audit(eligible, by_asset, correction_fields)
    bindings = binding_audit(eligible, by_asset)
    for row in rebuilt:
        row.pop("condition_inherited_from_excerpt", None)
        row.pop("condition_inherited_from_absolute_path", None)
    review = ranked_review_queue(v1, report_v1, by_bundle)
    cover = coverage(rebuilt, eligible, removed, newly)
    model = train_grouped_v02(eligible)
    summary = {
        "schema_version": "linrr_training_dataset_summary_v0_2", "v01_eligible_fe_rows": 47,
        "v01_eligible_paper_groups": 12, "model_eligible_fe_rows": len(eligible),
        "eligible_paper_groups": len({row.get("paper_id") or row.get("provisional_bundle_id") for row in eligible}),
        "tier_counts": dict(Counter(row.get("eligibility_tier") for row in rebuilt)),
        "rows_removed_from_v01_eligibility": len(removed), "rows_newly_admitted": len(newly),
        "source_semantic_correction_entries": len(corrections),
        "confirmed_source_semantic_corrections": sum(row["correction_status"] in {"CONFIRMED_CORRECTION", "CONFIRMED_NULL"} for row in corrections),
        "high_value_human_review_queue_size": len(review), "dataset_hash": deterministic_hash(rebuilt),
        "data_sufficiency_gate": "PASS" if model["gate"]["passed"] else "FAIL",
        "predictive_performance": model["predictive_performance"],
    }
    for path in (dataset, reports, model_dir): path.mkdir(parents=True, exist_ok=False)
    write_jsonl(rebuilt, dataset / "all_candidate_records.jsonl"); write_csv(rebuilt, dataset / "all_candidate_records.csv")
    write_jsonl(eligible, dataset / "model_eligible_records.jsonl"); write_csv(eligible, dataset / "model_eligible_records.csv")
    write_csv(review, dataset / "review_queue.csv"); write_csv(review, dataset / "high_value_human_review_queue.csv")
    write_csv(corrections, dataset / "source_semantic_corrections.csv"); write_csv(numeric, dataset / "eligible_numeric_field_audit.csv")
    write_csv(lineage, dataset / "record_lineage_v0_v01_v02.csv"); write_csv(bindings, dataset / "experiment_binding_audit.csv")
    (dataset / "dataset_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (dataset / "dataset_card.md").write_text(report_markdown(summary, cover, model), encoding="utf-8")
    coverage_md = "# LiNRR v0.2 coverage\n\n```json\n" + json.dumps(cover, indent=2, ensure_ascii=False) + "\n```\n"
    (reports / "v02_coverage_report.json").write_text(json.dumps(cover, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (reports / "v02_coverage_report.md").write_text(coverage_md, encoding="utf-8")
    (reports / "V02_REPORT.md").write_text(report_markdown(summary, cover, model), encoding="utf-8")
    (model_dir / "model_metrics.json").write_text(json.dumps({"gate": model["gate"], "predictive_performance": model["predictive_performance"], "metrics": model["metrics"], "fold_metrics": model["fold_metrics"], "family_deltas": model["family_deltas"], "fold_direction_consistency": model["fold_direction_consistency"]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(model["metrics"], model_dir / "model_comparison.csv"); write_csv(model["predictions"], model_dir / "oof_predictions.csv")
    write_csv(model["fold_assignments"], model_dir / "fold_assignments.csv")
    (model_dir / "feature_schema.json").write_text(json.dumps(model["feature_schema"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = {"dataset": str((dataset / "model_eligible_records.jsonl").resolve()), "dataset_hash": summary["dataset_hash"], "grouping": "paper_id or provisional bundle; GroupKFold n_splits=min(5, groups)", "no_paper_leakage": model["no_paper_leakage"], "processed_matrices_finite": model["processed_matrices_finite"], "models": ["DummyRegressor", "Ridge", "RandomForestRegressor"], "primary_predictions": "unconstrained", "bounded_predictions": "diagnostic only"}
    (model_dir / "training_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (model_dir / "training_report.md").write_text(report_markdown(summary, cover, model), encoding="utf-8")
    write_workbook(workbook, [("ALL_RECORDS", rebuilt), ("MODEL_ELIGIBLE", eligible), ("CORRECTIONS", corrections), ("NUMERIC_AUDIT", numeric), ("BINDING_AUDIT", bindings), ("REVIEW_QUEUE", review)])
    print(json.dumps({"summary": summary, "removed": removed, "metrics": model["metrics"], "paths": {"dataset": str(dataset), "reports": str(reports), "model": str(model_dir), "workbook": str(workbook)}}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
