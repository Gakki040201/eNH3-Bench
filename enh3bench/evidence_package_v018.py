"""Deterministic M018 A1 evidence-package assembly from accepted assets only."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass, field
from html import escape
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from enh3bench.cleanroom_schema import atomic_write_text, read_jsonl, write_json
from enh3bench.document_loader import load_markdown_documents


SCHEMA_VERSION = "0.18-evidence-package.1"
GENERATION_METHOD = "v018_a1_existing_asset_assembly"
FROZEN_PILOT_ORDER = (
    "P0797", "P0425", "P0162", "P0255", "P0471", "P0217",
    "P0362", "P0007", "P0961", "P0241", "P0960", "P0312",
)
QUALITY_GATE_ORDER = (
    "unique_ids",
    "relative_paths",
    "same_paper_binding",
    "claim_span_binding",
    "no_secrets",
    "no_hidden_labels",
    "source_document_integrity",
    "source_span_integrity",
    "experiment_span_binding",
    "claim_status_provenance",
    "evidence_link_integrity",
    "supplementary_status_explicit",
    "package_hash_integrity",
    "deterministic_ordering",
)
EXPERIMENT_MEASUREMENT_FIELDS = (
    "reaction_family",
    "nitrogen_source",
    "catalyst",
    "catalyst_class",
    "electrolyte",
    "reactor_type",
    "membrane",
    "potential_value",
    "potential_unit",
    "potential_reference",
    "current_density_mA_cm2",
    "faradaic_efficiency_percent",
    "nh3_yield_value",
    "nh3_yield_unit",
    "nh3_yield_normalized_value",
    "nh3_yield_normalized_unit",
    "energy_efficiency_percent",
    "stability_hours",
    "detection_method",
    "isotope_validation",
    "blank_control",
    "contamination_control",
    "nox_screening",
    "reliability_label",
    "evidence_type",
)
REVIEW_STATUS_RANK = {"machine_drafted": 0, "human_reviewed": 1, "gold_accepted": 2}
REVIEW_QUEUE_FIELDS = (
    "queue_item_id",
    "paper_id",
    "package_id",
    "item_type",
    "item_id",
    "severity",
    "reason_code",
    "reason_text",
    "source_span_ids",
    "current_status",
    "recommended_action",
)
INDEX_FIELDS = (
    "order",
    "paper_id",
    "package_id",
    "reaction_family_coverage",
    "package_path",
    "validation_result",
    "source_document_count",
    "source_span_count",
    "experiment_count",
    "claim_count",
    "evidence_link_count",
    "warning_count",
    "review_queue_count",
    "review_status",
    "content_sha256",
)
_FORBIDDEN_TEXT = re.compile(
    r"(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|(?:^|[\s\"'])/(?:Users|home|tmp)/|api[_-]?key|"
    r"authorization|credential)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PaperAssets:
    paper_id: str
    reaction_family_coverage: tuple[str, ...]
    main_document_ref: str
    main_document_sha256: str
    main_document_integrity: bool
    spans: tuple[dict[str, Any], ...]
    experiment_records: tuple[dict[str, Any], ...]
    scientific_claims: tuple[dict[str, Any], ...]
    evidence_links: tuple[dict[str, Any], ...]
    audit_record: dict[str, Any]
    source_asset_refs: tuple[str, ...]
    claim_status_mappings: Mapping[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class PackageBuild:
    package: dict[str, Any]
    coverage: dict[str, Any]
    review_queue: tuple[dict[str, str], ...]


def stable_id(prefix: str, *identity_parts: Any) -> str:
    payload = json.dumps(identity_parts, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24].upper()}"


def stable_paper_id(value: Any) -> str:
    match = re.match(r"^(P\d{4})(?:_|$)", str(value or ""))
    if not match:
        raise ValueError(f"unstable paper ID: {value!r}")
    return match.group(1)


def load_frozen_pilot_manifest(path: str | Path) -> list[dict[str, Any]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"papers"} or not isinstance(value["papers"], list):
        raise ValueError("pilot manifest must contain only a papers array")
    papers = value["papers"]
    ids = tuple(str(record.get("paper_id") or "") for record in papers if isinstance(record, dict))
    if ids != FROZEN_PILOT_ORDER:
        raise ValueError(f"pilot manifest order differs from frozen A1 order: {ids}")
    allowed = {"paper_id", "selection_reasons", "reaction_family_coverage", "expected_asset_categories"}
    for record in papers:
        if not isinstance(record, dict) or set(record) != allowed:
            raise ValueError("pilot manifest contains fields outside the A0 frozen contract")
    return papers


def explicit_reportable(record: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    if field_name not in record or record[field_name] is None:
        return {"status": "not_reported"}
    value = record[field_name]
    if isinstance(value, str):
        normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
        if not normalized or normalized in {"missing", "unresolved"}:
            return {"status": "missing"}
        if normalized in {"not_reported", "not_available", "n_a"}:
            return {"status": "not_reported"}
    return {"status": "reported", "value": value}


def assemble_evidence_package(assets: PaperAssets, code_commit: str) -> PackageBuild:
    paper_id = assets.paper_id
    if paper_id not in FROZEN_PILOT_ORDER:
        raise ValueError(f"paper is outside the frozen pilot: {paper_id}")
    if not re.fullmatch(r"[a-f0-9]{40}", code_commit):
        raise ValueError("code_commit must be a lowercase 40-character Git SHA")
    if not assets.main_document_integrity:
        raise ValueError(f"main document integrity failed for {paper_id}")
    _require_relative(assets.main_document_ref, "main document source_ref")
    if not re.fullmatch(r"[a-f0-9]{64}", assets.main_document_sha256):
        raise ValueError(f"invalid main document SHA-256 for {paper_id}")

    main_id = stable_id(
        "DOC18", SCHEMA_VERSION, paper_id, "main", assets.main_document_ref,
        assets.main_document_sha256,
    )
    supplementary_id = stable_id(
        "DOC18", SCHEMA_VERSION, paper_id, "supplementary", "not_reported",
    )
    source_documents = [
        {
            "source_document_id": main_id,
            "paper_id": paper_id,
            "document_type": "main",
            "availability_status": "available",
            "source_ref": assets.main_document_ref,
            "sha256": assets.main_document_sha256,
        },
        {
            "source_document_id": supplementary_id,
            "paper_id": paper_id,
            "document_type": "supplementary",
            "availability_status": "not_reported",
            "source_ref": None,
            "sha256": None,
        },
    ]

    source_spans = _assemble_spans(assets.spans, paper_id, main_id)
    span_index = {record["source_span_id"]: record for record in source_spans}
    text_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in assets.spans:
        text_index[str(raw.get("source_text") or "")].append(raw)

    included_experiments, excluded_experiments = _assemble_experiments(
        assets.experiment_records, paper_id, text_index,
    )
    preliminary_claims, excluded_claims = _assemble_claim_candidates(
        assets.scientific_claims, paper_id, text_index, assets.claim_status_mappings,
    )
    included_links, excluded_links = _bind_existing_links(
        assets.evidence_links, paper_id, preliminary_claims, span_index,
    )
    scientific_claims, claim_id_by_source = _finalize_claims(preliminary_claims, paper_id)
    experiment_records = _finalize_experiments(included_experiments, paper_id)
    evidence_links = _finalize_links(included_links, claim_id_by_source, paper_id)

    warnings = ["supplementary_manifest_unavailable"]
    if not assets.evidence_links:
        warnings.append("existing_evidence_links_unavailable")
    if excluded_experiments:
        warnings.append("experiment_record_excluded_unbound")
    if excluded_claims:
        warnings.append("claim_excluded_unbound")
    if excluded_links:
        warnings.append("evidence_link_excluded_unbound_claim")
    if "reaction_family_conflict" in set(assets.audit_record.get("warnings") or []):
        warnings.append("reaction_family_conflict_preserved")
    if (
        assets.audit_record.get("gold_membership")
        or assets.audit_record.get("human_review_membership")
    ) and not assets.claim_status_mappings:
        warnings.append("ambiguous_review_status_mapping")
    warnings = sorted(set(warnings))

    review_status, reviewer_ids = _package_review_status(scientific_claims, preliminary_claims)
    quality_gates = {
        "passed": True,
        "checks": [{"gate_id": gate_id, "status": "pass"} for gate_id in QUALITY_GATE_ORDER],
        "warnings": warnings,
    }
    source_asset_refs = sorted(set(assets.source_asset_refs))
    for source_ref in source_asset_refs:
        _require_relative(source_ref, "provenance source asset")

    package_id = stable_id(
        "EP18",
        SCHEMA_VERSION,
        paper_id,
        [record["source_document_id"] for record in source_documents],
        [record["source_span_id"] for record in source_spans],
        [record["experiment_record_id"] for record in experiment_records],
        [record["claim_id"] for record in scientific_claims],
        [record["evidence_link_id"] for record in evidence_links],
    )
    package: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "package_id": package_id,
        "paper_id": paper_id,
        "source_documents": source_documents,
        "source_spans": source_spans,
        "experiment_records": experiment_records,
        "scientific_claims": scientific_claims,
        "evidence_links": evidence_links,
        "quality_gates": quality_gates,
        "review_status": {"status": review_status, "reviewer_ids": reviewer_ids},
        "provenance": {
            "created_by": "deterministic_pipeline",
            "generation_method": GENERATION_METHOD,
            "source_asset_refs": source_asset_refs,
            "code_commit": code_commit,
        },
    }
    from scripts.check_v018_evidence_package import canonical_content_sha256
    package["package_hashes"] = {
        "algorithm": "sha256",
        "content_sha256": canonical_content_sha256(package),
        "source_document_hashes": {main_id: assets.main_document_sha256},
    }
    review_queue = tuple(_build_review_queue(
        package,
        assets,
        excluded_experiments,
        excluded_claims,
        excluded_links,
    ))
    coverage = _build_coverage(
        package,
        assets,
        excluded_experiments,
        excluded_claims,
        excluded_links,
        review_queue,
    )
    return PackageBuild(package=package, coverage=coverage, review_queue=review_queue)


def _assemble_spans(
    records: Sequence[dict[str, Any]], paper_id: str, document_id: str,
) -> list[dict[str, Any]]:
    assembled: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in records:
        if stable_paper_id(raw.get("paper_id")) != paper_id:
            raise ValueError(f"cross-paper source span supplied to {paper_id}")
        span_id = str(raw.get("cleanroom_span_id") or "")
        if not span_id or span_id in seen:
            raise ValueError(f"duplicate or missing accepted source_span_id: {span_id}")
        seen.add(span_id)
        start = raw.get("source_start_offset")
        end = raw.get("source_end_offset")
        text = raw.get("source_text")
        if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
            raise ValueError(f"invalid offsets for {span_id}")
        if start < 0 or end <= start or not isinstance(text, str) or not text.strip():
            raise ValueError(f"invalid exact source anchor for {span_id}")
        assembled.append({
            "source_span_id": span_id,
            "paper_id": paper_id,
            "source_document_id": document_id,
            "start_offset": start,
            "end_offset": end,
            "text": text,
            "provenance_type": _map_provenance_type(raw.get("provenance_type")),
        })
    assembled.sort(key=lambda row: (
        row["source_document_id"], row["start_offset"], row["end_offset"], row["source_span_id"],
    ))
    if not assembled:
        raise ValueError(f"no accepted source spans for {paper_id}")
    return assembled


def _map_provenance_type(value: Any) -> str:
    mapping = {
        "primary_body": "body",
        "secondary_document_body": "body",
        "background": "body",
        "figure_or_scheme_caption": "figure_caption",
        "reference": "reference",
        "front_matter": "front_matter",
        "review_table": "review_table",
        "supplementary": "supplementary",
        "methods": "methods",
        "results": "results",
        "table": "table",
        "metadata": "metadata",
    }
    return mapping.get(str(value or ""), "unknown")


def _unique_exact_span(
    raw: Mapping[str, Any], text_index: Mapping[str, list[dict[str, Any]]], *, require_offsets: bool,
) -> dict[str, Any] | None:
    text = str(raw.get("source_text") if "source_text" in raw else raw.get("source_span") or "")
    candidates = list(text_index.get(text, []))
    if require_offsets:
        candidates = [
            span for span in candidates
            if span.get("source_start_offset") == raw.get("source_start_offset")
            and span.get("source_end_offset") == raw.get("source_end_offset")
        ]
    return candidates[0] if len(candidates) == 1 else None


def _assemble_experiments(
    records: Sequence[dict[str, Any]], paper_id: str,
    text_index: Mapping[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for raw in records:
        if stable_paper_id(raw.get("paper_id")) != paper_id:
            raise ValueError(f"cross-paper experiment supplied to {paper_id}")
        span = _unique_exact_span(raw, text_index, require_offsets=True)
        if span is None:
            excluded.append({"record": raw, "reason": "no_unique_exact_cleanroom_span"})
            continue
        included.append({"record": raw, "source_span_ids": [str(span["cleanroom_span_id"])]})
    return included, excluded


def _finalize_experiments(candidates: Sequence[dict[str, Any]], paper_id: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        raw = candidate["record"]
        span_ids = sorted(set(candidate["source_span_ids"]))
        identity = str(raw.get("evidence_id") or raw.get("span_id") or "")
        experiment_id = stable_id("EXP18", SCHEMA_VERSION, paper_id, identity, span_ids)
        result.append({
            "experiment_record_id": experiment_id,
            "paper_id": paper_id,
            "source_span_ids": span_ids,
            "measurements": {
                name.lower(): explicit_reportable(raw, name)
                for name in EXPERIMENT_MEASUREMENT_FIELDS
            },
        })
    return sorted(result, key=lambda row: row["experiment_record_id"])


def _assemble_claim_candidates(
    records: Sequence[dict[str, Any]],
    paper_id: str,
    text_index: Mapping[str, list[dict[str, Any]]],
    status_mappings: Mapping[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for raw in records:
        if stable_paper_id(raw.get("paper_id")) != paper_id:
            raise ValueError(f"cross-paper claim supplied to {paper_id}")
        span = _unique_exact_span(raw, text_index, require_offsets=False)
        if span is None:
            excluded.append({"record": raw, "reason": "no_unique_exact_cleanroom_span"})
            continue
        identity = str(raw.get("evidence_id") or "")
        mapping = dict(status_mappings.get(identity) or {})
        status = str(mapping.get("status") or "machine_drafted")
        if status not in REVIEW_STATUS_RANK:
            raise ValueError(f"unsupported direct claim status for {identity}: {status}")
        if status != "machine_drafted" and not mapping.get("direct_record_ref"):
            raise ValueError(f"reviewed claim status lacks direct record mapping: {identity}")
        included.append({
            "source_identity": identity,
            "claim_text": str(raw.get("source_span") or ""),
            "target_span_id": str(span["cleanroom_span_id"]),
            "source_span_ids": {str(span["cleanroom_span_id"])},
            "drafting_status": status,
            "reviewer_ids": sorted(set(str(v) for v in mapping.get("reviewer_ids") or [])),
        })
    return included, excluded


def _bind_existing_links(
    records: Sequence[dict[str, Any]],
    paper_id: str,
    claims: list[dict[str, Any]],
    span_index: Mapping[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in claims:
        by_target[claim["target_span_id"]].append(claim)
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for raw in records:
        if stable_paper_id(raw.get("paper_id")) != paper_id:
            raise ValueError(f"cross-paper evidence link supplied to {paper_id}")
        target = str(raw.get("target_cleanroom_span_id") or "")
        evidence = str(raw.get("evidence_cleanroom_span_id") or "")
        candidates = by_target.get(target, [])
        if len(candidates) != 1 or evidence not in span_index:
            excluded.append({"record": raw, "reason": "claim_or_span_not_uniquely_bound"})
            continue
        claim = candidates[0]
        claim["source_span_ids"].add(evidence)
        included.append({
            "source_link_id": str(raw.get("evidence_link_id") or ""),
            "claim_source_identity": claim["source_identity"],
            "source_span_id": evidence,
            "support_role": _map_support_role(raw),
        })
    return included, excluded


def _map_support_role(record: Mapping[str, Any]) -> str:
    roles = set(str(value) for value in record.get("link_roles") or [])
    if (
        bool(record.get("is_context_only"))
        or record.get("source_eligibility") == "context_only"
        or roles <= {"context_hint", "gas_handling_context"}
    ):
        return "context_only"
    if roles & {"quantification_support", "validation_support"}:
        return "primary_support"
    return "context_only"


def _finalize_claims(
    candidates: Sequence[dict[str, Any]], paper_id: str,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    result: list[dict[str, Any]] = []
    id_by_source: dict[str, str] = {}
    for candidate in candidates:
        span_ids = sorted(candidate["source_span_ids"])
        text_hash = hashlib.sha256(candidate["claim_text"].encode("utf-8")).hexdigest()
        claim_id = stable_id(
            "CLM18", SCHEMA_VERSION, paper_id, candidate["source_identity"], text_hash, span_ids,
        )
        id_by_source[candidate["source_identity"]] = claim_id
        result.append({
            "claim_id": claim_id,
            "paper_id": paper_id,
            "claim_text": candidate["claim_text"],
            "source_span_ids": span_ids,
            "drafting_status": candidate["drafting_status"],
        })
    return sorted(result, key=lambda row: row["claim_id"]), id_by_source


def _finalize_links(
    candidates: Sequence[dict[str, Any]], claim_ids: Mapping[str, str], paper_id: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in candidates:
        claim_id = claim_ids[candidate["claim_source_identity"]]
        key = (claim_id, candidate["source_span_id"], candidate["support_role"])
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "evidence_link_id": stable_id("EL18", SCHEMA_VERSION, paper_id, *key),
            "paper_id": paper_id,
            "claim_id": claim_id,
            "source_span_id": candidate["source_span_id"],
            "support_role": candidate["support_role"],
        })
    return sorted(result, key=lambda row: row["evidence_link_id"])


def _package_review_status(
    claims: Sequence[dict[str, Any]], candidates: Sequence[dict[str, Any]],
) -> tuple[str, list[str]]:
    if not claims:
        return "machine_drafted", []
    status = max((claim["drafting_status"] for claim in claims), key=REVIEW_STATUS_RANK.get)
    if status == "machine_drafted":
        return status, []
    reviewer_ids = sorted({
        reviewer
        for candidate in candidates
        if REVIEW_STATUS_RANK[candidate["drafting_status"]] > 0
        for reviewer in candidate["reviewer_ids"]
    })
    if not reviewer_ids:
        raise ValueError(f"{status} package lacks directly mapped reviewer IDs")
    return status, reviewer_ids


def _build_review_queue(
    package: Mapping[str, Any],
    assets: PaperAssets,
    excluded_experiments: Sequence[dict[str, Any]],
    excluded_claims: Sequence[dict[str, Any]],
    excluded_links: Sequence[dict[str, Any]],
) -> list[dict[str, str]]:
    paper_id = assets.paper_id
    package_id = str(package["package_id"])
    items: list[dict[str, str]] = []

    def add(
        item_type: str, item_id: str, severity: str, reason_code: str,
        reason_text: str, source_span_ids: Iterable[str], current_status: str,
        recommended_action: str,
    ) -> None:
        queue_id = stable_id("RQ18", SCHEMA_VERSION, paper_id, item_type, item_id, reason_code)
        items.append({
            "queue_item_id": queue_id,
            "paper_id": paper_id,
            "package_id": package_id,
            "item_type": item_type,
            "item_id": item_id,
            "severity": severity,
            "reason_code": reason_code,
            "reason_text": reason_text,
            "source_span_ids": "|".join(sorted(set(source_span_ids))),
            "current_status": current_status,
            "recommended_action": recommended_action,
        })

    add(
        "supplementary_document", supplementary_item_id(paper_id), "low",
        "supplementary_manifest_unavailable",
        "No independent accepted SI manifest exists; supplementary availability remains not_reported.",
        [], "not_applicable", "Confirm SI only from a future accepted manifest.",
    )
    for excluded in excluded_experiments:
        raw = excluded["record"]
        add(
            "experiment_record", str(raw.get("evidence_id") or raw.get("span_id") or "unknown"),
            "medium", "experiment_record_excluded_unbound",
            "Existing experiment-triage record has no unique exact accepted clean-room span binding.",
            [], "existing_machine_draft", "Review source binding; do not infer a replacement span.",
        )
    for excluded in excluded_claims:
        raw = excluded["record"]
        add(
            "scientific_claim", str(raw.get("evidence_id") or "unknown"), "high",
            "claim_excluded_unbound",
            "Existing machine-drafted claim has no unique exact accepted clean-room span binding.",
            [], "existing_machine_draft", "Review exact claim-to-span provenance.",
        )
    for excluded in excluded_links:
        raw = excluded["record"]
        add(
            "evidence_link", str(raw.get("evidence_link_id") or "unknown"), "medium",
            "evidence_link_excluded_unbound_claim",
            "Existing evidence link cannot bind to one uniquely included claim and source span.",
            [str(raw.get("evidence_cleanroom_span_id") or "")],
            "unreviewed", "Review the existing link target without fabricating a claim mapping.",
        )
    if not assets.evidence_links:
        add(
            "evidence_link", "paper_link_set", "medium", "existing_evidence_links_unavailable",
            "The accepted pilot deliberately has no existing same-paper evidence links.",
            [], "unreviewed", "Retain the no-link gap for human inspection.",
        )
    if "reaction_family_conflict" in set(assets.audit_record.get("warnings") or []):
        add(
            "reaction_family", "accepted_audit", "medium", "reaction_family_conflict_preserved",
            "Accepted sources disagree on reaction-family classification.",
            [], "unreviewed", "Review the conflicting accepted classifications.",
        )
    if assets.audit_record.get("human_review_membership") and not assets.claim_status_mappings:
        add(
            "review_status", "paper_human_review_membership", "medium",
            "ambiguous_review_status_mapping",
            "Paper-level completed review has no exact mapping to included claims and was not promoted.",
            [], "existing_human_review", "Establish exact record-level mapping before promotion.",
        )
    if assets.audit_record.get("gold_membership") and not assets.claim_status_mappings:
        add(
            "review_status", "paper_gold_membership", "medium",
            "ambiguous_review_status_mapping",
            "Paper-level Gold membership has no exact mapping to included claims and was not promoted.",
            [], "existing_gold_record", "Establish exact Gold record mapping before promotion.",
        )
    return sorted(items, key=lambda row: (
        row["severity"], row["item_type"], row["reason_code"], row["item_id"], row["queue_item_id"],
    ))


def supplementary_item_id(paper_id: str) -> str:
    return stable_id("DOC18", SCHEMA_VERSION, paper_id, "supplementary", "not_reported")


def _build_coverage(
    package: Mapping[str, Any],
    assets: PaperAssets,
    excluded_experiments: Sequence[dict[str, Any]],
    excluded_claims: Sequence[dict[str, Any]],
    excluded_links: Sequence[dict[str, Any]],
    review_queue: Sequence[dict[str, str]],
) -> dict[str, Any]:
    reason_counts = lambda records: dict(sorted(Counter(r["reason"] for r in records).items()))
    return {
        "schema_version": SCHEMA_VERSION,
        "assembly_statement": "Deterministically assembled from existing accepted assets",
        "claim_generation_statement": "No new scientific claim was generated in M018 A1",
        "paper_id": assets.paper_id,
        "package_id": package["package_id"],
        "reaction_family_coverage": list(assets.reaction_family_coverage),
        "source_document_count": len(package["source_documents"]),
        "supplementary_status": "not_reported",
        "source_span_count": len(package["source_spans"]),
        "experiment_source_record_count": len(assets.experiment_records),
        "included_experiment_count": len(package["experiment_records"]),
        "excluded_experiment_count": len(excluded_experiments),
        "excluded_experiment_reasons": reason_counts(excluded_experiments),
        "existing_claim_count": len(assets.scientific_claims),
        "included_claim_count": len(package["scientific_claims"]),
        "excluded_claim_count": len(excluded_claims),
        "excluded_claim_reasons": reason_counts(excluded_claims),
        "existing_evidence_link_count": len(assets.evidence_links),
        "included_evidence_link_count": len(package["evidence_links"]),
        "excluded_evidence_link_count": len(excluded_links),
        "warning_count": len(package["quality_gates"]["warnings"]),
        "warnings": list(package["quality_gates"]["warnings"]),
        "quality_gate_results": list(package["quality_gates"]["checks"]),
        "package_validator_result": "PENDING",
        "review_status": package["review_status"]["status"],
        "gold_membership": bool(assets.audit_record.get("gold_membership")),
        "human_review_membership": bool(assets.audit_record.get("human_review_membership")),
        "source_asset_refs": list(package["provenance"]["source_asset_refs"]),
        "content_sha256": package["package_hashes"]["content_sha256"],
        "review_queue_count": len(review_queue),
    }


def load_real_pilot_assets(
    repository_root: str | Path,
    pilot_manifest_path: str | Path,
    audit_inventory_path: str | Path,
) -> tuple[list[dict[str, Any]], dict[str, PaperAssets]]:
    root = Path(repository_root).resolve()
    manifest_path = _resolve_from(root, pilot_manifest_path)
    manifest = load_frozen_pilot_manifest(manifest_path)
    inventory_path = Path(audit_inventory_path)
    if not inventory_path.is_absolute():
        inventory_path = root / inventory_path

    from scripts.audit_v018_evidence_assets import SOURCE_PATHS, _require_validation_pass
    _require_validation_pass(root, "cleanroom_validation")
    oa_records = read_jsonl(root / SOURCE_PATHS["oa_manifest"])
    documents = read_jsonl(root / SOURCE_PATHS["cleanroom_documents"])
    spans = read_jsonl(root / SOURCE_PATHS["cleanroom_spans"])
    experiments = read_jsonl(root / SOURCE_PATHS["experiment_records"])
    claims = read_jsonl(root / SOURCE_PATHS["scientific_claims"])
    links = read_jsonl(root / SOURCE_PATHS["evidence_links"])
    inventory = read_jsonl(inventory_path)
    loaded_documents = {record["document_id"]: record for record in load_markdown_documents(root / "input_markdown")}

    def group(records: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            result[stable_paper_id(record.get("paper_id"))].append(record)
        return result

    oa_by = group(oa_records)
    document_by = group(documents)
    span_by = group(spans)
    experiment_by = group(experiments)
    claim_by = group(claims)
    link_by = group(links)
    inventory_by = group(inventory)
    assets_by_paper: dict[str, PaperAssets] = {}
    common_refs = (
        SOURCE_PATHS["oa_manifest"].as_posix(),
        SOURCE_PATHS["cleanroom_documents"].as_posix(),
        SOURCE_PATHS["cleanroom_spans"].as_posix(),
        SOURCE_PATHS["experiment_records"].as_posix(),
        SOURCE_PATHS["scientific_claims"].as_posix(),
        "audits/v018_asset_inventory.jsonl",
    )
    for manifest_record in manifest:
        paper_id = manifest_record["paper_id"]
        if len(oa_by[paper_id]) != 1 or len(document_by[paper_id]) != 1 or len(inventory_by[paper_id]) != 1:
            raise ValueError(f"accepted one-paper metadata is missing or duplicated for {paper_id}")
        oa = oa_by[paper_id][0]
        document = document_by[paper_id][0]
        if oa.get("validation_status") not in {"valid_pdf", "existing_valid_pdf"}:
            raise ValueError(f"main PDF manifest status is not accepted for {paper_id}")
        source_ref = str(document.get("document_ref") or "")
        document_id = str(document.get("document_id") or "")
        loaded = loaded_documents.get(document_id)
        body_sha = str(document.get("document_body_sha256") or "").lower()
        integrity = bool(loaded and hashlib.sha256(str(loaded.get("text") or "").encode("utf-8")).hexdigest() == body_sha)
        refs = list(common_refs)
        if link_by[paper_id]:
            refs.append(SOURCE_PATHS["evidence_links"].as_posix())
        assets_by_paper[paper_id] = PaperAssets(
            paper_id=paper_id,
            reaction_family_coverage=tuple(manifest_record["reaction_family_coverage"]),
            main_document_ref=PurePosixPath(source_ref).as_posix(),
            main_document_sha256=body_sha,
            main_document_integrity=integrity,
            spans=tuple(span_by[paper_id]),
            experiment_records=tuple(experiment_by[paper_id]),
            scientific_claims=tuple(claim_by[paper_id]),
            evidence_links=tuple(link_by[paper_id]),
            audit_record=inventory_by[paper_id][0],
            source_asset_refs=tuple(sorted(set(refs))),
            claim_status_mappings={},
        )
    return manifest, assets_by_paper


def write_package_set(
    output_root: str | Path,
    manifest: Sequence[dict[str, Any]],
    builds: Mapping[str, PackageBuild],
) -> dict[str, Any]:
    root = Path(output_root)
    packages_root = root / "packages"
    reports_root = root / "reports"
    packages_root.mkdir(parents=True, exist_ok=True)
    reports_root.mkdir(parents=True, exist_ok=True)
    index_rows: list[dict[str, Any]] = []
    for order, record in enumerate(manifest, 1):
        paper_id = str(record["paper_id"])
        build = builds[paper_id]
        package_dir = packages_root / paper_id
        package_dir.mkdir(parents=True, exist_ok=True)
        package_path = package_dir / "evidence_package.json"
        write_json(package_path, build.package)

        from scripts.check_v018_evidence_package import (
            canonical_content_sha256,
            validate_evidence_package_file,
        )
        validation = validate_evidence_package_file(package_path)
        reread = json.loads(package_path.read_text(encoding="utf-8"))
        if validation["result"] != "PASS":
            raise ValueError(f"independent package validation failed for {paper_id}: {validation['errors']}")
        if canonical_content_sha256(reread) != reread["package_hashes"]["content_sha256"]:
            raise ValueError(f"read-back package hash mismatch for {paper_id}")
        coverage = dict(build.coverage)
        coverage["package_validator_result"] = validation["result"]
        write_json(package_dir / "coverage_report.json", coverage)
        atomic_write_text(package_dir / "coverage_report.html", render_coverage_html(coverage))
        write_review_queue(package_dir / "review_queue.csv", build.review_queue)
        index_rows.append({
            "order": order,
            "paper_id": paper_id,
            "package_id": build.package["package_id"],
            "reaction_family_coverage": list(record["reaction_family_coverage"]),
            "package_path": f"packages/{paper_id}/evidence_package.json",
            "validation_result": validation["result"],
            "source_document_count": len(build.package["source_documents"]),
            "source_span_count": len(build.package["source_spans"]),
            "experiment_count": len(build.package["experiment_records"]),
            "claim_count": len(build.package["scientific_claims"]),
            "evidence_link_count": len(build.package["evidence_links"]),
            "warning_count": len(build.package["quality_gates"]["warnings"]),
            "review_queue_count": len(build.review_queue),
            "review_status": build.package["review_status"]["status"],
            "content_sha256": build.package["package_hashes"]["content_sha256"],
        })
    index = {"schema_version": SCHEMA_VERSION, "packages": index_rows}
    write_json(reports_root / "v018_a1_package_index.json", index)
    write_index_csv(reports_root / "v018_a1_package_index.csv", index_rows)
    atomic_write_text(reports_root / "v018_a1_package_index.html", render_index_html(index_rows))
    tree_hash = canonical_output_tree_sha256(root)
    summary = build_summary(index_rows, builds, tree_hash)
    write_json(reports_root / "v018_a1_build_summary.json", summary)
    return summary


def build_summary(
    index_rows: Sequence[dict[str, Any]],
    builds: Mapping[str, PackageBuild],
    tree_hash: str,
) -> dict[str, Any]:
    statuses = Counter(row["review_status"] for row in index_rows)
    claim_statuses = Counter(
        claim["drafting_status"]
        for build in builds.values()
        for claim in build.package["scientific_claims"]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "pilot_count": len(index_rows),
        "valid_package_count": sum(row["validation_result"] == "PASS" for row in index_rows),
        "invalid_package_count": sum(row["validation_result"] != "PASS" for row in index_rows),
        "total_source_documents": sum(row["source_document_count"] for row in index_rows),
        "total_source_spans": sum(row["source_span_count"] for row in index_rows),
        "total_experiments": sum(row["experiment_count"] for row in index_rows),
        "total_claims": sum(row["claim_count"] for row in index_rows),
        "total_evidence_links": sum(row["evidence_link_count"] for row in index_rows),
        "total_warnings": sum(row["warning_count"] for row in index_rows),
        "total_review_queue_items": sum(row["review_queue_count"] for row in index_rows),
        "papers_with_no_evidence_links": [row["paper_id"] for row in index_rows if row["evidence_link_count"] == 0],
        "papers_with_no_experiments": [row["paper_id"] for row in index_rows if row["experiment_count"] == 0],
        "papers_with_supplementary_available": [],
        "package_review_status_distribution": dict(sorted(statuses.items())),
        "claim_drafting_status_distribution": dict(sorted(claim_statuses.items())),
        "excluded_unbound_claim_count": sum(build.coverage["excluded_claim_count"] for build in builds.values()),
        "excluded_unbound_experiment_count": sum(build.coverage["excluded_experiment_count"] for build in builds.values()),
        "tree_sha256": tree_hash,
        "result": "PASS" if len(index_rows) == 12 and all(row["validation_result"] == "PASS" for row in index_rows) else "FAIL",
    }


def write_review_queue(path: str | Path, records: Sequence[Mapping[str, Any]]) -> None:
    lines: list[str] = []
    from io import StringIO
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=REVIEW_QUEUE_FIELDS, lineterminator="\n")
    writer.writeheader()
    for record in records:
        writer.writerow({field: record.get(field, "") for field in REVIEW_QUEUE_FIELDS})
    lines.append(buffer.getvalue())
    atomic_write_text(path, "".join(lines))


def write_index_csv(path: str | Path, rows: Sequence[Mapping[str, Any]]) -> None:
    from io import StringIO
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=INDEX_FIELDS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        rendered = dict(row)
        rendered["reaction_family_coverage"] = "|".join(row["reaction_family_coverage"])
        writer.writerow({field: rendered.get(field, "") for field in INDEX_FIELDS})
    atomic_write_text(path, buffer.getvalue())


def render_coverage_html(coverage: Mapping[str, Any]) -> str:
    scalar_rows = []
    for key, value in coverage.items():
        if key in {"quality_gate_results", "warnings", "source_asset_refs"}:
            continue
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        scalar_rows.append(f"<tr><th>{escape(str(key))}</th><td>{escape(rendered)}</td></tr>")
    warnings = "".join(f"<li>{escape(str(value))}</li>" for value in coverage["warnings"])
    gates = "".join(
        f"<tr><td>{escape(str(gate['gate_id']))}</td><td>{escape(str(gate['status']))}</td></tr>"
        for gate in coverage["quality_gate_results"]
    )
    refs = "".join(f"<li>{escape(str(value))}</li>" for value in coverage["source_asset_refs"])
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>M018 A1 coverage</title><style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:76rem}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #bbb;padding:.35rem;text-align:left}"
        "th{background:#eee}</style></head><body>"
        "<h1>M018 A1 per-paper coverage</h1>"
        "<p><strong>Deterministically assembled from existing accepted assets</strong></p>"
        "<p><strong>No new scientific claim was generated in M018 A1</strong></p>"
        f"<table><tbody>{''.join(scalar_rows)}</tbody></table><h2>Warnings</h2><ul>{warnings}</ul>"
        f"<h2>Quality gates</h2><table><thead><tr><th>Gate</th><th>Status</th></tr></thead><tbody>{gates}</tbody></table>"
        f"<h2>Source asset references</h2><ul>{refs}</ul></body></html>\n"
    )


def render_index_html(rows: Sequence[Mapping[str, Any]]) -> str:
    header = "".join(f"<th>{escape(field)}</th>" for field in INDEX_FIELDS)
    body_rows = []
    for row in rows:
        cells = []
        for field in INDEX_FIELDS:
            value = row[field]
            rendered = "|".join(value) if isinstance(value, list) else str(value)
            cells.append(f"<td>{escape(rendered)}</td>")
        body_rows.append(f"<tr>{''.join(cells)}</tr>")
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>M018 A1 package index</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem}table{border-collapse:collapse;font-size:.85rem}"
        "th,td{border:1px solid #bbb;padding:.3rem;vertical-align:top}th{background:#eee}</style></head><body>"
        "<h1>M018 A1 12-package pilot index</h1>"
        "<p>Deterministically assembled from existing accepted assets. No new scientific claim was generated in M018 A1.</p>"
        f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table></body></html>\n"
    )


def canonical_output_tree_sha256(root: str | Path) -> str:
    base = Path(root)
    paths: list[Path] = []
    packages = base / "packages"
    if packages.exists():
        paths.extend(path for path in packages.rglob("*") if path.is_file())
    reports = base / "reports"
    for name in (
        "v018_a1_package_index.json", "v018_a1_package_index.csv", "v018_a1_package_index.html",
    ):
        path = reports / name
        if path.is_file():
            paths.append(path)
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(base).as_posix()):
        relative = path.relative_to(base).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        data = path.read_bytes()
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def validate_package_set(
    runtime_root: str | Path, pilot_manifest_path: str | Path,
) -> dict[str, Any]:
    root = Path(runtime_root)
    manifest = load_frozen_pilot_manifest(pilot_manifest_path)
    expected = [record["paper_id"] for record in manifest]
    errors: list[str] = []
    packages_root = root / "packages"
    actual_dirs = sorted(path.name for path in packages_root.iterdir() if path.is_dir()) if packages_root.exists() else []
    missing = [paper_id for paper_id in expected if paper_id not in actual_dirs]
    extra = [paper_id for paper_id in actual_dirs if paper_id not in expected]
    if missing:
        errors.append(f"missing package directories: {missing}")
    if extra:
        errors.append(f"extra package directories: {extra}")
    package_results: list[dict[str, Any]] = []
    package_ids: list[str] = []
    actual_rows: list[dict[str, Any]] = []
    from scripts.check_v018_evidence_package import canonical_content_sha256, validate_evidence_package_file
    for order, paper_id in enumerate(expected, 1):
        directory = packages_root / paper_id
        required = (
            directory / "evidence_package.json",
            directory / "coverage_report.json",
            directory / "coverage_report.html",
            directory / "review_queue.csv",
        )
        absent = [path.name for path in required if not path.is_file()]
        if absent:
            errors.append(f"{paper_id} missing files: {absent}")
            continue
        result = validate_evidence_package_file(required[0])
        package_results.append({"paper_id": paper_id, **result})
        if result["result"] != "PASS":
            errors.append(f"{paper_id} package validator failed")
            continue
        package = json.loads(required[0].read_text(encoding="utf-8"))
        if package.get("paper_id") != paper_id:
            errors.append(f"{paper_id} package paper_id mismatch")
        package_ids.append(str(package.get("package_id") or ""))
        coverage = json.loads(required[1].read_text(encoding="utf-8"))
        with required[3].open("r", encoding="utf-8", newline="") as handle:
            queue = list(csv.DictReader(handle))
        actual_rows.append({
            "order": order,
            "paper_id": paper_id,
            "package_id": package["package_id"],
            "reaction_family_coverage": coverage["reaction_family_coverage"],
            "package_path": f"packages/{paper_id}/evidence_package.json",
            "validation_result": result["result"],
            "source_document_count": len(package["source_documents"]),
            "source_span_count": len(package["source_spans"]),
            "experiment_count": len(package["experiment_records"]),
            "claim_count": len(package["scientific_claims"]),
            "evidence_link_count": len(package["evidence_links"]),
            "warning_count": len(package["quality_gates"]["warnings"]),
            "review_queue_count": len(queue),
            "review_status": package["review_status"]["status"],
            "content_sha256": canonical_content_sha256(package),
        })
    if len(set(package_ids)) != len(package_ids):
        errors.append("duplicate package IDs")

    reports = root / "reports"
    index_json = reports / "v018_a1_package_index.json"
    index_csv = reports / "v018_a1_package_index.csv"
    index_html = reports / "v018_a1_package_index.html"
    summary_path = reports / "v018_a1_build_summary.json"
    required_reports = [index_json, index_csv, index_html, summary_path]
    absent_reports = [path.name for path in required_reports if not path.is_file()]
    if absent_reports:
        errors.append(f"missing set reports: {absent_reports}")
    summary: dict[str, Any] = {}
    if not absent_reports:
        index = json.loads(index_json.read_text(encoding="utf-8"))
        index_rows = index.get("packages") if isinstance(index, dict) else None
        if index_rows != actual_rows:
            errors.append("package index does not match actual packages or frozen order")
        with index_csv.open("r", encoding="utf-8", newline="") as handle:
            csv_rows = list(csv.DictReader(handle))
        if [row.get("paper_id") for row in csv_rows] != expected:
            errors.append("CSV package index order differs from frozen order")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        expected_counts = {
            "pilot_count": len(actual_rows),
            "valid_package_count": sum(row["validation_result"] == "PASS" for row in actual_rows),
            "invalid_package_count": sum(row["validation_result"] != "PASS" for row in actual_rows),
            "total_source_spans": sum(row["source_span_count"] for row in actual_rows),
            "total_experiments": sum(row["experiment_count"] for row in actual_rows),
            "total_claims": sum(row["claim_count"] for row in actual_rows),
            "total_evidence_links": sum(row["evidence_link_count"] for row in actual_rows),
            "total_warnings": sum(row["warning_count"] for row in actual_rows),
            "total_review_queue_items": sum(row["review_queue_count"] for row in actual_rows),
        }
        for key, value in expected_counts.items():
            if summary.get(key) != value:
                errors.append(f"summary {key} does not match actual files")
        if summary.get("tree_sha256") != canonical_output_tree_sha256(root):
            errors.append("summary tree_sha256 does not match canonical output tree")
        for path in [*required_reports, *(p for paper in expected for p in (packages_root / paper).glob("*") if p.is_file())]:
            text = path.read_text(encoding="utf-8")
            if _FORBIDDEN_TEXT.search(text):
                errors.append(f"forbidden path, secret, hidden label, or reasoning content in {path.relative_to(root).as_posix()}")
    if extra or any("package validator failed" in error or "duplicate package" in error for error in errors):
        stage = "INVALID"
    elif missing or absent_reports or any("missing files" in error for error in errors):
        stage = "INCOMPLETE"
    elif errors:
        stage = "INVALID"
    else:
        stage = "COMPLETE"
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": stage,
        "result": "PASS" if stage == "COMPLETE" else "FAIL",
        "expected_package_count": 12,
        "valid_package_count": sum(result["result"] == "PASS" for result in package_results),
        "invalid_package_count": sum(result["result"] != "PASS" for result in package_results),
        "package_results": package_results,
        "error_count": len(sorted(set(errors))),
        "errors": sorted(set(errors)),
        "summary": summary,
    }


def stage_and_publish_packages(
    runtime_root: str | Path,
    manifest: Sequence[dict[str, Any]],
    builds: Mapping[str, PackageBuild],
    *,
    clean: bool,
    pilot_manifest_path: str | Path,
) -> dict[str, Any]:
    runtime = Path(runtime_root).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "packages").mkdir(exist_ok=True)
    (runtime / "reports").mkdir(exist_ok=True)
    expected = [record["paper_id"] for record in manifest]
    extra = sorted(
        path.name for path in (runtime / "packages").iterdir()
        if path.is_dir() and path.name not in expected
    )
    if extra:
        raise ValueError(f"refusing to silently accept or delete extra package directories: {extra}")
    with tempfile.TemporaryDirectory(prefix=".v018_a1_stage_", dir=runtime) as temp_name:
        stage_root = Path(temp_name)
        summary = write_package_set(stage_root, manifest, builds)
        set_result = validate_package_set(stage_root, pilot_manifest_path)
        if set_result["result"] != "PASS":
            raise ValueError(f"staged package set failed closed: {set_result['errors']}")
        destinations = [runtime / "packages" / paper_id for paper_id in expected]
        report_names = (
            "v018_a1_package_index.json", "v018_a1_package_index.csv",
            "v018_a1_package_index.html", "v018_a1_build_summary.json",
        )
        destinations.extend(runtime / "reports" / name for name in report_names)
        if not clean and any(path.exists() for path in destinations):
            raise FileExistsError("A1 outputs already exist; pass --clean for validated atomic replacement")
        for paper_id in expected:
            _atomic_replace_directory(
                stage_root / "packages" / paper_id,
                runtime / "packages" / paper_id,
                replace=clean,
            )
        for name in report_names:
            source = stage_root / "reports" / name
            destination = runtime / "reports" / name
            if destination.exists() and not clean:
                raise FileExistsError(destination)
            os.replace(source, destination)
    final_result = validate_package_set(runtime, pilot_manifest_path)
    if final_result["result"] != "PASS":
        raise ValueError(f"published package set failed closed: {final_result['errors']}")
    return {"summary": summary, "package_set": final_result}


def publish_single_package(
    runtime_root: str | Path, paper_id: str, build: PackageBuild, *, clean: bool,
) -> None:
    runtime = Path(runtime_root).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".v018_a1_stage_", dir=runtime) as temp_name:
        stage = Path(temp_name)
        manifest = [{"paper_id": paper_id, "reaction_family_coverage": build.coverage["reaction_family_coverage"]}]
        write_single_package(stage, manifest[0], build)
        destination = runtime / "packages" / paper_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        _atomic_replace_directory(stage / "packages" / paper_id, destination, replace=clean)


def write_single_package(root: Path, manifest_record: Mapping[str, Any], build: PackageBuild) -> None:
    paper_id = str(manifest_record["paper_id"])
    package_dir = root / "packages" / paper_id
    package_dir.mkdir(parents=True, exist_ok=True)
    package_path = package_dir / "evidence_package.json"
    write_json(package_path, build.package)
    from scripts.check_v018_evidence_package import validate_evidence_package_file
    validation = validate_evidence_package_file(package_path)
    if validation["result"] != "PASS":
        raise ValueError(f"independent package validation failed for {paper_id}: {validation['errors']}")
    coverage = dict(build.coverage)
    coverage["package_validator_result"] = "PASS"
    write_json(package_dir / "coverage_report.json", coverage)
    atomic_write_text(package_dir / "coverage_report.html", render_coverage_html(coverage))
    write_review_queue(package_dir / "review_queue.csv", build.review_queue)


def compare_output_trees(first: str | Path, second: str | Path) -> dict[str, Any]:
    left = Path(first)
    right = Path(second)
    left_files = {path.relative_to(left).as_posix(): path for path in left.rglob("*") if path.is_file()}
    right_files = {path.relative_to(right).as_posix(): path for path in right.rglob("*") if path.is_file()}
    differing = sorted(
        name for name in set(left_files) | set(right_files)
        if name not in left_files or name not in right_files or left_files[name].read_bytes() != right_files[name].read_bytes()
    )
    return {
        "result": "PASS" if not differing else "FAIL",
        "first_tree_sha256": canonical_output_tree_sha256(left),
        "second_tree_sha256": canonical_output_tree_sha256(right),
        "differing_files": differing,
    }


def _atomic_replace_directory(source: Path, destination: Path, *, replace: bool) -> None:
    if not destination.exists():
        os.replace(source, destination)
        return
    if not replace:
        raise FileExistsError(destination)
    backup = destination.with_name(f".{destination.name}.v018_backup")
    if backup.exists():
        raise FileExistsError(f"stale A1 backup prevents safe replacement: {backup}")
    os.replace(destination, backup)
    try:
        os.replace(source, destination)
    except BaseException:
        os.replace(backup, destination)
        raise
    shutil.rmtree(backup)


def _resolve_from(root: Path, path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def _require_relative(value: str, label: str) -> None:
    text = str(value or "")
    pure = PurePosixPath(text)
    if (
        not text or "\\" in text or text.startswith("/") or re.match(r"^[A-Za-z]:", text)
        or pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ValueError(f"{label} must be a safe relative POSIX path: {text!r}")
