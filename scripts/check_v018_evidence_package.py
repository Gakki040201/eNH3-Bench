from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "v018_evidence_package.schema.json"
EVIDENCE_PACKAGE_SCHEMA_VERSION = "0.18-evidence-package.1"

TOP_LEVEL_FIELDS = {
    "schema_version",
    "package_id",
    "paper_id",
    "source_documents",
    "source_spans",
    "experiment_records",
    "scientific_claims",
    "evidence_links",
    "quality_gates",
    "review_status",
    "provenance",
    "package_hashes",
}
DOCUMENT_FIELDS = {
    "source_document_id",
    "paper_id",
    "document_type",
    "availability_status",
    "source_ref",
    "sha256",
}
SPAN_FIELDS = {
    "source_span_id",
    "paper_id",
    "source_document_id",
    "start_offset",
    "end_offset",
    "text",
    "provenance_type",
}
EXPERIMENT_FIELDS = {"experiment_record_id", "paper_id", "source_span_ids", "measurements"}
CLAIM_FIELDS = {"claim_id", "paper_id", "claim_text", "source_span_ids", "drafting_status"}
LINK_FIELDS = {"evidence_link_id", "paper_id", "claim_id", "source_span_id", "support_role"}
QUALITY_FIELDS = {"passed", "checks", "warnings"}
QUALITY_CHECK_FIELDS = {"gate_id", "status"}
REVIEW_FIELDS = {"status", "reviewer_ids"}
PROVENANCE_FIELDS = {"created_by", "generation_method", "source_asset_refs", "code_commit"}
HASH_FIELDS = {"algorithm", "content_sha256", "source_document_hashes"}
REQUIRED_GATE_IDS = {
    "claim_span_binding",
    "no_hidden_labels",
    "no_secrets",
    "relative_paths",
    "same_paper_binding",
    "unique_ids",
}
REVIEW_RANK = {"machine_drafted": 0, "human_reviewed": 1, "gold_accepted": 2}
PAPER_ID_RE = re.compile(r"^P\d{4}$")
ID_PATTERNS = {
    "package_id": re.compile(r"^EP18_[A-Z0-9]{16,64}$"),
    "source_document_id": re.compile(r"^DOC18_[A-Z0-9]{16,64}$"),
    "experiment_record_id": re.compile(r"^EXP18_[A-Z0-9]{16,64}$"),
    "claim_id": re.compile(r"^CLM18_[A-Z0-9]{16,64}$"),
    "evidence_link_id": re.compile(r"^EL18_[A-Z0-9]{16,64}$"),
    "source_span_id": re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}$"),
}
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
FORBIDDEN_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "chain_of_thought",
    "cookie",
    "credential",
    "credentials",
    "hidden_label",
    "hidden_labels",
    "model_reasoning",
    "password",
    "reasoning",
    "secret",
    "token",
}
FORBIDDEN_KEY_SEGMENTS = {
    "authorization",
    "cookie",
    "credential",
    "credentials",
    "password",
    "secret",
    "token",
}
SECRET_VALUE_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE),
    re.compile(r"\b(?:sk|ghp|github_pat)-?[A-Za-z0-9_]{16,}\b"),
)


def canonical_content_sha256(package: dict[str, Any]) -> str:
    payload = {key: value for key, value in package.items() if key != "package_hashes"}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_evidence_package(
    package: Any,
    *,
    schema_path: str | Path = SCHEMA_PATH,
) -> dict[str, Any]:
    errors: list[str] = []
    _validate_schema_contract(Path(schema_path), errors)
    if not isinstance(package, dict):
        return _result(None, [*errors, "package must be a JSON object"])

    _check_fields(package, TOP_LEVEL_FIELDS, "package", errors)
    _scan_forbidden_content(package, "$", errors)
    if package.get("schema_version") != EVIDENCE_PACKAGE_SCHEMA_VERSION:
        errors.append(f"invalid schema_version: {package.get('schema_version')}")
    _check_id("package_id", package.get("package_id"), errors)
    paper_id = _paper_id(package.get("paper_id"), "paper_id", errors)

    documents = _object_list(package.get("source_documents"), "source_documents", errors, require_nonempty=True)
    spans = _object_list(package.get("source_spans"), "source_spans", errors, require_nonempty=True)
    experiments = _object_list(package.get("experiment_records"), "experiment_records", errors)
    claims = _object_list(package.get("scientific_claims"), "scientific_claims", errors)
    links = _object_list(package.get("evidence_links"), "evidence_links", errors)

    document_index = _validate_documents(documents, paper_id, errors)
    span_index = _validate_spans(spans, paper_id, document_index, errors)
    experiment_ids = _validate_experiments(experiments, paper_id, span_index, errors)
    claim_index = _validate_claims(claims, paper_id, span_index, errors)
    link_ids = _validate_links(links, paper_id, span_index, claim_index, errors)

    all_ids: list[str] = [str(package.get("package_id") or "")]
    all_ids.extend(document_index)
    all_ids.extend(span_index)
    all_ids.extend(experiment_ids)
    all_ids.extend(claim_index)
    all_ids.extend(link_ids)
    duplicates = sorted({value for value in all_ids if value and all_ids.count(value) > 1})
    if duplicates:
        errors.append(f"IDs must be globally unique: {duplicates}")

    review_rank = _validate_review_status(package.get("review_status"), errors)
    for index, claim in enumerate(claims):
        claim_rank = REVIEW_RANK.get(str(claim.get("drafting_status") or ""), -1)
        if review_rank >= 0 and claim_rank > review_rank:
            errors.append(
                f"scientific_claims[{index}].drafting_status exceeds package review_status"
            )
    _validate_quality_gates(package.get("quality_gates"), errors)
    _validate_provenance(package.get("provenance"), errors)
    _validate_hashes(package, documents, errors)
    return _result(package.get("package_id"), errors)


