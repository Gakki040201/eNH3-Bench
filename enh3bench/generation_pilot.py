"""Offline-only v0.16 B1B0 seven-case generation pilot.

This module deliberately has no provider adapter, credential handling, or model-output
contract.  The only enabled backend is a fixture that emits nonimportable dry-run
receipts for request-shape and provenance verification.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
import hashlib
from itertools import product
import json
import math
import os
from pathlib import Path
import re
import shutil
from typing import Any, Protocol, runtime_checkable
import uuid

from enh3bench.calibration_package import tree_hash
from enh3bench.e2e_eval_schema import (
    canonical_json,
    read_json,
    read_jsonl,
    resolve_run_target,
    sha256_bytes,
    sha256_file,
    validate_run_name,
    write_json,
    write_jsonl,
)
from enh3bench.e2e_eval_validation import validate_selective_eval_package
from enh3bench.e2e_holdout import validate_generation_batch_rows


GENERATION_RUN_SCHEMA_VERSION = "0.16-generation-run.1"
GENERATION_PROMPT_VERSION = "v016-development-generation-v1"
GENERATION_PILOT_PROFILE = "development_seven_case_pilot_v1"
GENERATION_BACKEND_INTERFACE_VERSION = "generation-backend-v1"
COST_ESTIMATE_SCHEMA_VERSION = "0.16-generation-cost.1"
FIXTURE_BACKEND_VERSION = "fixture-generation-v1"
PILOT_CASE_COUNT = 7
DEFAULT_PROMPT_TEMPLATE = Path(__file__).resolve().parents[1] / "prompts/v016_development_generation_v1.md"

CASE_TYPES = (
    "paper_scope_classification",
    "reaction_family_identification",
    "primary_evidence_sufficiency",
    "ammonia_quantification_assessment",
    "validation_reliability_assessment",
    "reactor_process_extraction",
    "claim_ownership_assessment",
)
ANSWERABILITY_STATUSES = (
    "answerable", "partially_answerable", "insufficient_evidence",
)
EVALUATOR_ONLY_FIELDS = frozenset({
    "split", "holdout", "answerability_status", "answerability_reasons",
    "abstention_expected", "automatic_case_risk_score", "automatic_case_risk_tier",
    "automatic_case_risk_reasons", "automatic_signal_stratum", "human_route",
    "machine_route", "evaluator_expected_verdict", "selection_reasons", "stable_rank_sha256",
})
GENERATOR_BATCH_FIELDS = frozenset({
    "schema_version", "profile", "case_id", "paper_id", "question",
    "expected_answer_contract", "required_answer_sections", "allowed_source_span_ids",
    "allowed_evidence_link_ids", "bounded_source_context", "abstention_allowed",
    "source_manifest_sha256",
})
EXECUTION_ONLY_FIELDS = frozenset({
    "generation_status", "network_call_performed", "execution_status",
    "model_output_generated", "importable_api_output", "backend_name",
    "backend_version", "execution_receipt_id", "created_at_utc",
})
COMPILED_PROMPT_FIELDS = frozenset({
    "schema_version", "prompt_instance_id", "prompt_version", "case_id", "paper_id",
    "case_type", "question", "required_answer_sections", "expected_answer_contract",
    "allowed_source_span_ids", "allowed_evidence_link_ids", "bounded_source_context",
    "response_json_schema", "source_manifest_sha256", "prompt_template_sha256",
    "compiled_prompt_sha256",
})
RECEIPT_FIELDS = frozenset({
    "schema_version", "execution_receipt_id", "prompt_instance_id", "case_id",
    "backend_name", "backend_version", "execution_status", "network_call_performed",
    "model_output_generated", "importable_api_output", "request_sha256", "created_at_utc",
})
REQUEST_ENVELOPE_FIELDS = frozenset({
    "schema_version", "backend_interface_version", "request_envelope_id",
    "generation_run_name", "prompt_instance_id", "case_id", "paper_id", "backend_name",
    "backend_version", "prompt_version", "compiled_prompt_sha256", "request_sha256",
    "execution_mode", "created_at_utc",
})
RESPONSE_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "answer_text", "answer_status", "confidence_statement", "claims", "citations",
        "limitations", "abstention_reason",
    ],
    "properties": {
        "answer_text": {"type": "string"},
        "answer_status": {"enum": ["answered", "partially_answered", "abstained"]},
        "confidence_statement": {"type": "string"},
        "claims": {"type": "array", "items": {"type": "object"}},
        "citations": {"type": "array", "items": {"type": "object"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "abstention_reason": {"type": "string"},
    },
}
NORMALIZED_FIELDS = {"generation_run_name", "created_at_utc", "external_output_root"}
FORBIDDEN_ARTIFACT_NAMES = {
    "api_outputs.jsonl", "machine_judgments.jsonl", "human_labels.jsonl",
    "holdout_release_manifest.json", "holdout_generation_batch.jsonl",
    "freeze_manifest.json", "generation_attempts.jsonl",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_id(prefix: str, payload: Any) -> str:
    return f"{prefix}_{sha256_bytes(canonical_json(payload).encode('utf-8'))[:20].upper()}"


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def resolve_external_run_target(root: str | Path, run_name: str) -> Path:
    root_path = Path(root).resolve()
    repository_root = Path(__file__).resolve().parents[1]
    if _path_is_within(root_path, repository_root):
        raise ValueError("generation_output_root_must_be_external")
    value = validate_run_name(run_name)
    target = (root_path / value).resolve()
    if target.parent != root_path:
        raise ValueError("generation_run_target_escapes_external_root")
    if target.is_symlink() or getattr(target, "is_junction", lambda: False)():
        raise ValueError("generation_run_target_is_link")
    return target


def _case_type(row: dict[str, Any]) -> str:
    return str(row.get("case_type") or "")


def _selection_objective(rows: tuple[dict[str, Any], ...]) -> tuple[int, int, int, int]:
    answerability = Counter(str(row.get("answerability_status") or "") for row in rows)
    minimum = min(answerability[status] for status in ANSWERABILITY_STATUSES)
    risk_diversity = len({str(row.get("automatic_case_risk_tier") or "") for row in rows})
    signal_diversity = len({str(row.get("automatic_signal_stratum") or "") for row in rows})
    pair_diversity = len({(
        str(row.get("automatic_case_risk_tier") or ""),
        str(row.get("automatic_signal_stratum") or ""),
    ) for row in rows})
    return minimum, risk_diversity, signal_diversity, pair_diversity


def select_pilot_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Choose one development case per type with fixed semantic-diversity constraints."""

    development = [row for row in cases if row.get("split") == "development"]
    by_type = {
        case_type: sorted(
            (row for row in development if _case_type(row) == case_type),
            key=lambda row: str(row.get("case_id") or ""),
        )
        for case_type in CASE_TYPES
    }
    unavailable = [case_type for case_type, rows in by_type.items() if not rows]
    if unavailable:
        raise ValueError(f"pilot_case_types_unavailable:{unavailable}")
    feasible: list[tuple[tuple[int, int, int, int], str, tuple[dict[str, Any], ...]]] = []
    for combination in product(*(by_type[case_type] for case_type in CASE_TYPES)):
        if len({str(row.get("paper_id") or "") for row in combination}) != PILOT_CASE_COUNT:
            continue
        distribution = Counter(str(row.get("answerability_status") or "") for row in combination)
        if any(distribution[status] < 2 for status in ANSWERABILITY_STATUSES):
            continue
        rank = sha256_bytes(
            canonical_json(sorted(str(row["case_id"]) for row in combination)).encode("utf-8")
        )
        feasible.append((_selection_objective(combination), rank, combination))
    if not feasible:
        raise ValueError("pilot_answerability_diversity_unavailable")
    best_objective = max(value[0] for value in feasible)
    finalists = [value for value in feasible if value[0] == best_objective]
    _, combination_rank, chosen = min(finalists, key=lambda value: value[1])
    result: list[dict[str, Any]] = []
    for row in chosen:
        case_id = str(row["case_id"])
        stable_rank = sha256_bytes(
            canonical_json({
                "algorithm": "evaluator-diversity-sha256-v1",
                "case_id": case_id,
                "combination_rank": combination_rank,
            }).encode("utf-8")
        )
        result.append({
            "case_id": case_id,
            "paper_id": str(row["paper_id"]),
            "case_type": _case_type(row),
            "answerability_status": str(row["answerability_status"]),
            "automatic_case_risk_tier": str(row["automatic_case_risk_tier"]),
            "automatic_signal_stratum": str(row["automatic_signal_stratum"]),
            "stable_rank_sha256": stable_rank,
            "selection_reasons": [
                "development_split_only",
                "one_case_per_required_type",
                "answerability_minimum_two_per_status",
                f"risk_tier_diversity={best_objective[1]}",
                f"signal_stratum_diversity={best_objective[2]}",
                f"risk_signal_pair_diversity={best_objective[3]}",
                f"stable_combination_rank={combination_rank}",
            ],
        })
    result.sort(key=lambda row: (CASE_TYPES.index(str(row["case_type"])), str(row["case_id"])))
    return result


