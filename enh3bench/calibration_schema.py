"""Versioned schema and serialization helpers for v0.16 semantic calibration."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable, TypedDict


CALIBRATION_SCHEMA_VERSION = "0.16-calibration.1"
CALIBRATION_PROFILE = "human_semantic_calibration_round1_v1"
SAMPLING_ALGORITHM_VERSION = "v016-deterministic-strata-v1"
ALLOWED_HUMAN_LABELS = {"yes", "no", "uncertain", "not_applicable"}
ALLOWED_REVIEW_STATUSES = {"", "in_progress", "completed"}
SAFE_RUN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
RESERVED_RUN_NAMES = {"data", "calibration", "cleanroom", ".", ".."}

COMMON_FIELDS = (
    "schema_version",
    "calibration_profile",
    "calibration_run_name",
    "source_cleanroom_run_name",
    "source_cleanroom_manifest_sha256",
    "record_created_by_stage",
)

SPAN_HUMAN_FIELDS = (
    "reviewer_id", "review_status", "human_span_scope_correct",
    "human_claim_ownership_correct", "human_claim_type_correct",
    "human_effective_family_correct", "human_performance_result_correct",
    "human_quantification_correct", "human_validation_gate_correct",
    "human_primary_eligibility_correct", "human_context_sufficient", "human_notes",
)
DOCUMENT_HUMAN_FIELDS = (
    "reviewer_id", "review_status", "human_document_genre_correct",
    "human_document_family_correct", "human_document_scope_correct", "human_document_notes",
)
PAPER_HUMAN_FIELDS = (
    "reviewer_id", "review_status", "human_paper_status_correct",
    "human_primary_evidence_sufficient", "human_validation_summary_correct",
    "human_limitations_complete", "human_paper_notes",
)
LINK_HUMAN_FIELDS = (
    "reviewer_id", "review_status", "human_link_relevant", "human_link_role_correct",
    "human_link_source_eligible", "human_link_context_only_correct", "human_link_notes",
)
HUMAN_FIELDS_BY_TYPE = {
    "span": SPAN_HUMAN_FIELDS,
    "paper": PAPER_HUMAN_FIELDS,
    "document": DOCUMENT_HUMAN_FIELDS,
    "link": LINK_HUMAN_FIELDS,
}
LABEL_FIELDS_BY_TYPE = {
    item_type: tuple(field for field in fields if field.startswith("human_") and not field.endswith("notes"))
    for item_type, fields in HUMAN_FIELDS_BY_TYPE.items()
}
NOTE_FIELD_BY_TYPE = {
    "span": "human_notes", "paper": "human_paper_notes",
    "document": "human_document_notes", "link": "human_link_notes",
}
ADJUDICATION_FIELDS = (
    "calibration_item_id", "item_type", "reviewer_1_id", "reviewer_2_id",
    "reviewer_1_label_summary", "reviewer_2_label_summary", "disagreement_fields",
    "adjudicator_id", "adjudication_status", "adjudicated_correctness", "corrected_label",
    "adjudication_notes",
)
ADJUDICATION_HUMAN_FIELDS = tuple(field for field in ADJUDICATION_FIELDS if field not in {"calibration_item_id", "item_type"})

SPAN_REQUIRED_FIELDS = set(COMMON_FIELDS) | set(SPAN_HUMAN_FIELDS) | {
    "item_type", "calibration_item_id", "cleanroom_span_id", "paper_id", "document_id",
    "source_node_id", "source_start_offset", "source_end_offset", "source_locator",
    "candidate_kind", "semantic_claim_type", "document_genre", "document_reaction_family",
    "effective_reaction_family", "claim_ownership", "primary_semantic_eligibility",
    "hard_gate_failures", "validation_gate_decisions", "needs_review", "semantic_confidence",
    "assigned_primary_stratum", "selection_stratum", "all_matching_strata", "sampling_rank", "sampling_hash",
    "target_excerpt", "previous_context_excerpt", "next_context_excerpt",
    "linked_evidence_ids", "linked_evidence_excerpt",
}
PAPER_REQUIRED_FIELDS = set(COMMON_FIELDS) | set(PAPER_HUMAN_FIELDS) | {
    "item_type", "calibration_item_id", "paper_id", "document_id", "paper_admissibility_status",
    "document_genre", "document_reaction_family", "candidate_count", "semantic_span_count",
    "primary_eligible_count", "needs_review_count", "best_evidence_span_ids", "limitations",
    "assigned_sampling_stratum", "sampling_rank", "sampling_hash",
}
DOCUMENT_REQUIRED_FIELDS = set(COMMON_FIELDS) | set(DOCUMENT_HUMAN_FIELDS) | {
    "item_type", "calibration_item_id", "document_id", "paper_id", "document_ref",
    "document_body_sha256", "document_genre", "document_reaction_family", "document_conflicts",
    "front_matter_excerpt", "assigned_sampling_stratum", "sampling_rank", "sampling_hash",
}
LINK_REQUIRED_FIELDS = set(COMMON_FIELDS) | set(LINK_HUMAN_FIELDS) | {
    "item_type", "calibration_item_id", "evidence_link_id", "paper_id", "target_span_id",
    "evidence_span_id", "link_role", "target_claim_type", "evidence_claim_type",
    "target_excerpt", "evidence_excerpt", "same_paper", "assigned_sampling_stratum",
    "sampling_rank", "sampling_hash",
}
REQUIRED_FIELDS_BY_TYPE = {
    "span": SPAN_REQUIRED_FIELDS, "paper": PAPER_REQUIRED_FIELDS,
    "document": DOCUMENT_REQUIRED_FIELDS, "link": LINK_REQUIRED_FIELDS,
}


class CalibrationManifest(TypedDict, total=False):
    schema_version: str
    calibration_profile: str
    calibration_run_name: str
    status: str
    errors: list[str]
    warnings: list[str]


class CalibrationSpanItem(TypedDict, total=False):
    calibration_item_id: str
    cleanroom_span_id: str
    target_excerpt: str


class CalibrationPaperItem(TypedDict, total=False):
    calibration_item_id: str
    paper_id: str


class CalibrationDocumentItem(TypedDict, total=False):
    calibration_item_id: str
    document_id: str


class CalibrationLinkItem(TypedDict, total=False):
    calibration_item_id: str
    evidence_link_id: str


class CalibrationReviewRow(TypedDict, total=False):
    calibration_item_id: str
    reviewer_id: str
    review_status: str


class CalibrationAdjudicationRow(TypedDict, total=False):
    calibration_item_id: str
    adjudication_status: str
    corrected_label: str


class CalibrationSummary(TypedDict, total=False):
    selected_counts: dict[str, int]
    warnings: list[str]


class CalibrationMetricSummary(TypedDict, total=False):
    completeness: dict[str, Any]
    agreement: dict[str, Any]
    correctness_metrics: dict[str, Any]
    class_label_metrics: dict[str, Any]


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


def _stable_id(prefix: str, underlying_id: str) -> str:
    payload = canonical_json({
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "calibration_profile": CALIBRATION_PROFILE,
        "underlying_id": str(underlying_id),
    })
    return f"{prefix}_{sha256_bytes(payload.encode('utf-8'))[:20].upper()}"


def make_span_item_id(cleanroom_span_id: str) -> str:
    return _stable_id("CC16S", cleanroom_span_id)


def make_paper_item_id(paper_id: str) -> str:
    return _stable_id("CC16P", paper_id)


def make_document_item_id(document_id: str) -> str:
    return _stable_id("CC16D", document_id)


def make_link_item_id(evidence_link_id: str) -> str:
    return _stable_id("CC16L", evidence_link_id)


ID_BUILDERS = {
    "span": ("cleanroom_span_id", make_span_item_id),
    "paper": ("paper_id", make_paper_item_id),
    "document": ("document_id", make_document_item_id),
    "link": ("evidence_link_id", make_link_item_id),
}


def common_fields(
    calibration_run_name: str,
    source_cleanroom_run_name: str,
    source_manifest_sha256: str,
    stage: str,
) -> dict[str, str]:
    return {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "calibration_profile": CALIBRATION_PROFILE,
        "calibration_run_name": calibration_run_name,
        "source_cleanroom_run_name": source_cleanroom_run_name,
        "source_cleanroom_manifest_sha256": source_manifest_sha256,
        "record_created_by_stage": stage,
    }


def blank_human_fields(item_type: str) -> dict[str, str]:
    return {field: "" for field in HUMAN_FIELDS_BY_TYPE[item_type]}


def validate_run_name(run_name: str) -> str:
    value = str(run_name or "").strip()
    if not value or value.casefold() in RESERVED_RUN_NAMES:
        raise ValueError(f"unsafe calibration run name: {value!r}")
    if not SAFE_RUN_NAME.fullmatch(value) or "/" in value or "\\" in value:
        raise ValueError(f"unsafe calibration run name: {value!r}")
    return value


def resolve_calibration_target(calibration_root: str | Path, run_name: str) -> Path:
    root_value = Path(calibration_root)
    if str(root_value).strip() in {"", "."}:
        raise ValueError("refusing current directory as calibration root")
    root = root_value.resolve()
    value = validate_run_name(run_name)
    unresolved = root / value
    is_junction = getattr(unresolved, "is_junction", lambda: False)
    if unresolved.is_symlink() or is_junction():
        raise ValueError(f"refusing symlink or junction calibration target: {unresolved}")
    target = unresolved.resolve()
    if target == root or target.parent != root:
        raise ValueError(f"calibration target escapes calibration root: {target}")
    return target


def validate_review_row(item_type: str, row: dict[str, Any], *, require_blank: bool = False) -> list[str]:
    errors: list[str] = []
    human_fields = HUMAN_FIELDS_BY_TYPE[item_type]
    for field in human_fields:
        value = str(row.get(field) or "").strip()
        if require_blank and value:
            errors.append(f"nonblank_human_field:{field}")
    status = str(row.get("review_status") or "").strip()
    if status not in ALLOWED_REVIEW_STATUSES:
        errors.append("invalid_review_status")
    for field in LABEL_FIELDS_BY_TYPE[item_type]:
        value = str(row.get(field) or "").strip()
        if value and value not in ALLOWED_HUMAN_LABELS:
            errors.append(f"invalid_human_label:{field}:{value}")
    labels = [str(row.get(field) or "").strip() for field in LABEL_FIELDS_BY_TYPE[item_type]]
    if status == "completed":
        if not str(row.get("reviewer_id") or "").strip():
            errors.append("completed_review_missing_reviewer_id")
        if any(not value for value in labels):
            errors.append("completed_review_missing_labels")
    if any(value in {"no", "uncertain"} for value in labels):
        note_field = NOTE_FIELD_BY_TYPE[item_type]
        if not str(row.get(note_field) or "").strip():
            errors.append(f"no_or_uncertain_requires_notes:{note_field}")
    return errors


def validate_item(item_type: str, record: dict[str, Any], *, require_blank: bool = False) -> list[str]:
    errors = [f"missing_field:{field}" for field in sorted(REQUIRED_FIELDS_BY_TYPE[item_type] - set(record))]
    if record.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
        errors.append("invalid_schema_version")
    if record.get("calibration_profile") != CALIBRATION_PROFILE:
        errors.append("invalid_calibration_profile")
    if record.get("item_type") != item_type:
        errors.append("invalid_item_type")
    source_field, builder = ID_BUILDERS[item_type]
    if str(record.get("calibration_item_id") or "") != builder(str(record.get(source_field) or "")):
        errors.append("invalid_calibration_item_id")
    for field in COMMON_FIELDS:
        if not isinstance(record.get(field), str) or not str(record.get(field) or ""):
            errors.append(f"invalid_string_field:{field}")
    if not isinstance(record.get("sampling_rank"), int) or isinstance(record.get("sampling_rank"), bool):
        errors.append("invalid_type:sampling_rank")
    if not isinstance(record.get("sampling_hash"), str) or len(str(record.get("sampling_hash") or "")) != 64:
        errors.append("invalid_type:sampling_hash")
    if item_type == "span":
        for field in ("source_start_offset", "source_end_offset"):
            if not isinstance(record.get(field), int) or isinstance(record.get(field), bool):
                errors.append(f"invalid_type:{field}")
        for field in ("hard_gate_failures", "all_matching_strata", "linked_evidence_ids"):
            if not isinstance(record.get(field), list):
                errors.append(f"invalid_type:{field}")
        if not isinstance(record.get("validation_gate_decisions"), dict):
            errors.append("invalid_type:validation_gate_decisions")
        for field in ("primary_semantic_eligibility", "needs_review"):
            if not isinstance(record.get(field), bool):
                errors.append(f"invalid_type:{field}")
    if item_type == "link" and not isinstance(record.get("same_paper"), bool):
        errors.append("invalid_type:same_paper")
    errors.extend(validate_review_row(item_type, record, require_blank=require_blank))
    return errors


def atomic_write_text(path: str | Path, text: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
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


def write_csv(path: str | Path, records: list[dict[str, Any]], fieldnames: Iterable[str] | None = None) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    columns = list(fieldnames or sorted({key for record in records for key in record}))
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for record in records:
                writer.writerow({key: _csv_value(record.get(key)) for key in columns})
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON is not an object: {path}")
    return value


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


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple, set)):
        return canonical_json(value)
    return value
