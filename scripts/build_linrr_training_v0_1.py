#!/usr/bin/env python
"""Build LiNRR Training Dataset v0.1 rescue and review artifacts outside Git."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.linrr_predictor import secondary_target_assessment, train_grouped_models, write_training_outputs  # noqa: E402
from enh3bench.training_ingest import deterministic_dataset_hash, write_csv, write_jsonl  # noqa: E402
from enh3bench.training_rescue import (  # noqa: E402
    RESCUE_QUEUE_FIELDS,
    V01_FIELDS,
    build_rescue_queue,
    classify_source_conflicts,
    copy_for_v01,
    extract_structured_experiments,
    inherit_same_paper_series,
    load_records_csv,
    recalculate_v01,
    rescue_priority,
    resolve_duplicates,
    validate_no_cross_paper_inheritance,
    write_review_packets,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--work-root", type=Path, default=Path(r"F:\eNH3_Bench_Work"))
    result.add_argument("--repo-root", type=Path, default=ROOT)
    result.add_argument("--replace-partial", action="store_true", help="Replace only partial v0.1 dataset/report files; never overwrite a workbook or model directory.")
    result.add_argument("--replace-completed-v01", action="store_true", help="Explicitly replace only v0.1 workbook/model artifacts after an interrupted or corrected build.")
    return result


def _load_manifests(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_workbook(path: Path, records: list[dict], rescue_queue: list[dict], auto: list[dict], human: list[dict], duplicate: list[dict], conflicts: list[dict], summary: dict) -> None:
    from openpyxl import Workbook
    workbook = Workbook()
    workbook.remove(workbook.active)
    sheets = [
        ("README", [{"key": "dataset", "value": "LiNRR Training Dataset v0.1"}, {"key": "boundary", "value": "Deterministic rescue only; human suggestions are not automatically applied."}]),
        ("ALL_RECORDS", records),
        ("MODEL_ELIGIBLE", [row for row in records if row.get("model_eligible_fe")]),
        ("TIER_C_RESCUE", rescue_queue),
        ("AUTO_RESOLVED", auto),
        ("HUMAN_REVIEW", human),
        ("DUPLICATES", duplicate),
        ("SOURCE_CONFLICTS", conflicts),
        ("DATASET_SUMMARY", [{"metric": key, "value": json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value} for key, value in summary.items()]),
    ]
    for title, rows in sheets:
        sheet = workbook.create_sheet(title)
        fields = list(rows[0]) if rows else ["EMPTY"]
        sheet.append(fields)
        for row in rows:
            values = []
            for field in fields:
                value = row.get(field)
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, str) and len(value) > 32767:
                    value = value[:32730] + " [TRUNCATED]"
                if isinstance(value, str):
                    value = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "�", value)
                values.append(value)
            sheet.append(values)
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def _summary(records: list[dict], starting: dict, structured: list[dict], human: list[dict]) -> dict:
    eligible = [row for row in records if row.get("model_eligible_fe")]
    groups = {row.get("paper_id") or row.get("provisional_bundle_id") or row.get("source_bundle_id") for row in eligible}
    return {
        "schema_version": "linrr_training_dataset_summary_v0_1",
        "starting_eligible_fe_rows": starting["eligible_rows"],
        "starting_eligible_paper_groups": starting["eligible_groups"],
        "starting_tier_counts": starting["tiers"],
        "tier_c_reviewed": starting["tier_c"],
        "auto_resolved_rows": len(structured),
        "human_review_required": len(human),
        "condition_level_candidate_records": len(records),
        "tier_counts": dict(sorted(Counter(row.get("eligibility_tier") for row in records).items())),
        "model_eligible_fe_rows": len(eligible),
        "unique_paper_groups": len(groups),
        "modeling_gate": "PASS" if len(eligible) >= 25 and len(groups) >= 5 else "FAIL",
        "dataset_sha256": deterministic_dataset_hash(records),
    }


def _reports(summary: dict, structured: list[dict], human: list[dict], conflicts: list[dict], duplicate: list[dict], manifests: dict[str, dict]) -> tuple[str, str, dict]:
    by_paper = Counter(row.get("paper_id") or row.get("source_bundle_id") for row in structured)
    unresolved_conflicts = sum(row["classification"] == "TRUE_UNRESOLVED_CONFLICT" for row in conflicts)
    resolved_conflicts = len(conflicts) - unresolved_conflicts
    promoted_a = sum(row.get("eligibility_tier") == "TIER_A" for row in structured)
    promoted_b = sum(row.get("eligibility_tier") == "TIER_B" for row in structured)
    missing = Counter(failure for row in human for failure in (row.get("missing_required_fields") or []))
    largest = []
    for group, count in by_paper.most_common():
        manifest = next((item for item in manifests.values() if item.get("identity_match", {}).get("existing_paper_id") == group or item.get("bundle_id") == group), {})
        bundle_title = Path(str(manifest.get("bundle_path") or "")).name
        largest.append({"paper_group": group, "title": bundle_title or (manifest.get("identity") or {}).get("title"), "auto_resolved_rows": count})
    coverage = {**summary, "most_recoverable_papers": largest, "remaining_missing_admission_fields_in_auto_resolved": dict(missing)}
    report = f"""# LiNRR Training Dataset v0.1 rescue report

