"""Schema, stable identities, and serialization for v0.16 selective evaluation."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable


SELECTIVE_EVAL_SCHEMA_VERSION = "0.16-selective-eval.1"
SELECTIVE_EVAL_PROFILE = "selective_human_anchor_and_e2e_api_v1"
RISK_MODEL_VERSION = "structured_risk_router_v1"
E2E_CASE_PROFILE = "single_paper_scientific_answer_v1"
QUESTION_TEMPLATE_VERSION = "v016-e2e-question-templates-v1"
ANSWER_CONTRACT_VERSION = "v016-scientific-answer-contract-v1"
JUDGE_TEMPLATE_VERSION = "v016-multijudge-template-v1"
HUMAN_REVIEW_TEMPLATE_VERSION = "v016-final-output-review-v1"
SPLIT_ALGORITHM = "sha256-paper-bucket-75-25-v1"
DEFAULT_SEED = 16
REVIEWER_IDS = ("R1", "R2")
JUDGE_SLOTS = ("judge_1", "judge_2")
ALLOWED_HUMAN_LABELS = {"", "yes", "no", "uncertain", "not_applicable"}
ALLOWED_OVERALL_VERDICTS = {"", "pass", "minor_revision", "major_revision", "reject", "uncertain"}
ALLOWED_REVIEW_STATUSES = {"", "in_progress", "completed"}
ALLOWED_ANSWER_STATUSES = {"answered", "partially_answered", "abstained", "failed"}
ALLOWED_ANSWERABILITY_STATUSES = {"answerable", "partially_answerable", "insufficient_evidence", "out_of_scope"}
ALLOWED_SUPPORT_STATUSES = {"supported", "partially_supported", "unsupported", "uncertain"}
ALLOWED_JUDGE_VERDICTS = {"pass", "fail", "uncertain", "not_applicable"}
SAFE_RUN_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
RESERVED_RUN_NAMES = {".", "..", "data", "selective_eval", "calibration", "cleanroom", "gold"}

ANCHOR_TYPE_QUOTAS = {"span": 12, "paper": 4, "document": 4, "link": 4}
CASE_TYPE_QUOTAS = {
    "paper_scope_classification": 8,
    "reaction_family_identification": 8,
    "primary_evidence_sufficiency": 8,
    "ammonia_quantification_assessment": 8,
    "validation_reliability_assessment": 6,
    "reactor_process_extraction": 5,
    "claim_ownership_assessment": 5,
}
HOLDOUT_CASE_TYPE_QUOTAS = {
    "paper_scope_classification": 2,
    "reaction_family_identification": 2,
    "primary_evidence_sufficiency": 2,
    "ammonia_quantification_assessment": 2,
    "validation_reliability_assessment": 2,
    "reactor_process_extraction": 1,
    "claim_ownership_assessment": 1,
}
QUESTION_TEMPLATES = {
    "paper_scope_classification": (
        "Does this paper report original experimental research on electrochemical nitrogen reduction, "
        "and what scope limitations prevent a stronger classification?"
    ),
    "reaction_family_identification": (
        "Which reaction family is actually studied in this paper, and what bounded evidence supports "
        "that identification?"
    ),
    "primary_evidence_sufficiency": (
        "Does this paper provide sufficient primary evidence to support its ammonia-generation conclusion, "
        "or should the conclusion remain uncertain?"
    ),
    "ammonia_quantification_assessment": (
        "Are the ammonia quantification method, calibration, and contamination controls reported in this "
        "paper sufficient for a defensible quantitative conclusion?"
    ),
    "validation_reliability_assessment": (
        "How reliable is the paper's validation of ammonia origin, and which required controls or checks are "
        "present, missing, or ambiguous?"
    ),
    "reactor_process_extraction": (
        "Which reactor, flow, or process parameters are explicitly reported by this paper, and which material "
        "parameters remain unreported?"
    ),
    "claim_ownership_assessment": (
        "Are the performance and mechanistic claims in the supplied evidence the target authors' own results, "
        "or are they attributed to external studies?"
    ),
}
REQUIRED_ANSWER_SECTIONS = (
    "answer", "evidence_and_citations", "limitations", "confidence_or_abstention"
)
JUDGE_DIMENSIONS = (
    "answer_correctness", "citation_entailment", "citation_completeness", "claim_ownership",
    "reaction_family_correctness", "quantification_correctness", "validation_correctness",
    "uncertainty_calibration", "abstention_appropriateness", "unsupported_claim_count",
    "overall_usefulness",
)
FINAL_HUMAN_LABEL_FIELDS = (
    "human_answer_correct", "human_citations_support_claims", "human_citations_complete",
    "human_reaction_family_correct", "human_claim_ownership_correct", "human_quantification_correct",
    "human_validation_correct", "human_uncertainty_appropriate", "human_abstention_appropriate",
    "human_no_unsupported_claims", "human_scientifically_useful",
)
FINAL_HUMAN_FIELDS = (
    "reviewer_id", "review_status", *FINAL_HUMAN_LABEL_FIELDS, "human_overall_verdict",
    "human_corrected_answer", "human_notes",
)
ANCHOR_HUMAN_FIELDS = (
    "reviewer_id", "review_status", "human_automatic_assertions_correct",
    "human_context_sufficient", "human_error_category", "human_notes",
)
ADJUDICATION_FIELDS = (
    "adjudicator_id", "adjudication_status", "disagreement_fields", "adjudicated_overall_verdict",
    "adjudicated_corrected_answer", "adjudication_notes",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(prefix: str, *, source_ids: Iterable[str], case_type: str, template_version: str) -> str:
    payload = canonical_json({
        "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
        "source_ids": [str(value) for value in source_ids],
        "case_type": str(case_type),
        "question_template_version": str(template_version),
    })
    return f"{prefix}_{sha256_bytes(payload.encode('utf-8'))[:20].upper()}"


def make_anchor_id(item_type: str, calibration_item_id: str) -> str:
    return stable_id(
        "SC16A", source_ids=(calibration_item_id,), case_type=f"intermediate_anchor:{item_type}",
        template_version=QUESTION_TEMPLATE_VERSION,
    )


def make_case_id(paper_id: str, document_id: str, case_type: str) -> str:
    return stable_id(
        "EC16", source_ids=(paper_id, document_id), case_type=case_type,
        template_version=QUESTION_TEMPLATE_VERSION,
    )


def make_output_id(case_id: str) -> str:
    return stable_id(
        "EO16", source_ids=(case_id,), case_type="api_output",
        template_version=ANSWER_CONTRACT_VERSION,
    )


def make_judgment_id(case_id: str, judge_slot: str) -> str:
    return stable_id(
        "MJ16", source_ids=(case_id, judge_slot), case_type="machine_judgment",
        template_version=JUDGE_TEMPLATE_VERSION,
    )


def make_human_review_id(case_id: str, reviewer_slot: str) -> str:
    return stable_id(
        "HR16", source_ids=(case_id, reviewer_slot), case_type="human_final_output_review",
        template_version=HUMAN_REVIEW_TEMPLATE_VERSION,
    )


def deterministic_hash(seed: int, namespace: str, *values: str) -> str:
    payload = canonical_json({"seed": int(seed), "namespace": namespace, "values": list(values)})
    return sha256_bytes(payload.encode("utf-8"))


def paper_split(seed: int, paper_id: str) -> tuple[str, str]:
    digest = deterministic_hash(seed, "paper_split", paper_id)
    bucket = int(digest, 16) % 4
    return ("holdout" if bucket == 3 else "development"), digest


def validate_run_name(run_name: str) -> str:
    value = str(run_name or "").strip()
    if not value or value.casefold() in RESERVED_RUN_NAMES or not SAFE_RUN_NAME.fullmatch(value):
        raise ValueError(f"unsafe selective-eval run name: {value!r}")
    if "/" in value or "\\" in value:
        raise ValueError(f"unsafe selective-eval run name: {value!r}")
    return value


def resolve_run_target(root: str | Path, run_name: str) -> Path:
    root_value = Path(root)
    if str(root_value).strip() in {"", "."}:
        raise ValueError("refusing current directory as selective-eval root")
    resolved_root = root_value.resolve()
    value = validate_run_name(run_name)
    unresolved = resolved_root / value
    is_junction = getattr(unresolved, "is_junction", lambda: False)
    if unresolved.is_symlink() or is_junction():
        raise ValueError(f"refusing symlink or junction target: {unresolved}")
    target = unresolved.resolve()
    if target == resolved_root or target.parent != resolved_root:
        raise ValueError(f"selective-eval target escapes root: {target}")
    return target


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"expected JSON object at {path}:{line_number}")
                rows.append(value)
    return rows


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f"invalid CSV header: {path}")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError(f"CSV row has unexpected cells: {path}")
    return rows


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


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    atomic_write_text(path, "".join(canonical_json(row) + "\n" for row in rows))


def write_csv(path: str | Path, rows: list[dict[str, Any]], fieldnames: Iterable[str]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=list(fieldnames), extrasaction="raise", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def normalized_hash(path: str | Path) -> str:
    source = Path(path)
    ignored = {"selective_eval_run_name", "created_at_utc"}

    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in sorted(value.items()) if key not in ignored}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    if source.suffix == ".jsonl":
        value: Any = read_jsonl(source)
    elif source.suffix == ".json":
        value = read_json(source)
    elif source.suffix == ".csv":
        value = read_csv(source)
    else:
        value = source.read_text(encoding="utf-8")
    return sha256_bytes(canonical_json(normalize(value)).encode("utf-8"))
