#!/usr/bin/env python
"""Build the provenance-first LiNRR Training Dataset v0 outside Git."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.training_ingest import (  # noqa: E402
    UNIFIED_FIELDS,
    apply_admission,
    build_battery_additive_prior,
    build_identity_map,
    deterministic_dataset_hash,
    extract_curated_records,
    find_master_workbook,
    ingest_legacy_candidates,
    inspect_legacy_mapping,
    load_paper_registry,
    mark_duplicates_and_conflicts,
    scan_bundle_roots,
    source_inventory,
    summarize_dataset,
    taxonomy,
    write_csv,
    write_jacs_method_map,
    write_jsonl,
    write_source_inventory_reports,
    write_workbook,
)


LEGACY_RELATIVE_PATHS = [
    "data/reports/experiment_triage_scores.enrr_round1_oa_20260712.jsonl",
    "data/reports/experiment_triage_scores.enrr_round1_oa_20260712.csv",
    "data/reports/experiment_triage_table.enrr_round1_oa_20260712.csv",
    "data/ledgers/enrr_round1_oa_20260712/performance_ledger.jsonl",
    "data/cleanroom/enrr_cleanroom_v015_20260718/semantics/semantic_spans.jsonl",
    "data/cleanroom/enrr_cleanroom_v015_20260718/links/evidence_links.jsonl",
    "data/gold/enrr_round1_oa_20260712/human_gold_claim_rights.jsonl",
    "data/human_audit/enrr_round1_oa_20260712/reviewed_audit_records.jsonl",
]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--work-root", type=Path, default=Path(r"F:\eNH3_Bench_Work"))
    result.add_argument("--repo-root", type=Path, default=ROOT)
    return result


def main() -> int:
    args = parser().parse_args()
    repo = args.repo_root.resolve()
    work = args.work_root.resolve()
    dataset_dir = work / "02_Data" / "Experiment_Records" / "LiNRR_Training_v0"
    reports_dir = work / "04_Exports" / "Reports" / "LiNRR_Training_v0"
    workbook_path = work / "03_Database" / "LiNRR_Training_Dataset_v0.xlsx"
    occupied = [path for path in (dataset_dir, reports_dir, workbook_path) if path.exists()]
    if occupied:
        raise FileExistsError("Refusing to overwrite LiNRR Training v0 outputs: " + ", ".join(map(str, occupied)))

    legacy_paths = [repo / relative for relative in LEGACY_RELATIVE_PATHS]
    inventory = source_inventory(legacy_paths)
    write_source_inventory_reports(inventory, reports_dir)

    roots = {
        "shaofeng_li_curated": work / "00_Inbox" / "Shaofeng_Li",
        "linrr_electrolyte_curated": work / "00_Inbox" / "LiNRR_Electrolytes",
        "battery_transfer_curated": work / "00_Inbox" / "Battery_Additives",
    }
    manifests = scan_bundle_roots(roots)
    registry = load_paper_registry(repo / "data" / "reports" / "oa_download_manifest.csv")
    identity_rows = build_identity_map(manifests, registry)

    legacy_path = legacy_paths[0]
    if not legacy_path.exists():
        legacy_records = []
        mapping_rows = []
    else:
        legacy_records = ingest_legacy_candidates(legacy_path)
        mapping_rows = inspect_legacy_mapping(legacy_path)
    curated_records = extract_curated_records(manifests)
    records = sorted([*legacy_records, *curated_records], key=lambda row: str(row["record_id"]))
    mark_duplicates_and_conflicts(records)
    admissions = [apply_admission(record) for record in records]
    battery_rows = build_battery_additive_prior(manifests)
    eligible = [record for record in records if record["model_eligible_fe"]]
    excluded = [record for record in records if record["eligibility_tier"] == "EXCLUDED"]
    review = [record for record in records if record["review_status"] in {"PENDING_REVIEW", "REVIEW_REQUIRED"} or record["eligibility_tier"] == "TIER_C"]

    dataset_dir.mkdir(parents=True, exist_ok=False)
    write_jsonl(records, dataset_dir / "all_candidate_records.jsonl")
    write_csv(records, dataset_dir / "all_candidate_records.csv", UNIFIED_FIELDS)
    write_jsonl(legacy_records, dataset_dir / "legacy_candidate_records.jsonl")
    write_csv(legacy_records, dataset_dir / "legacy_candidate_records.csv", UNIFIED_FIELDS)
    write_jsonl(eligible, dataset_dir / "model_eligible_records.jsonl")
    write_csv(eligible, dataset_dir / "model_eligible_records.csv", UNIFIED_FIELDS)
    write_csv(excluded, dataset_dir / "excluded_records.csv", UNIFIED_FIELDS)
    write_csv(review, dataset_dir / "review_queue.csv", UNIFIED_FIELDS)
    write_jsonl(manifests, dataset_dir / "paper_asset_manifest.jsonl")
    write_csv(identity_rows, dataset_dir / "paper_identity_map.csv", ["bundle_id", "source_group", "title", "doi", "existing_paper_id", "probable_existing_paper_id", "match_type", "match_confidence", "review_status"])
    write_csv(mapping_rows, dataset_dir / "legacy_triage_field_mapping.csv", ["legacy_field", "unified_field", "conversion", "admission_impact"])
    write_csv(battery_rows, dataset_dir / "battery_additive_prior.csv")
    electrolyte_rows = taxonomy(records, "lithium_salt", "lithium_salt") + taxonomy(records, "solvent", "solvent") + taxonomy(records, "proton_donor", "proton_donor")
    write_csv(electrolyte_rows, dataset_dir / "electrolyte_taxonomy.csv", ["taxonomy_type", "canonical_name", "record_count"])
    additive_rows = taxonomy(records, "additive", "linrr_additive")
    additive_rows += [{"taxonomy_type": "battery_prior", "canonical_name": name, "record_count": count} for name, count in sorted(Counter(row["canonical_name"] for row in battery_rows).items())]
    write_csv(additive_rows, dataset_dir / "additive_taxonomy.csv", ["taxonomy_type", "canonical_name", "record_count"])
    write_jsonl(admissions, dataset_dir / "training_admissions.jsonl")

    summary = summarize_dataset(records, manifests, battery_rows, len(legacy_records))
    summary["dataset_sha256"] = deterministic_dataset_hash(records)
    (dataset_dir / "dataset_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (dataset_dir / "dataset_card.md").write_text(_dataset_card(summary), encoding="utf-8")
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "coverage_report.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (reports_dir / "coverage_report.md").write_text(_coverage_report(summary), encoding="utf-8")

    jacs = next((m for m in manifests if (m.get("identity") or {}).get("doi") == "10.1021/jacs.6c08057"), None)
    if jacs is None:
        jacs = next((m for m in manifests if any("6c08057" in a["relative_path"].casefold() for a in m["assets"])), None)
    if jacs:
        write_jacs_method_map(jacs, reports_dir / "JACS_6C08057_METHOD_MAP.md")

    master = find_master_workbook(work, workbook_path)
    write_workbook(workbook_path, records, manifests, identity_rows, battery_rows, mapping_rows, summary, master)
    print(json.dumps({"dataset_dir": str(dataset_dir), "reports_dir": str(reports_dir), "workbook": str(workbook_path), "summary": summary}, indent=2, ensure_ascii=False))
    return 0


def _dataset_card(summary: dict[str, object]) -> str:
    return f"""# LiNRR Training Dataset v0

