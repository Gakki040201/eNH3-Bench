"""Sealed holdout export rules for v0.16 selective evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any

from enh3bench.e2e_case_generation import EVALUATOR_ONLY_CASE_FIELDS, GENERATION_BATCH_FIELDS
from enh3bench.e2e_eval_metrics import validate_api_output
from enh3bench.e2e_eval_schema import (
    ANSWER_CONTRACT_VERSION,
    QUESTION_TEMPLATE_VERSION,
    RISK_MODEL_VERSION,
    SELECTIVE_EVAL_SCHEMA_VERSION,
    canonical_json,
    read_csv,
    read_json,
    read_jsonl,
    sha256_bytes,
    sha256_file,
    write_json,
    write_jsonl,
)


FREEZE_MANIFEST_SCHEMA_VERSION = "0.16-holdout-freeze.1"
FREEZE_MANIFEST_FIELDS = frozenset({
    "schema_version", "freeze_manifest_schema_version", "selective_eval_run_name",
    "source_calibration_manifest_sha256", "package_manifest_sha256",
    "case_frame_sha256", "generation_batch_sha256", "development_api_outputs_sha256",
    "development_api_output_count", "prompt_sha256",
    "development_generation_model_family", "development_prompt_version",
    "development_generation_parameters_sha256", "development_generation_provenance_consistent",
    "prompt_version", "generation_model_family", "generation_parameters_sha256",
    "risk_model_version", "question_template_version", "answer_contract_version",
    "development_case_count", "holdout_case_count", "development_results_frozen",
    "routing_rules_frozen", "prompt_frozen", "created_at_utc", "status",
})
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
RELEASE_MANIFEST_FIELDS = frozenset({
    "freeze_manifest_sha256", "exported_holdout_batch_sha256", "holdout_case_count",
    "selective_eval_run_name", "created_at_utc", "network_calls_performed",
})


def path_is_within(path: str | Path, root: str | Path) -> bool:
    candidate = Path(path).resolve()
    boundary = Path(root).resolve()
    return candidate == boundary or boundary in candidate.parents


def canonical_json_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json(value).encode("utf-8"))


def generation_batch_sha256(rows: list[dict[str, Any]]) -> str:
    payload = "".join(canonical_json(row) + "\n" for row in rows).encode("utf-8")
    return sha256_bytes(payload)


def write_holdout_release(
    output: str | Path, rows: list[dict[str, Any]], *, freeze_manifest: str | Path,
    selective_eval_run_name: str, created_at_utc: str | None = None,
) -> tuple[str, Path, dict[str, Any]]:
    destination = Path(output).resolve()
    release_path = destination.parent / "holdout_release_manifest.json"
    batch_hash = generation_batch_sha256(rows)
    identity = {
        "freeze_manifest_sha256": sha256_file(freeze_manifest),
        "exported_holdout_batch_sha256": batch_hash,
        "holdout_case_count": len(rows),
        "selective_eval_run_name": selective_eval_run_name,
        "network_calls_performed": 0,
    }
    if destination.exists() or release_path.exists():
        if not destination.is_file() or not release_path.is_file():
            raise FileExistsError("incomplete existing holdout release")
        existing = read_json(release_path)
        if (
            not isinstance(existing, dict)
            or set(existing) != RELEASE_MANIFEST_FIELDS
            or any(existing.get(key) != value for key, value in identity.items())
            or sha256_file(destination) != batch_hash
        ):
            raise FileExistsError("existing holdout release differs from requested release")
        return "already_released", release_path, existing
    release = {
        **identity,
        "created_at_utc": created_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    try:
        write_jsonl(destination, rows)
        write_json(release_path, release)
    except Exception:
        release_path.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise
    return "released", release_path, release


def read_generation_parameters(path: str | Path) -> Any:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"generation parameters are not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("generation parameters JSON must be an object")
    return value


def validate_development_freeze_outputs(
    outputs: list[dict[str, Any]], cases: list[dict[str, Any]], *,
    generation_model_family: str, prompt_version: str, generation_parameters: Any,
) -> tuple[list[str], list[dict[str, Any]]]:
    errors: list[str] = []
    case_by_id = {str(case.get("case_id") or ""): case for case in cases}
    development_ids = {
        case_id for case_id, case in case_by_id.items() if case.get("split") == "development"
    }
    holdout_ids = {
        case_id for case_id, case in case_by_id.items() if case.get("split") == "holdout"
    }
    source_ids = [str(row.get("source_case_id") or "") for row in outputs]
    output_ids = [str(row.get("api_output_id") or "") for row in outputs]
    source_id_set = set(source_ids)
    holdout_count = sum(case_id in holdout_ids for case_id in source_ids)
    unknown_count = sum(case_id not in case_by_id for case_id in source_ids)
    duplicate_count = len(source_ids) - len(source_id_set) + len(output_ids) - len(set(output_ids))
    if holdout_count:
        errors.append(f"freeze_holdout_output_already_exists:{holdout_count}")
    if (
        len(outputs) != len(development_ids)
        or source_id_set != development_ids
        or unknown_count
        or duplicate_count
    ):
        errors.append(
            "freeze_requires_development_only_outputs:"
            f"rows={len(outputs)}:unknown={unknown_count}:duplicates={duplicate_count}"
        )
    selected = [row for row in outputs if str(row.get("source_case_id") or "") in development_ids]
    selected.sort(key=lambda row: str(row.get("source_case_id") or ""))
    failed_count = sum(row.get("answer_status") == "failed" for row in selected)
    if failed_count:
        errors.append(f"freeze_failed_development_output:{failed_count}")
    declared_parameters = canonical_json(generation_parameters)
    provenance_incomplete = False
    observed_models: set[str] = set()
    observed_prompts: set[str] = set()
    observed_parameters: set[str] = set()
    for row in selected:
        case_id = str(row.get("source_case_id") or "")
        case = case_by_id[case_id]
        model = str(row.get("generation_model") or "")
        prompt = str(row.get("generation_prompt_version") or "")
        parameters = row.get("generation_parameters")
        observed_models.add(model)
        observed_prompts.add(prompt)
        if isinstance(parameters, dict):
            observed_parameters.add(canonical_json(parameters))
        if (
            row.get("answer_status") not in {"answered", "partially_answered", "abstained"}
            or row.get("generation_status") != "completed"
            or row.get("api_call_performed") is not True
            or not model or not prompt
            or not isinstance(parameters, dict) or not parameters
            or validate_api_output(row, case)
        ):
            provenance_incomplete = True
        if model != generation_model_family:
            errors.append(f"freeze_development_model_mismatch:{case_id}")
        if prompt != prompt_version:
            errors.append(f"freeze_development_prompt_mismatch:{case_id}")
        if not isinstance(parameters, dict) or canonical_json(parameters) != declared_parameters:
            errors.append(f"freeze_development_parameters_mismatch:{case_id}")
    if len(observed_models) > 1 or len(observed_prompts) > 1 or len(observed_parameters) > 1:
        errors.append("freeze_heterogeneous_development_provenance")
    if provenance_incomplete:
        errors.append("freeze_incomplete_generation_provenance")
    return errors, selected


def validate_no_holdout_pre_exposure(
    run_dir: str | Path, cases: list[dict[str, Any]], outputs: list[dict[str, Any]],
) -> list[str]:
    root = Path(run_dir)
    errors: list[str] = []
    holdout_ids = {
        str(case.get("case_id") or "") for case in cases if case.get("split") == "holdout"
    }
    holdout_outputs = sum(
        str(row.get("source_case_id") or "") in holdout_ids for row in outputs
    )
    if holdout_outputs:
        errors.append(f"freeze_holdout_output_already_exists:{holdout_outputs}")
    judgment_path = root / "cases/machine_judgments.jsonl"
    if judgment_path.is_file():
        judgments = read_jsonl(judgment_path)
        holdout_judgments = sum(
            str(row.get("source_case_id") or "") in holdout_ids for row in judgments
        )
        if holdout_judgments:
            errors.append(f"holdout_machine_judgment_already_exists:{holdout_judgments}")
    reviews = read_csv(root / "review/e2e_human_review.csv")
    holdout_completed_reviews = sum(
        str(row.get("case_id") or "") in holdout_ids
        and row.get("review_status") == "completed"
        for row in reviews
    )
    if holdout_completed_reviews:
        errors.append(f"holdout_completed_review_already_exists:{holdout_completed_reviews}")
    return errors


def development_outputs(
    outputs: list[dict[str, Any]], cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    development_ids = {
        str(case.get("case_id") or "") for case in cases if case.get("split") == "development"
    }
    selected = [
        row for row in outputs if str(row.get("source_case_id") or "") in development_ids
    ]
    selected.sort(key=lambda row: str(row.get("source_case_id") or ""))
    return selected


def compute_freeze_snapshot(
    run_dir: str | Path, cases: list[dict[str, Any]], *,
    prompt_file: str | Path, generation_parameters: Any,
) -> dict[str, Any]:
    root = Path(run_dir)
    outputs = read_jsonl(root / "cases/api_outputs.jsonl")
    selected = development_outputs(outputs, cases)
    return {
        "package_manifest_sha256": sha256_file(root / "manifests/selective_eval_manifest.json"),
        "case_frame_sha256": sha256_file(root / "cases/e2e_case_frame.jsonl"),
        "generation_batch_sha256": sha256_file(root / "cases/api_generation_batch.jsonl"),
        "development_api_outputs_sha256": canonical_json_sha256(selected),
        "development_api_output_count": len(selected),
        "prompt_sha256": sha256_file(prompt_file),
        "generation_parameters_sha256": canonical_json_sha256(generation_parameters),
    }


def build_freeze_manifest(
    package_manifest: dict[str, Any], cases: list[dict[str, Any]], *,
    run_dir: str | Path, prompt_file: str | Path, generation_parameters: Any,
    prompt_version: str, generation_model_family: str,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    if not prompt_version.strip() or not generation_model_family.strip():
        raise ValueError("prompt version and generation model family must be nonblank")
    outputs = read_jsonl(Path(run_dir) / "cases/api_outputs.jsonl")
    gate_errors, _ = validate_development_freeze_outputs(
        outputs, cases, generation_model_family=generation_model_family,
        prompt_version=prompt_version, generation_parameters=generation_parameters,
    )
    if gate_errors:
        raise ValueError("; ".join(gate_errors))
    snapshot = compute_freeze_snapshot(
        run_dir, cases, prompt_file=prompt_file, generation_parameters=generation_parameters,
    )
    if snapshot["development_api_output_count"] != 36:
        raise ValueError(
            "holdout freeze requires exactly 36 development API outputs; "
            f"found {snapshot['development_api_output_count']}"
        )
    return {
        "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
        "freeze_manifest_schema_version": FREEZE_MANIFEST_SCHEMA_VERSION,
        "selective_eval_run_name": package_manifest.get("selective_eval_run_name"),
        "source_calibration_manifest_sha256": package_manifest.get("source_calibration_manifest_sha256"),
        **snapshot,
        "development_generation_model_family": generation_model_family,
        "development_prompt_version": prompt_version,
        "development_generation_parameters_sha256": canonical_json_sha256(generation_parameters),
        "development_generation_provenance_consistent": True,
        "prompt_version": prompt_version,
        "generation_model_family": generation_model_family,
        "risk_model_version": RISK_MODEL_VERSION,
        "question_template_version": QUESTION_TEMPLATE_VERSION,
        "answer_contract_version": ANSWER_CONTRACT_VERSION,
        "development_case_count": sum(case.get("split") == "development" for case in cases),
        "holdout_case_count": sum(case.get("split") == "holdout" for case in cases),
        "development_results_frozen": True,
        "routing_rules_frozen": True,
        "prompt_frozen": True,
        "created_at_utc": created_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "frozen",
    }


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
    freeze: dict[str, Any], package_manifest: dict[str, Any], cases: list[dict[str, Any]], *,
    run_dir: str | Path, prompt_file: str | Path, generation_parameters: Any,
) -> list[str]:
    errors: list[str] = []
    if set(freeze) != FREEZE_MANIFEST_FIELDS:
        errors.append("freeze_manifest_field_set_mismatch")
    expected = {
        "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
        "freeze_manifest_schema_version": FREEZE_MANIFEST_SCHEMA_VERSION,
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
        "development_generation_model_family": freeze.get("generation_model_family"),
        "development_prompt_version": freeze.get("prompt_version"),
        "development_generation_parameters_sha256": canonical_json_sha256(generation_parameters),
        "development_generation_provenance_consistent": True,
    }
    try:
        outputs = read_jsonl(Path(run_dir) / "cases/api_outputs.jsonl")
        gate_errors, _ = validate_development_freeze_outputs(
            outputs, cases,
            generation_model_family=str(freeze.get("generation_model_family") or ""),
            prompt_version=str(freeze.get("prompt_version") or ""),
            generation_parameters=generation_parameters,
        )
        errors.extend(gate_errors)
        errors.extend(validate_no_holdout_pre_exposure(run_dir, cases, outputs))
    except (OSError, ValueError) as exc:
        errors.append(f"freeze_manifest_output_validation_unavailable:{exc}")
    try:
        expected.update(compute_freeze_snapshot(
            run_dir, cases, prompt_file=prompt_file,
            generation_parameters=generation_parameters,
        ))
    except (OSError, ValueError) as exc:
        errors.append(f"freeze_manifest_snapshot_unavailable:{exc}")
    for field, value in expected.items():
        if freeze.get(field) != value:
            errors.append(f"freeze_manifest_mismatch:{field}")
    if expected.get("development_api_output_count") != expected["development_case_count"]:
        errors.append("freeze_manifest_incomplete_development_outputs")
    for field in ("prompt_version", "generation_model_family"):
        if not str(freeze.get(field) or "").strip():
            errors.append(f"freeze_manifest_blank:{field}")
    for field in (
        "package_manifest_sha256", "case_frame_sha256", "generation_batch_sha256",
        "development_api_outputs_sha256", "prompt_sha256", "generation_parameters_sha256",
        "development_generation_parameters_sha256",
    ):
        if not SHA256_PATTERN.fullmatch(str(freeze.get(field) or "")):
            errors.append(f"freeze_manifest_invalid_sha256:{field}")
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