- Starting eligible rows: 16
- Starting eligible groups: 12
- Tier-C reviewed: {summary['tier_c_reviewed']}
- Auto-resolved rows: {summary['auto_resolved_rows']}
- Still human-review-required: {summary['human_review_required']}
- Records promoted to Tier B: {promoted_b}
- Records promoted to Tier A: {promoted_a}
- Duplicate rows merged: {len(duplicate)}
- Source conflicts resolved: {resolved_conflicts}
- Source conflicts unresolved: {unresolved_conflicts}
- Final eligible FE rows: {summary['model_eligible_fe_rows']}
- Final eligible paper groups: {summary['unique_paper_groups']}
- Modeling gate: {summary['modeling_gate']}

## Most recoverable papers

""" + "\n".join(f"- {row['paper_group']}: {row['auto_resolved_rows']} rows - {row['title'] or ''}" for row in largest) + "\n\n## Most important remaining admission failures\n\n" + "\n".join(f"- {field}: {count}" for field, count in missing.most_common()) + "\n"
    coverage_md = "# LiNRR Training v0.1 coverage\n\n" + "\n".join(f"- {key}: {value}" for key, value in summary.items() if key != "dataset_sha256") + "\n"
    card = f"""# LiNRR Training Dataset v0.1

This independent v0.1 profile preserves v0 and audit schema 0.13 behavior. It adds deterministic row-wise table extraction and same-paper-series condition inheritance with both direct and inherited locators. Human-review suggestions never grant automatic training admission.

