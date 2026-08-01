from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from html import escape
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.audit_schema import is_reviewed_record  # noqa: E402
from enh3bench.cleanroom_schema import read_jsonl, write_json, write_jsonl  # noqa: E402


AUDIT_SCHEMA_VERSION = "0.18-asset-audit.1"
DEFAULT_RUNTIME_ROOT = Path(r"F:\eNH3_Bench_API\v018")
DEFAULT_PILOT_MANIFEST = Path("data/manifests/v018_a1_pilot_corpus.json")
STABLE_PAPER_ID_RE = re.compile(r"^(P\d{4})(?:_|$)")
SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")
VALID_MAIN_DOCUMENT_STATUSES = {"valid_pdf", "existing_valid_pdf"}

SOURCE_PATHS = {
    "oa_manifest": Path("data/reports/oa_download_manifest.jsonl"),
    "cleanroom_validation": Path(
        "data/cleanroom/enrr_cleanroom_v015_20260718/reports/cleanroom_validation_summary.json"
    ),
    "cleanroom_documents": Path(
        "data/cleanroom/enrr_cleanroom_v015_20260718/documents/document_ledger.jsonl"
    ),
    "cleanroom_spans": Path(
        "data/cleanroom/enrr_cleanroom_v015_20260718/semantics/semantic_spans.jsonl"
    ),
    "cleanroom_papers": Path(
        "data/cleanroom/enrr_cleanroom_v015_20260718/papers/paper_records.jsonl"
    ),
    "evidence_links": Path(
        "data/cleanroom/enrr_cleanroom_v015_20260718/links/evidence_links.jsonl"
    ),
    "experiment_records": Path("data/reports/experiment_triage_scores.enrr_round1_oa_20260712.jsonl"),
    "scientific_claims": Path("data/drafts/draft_evidence.enrr_round1_oa_20260712.jsonl"),
    "calibration_validation": Path(
        "data/calibration/enrr_calibration_v016_round1_20260719/reports/validation_summary.json"
    ),
    "calibration_span": Path(
        "data/calibration/enrr_calibration_v016_round1_20260719/sampling/span_sampling_frame.jsonl"
    ),
    "calibration_paper": Path(
        "data/calibration/enrr_calibration_v016_round1_20260719/sampling/paper_sampling_frame.jsonl"
    ),
    "calibration_document": Path(
        "data/calibration/enrr_calibration_v016_round1_20260719/sampling/document_sampling_frame.jsonl"
    ),
    "calibration_link": Path(
        "data/calibration/enrr_calibration_v016_round1_20260719/sampling/link_sampling_frame.jsonl"
    ),
    "selective_validation": Path(
        "data/selective_eval/enrr_selective_eval_v016_round1_20260720/reports/validation_summary.json"
    ),
    "selective_cases": Path(
        "data/selective_eval/enrr_selective_eval_v016_round1_20260720/cases/e2e_case_frame.jsonl"
    ),
    "selective_anchors": Path(
        "data/selective_eval/enrr_selective_eval_v016_round1_20260720/anchors/selected_anchor_frame.jsonl"
    ),
    "gold": Path("data/gold/enrr_round1_oa_20260712/human_gold_claim_rights.jsonl"),
    "human_review": Path("data/human_audit/enrr_round1_oa_20260712/reviewed_audit_records.jsonl"),
}

INVENTORY_FIELDS = (
    "paper_id",
    "reaction_family",
    "document_genre",
    "paper_admissibility_status",
    "main_document_available",
    "supplementary_document_available",
    "cleanroom_available",
    "source_span_count",
    "experiment_record_count",
    "claim_count",
    "evidence_link_count",
    "calibration_membership",
    "selective_eval_membership",
    "gold_membership",
    "human_review_membership",
    "development_case_types",
    "development_answerability_statuses",
    "validation_gate_counts",
    "reactor_process_span_count",
    "known_source_locations",
    "warnings",
)