def validate_evidence_package_file(
    package_path: str | Path,
    *,
    schema_path: str | Path = SCHEMA_PATH,
) -> dict[str, Any]:
    path = Path(package_path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return _result(None, [f"cannot read package: {exc}"])
    except json.JSONDecodeError as exc:
        return _result(None, [f"invalid package JSON: {exc.msg} at line {exc.lineno}"])
    return validate_evidence_package(value, schema_path=schema_path)


def _validate_schema_contract(path: Path, errors: list[str]) -> None:
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid or missing schema contract: {exc}")
        return
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append("schema contract must use JSON Schema draft 2020-12")
    if set(schema.get("required") or []) != TOP_LEVEL_FIELDS:
        errors.append("schema contract top-level required fields do not match the frozen contract")
    if schema.get("additionalProperties") is not False:
        errors.append("schema contract must fail closed on unknown top-level fields")


def _validate_documents(
    documents: list[dict[str, Any]],
    package_paper_id: str,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    available_main = 0
    for position, record in enumerate(documents):
        path = f"source_documents[{position}]"
        _check_fields(record, DOCUMENT_FIELDS, path, errors)
        document_id = _check_id("source_document_id", record.get("source_document_id"), errors, path)
        _same_paper(record.get("paper_id"), package_paper_id, path, errors)
        document_type = record.get("document_type")
        if document_type not in {"main", "supplementary"}:
            errors.append(f"{path}.document_type must distinguish main or supplementary")
        status = record.get("availability_status")
        if status not in {"available", "missing", "not_reported"}:
            errors.append(f"{path}.availability_status is invalid")
        source_ref = record.get("source_ref")
        digest = record.get("sha256")
        if status == "available":
            if document_type == "main":
                available_main += 1
            _relative_path(source_ref, f"{path}.source_ref", errors)
            if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
                errors.append(f"{path}.sha256 must be lowercase SHA-256 for an available document")
        elif source_ref is not None or digest is not None:
            errors.append(f"{path} {status} document must serialize null source_ref and sha256")
        if document_id:
            if document_id in index:
                errors.append(f"duplicate source_document_id: {document_id}")
            index[document_id] = record
    if available_main != 1:
        errors.append(f"source_documents must contain exactly one available main document; found {available_main}")
    return index


def _validate_spans(
    spans: list[dict[str, Any]],
    package_paper_id: str,
    documents: dict[str, dict[str, Any]],
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    allowed_provenance = {
        "body", "methods", "results", "table", "figure_caption", "scheme_caption",
        "review_table", "supplementary", "reference", "front_matter", "metadata", "unknown",
    }
    for position, record in enumerate(spans):
        path = f"source_spans[{position}]"
        _check_fields(record, SPAN_FIELDS, path, errors)
        span_id = _check_id("source_span_id", record.get("source_span_id"), errors, path)
        _same_paper(record.get("paper_id"), package_paper_id, path, errors)
        document_id = str(record.get("source_document_id") or "")
        document = documents.get(document_id)
        if document is None:
            errors.append(f"{path}.source_document_id is unbound: {document_id}")
        elif document.get("availability_status") != "available":
            errors.append(f"{path} cannot bind to an unavailable source document")
        start = record.get("start_offset")
        end = record.get("end_offset")
        if not isinstance(start, int) or isinstance(start, bool) or start < 0:
            errors.append(f"{path}.start_offset must be a non-negative integer")
        if not isinstance(end, int) or isinstance(end, bool) or end <= 0:
            errors.append(f"{path}.end_offset must be a positive integer")
        if isinstance(start, int) and isinstance(end, int) and start >= end:
            errors.append(f"{path} offsets must satisfy start_offset < end_offset")
        if not isinstance(record.get("text"), str) or not record.get("text", "").strip():
            errors.append(f"{path}.text must be a non-empty exact evidence anchor")
        if record.get("provenance_type") not in allowed_provenance:
            errors.append(f"{path}.provenance_type is invalid")
        if span_id:
            if span_id in index:
                errors.append(f"duplicate source_span_id: {span_id}")
            index[span_id] = record
    return index


def _validate_experiments(
    experiments: list[dict[str, Any]],
    package_paper_id: str,
    spans: dict[str, dict[str, Any]],
    errors: list[str],
) -> list[str]:
    ids: list[str] = []
    for position, record in enumerate(experiments):
        path = f"experiment_records[{position}]"
        _check_fields(record, EXPERIMENT_FIELDS, path, errors)
        value = _check_id("experiment_record_id", record.get("experiment_record_id"), errors, path)
        if value:
            ids.append(value)
        _same_paper(record.get("paper_id"), package_paper_id, path, errors)
        _bound_span_ids(record.get("source_span_ids"), spans, package_paper_id, path, errors)
        measurements = record.get("measurements")
        if not isinstance(measurements, dict) or not measurements:
            errors.append(f"{path}.measurements must be a non-empty object")
            continue
        for name, measurement in measurements.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]*", str(name)):
                errors.append(f"{path}.measurements has invalid field name: {name}")
            _validate_reportable_value(measurement, f"{path}.measurements.{name}", errors)
    _duplicates("experiment_record_id", ids, errors)
    return ids


def _validate_claims(
    claims: list[dict[str, Any]],
    package_paper_id: str,
    spans: dict[str, dict[str, Any]],
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for position, record in enumerate(claims):
        path = f"scientific_claims[{position}]"
        _check_fields(record, CLAIM_FIELDS, path, errors)
        claim_id = _check_id("claim_id", record.get("claim_id"), errors, path)
        _same_paper(record.get("paper_id"), package_paper_id, path, errors)
        if not isinstance(record.get("claim_text"), str) or not record.get("claim_text", "").strip():
            errors.append(f"{path}.claim_text must be non-empty")
        _bound_span_ids(record.get("source_span_ids"), spans, package_paper_id, path, errors)
        if record.get("drafting_status") not in REVIEW_RANK:
            errors.append(f"{path}.drafting_status is invalid")
        if claim_id:
            if claim_id in index:
                errors.append(f"duplicate claim_id: {claim_id}")
            index[claim_id] = record
    return index


def _validate_links(
    links: list[dict[str, Any]],
    package_paper_id: str,
    spans: dict[str, dict[str, Any]],
    claims: dict[str, dict[str, Any]],
    errors: list[str],
) -> list[str]:
    ids: list[str] = []
    allowed_roles = {"primary_support", "context_only", "contradiction", "insufficient"}
    for position, record in enumerate(links):
        path = f"evidence_links[{position}]"
        _check_fields(record, LINK_FIELDS, path, errors)
        link_id = _check_id("evidence_link_id", record.get("evidence_link_id"), errors, path)
        if link_id:
            ids.append(link_id)
        _same_paper(record.get("paper_id"), package_paper_id, path, errors)
        claim_id = str(record.get("claim_id") or "")
        span_id = str(record.get("source_span_id") or "")
        claim = claims.get(claim_id)
        span = spans.get(span_id)
        if claim is None:
            errors.append(f"{path}.claim_id is unbound: {claim_id}")
        if span is None:
            errors.append(f"{path}.source_span_id is unbound: {span_id}")
        for linked, label in ((claim, "claim"), (span, "span")):
            if linked is not None and linked.get("paper_id") != package_paper_id:
                errors.append(f"{path} cross-paper {label} evidence is forbidden")
        if claim is not None and span_id not in claim.get("source_span_ids", []):
            errors.append(f"{path} must bind a span already cited by the claim")
        if record.get("support_role") not in allowed_roles:
            errors.append(f"{path}.support_role is invalid")
    _duplicates("evidence_link_id", ids, errors)
    return ids


def _validate_reportable_value(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{path} must be an object with explicit status")
        return
    _check_fields(value, {"status", "value"}, path, errors, required={"status"})
    status = value.get("status")
    if status not in {"reported", "missing", "not_reported"}:
        errors.append(f"{path}.status must be reported, missing, or not_reported")
    if status == "reported" and "value" not in value:
        errors.append(f"{path} reported value is missing value")
    if status in {"missing", "not_reported"} and "value" in value:
        errors.append(f"{path} {status} value must not serialize a value")


def _validate_quality_gates(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("quality_gates must be an object")
        return
    _check_fields(value, QUALITY_FIELDS, "quality_gates", errors)
    if not isinstance(value.get("passed"), bool):
        errors.append("quality_gates.passed must be boolean")
    checks = _object_list(value.get("checks"), "quality_gates.checks", errors, require_nonempty=True)
    gate_ids: list[str] = []
    statuses: list[str] = []
    for position, check in enumerate(checks):
        path = f"quality_gates.checks[{position}]"
        _check_fields(check, QUALITY_CHECK_FIELDS, path, errors)
        gate_id = str(check.get("gate_id") or "")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", gate_id):
            errors.append(f"{path}.gate_id is invalid")
        gate_ids.append(gate_id)
        status = str(check.get("status") or "")
        if status not in {"pass", "fail", "not_run"}:
            errors.append(f"{path}.status is invalid")
        statuses.append(status)
    _duplicates("quality gate_id", gate_ids, errors)
    missing_gates = sorted(REQUIRED_GATE_IDS - set(gate_ids))
    if missing_gates:
        errors.append(f"quality_gates missing required checks: {missing_gates}")
    expected_pass = bool(checks) and all(status == "pass" for status in statuses)
    if value.get("passed") is not expected_pass:
        errors.append("quality_gates.passed must equal the conjunction of check statuses")
    warnings = value.get("warnings")
    if not isinstance(warnings, list) or any(not isinstance(item, str) for item in warnings):
        errors.append("quality_gates.warnings must be a string list")


def _validate_review_status(value: Any, errors: list[str]) -> int:
    if not isinstance(value, dict):
        errors.append("review_status must be an object")
        return -1
    _check_fields(value, REVIEW_FIELDS, "review_status", errors)
    status = str(value.get("status") or "")
    if status not in REVIEW_RANK:
        errors.append("review_status.status is invalid")
        rank = -1
    else:
        rank = REVIEW_RANK[status]
    reviewers = value.get("reviewer_ids")
    if not isinstance(reviewers, list) or any(not ID_PATTERNS["source_span_id"].fullmatch(str(item)) for item in reviewers):
        errors.append("review_status.reviewer_ids must be a stable-ID list")
        reviewers = []
    if len(set(reviewers)) != len(reviewers):
        errors.append("review_status.reviewer_ids must be unique")
    if status == "machine_drafted" and reviewers:
        errors.append("machine_drafted package must not claim human reviewers")
    if status in {"human_reviewed", "gold_accepted"} and not reviewers:
        errors.append(f"{status} package requires at least one reviewer_id")
    return rank


def _validate_provenance(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("provenance must be an object")
        return
    _check_fields(value, PROVENANCE_FIELDS, "provenance", errors)
    if value.get("created_by") not in {"offline_audit", "deterministic_pipeline", "human"}:
        errors.append("provenance.created_by is invalid")
    if not isinstance(value.get("generation_method"), str) or not value.get("generation_method", "").strip():
        errors.append("provenance.generation_method must be non-empty")
    refs = value.get("source_asset_refs")
    if not isinstance(refs, list) or not refs:
        errors.append("provenance.source_asset_refs must be a non-empty list")
    else:
        for position, source_ref in enumerate(refs):
            _relative_path(source_ref, f"provenance.source_asset_refs[{position}]", errors)
        if len(set(refs)) != len(refs):
            errors.append("provenance.source_asset_refs must be unique")
    if not re.fullmatch(r"[a-f0-9]{40}", str(value.get("code_commit") or "")):
        errors.append("provenance.code_commit must be a lowercase 40-character commit SHA")


def _validate_hashes(package: dict[str, Any], documents: list[dict[str, Any]], errors: list[str]) -> None:
    value = package.get("package_hashes")
    if not isinstance(value, dict):
        errors.append("package_hashes must be an object")
        return
    _check_fields(value, HASH_FIELDS, "package_hashes", errors)
    if value.get("algorithm") != "sha256":
        errors.append("package_hashes.algorithm must be sha256")
    expected_content = canonical_content_sha256(package)
    if value.get("content_sha256") != expected_content:
        errors.append(
            f"package_hashes.content_sha256 mismatch: expected {expected_content}"
        )
    source_hashes = value.get("source_document_hashes")
    if not isinstance(source_hashes, dict):
        errors.append("package_hashes.source_document_hashes must be an object")
        return
    expected_source_hashes = {
        str(record.get("source_document_id")): str(record.get("sha256"))
        for record in documents
        if record.get("availability_status") == "available"
    }
    if source_hashes != expected_source_hashes:
        errors.append("package_hashes.source_document_hashes must exactly match available source documents")


def _scan_forbidden_content(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).casefold()).strip("_")
            segments = set(normalized.split("_"))
            if normalized in FORBIDDEN_KEYS or segments & FORBIDDEN_KEY_SEGMENTS:
                errors.append(f"forbidden secret, reasoning, or hidden-label field at {path}.{key}")
            _scan_forbidden_content(child, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_forbidden_content(child, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        for pattern in SECRET_VALUE_PATTERNS:
            if pattern.search(value):
                errors.append(f"possible credential value at {path}")
                break


def _check_fields(
    value: dict[str, Any],
    allowed: set[str],
    path: str,
    errors: list[str],
    *,
    required: set[str] | None = None,
) -> None:
    required_fields = allowed if required is None else required
    missing = sorted(required_fields - set(value))
    extra = sorted(set(value) - allowed)
    if missing:
        errors.append(f"{path} missing fields: {missing}")
    if extra:
        errors.append(f"{path} has unknown fields: {extra}")


def _object_list(value: Any, path: str, errors: list[str], *, require_nonempty: bool = False) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{path} must be an array")
        return []
    if require_nonempty and not value:
        errors.append(f"{path} must not be empty")
    records: list[dict[str, Any]] = []
    for position, record in enumerate(value):
        if not isinstance(record, dict):
            errors.append(f"{path}[{position}] must be an object")
        else:
            records.append(record)
    return records


def _paper_id(value: Any, path: str, errors: list[str]) -> str:
    text = str(value or "")
    if not PAPER_ID_RE.fullmatch(text):
        errors.append(f"{path} must be a stable P#### paper ID")
    return text


def _same_paper(value: Any, package_paper_id: str, path: str, errors: list[str]) -> None:
    record_paper_id = _paper_id(value, f"{path}.paper_id", errors)
    if record_paper_id != package_paper_id:
        errors.append(f"{path} crosses paper_id boundary: {record_paper_id} != {package_paper_id}")


def _check_id(kind: str, value: Any, errors: list[str], path: str = "package") -> str:
    text = str(value or "")
    pattern = ID_PATTERNS[kind]
    if not pattern.fullmatch(text):
        errors.append(f"{path}.{kind} is not a stable {kind}")
    return text


def _bound_span_ids(
    value: Any,
    spans: dict[str, dict[str, Any]],
    package_paper_id: str,
    path: str,
    errors: list[str],
) -> None:
    if not isinstance(value, list) or not value:
        errors.append(f"{path}.source_span_ids must be a non-empty list")
        return
    normalized = [str(item) for item in value]
    if len(set(normalized)) != len(normalized):
        errors.append(f"{path}.source_span_ids must be unique")
    for span_id in normalized:
        span = spans.get(span_id)
        if span is None:
            errors.append(f"{path}.source_span_ids contains unbound span: {span_id}")
        elif span.get("paper_id") != package_paper_id:
            errors.append(f"{path}.source_span_ids contains cross-paper span: {span_id}")


def _relative_path(value: Any, path: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path} must be a non-empty relative path")
        return
    text = value.strip()
    pure = PurePosixPath(text)
    if (
        "\\" in text
        or text.startswith("/")
        or text.startswith("//")
        or re.match(r"^[A-Za-z]:", text)
        or pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        errors.append(f"{path} must be repository-relative or package-relative: {text}")


def _duplicates(label: str, values: list[str], errors: list[str]) -> None:
    duplicates = sorted({value for value in values if value and values.count(value) > 1})
    if duplicates:
        errors.append(f"duplicate {label} values: {duplicates}")


def _result(package_id: Any, errors: list[str]) -> dict[str, Any]:
    unique_errors = sorted(set(errors))
    return {
        "schema_version": EVIDENCE_PACKAGE_SCHEMA_VERSION,
        "package_id": str(package_id or ""),
        "result": "FAIL" if unique_errors else "PASS",
        "error_count": len(unique_errors),
        "errors": unique_errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail-closed validator for an M018 per-paper evidence package.")
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--schema", type=Path, default=SCHEMA_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate_evidence_package_file(args.package, schema_path=args.schema)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