def _selection_manifest(
    selected: list[dict[str, Any]], *, source_run_name: str,
    source_manifest_sha256: str, created_at_utc: str,
) -> dict[str, Any]:
    return {
        "schema_version": GENERATION_RUN_SCHEMA_VERSION,
        "profile": GENERATION_PILOT_PROFILE,
        "selection_algorithm": "evaluator-diversity-sha256-v1",
        "created_at_utc": created_at_utc,
        "source_selective_eval_run_name": source_run_name,
        "source_selective_eval_manifest_sha256": source_manifest_sha256,
        "selected_case_count": len(selected),
        "unique_paper_count": len({row["paper_id"] for row in selected}),
        "development_case_count": len(selected),
        "holdout_case_count": 0,
        "case_type_counts": dict(sorted(Counter(row["case_type"] for row in selected).items())),
        "answerability_distribution": dict(sorted(Counter(
            row["answerability_status"] for row in selected
        ).items())),
        "selected_cases": selected,
    }


def _install_staged_run(stage: Path, target: Path, *, clean: bool) -> None:
    backup: Path | None = None
    if target.exists():
        if not clean:
            raise FileExistsError(f"generation pilot run already exists: {target}")
        backup = target.parent / f".{target.name}.backup_{uuid.uuid4().hex}"
        os.replace(target, backup)
    try:
        os.replace(stage, target)
    except BaseException:
        if backup is not None and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    if backup is not None and backup.exists():
        shutil.rmtree(backup)