PILOT_RULES: tuple[
    tuple[str, Callable[[dict[str, Any]], bool], Callable[[dict[str, Any]], int]], ...
] = (
    (
        "LiNRR",
        lambda row: row["reaction_family"] == "LiNRR",
        lambda row: 0,
    ),
    (
        "direct_eNRR",
        lambda row: row["reaction_family"] == "eNRR" and row["document_genre"] == "primary_research",
        lambda row: 0,
    ),
    (
        "ammonia_quantification",
        lambda row: (
            "ammonia_quantification_assessment" in row["development_case_types"]
            or row["validation_gate_counts"].get("ammonia_quantification", 0) > 0
        ),
        lambda row: (
            1000 * ("ammonia_quantification_assessment" in row["development_case_types"])
            + 2000 * (row["validation_gate_counts"].get("ammonia_quantification", 0) > 0)
        ),
    ),
    (
        "isotope_or_contamination_validation",
        lambda row: (
            "validation_reliability_assessment" in row["development_case_types"]
            or row["validation_gate_counts"].get("isotope_15N", 0) > 0
            or row["validation_gate_counts"].get("contamination_control", 0) > 0
        ),
        lambda row: (
            1000 * ("validation_reliability_assessment" in row["development_case_types"])
            + 2000
            * (
                row["validation_gate_counts"].get("isotope_15N", 0) > 0
                or row["validation_gate_counts"].get("contamination_control", 0) > 0
            )
        ),
    ),
    (
        "reactor_or_process_extraction",
        lambda row: (
            "reactor_process_extraction" in row["development_case_types"]
            or row["reactor_process_span_count"] > 0
        ),
        lambda row: (
            1000 * ("reactor_process_extraction" in row["development_case_types"])
            + 2000 * (row["reactor_process_span_count"] > 0)
        ),
    ),
    (
        "claim_ownership",
        lambda row: "claim_ownership_assessment" in row["development_case_types"],
        lambda row: 1000,
    ),
    (
        "insufficient_evidence",
        lambda row: "insufficient_evidence" in row["development_answerability_statuses"],
        lambda row: 1000,
    ),
    (
        "review_perspective_or_non_target_negative",
        lambda row: (
            row["document_genre"] in {"review", "perspective"}
            or row["reaction_family"] in {"NO2RR", "NORR", "mixed", "unclear"}
        ),
        lambda row: 1000 * (row["document_genre"] in {"review", "perspective"}),
    ),
)


@dataclass(frozen=True)
class AuditSources:
    oa_manifest: list[dict[str, Any]]
    cleanroom_documents: list[dict[str, Any]]
    cleanroom_spans: list[dict[str, Any]]
    cleanroom_papers: list[dict[str, Any]]
    experiment_records: list[dict[str, Any]]
    scientific_claims: list[dict[str, Any]]
    evidence_links: list[dict[str, Any]]
    calibration_records: list[dict[str, Any]]
    selective_cases: list[dict[str, Any]]
    selective_anchors: list[dict[str, Any]]
    gold_records: list[dict[str, Any]]
    human_review_records: list[dict[str, Any]]
    supplementary_documents: list[dict[str, Any]]


