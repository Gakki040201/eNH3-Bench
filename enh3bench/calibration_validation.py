"""Independent validator for v0.16 semantic calibration packages."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from typing import Any, Iterable

from enh3bench.calibration_package import (
    EXCERPT_LIMITS,
    SOURCE_FILES,
    bounded_excerpt,
    output_hashes,
    tree_hash,
)
from enh3bench.calibration_sampling import sample_links, sample_papers, sample_spans, sampling_hash
from enh3bench.calibration_schema import (
    ADJUDICATION_HUMAN_FIELDS,
    CALIBRATION_PROFILE,
    CALIBRATION_SCHEMA_VERSION,
    HUMAN_FIELDS_BY_TYPE,
    read_csv,
    read_json,
    read_jsonl,
    resolve_calibration_target,
    sha256_file,
    validate_item,
    validate_review_row,
)


FRAME_PATHS = {
    "span": "sampling/span_sampling_frame.jsonl",
    "paper": "sampling/paper_sampling_frame.jsonl",
    "document": "sampling/document_sampling_frame.jsonl",
    "link": "sampling/link_sampling_frame.jsonl",
}
REVIEW_PATHS = {item_type: f"review/{item_type}_review.csv" for item_type in FRAME_PATHS}
REQUIRED_PACKAGE_FILES = tuple(FRAME_PATHS.values()) + tuple(REVIEW_PATHS.values()) + (
    "review/adjudication_template.csv",
    "reports/calibration_summary.json",
    "reports/stratum_coverage.csv",
    "reports/validation_summary.json",
    "reports/calibration_metrics_template.json",
    "previews/calibration_preview.md",
    "manifests/calibration_manifest.json",
)
OPTIONAL_PACKAGE_FILES = ("reports/calibration_metrics_summary.json",)
ALLOWED_PACKAGE_FILES = frozenset((*REQUIRED_PACKAGE_FILES, *OPTIONAL_PACKAGE_FILES))
UNSUPPORTED_BINARY_SUFFIXES = frozenset({
    ".7z", ".bin", ".bmp", ".doc", ".docx", ".exe", ".gif", ".gz", ".jpeg", ".jpg",
    ".pdf", ".png", ".ppt", ".pptx", ".tar", ".tif", ".tiff", ".xls", ".xlsx", ".zip",
})
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?i)(?:(?<![A-Za-z0-9])[A-Z]:[\\/]|\\\\[A-Za-z0-9_.-]+[\\/][A-Za-z0-9_.$ -]+|(?<![A-Za-z0-9])/(?:home|users|var|tmp)/|file://)"
)
USERNAME_PATH_PATTERN = re.compile(r"(?i)[A-Z]:[\\/](?:Users|Documents and Settings)[\\/][^\\/\s]+")
SECRET_PATTERN = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}"
)
ID_PATTERNS = {
    "span": re.compile(r"^CR15_[0-9A-F]{20}$"),
    "link": re.compile(r"^CRL15_[0-9A-F]{20}$"),
    "node": re.compile(r"^CRN15_[0-9A-F]{20}$"),
}


def validate_calibration_package(
    *,
    calibration_run_name: str,
    calibration_root: str | Path = "data/calibration",
    cleanroom_root: str | Path = "data/cleanroom",
    require_blank_human_fields: bool = False,
    allow_building_manifest: bool = False,
) -> dict[str, Any]:
    run_dir = resolve_calibration_target(calibration_root, calibration_run_name)
    errors: list[str] = []
    warnings: list[str] = []
    counts = {
        "human_label_nonempty_count": 0,
        "absolute_path_count": 0,
        "username_path_count": 0,
        "secret_count": 0,
        "full_document_embedding_count": 0,
        "duplicate_calibration_item_ids": 0,
        "unresolved_source_ids": 0,
    }
    missing = _validate_package_inventory(run_dir, errors)
    if missing:
        return _result(errors, warnings, counts, {})
    try:
        manifest = read_json(run_dir / "manifests/calibration_manifest.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid_manifest:{exc}")
        return _result(errors, warnings, counts, {})
    source_run_name = str(manifest.get("source_cleanroom_run_name") or "")
    cleanroom_run_dir = Path(cleanroom_root) / source_run_name
    source_paths = {name: cleanroom_run_dir / relative for name, relative in SOURCE_FILES.items()}
    if any(not path.is_file() for path in source_paths.values()):
        errors.append("missing_authoritative_cleanroom_source")
        return _result(errors, warnings, counts, manifest)
    try:
        documents = read_jsonl(source_paths["documents"])
        nodes = read_jsonl(source_paths["source_nodes"])
        semantics = read_jsonl(source_paths["semantic_spans"])
        links = read_jsonl(source_paths["evidence_links"])
        papers = read_jsonl(source_paths["papers"])
        frames = {item_type: read_jsonl(run_dir / relative) for item_type, relative in FRAME_PATHS.items()}
        reviews = {item_type: read_csv(run_dir / relative) for item_type, relative in REVIEW_PATHS.items()}
        adjudication = read_csv(run_dir / "review/adjudication_template.csv")
        validation_summary = read_json(run_dir / "reports/validation_summary.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid_package_or_source_data:{exc}")
        return _result(errors, warnings, counts, manifest)

    _validate_manifest_identity(manifest, calibration_run_name, source_paths, allow_building_manifest, errors)
    _validate_validation_summary(
        validation_summary, manifest, run_dir / "reports/validation_summary.json",
        allow_building_manifest, errors,
    )
    all_item_ids: list[str] = []
    for item_type, rows in frames.items():
        for index, row in enumerate(rows, 1):
            all_item_ids.append(str(row.get("calibration_item_id") or ""))
            item_errors = validate_item(item_type, row, require_blank=require_blank_human_fields)
            errors.extend(f"{item_type}_frame:{index}:{error}" for error in item_errors)
            if str(row.get("calibration_run_name") or "") != calibration_run_name:
                errors.append(f"{item_type}_frame:{index}:calibration_run_name_mismatch")
            if str(row.get("source_cleanroom_run_name") or "") != source_run_name:
                errors.append(f"{item_type}_frame:{index}:source_run_name_mismatch")
            if str(row.get("source_cleanroom_manifest_sha256") or "") != str(manifest.get("source_cleanroom_manifest_sha256") or ""):
                errors.append(f"{item_type}_frame:{index}:source_manifest_sha_mismatch")
            if str(row.get("sampling_hash") or "") != sampling_hash(
                int(manifest.get("seed") or 0), _underlying_id(item_type, row)
            ):
                errors.append(f"{item_type}_frame:{index}:invalid_sampling_hash")
            if int(row.get("sampling_rank") or 0) <= 0:
                errors.append(f"{item_type}_frame:{index}:invalid_sampling_rank")
            counts["human_label_nonempty_count"] += _human_nonempty(item_type, row)
    duplicate_ids = sum(value - 1 for value in Counter(all_item_ids).values() if value > 1)
    counts["duplicate_calibration_item_ids"] = duplicate_ids
    if duplicate_ids:
        errors.append(f"duplicate_calibration_item_ids:{duplicate_ids}")

    for item_type, rows in reviews.items():
        _validate_review_rows(
            item_type, frames[item_type], rows, require_blank_human_fields, counts, errors
        )
    for index, row in enumerate(adjudication, 2):
        for field in ("schema_version", "calibration_profile", "calibration_run_name", "source_cleanroom_run_name", "source_cleanroom_manifest_sha256", "record_created_by_stage"):
            if not str(row.get(field) or "").strip():
                errors.append(f"adjudication:row_{index}:missing_common_field:{field}")
        nonempty = [field for field in ADJUDICATION_HUMAN_FIELDS if str(row.get(field) or "").strip()]
        counts["human_label_nonempty_count"] += len(nonempty)
        if require_blank_human_fields and nonempty:
            errors.append(f"adjudication:row_{index}:nonblank_human_fields:{','.join(nonempty)}")

    documents_by_id = {str(item["document_id"]): item for item in documents}
    nodes_by_id = {str(item["source_node_id"]): item for item in nodes}
    semantics_by_id = {str(item["cleanroom_span_id"]): item for item in semantics}
    links_by_id = {str(item["evidence_link_id"]): item for item in links}
    papers_by_id = {str(item["paper_id"]): item for item in papers}
    _validate_spans(frames["span"], semantics_by_id, nodes_by_id, links_by_id, semantics_by_id, counts, errors)
    _validate_papers(frames["paper"], papers_by_id, documents_by_id, counts, errors)
    _validate_documents(frames["document"], documents_by_id, nodes_by_id, counts, errors)
    _validate_links(frames["link"], links_by_id, semantics_by_id, counts, errors)
    _validate_paper_document_alignment(frames["paper"], frames["document"], errors)
    _validate_sampling_counts(manifest, frames, errors, warnings)
    _validate_recomputed_sampling(manifest, frames, semantics, papers, links, errors)
    _validate_hashes(manifest, run_dir, cleanroom_run_dir, source_paths, errors)

    path_counts = _scan_package_text(run_dir)
    for key, value in path_counts.items():
        counts[key] = value
    if counts["absolute_path_count"]:
        errors.append(f"absolute_paths_detected:{counts['absolute_path_count']}")
    if counts["username_path_count"]:
        errors.append(f"username_paths_detected:{counts['username_path_count']}")
    if counts["secret_count"]:
        errors.append(f"secrets_detected:{counts['secret_count']}")
    counts["full_document_embedding_count"] += _full_document_embedding_count(frames, documents_by_id)
    if counts["full_document_embedding_count"]:
        errors.append(f"full_document_embeddings_detected:{counts['full_document_embedding_count']}")
    if require_blank_human_fields and counts["human_label_nonempty_count"]:
        errors.append(f"human_fields_are_not_blank:{counts['human_label_nonempty_count']}")
    if counts["unresolved_source_ids"]:
        errors.append(f"unresolved_source_ids:{counts['unresolved_source_ids']}")

    expected_counts = manifest.get("selected_sample_counts") or {}
    for item_type, rows in frames.items():
        counts[f"selected_{item_type}_count"] = len(rows)
        if int(expected_counts.get(item_type) or -1) != len(rows):
            errors.append(f"manifest_selected_count_mismatch:{item_type}")
    for manifest_field, count_field in (
        ("human_label_nonempty_count", "human_label_nonempty_count"),
        ("absolute_path_count", "absolute_path_count"),
        ("full_document_embedding_count", "full_document_embedding_count"),
        ("duplicate_calibration_item_ids", "duplicate_calibration_item_ids"),
        ("unresolved_source_ids", "unresolved_source_ids"),
    ):
        if manifest_field == "human_label_nonempty_count" and not require_blank_human_fields:
            continue
        if int(manifest.get(manifest_field) or 0) != counts[count_field]:
            errors.append(f"manifest_safety_count_mismatch:{manifest_field}")
    errors = sorted(set(errors))
    warnings = sorted(set(warnings))
    return _result(errors, warnings, counts, manifest)


def _validate_package_inventory(run_dir: Path, errors: list[str]) -> list[str]:
    actual = {
        path.relative_to(run_dir).as_posix()
        for path in run_dir.rglob("*")
        if path.is_file()
    }
    missing = sorted(set(REQUIRED_PACKAGE_FILES) - actual)
    unexpected = sorted(actual - ALLOWED_PACKAGE_FILES)
    errors.extend(f"missing_package_file:{relative}" for relative in missing)
    errors.extend(f"unexpected_package_file:{relative}" for relative in unexpected)
    for relative in sorted(actual):
        path = run_dir / relative
        if path.suffix.casefold() in UNSUPPORTED_BINARY_SUFFIXES or _looks_binary(path):
            errors.append(f"unsupported_binary_file:{relative}")
    return missing


def _looks_binary(path: Path) -> bool:
    try:
        payload = path.read_bytes()[:8192]
    except OSError:
        return True
    if b"\x00" in payload:
        return True
    try:
        payload.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def _validate_review_rows(
    item_type: str,
    frame_rows: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
    require_blank: bool,
    counts: dict[str, int],
    errors: list[str],
) -> None:
    frame_by_id = {str(row.get("calibration_item_id") or ""): row for row in frame_rows}
    seen_item_ids: set[str] = set()
    seen_observations: set[tuple[str, str]] = set()
    allowed_fields = set(HUMAN_FIELDS_BY_TYPE[item_type])
    for index, row in enumerate(review_rows, 2):
        item_id = str(row.get("calibration_item_id") or "")
        reviewer_id = str(row.get("reviewer_id") or "").strip()
        observation = (item_id, reviewer_id)
        if observation in seen_observations:
            errors.append(f"duplicate_review_observation:{item_type}:{item_id}:{reviewer_id or '<blank>'}")
        seen_observations.add(observation)
        source = frame_by_id.get(item_id)
        if source is None:
            errors.append(f"extra_review_row:{item_type}:{item_id}")
        else:
            seen_item_ids.add(item_id)
            actual_type = str(row.get("item_type") or "")
            if actual_type != item_type:
                errors.append(f"review_item_type_mismatch:{item_type}:{item_id}:{actual_type}")
            fields = (set(source) | set(row)) - allowed_fields
            for field in sorted(fields):
                if field not in source:
                    # CSV headers are the union of frame keys; an empty cell represents an
                    # optional key absent from this particular JSONL record.
                    if field in row and str(row.get(field) or "") == "":
                        continue
                    errors.append(f"review_automatic_field_mismatch:{item_type}:{item_id}:{field}")
                    continue
                if field not in row:
                    errors.append(f"review_automatic_field_mismatch:{item_type}:{item_id}:{field}")
                    continue
                decoded, decode_error = _decode_review_automatic_value(row.get(field), source[field])
                if decode_error or decoded != source[field]:
                    errors.append(f"review_automatic_field_mismatch:{item_type}:{item_id}:{field}")
        review_errors = validate_review_row(item_type, row, require_blank=require_blank)
        errors.extend(f"{item_type}_review:row_{index}:{error}" for error in review_errors)
        counts["human_label_nonempty_count"] += _human_nonempty(item_type, row)
    for item_id in sorted(set(frame_by_id) - seen_item_ids):
        errors.append(f"missing_review_row:{item_type}:{item_id}")


def _decode_review_automatic_value(raw_value: Any, expected: Any) -> tuple[Any, bool]:
    raw = "" if raw_value is None else str(raw_value)
    try:
        if expected is None:
            return (None, False) if raw == "" else (raw, True)
        if isinstance(expected, bool):
            normalized = raw.strip().casefold()
            if normalized not in {"true", "false"}:
                return raw, True
            return normalized == "true", False
        if isinstance(expected, int):
            return int(raw.strip()), False
        if isinstance(expected, float):
            return float(raw.strip()), False
        if isinstance(expected, list):
            decoded = json.loads(raw)
            return decoded, not isinstance(decoded, list)
        if isinstance(expected, dict):
            decoded = json.loads(raw)
            return decoded, not isinstance(decoded, dict)
        if isinstance(expected, str):
            return raw, False
        return raw, raw != str(expected)
    except (TypeError, ValueError, json.JSONDecodeError):
        return raw, True


def _validate_validation_summary(
    summary: dict[str, Any], manifest: dict[str, Any], summary_path: Path,
    allow_building: bool, errors: list[str],
) -> None:
    for field in (
        "schema_version", "calibration_profile", "calibration_run_name",
        "source_cleanroom_run_name", "source_cleanroom_manifest_sha256",
    ):
        if summary.get(field) != manifest.get(field):
            errors.append(f"validation_summary_field_mismatch:{field}")
    if summary.get("record_created_by_stage") != "validation":
        errors.append("validation_summary_field_mismatch:record_created_by_stage")
    building = manifest.get("status") == "building" and allow_building
    if building:
        if summary.get("result") != "PENDING":
            errors.append(f"building_validation_summary_not_pending:{summary.get('result')}")
    else:
        if summary.get("result") != "PASS":
            errors.append(f"completed_validation_summary_not_pass:{summary.get('result')}")
        try:
            error_count = int(summary.get("error_count") or 0)
        except (TypeError, ValueError):
            error_count = -1
        if error_count != 0:
            errors.append("completed_validation_summary_error_count_nonzero")
        if summary.get("errors") != []:
            errors.append("completed_validation_summary_errors_nonempty")
        expected_hash = str(manifest.get("validation_summary_sha256") or "")
        if not expected_hash or expected_hash != sha256_file(summary_path):
            errors.append("validation_summary_sha256_mismatch")


def _validate_manifest_identity(
    manifest: dict[str, Any], run_name: str, source_paths: dict[str, Path],
    allow_building: bool, errors: list[str],
) -> None:
    if manifest.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
        errors.append("manifest_invalid_schema_version")
    if manifest.get("calibration_profile") != CALIBRATION_PROFILE:
        errors.append("manifest_invalid_profile")
    if manifest.get("calibration_run_name") != run_name:
        errors.append("manifest_run_name_mismatch")
    status = manifest.get("status")
    if status != "completed" and not (allow_building and status == "building"):
        errors.append(f"manifest_not_completed:{status}")
    expected_sha = sha256_file(source_paths["final_manifest"])
    if manifest.get("source_cleanroom_manifest_sha256") != expected_sha:
        errors.append("source_manifest_sha256_mismatch")
    source_manifest = read_json(source_paths["final_manifest"])
    source_validation = read_json(source_paths["validation_summary"])
    if source_manifest.get("pipeline_status") != "completed":
        errors.append("source_manifest_not_completed")
    if source_validation.get("result") != "PASS" or int(source_validation.get("error_count") or 0):
        errors.append("source_validation_not_pass")


def _validate_spans(
    rows: list[dict[str, Any]], semantics: dict[str, dict[str, Any]], nodes: dict[str, dict[str, Any]],
    links: dict[str, dict[str, Any]], all_semantics: dict[str, dict[str, Any]],
    counts: dict[str, int], errors: list[str],
) -> None:
    nodes_by_paragraph = {
        (str(item.get("document_id") or ""), str(item.get("paragraph_uid") or "")): item
        for item in nodes.values()
    }
    for index, row in enumerate(rows, 1):
        span_id = str(row.get("cleanroom_span_id") or "")
        source = semantics.get(span_id)
        node_id = str(row.get("source_node_id") or "")
        node = nodes.get(node_id)
        if source is None or not ID_PATTERNS["span"].fullmatch(span_id):
            counts["unresolved_source_ids"] += 1
            errors.append(f"span:{index}:unresolved_cleanroom_span_id")
            continue
        if node is None or not ID_PATTERNS["node"].fullmatch(node_id):
            counts["unresolved_source_ids"] += 1
            errors.append(f"span:{index}:unresolved_source_node_id")
            continue
        for field in ("paper_id", "document_id", "source_node_id", "source_start_offset", "source_end_offset", "source_locator"):
            if row.get(field) != source.get(field):
                errors.append(f"span:{index}:source_field_mismatch:{field}")
        start, end = int(row.get("source_start_offset", -1)), int(row.get("source_end_offset", -1))
        node_start, node_end = int(node.get("source_start_offset", -2)), int(node.get("source_end_offset", -2))
        if start < node_start or end <= start or end > node_end:
            errors.append(f"span:{index}:invalid_source_offsets")
        relative_start, relative_end = start - node_start, end - node_start
        node_slice = str(node.get("source_text") or "")[relative_start:relative_end]
        if str(source.get("source_text") or "") != node_slice:
            errors.append(f"span:{index}:target_text_source_node_slice_mismatch")
        _check_excerpt(row, "target_excerpt", str(source.get("source_text") or ""), 700, f"span:{index}", errors)
        for context_field, id_field, adjacency_field in (
            ("previous_context_excerpt", "previous_context_source_node_id", "previous_paragraph_uid"),
            ("next_context_excerpt", "next_context_source_node_id", "next_paragraph_uid"),
        ):
            context_id = str(row.get(id_field) or "")
            adjacent_uid = str(node.get(adjacency_field) or "")
            expected_context = nodes_by_paragraph.get((str(node.get("document_id") or ""), adjacent_uid)) if adjacent_uid else None
            expected_id = str((expected_context or {}).get("source_node_id") or "")
            if adjacent_uid and expected_context is None:
                errors.append(f"span:{index}:unresolved_authoritative_context:{adjacency_field}:{adjacent_uid}")
            if context_id != expected_id:
                errors.append(f"span:{index}:context_source_node_id_mismatch:{id_field}")
            if expected_context is None:
                if str(row.get(context_field) or ""):
                    errors.append(f"span:{index}:context_excerpt_without_authoritative_neighbor:{context_field}")
            else:
                if expected_context.get("paper_id") != source.get("paper_id") or expected_context.get("document_id") != source.get("document_id"):
                    errors.append(f"span:{index}:cross_document_context:{context_field}")
                _check_excerpt(
                    row, context_field, str(expected_context.get("source_text") or ""), 500,
                    f"span:{index}", errors,
                )
        linked_ids = row.get("linked_evidence_ids") or []
        linked_span_ids = row.get("linked_evidence_span_ids") or []
        if not isinstance(linked_ids, list) or not isinstance(linked_span_ids, list):
            errors.append(f"span:{index}:invalid_linked_evidence_lists")
            continue
        if len(linked_ids) != len(linked_span_ids):
            errors.append(f"span:{index}:linked_evidence_list_length_mismatch")
        first_evidence: dict[str, Any] | None = None
        for evidence_index, link_id in enumerate(linked_ids):
            link = links.get(str(link_id))
            if link is None:
                counts["unresolved_source_ids"] += 1
                errors.append(f"span:{index}:unresolved_link:{link_id}")
                continue
            if str(link.get("target_cleanroom_span_id") or "") != span_id:
                errors.append(f"span:{index}:linked_evidence_target_mismatch:{link_id}")
            if str(link.get("paper_id") or "") != str(source.get("paper_id") or ""):
                errors.append(f"span:{index}:cross_paper_link")
            if evidence_index >= len(linked_span_ids):
                continue
            evidence_span_id = str(linked_span_ids[evidence_index])
            if str(link.get("evidence_cleanroom_span_id") or "") != evidence_span_id:
                errors.append(f"span:{index}:linked_evidence_endpoint_mismatch:{evidence_index}")
            evidence = all_semantics.get(evidence_span_id)
            if evidence is None:
                counts["unresolved_source_ids"] += 1
                errors.append(f"span:{index}:unresolved_linked_evidence_span:{evidence_span_id}")
                continue
            if evidence.get("paper_id") != source.get("paper_id"):
                errors.append(f"span:{index}:cross_paper_linked_evidence:{evidence_span_id}")
            if evidence_index == 0:
                first_evidence = evidence
        if first_evidence is not None:
            _check_excerpt(
                row, "linked_evidence_excerpt", str(first_evidence.get("source_text") or ""), 700,
                f"span:{index}", errors,
            )
        elif str(row.get("linked_evidence_excerpt") or ""):
            errors.append(f"span:{index}:orphan_linked_evidence_excerpt")


def _validate_papers(
    rows: list[dict[str, Any]], source: dict[str, dict[str, Any]], documents: dict[str, dict[str, Any]],
    counts: dict[str, int], errors: list[str],
) -> None:
    for index, row in enumerate(rows, 1):
        paper = source.get(str(row.get("paper_id") or ""))
        if paper is None:
            counts["unresolved_source_ids"] += 1
            errors.append(f"paper:{index}:unresolved_paper_id")
            continue
        if str(row.get("document_id") or "") not in documents:
            counts["unresolved_source_ids"] += 1
            errors.append(f"paper:{index}:unresolved_document_id")
        for output_field, source_field in (
            ("document_id", "document_id"), ("paper_admissibility_status", "paper_admissibility_status"),
            ("document_genre", "document_genre"), ("document_reaction_family", "document_reaction_family"),
            ("candidate_count", "candidate_span_count"), ("semantic_span_count", "semantic_span_count"),
            ("primary_eligible_count", "primary_eligible_span_count"),
        ):
            if row.get(output_field) != paper.get(source_field):
                errors.append(f"paper:{index}:source_field_mismatch:{output_field}")


def _validate_documents(
    rows: list[dict[str, Any]], source: dict[str, dict[str, Any]], nodes: dict[str, dict[str, Any]],
    counts: dict[str, int], errors: list[str],
) -> None:
    nodes_by_document: dict[str, list[dict[str, Any]]] = {}
    for node in nodes.values():
        nodes_by_document.setdefault(str(node["document_id"]), []).append(node)
    for index, row in enumerate(rows, 1):
        document_id = str(row.get("document_id") or "")
        document = source.get(document_id)
        if document is None:
            counts["unresolved_source_ids"] += 1
            errors.append(f"document:{index}:unresolved_document_id")
            continue
        for field in ("paper_id", "document_ref", "document_body_sha256", "document_genre", "document_reaction_family"):
            if row.get(field) != document.get(field):
                errors.append(f"document:{index}:source_field_mismatch:{field}")
        document_nodes = sorted(nodes_by_document.get(document_id, []), key=lambda item: int(item["source_start_offset"]))
        front_nodes = [node for node in document_nodes if str(node.get("document_region") or "") == "front_matter"]
        expected = "\n\n".join(str(node.get("source_text") or "") for node in (front_nodes or document_nodes[:2]))
        _check_excerpt(row, "front_matter_excerpt", expected, 700, f"document:{index}", errors)


def _validate_links(
    rows: list[dict[str, Any]], source: dict[str, dict[str, Any]], semantics: dict[str, dict[str, Any]],
    counts: dict[str, int], errors: list[str],
) -> None:
    endpoint_pairs: set[tuple[str, str]] = set()
    for index, row in enumerate(rows, 1):
        link_id = str(row.get("evidence_link_id") or "")
        link = source.get(link_id)
        target_id, evidence_id = str(row.get("target_span_id") or ""), str(row.get("evidence_span_id") or "")
        target, evidence = semantics.get(target_id), semantics.get(evidence_id)
        if link is None or not ID_PATTERNS["link"].fullmatch(link_id):
            counts["unresolved_source_ids"] += 1
            errors.append(f"link:{index}:unresolved_link_id")
            continue
        if target is None or evidence is None:
            counts["unresolved_source_ids"] += 1
            errors.append(f"link:{index}:unresolved_endpoint")
            continue
        pair = (target_id, evidence_id)
        if target_id == evidence_id:
            errors.append(f"link:{index}:self_link")
        if pair in endpoint_pairs:
            errors.append(f"link:{index}:duplicate_endpoint_pair")
        endpoint_pairs.add(pair)
        if target_id != str(link.get("target_cleanroom_span_id") or "") or evidence_id != str(link.get("evidence_cleanroom_span_id") or ""):
            errors.append(f"link:{index}:endpoint_mismatch")
        same_paper = str(target.get("paper_id") or "") == str(evidence.get("paper_id") or "") == str(row.get("paper_id") or "")
        if not same_paper or row.get("same_paper") is not True:
            errors.append(f"link:{index}:cross_paper_or_same_paper_flag_mismatch")
        _check_excerpt(row, "target_excerpt", str(target.get("source_text") or ""), 700, f"link:{index}", errors)
        _check_excerpt(row, "evidence_excerpt", str(evidence.get("source_text") or ""), 700, f"link:{index}", errors)


def _validate_paper_document_alignment(
    papers: list[dict[str, Any]], documents: list[dict[str, Any]], errors: list[str]
) -> None:
    paper_pairs = {(str(item["paper_id"]), str(item["document_id"])) for item in papers}
    document_pairs = {(str(item["paper_id"]), str(item["document_id"])) for item in documents}
    if paper_pairs != document_pairs or len(paper_pairs) != len(papers) or len(document_pairs) != len(documents):
        errors.append("paper_document_sample_alignment_failure")


def _validate_sampling_counts(
    manifest: dict[str, Any], frames: dict[str, list[dict[str, Any]]], errors: list[str], warnings: list[str]
) -> None:
    requested = manifest.get("requested_sample_counts") or {}
    link_coverage = manifest.get("link_sampling_coverage") or {}
    for item_type in ("span", "paper", "document"):
        if len(frames[item_type]) != int(requested.get(item_type) or -1):
            errors.append(f"requested_sample_count_not_met:{item_type}")
    link_requested = int(requested.get("link") or -1)
    if len(frames["link"]) != link_requested:
        shortage = int(link_coverage.get("shortage") or 0)
        if shortage != link_requested - len(frames["link"]) or shortage <= 0:
            errors.append("link_shortage_not_explicit")
        else:
            warnings.append(f"link_sample_shortage:{shortage}")
    coverage = manifest.get("span_stratum_coverage") or {}
    for stratum, values in coverage.items():
        try:
            requested_count = int(values["requested"])
            available = int(values["available"])
            selected = int(values["selected"])
            shortage = int(values["shortage"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"invalid_stratum_coverage:{stratum}")
            continue
        if selected > available or shortage != max(0, requested_count - selected):
            errors.append(f"inconsistent_stratum_coverage:{stratum}")
        if shortage and stratum != "high_risk_reservoir":
            warnings.append(f"span_stratum_shortage:{stratum}:{shortage}")


def _validate_recomputed_sampling(
    manifest: dict[str, Any], frames: dict[str, list[dict[str, Any]]],
    semantics: list[dict[str, Any]], papers: list[dict[str, Any]], links: list[dict[str, Any]],
    errors: list[str],
) -> None:
    requested = manifest.get("requested_sample_counts") or {}
    seed = int(manifest.get("seed") or 0)
    try:
        expected_spans, span_coverage = sample_spans(semantics, int(requested["span"]), seed)
        expected_papers = sample_papers(papers, semantics, int(requested["paper"]), seed)
        expected_links, link_coverage = sample_links(links, semantics, int(requested["link"]), seed)
    except (KeyError, TypeError, ValueError, AssertionError) as exc:
        errors.append(f"sampling_recomputation_failed:{exc}")
        return
    comparisons = (
        ("span", "cleanroom_span_id", expected_spans),
        ("paper", "paper_id", expected_papers),
        ("link", "evidence_link_id", expected_links),
    )
    for item_type, field, expected in comparisons:
        actual_ids = [str(item.get(field) or "") for item in frames[item_type]]
        expected_ids = [str(item.get(field) or "") for item in expected]
        if actual_ids != expected_ids:
            errors.append(f"deterministic_sampling_mismatch:{item_type}")
    if manifest.get("span_stratum_coverage") != span_coverage:
        errors.append("span_stratum_coverage_recomputation_mismatch")
    if manifest.get("link_sampling_coverage") != link_coverage:
        errors.append("link_sampling_coverage_recomputation_mismatch")


def _validate_hashes(
    manifest: dict[str, Any], run_dir: Path, cleanroom_run_dir: Path,
    source_paths: dict[str, Path], errors: list[str],
) -> None:
    for relative, expected in (manifest.get("input_file_hashes") or {}).items():
        path = cleanroom_run_dir / str(relative)
        if not path.is_file() or sha256_file(path) != expected:
            errors.append(f"input_file_hash_mismatch:{relative}")
    current_output = output_hashes(run_dir)
    for relative, expected in (manifest.get("output_file_hashes") or {}).items():
        if relative in REVIEW_PATHS.values():
            # Review sheets are intentionally mutable only in human fields; their automatic
            # content is protected by schema-aware comparison against the sampling frames.
            continue
        if current_output.get(relative) != expected:
            errors.append(f"output_file_hash_mismatch:{relative}")
    cleanroom_hash = tree_hash(cleanroom_run_dir)
    if manifest.get("source_cleanroom_tree_sha256_before") != cleanroom_hash or manifest.get("source_cleanroom_tree_sha256_after") != cleanroom_hash:
        errors.append("cleanroom_tree_hash_mismatch")
    gold_hash = tree_hash(Path("data/gold"))
    if manifest.get("gold_tree_sha256_before") != gold_hash or manifest.get("gold_tree_sha256_after") != gold_hash:
        errors.append("gold_tree_hash_mismatch")


def _check_excerpt(
    row: dict[str, Any], field: str, source_text: str, limit: int, prefix: str, errors: list[str]
) -> None:
    value = str(row.get(field) or "")
    if len(value) > limit:
        errors.append(f"{prefix}:excerpt_too_long:{field}")
    if value != bounded_excerpt(source_text, limit):
        errors.append(f"{prefix}:excerpt_not_source_derived:{field}")


def _scan_package_text(run_dir: Path) -> dict[str, int]:
    values = {"absolute_path_count": 0, "username_path_count": 0, "secret_count": 0}
    for path in sorted(item for item in run_dir.rglob("*") if item.is_file()):
        strings: list[str] = []
        try:
            if path.suffix.lower() == ".jsonl":
                strings = list(_iter_strings(read_jsonl(path)))
            elif path.suffix.lower() == ".json":
                strings = list(_iter_strings(read_json(path)))
            elif path.suffix.lower() == ".csv":
                strings = list(_iter_strings(read_csv(path)))
            else:
                strings = [path.read_text(encoding="utf-8", errors="replace")]
        except (OSError, ValueError, json.JSONDecodeError):
            strings = [path.read_text(encoding="utf-8", errors="replace")]
        for text in strings:
            values["absolute_path_count"] += len(ABSOLUTE_PATH_PATTERN.findall(text))
            values["username_path_count"] += len(USERNAME_PATH_PATTERN.findall(text))
            values["secret_count"] += len(SECRET_PATTERN.findall(text))
    return values


def _iter_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _iter_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_strings(item)


def _full_document_embedding_count(
    frames: dict[str, list[dict[str, Any]]], documents: dict[str, dict[str, Any]]
) -> int:
    count = 0
    for rows in frames.values():
        for row in rows:
            if any(key in row for key in ("document_body", "full_document_text", "full_text", "pdf_bytes")):
                count += 1
            document = documents.get(str(row.get("document_id") or ""))
            if document:
                document_length = int(document.get("document_character_count") or 0)
                for field, limit in EXCERPT_LIMITS.items():
                    value = str(row.get(field) or "")
                    if len(value) > limit or (document_length > 0 and len(value) >= document_length):
                        count += 1
    return count


def _human_nonempty(item_type: str, row: dict[str, Any]) -> int:
    return sum(bool(str(row.get(field) or "").strip()) for field in HUMAN_FIELDS_BY_TYPE[item_type])


def _underlying_id(item_type: str, row: dict[str, Any]) -> str:
    return str(row.get({
        "span": "cleanroom_span_id", "paper": "paper_id",
        "document": "document_id", "link": "evidence_link_id",
    }[item_type]) or "")


def _result(
    errors: list[str], warnings: list[str], counts: dict[str, int], manifest: dict[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "calibration_profile": CALIBRATION_PROFILE,
        "calibration_run_name": manifest.get("calibration_run_name"),
        "source_cleanroom_run_name": manifest.get("source_cleanroom_run_name"),
        "source_cleanroom_manifest_sha256": manifest.get("source_cleanroom_manifest_sha256"),
        "record_created_by_stage": "validation",
        "result": "PASS" if not errors else "FAIL",
        "error_count": len(errors), "warning_count": len(warnings),
        "errors": errors, "warnings": warnings, "counts": counts,
    }