def build_development_pilot(
    *,
    selective_eval_run_name: str,
    selective_eval_root: str | Path,
    source_calibration_root: str | Path,
    generation_run_name: str,
    generation_root: str | Path,
    prompt_template: str | Path = DEFAULT_PROMPT_TEMPLATE,
    clean: bool = False,
    validate_source_package: bool = True,
) -> dict[str, Any]:
    source_dir = resolve_run_target(selective_eval_root, selective_eval_run_name)
    target = resolve_external_run_target(generation_root, generation_run_name)
    pilot_root = target.parent
    if _path_is_within(pilot_root, source_dir) or _path_is_within(source_dir, pilot_root):
        raise ValueError("generation_output_root_overlaps_source_package")
    prompt_path = Path(prompt_template).resolve()
    if not prompt_path.is_file() or not prompt_path.read_text(encoding="utf-8").strip():
        raise ValueError("generation_prompt_template_missing_or_blank")
    source_validation = validate_selective_eval_package(
        selective_eval_run_name=selective_eval_run_name,
        selective_eval_root=selective_eval_root,
        source_calibration_root=source_calibration_root,
        check_source_package=validate_source_package,
    )
    if source_validation["result"] != "PASS":
        raise ValueError("source_selective_eval_validation_failed:" + ";".join(source_validation["errors"][:8]))
    if source_validation.get("counts", {}).get("package_stage") not in {None, "blank"}:
        raise ValueError("source_selective_eval_not_blank")
    source_tree_before = tree_hash(source_dir)
    source_manifest_path = source_dir / "manifests/selective_eval_manifest.json"
    source_manifest = read_json(source_manifest_path)
    cases = read_jsonl(source_dir / "cases/e2e_case_frame.jsonl")
    batch = read_jsonl(source_dir / "cases/api_generation_batch.jsonl")
    batch_errors = validate_generation_batch_rows(batch, cases)
    if batch_errors:
        raise ValueError("source_generation_batch_invalid:" + ";".join(batch_errors[:8]))
    selected = select_pilot_cases(cases)
    selected_ids = {row["case_id"] for row in selected}
    pilot_batch = [
        {field: row[field] for field in GENERATOR_BATCH_FIELDS}
        for row in batch
        if row.get("case_id") in selected_ids
    ]
    pilot_batch.sort(key=lambda row: CASE_TYPES.index(str(row["expected_answer_contract"]["case_type"])))
    if len(pilot_batch) != PILOT_CASE_COUNT or any(set(row) != GENERATOR_BATCH_FIELDS for row in pilot_batch):
        raise ValueError("pilot_generator_batch_contract_mismatch")
    created_at = _utc_now()
    root_path = target.parent
    root_path.mkdir(parents=True, exist_ok=True)
    stage = root_path / f".{target.name}.staging_{uuid.uuid4().hex}"
    stage.mkdir()
    try:
        selection_manifest = _selection_manifest(
            selected,
            source_run_name=selective_eval_run_name,
            source_manifest_sha256=sha256_file(source_manifest_path),
            created_at_utc=created_at,
        )
        write_json(stage / "pilot/pilot_selection_manifest.json", selection_manifest)
        write_jsonl(stage / "pilot/development_pilot_batch.jsonl", pilot_batch)
        source_tree_after = tree_hash(source_dir)
        if source_tree_before != source_tree_after:
            raise ValueError("source_package_mutation_detected_during_build")
        manifest = {
            "schema_version": GENERATION_RUN_SCHEMA_VERSION,
            "profile": GENERATION_PILOT_PROFILE,
            "prompt_version": GENERATION_PROMPT_VERSION,
            "backend_interface_version": GENERATION_BACKEND_INTERFACE_VERSION,
            "generation_run_name": generation_run_name,
            "created_at_utc": created_at,
            "status": "pilot_built",
            "source_selective_eval_run_name": selective_eval_run_name,
            "source_selective_eval_manifest_sha256": sha256_file(source_manifest_path),
            "source_selective_eval_tree_sha256_before": source_tree_before,
            "source_selective_eval_tree_sha256_after": source_tree_after,
            "source_case_frame_sha256": sha256_file(source_dir / "cases/e2e_case_frame.jsonl"),
            "source_generation_batch_sha256": sha256_file(source_dir / "cases/api_generation_batch.jsonl"),
            "source_calibration_run_name": source_manifest.get("source_calibration_run_name"),
            "source_calibration_manifest_sha256": source_manifest.get("source_calibration_manifest_sha256"),
            "prompt_template_sha256": sha256_file(prompt_path),
            "prompt_template_character_count": len(prompt_path.read_text(encoding="utf-8")),
            "selected_case_count": PILOT_CASE_COUNT,
            "unique_paper_count": PILOT_CASE_COUNT,
            "holdout_case_count": 0,
            "network_call_count": 0,
            "model_output_count": 0,
            "importable_output_count": 0,
        }
        write_json(stage / "manifests/generation_run_manifest.json", manifest)
        _install_staged_run(stage, target, clean=clean)
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return {
        "result": "PASS", "run_dir": str(target), "case_count": PILOT_CASE_COUNT,
        "network_call_count": 0, "model_output_count": 0, "importable_output_count": 0,
    }


def prepare_generation_prompts(
    *, generation_run_name: str, generation_root: str | Path,
    prompt_template: str | Path = DEFAULT_PROMPT_TEMPLATE,
) -> dict[str, Any]:
    run_dir = resolve_external_run_target(generation_root, generation_run_name)
    manifest = read_json(run_dir / "manifests/generation_run_manifest.json")
    batch = read_jsonl(run_dir / "pilot/development_pilot_batch.jsonl")
    if len(batch) != PILOT_CASE_COUNT or any(set(row) != GENERATOR_BATCH_FIELDS for row in batch):
        raise ValueError("pilot_generator_batch_contract_mismatch")
    if any(_forbidden_execution_keys(row) or _forbidden_evaluator_keys(row) for row in batch):
        raise ValueError("pilot_generator_batch_metadata_firewall_failed")
    template_path = Path(prompt_template).resolve()
    template_sha = sha256_file(template_path)
    if manifest.get("prompt_template_sha256") != template_sha:
        raise ValueError("prompt_template_hash_mismatch")
    compiled: list[dict[str, Any]] = []
    for row in batch:
        case_type = str(row["expected_answer_contract"]["case_type"])
        prompt_id = _stable_id("GPI16", {
            "schema_version": GENERATION_RUN_SCHEMA_VERSION,
            "prompt_version": GENERATION_PROMPT_VERSION,
            "case_id": row["case_id"],
            "prompt_template_sha256": template_sha,
        })
        base = {
            "schema_version": GENERATION_RUN_SCHEMA_VERSION,
            "prompt_instance_id": prompt_id,
            "prompt_version": GENERATION_PROMPT_VERSION,
            "case_id": row["case_id"],
            "paper_id": row["paper_id"],
            "case_type": case_type,
            "question": row["question"],
            "required_answer_sections": row["required_answer_sections"],
            "expected_answer_contract": row["expected_answer_contract"],
            "allowed_source_span_ids": row["allowed_source_span_ids"],
            "allowed_evidence_link_ids": row["allowed_evidence_link_ids"],
            "bounded_source_context": row["bounded_source_context"],
            "response_json_schema": RESPONSE_JSON_SCHEMA,
            "source_manifest_sha256": row["source_manifest_sha256"],
            "prompt_template_sha256": template_sha,
        }
        compiled.append({
            **base,
            "compiled_prompt_sha256": sha256_bytes(canonical_json(base).encode("utf-8")),
        })
    if len(compiled) != PILOT_CASE_COUNT:
        raise ValueError("compiled_prompt_count_mismatch")
    write_jsonl(run_dir / "prompts/compiled_prompt_instances.jsonl", compiled)
    manifest.update({
        "status": "prompts_prepared",
        "compiled_prompt_count": len(compiled),
        "compiled_prompt_instances_sha256": sha256_file(run_dir / "prompts/compiled_prompt_instances.jsonl"),
        "last_updated_at_utc": _utc_now(),
    })
    write_json(run_dir / "manifests/generation_run_manifest.json", manifest)
    return {"result": "PASS", "prompt_count": len(compiled), "network_call_count": 0}