def load_repository_assets(repository_root: str | Path) -> AuditSources:
    root = Path(repository_root)
    _require_validation_pass(root, "cleanroom_validation")
    _require_validation_pass(root, "calibration_validation")
    _require_validation_pass(root, "selective_validation")
    calibration_records: list[dict[str, Any]] = []
    for label in ("calibration_span", "calibration_paper", "calibration_document", "calibration_link"):
        calibration_records.extend(_read_required_jsonl(root / SOURCE_PATHS[label]))
    return AuditSources(
        oa_manifest=_read_required_jsonl(root / SOURCE_PATHS["oa_manifest"]),
        cleanroom_documents=_read_required_jsonl(root / SOURCE_PATHS["cleanroom_documents"]),
        cleanroom_spans=_read_required_jsonl(root / SOURCE_PATHS["cleanroom_spans"]),
        cleanroom_papers=_read_required_jsonl(root / SOURCE_PATHS["cleanroom_papers"]),
        experiment_records=_read_required_jsonl(root / SOURCE_PATHS["experiment_records"]),
        scientific_claims=_read_required_jsonl(root / SOURCE_PATHS["scientific_claims"]),
        evidence_links=_read_required_jsonl(root / SOURCE_PATHS["evidence_links"]),
        calibration_records=calibration_records,
        selective_cases=_read_required_jsonl(root / SOURCE_PATHS["selective_cases"]),
        selective_anchors=_read_required_jsonl(root / SOURCE_PATHS["selective_anchors"]),
        gold_records=_read_required_jsonl(root / SOURCE_PATHS["gold"]),
        human_review_records=_read_required_jsonl(root / SOURCE_PATHS["human_review"]),
        supplementary_documents=[],
    )


