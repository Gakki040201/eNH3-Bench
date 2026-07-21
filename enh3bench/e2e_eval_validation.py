"""Independent validator for v0.16 selective human and E2E evaluation packages."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from enh3bench.calibration_package import tree_hash
from enh3bench.calibration_validation import validate_calibration_package
from enh3bench.e2e_case_generation import assess_case_answerability, generate_cases
from enh3bench.e2e_eval_package import SOURCE_FILES, protected_v015_modules_hash, source_hashes
from enh3bench.e2e_eval_schema import (
    ADJUDICATION_FIELDS,
    ALLOWED_ANSWERABILITY_STATUSES,
    ALLOWED_HUMAN_LABELS,
    ANCHOR_TYPE_QUOTAS,
    CASE_TYPE_QUOTAS,
    FINAL_HUMAN_FIELDS,
    FINAL_HUMAN_LABEL_FIELDS,
    JUDGE_DIMENSIONS,
    JUDGE_SLOTS,
    REVIEWER_IDS,
    SELECTIVE_EVAL_PROFILE,
    SELECTIVE_EVAL_SCHEMA_VERSION,
    canonical_json,
    make_anchor_id,
    make_case_id,
    make_human_review_id,
    make_judgment_id,
    make_output_id,
    paper_split,
    read_csv,
    read_json,
    read_jsonl,
    resolve_run_target,
    sha256_file,
)
from enh3bench.e2e_risk_routing import build_risk_ledger, score_item
from enh3bench.selective_calibration import select_anchors


REQUIRED_FILES = frozenset({
    "manifests/selective_eval_manifest.json", "manifests/split_manifest.json",
    "manifests/source_hashes.json", "risk/full_item_risk_ledger.jsonl", "risk/risk_summary.json",
    "risk/routing_summary.csv", "anchors/selected_anchor_frame.jsonl", "anchors/anchor_review.csv",
    "cases/e2e_case_frame.jsonl", "cases/api_generation_batch.jsonl",
    "cases/api_output_template.jsonl", "cases/machine_judgment_template.jsonl",
    "review/e2e_human_review.csv", "review/adjudication_template.csv",
    "reports/selection_summary.json", "reports/case_coverage.csv",
    "reports/validation_summary.json", "reports/metrics_template.json",
    "previews/selective_eval_preview.md",
})
OPTIONAL_FILES = frozenset({
    "cases/api_outputs.jsonl", "cases/machine_judgments.jsonl", "reports/e2e_metrics_summary.json",
})
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?i)(?:(?<![A-Za-z0-9])[A-Z]:[\\/]|\\\\[A-Za-z0-9_.-]+[\\/][A-Za-z0-9_.$ -]+|(?<![A-Za-z0-9])/(?:home|users|var|tmp)/|file://)"
)
SECRET_PATTERN = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}"
)
FULL_DOCUMENT_KEYS = {"document_body", "full_document_text", "full_text", "pdf_bytes"}


def _result(errors: list[str], warnings: list[str], counts: dict[str, int]) -> dict[str, Any]:
    unique_errors = sorted(set(errors))
    unique_warnings = sorted(set(warnings))
    return {
        "result": "PASS" if not unique_errors else "FAIL",
        "error_count": len(unique_errors), "warning_count": len(unique_warnings),
        "errors": unique_errors, "warnings": unique_warnings, "counts": counts,
    }


def _frames(source_dir: Path) -> dict[str, list[dict[str, Any]]]:
    return {
        item_type: read_jsonl(source_dir / "sampling" / f"{item_type}_sampling_frame.jsonl")
        for item_type in ("span", "paper", "document", "link")
    }


def _groups_for_validation(
    frames: dict[str, list[dict[str, Any]]], paper_id: str,
) -> dict[str, list[dict[str, Any]]]:
    return {
        item_type: [row for row in rows if str(row.get("paper_id") or "") == paper_id]
        for item_type, rows in frames.items()
    }


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _scan(run_dir: Path) -> dict[str, int]:
    counts = {"absolute_paths": 0, "secrets": 0, "full_document_embeddings": 0}
    for path in sorted(item for item in run_dir.rglob("*") if item.is_file()):
        try:
            if path.suffix == ".jsonl":
                value: Any = read_jsonl(path)
            elif path.suffix == ".json":
                value = read_json(path)
            elif path.suffix == ".csv":
                value = read_csv(path)
            else:
                value = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError, json.JSONDecodeError):
            value = path.read_text(encoding="utf-8", errors="replace")
        strings = list(_iter_strings(value))
        counts["absolute_paths"] += sum(len(ABSOLUTE_PATH_PATTERN.findall(text)) for text in strings)
        counts["secrets"] += sum(len(SECRET_PATTERN.findall(text)) for text in strings)
        if isinstance(value, (dict, list)):
            keys = set()
            stack = [value]
            while stack:
                current = stack.pop()
                if isinstance(current, dict):
                    keys.update(current)
                    stack.extend(current.values())
                elif isinstance(current, list):
                    stack.extend(current)
            counts["full_document_embeddings"] += len(keys & FULL_DOCUMENT_KEYS)
    return counts


def _without_run(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key != "selective_eval_run_name"}


def validate_selective_eval_package(
    *,
    selective_eval_run_name: str,
    selective_eval_root: str | Path = "data/selective_eval",
    source_calibration_root: str | Path = "data/calibration",
    check_source_package: bool = True,
) -> dict[str, Any]:
    run_dir = resolve_run_target(selective_eval_root, selective_eval_run_name)
    source_root = Path(source_calibration_root).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    counts = {
        "risk_ledger_items": 0, "anchors": 0, "anchor_review_rows": 0, "e2e_cases": 0,
        "e2e_human_review_rows": 0, "development_papers": 0, "holdout_papers": 0,
        "unique_case_papers": 0, "cross_split_leakage": 0, "api_outputs_filled": 0,
        "machine_judgments_filled": 0, "human_labels_filled": 0, "unresolved_ids": 0,
        "absolute_paths": 0, "full_document_embeddings": 0, "secrets": 0,
        "duplicate_ids": 0, "abstention_expected_cases": 0,
        "answerable_cases": 0, "partially_answerable_cases": 0,
        "insufficient_evidence_cases": 0, "out_of_scope_cases": 0,
    }
    actual_files = {
        path.relative_to(run_dir).as_posix() for path in run_dir.rglob("*") if path.is_file()
    } if run_dir.is_dir() else set()
    errors.extend(f"missing_file:{value}" for value in sorted(REQUIRED_FILES - actual_files))
    errors.extend(f"unexpected_file:{value}" for value in sorted(actual_files - REQUIRED_FILES - OPTIONAL_FILES))
    if errors:
        return _result(errors, warnings, counts)
    try:
        manifest = read_json(run_dir / "manifests/selective_eval_manifest.json")
        split_manifest = read_json(run_dir / "manifests/split_manifest.json")
        source_hash_manifest = read_json(run_dir / "manifests/source_hashes.json")
        ledger = read_jsonl(run_dir / "risk/full_item_risk_ledger.jsonl")
        anchors = read_jsonl(run_dir / "anchors/selected_anchor_frame.jsonl")
        anchor_reviews = read_csv(run_dir / "anchors/anchor_review.csv")
        cases = read_jsonl(run_dir / "cases/e2e_case_frame.jsonl")
        batch = read_jsonl(run_dir / "cases/api_generation_batch.jsonl")
        outputs = read_jsonl(run_dir / "cases/api_output_template.jsonl")
        judgments = read_jsonl(run_dir / "cases/machine_judgment_template.jsonl")
        human_reviews = read_csv(run_dir / "review/e2e_human_review.csv")
        adjudication = read_csv(run_dir / "review/adjudication_template.csv")
        validation_summary = read_json(run_dir / "reports/validation_summary.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid_package_data:{exc}")
        return _result(errors, warnings, counts)

    for label, value in (("manifest", manifest), ("split", split_manifest), ("source_hashes", source_hash_manifest)):
        if value.get("schema_version") != SELECTIVE_EVAL_SCHEMA_VERSION:
            errors.append(f"{label}_schema_version_mismatch")
        if value.get("profile") != SELECTIVE_EVAL_PROFILE:
            errors.append(f"{label}_profile_mismatch")
    if manifest.get("selective_eval_run_name") != selective_eval_run_name:
        errors.append("manifest_run_name_mismatch")
    if manifest.get("status") != "completed":
        errors.append(f"manifest_not_completed:{manifest.get('status')}")
    source_run_name = str(manifest.get("source_calibration_run_name") or "")
    source_dir = source_root / source_run_name
    if not source_dir.is_dir():
        errors.append("missing_source_calibration_package")
        return _result(errors, warnings, counts)
    if check_source_package:
        source_validation = validate_calibration_package(
            calibration_run_name=source_run_name,
            calibration_root=source_root,
            cleanroom_root=source_root.parent / "cleanroom",
            require_blank_human_fields=True,
        )
        if source_validation["result"] != "PASS":
            errors.append("source_calibration_package_not_pass")
    actual_source_hashes = source_hashes(source_dir)
    if manifest.get("source_file_hashes") != actual_source_hashes:
        errors.append("manifest_source_file_hash_mismatch")
    if source_hash_manifest.get("source_file_hashes") != actual_source_hashes:
        errors.append("source_hash_manifest_mismatch")
    source_manifest_sha = sha256_file(source_dir / "manifests/calibration_manifest.json")
    if manifest.get("source_calibration_manifest_sha256") != source_manifest_sha:
        errors.append("source_calibration_manifest_sha_mismatch")
    source_tree = tree_hash(source_dir)
    for suffix in ("before", "after"):
        if manifest.get(f"source_calibration_tree_sha256_{suffix}") != source_tree:
            errors.append(f"source_calibration_tree_{suffix}_mismatch")
    protected_trees = {
        "cleanroom_tree_sha256": tree_hash(source_root.parent / "cleanroom"),
        "gold_tree_sha256": tree_hash(source_root.parent / "gold"),
        "protected_v015_modules_sha256": protected_v015_modules_hash(),
    }
    for field, current in protected_trees.items():
        if source_hash_manifest.get(field) != current:
            errors.append(f"source_hash_manifest_{field}_mismatch")
        for suffix in ("before", "after"):
            if manifest.get(f"{field}_{suffix}") != current:
                errors.append(f"protected_integrity_{field}_{suffix}_mismatch")

    frames = _frames(source_dir)
    frame_ids = {
        str(row["calibration_item_id"])
        for rows in frames.values() for row in rows
    }
    known_papers = {str(row["paper_id"]) for rows in frames.values() for row in rows}
    known_spans = {
        str(row.get(field) or "")
        for row in frames["span"] for field in ("cleanroom_span_id",)
    } | {
        str(row.get(field) or "")
        for row in frames["link"] for field in ("target_span_id", "evidence_span_id")
    }
    known_links = {str(row.get("evidence_link_id") or "") for row in frames["link"]}
    expected_ledger = build_risk_ledger(frames)
    expected_anchors = select_anchors(frames, expected_ledger, seed=int(manifest.get("seed") or 0), anchor_count=24)
    expected_anchor_by_item = {row["source_calibration_item_id"]: row for row in expected_anchors}
    for row in expected_ledger:
        anchor = expected_anchor_by_item.get(row["calibration_item_id"])
        row["selected_as_anchor"] = anchor is not None
        row["anchor_id"] = str(anchor["anchor_id"]) if anchor else ""
        row["anchor_usage"] = str(anchor["anchor_usage"]) if anchor else ""
    counts["risk_ledger_items"] = len(ledger)
    if len(ledger) != 520:
        errors.append(f"risk_ledger_count:{len(ledger)}")
    ledger_by_id = {str(row.get("calibration_item_id") or ""): row for row in ledger}
    counts["duplicate_ids"] += len(ledger) - len(ledger_by_id)
    if set(ledger_by_id) != frame_ids:
        counts["unresolved_ids"] += len(set(ledger_by_id) ^ frame_ids)
        errors.append("risk_ledger_source_id_set_mismatch")
    for expected in expected_ledger:
        actual = ledger_by_id.get(expected["calibration_item_id"], {})
        for field in (
            "item_type", "paper_id", "document_id", "source_sampling_hash", "risk_model_version",
            "risk_score", "risk_tier", "risk_reasons", "human_route", "machine_route",
            "selected_as_anchor", "anchor_id", "anchor_usage",
        ):
            if actual.get(field) != expected.get(field):
                errors.append(f"risk_recomputation_mismatch:{expected['calibration_item_id']}:{field}")

    counts["anchors"] = len(anchors)
    anchor_ids = [str(row.get("anchor_id") or "") for row in anchors]
    counts["duplicate_ids"] += len(anchor_ids) - len(set(anchor_ids))
    if len(anchors) != 24 or Counter(row.get("anchor_type") for row in anchors) != Counter(ANCHOR_TYPE_QUOTAS):
        errors.append("anchor_quota_mismatch")
    if {canonical_json(_without_run(row)) for row in anchors} != {canonical_json(row) for row in expected_anchors}:
        errors.append("deterministic_anchor_selection_mismatch")
    for row in anchors:
        if row.get("anchor_id") != make_anchor_id(str(row.get("anchor_type")), str(row.get("source_calibration_item_id"))):
            errors.append(f"invalid_anchor_id:{row.get('anchor_id')}")
        if row.get("source_calibration_item_id") not in frame_ids:
            counts["unresolved_ids"] += 1

    counts["anchor_review_rows"] = len(anchor_reviews)
    if len(anchor_reviews) != 48:
        errors.append(f"anchor_review_row_count:{len(anchor_reviews)}")
    observations = Counter((row.get("anchor_id"), row.get("reviewer_id")) for row in anchor_reviews)
    if any(value != 1 for value in observations.values()) or set(row.get("reviewer_id") for row in anchor_reviews) != set(REVIEWER_IDS):
        errors.append("anchor_review_reviewer_observation_mismatch")
    for row in anchor_reviews:
        for field, value in row.items():
            if field.startswith("human_") or field == "review_status":
                if str(value or "").strip():
                    counts["human_labels_filled"] += 1

    expected_cases = generate_cases(
        frames, expected_ledger, source_manifest_sha256=source_manifest_sha,
        seed=int(manifest.get("seed") or 0), e2e_case_count=48, development_case_count=36,
    )
    counts["e2e_cases"] = len(cases)
    case_ids = [str(row.get("case_id") or "") for row in cases]
    counts["duplicate_ids"] += len(case_ids) - len(set(case_ids))
    if len(cases) != 48 or Counter(row.get("case_type") for row in cases) != Counter(CASE_TYPE_QUOTAS):
        errors.append("case_quota_mismatch")
    if {canonical_json(_without_run(row)) for row in cases} != {canonical_json(row) for row in expected_cases}:
        errors.append("deterministic_case_generation_mismatch")
    case_by_id = {str(row["case_id"]): row for row in cases}
    development = {str(row["paper_id"]) for row in cases if row.get("split") == "development"}
    holdout = {str(row["paper_id"]) for row in cases if row.get("split") == "holdout"}
    counts["development_papers"] = len(development)
    counts["holdout_papers"] = len(holdout)
    counts["unique_case_papers"] = len({str(row["paper_id"]) for row in cases})
    leakage = development & holdout
    counts["cross_split_leakage"] = len(leakage)
    counts["abstention_expected_cases"] = sum(bool(row.get("abstention_expected")) for row in cases)
    answerability = Counter(str(row.get("answerability_status") or "") for row in cases)
    counts["answerable_cases"] = answerability["answerable"]
    counts["partially_answerable_cases"] = answerability["partially_answerable"]
    counts["insufficient_evidence_cases"] = answerability["insufficient_evidence"]
    counts["out_of_scope_cases"] = answerability["out_of_scope"]
    if (len(development), len(holdout), counts["unique_case_papers"], len(leakage)) != (36, 12, 48, 0):
        errors.append("case_split_or_unique_paper_mismatch")
    for case_type in CASE_TYPE_QUOTAS:
        subset = [row for row in cases if row.get("case_type") == case_type]
        if not any(row.get("answerability_status") in {"answerable", "partially_answerable"} for row in subset):
            errors.append(f"case_type_has_no_answerable_coverage:{case_type}")
    for row in cases:
        case_id = str(row.get("case_id") or "")
        if case_id != make_case_id(str(row.get("paper_id")), str(row.get("document_id")), str(row.get("case_type"))):
            errors.append(f"invalid_case_id:{case_id}")
        if row.get("paper_id") not in known_papers:
            counts["unresolved_ids"] += 1
        split, _ = paper_split(int(manifest.get("seed") or 0), str(row.get("paper_id")))
        if split != row.get("split"):
            errors.append(f"case_paper_split_mismatch:{case_id}")
        if row.get("generation_status") != "pending":
            errors.append(f"case_generation_not_pending:{case_id}")
        status = str(row.get("answerability_status") or "")
        if status not in ALLOWED_ANSWERABILITY_STATUSES:
            errors.append(f"invalid_answerability_status:{case_id}:{status}")
        if not isinstance(row.get("answerability_reasons"), list) or not row.get("answerability_reasons"):
            errors.append(f"invalid_answerability_reasons:{case_id}")
        expected_status, expected_reasons = assess_case_answerability(
            _groups_for_validation(frames, str(row.get("paper_id") or "")),
            str(row.get("case_type") or ""), list(row.get("bounded_source_context") or []),
        )
        if status != expected_status or row.get("answerability_reasons") != expected_reasons:
            errors.append(f"answerability_recomputation_mismatch:{case_id}")
        if bool(row.get("abstention_expected")) != (status in {"insufficient_evidence", "out_of_scope"}):
            errors.append(f"abstention_answerability_mismatch:{case_id}")
        if any(str(value or "").strip() for value in (row.get("human_fields") or {}).values()):
            counts["human_labels_filled"] += 1
        for context in row.get("bounded_source_context") or []:
            if len(str(context.get("excerpt") or "")) > 700:
                errors.append(f"context_excerpt_too_long:{case_id}")
            span_id = str(context.get("source_span_id") or "")
            link_id = str(context.get("evidence_link_id") or "")
            if span_id and span_id not in known_spans:
                counts["unresolved_ids"] += 1
            if link_id and link_id not in known_links:
                counts["unresolved_ids"] += 1
        if any(value not in known_spans for value in row.get("allowed_source_span_ids") or []):
            counts["unresolved_ids"] += 1
        if any(value not in known_links for value in row.get("allowed_evidence_link_ids") or []):
            counts["unresolved_ids"] += 1

    if len(batch) != 48 or {row.get("case_id") for row in batch} != set(case_by_id):
        errors.append("api_batch_case_mismatch")
    for row in batch:
        if row.get("generation_status") != "pending" or row.get("network_call_performed") is not False:
            errors.append(f"api_batch_not_blank:{row.get('case_id')}")
        case = case_by_id.get(str(row.get("case_id") or ""), {})
        for field in ("answerability_status", "answerability_reasons", "abstention_expected"):
            if row.get(field) != case.get(field):
                errors.append(f"api_batch_case_field_mismatch:{row.get('case_id')}:{field}")

    if len(outputs) != 48:
        errors.append(f"api_output_template_count:{len(outputs)}")
    for row in outputs:
        case_id = str(row.get("source_case_id") or "")
        if case_id not in case_by_id or row.get("api_output_id") != make_output_id(case_id):
            counts["unresolved_ids"] += 1
        filled = bool(
            str(row.get("answer_text") or "").strip() or str(row.get("answer_status") or "").strip()
            or str(row.get("generation_model") or "").strip() or row.get("claims") or row.get("citations")
            or row.get("limitations") or str(row.get("abstention_reason") or "").strip()
        )
        counts["api_outputs_filled"] += int(filled)
        if row.get("generation_status") != "pending" or row.get("api_call_performed") is not False:
            errors.append(f"api_output_not_pending:{case_id}")

    if len(judgments) != 96:
        errors.append(f"machine_judgment_template_count:{len(judgments)}")
    judgment_observations: set[tuple[str, str]] = set()
    for row in judgments:
        case_id = str(row.get("source_case_id") or "")
        slot = str(row.get("judge_slot") or "")
        observation = (case_id, slot)
        if observation in judgment_observations:
            counts["duplicate_ids"] += 1
        judgment_observations.add(observation)
        if case_id not in case_by_id or slot not in JUDGE_SLOTS or row.get("machine_judgment_id") != make_judgment_id(case_id, slot):
            counts["unresolved_ids"] += 1
        dimensions = row.get("dimensions") or {}
        if set(dimensions) != set(JUDGE_DIMENSIONS):
            errors.append(f"judge_dimension_schema_mismatch:{case_id}:{slot}")
        filled = bool(str(row.get("judge_id") or "").strip())
        for dimension in dimensions.values():
            filled = filled or dimension.get("score") is not None or bool(str(dimension.get("verdict") or "").strip())
            filled = filled or bool(str(dimension.get("rationale") or "").strip()) or bool(dimension.get("evidence"))
        counts["machine_judgments_filled"] += int(filled)
        if row.get("judgment_status") != "pending" or row.get("judge_call_performed") is not False or row.get("human_truth_claimed") is not False:
            errors.append(f"machine_judgment_not_blank:{case_id}:{slot}")

    counts["e2e_human_review_rows"] = len(human_reviews)
    if len(human_reviews) != 96:
        errors.append(f"e2e_human_review_row_count:{len(human_reviews)}")
    review_observations: set[tuple[str, str]] = set()
    for row in human_reviews:
        case_id = str(row.get("case_id") or "")
        reviewer_id = str(row.get("reviewer_id") or "")
        reviewer_slot = str(row.get("reviewer_slot") or "")
        observation = (case_id, reviewer_id)
        if observation in review_observations:
            counts["duplicate_ids"] += 1
        review_observations.add(observation)
        if reviewer_id not in REVIEWER_IDS:
            errors.append(f"third_reviewer:{case_id}:{reviewer_id}")
        if row.get("human_review_id") != make_human_review_id(case_id, reviewer_slot):
            errors.append(f"invalid_human_review_id:{case_id}:{reviewer_slot}")
        for field, value in row.items():
            if field in FINAL_HUMAN_FIELDS and field != "reviewer_id" and str(value or "").strip():
                counts["human_labels_filled"] += 1
    for row in adjudication:
        for field in (
            "reviewer_1_id", "reviewer_2_id", "reviewer_1_summary", "reviewer_2_summary", *ADJUDICATION_FIELDS,
        ):
            if str(row.get(field) or "").strip():
                counts["human_labels_filled"] += 1

    if split_manifest.get("cross_split_leakage_count") != 0:
        errors.append("split_manifest_leakage_nonzero")
    if validation_summary.get("result") != "PASS" or validation_summary.get("error_count") != 0:
        errors.append("validation_summary_not_pass")
    if manifest.get("validation_summary_sha256") != sha256_file(run_dir / "reports/validation_summary.json"):
        errors.append("validation_summary_hash_mismatch")
    current_hashes = {
        path.relative_to(run_dir).as_posix(): sha256_file(path)
        for path in sorted(item for item in run_dir.rglob("*") if item.is_file())
        if path.relative_to(run_dir).as_posix() != "manifests/selective_eval_manifest.json"
        and path.relative_to(run_dir).as_posix() not in OPTIONAL_FILES
    }
    if manifest.get("output_file_hashes") != current_hashes:
        errors.append("output_file_hash_mismatch")
    scan_counts = _scan(run_dir)
    counts.update(scan_counts)
    if counts["absolute_paths"]:
        errors.append(f"absolute_paths_detected:{counts['absolute_paths']}")
    if counts["secrets"]:
        errors.append(f"secrets_detected:{counts['secrets']}")
    if counts["full_document_embeddings"]:
        errors.append(f"full_document_embeddings_detected:{counts['full_document_embeddings']}")
    for key in (
        "api_outputs_filled", "machine_judgments_filled", "human_labels_filled", "unresolved_ids",
        "absolute_paths", "full_document_embeddings", "secrets", "duplicate_ids",
    ):
        if counts[key]:
            errors.append(f"nonzero_safety_count:{key}:{counts[key]}")
    return _result(errors, warnings, counts)