This is a provenance-first condition-record dataset, not a Gold evidence run. The 1,787 legacy experiment-triage rows enter only as candidates and receive the same scientific admission gates as curated sources. Paper-level review or Gold membership never grants row-level training authority.

The dataset contains {summary['condition_level_candidate_records']} candidate records and {summary['model_eligible_fe_rows']} FE-model-eligible rows. Unknown values remain null. Structured source locations and source hashes are retained. Reviews, perspectives, cited literature values, cross-paper evidence, incompatible NH3-rate units, and battery performance targets are not admitted as LiNRR labels.

Eligibility uses `TIER_A`, `TIER_B`, `TIER_C`, and `EXCLUDED`. The first literature shadow model may use A+B and, if large enough, A-only. It is not prospective proof, an autonomous design model, or a validated optimization engine.
"""


def _coverage_report(summary: dict[str, object]) -> str:
    tier = summary["tier_counts"]
    fields = summary["field_coverage"]
    lines = [
        "# LiNRR Training v0 coverage report", "",
        f"- Acquisition bundles: {summary['number_of_bundles']}",
        f"- Bundles with DOI: {summary['number_with_doi']}",
        f"- Exact DOI matches to Pxxxx: {summary['number_matched_existing_paper_id']}",
        f"- Legacy candidate rows: {summary['legacy_candidate_rows']}",
        f"- New curated candidate rows: {summary['new_curated_candidate_rows']}",
        f"- Battery descriptor-prior rows: {summary['battery_prior_rows']}",
        f"- Model-eligible FE rows: {summary['model_eligible_fe_rows']}",
        f"- Unique eligible paper groups: {summary['unique_paper_groups']}", "",
        "## Admission tiers", "",
    ]
    lines.extend(f"- {name}: {count}" for name, count in sorted(tier.items()))
    lines.extend(["", "## Field coverage", ""])
    lines.extend(f"- {name}: {count}" for name, count in sorted(fields.items()))
    lines.extend(["", "Unknown values were preserved as null. Counts describe deterministic candidate extraction and admission, not manual scientific verification.", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