def build_inventory(sources: AuditSources) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    oa_by_paper = _unique_paper_index(sources.oa_manifest, "OA manifest", require_exact_stable_id=True)
    document_by_paper = _unique_paper_index(sources.cleanroom_documents, "clean-room document ledger")
    paper_by_paper = _unique_paper_index(sources.cleanroom_papers, "clean-room paper records")
    supplementary_by_paper = _group_by_paper(sources.supplementary_documents)
    span_counts = _counts_by_paper(sources.cleanroom_spans)
    experiment_counts = _counts_by_paper(sources.experiment_records)
    claim_counts = _counts_by_paper(sources.scientific_claims)
    evidence_link_counts = _counts_by_paper(sources.evidence_links)
    calibration_ids = set(_group_by_paper(sources.calibration_records))
    gold_ids = set(_group_by_paper(sources.gold_records))
    reviewed_ids = {
        stable_paper_id(record.get("paper_id"))
        for record in sources.human_review_records
        if is_reviewed_record(record)
    }

    development: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"case_types": set(), "answerability": set()}
    )
    selective_development_ids: set[str] = set()
    excluded_holdout_ids: set[str] = set()
    for record in [*sources.selective_cases, *sources.selective_anchors]:
        paper_id = stable_paper_id(record.get("paper_id"))
        if record.get("split") != "development":
            excluded_holdout_ids.add(paper_id)
            continue
        selective_development_ids.add(paper_id)
        case_type = str(record.get("case_type") or "").strip()
        answerability = str(record.get("answerability_status") or "").strip()
        if case_type:
            development[paper_id]["case_types"].add(case_type)
        if answerability:
            development[paper_id]["answerability"].add(answerability)

    inventories: list[dict[str, Any]] = []
    for paper_id in sorted(oa_by_paper):
        oa_record = oa_by_paper[paper_id]
        document = document_by_paper.get(paper_id)
        paper = paper_by_paper.get(paper_id)
        main_available = _main_document_available(oa_record)
        supplementary_available = any(
            str(record.get("availability_status") or "") == "available"
            for record in supplementary_by_paper.get(paper_id, [])
        )
        cleanroom_available = document is not None
        reaction_family = str((document or {}).get("document_reaction_family") or "not_reported")
        document_genre = str((document or {}).get("document_genre") or "not_reported")
        paper_status = str((paper or {}).get("paper_admissibility_status") or "not_reported")
        gate_counts = {
            str(key): int(value)
            for key, value in sorted(((paper or {}).get("validation_gate_summary") or {}).items())
        }
        reactor_process_count = sum(
            int(value) for value in ((paper or {}).get("reactor_process_summary") or {}).values()
        )
        known_locations = {SOURCE_PATHS["oa_manifest"].as_posix()}
        if main_available:
            known_locations.add(_safe_relative_location(oa_record.get("relative_path")))
        if document is not None:
            known_locations.add(_safe_relative_location(document.get("document_ref")))
            known_locations.add(SOURCE_PATHS["cleanroom_documents"].as_posix())
        if span_counts[paper_id]:
            known_locations.add(SOURCE_PATHS["cleanroom_spans"].as_posix())
        if experiment_counts[paper_id]:
            known_locations.add(SOURCE_PATHS["experiment_records"].as_posix())
        if claim_counts[paper_id]:
            known_locations.add(SOURCE_PATHS["scientific_claims"].as_posix())
        if evidence_link_counts[paper_id]:
            known_locations.add(SOURCE_PATHS["evidence_links"].as_posix())
        if paper_id in calibration_ids:
            known_locations.add(SOURCE_PATHS["calibration_span"].as_posix())
        if paper_id in selective_development_ids:
            known_locations.add(SOURCE_PATHS["selective_cases"].as_posix())
        if paper_id in gold_ids:
            known_locations.add(SOURCE_PATHS["gold"].as_posix())
        if paper_id in reviewed_ids:
            known_locations.add(SOURCE_PATHS["human_review"].as_posix())

        warnings: list[str] = []
        if not main_available:
            warnings.append("main_document_not_available")
        if not sources.supplementary_documents:
            warnings.append("supplementary_asset_manifest_not_available")
        elif not supplementary_available:
            warnings.append("supplementary_document_not_available")
        if not cleanroom_available:
            warnings.append("cleanroom_not_available")
        if main_available != cleanroom_available:
            warnings.append("main_document_cleanroom_coverage_mismatch")
        if cleanroom_available and span_counts[paper_id] == 0:
            warnings.append("cleanroom_document_has_no_source_spans")
        if cleanroom_available and experiment_counts[paper_id] == 0:
            warnings.append("no_experiment_level_records")
        if cleanroom_available and claim_counts[paper_id] == 0:
            warnings.append("no_scientific_claim_records")
        if cleanroom_available and evidence_link_counts[paper_id] == 0:
            warnings.append("no_evidence_links")
        if bool((document or {}).get("document_reaction_family_conflict")):
            warnings.append("reaction_family_conflict")
        if reaction_family == "not_reported":
            warnings.append("reaction_family_not_reported")

        row = {
            "paper_id": paper_id,
            "reaction_family": reaction_family,
            "document_genre": document_genre,
            "paper_admissibility_status": paper_status,
            "main_document_available": main_available,
            "supplementary_document_available": supplementary_available,
            "cleanroom_available": cleanroom_available,
            "source_span_count": span_counts[paper_id],
            "experiment_record_count": experiment_counts[paper_id],
            "claim_count": claim_counts[paper_id],
            "evidence_link_count": evidence_link_counts[paper_id],
            "calibration_membership": paper_id in calibration_ids,
            "selective_eval_membership": paper_id in selective_development_ids,
            "gold_membership": paper_id in gold_ids,
            "human_review_membership": paper_id in reviewed_ids,
            "development_case_types": sorted(development[paper_id]["case_types"]),
            "development_answerability_statuses": sorted(development[paper_id]["answerability"]),
            "validation_gate_counts": gate_counts,
            "reactor_process_span_count": reactor_process_count,
            "known_source_locations": sorted(location for location in known_locations if location),
            "warnings": sorted(warnings),
        }
        if tuple(row) != INVENTORY_FIELDS:
            raise AssertionError("inventory field order changed")
        inventories.append(row)

    represented_ids = set(oa_by_paper)
    orphan_ids = sorted(
        (
            set(document_by_paper)
            | set(paper_by_paper)
            | set(span_counts)
            | set(experiment_counts)
            | set(claim_counts)
            | set(evidence_link_counts)
            | calibration_ids
            | selective_development_ids
            | gold_ids
            | reviewed_ids
        )
        - represented_ids
    )
    context = {
        "excluded_holdout_paper_ids": excluded_holdout_ids,
        "excluded_holdout_paper_count": len(excluded_holdout_ids),
        "orphan_paper_ids": orphan_ids,
        "supplementary_manifest_available": bool(sources.supplementary_documents),
    }
    return inventories, context