@runtime_checkable
class GenerationBackend(Protocol):
    backend_name: str
    backend_version: str

    def prepare_request(
        self, prompt_instance: dict[str, Any], *, generation_run_name: str,
        created_at_utc: str,
    ) -> dict[str, Any]: ...

    def execute(self, request_envelope: dict[str, Any], *, created_at_utc: str) -> dict[str, Any]: ...

    def parse_response(self, value: dict[str, Any]) -> dict[str, Any]: ...


class FixtureGenerationBackend:
    backend_name = "fixture"
    backend_version = FIXTURE_BACKEND_VERSION

    def prepare_request(
        self, prompt_instance: dict[str, Any], *, generation_run_name: str,
        created_at_utc: str,
    ) -> dict[str, Any]:
        stable = {
            "schema_version": GENERATION_RUN_SCHEMA_VERSION,
            "backend_interface_version": GENERATION_BACKEND_INTERFACE_VERSION,
            "prompt_instance_id": prompt_instance["prompt_instance_id"],
            "case_id": prompt_instance["case_id"],
            "paper_id": prompt_instance["paper_id"],
            "backend_name": self.backend_name,
            "backend_version": self.backend_version,
            "prompt_version": prompt_instance["prompt_version"],
            "compiled_prompt_sha256": prompt_instance["compiled_prompt_sha256"],
            "execution_mode": "dry_run",
        }
        request_sha = sha256_bytes(canonical_json(stable).encode("utf-8"))
        return {
            **stable,
            "request_envelope_id": _stable_id("GRE16", stable),
            "generation_run_name": generation_run_name,
            "request_sha256": request_sha,
            "created_at_utc": created_at_utc,
        }

    def execute(self, request_envelope: dict[str, Any], *, created_at_utc: str) -> dict[str, Any]:
        return {
            "schema_version": GENERATION_RUN_SCHEMA_VERSION,
            "execution_receipt_id": _stable_id("GRC16", {
                "request_sha256": request_envelope["request_sha256"],
                "backend_name": self.backend_name,
                "backend_version": self.backend_version,
            }),
            "prompt_instance_id": request_envelope["prompt_instance_id"],
            "case_id": request_envelope["case_id"],
            "backend_name": self.backend_name,
            "backend_version": self.backend_version,
            "execution_status": "dry_run",
            "network_call_performed": False,
            "model_output_generated": False,
            "importable_api_output": False,
            "request_sha256": request_envelope["request_sha256"],
            "created_at_utc": created_at_utc,
        }

    def parse_response(self, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict) or set(value) != RECEIPT_FIELDS:
            raise ValueError("fixture_receipt_field_mismatch")
        if (
            value.get("backend_name") != self.backend_name
            or value.get("backend_version") != self.backend_version
            or value.get("execution_status") != "dry_run"
            or value.get("network_call_performed") is not False
            or value.get("model_output_generated") is not False
            or value.get("importable_api_output") is not False
        ):
            raise ValueError("fixture_receipt_contract_mismatch")
        return value


def get_generation_backend(name: str) -> GenerationBackend:
    if str(name or "").strip().casefold() != "fixture":
        raise ValueError("real_api_backend_not_enabled")
    return FixtureGenerationBackend()


def run_generation_dry_run(
    *, generation_run_name: str, generation_root: str | Path,
    backend_name: str = "fixture", backend: GenerationBackend | None = None,
) -> dict[str, Any]:
    run_dir = resolve_external_run_target(generation_root, generation_run_name)
    selected_backend = backend if backend is not None else get_generation_backend(backend_name)
    if selected_backend.backend_name != "fixture":
        raise ValueError("real_api_backend_not_enabled")
    prompts = read_jsonl(run_dir / "prompts/compiled_prompt_instances.jsonl")
    if len(prompts) != PILOT_CASE_COUNT:
        raise ValueError("dry_run_requires_seven_compiled_prompts")
    if any(set(row) != COMPILED_PROMPT_FIELDS for row in prompts):
        raise ValueError("compiled_prompt_contract_mismatch")
    if any(_forbidden_execution_keys(row) or _forbidden_evaluator_keys(row) for row in prompts):
        raise ValueError("compiled_prompt_metadata_firewall_failed")
    envelopes: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for prompt_instance in prompts:
        created_at = _utc_now()
        envelope = selected_backend.prepare_request(
            prompt_instance, generation_run_name=generation_run_name, created_at_utc=created_at,
        )
        if set(envelope) != REQUEST_ENVELOPE_FIELDS:
            raise ValueError("request_envelope_field_mismatch")
        receipt = selected_backend.execute(envelope, created_at_utc=created_at)
        parsed = selected_backend.parse_response(receipt)
        if parsed["request_sha256"] != envelope["request_sha256"]:
            raise ValueError("fixture_receipt_request_hash_mismatch")
        envelopes.append(envelope)
        receipts.append(parsed)
    if len(envelopes) != PILOT_CASE_COUNT or len(receipts) != PILOT_CASE_COUNT:
        raise ValueError("dry_run_artifact_count_mismatch")
    execution_dir = run_dir / "execution"
    if execution_dir.exists():
        raise FileExistsError("dry_run_artifacts_already_exist")
    stage = run_dir / f".execution.staging_{uuid.uuid4().hex}"
    stage.mkdir()
    try:
        write_jsonl(stage / "request_envelopes.jsonl", envelopes)
        write_jsonl(stage / "dry_run_receipts.jsonl", receipts)
        os.replace(stage, execution_dir)
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    manifest = read_json(run_dir / "manifests/generation_run_manifest.json")
    manifest.update({
        "status": "dry_run_completed",
        "backend_name": selected_backend.backend_name,
        "backend_version": selected_backend.backend_version,
        "request_envelope_count": len(envelopes),
        "dry_run_receipt_count": len(receipts),
        "network_call_count": 0,
        "model_output_count": 0,
        "importable_output_count": 0,
        "last_updated_at_utc": _utc_now(),
    })
    write_json(run_dir / "manifests/generation_run_manifest.json", manifest)
    return {
        "result": "PASS", "request_envelope_count": len(envelopes),
        "dry_run_receipt_count": len(receipts), "network_call_count": 0,
        "model_output_count": 0, "importable_output_count": 0,
    }


