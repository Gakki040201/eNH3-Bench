"""Build the v0.16 selective human-anchor and E2E evaluation package."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from enh3bench.calibration_package import tree_hash
from enh3bench.calibration_validation import validate_calibration_package
from enh3bench.e2e_case_generation import (
    ADJUDICATION_COLUMNS,
    E2E_REVIEW_COLUMNS,
    generate_cases,
    make_adjudication_rows,
    make_api_generation_batch,
    make_api_output_templates,
    make_e2e_human_review_rows,
    make_machine_judgment_templates,
)
from enh3bench.e2e_eval_schema import (
    ANCHOR_TYPE_QUOTAS,
    CASE_TYPE_QUOTAS,
    DEFAULT_SEED,
    E2E_CASE_PROFILE,
    RISK_MODEL_VERSION,
    SELECTIVE_EVAL_PROFILE,
    SELECTIVE_EVAL_SCHEMA_VERSION,
    SPLIT_ALGORITHM,
    atomic_write_text,
    normalized_hash,
    paper_split,
    read_json,
    read_jsonl,
    resolve_run_target,
    sha256_file,
    write_csv,
    write_json,
    write_jsonl,
)
from enh3bench.e2e_risk_routing import build_risk_ledger, summarize_risk
from enh3bench.selective_calibration import (
    ANCHOR_REVIEW_COLUMNS,
    make_anchor_review_rows,
    select_anchors,
)


SOURCE_FILES = (
    "manifests/calibration_manifest.json",
    "sampling/span_sampling_frame.jsonl",
    "sampling/paper_sampling_frame.jsonl",
    "sampling/document_sampling_frame.jsonl",
    "sampling/link_sampling_frame.jsonl",
    "review/span_review.csv",
    "review/paper_review.csv",
    "review/document_review.csv",
    "review/link_review.csv",
    "previews/calibration_preview.md",
)
RISK_ROUTING_COLUMNS = (
    "calibration_item_id", "item_type", "paper_id", "risk_score", "risk_tier",
    "human_route", "machine_route", "selected_as_anchor", "anchor_id",
)
CASE_COVERAGE_COLUMNS = (
    "case_type", "requested", "selected", "development", "holdout",
    "T0", "T1", "T2", "T3", "answerable", "partially_answerable",
    "insufficient_evidence", "out_of_scope", "abstention_expected",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def protected_v015_modules_hash() -> str:
    package_root = Path(__file__).resolve().parent
    paths = sorted({
        *package_root.glob("cleanroom_*.py"),
        *package_root.glob("calibration_*.py"),
    })
    lines = [f"{sha256_file(path)}  {path.name}" for path in paths if path.is_file()]
    payload = (("\n".join(lines) + "\n") if lines else "").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _frames(source_dir: Path) -> dict[str, list[dict[str, Any]]]:
    return {
        item_type: read_jsonl(source_dir / "sampling" / f"{item_type}_sampling_frame.jsonl")
        for item_type in ("span", "paper", "document", "link")
    }


def source_hashes(source_dir: Path) -> dict[str, str]:
    return {relative: sha256_file(source_dir / relative) for relative in SOURCE_FILES}


def _split_manifest(
    cases: list[dict[str, Any]], anchors: list[dict[str, Any]], *, seed: int, created_at_utc: str,
) -> dict[str, Any]:
    by_paper: dict[str, dict[str, Any]] = {}
    for case in cases:
        paper_id = str(case["paper_id"])
        split, digest = paper_split(seed, paper_id)
        entry = by_paper.setdefault(paper_id, {"paper_id": paper_id, "split": split, "split_hash_sha256": digest, "case_ids": [], "anchor_ids": []})
        if entry["split"] != case["split"]:
            raise ValueError(f"case split mismatch: {paper_id}")
        entry["case_ids"].append(case["case_id"])
    for anchor in anchors:
        paper_id = str(anchor["paper_id"])
        split, digest = paper_split(seed, paper_id)
        entry = by_paper.setdefault(paper_id, {"paper_id": paper_id, "split": split, "split_hash_sha256": digest, "case_ids": [], "anchor_ids": []})
        if entry["split"] != anchor["split"]:
            raise ValueError(f"anchor split mismatch: {paper_id}")
        entry["anchor_ids"].append(anchor["anchor_id"])
    for entry in by_paper.values():
        entry["case_ids"].sort()
        entry["anchor_ids"].sort()
    development = {str(row["paper_id"]) for row in cases if row["split"] == "development"}
    holdout = {str(row["paper_id"]) for row in cases if row["split"] == "holdout"}
    leakage = sorted(development & holdout)
    return {
        "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
        "profile": SELECTIVE_EVAL_PROFILE,
        "seed": seed,
        "algorithm": SPLIT_ALGORITHM,
        "created_at_utc": created_at_utc,
        "paper_assignments": sorted(by_paper.values(), key=lambda row: row["paper_id"]),
        "development_case_paper_count": len(development),
        "holdout_case_paper_count": len(holdout),
        "cross_split_leakage_count": len(leakage),
        "cross_split_leakage": leakage,
        "holdout_policy": "sealed until prompt and routing rules are frozen",
    }


def _selection_summary(anchors: list[dict[str, Any]], cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
        "profile": SELECTIVE_EVAL_PROFILE,
        "anchor_count": len(anchors),
        "anchor_type_counts": dict(sorted(Counter(row["anchor_type"] for row in anchors).items())),
        "anchor_category_counts": dict(sorted(Counter(row["selection_category"] for row in anchors).items())),
        "anchor_split_counts": dict(sorted(Counter(row["split"] for row in anchors).items())),
        "e2e_case_count": len(cases),
        "case_type_counts": dict(sorted(Counter(row["case_type"] for row in cases).items())),
        "case_split_counts": dict(sorted(Counter(row["split"] for row in cases).items())),
        "unique_case_paper_count": len({row["paper_id"] for row in cases}),
        "abstention_expected_case_count": sum(bool(row["abstention_expected"]) for row in cases),
        "answerability_counts": dict(sorted(Counter(row["answerability_status"] for row in cases).items())),
        "automatic_signal_stratum_counts": dict(sorted(Counter(row["automatic_signal_stratum"] for row in cases).items())),
    }


def _preview(anchors: list[dict[str, Any]], cases: list[dict[str, Any]], risk_summary: dict[str, Any]) -> str:
    lines = [
        "# v0.16 Selective Human and E2E Evaluation Preview", "",
        "This is an infrastructure-only blank package. No API output, machine judgment, or human label exists.",
        "The preview is not a completed audit and establishes no scientific accuracy.", "",
        "## Risk ledger", "",
        f"- Total deterministic risk-scored items: {risk_summary['total_items']}",
        f"- Tier counts: {json.dumps(risk_summary['risk_tier_counts'], sort_keys=True)}", "",
        f"- Case answerability: {json.dumps(dict(sorted(Counter(row['answerability_status'] for row in cases).items())), sort_keys=True)}",
        f"- Abstention expected: {sum(bool(row['abstention_expected']) for row in cases)}", "",
        "## Selected intermediate anchors", "",
    ]
    for row in anchors[:6]:
        lines.append(f"- {row['anchor_id']}: {row['anchor_type']} / {row['selection_category']} / {row['split']}")
    lines.extend(("", "## E2E case examples", ""))
    for row in cases[:6]:
        lines.extend((f"### {row['case_id']} ({row['case_type']}, {row['split']})", "", str(row["question"]), ""))
    lines.extend((
        "No reference answer text is included. Every generation_status is pending.",
        "Human reviewers will primarily assess future end-to-end API outputs.", "",
    ))
    return "\n".join(lines)


def _output_hashes(run_dir: Path) -> dict[str, str]:
    excluded = {"manifests/selective_eval_manifest.json"}
    return {
        path.relative_to(run_dir).as_posix(): sha256_file(path)
        for path in sorted(item for item in run_dir.rglob("*") if item.is_file())
        if path.relative_to(run_dir).as_posix() not in excluded
    }


def build_selective_eval_package(
    *,
    source_calibration_run_name: str,
    source_calibration_root: str | Path,
    selective_eval_run_name: str,
    selective_eval_root: str | Path,
    anchor_count: int = 24,
    e2e_case_count: int = 48,
    development_case_count: int = 36,
    seed: int = DEFAULT_SEED,
    clean: bool = False,
    dry_run: bool = False,
    validate_source_package: bool = True,
) -> dict[str, Any]:
    source_root = Path(source_calibration_root).resolve()
    source_dir = (source_root / source_calibration_run_name).resolve()
    if source_dir.parent != source_root or not source_dir.is_dir():
        raise ValueError(f"invalid source calibration package: {source_dir}")
    run_dir = resolve_run_target(selective_eval_root, selective_eval_run_name)
    if run_dir == source_dir or source_dir in run_dir.parents or run_dir in source_dir.parents:
        raise ValueError("selective-eval target overlaps source calibration package")
    if dry_run:
        return {
            "result": "DRY_RUN", "source": str(source_dir), "target": str(run_dir),
            "would_clean": bool(clean and run_dir.exists()), "network_call_performed": False,
        }
    if run_dir.exists():
        if not clean:
            raise FileExistsError(f"selective-eval run already exists: {run_dir}")
        if run_dir.is_symlink() or getattr(run_dir, "is_junction", lambda: False)():
            raise ValueError(f"refusing to clean symlink or junction: {run_dir}")
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    created_at = _utc_now()
    manifest_path = run_dir / "manifests" / "selective_eval_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    source_manifest_path = source_dir / "manifests" / "calibration_manifest.json"
    source_manifest = read_json(source_manifest_path)
    source_manifest_sha = sha256_file(source_manifest_path)
    cleanroom_root = source_root.parent / "cleanroom"
    gold_root = source_root.parent / "gold"
    before = {
        "source_calibration_tree_sha256": tree_hash(source_dir),
        "cleanroom_tree_sha256": tree_hash(cleanroom_root),
        "gold_tree_sha256": tree_hash(gold_root),
        "protected_v015_modules_sha256": protected_v015_modules_hash(),
    }
    building_manifest = {
        "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
        "profile": SELECTIVE_EVAL_PROFILE,
        "e2e_case_profile": E2E_CASE_PROFILE,
        "risk_model_version": RISK_MODEL_VERSION,
        "selective_eval_run_name": selective_eval_run_name,
        "source_calibration_run_name": source_calibration_run_name,
        "source_calibration_manifest_sha256": source_manifest_sha,
        "source_cleanroom_run_name": source_manifest.get("source_cleanroom_run_name"),
        "seed": int(seed), "created_at_utc": created_at, "status": "building", "errors": [],
        **{f"{key}_before": value for key, value in before.items()},
    }
    write_json(manifest_path, building_manifest)
    try:
        if validate_source_package:
            source_validation = validate_calibration_package(
                calibration_run_name=source_calibration_run_name,
                calibration_root=source_root,
                cleanroom_root=cleanroom_root,
                require_blank_human_fields=True,
            )
            if source_validation["result"] != "PASS":
                raise ValueError(f"source calibration package failed validation: {source_validation['errors'][:5]}")
        frames = _frames(source_dir)
        ledger = build_risk_ledger(frames)
        if len(ledger) != 520:
            raise ValueError(f"source calibration candidate pool must contain 520 items, got {len(ledger)}")
        anchors = select_anchors(frames, ledger, seed=seed, anchor_count=anchor_count)
        anchor_by_item = {row["source_calibration_item_id"]: row for row in anchors}
        for row in ledger:
            anchor = anchor_by_item.get(row["calibration_item_id"])
            row["selected_as_anchor"] = anchor is not None
            row["anchor_id"] = str(anchor["anchor_id"]) if anchor else ""
            row["anchor_usage"] = str(anchor["anchor_usage"]) if anchor else ""
        cases = generate_cases(
            frames, ledger, source_manifest_sha256=source_manifest_sha, seed=seed,
            e2e_case_count=e2e_case_count, development_case_count=development_case_count,
        )
        risk_summary = summarize_risk(ledger)
        selection_summary = _selection_summary(anchors, cases)
        anchor_reviews = make_anchor_review_rows(anchors)
        e2e_reviews = make_e2e_human_review_rows(cases)

        write_jsonl(run_dir / "risk/full_item_risk_ledger.jsonl", ({
            "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
            "profile": SELECTIVE_EVAL_PROFILE,
            "selective_eval_run_name": selective_eval_run_name,
            **row,
        } for row in ledger))
        write_json(run_dir / "risk/risk_summary.json", {
            "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION, "profile": SELECTIVE_EVAL_PROFILE,
            "selective_eval_run_name": selective_eval_run_name, **risk_summary,
        })
        write_csv(run_dir / "risk/routing_summary.csv", [{
            key: (str(row.get(key, "")).lower() if isinstance(row.get(key), bool) else row.get(key, ""))
            for key in RISK_ROUTING_COLUMNS
        } for row in ledger], RISK_ROUTING_COLUMNS)
        write_jsonl(run_dir / "anchors/selected_anchor_frame.jsonl", ({
            "selective_eval_run_name": selective_eval_run_name, **row,
        } for row in anchors))
        write_csv(run_dir / "anchors/anchor_review.csv", anchor_reviews, ANCHOR_REVIEW_COLUMNS)
        write_jsonl(run_dir / "cases/e2e_case_frame.jsonl", ({
            "selective_eval_run_name": selective_eval_run_name, **row,
        } for row in cases))
        write_jsonl(run_dir / "cases/api_generation_batch.jsonl", make_api_generation_batch(cases))
        write_jsonl(run_dir / "cases/api_output_template.jsonl", make_api_output_templates(cases))
        write_jsonl(run_dir / "cases/machine_judgment_template.jsonl", make_machine_judgment_templates(cases))
        write_csv(run_dir / "review/e2e_human_review.csv", e2e_reviews, E2E_REVIEW_COLUMNS)
        write_csv(run_dir / "review/adjudication_template.csv", make_adjudication_rows(cases), ADJUDICATION_COLUMNS)
        split = _split_manifest(cases, anchors, seed=seed, created_at_utc=created_at)
        write_json(run_dir / "manifests/split_manifest.json", split)
        write_json(run_dir / "manifests/source_hashes.json", {
            "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
            "profile": SELECTIVE_EVAL_PROFILE,
            "source_calibration_run_name": source_calibration_run_name,
            "source_calibration_manifest_sha256": source_manifest_sha,
            "source_file_hashes": source_hashes(source_dir), **before,
        })
        write_json(run_dir / "reports/selection_summary.json", selection_summary)
        case_counts = Counter(row["case_type"] for row in cases)
        development_counts = Counter(row["case_type"] for row in cases if row["split"] == "development")
        holdout_counts = Counter(row["case_type"] for row in cases if row["split"] == "holdout")
        write_csv(run_dir / "reports/case_coverage.csv", [{
            "case_type": case_type, "requested": requested, "selected": case_counts[case_type],
            "development": development_counts[case_type], "holdout": holdout_counts[case_type],
            **{
                tier: sum(row["case_type"] == case_type and row["automatic_case_risk_tier"] == tier for row in cases)
                for tier in ("T0", "T1", "T2", "T3")
            },
            **{
                status: sum(row["case_type"] == case_type and row["answerability_status"] == status for row in cases)
                for status in ("answerable", "partially_answerable", "insufficient_evidence", "out_of_scope")
            },
            "abstention_expected": sum(row["case_type"] == case_type and row["abstention_expected"] for row in cases),
        } for case_type, requested in CASE_TYPE_QUOTAS.items()], CASE_COVERAGE_COLUMNS)
        write_json(run_dir / "reports/metrics_template.json", {
            "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION, "profile": SELECTIVE_EVAL_PROFILE,
            "status": "not_available", "reason": "API outputs, machine judgments, and human reviews are blank",
            "precision": None, "pass_rate": None, "cohen_kappa": None,
            "judge_human_agreement": None, "unsupported_claim_rate": None,
            "generation_completion": None, "answerability": None,
            "human_final_output_assessment": None, "machine_judge_assessment": None,
            "abstention_correctness": None, "citation_entailment": None,
            "citation_completeness": None, "fabricated_metric_count": 0,
        })
        atomic_write_text(run_dir / "previews/selective_eval_preview.md", _preview(anchors, cases, risk_summary))
        validation_counts = {
            "anchors": len(anchors), "anchor_review_rows": len(anchor_reviews), "e2e_cases": len(cases),
            "e2e_human_review_rows": len(e2e_reviews), "development_papers": 36,
            "holdout_papers": 12, "unique_case_papers": len({row["paper_id"] for row in cases}),
            "cross_split_leakage": split["cross_split_leakage_count"], "api_outputs_filled": 0,
            "machine_judgments_filled": 0, "human_labels_filled": 0,
        }
        write_json(run_dir / "reports/validation_summary.json", {
            "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION, "profile": SELECTIVE_EVAL_PROFILE,
            "selective_eval_run_name": selective_eval_run_name, "result": "PASS", "error_count": 0,
            "errors": [], "counts": validation_counts,
        })
        after = {
            "source_calibration_tree_sha256": tree_hash(source_dir),
            "cleanroom_tree_sha256": tree_hash(cleanroom_root),
            "gold_tree_sha256": tree_hash(gold_root),
            "protected_v015_modules_sha256": protected_v015_modules_hash(),
        }
        if before != after:
            raise ValueError(f"protected source mutation detected: before={before}, after={after}")
        final_manifest = {
            **building_manifest,
            "status": "completed",
            "requested_anchor_count": anchor_count,
            "requested_e2e_case_count": e2e_case_count,
            "requested_development_case_count": development_case_count,
            "selected_anchor_count": len(anchors), "selected_e2e_case_count": len(cases),
            "development_case_count": 36, "holdout_case_count": 12,
            "source_file_hashes": source_hashes(source_dir),
            **{f"{key}_after": value for key, value in after.items()},
            "validation_summary_sha256": sha256_file(run_dir / "reports/validation_summary.json"),
        }
        final_manifest["output_file_hashes"] = _output_hashes(run_dir)
        write_json(manifest_path, final_manifest)
        from enh3bench.e2e_eval_validation import validate_selective_eval_package
        validation = validate_selective_eval_package(
            selective_eval_run_name=selective_eval_run_name,
            selective_eval_root=selective_eval_root,
            source_calibration_root=source_calibration_root,
            check_source_package=validate_source_package,
        )
        if validation["result"] != "PASS":
            raise ValueError(f"selective-eval package validation failed: {validation['errors'][:8]}")
        return {
            "result": "PASS", "run_dir": str(run_dir), "counts": validation["counts"],
            "normalized_hashes": {
                relative: normalized_hash(run_dir / relative)
                for relative in (
                    "risk/full_item_risk_ledger.jsonl", "anchors/selected_anchor_frame.jsonl",
                    "anchors/anchor_review.csv", "cases/e2e_case_frame.jsonl",
                    "cases/api_generation_batch.jsonl", "cases/api_output_template.jsonl",
                    "cases/machine_judgment_template.jsonl", "review/e2e_human_review.csv",
                    "manifests/split_manifest.json",
                )
            },
        }
    except BaseException as exc:
        failed = {**building_manifest, "status": "failed", "errors": [str(exc)]}
        write_json(manifest_path, failed)
        raise