def select_pilot_corpus(
    inventory: Iterable[dict[str, Any]],
    *,
    excluded_paper_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    excluded = set(excluded_paper_ids or set())
    records = [dict(record) for record in inventory]
    eligible = [
        record
        for record in records
        if record["paper_id"] not in excluded
        and record["main_document_available"]
        and record["cleanroom_available"]
        and record["source_span_count"] > 0
        and record["experiment_record_count"] > 0
        and record["claim_count"] > 0
    ]
    if len(eligible) < 12:
        raise ValueError(f"fewer than 12 eligible development/public papers: {len(eligible)}")

    selected: list[dict[str, Any]] = []
    selection_modes: dict[str, str] = {}
    for lane, predicate, boost in PILOT_RULES:
        candidates = [record for record in eligible if record not in selected and predicate(record)]
        if not candidates:
            raise ValueError(f"pilot coverage lane has no eligible paper: {lane}")
        chosen = _ranked(candidates, boost)[0]
        selected.append(chosen)
        selection_modes[chosen["paper_id"]] = f"coverage_lane:{lane}"

    covered_families = {record["reaction_family"] for record in selected}
    for family in ("LiNRR", "eNRR", "NO3RR", "NO2RR", "NORR", "mixed", "unclear"):
        if len(selected) >= 12:
            break
        if family in covered_families:
            continue
        candidates = [
            record
            for record in eligible
            if record not in selected and record["reaction_family"] == family
        ]
        if candidates:
            chosen = _ranked(candidates)[0]
            selected.append(chosen)
            covered_families.add(family)
            selection_modes[chosen["paper_id"]] = f"reaction_family_diversity:{family}"

    while len(selected) < 12:
        candidates = [record for record in eligible if record not in selected]
        chosen = _ranked(candidates)[0]
        selected.append(chosen)
        selection_modes[chosen["paper_id"]] = "deterministic_fill"
    if len(selected) != 12 or len({record["paper_id"] for record in selected}) != 12:
        raise AssertionError("pilot selection must contain exactly 12 unique papers")
    if any(record["paper_id"] in excluded for record in selected):
        raise AssertionError("pilot selection contains an excluded holdout paper")
    return selected, selection_modes


def expected_pilot_manifest(
    selected: Iterable[dict[str, Any]],
    selection_modes: dict[str, str],
) -> dict[str, Any]:
    papers: list[dict[str, Any]] = []
    for record in selected:
        reasons = [selection_modes[record["paper_id"]], "deterministic_asset_rank"]
        reasons.extend(f"development_case:{value}" for value in record["development_case_types"])
        reasons.extend(
            f"development_answerability:{value}"
            for value in record["development_answerability_statuses"]
        )
        categories = ["main_document", "cleanroom_source_spans", "experiment_records", "scientific_claims"]
        if record["evidence_link_count"]:
            categories.append("evidence_links")
        if record["calibration_membership"]:
            categories.append("calibration")
        if record["selective_eval_membership"]:
            categories.append("selective_eval_development")
        if record["gold_membership"]:
            categories.append("gold")
        if record["human_review_membership"]:
            categories.append("human_review")
        papers.append(
            {
                "paper_id": record["paper_id"],
                "selection_reasons": sorted(set(reasons)),
                "reaction_family_coverage": [record["reaction_family"]],
                "expected_asset_categories": sorted(categories),
            }
        )
    return {"papers": papers}


def validate_pilot_manifest(manifest: Any, expected: dict[str, Any]) -> None:
    if not isinstance(manifest, dict) or set(manifest) != {"papers"}:
        raise ValueError("pilot manifest may contain only the papers collection")
    papers = manifest.get("papers")
    if not isinstance(papers, list) or len(papers) != 12:
        raise ValueError("pilot manifest must contain exactly 12 papers")
    allowed = {"paper_id", "selection_reasons", "reaction_family_coverage", "expected_asset_categories"}
    for index, paper in enumerate(papers):
        if not isinstance(paper, dict) or set(paper) != allowed:
            raise ValueError(f"pilot manifest paper {index} has fields outside the frozen allowlist")
        if not re.fullmatch(r"P\d{4}", str(paper.get("paper_id") or "")):
            raise ValueError(f"pilot manifest paper {index} has an unstable paper ID")
        for field in ("selection_reasons", "reaction_family_coverage", "expected_asset_categories"):
            values = paper.get(field)
            if not isinstance(values, list) or not values or any(not isinstance(value, str) for value in values):
                raise ValueError(f"pilot manifest paper {index} has invalid {field}")
    if manifest != expected:
        raise ValueError("pilot manifest does not match deterministic selection")


def build_summary(
    inventory: list[dict[str, Any]],
    context: dict[str, Any],
    selected: list[dict[str, Any]],
) -> dict[str, Any]:
    total = len(inventory)

    def coverage(field: str) -> dict[str, Any]:
        count = sum(bool(record[field]) for record in inventory)
        return {"count": count, "rate": round(count / total, 6) if total else 0.0}

    warning_counts = Counter(warning for record in inventory for warning in record["warnings"])
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "unique_paper_count": total,
        "coverage": {
            "main_document": coverage("main_document_available"),
            "supplementary_document": coverage("supplementary_document_available"),
            "cleanroom_source_spans": coverage("cleanroom_available"),
            "experiment_records": {
                "count": sum(record["experiment_record_count"] > 0 for record in inventory),
                "rate": round(sum(record["experiment_record_count"] > 0 for record in inventory) / total, 6),
                "record_count": sum(record["experiment_record_count"] for record in inventory),
            },
            "scientific_claims": {
                "count": sum(record["claim_count"] > 0 for record in inventory),
                "rate": round(sum(record["claim_count"] > 0 for record in inventory) / total, 6),
                "record_count": sum(record["claim_count"] for record in inventory),
            },
            "evidence_links": {
                "count": sum(record["evidence_link_count"] > 0 for record in inventory),
                "rate": round(sum(record["evidence_link_count"] > 0 for record in inventory) / total, 6),
                "record_count": sum(record["evidence_link_count"] for record in inventory),
            },
            "calibration": coverage("calibration_membership"),
            "selective_eval_development": coverage("selective_eval_membership"),
            "gold": coverage("gold_membership"),
            "human_review": coverage("human_review_membership"),
        },
        "source_span_count": sum(record["source_span_count"] for record in inventory),
        "selected_pilot_paper_ids": [record["paper_id"] for record in selected],
        "warning_counts": dict(sorted(warning_counts.items())),
        "unresolved_inconsistencies": {
            "orphan_paper_id_count": len(context["orphan_paper_ids"]),
            "orphan_paper_ids": context["orphan_paper_ids"],
            "supplementary_manifest_available": context["supplementary_manifest_available"],
            "main_document_cleanroom_mismatch_count": warning_counts[
                "main_document_cleanroom_coverage_mismatch"
            ],
        },
        "safety_counters": {
            "api_calls": 0,
            "network_calls": 0,
            "credential_reads": 0,
            "model_calls": 0,
            "holdout_papers_included": 0,
            "holdout_papers_excluded": context["excluded_holdout_paper_count"],
        },
        "source_validation": {
            "cleanroom": "PASS",
            "calibration": "PASS",
            "selective_eval": "PASS",
        },
    }


