"""Future import contracts and conservative metrics for E2E evaluation."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from enh3bench.e2e_eval_schema import (
    ALLOWED_ANSWER_STATUSES,
    ALLOWED_JUDGE_VERDICTS,
    ALLOWED_SUPPORT_STATUSES,
    E2E_METRICS_SCHEMA_VERSION,
    JUDGE_DIMENSIONS,
    SELECTIVE_EVAL_PROFILE,
    SELECTIVE_EVAL_SCHEMA_VERSION,
    make_judgment_id,
    make_output_id,
    read_csv,
    read_json,
    read_jsonl,
)


API_OUTPUT_FIELDS = {
    "schema_version", "profile", "api_output_id", "source_case_id", "source_manifest_sha256",
    "answer_text", "answer_status", "confidence_statement", "claims", "citations", "limitations",
    "abstention_reason", "generation_model", "generation_prompt_version", "generation_parameters",
    "generation_status", "api_call_performed",
}
JUDGMENT_FIELDS = {
    "schema_version", "profile", "machine_judgment_id", "source_case_id", "source_api_output_id",
    "source_manifest_sha256", "judge_slot", "judge_id", "judgment_status", "dimensions",
    "judge_disagreement_status", "human_truth_claimed", "judge_call_performed",
}
METRICS_SUMMARY_FIELDS = {
    "schema_version", "profile", "metric_schema_version", "selective_eval_run_name",
    "source_calibration_run_name", "source_calibration_manifest_sha256", "status",
    "validation_errors", "package_stage", "case_count", "api_output_count",
    "machine_judgment_count", "completed_human_review_count", "precision", "pass_rate",
    "cohen_kappa", "judge_human_agreement", "unsupported_claim_rate",
    "generation_completion", "answerability", "human_final_output_assessment",
    "machine_judge_assessment", "abstention_correctness", "citation_entailment",
    "citation_completeness", "fabricated_metric_count", "reviewer_coverage",
    "inferential_metrics_ready", "judge_disagreement_count", "reason",
}


def validate_api_output(row: dict[str, Any], case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    unknown = sorted(set(row) - API_OUTPUT_FIELDS)
    missing = sorted(API_OUTPUT_FIELDS - set(row))
    errors.extend(f"unknown_api_output_field:{field}" for field in unknown)
    errors.extend(f"missing_api_output_field:{field}" for field in missing)
    if row.get("schema_version") != SELECTIVE_EVAL_SCHEMA_VERSION or row.get("profile") != SELECTIVE_EVAL_PROFILE:
        errors.append("api_output_schema_or_profile_mismatch")
    case_id = str(case.get("case_id") or "")
    if row.get("source_case_id") != case_id or row.get("api_output_id") != make_output_id(case_id):
        errors.append("api_output_source_identity_mismatch")
    if row.get("source_manifest_sha256") != case.get("source_manifest_sha256"):
        errors.append("api_output_source_manifest_mismatch")
    status = str(row.get("answer_status") or "")
    if status not in ALLOWED_ANSWER_STATUSES:
        errors.append(f"invalid_answer_status:{status}")
    if row.get("generation_status") not in {"completed", "failed"}:
        errors.append("api_output_generation_status_not_terminal")
    if status == "failed" and row.get("generation_status") != "failed":
        errors.append("failed_answer_status_generation_mismatch")
    if status != "failed" and row.get("generation_status") != "completed":
        errors.append("completed_answer_status_generation_mismatch")
    if not isinstance(row.get("api_call_performed"), bool):
        errors.append("api_call_performed_not_boolean")
    if not isinstance(row.get("generation_parameters"), dict):
        errors.append("generation_parameters_not_object")
    for field in ("claims", "citations", "limitations"):
        if not isinstance(row.get(field), list):
            errors.append(f"api_output_{field}_not_list")
    if isinstance(row.get("limitations"), list) and any(not isinstance(value, str) for value in row["limitations"]):
        errors.append("api_output_limitations_not_string_list")
    if status in {"answered", "partially_answered"} and not str(row.get("answer_text") or "").strip():
        errors.append("answered_output_missing_answer_text")
    if status in {"answered", "partially_answered"} and not row.get("claims"):
        errors.append("answered_output_missing_claims")
    if status == "abstained" and not str(row.get("abstention_reason") or "").strip():
        errors.append("abstained_output_missing_reason")
    if status == "abstained" and (
        str(row.get("answer_text") or "").strip() or row.get("claims") or row.get("citations")
    ):
        errors.append("abstained_output_contains_substantive_answer")
    allowed_spans = set(case.get("allowed_source_span_ids") or [])
    allowed_links = set(case.get("allowed_evidence_link_ids") or [])
    claim_ids: set[str] = set()
    for index, claim in enumerate(row.get("claims") or [], 1):
        if not isinstance(claim, dict):
            errors.append(f"claim_not_object:{index}")
            continue
        required = {
            "claim_id", "claim_text", "claim_type", "supporting_source_span_ids",
            "supporting_evidence_link_ids", "support_status",
        }
        if set(claim) != required:
            errors.append(f"claim_schema_mismatch:{index}")
            continue
        claim_id = str(claim.get("claim_id") or "")
        if not claim_id or claim_id in claim_ids:
            errors.append(f"duplicate_or_blank_claim_id:{index}")
        claim_ids.add(claim_id)
        if not str(claim.get("claim_text") or "").strip() or not str(claim.get("claim_type") or "").strip():
            errors.append(f"blank_claim_content:{index}")
        claim_citation_lists_valid = True
        for field in ("supporting_source_span_ids", "supporting_evidence_link_ids"):
            values = claim.get(field)
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                errors.append(f"claim_citation_ids_not_string_list:{index}:{field}")
                claim_citation_lists_valid = False
        if claim.get("support_status") not in ALLOWED_SUPPORT_STATUSES:
            errors.append(f"invalid_claim_support_status:{index}")
        if claim_citation_lists_valid and not set(claim.get("supporting_source_span_ids") or []).issubset(allowed_spans):
            errors.append(f"citation_outside_span_allowlist:{index}")
        if claim_citation_lists_valid and not set(claim.get("supporting_evidence_link_ids") or []).issubset(allowed_links):
            errors.append(f"citation_outside_link_allowlist:{index}")
    citation_ids: set[str] = set()
    for index, citation in enumerate(row.get("citations") or [], 1):
        if not isinstance(citation, dict):
            errors.append(f"citation_not_object:{index}")
            continue
        required = {"citation_id", "claim_ids", "source_span_ids", "evidence_link_ids"}
        if set(citation) != required:
            errors.append(f"citation_schema_mismatch:{index}")
            continue
        citation_id = str(citation.get("citation_id") or "")
        if not citation_id or citation_id in citation_ids:
            errors.append(f"duplicate_or_blank_citation_id:{index}")
        citation_ids.add(citation_id)
        claim_references = citation.get("claim_ids")
        if (
            not isinstance(claim_references, list)
            or any(not isinstance(value, str) for value in claim_references)
            or not set(claim_references).issubset(claim_ids)
        ):
            errors.append(f"citation_unknown_claim:{index}")
        citation_lists_valid = True
        for field in ("source_span_ids", "evidence_link_ids"):
            if not isinstance(citation.get(field), list) or any(not isinstance(value, str) for value in citation.get(field) or []):
                errors.append(f"citation_ids_not_string_list:{index}:{field}")
                citation_lists_valid = False
        if citation_lists_valid and not set(citation.get("source_span_ids") or []).issubset(allowed_spans):
            errors.append(f"citation_outside_span_allowlist:top:{index}")
        if citation_lists_valid and not set(citation.get("evidence_link_ids") or []).issubset(allowed_links):
            errors.append(f"citation_outside_link_allowlist:top:{index}")
    return errors


def validate_machine_judgment(
    row: dict[str, Any], template: dict[str, Any], case: dict[str, Any] | None = None,
    api_output: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    errors.extend(f"unknown_judgment_field:{field}" for field in sorted(set(row) - JUDGMENT_FIELDS))
    errors.extend(f"missing_judgment_field:{field}" for field in sorted(JUDGMENT_FIELDS - set(row)))
    if row.get("schema_version") != SELECTIVE_EVAL_SCHEMA_VERSION or row.get("profile") != SELECTIVE_EVAL_PROFILE:
        errors.append("judgment_schema_or_profile_mismatch")
    case_id = str(template.get("source_case_id") or "")
    slot = str(template.get("judge_slot") or "")
    for field in ("source_case_id", "source_api_output_id", "source_manifest_sha256", "judge_slot"):
        if row.get(field) != template.get(field):
            errors.append(f"judgment_source_identity_mismatch:{field}")
    if row.get("machine_judgment_id") != make_judgment_id(case_id, slot):
        errors.append("judgment_id_mismatch")
    if not str(row.get("judge_id") or "").strip():
        errors.append("judgment_missing_judge_id")
    if row.get("judgment_status") != "completed":
        errors.append("judgment_status_not_completed")
    dimensions = row.get("dimensions")
    if not isinstance(dimensions, dict) or set(dimensions) != set(JUDGE_DIMENSIONS):
        errors.append("invalid_judge_dimension_set")
        return errors
    for name, dimension in dimensions.items():
        if not isinstance(dimension, dict) or set(dimension) != {
            "score", "verdict", "confidence", "rationale", "evidence", "judge_model", "judge_prompt_version",
        }:
            errors.append(f"invalid_judge_dimension_schema:{name}")
            continue
        score = dimension.get("score")
        if name == "unsupported_claim_count":
            if not isinstance(score, int) or isinstance(score, bool) or score < 0:
                errors.append(f"invalid_judge_score:{name}")
        elif not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 1:
            errors.append(f"invalid_judge_score:{name}")
        if dimension.get("verdict") not in ALLOWED_JUDGE_VERDICTS:
            errors.append(f"invalid_judge_verdict:{name}")
        confidence = dimension.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            errors.append(f"invalid_judge_confidence:{name}")
        for field in ("rationale", "judge_model", "judge_prompt_version"):
            if not str(dimension.get(field) or "").strip():
                errors.append(f"blank_judge_dimension_field:{name}:{field}")
        evidence = dimension.get("evidence")
        if not isinstance(evidence, list):
            errors.append(f"judge_evidence_not_list:{name}")
        elif case is not None:
            allowed_spans = set(case.get("allowed_source_span_ids") or [])
            allowed_links = set(case.get("allowed_evidence_link_ids") or [])
            for index, reference in enumerate(evidence, 1):
                if not isinstance(reference, dict) or set(reference) != {"source_span_ids", "evidence_link_ids", "claim_ids"}:
                    errors.append(f"judge_evidence_schema_mismatch:{name}:{index}")
                    continue
                ref_lists_valid = all(
                    isinstance(reference.get(field), list)
                    and all(isinstance(value, str) for value in reference.get(field) or [])
                    for field in ("source_span_ids", "evidence_link_ids")
                )
                if not ref_lists_valid:
                    errors.append(f"judge_evidence_ids_not_string_lists:{name}:{index}")
                    continue
                if not set(reference.get("source_span_ids") or []).issubset(allowed_spans):
                    errors.append(f"judge_evidence_outside_span_allowlist:{name}:{index}")
                if not set(reference.get("evidence_link_ids") or []).issubset(allowed_links):
                    errors.append(f"judge_evidence_outside_link_allowlist:{name}:{index}")
                claim_references = reference.get("claim_ids")
                if not isinstance(claim_references, list) or any(not isinstance(value, str) for value in claim_references):
                    errors.append(f"judge_evidence_claim_ids_not_list:{name}:{index}")
                elif api_output is not None:
                    known_claim_ids = {
                        str(claim.get("claim_id") or "")
                        for claim in api_output.get("claims") or [] if isinstance(claim, dict)
                    }
                    if not set(claim_references).issubset(known_claim_ids):
                        errors.append(f"judge_evidence_unknown_claim:{name}:{index}")
    if row.get("human_truth_claimed") is not False:
        errors.append("machine_judgment_claims_human_truth")
    return errors


def summarize_e2e(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir)
    manifest = read_json(root / "manifests/selective_eval_manifest.json")
    cases = read_jsonl(root / "cases/e2e_case_frame.jsonl")
    output_path = root / "cases/api_outputs.jsonl"
    judgment_path = root / "cases/machine_judgments.jsonl"
    reviews = read_csv(root / "review/e2e_human_review.csv")
    outputs = read_jsonl(output_path) if output_path.is_file() else []
    judgments = read_jsonl(judgment_path) if judgment_path.is_file() else []
    completed_reviews = [row for row in reviews if row.get("review_status") == "completed"]
    reviewer_counts = Counter(row.get("reviewer_id") for row in completed_reviews)
    stage = (
        "human_reviewed" if completed_reviews else
        "judged" if judgments else
        "generated" if outputs else
        "blank"
    )
    result: dict[str, Any] = {
        "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
        "profile": SELECTIVE_EVAL_PROFILE,
        "metric_schema_version": E2E_METRICS_SCHEMA_VERSION,
        "selective_eval_run_name": manifest.get("selective_eval_run_name"),
        "source_calibration_run_name": manifest.get("source_calibration_run_name"),
        "source_calibration_manifest_sha256": manifest.get("source_calibration_manifest_sha256"),
        "status": "not_available",
        "validation_errors": [], "package_stage": stage,
        "case_count": len(cases), "api_output_count": len(outputs),
        "machine_judgment_count": len(judgments), "completed_human_review_count": len(completed_reviews),
        "precision": None, "pass_rate": None, "cohen_kappa": None,
        "judge_human_agreement": None, "unsupported_claim_rate": None,
        "generation_completion": None, "answerability": None,
        "human_final_output_assessment": None, "machine_judge_assessment": None,
        "abstention_correctness": None, "citation_entailment": None,
        "citation_completeness": None, "fabricated_metric_count": 0,
        "reviewer_coverage": dict(sorted(reviewer_counts.items())),
        "inferential_metrics_ready": bool(outputs and completed_reviews),
        "judge_disagreement_count": None,
    }
    if not outputs or not completed_reviews:
        result["reason"] = "API outputs and completed human reviews are required before inferential metrics"
        return result
    result["reason"] = "metric computation remains unavailable until a separately approved completed-review phase"
    return result