def _pricing_errors(
    input_price: float | None, output_price: float | None, currency: str,
    source: str, as_of: str,
) -> list[str]:
    prices = (input_price, output_price)
    if all(value is None for value in prices):
        return ["pricing_metadata_without_prices"] if any(
            str(value or "").strip() for value in (currency, source, as_of)
        ) else []
    errors: list[str] = []
    if any(value is None for value in prices):
        errors.append("pricing_requires_both_input_and_output_prices")
    for label, value in zip(("input", "output"), prices):
        if value is not None and (not math.isfinite(value) or value < 0):
            errors.append(f"invalid_{label}_price")
    if not str(currency or "").strip():
        errors.append("blank_currency")
    if not str(source or "").strip():
        errors.append("blank_pricing_source")
    try:
        date.fromisoformat(str(as_of or ""))
    except ValueError:
        errors.append("invalid_pricing_date")
    return errors


def estimate_generation_cost(
    *,
    generation_run_name: str,
    generation_root: str | Path,
    estimated_output_tokens_per_case: int = 1200,
    pricing_input_per_million: float | None = None,
    pricing_output_per_million: float | None = None,
    currency: str = "",
    pricing_source: str = "",
    pricing_as_of: str = "",
) -> dict[str, Any]:
    if not isinstance(estimated_output_tokens_per_case, int) or estimated_output_tokens_per_case < 0:
        raise ValueError("invalid_estimated_output_tokens_per_case")
    errors = _pricing_errors(
        pricing_input_per_million, pricing_output_per_million,
        currency, pricing_source, pricing_as_of,
    )
    if errors:
        raise ValueError(";".join(errors))
    run_dir = resolve_external_run_target(generation_root, generation_run_name)
    prompts = read_jsonl(run_dir / "prompts/compiled_prompt_instances.jsonl")
    if len(prompts) != PILOT_CASE_COUNT:
        raise ValueError("cost_estimate_requires_seven_compiled_prompts")
    manifest = read_json(run_dir / "manifests/generation_run_manifest.json")
    template_character_count = int(manifest.get("prompt_template_character_count") or 0)
    if template_character_count < 1:
        raise ValueError("prompt_template_character_count_missing")
    character_count = sum(template_character_count + len(canonical_json(row)) for row in prompts)
    input_lower = math.ceil(character_count / 4.5)
    input_upper = math.ceil(character_count / 3.0)
    total_output = estimated_output_tokens_per_case * len(prompts)
    token_estimate = {
        "schema_version": COST_ESTIMATE_SCHEMA_VERSION,
        "profile": GENERATION_PILOT_PROFILE,
        "prompt_version": GENERATION_PROMPT_VERSION,
        "case_count": len(prompts),
        "prompt_character_count": character_count,
        "estimated_input_tokens_lower": input_lower,
        "estimated_input_tokens_upper": input_upper,
        "estimated_output_tokens_per_case": estimated_output_tokens_per_case,
        "estimated_total_input_tokens": input_upper,
        "estimated_total_output_tokens": total_output,
        "estimation_method": "offline_character_bounds_v1",
    }
    priced = pricing_input_per_million is not None
    if priced:
        assert pricing_output_per_million is not None
        cost_lower = input_lower / 1_000_000 * pricing_input_per_million + total_output / 1_000_000 * pricing_output_per_million
        cost_upper = input_upper / 1_000_000 * pricing_input_per_million + total_output / 1_000_000 * pricing_output_per_million
        estimate_status = "priced"
    else:
        cost_lower = None
        cost_upper = None
        estimate_status = "token_only"
    cost_estimate = {
        "schema_version": COST_ESTIMATE_SCHEMA_VERSION,
        "profile": GENERATION_PILOT_PROFILE,
        **{key: value for key, value in token_estimate.items() if key not in {"schema_version", "profile"}},
        "pricing_input_per_million": pricing_input_per_million,
        "pricing_output_per_million": pricing_output_per_million,
        "estimated_cost_lower": round(cost_lower, 8) if cost_lower is not None else None,
        "estimated_cost_upper": round(cost_upper, 8) if cost_upper is not None else None,
        "currency": str(currency or "").strip(),
        "pricing_source": str(pricing_source or "").strip(),
        "pricing_as_of": str(pricing_as_of or "").strip(),
        "estimate_status": estimate_status,
    }
    write_json(run_dir / "reports/token_estimate.json", token_estimate)
    write_json(run_dir / "reports/cost_estimate_template.json", cost_estimate)
    manifest.update({
        "status": "offline_estimate_completed",
        "cost_estimate_status": estimate_status,
        "last_updated_at_utc": _utc_now(),
    })
    write_json(run_dir / "manifests/generation_run_manifest.json", manifest)
    return {"result": "PASS", "token_estimate": token_estimate, "cost_estimate": cost_estimate}


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in sorted(value.items()) if key not in NORMALIZED_FIELDS}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def normalized_artifact_hash(path: str | Path) -> str:
    source = Path(path)
    value: Any = read_jsonl(source) if source.suffix == ".jsonl" else read_json(source)
    return sha256_bytes(canonical_json(_normalize(value)).encode("utf-8"))


def reproducibility_hashes(run_dir: str | Path) -> dict[str, str]:
    root = Path(run_dir)
    relatives = (
        "pilot/pilot_selection_manifest.json",
        "pilot/development_pilot_batch.jsonl",
        "prompts/compiled_prompt_instances.jsonl",
        "execution/request_envelopes.jsonl",
        "reports/token_estimate.json",
    )
    return {relative: normalized_artifact_hash(root / relative) for relative in relatives}


def _walk_values(value: Any):
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key), item
            yield from _walk_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_values(item)


def _forbidden_evaluator_keys(value: Any) -> set[str]:
    return {key for key, _ in _walk_values(value) if key in EVALUATOR_ONLY_FIELDS}


def _forbidden_execution_keys(value: Any) -> set[str]:
    return {key for key, _ in _walk_values(value) if key in EXECUTION_ONLY_FIELDS}


def _safety_counts(paths: list[Path]) -> dict[str, int]:
    counts = {"absolute_paths": 0, "secrets": 0}
    secret_pattern = re.compile(r"(?i)(api[_-]?key|authorization\s*:|bearer\s+[A-Za-z0-9])")
    drive_pattern = re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]")
    for path in paths:
        text = path.read_text(encoding="utf-8")
        counts["absolute_paths"] += len(drive_pattern.findall(text))
        counts["secrets"] += len(secret_pattern.findall(text))
    return counts


