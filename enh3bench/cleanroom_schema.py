"""Schema and deterministic serialization helpers for the v0.15 clean-room pipeline."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Iterable


CLEANROOM_SCHEMA_VERSION = "0.15-cleanroom.1"
CLEANROOM_PROFILE = "document_first_cleanroom_v1"
CLEANROOM_STAGES = (
    "ingest",
    "documents",
    "source_nodes",
    "candidates",
    "semantics",
    "links",
    "papers",
    "review",
    "validate",
)
PAPER_ADMISSIBILITY_STATUSES = {
    "not_evaluated",
    "needs_review",
    "insufficient_evidence",
    "partially_supported",
    "supported_with_limitations",
}
HISTORICAL_RUN_NAME = "enrr_round1_oa_20260712"
SAFE_RUN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
RESERVED_RUN_NAMES = {"data", "cleanroom"}

COMMON_REQUIRED_FIELDS = {
    "schema_version",
    "pipeline_profile",
    "run_name",
    "record_created_by_stage",
}
REQUIRED_FIELDS: dict[str, set[str]] = {
    "document": COMMON_REQUIRED_FIELDS | {
        "paper_id", "document_id", "document_ref", "document_body_sha256",
        "document_character_count", "section_count", "paragraph_count", "document_genre",
        "document_genre_confidence", "document_genre_signals", "document_reaction_family",
        "document_reaction_family_confidence", "document_reaction_family_signals",
        "document_reaction_family_conflict", "front_matter_signals", "document_warnings",
    },
    "source_node": COMMON_REQUIRED_FIELDS | {
        "source_node_id", "paper_id", "document_id", "section_uid", "paragraph_uid",
        "source_start_offset", "source_end_offset", "source_locator", "source_order_key",
        "raw_heading", "direct_section_type", "effective_section_type", "document_region",
        "source_text", "source_text_sha256", "provenance_type", "maximum_support_role",
    },
    "candidate": COMMON_REQUIRED_FIELDS | {
        "cleanroom_span_id", "source_node_id", "paper_id", "document_id", "candidate_kind",
        "source_start_offset", "source_end_offset", "source_locator", "source_order_key",
        "source_text", "source_text_sha256", "trigger_signals", "candidate_score",
        "candidate_priority", "generation_method",
    },
    "semantic": COMMON_REQUIRED_FIELDS | {
        "cleanroom_span_id", "source_node_id", "paper_id", "document_id", "document_genre",
        "document_reaction_family", "effective_reaction_family", "span_claim_scope",
        "document_scope", "claim_ownership", "semantic_claim_type",
        "semantic_claim_type_confidence", "performance_result_evidence",
        "quantitative_performance_evidence", "target_ammonia_reaction_outcome_anchor",
        "ammonia_quantification_signal", "gas_purification_trap_signal",
        "validation_gate_decisions", "primary_semantic_eligibility", "hard_gate_failures",
        "semantic_warnings", "needs_review", "needs_review_reasons",
    },
    "paper": COMMON_REQUIRED_FIELDS | {
        "paper_id", "document_id", "document_genre", "document_reaction_family",
        "document_conflicts", "candidate_span_count", "semantic_span_count",
        "primary_eligible_span_count", "primary_claim_counts", "secondary_context_count",
        "evidence_link_count", "validation_gate_summary", "quantification_summary",
        "performance_summary", "reactor_process_summary", "paper_admissibility_status",
        "paper_admissibility_reasons", "best_evidence_span_ids", "review_priority",
        "paper_warnings",
    },
}


def common_fields(run_name: str, stage: str, profile: str = CLEANROOM_PROFILE) -> dict[str, str]:
    return {
        "schema_version": CLEANROOM_SCHEMA_VERSION,
        "pipeline_profile": profile,
        "run_name": run_name,
        "record_created_by_stage": stage,
    }


def make_cleanroom_span_id(
    document_body_sha256: str,
    source_start_offset: int,
    source_end_offset: int,
    candidate_kind: str,
) -> str:
    """Create a stable identity independent of path, run name, ranking, and traversal order."""

    payload = {
        "document_body_sha256": str(document_body_sha256).lower(),
        "source_start_offset": int(source_start_offset),
        "source_end_offset": int(source_end_offset),
        "candidate_kind": str(candidate_kind),
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()[:20].upper()
    return f"CR15_{digest}"


def make_source_node_id(
    document_body_sha256: str, source_start_offset: int, source_end_offset: int
) -> str:
    payload = f"{document_body_sha256.lower()}:{int(source_start_offset)}:{int(source_end_offset)}"
    return f"CRN15_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20].upper()}"


def make_evidence_link_id(paper_id: str, target_span_id: str, evidence_span_id: str) -> str:
    payload = canonical_json({
        "paper_id": str(paper_id),
        "target_cleanroom_span_id": str(target_span_id),
        "evidence_cleanroom_span_id": str(evidence_span_id),
    })
    return f"CRL15_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:20].upper()}"


def validate_record(record_type: str, record: dict[str, Any]) -> list[str]:
    missing = sorted(REQUIRED_FIELDS[record_type] - set(record))
    errors = [f"missing_field:{field}" for field in missing]
    if record.get("schema_version") != CLEANROOM_SCHEMA_VERSION:
        errors.append("invalid_schema_version")
    if record.get("pipeline_profile") != CLEANROOM_PROFILE:
        errors.append("invalid_pipeline_profile")
    if record_type == "paper" and record.get("paper_admissibility_status") not in PAPER_ADMISSIBILITY_STATUSES:
        errors.append("invalid_paper_admissibility_status")
    return errors


def validate_run_name(run_name: str) -> str:
    value = str(run_name or "").strip()
    if not value or value in {".", ".."}:
        raise ValueError("run name must be non-empty and must not be '.' or '..'")
    if value == HISTORICAL_RUN_NAME:
        raise ValueError(f"refusing authoritative historical run name: {value}")
    if value.casefold() in RESERVED_RUN_NAMES:
        raise ValueError(f"refusing reserved clean-room run name: {value}")
    if not SAFE_RUN_NAME.fullmatch(value) or "/" in value or "\\" in value:
        raise ValueError(f"unsafe clean-room run name: {value!r}")
    return value


def validate_compare_run_name(run_name: str) -> str:
    value = str(run_name or "").strip()
    if not value or not SAFE_RUN_NAME.fullmatch(value) or "/" in value or "\\" in value:
        raise ValueError(f"unsafe comparison run name: {value!r}")
    return value


def resolve_clean_target(cleanroom_root: str | Path, run_name: str) -> Path:
    root = Path(cleanroom_root).resolve()
    value = validate_run_name(run_name)
    unresolved = root / value
    is_junction = getattr(unresolved, "is_junction", lambda: False)
    if unresolved.is_symlink() or is_junction():
        raise ValueError(f"refusing symlink or junction clean-room target: {unresolved}")
    target = unresolved.resolve()
    if target.parent != root or target == root:
        raise ValueError(f"clean target escapes clean-room root: {target}")
    return target


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: str | Path, text: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(temp_name, destination)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def write_json(path: str | Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n")


def write_jsonl(path: str | Path, records: Iterable[dict[str, Any]]) -> None:
    atomic_write_text(path, "".join(canonical_json(record) + "\n" for record in records))


def write_csv(path: str | Path, records: list[dict[str, Any]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for record in records for key in record})
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                writer.writerow({key: _csv_value(record.get(key)) for key in fieldnames})
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(temp_name, destination)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL line {line_number} is not an object: {path}")
            records.append(value)
    return records


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple, set)):
        return canonical_json(value)
    return value


def _replace_with_retry(temp_name: str, destination: Path) -> None:
    """Tolerate short-lived Windows scanner locks while retaining replace semantics."""

    last_error: PermissionError | None = None
    for attempt in range(8):
        try:
            os.replace(temp_name, destination)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.025 * (attempt + 1))
    if last_error is not None:
        raise last_error