def write_runtime_outputs(
    runtime_root: str | Path,
    repository_root: str | Path,
    inventory: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, Path]:
    runtime = ensure_runtime_outside_repository(runtime_root, repository_root)
    layout = {name: runtime / name for name in ("audits", "packages", "reports", "review", "logs")}
    for path in layout.values():
        path.mkdir(parents=True, exist_ok=True)
    outputs = {
        "inventory": layout["audits"] / "v018_asset_inventory.jsonl",
        "summary": layout["audits"] / "v018_asset_summary.json",
        "coverage_html": layout["reports"] / "v018_asset_coverage.html",
        "gaps_csv": layout["reports"] / "v018_asset_gaps.csv",
    }
    write_jsonl(outputs["inventory"], inventory)
    write_json(outputs["summary"], summary)
    _write_gaps_csv(outputs["gaps_csv"], inventory)
    _write_coverage_html(outputs["coverage_html"], inventory, summary)
    return outputs


def ensure_runtime_outside_repository(runtime_root: str | Path, repository_root: str | Path) -> Path:
    runtime = Path(runtime_root).resolve()
    repository = Path(repository_root).resolve()
    if runtime == repository or repository in runtime.parents:
        raise ValueError("v018 runtime must be outside the Git repository")
    return runtime


def audit_repository(
    repository_root: str | Path,
    runtime_root: str | Path,
    pilot_manifest_path: str | Path = DEFAULT_PILOT_MANIFEST,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Path]]:
    repository = Path(repository_root)
    sources = load_repository_assets(repository)
    inventory, context = build_inventory(sources)
    selected, modes = select_pilot_corpus(
        inventory,
        excluded_paper_ids=context["excluded_holdout_paper_ids"],
    )
    expected_manifest = expected_pilot_manifest(selected, modes)
    manifest_path = Path(pilot_manifest_path)
    if not manifest_path.is_absolute():
        manifest_path = repository / manifest_path
    validate_pilot_manifest(_read_json(manifest_path), expected_manifest)
    summary = build_summary(inventory, context, selected)
    outputs = write_runtime_outputs(runtime_root, repository, inventory, summary)
    return inventory, summary, outputs