def validate_generation_pilot(
    *,
    generation_run_name: str,
    generation_root: str | Path,
    selective_eval_root: str | Path = Path("data/selective_eval"),
    source_calibration_root: str | Path = Path("data/calibration"),
    check_source_package: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []
    counts: Counter[str] = Counter()
    run_dir = resolve_external_run_target(generation_root, generation_run_name)
    required = {
        "manifests/generation_run_manifest.json",
        "pilot/pilot_selection_manifest.json",
        "pilot/development_pilot_batch.jsonl",
        "prompts/compiled_prompt_instances.jsonl",
        "execution/request_envelopes.jsonl",
        "execution/dry_run_receipts.jsonl",
        "reports/token_estimate.json",
        "reports/cost_estimate_template.json",
    }
    missing = sorted(relative for relative in required if not (run_dir / relative).is_file())
    if missing:
        return {"result": "FAIL", "errors": [f"missing_artifacts:{missing}"], "counts": dict(counts)}
    try:
        manifest = read_json(run_dir / "manifests/generation_run_manifest.json")
        selection = read_json(run_dir / "pilot/pilot_selection_manifest.json")
        batch = read_jsonl(run_dir / "pilot/development_pilot_batch.jsonl")
        prompts = read_jsonl(run_dir / "prompts/compiled_prompt_instances.jsonl")
        envelopes = read_jsonl(run_dir / "execution/request_envelopes.jsonl")
        receipts = read_jsonl(run_dir / "execution/dry_run_receipts.jsonl")
        token_estimate = read_json(run_dir / "reports/token_estimate.json")
        cost_estimate = read_json(run_dir / "reports/cost_estimate_template.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"result": "FAIL", "errors": [f"artifact_read_failed:{exc}"], "counts": dict(counts)}
    if not all(isinstance(value, dict) for value in (manifest, selection, token_estimate, cost_estimate)):
        errors.append("object_artifact_type_mismatch")
    if manifest.get("schema_version") != GENERATION_RUN_SCHEMA_VERSION:
        errors.append("generation_run_schema_mismatch")
    if manifest.get("profile") != GENERATION_PILOT_PROFILE:
        errors.append("generation_pilot_profile_mismatch")
    if manifest.get("prompt_version") != GENERATION_PROMPT_VERSION:
        errors.append("generation_prompt_version_mismatch")
    if manifest.get("backend_interface_version") != GENERATION_BACKEND_INTERFACE_VERSION:
        errors.append("generation_backend_interface_mismatch")
    if manifest.get("generation_run_name") != generation_run_name:
        errors.append("generation_run_name_mismatch")
    if selection.get("schema_version") != GENERATION_RUN_SCHEMA_VERSION:
        errors.append("selection_manifest_schema_mismatch")
    if selection.get("profile") != GENERATION_PILOT_PROFILE:
        errors.append("selection_manifest_profile_mismatch")
    if selection.get("source_selective_eval_manifest_sha256") != manifest.get("source_selective_eval_manifest_sha256"):
        errors.append("selection_source_manifest_mismatch")
    if manifest.get("prompt_template_sha256") != sha256_file(DEFAULT_PROMPT_TEMPLATE):
        errors.append("manifest_prompt_template_hash_mismatch")
    if manifest.get("prompt_template_character_count") != len(DEFAULT_PROMPT_TEMPLATE.read_text(encoding="utf-8")):
        errors.append("manifest_prompt_template_character_count_mismatch")
    source_name = str(manifest.get("source_selective_eval_run_name") or "")
    try:
        source_dir = resolve_run_target(selective_eval_root, source_name)
        source_manifest_path = source_dir / "manifests/selective_eval_manifest.json"
        cases = read_jsonl(source_dir / "cases/e2e_case_frame.jsonl")
        source_batch = read_jsonl(source_dir / "cases/api_generation_batch.jsonl")
        current_tree = tree_hash(source_dir)
        if manifest.get("source_selective_eval_manifest_sha256") != sha256_file(source_manifest_path):
            errors.append("source_selective_eval_manifest_hash_mismatch")
        if manifest.get("source_case_frame_sha256") != sha256_file(source_dir / "cases/e2e_case_frame.jsonl"):
            errors.append("source_case_frame_hash_mismatch")
        if manifest.get("source_generation_batch_sha256") != sha256_file(source_dir / "cases/api_generation_batch.jsonl"):
            errors.append("source_generation_batch_hash_mismatch")
        if manifest.get("source_selective_eval_tree_sha256_before") != current_tree:
            errors.append("source_tree_changed_since_build")
        if manifest.get("source_selective_eval_tree_sha256_after") != current_tree:
            errors.append("source_tree_after_hash_mismatch")
        if check_source_package:
            source_validation = validate_selective_eval_package(
                selective_eval_run_name=source_name,
                selective_eval_root=selective_eval_root,
                source_calibration_root=source_calibration_root,
                check_source_package=True,
            )
            if source_validation["result"] != "PASS":
                errors.extend(f"source_package:{error}" for error in source_validation["errors"][:8])
            source_counts = source_validation.get("counts", {})
            counts["source_imported_api_output_count"] = int(source_counts.get("imported_api_output_count", 0))
            counts["source_imported_machine_judgment_count"] = int(source_counts.get("imported_machine_judgment_count", 0))
            counts["source_human_labels_filled"] = int(source_counts.get("human_labels_filled", 0))
            if source_counts.get("package_stage") != "blank":
                errors.append("source_selective_eval_not_blank")
        recomputed = select_pilot_cases(cases)
        selected_rows = selection.get("selected_cases") if isinstance(selection.get("selected_cases"), list) else []
        if selected_rows != recomputed:
            errors.append("pilot_selection_not_reproducible")
        selected_ids = {row["case_id"] for row in recomputed}
        expected_batch = [
            {field: row[field] for field in GENERATOR_BATCH_FIELDS}
            for row in source_batch
            if row.get("case_id") in selected_ids
        ]
        expected_batch.sort(key=lambda row: CASE_TYPES.index(str(row["expected_answer_contract"]["case_type"])))
        if batch != expected_batch:
            errors.append("generator_batch_source_mismatch")
        case_by_id = {str(row["case_id"]): row for row in cases}
    except (OSError, ValueError, KeyError) as exc:
        errors.append(f"source_validation_failed:{exc}")
        case_by_id = {}
    selected_rows = selection.get("selected_cases") if isinstance(selection.get("selected_cases"), list) else []
    counts["selected_case_count"] = len(selected_rows)
    counts["unique_paper_count"] = len({str(row.get("paper_id") or "") for row in selected_rows})
    counts["case_type_count"] = len({str(row.get("case_type") or "") for row in selected_rows})
    counts["development_case_count"] = sum(
        case_by_id.get(str(row.get("case_id") or ""), {}).get("split") == "development"
        for row in selected_rows
    )
    counts["holdout_case_count"] = sum(
        case_by_id.get(str(row.get("case_id") or ""), {}).get("split") == "holdout"
        for row in selected_rows
    )
    distribution = Counter(str(row.get("answerability_status") or "") for row in selected_rows)
    counts["answerable_count"] = distribution["answerable"]
    counts["partially_answerable_count"] = distribution["partially_answerable"]
    counts["insufficient_evidence_count"] = distribution["insufficient_evidence"]
    if counts["selected_case_count"] != PILOT_CASE_COUNT:
        errors.append("selected_case_count_not_seven")
    if counts["unique_paper_count"] != PILOT_CASE_COUNT:
        errors.append("unique_paper_count_not_seven")
    if counts["case_type_count"] != PILOT_CASE_COUNT:
        errors.append("case_type_count_not_seven")
    if counts["development_case_count"] != PILOT_CASE_COUNT or counts["holdout_case_count"]:
        errors.append("development_holdout_boundary_mismatch")
    if any(distribution[status] < 2 for status in ANSWERABILITY_STATUSES):
        errors.append("answerability_diversity_not_met")
    expected_case_type_counts = dict(sorted(Counter(str(row.get("case_type") or "") for row in selected_rows).items()))
    expected_answerability = dict(sorted(distribution.items()))
    for field, expected in (
        ("selected_case_count", counts["selected_case_count"]),
        ("unique_paper_count", counts["unique_paper_count"]),
        ("development_case_count", counts["development_case_count"]),
        ("holdout_case_count", counts["holdout_case_count"]),
        ("case_type_counts", expected_case_type_counts),
        ("answerability_distribution", expected_answerability),
    ):
        if selection.get(field) != expected:
            errors.append(f"selection_manifest_count_mismatch:{field}")
    counts["pilot_batch_count"] = len(batch)
    counts["pilot_batch_unknown_field_count"] = sum(
        len(set(row) - GENERATOR_BATCH_FIELDS) for row in batch
    )
    counts["pilot_batch_missing_field_count"] = sum(
        len(GENERATOR_BATCH_FIELDS - set(row)) for row in batch
    )
    batch_execution_fields = sum(len(_forbidden_execution_keys(row)) for row in batch)
    for row in batch:
        if set(row) != GENERATOR_BATCH_FIELDS:
            errors.append(f"generator_batch_field_mismatch:{row.get('case_id', '')}")
        execution_fields = _forbidden_execution_keys(row)
        if execution_fields:
            errors.append(f"execution_metadata_in_batch:{row.get('case_id', '')}:{sorted(execution_fields)}")
        forbidden = _forbidden_evaluator_keys(row)
        if forbidden:
            errors.append(f"evaluator_metadata_in_batch:{row.get('case_id', '')}:{sorted(forbidden)}")
    template_sha = sha256_file(DEFAULT_PROMPT_TEMPLATE)
    counts["prompt_instance_count"] = len(prompts)
    counts["compiled_prompt_forbidden_execution_field_count"] = sum(
        len(_forbidden_execution_keys(row)) for row in prompts
    )
    counts["compiled_prompt_evaluator_field_count"] = sum(
        len(_forbidden_evaluator_keys(row)) for row in prompts
    )
    for row in prompts:
        case_id = str(row.get("case_id") or "")
        execution_fields = _forbidden_execution_keys(row)
        if execution_fields:
            errors.append(f"execution_metadata_in_prompt:{case_id}:{sorted(execution_fields)}")
        forbidden = _forbidden_evaluator_keys(row)
        if forbidden:
            errors.append(f"evaluator_metadata_in_prompt:{case_id}:{sorted(forbidden)}")
        if set(row) != COMPILED_PROMPT_FIELDS:
            errors.append(f"compiled_prompt_field_mismatch:{case_id}")
            continue
        base = {key: value for key, value in row.items() if key != "compiled_prompt_sha256"}
        if row.get("compiled_prompt_sha256") != sha256_bytes(canonical_json(base).encode("utf-8")):
            errors.append(f"compiled_prompt_hash_mismatch:{case_id}")
        if row.get("prompt_template_sha256") != template_sha:
            errors.append(f"prompt_template_hash_mismatch:{case_id}")
        if row.get("prompt_instance_id") != _stable_id("GPI16", {
            "schema_version": GENERATION_RUN_SCHEMA_VERSION,
            "prompt_version": GENERATION_PROMPT_VERSION,
            "case_id": case_id,
            "prompt_template_sha256": template_sha,
        }):
            errors.append(f"prompt_instance_id_mismatch:{case_id}")
    backend = FixtureGenerationBackend()
    prompt_by_id = {str(row.get("prompt_instance_id") or ""): row for row in prompts}
    counts["request_envelope_count"] = len(envelopes)
    counts["dry_run_receipt_count"] = len(receipts)
    envelope_by_case = {str(row.get("case_id") or ""): row for row in envelopes}
    counts["request_envelope_forbidden_evaluator_field_count"] = sum(
        len(_forbidden_evaluator_keys(row)) for row in envelopes
    )
    for row in envelopes:
        if set(row) != REQUEST_ENVELOPE_FIELDS:
            errors.append(f"request_envelope_field_mismatch:{row.get('case_id', '')}")
        forbidden = _forbidden_evaluator_keys(row)
        if forbidden:
            errors.append(f"evaluator_metadata_in_request:{row.get('case_id', '')}:{sorted(forbidden)}")
        if row.get("generation_run_name") != generation_run_name:
            errors.append(f"request_run_name_mismatch:{row.get('case_id', '')}")
        prompt_instance = prompt_by_id.get(str(row.get("prompt_instance_id") or ""))
        if prompt_instance is None:
            errors.append(f"request_unknown_prompt_instance:{row.get('case_id', '')}")
        else:
            expected_envelope = backend.prepare_request(
                prompt_instance,
                generation_run_name=generation_run_name,
                created_at_utc=str(row.get("created_at_utc") or ""),
            )
            if row != expected_envelope:
                errors.append(f"request_envelope_hash_or_identity_mismatch:{row.get('case_id', '')}")
    counts["receipt_forbidden_evaluator_field_count"] = sum(
        len(_forbidden_evaluator_keys(row)) for row in receipts
    )
    for row in receipts:
        case_id = str(row.get("case_id") or "")
        forbidden = _forbidden_evaluator_keys(row)
        if forbidden:
            errors.append(f"evaluator_metadata_in_receipt:{case_id}:{sorted(forbidden)}")
        try:
            backend.parse_response(row)
        except ValueError as exc:
            errors.append(f"receipt_invalid:{case_id}:{exc}")
        if case_id not in envelope_by_case or row.get("request_sha256") != envelope_by_case[case_id].get("request_sha256"):
            errors.append(f"receipt_request_mismatch:{case_id}")
        elif row != backend.execute(
            envelope_by_case[case_id], created_at_utc=str(row.get("created_at_utc") or ""),
        ):
            errors.append(f"receipt_identity_mismatch:{case_id}")
    expected_case_ids = {str(row.get("case_id") or "") for row in selected_rows}
    for label, values in (
        ("batch", {str(row.get("case_id") or "") for row in batch}),
        ("prompts", {str(row.get("case_id") or "") for row in prompts}),
        ("envelopes", {str(row.get("case_id") or "") for row in envelopes}),
        ("receipts", {str(row.get("case_id") or "") for row in receipts}),
    ):
        if values != expected_case_ids:
            errors.append(f"case_identity_set_mismatch:{label}")
    counts["network_call_count"] = sum(bool(row.get("network_call_performed")) for row in receipts)
    counts["model_output_count"] = sum(bool(row.get("model_output_generated")) for row in receipts)
    counts["importable_output_count"] = sum(bool(row.get("importable_api_output")) for row in receipts)
    counts["api_output_artifact_count"] = sum(path.name == "api_outputs.jsonl" for path in run_dir.rglob("*"))
    counts["forbidden_artifact_count"] = sum(path.name in FORBIDDEN_ARTIFACT_NAMES for path in run_dir.rglob("*") if path.is_file())
    if counts["request_envelope_count"] != PILOT_CASE_COUNT or counts["dry_run_receipt_count"] != PILOT_CASE_COUNT:
        errors.append("execution_artifact_count_mismatch")
    for key in ("network_call_count", "model_output_count", "importable_output_count", "api_output_artifact_count", "forbidden_artifact_count"):
        if counts[key]:
            errors.append(f"nonzero_offline_safety_count:{key}:{counts[key]}")
    if token_estimate.get("schema_version") != COST_ESTIMATE_SCHEMA_VERSION or token_estimate.get("case_count") != PILOT_CASE_COUNT:
        errors.append("token_estimate_contract_mismatch")
    if cost_estimate.get("schema_version") != COST_ESTIMATE_SCHEMA_VERSION:
        errors.append("cost_estimate_schema_mismatch")
    if cost_estimate.get("estimate_status") not in {"token_only", "priced"}:
        errors.append("cost_estimate_status_invalid")
    if cost_estimate.get("estimate_status") == "token_only" and any(
        cost_estimate.get(field) is not None for field in (
            "pricing_input_per_million", "pricing_output_per_million",
            "estimated_cost_lower", "estimated_cost_upper",
        )
    ):
        errors.append("token_only_cost_fields_not_null")
    template_character_count = int(manifest.get("prompt_template_character_count") or 0)
    expected_characters = sum(template_character_count + len(canonical_json(row)) for row in prompts)
    expected_input_lower = math.ceil(expected_characters / 4.5)
    expected_input_upper = math.ceil(expected_characters / 3.0)
    expected_output_per_case = token_estimate.get("estimated_output_tokens_per_case")
    if not isinstance(expected_output_per_case, int) or expected_output_per_case < 0:
        errors.append("token_estimate_output_tokens_invalid")
        expected_output_per_case = 0
    expected_token_fields = {
        "prompt_character_count": expected_characters,
        "estimated_input_tokens_lower": expected_input_lower,
        "estimated_input_tokens_upper": expected_input_upper,
        "estimated_total_input_tokens": expected_input_upper,
        "estimated_total_output_tokens": expected_output_per_case * PILOT_CASE_COUNT,
    }
    for field, expected in expected_token_fields.items():
        if token_estimate.get(field) != expected or cost_estimate.get(field) != expected:
            errors.append(f"token_estimate_value_mismatch:{field}")
    serialized_paths = [path for path in run_dir.rglob("*") if path.is_file() and path.suffix in {".json", ".jsonl", ".md"}]
    safety = _safety_counts(serialized_paths)
    counts.update(safety)
    for key, value in safety.items():
        if value:
            errors.append(f"nonzero_serialized_safety_count:{key}:{value}")
    counts["evaluator_metadata_in_generator_artifacts"] = sum(
        1 for error in errors if error.startswith("evaluator_metadata_in_")
    )
    counts["input_execution_state_field_count"] = (
        batch_execution_fields + counts["compiled_prompt_forbidden_execution_field_count"]
    )
    counts["source_package_mutation_count"] = sum(
        1 for error in errors if "source_tree" in error or "source_package_mutation" in error
    )
    counts["machine_judgment_artifact_count"] = sum("machine_judgment" in path.name for path in run_dir.rglob("*") if path.is_file())
    counts["human_label_artifact_count"] = sum("human" in path.name for path in run_dir.rglob("*") if path.is_file())
    counts["freeze_artifact_count"] = sum("freeze" in path.name for path in run_dir.rglob("*") if path.is_file())
    counts["holdout_release_artifact_count"] = sum("holdout_release" in path.name for path in run_dir.rglob("*") if path.is_file())
    for key in (
        "machine_judgment_artifact_count", "human_label_artifact_count",
        "freeze_artifact_count", "holdout_release_artifact_count",
    ):
        if counts[key]:
            errors.append(f"forbidden_phase_artifact:{key}:{counts[key]}")
    return {
        "result": "PASS" if not errors else "FAIL",
        "errors": errors,
        "counts": dict(sorted(counts.items())),
        "normalized_hashes": reproducibility_hashes(run_dir) if not missing else {},
    }
