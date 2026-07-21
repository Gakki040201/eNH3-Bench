"""Sealed holdout export rules for v0.16 selective evaluation."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from enh3bench.e2e_case_generation import EVALUATOR_ONLY_CASE_FIELDS, GENERATION_BATCH_FIELDS
from enh3bench.e2e_eval_schema import (
    ANSWER_CONTRACT_VERSION,
    QUESTION_TEMPLATE_VERSION,
    RISK_MODEL_VERSION,
    SELECTIVE_EVAL_SCHEMA_VERSION,
)


FREEZE_MANIFEST_FIELDS = frozenset({
    "schema_version", "selective_eval_run_name", "source_calibration_manifest_sha256",
    "prompt_version", "generation_model_family", "generation_parameters_sha256",
    "risk_model_version", "question_template_version", "answer_contract_version",
    "development_case_count", "holdout_case_count", "development_results_frozen",
    "routing_rules_frozen", "prompt_frozen", "created_at_utc", "status",
})
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


def validate_generation_batch_rows(
    rows: list[dict[str, Any]], cases: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    case_by_id = {str(case.get("case_id") or ""): case for case in cases}
    if len(rows) != len(case_by_id) or {str(row.get("case_id") or "") for row in rows} != set(case_by_id):
        errors.append("api_batch_case_mismatch")
    seen: set[str] = set()
    copied_fields = (
        "paper_id", "question", "expected_answer_contract", "required_answer_sections",
        "allowed_source_span_ids", "allowed_evidence_link_ids", "bounded_source_context",
        "abstention_allowed", "source_manifest_sha256",
    )
    for index, row in enumerate(rows, 1):
        unknown = set(row) - GENERATION_BATCH_FIELDS
        missing = GENERATION_BATCH_FIELDS - set(row)
        if unknown:
            errors.append(f"api_batch_unknown_fields:{index}:{','.join(sorted(unknown))}")
        if missing:
            errors.append(f"api_batch_missing_fields:{index}:{','.join(sorted(missing))}")
        if set(row) & EVALUATOR_ONLY_CASE_FIELDS:
            errors.append(f"api_batch_evaluator_metadata_exposed:{index}")
        case_id = str(row.get("case_id") or "")
        if not case_id or case_id in seen:
            errors.append(f"api_batch_duplicate_or_blank_case:{index}")
        seen.add(case_id)
        case = case_by_id.get(case_id)
        if case is None:
            continue
        for field in copied_fields:
            if row.get(field) != case.get(field):
                errors.append(f"api_batch_case_field_mismatch:{case_id}:{field}")
        if row.get("schema_version") != case.get("schema_version") or row.get("profile") != case.get("profile"):
            errors.append(f"api_batch_case_identity_mismatch:{case_id}")
        if row.get("generation_status") != "pending" or row.get("network_call_performed") is not False:
            errors.append(f"api_batch_not_blank:{case_id}")
    return errors


def validate_freeze_manifest(
    freeze: dict[str, Any], package_manifest: dict[str, Any], cases: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if set(freeze) != FREEZE_MANIFEST_FIELDS:
        errors.append("freeze_manifest_field_set_mismatch")
    expected = {
        "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
        "selective_eval_run_name": package_manifest.get("selective_eval_run_name"),
        "source_calibration_manifest_sha256": package_manifest.get("source_calibration_manifest_sha256"),
        "risk_model_version": RISK_MODEL_VERSION,
        "question_template_version": QUESTION_TEMPLATE_VERSION,
        "answer_contract_version": ANSWER_CONTRACT_VERSION,
        "development_case_count": sum(case.get("split") == "development" for case in cases),
        "holdout_case_count": sum(case.get("split") == "holdout" for case in cases),
        "status": "frozen",
        "development_results_frozen": True,
        "routing_rules_frozen": True,
        "prompt_frozen": True,
    }
    for field, value in expected.items():
        if freeze.get(field) != value:
            errors.append(f"freeze_manifest_mismatch:{field}")
    for field in ("prompt_version", "generation_model_family"):
        if not str(freeze.get(field) or "").strip():
            errors.append(f"freeze_manifest_blank:{field}")
    if not SHA256_PATTERN.fullmatch(str(freeze.get("generation_parameters_sha256") or "")):
        errors.append("freeze_manifest_invalid_generation_parameters_sha256")
    created = str(freeze.get("created_at_utc") or "")
    try:
        if not created.endswith("Z"):
            raise ValueError
        datetime.fromisoformat(created[:-1] + "+00:00")
    except ValueError:
        errors.append("freeze_manifest_invalid_created_at_utc")
    return errors


def select_generation_rows(
    batch: list[dict[str, Any]], cases: list[dict[str, Any]], *, split: str,
) -> list[dict[str, Any]]:
    if split not in {"development", "holdout"}:
        raise ValueError(f"unsupported generation split: {split}")
    selected_ids = {str(case["case_id"]) for case in cases if case.get("split") == split}
    rows = [row for row in batch if str(row.get("case_id") or "") in selected_ids]
    if len(rows) != len(selected_ids) or {str(row.get("case_id") or "") for row in rows} != selected_ids:
        raise ValueError(f"generation batch split identity mismatch: {split}")
    return rows