def stable_paper_id(value: Any) -> str:
    match = STABLE_PAPER_ID_RE.match(str(value or "").strip())
    if match is None:
        raise ValueError(f"paper_id does not begin with stable P#### identity: {value}")
    return match.group(1)


def _main_document_available(record: dict[str, Any]) -> bool:
    return bool(
        str(record.get("validation_status") or "") in VALID_MAIN_DOCUMENT_STATUSES
        and str(record.get("relative_path") or "").strip()
        and SHA256_RE.fullmatch(str(record.get("sha256") or ""))
    )


def _unique_paper_index(
    records: Iterable[dict[str, Any]],
    label: str,
    *,
    require_exact_stable_id: bool = False,
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for position, record in enumerate(records):
        paper_id = stable_paper_id(record.get("paper_id"))
        if require_exact_stable_id and record.get("paper_id") != paper_id:
            raise ValueError(f"{label} row {position} must use exact stable paper_id: {record.get('paper_id')}")
        if paper_id in index:
            raise ValueError(f"{label} contains duplicate paper_id: {paper_id}")
        index[paper_id] = record
    return index


def _group_by_paper(records: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[stable_paper_id(record.get("paper_id"))].append(record)
    return dict(grouped)


def _counts_by_paper(records: Iterable[dict[str, Any]]) -> defaultdict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for record in records:
        counts[stable_paper_id(record.get("paper_id"))] += 1
    return counts


def _ranked(
    records: Iterable[dict[str, Any]],
    boost: Callable[[dict[str, Any]], int] | None = None,
) -> list[dict[str, Any]]:
    extra = boost or (lambda row: 0)
    return sorted(records, key=lambda row: (-(_asset_score(row) + extra(row)), row["paper_id"]))


def _asset_score(record: dict[str, Any]) -> float:
    return (
        100 * bool(record["gold_membership"])
        + 100 * bool(record["human_review_membership"])
        + 50 * bool(record["selective_eval_membership"])
        + 30 * bool(record["calibration_membership"])
        + 20 * (record["evidence_link_count"] > 0)
        + 10 * (record["experiment_record_count"] > 0)
        + 10 * (record["claim_count"] > 0)
        + min(int(record["source_span_count"]), 150) / 150
    )


def _safe_relative_location(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    path = Path(text)
    if not text or path.is_absolute() or re.match(r"^[A-Za-z]:", text) or ".." in path.parts:
        raise ValueError(f"unsafe or absolute source location: {value}")
    return text


def _require_validation_pass(root: Path, label: str) -> None:
    value = _read_json(root / SOURCE_PATHS[label])
    if not isinstance(value, dict) or value.get("result") != "PASS":
        raise ValueError(f"required validator output is not PASS: {SOURCE_PATHS[label].as_posix()}")


def _read_required_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"required audit source missing: {path}")
    return read_jsonl(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_gaps_csv(path: Path, inventory: list[dict[str, Any]]) -> None:
    fields = (
        "paper_id",
        "reaction_family",
        "main_document_available",
        "supplementary_document_available",
        "cleanroom_available",
        "source_span_count",
        "experiment_record_count",
        "claim_count",
        "evidence_link_count",
        "warnings",
    )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for record in inventory:
            if record["warnings"]:
                writer.writerow(
                    {
                        field: ";".join(record[field]) if field == "warnings" else record[field]
                        for field in fields
                    }
                )


def _write_coverage_html(path: Path, inventory: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    coverage_rows = "".join(
        "<tr><th>{}</th><td>{}</td><td>{:.2%}</td></tr>".format(
            escape(label.replace("_", " ").title()),
            value["count"],
            value["rate"],
        )
        for label, value in summary["coverage"].items()
    )
    inventory_rows = "".join(
        "<tr>"
        f"<td>{escape(record['paper_id'])}</td>"
        f"<td>{escape(record['reaction_family'])}</td>"
        f"<td>{'yes' if record['main_document_available'] else 'no'}</td>"
        f"<td>{'yes' if record['supplementary_document_available'] else 'no'}</td>"
        f"<td>{record['source_span_count']}</td>"
        f"<td>{record['experiment_record_count']}</td>"
        f"<td>{record['claim_count']}</td>"
        f"<td>{record['evidence_link_count']}</td>"
        f"<td>{escape('; '.join(record['warnings']))}</td>"
        "</tr>"
        for record in inventory
    )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>M018 A0 evidence asset coverage</title>
<style>body{{font:14px/1.45 system-ui,sans-serif;margin:2rem;color:#18202a}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}th,td{{border:1px solid #ccd3da;padding:.4rem;text-align:left;vertical-align:top}}th{{background:#eef2f5;position:sticky;top:0}}.summary{{max-width:48rem}}code{{background:#eef2f5;padding:.1rem .25rem}}</style>
</head><body><h1>M018 A0 evidence asset coverage</h1>
<p>Deterministic offline inventory. No model, provider, credential, or network operation was used.</p>
<section class="summary"><h2>Coverage</h2><p>Unique papers: <strong>{summary['unique_paper_count']}</strong>; exact source spans: <strong>{summary['source_span_count']}</strong>.</p>
<table><thead><tr><th>Asset</th><th>Papers</th><th>Coverage</th></tr></thead><tbody>{coverage_rows}</tbody></table></section>
<h2>Paper inventory</h2><table><thead><tr><th>Paper</th><th>Family</th><th>Main</th><th>SI</th><th>Spans</th><th>Experiments</th><th>Claims</th><th>Links</th><th>Warnings</th></tr></thead><tbody>{inventory_rows}</tbody></table>
</body></html>\n"""
    path.write_text(html, encoding="utf-8", newline="\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit existing evidence assets for M018 without network access.")
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--pilot-manifest", type=Path, default=DEFAULT_PILOT_MANIFEST)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        inventory, summary, outputs = audit_repository(
            args.repository_root,
            args.runtime_root,
            args.pilot_manifest,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"v018_asset_audit: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print("v018_asset_audit: PASS")
    print(f"unique_papers: {len(inventory)}")
    for label, output in outputs.items():
        print(f"{label}: {output}")
    print("safety_counters: " + json.dumps(summary["safety_counters"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