The dataset contains {summary['model_eligible_fe_rows']} model-eligible FE rows across {summary['unique_paper_groups']} paper groups. Battery-additive assets remain descriptor priors and never supply FE_NH3 labels.
"""
    return report, coverage_md, {"coverage": coverage, "card": card}


def main() -> int:
    args = parser().parse_args()
    work = args.work_root.resolve()
    source_dir = work / "02_Data" / "Experiment_Records" / "LiNRR_Training_v0"
    dataset_dir = work / "02_Data" / "Experiment_Records" / "LiNRR_Training_v0_1"
    report_dir = work / "04_Exports" / "Reports" / "LiNRR_Training_v0_1"
    workbook_path = work / "03_Database" / "LiNRR_Training_Dataset_v0_1.xlsx"
    model_dir = work / "02_Data" / "Modeling" / "LiNRR_Shadow_v0_1"
    protected_occupied = [path for path in (workbook_path, model_dir) if path.exists()]
    if protected_occupied and not args.replace_completed_v01:
        raise FileExistsError("Refusing to overwrite completed v0.1 workbook/model outputs: " + ", ".join(map(str, protected_occupied)))
    occupied = [path for path in (dataset_dir, report_dir) if path.exists()]
    if args.replace_partial:
        occupied = []
    if occupied:
        raise FileExistsError("Refusing to overwrite v0.1 runtime outputs: " + ", ".join(map(str, occupied)))

    source_records = load_records_csv(source_dir / "all_candidate_records.csv")
    eligible_v0 = [row for row in source_records if row.get("model_eligible_fe")]
    tier_c_v0 = [row for row in source_records if row.get("eligibility_tier") == "TIER_C"]
    starting_groups = {row.get("paper_id") or row.get("provisional_bundle_id") or row.get("source_bundle_id") for row in eligible_v0}
    starting = {"eligible_rows": len(eligible_v0), "eligible_groups": len(starting_groups), "tier_c": len(tier_c_v0), "tiers": dict(Counter(row.get("eligibility_tier") for row in source_records))}
    required = {"eligible_rows": 16, "eligible_groups": 12, "tier_c": 119, "tiers": {"TIER_B": 16, "TIER_C": 119, "EXCLUDED": 1831}}
    if starting != required:
        raise RuntimeError(f"v0 scientific baseline mismatch: {starting!r}")

    manifests_list = _load_manifests(source_dir / "paper_asset_manifest.jsonl")
    manifests = {item["bundle_id"]: item for item in manifests_list}
    tier_c_bundles = {str(row.get("source_bundle_id")) for row in tier_c_v0 if row.get("source_group") != "legacy_oa"}
    structured = []
    for bundle_id in tier_c_bundles:
        manifest = manifests.get(bundle_id)
        if not manifest:
            continue
        for record in extract_structured_experiments(manifest):
            inherit_same_paper_series(record, manifest)
            recalculate_v01(record)
            if record.get("model_eligible_fe"):
                structured.append(record)

    records = copy_for_v01(source_records)
    for row in records:
        if row.get("eligibility_tier") == "TIER_C":
            row["human_review_required"] = True
            row["review_status"] = "HUMAN_REVIEW_REQUIRED"
    records.extend(structured)
    validate_no_cross_paper_inheritance(structured, manifests)
    duplicate = resolve_duplicates(records)
    conflicts = classify_source_conflicts(records)
    eligible = [row for row in records if row.get("model_eligible_fe") and row.get("review_status") != "MERGED_DUPLICATE"]
    human = [row for row in records if row.get("human_review_required")]
    rescue_queue = build_rescue_queue(tier_c_v0, manifests)
    priorities = [{"record_id": row.get("record_id"), "paper_id": row.get("paper_id"), "source_group": row.get("source_group"), "priority": rescue_priority(row), "admission_failures": row.get("missing_required_fields"), "ambiguity_flags": row.get("ambiguity_flags")} for row in tier_c_v0]

    summary = _summary(records, starting, structured, human)
    dataset_dir.mkdir(parents=True, exist_ok=args.replace_partial)
    report_dir.mkdir(parents=True, exist_ok=args.replace_partial)
    write_jsonl(records, dataset_dir / "all_candidate_records.jsonl")
    write_csv(records, dataset_dir / "all_candidate_records.csv", V01_FIELDS)
    write_jsonl(eligible, dataset_dir / "model_eligible_records.jsonl")
    write_csv(eligible, dataset_dir / "model_eligible_records.csv", V01_FIELDS)
    write_csv(rescue_queue, dataset_dir / "tier_c_rescue_queue.csv", RESCUE_QUEUE_FIELDS)
    write_csv(structured, dataset_dir / "auto_resolved_records.csv", V01_FIELDS)
    write_csv(human, dataset_dir / "human_review_required.csv", V01_FIELDS)
    write_csv(duplicate, dataset_dir / "duplicate_resolution.csv")
    write_csv(conflicts, dataset_dir / "source_conflict_resolution.csv")
    write_csv(human, dataset_dir / "review_queue.csv", V01_FIELDS)
    (dataset_dir / "dataset_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(rescue_queue, report_dir / "tier_c_rescue_queue.csv", RESCUE_QUEUE_FIELDS)
    write_csv(priorities, report_dir / "rescue_priority.csv")
    write_review_packets(tier_c_v0, manifests, report_dir / "review_packets")
    report, coverage_md, extra = _reports(summary, structured, human, conflicts, duplicate, manifests)
    (dataset_dir / "dataset_card.md").write_text(extra["card"], encoding="utf-8")
    (dataset_dir / "coverage_report.md").write_text(coverage_md, encoding="utf-8")
    (dataset_dir / "coverage_report.json").write_text(json.dumps(extra["coverage"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (report_dir / "coverage_report.md").write_text(coverage_md, encoding="utf-8")
    (report_dir / "coverage_report.json").write_text(json.dumps(extra["coverage"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (report_dir / "RESCUE_REPORT.md").write_text(report, encoding="utf-8")
    _write_workbook(workbook_path, records, rescue_queue, structured, human, duplicate, conflicts, summary)

    result = train_grouped_models(eligible)
    result["secondary_target_gate"] = secondary_target_assessment(eligible, result["gate"]["passed"])
    write_training_outputs(result, model_dir, dataset_dir / "model_eligible_records.jsonl", args.repo_root, overwrite=args.replace_completed_v01)
    print(json.dumps({"summary": summary, "model_metrics": result["metrics"], "dataset_dir": str(dataset_dir), "report_dir": str(report_dir), "workbook": str(workbook_path), "model_dir": str(model_dir)}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
