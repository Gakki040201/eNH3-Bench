"""Validation and normalized reproducibility checks for clean-room outputs."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from enh3bench.cleanroom_schema import read_jsonl, validate_record


CORE_REQUIRED_OUTPUTS = (
    "config/resolved_config.json",
    "ingest/input_manifest.json",
    "documents/document_ledger.jsonl",
    "documents/document_ledger.csv",
    "source_nodes/section_nodes.jsonl",
    "source_nodes/paragraph_nodes.jsonl",
    "source_nodes/source_nodes.jsonl",
    "candidates/candidate_spans.jsonl",
    "candidates/candidate_spans.csv",
    "semantics/semantic_spans.jsonl",
    "semantics/semantic_spans.csv",
    "links/evidence_links.jsonl",
    "links/evidence_link_index.json",
    "papers/paper_records.jsonl",
    "papers/paper_records.csv",
    "review/semantic_review_sample.md",
    "review/semantic_review_sample.csv",
    "database/final_database.jsonl",
    "database/final_database.csv",
    "manifests/stage_manifest.json",
)
COMPLETED_REQUIRED_OUTPUTS = CORE_REQUIRED_OUTPUTS + (
    "reports/cleanroom_validation_report.md",
    "reports/cleanroom_validation_summary.json",
    "manifests/final_manifest.json",
)
NORMALIZED_FILES = {
    "documents": "documents/document_ledger.jsonl",
    "source_nodes": "source_nodes/source_nodes.jsonl",
    "candidate_spans": "candidates/candidate_spans.jsonl",
    "semantic_spans": "semantics/semantic_spans.jsonl",
    "links": "links/evidence_links.jsonl",
    "paper_records": "papers/paper_records.jsonl",
}
_ABSOLUTE_WINDOWS = re.compile(r"(?i)(?<![A-Z])[A-Z]:[\\/]")


def validate_cleanroom_run(run_dir: str | Path, *, require_completed: bool = True) -> dict[str, Any]:
    root = Path(run_dir)
    errors: list[str] = []
    warnings: list[str] = []
    required = COMPLETED_REQUIRED_OUTPUTS if require_completed else CORE_REQUIRED_OUTPUTS
    missing = [relative for relative in required if not (root / relative).is_file()]
    errors.extend(f"missing_required_output:{relative}" for relative in missing)
    documents = _safe_jsonl(root / "documents/document_ledger.jsonl", errors)
    nodes = _safe_jsonl(root / "source_nodes/source_nodes.jsonl", errors)
    candidates = _safe_jsonl(root / "candidates/candidate_spans.jsonl", errors)
    semantics = _safe_jsonl(root / "semantics/semantic_spans.jsonl", errors)
    links = _safe_jsonl(root / "links/evidence_links.jsonl", errors)
    papers = _safe_jsonl(root / "papers/paper_records.jsonl", errors)
    database = _safe_jsonl(root / "database/final_database.jsonl", errors)
    for record_type, records in (
        ("document", documents), ("source_node", nodes), ("candidate", candidates),
        ("semantic", semantics), ("paper", papers),
    ):
        for index, record in enumerate(records):
            for message in validate_record(record_type, record):
                errors.append(f"schema:{record_type}:{index}:{message}")
    document_ids = [str(item.get("document_id") or "") for item in documents]
    node_ids = [str(item.get("source_node_id") or "") for item in nodes]
    candidate_ids = [str(item.get("cleanroom_span_id") or "") for item in candidates]
    semantic_ids = [str(item.get("cleanroom_span_id") or "") for item in semantics]
    document_lengths = {
        str(item.get("document_id") or ""): int(item.get("document_character_count") or 0)
        for item in documents
    }
    node_index = {str(item.get("source_node_id") or ""): item for item in nodes}
    semantic_index = {str(item.get("cleanroom_span_id") or ""): item for item in semantics}
    unresolved = 0
    invalid_offsets = 0
    cross_paragraph = 0
    for node in nodes:
        start = int(node.get("source_start_offset") or 0)
        end = int(node.get("source_end_offset") or 0)
        text = str(node.get("source_text") or "")
        document_length = document_lengths.get(str(node.get("document_id") or ""))
        if document_length is None:
            unresolved += 1
        elif start < 0 or end <= start or end > document_length or len(text) != end - start:
            invalid_offsets += 1
    for candidate in candidates:
        node = node_index.get(str(candidate.get("source_node_id") or ""))
        if node is None:
            unresolved += 1
            continue
        start = int(candidate.get("source_start_offset") or 0)
        end = int(candidate.get("source_end_offset") or 0)
        node_start = int(node.get("source_start_offset") or 0)
        node_end = int(node.get("source_end_offset") or 0)
        if start < 0 or end <= start or start < node_start or end > node_end:
            invalid_offsets += 1
            cross_paragraph += 1
        else:
            local_start, local_end = start - node_start, end - node_start
            if str(node.get("source_text") or "")[local_start:local_end] != str(candidate.get("source_text") or ""):
                invalid_offsets += 1
    pairs: list[tuple[str, str]] = []
    link_ids = [str(item.get("evidence_link_id") or "") for item in links]
    if any(not value for value in link_ids):
        errors.append("missing_evidence_link_id")
    cross_paper = self_links = context_upgrades = 0
    for link in links:
        target_id = str(link.get("target_cleanroom_span_id") or "")
        evidence_id = str(link.get("evidence_cleanroom_span_id") or "")
        pairs.append((target_id, evidence_id))
        target = semantic_index.get(target_id)
        evidence = semantic_index.get(evidence_id)
        if target is None or evidence is None:
            errors.append(f"unresolved_link_endpoint:{target_id}:{evidence_id}")
            continue
        if str(target.get("paper_id")) != str(evidence.get("paper_id")) or str(link.get("paper_id")) != str(target.get("paper_id")):
            cross_paper += 1
        if target_id == evidence_id:
            self_links += 1
        if link.get("is_context_only") and target.get("primary_semantic_eligibility") and target.get("primary_semantic_eligibility_source") == "evidence_link":
            context_upgrades += 1
    reference_primary = sum(
        item.get("provenance_type") == "reference" and item.get("primary_semantic_eligibility") for item in semantics
    )
    caption_primary = sum(
        item.get("provenance_type") == "figure_or_scheme_caption" and item.get("primary_semantic_eligibility") for item in semantics
    )
    review_table_primary = sum(
        item.get("provenance_type") == "review_table" and item.get("primary_semantic_eligibility") for item in semantics
    )
    context_primary = sum(
        item.get("maximum_support_role") != "primary_support" and item.get("primary_semantic_eligibility") for item in semantics
    )
    absolute_paths = 0
    for path in root.rglob("*") if root.exists() else []:
        if path.is_file() and path.suffix.casefold() in {".json", ".jsonl", ".csv", ".md"}:
            try:
                absolute_paths += len(_ABSOLUTE_WINDOWS.findall(path.read_text(encoding="utf-8", errors="ignore")))
            except OSError:
                warnings.append(f"unreadable_export:{path.name}")
    failed_stage_completed_manifest = 0
    final_path = root / "manifests/final_manifest.json"
    stage_path = root / "manifests/stage_manifest.json"
    if final_path.exists() and stage_path.exists():
        final = json.loads(final_path.read_text(encoding="utf-8"))
        stages = json.loads(stage_path.read_text(encoding="utf-8")).get("stages", {})
        if final.get("pipeline_status") == "completed" and any(value.get("status") != "completed" for value in stages.values()):
            failed_stage_completed_manifest = 1
        if require_completed and final.get("pipeline_status") != "completed":
            errors.append(f"pipeline_not_completed:{final.get('pipeline_status')}")
    elif require_completed:
        errors.append("missing_completed_manifest")
    review_rows = _read_csv(root / "review/semantic_review_sample.csv")
    review_ids = [str(item.get("cleanroom_span_id") or "") for item in review_rows]
    human_fields = (
        "human_scope_correct", "human_ownership_correct", "human_claim_type_correct",
        "human_family_correct", "human_primary_eligibility_correct", "human_notes",
    )
    counts: dict[str, Any] = {
        "document_count": len(documents),
        "source_node_count": len(nodes),
        "candidate_span_count": len(candidates),
        "semantic_span_count": len(semantics),
        "primary_eligible_count": sum(bool(item.get("primary_semantic_eligibility")) for item in semantics),
        "paper_record_count": len(papers),
        "review_sample_count": len(review_rows),
        "duplicate_review_cleanroom_span_id_count": len(review_ids) - len(set(review_ids)),
        "review_human_fields_filled_count": sum(
            bool(str(row.get(field) or "").strip()) for row in review_rows for field in human_fields
        ),
        "review_full_document_embedding_count": sum(
            any(field in row for field in ("full_body_text", "document_body_text", "full_document"))
            for row in review_rows
        ),
        "evidence_link_count": len(links),
        "duplicate_document_id_count": len(document_ids) - len(set(document_ids)),
        "duplicate_source_node_id_count": len(node_ids) - len(set(node_ids)),
        "duplicate_cleanroom_span_id_count": max(len(candidate_ids) - len(set(candidate_ids)), len(semantic_ids) - len(set(semantic_ids))),
        "unresolved_source_mapping_count": unresolved,
        "invalid_source_offset_count": invalid_offsets,
        "cross_paragraph_candidate_count": cross_paragraph,
        "cross_paper_link_count": cross_paper,
        "self_link_count": self_links,
        "duplicate_link_count": len(pairs) - len(set(pairs)),
        "duplicate_evidence_link_id_count": len(link_ids) - len(set(link_ids)),
        "reference_primary_support_count": reference_primary,
        "caption_primary_support_count": caption_primary,
        "review_table_primary_support_count": review_table_primary,
        "context_only_primary_upgrade_count": context_upgrades + context_primary,
        "absolute_runtime_path_in_export_count": absolute_paths,
        "completed_manifest_with_failed_stage_count": failed_stage_completed_manifest,
        "paper_admissibility_distribution": dict(sorted(Counter(str(item.get("paper_admissibility_status") or "") for item in papers).items())),
        "unclear_family_count": sum(item.get("effective_reaction_family") == "unclear" for item in semantics),
        "needs_review_count": sum(bool(item.get("needs_review")) for item in semantics),
    }
    zero_fields = (
        "duplicate_document_id_count", "duplicate_source_node_id_count", "duplicate_cleanroom_span_id_count",
        "unresolved_source_mapping_count", "invalid_source_offset_count", "cross_paragraph_candidate_count",
        "cross_paper_link_count", "self_link_count", "duplicate_link_count", "duplicate_evidence_link_id_count",
        "reference_primary_support_count",
        "caption_primary_support_count", "review_table_primary_support_count", "context_only_primary_upgrade_count",
        "absolute_runtime_path_in_export_count", "completed_manifest_with_failed_stage_count",
        "duplicate_review_cleanroom_span_id_count", "review_human_fields_filled_count",
        "review_full_document_embedding_count",
    )
    errors.extend(f"nonzero_diagnostic:{field}:{counts[field]}" for field in zero_fields if counts[field])
    if len(papers) != len(documents):
        errors.append(f"paper_document_count_mismatch:{len(papers)}:{len(documents)}")
    if len(database) != len(papers):
        errors.append(f"final_database_paper_count_mismatch:{len(database)}:{len(papers)}")
    return {
        "result": "PASS" if not errors else "FAIL",
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "counts": counts,
    }


def compare_normalized_runs(left_run_dir: str | Path, right_run_dir: str | Path) -> dict[str, Any]:
    left_root, right_root = Path(left_run_dir), Path(right_run_dir)
    file_results: dict[str, Any] = {}
    first_difference: dict[str, Any] | None = None
    for label, relative in NORMALIZED_FILES.items():
        left = [_normalize(item) for item in read_jsonl(left_root / relative)]
        right = [_normalize(item) for item in read_jsonl(right_root / relative)]
        left_text = json.dumps(left, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        right_text = json.dumps(right, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        import hashlib
        left_hash = hashlib.sha256(left_text.encode("utf-8")).hexdigest()
        right_hash = hashlib.sha256(right_text.encode("utf-8")).hexdigest()
        match = left_hash == right_hash
        file_results[label] = {"match": match, "left_hash": left_hash, "right_hash": right_hash}
        if not match and first_difference is None:
            first_difference = _first_difference(label, left, right)
    return {
        "reproducibility_match": all(value["match"] for value in file_results.values()),
        "files": file_results,
        "first_difference": first_difference,
    }


def _normalize(value: Any) -> Any:
    ignored = {"run_name", "created_at", "started_at", "finished_at", "log_path", "runtime_path"}
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in sorted(value.items()) if key not in ignored}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _first_difference(label: str, left: list[Any], right: list[Any]) -> dict[str, Any]:
    if len(left) != len(right):
        return {"file": label, "field": "record_count", "left": len(left), "right": len(right)}
    for index, (left_record, right_record) in enumerate(zip(left, right)):
        if left_record != right_record:
            keys = sorted(set(left_record) | set(right_record))
            field = next(key for key in keys if left_record.get(key) != right_record.get(key))
            return {"file": label, "record_index": index, "field": field, "left": left_record.get(field), "right": right_record.get(field)}
    return {"file": label, "field": "unknown"}


def _safe_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return read_jsonl(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid_jsonl:{path.name}:{exc}")
        return []


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
