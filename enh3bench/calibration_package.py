"""Build the read-only-source v0.16 semantic calibration review package."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Callable, Iterator

from enh3bench.calibration_metrics import empty_metrics_template
from enh3bench.calibration_sampling import (
    HIGH_RISK_RESERVOIR,
    sample_links,
    sample_papers,
    sample_spans,
)
from enh3bench.calibration_schema import (
    ADJUDICATION_FIELDS,
    COMMON_FIELDS,
    SAMPLING_ALGORITHM_VERSION,
    blank_human_fields,
    common_fields,
    make_document_item_id,
    make_link_item_id,
    make_paper_item_id,
    make_span_item_id,
    read_json,
    read_jsonl,
    resolve_calibration_target,
    sha256_file,
    validate_run_name,
    write_csv,
    write_json,
    write_jsonl,
)


SOURCE_FILES = {
    "documents": "documents/document_ledger.jsonl",
    "source_nodes": "source_nodes/source_nodes.jsonl",
    "candidates": "candidates/candidate_spans.jsonl",
    "semantic_spans": "semantics/semantic_spans.jsonl",
    "evidence_links": "links/evidence_links.jsonl",
    "papers": "papers/paper_records.jsonl",
    "final_manifest": "manifests/final_manifest.json",
    "validation_summary": "reports/cleanroom_validation_summary.json",
}
TRUNCATION_MARKER = "[bounded excerpt truncated]"
EXCERPT_LIMITS = {
    "target_excerpt": 700,
    "previous_context_excerpt": 500,
    "next_context_excerpt": 500,
    "linked_evidence_excerpt": 700,
    "front_matter_excerpt": 700,
    "evidence_excerpt": 700,
}


class CalibrationPackageBuilder:
    """Build one immutable-by-default blank calibration review package."""

    def __init__(
        self,
        *,
        cleanroom_run_name: str,
        calibration_run_name: str,
        cleanroom_root: str | Path = "data/cleanroom",
        calibration_root: str | Path = "data/calibration",
        span_sample_size: int = 300,
        paper_sample_size: int = 60,
        link_sample_size: int = 100,
        seed: int = 16,
    ) -> None:
        self.cleanroom_run_name = validate_run_name(cleanroom_run_name)
        self.calibration_run_name = validate_run_name(calibration_run_name)
        self.cleanroom_root = Path(cleanroom_root)
        self.calibration_root = Path(calibration_root)
        _validate_root_separation(self.calibration_root, self.cleanroom_root)
        self.cleanroom_run_dir = self.cleanroom_root / self.cleanroom_run_name
        self.run_dir = resolve_calibration_target(self.calibration_root, self.calibration_run_name)
        self.span_sample_size = _positive_count("span_sample_size", span_sample_size)
        self.paper_sample_size = _positive_count("paper_sample_size", paper_sample_size)
        self.link_sample_size = _positive_count("link_sample_size", link_sample_size)
        self.seed = int(seed)

    def build(
        self,
        *,
        clean: bool = False,
        dry_run: bool = False,
        emit: Callable[[str], None] = print,
    ) -> dict[str, Any]:
        if dry_run:
            action = "would clean and build" if clean else "would build"
            result = {
                "status": "dry_run", "action": action,
                "calibration_run_name": self.calibration_run_name,
                "source_cleanroom_run_name": self.cleanroom_run_name,
            }
            emit(json.dumps(result, sort_keys=True))
            return result
        self.calibration_root.mkdir(parents=True, exist_ok=True)
        lock_path = self.calibration_root.resolve() / f".{self.calibration_run_name}.lock"
        with _exclusive_lock(lock_path):
            self._prepare_target(clean=clean)
            self.run_dir.mkdir(parents=True, exist_ok=False)
            try:
                return self._build_locked()
            except BaseException as exc:
                self._write_failed_manifest(exc)
                raise

    def clean(self, *, dry_run: bool = False, emit: Callable[[str], None] = print) -> Path:
        target = resolve_calibration_target(self.calibration_root, self.calibration_run_name)
        if dry_run:
            emit(f"would remove calibration run: {self.calibration_run_name}")
            return target
        self.calibration_root.mkdir(parents=True, exist_ok=True)
        lock_path = self.calibration_root.resolve() / f".{self.calibration_run_name}.lock"
        with _exclusive_lock(lock_path):
            if target.exists():
                _safe_remove_target(self.calibration_root, target)
        return target

    def _prepare_target(self, *, clean: bool) -> None:
        target = resolve_calibration_target(self.calibration_root, self.calibration_run_name)
        if target.exists():
            if not clean:
                raise FileExistsError(
                    f"calibration package already exists; refusing overwrite without --clean: {self.calibration_run_name}"
                )
            _safe_remove_target(self.calibration_root, target)

    def _build_locked(self) -> dict[str, Any]:
        source_paths = {name: self.cleanroom_run_dir / relative for name, relative in SOURCE_FILES.items()}
        missing = [relative for name, relative in SOURCE_FILES.items() if not source_paths[name].is_file()]
        if missing:
            raise FileNotFoundError(f"missing required clean-room inputs: {missing}")
        source_manifest = read_json(source_paths["final_manifest"])
        source_validation = read_json(source_paths["validation_summary"])
        if source_manifest.get("pipeline_status") != "completed":
            raise ValueError("source clean-room final manifest is not completed")
        if source_validation.get("result") != "PASS" or int(source_validation.get("error_count") or 0):
            raise ValueError("source clean-room validation is not PASS")
        source_manifest_sha = sha256_file(source_paths["final_manifest"])
        source_hashes = {relative: sha256_file(path) for name, relative in SOURCE_FILES.items() for path in [source_paths[name]]}
        cleanroom_before = tree_hash(self.cleanroom_run_dir)
        gold_root = Path("data/gold")
        gold_before = tree_hash(gold_root)

        documents = read_jsonl(source_paths["documents"])
        nodes = read_jsonl(source_paths["source_nodes"])
        candidates = read_jsonl(source_paths["candidates"])
        semantics = read_jsonl(source_paths["semantic_spans"])
        links = read_jsonl(source_paths["evidence_links"])
        papers = read_jsonl(source_paths["papers"])
        source_counts = {
            "document_count": len(documents), "source_node_count": len(nodes),
            "candidate_span_count": len(candidates), "semantic_span_count": len(semantics),
            "evidence_link_count": len(links), "paper_record_count": len(papers),
        }

        selected_spans, span_coverage = sample_spans(semantics, self.span_sample_size, self.seed)
        selected_papers = sample_papers(papers, semantics, self.paper_sample_size, self.seed)
        selected_links, link_coverage = sample_links(links, semantics, self.link_sample_size, self.seed)
        span_items = self._span_items(selected_spans, nodes, links, semantics, source_manifest_sha)
        paper_items = self._paper_items(selected_papers, source_manifest_sha)
        document_items = self._document_items(selected_papers, documents, nodes, source_manifest_sha)
        link_items = self._link_items(selected_links, semantics, source_manifest_sha)
        if len(document_items) != self.paper_sample_size:
            raise ValueError(
                f"cannot form exactly {self.paper_sample_size} unambiguous document review units: {len(document_items)}"
            )

        self._write_outputs(
            span_items, paper_items, document_items, link_items, span_coverage, link_coverage, source_manifest_sha
        )
        warnings: list[str] = []
        if link_coverage["shortage"]:
            warnings.append(
                f"evidence_link_shortage:requested={link_coverage['requested']}:available={link_coverage['available']}"
            )
        if link_coverage["invalid"]:
            warnings.append(f"invalid_source_links_excluded:{link_coverage['invalid']}")
        for stratum, counts in span_coverage.items():
            if stratum != HIGH_RISK_RESERVOIR and counts["shortage"]:
                warnings.append(
                    f"span_stratum_shortage:{stratum}:requested={counts['requested']}:available={counts['available']}"
                )

        cleanroom_after = tree_hash(self.cleanroom_run_dir)
        gold_after = tree_hash(gold_root)
        mutation_errors: list[str] = []
        if cleanroom_before != cleanroom_after:
            mutation_errors.append("cleanroom_input_hash_changed_during_build")
        if gold_before != gold_after:
            mutation_errors.append("gold_hash_changed_during_build")
        requested_counts = {
            "span": self.span_sample_size, "paper": self.paper_sample_size,
            "document": self.paper_sample_size, "link": self.link_sample_size,
        }
        selected_counts = {
            "span": len(span_items), "paper": len(paper_items),
            "document": len(document_items), "link": len(link_items),
        }
        manifest = {
            **common_fields(self.calibration_run_name, self.cleanroom_run_name, source_manifest_sha, "manifest"),
            "seed": self.seed,
            "sampling_algorithm_version": SAMPLING_ALGORITHM_VERSION,
            "source_cleanroom_validation_status": source_validation.get("result"),
            "source_record_counts": source_counts,
            "requested_sample_counts": requested_counts,
            "selected_sample_counts": selected_counts,
            "span_stratum_coverage": span_coverage,
            "link_sampling_coverage": link_coverage,
            "paper_document_relationships": _paper_document_relationships(papers),
            "input_file_hashes": source_hashes,
            "source_cleanroom_tree_sha256_before": cleanroom_before,
            "source_cleanroom_tree_sha256_after": cleanroom_after,
            "gold_tree_sha256_before": gold_before,
            "gold_tree_sha256_after": gold_after,
            "output_file_hashes": output_hashes(self.run_dir),
            "human_label_nonempty_count": 0,
            "absolute_path_count": 0,
            "full_document_embedding_count": 0,
            "duplicate_calibration_item_ids": 0,
            "unresolved_source_ids": 0,
            "warnings": warnings,
            "errors": mutation_errors,
            "status": "building",
            "created_at_utc": _utc_now(),
        }
        write_json(self.run_dir / "manifests/calibration_manifest.json", manifest)

        from enh3bench.calibration_validation import validate_calibration_package

        validation = validate_calibration_package(
            calibration_run_name=self.calibration_run_name,
            calibration_root=self.calibration_root,
            cleanroom_root=self.cleanroom_root,
            require_blank_human_fields=True,
            allow_building_manifest=True,
        )
        all_errors = mutation_errors + list(validation["errors"])
        manifest.update({
            "human_label_nonempty_count": validation["counts"]["human_label_nonempty_count"],
            "absolute_path_count": validation["counts"]["absolute_path_count"],
            "full_document_embedding_count": validation["counts"]["full_document_embedding_count"],
            "duplicate_calibration_item_ids": validation["counts"]["duplicate_calibration_item_ids"],
            "unresolved_source_ids": validation["counts"]["unresolved_source_ids"],
            "validation_error_count": len(all_errors),
            "errors": all_errors,
        })
        completed = (
            not all_errors
            and source_manifest.get("pipeline_status") == "completed"
            and source_validation.get("result") == "PASS"
            and selected_counts["span"] == self.span_sample_size
            and selected_counts["paper"] == self.paper_sample_size
            and selected_counts["document"] == self.paper_sample_size
            and (selected_counts["link"] == self.link_sample_size or link_coverage["shortage"] > 0)
        )
        # The building manifest is validated against an explicit PENDING summary. The resulting
        # PASS payload is then frozen, hashed, and referenced by the completed manifest.
        write_json(self.run_dir / "reports/validation_summary.json", validation)
        manifest["status"] = "completed" if completed else "failed"
        manifest["validation_summary_sha256"] = sha256_file(
            self.run_dir / "reports/validation_summary.json"
        )
        manifest["output_file_hashes"] = output_hashes(self.run_dir)
        write_json(self.run_dir / "manifests/calibration_manifest.json", manifest)
        final_validation = validate_calibration_package(
            calibration_run_name=self.calibration_run_name,
            calibration_root=self.calibration_root,
            cleanroom_root=self.cleanroom_root,
            require_blank_human_fields=True,
        )
        if final_validation["result"] != "PASS" or not completed:
            if final_validation["errors"]:
                manifest["errors"] = sorted(set(manifest["errors"] + final_validation["errors"]))
            manifest["validation_error_count"] = len(manifest["errors"])
            manifest["status"] = "failed"
            write_json(self.run_dir / "manifests/calibration_manifest.json", manifest)
            raise ValueError(f"calibration package validation failed: {manifest['errors'][:5]}")
        return manifest

    def _span_items(
        self,
        selected: list[dict[str, Any]],
        nodes: list[dict[str, Any]],
        links: list[dict[str, Any]],
        semantics: list[dict[str, Any]],
        manifest_sha: str,
    ) -> list[dict[str, Any]]:
        nodes_by_id = {str(item["source_node_id"]): item for item in nodes}
        nodes_by_paragraph = {(str(item["document_id"]), str(item["paragraph_uid"])): item for item in nodes}
        spans_by_id = {str(item["cleanroom_span_id"]): item for item in semantics}
        links_by_target: dict[str, list[dict[str, Any]]] = {}
        for link in links:
            links_by_target.setdefault(str(link["target_cleanroom_span_id"]), []).append(link)
        items: list[dict[str, Any]] = []
        for span in selected:
            span_id = str(span["cleanroom_span_id"])
            node = nodes_by_id.get(str(span["source_node_id"]))
            if node is None:
                raise ValueError(f"unresolved source node for selected span: {span_id}")
            previous = nodes_by_paragraph.get((str(node["document_id"]), str(node.get("previous_paragraph_uid") or "")))
            following = nodes_by_paragraph.get((str(node["document_id"]), str(node.get("next_paragraph_uid") or "")))
            linked = sorted(links_by_target.get(span_id, []), key=lambda item: str(item["evidence_link_id"]))
            linked_span = spans_by_id.get(str(linked[0]["evidence_cleanroom_span_id"])) if linked else None
            item = {
                **common_fields(self.calibration_run_name, self.cleanroom_run_name, manifest_sha, "sampling"),
                "item_type": "span",
                "calibration_item_id": make_span_item_id(span_id),
                "cleanroom_span_id": span_id,
                "paper_id": span["paper_id"], "document_id": span["document_id"],
                "source_node_id": span["source_node_id"],
                "source_start_offset": int(span["source_start_offset"]),
                "source_end_offset": int(span["source_end_offset"]),
                "source_locator": span["source_locator"],
                "candidate_kind": span["candidate_kind"],
                "semantic_claim_type": span["semantic_claim_type"],
                "document_genre": span["document_genre"],
                "document_reaction_family": span["document_reaction_family"],
                "effective_reaction_family": span["effective_reaction_family"],
                "claim_ownership": span["claim_ownership"],
                "primary_semantic_eligibility": bool(span["primary_semantic_eligibility"]),
                "hard_gate_failures": span.get("hard_gate_failures") or [],
                "validation_gate_decisions": span.get("validation_gate_decisions") or {},
                "needs_review": bool(span.get("needs_review")),
                "semantic_confidence": span.get("semantic_claim_type_confidence"),
                "assigned_primary_stratum": span["assigned_primary_stratum"],
                "selection_stratum": span["selection_stratum"],
                "all_matching_strata": span["all_matching_strata"],
                "sampling_rank": int(span["sampling_rank"]),
                "sampling_hash": span["sampling_hash"],
                "target_excerpt": bounded_excerpt(str(span.get("source_text") or ""), 700),
                "previous_context_excerpt": bounded_excerpt(str((previous or {}).get("source_text") or ""), 500),
                "next_context_excerpt": bounded_excerpt(str((following or {}).get("source_text") or ""), 500),
                "previous_context_source_node_id": str((previous or {}).get("source_node_id") or ""),
                "next_context_source_node_id": str((following or {}).get("source_node_id") or ""),
                "linked_evidence_ids": [str(link["evidence_link_id"]) for link in linked],
                "linked_evidence_span_ids": [str(link["evidence_cleanroom_span_id"]) for link in linked],
                "linked_evidence_excerpt": bounded_excerpt(str((linked_span or {}).get("source_text") or ""), 700),
                **blank_human_fields("span"),
            }
            if span.get("quota_fill_source_stratum"):
                item["quota_fill_source_stratum"] = span["quota_fill_source_stratum"]
            items.append(item)
        return items

    def _paper_items(self, selected: list[dict[str, Any]], manifest_sha: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for paper in selected:
            items.append({
                **common_fields(self.calibration_run_name, self.cleanroom_run_name, manifest_sha, "sampling"),
                "item_type": "paper", "calibration_item_id": make_paper_item_id(str(paper["paper_id"])),
                "paper_id": paper["paper_id"], "document_id": paper["document_id"],
                "paper_admissibility_status": paper["paper_admissibility_status"],
                "document_genre": paper["document_genre"],
                "document_reaction_family": paper["document_reaction_family"],
                "candidate_count": int(paper["candidate_span_count"]),
                "semantic_span_count": int(paper["semantic_span_count"]),
                "primary_eligible_count": int(paper["primary_eligible_span_count"]),
                "needs_review_count": int(paper["needs_review_count"]),
                "best_evidence_span_ids": paper.get("best_evidence_span_ids") or [],
                "limitations": sorted(set(
                    list(paper.get("paper_admissibility_reasons") or [])
                    + list(paper.get("paper_warnings") or []) + list(paper.get("document_conflicts") or [])
                )),
                "has_validation_evidence": paper["has_validation_evidence"],
                "has_quantification_evidence": paper["has_quantification_evidence"],
                "has_performance_evidence": paper["has_performance_evidence"],
                "has_reactor_process_evidence": paper["has_reactor_process_evidence"],
                "assigned_sampling_stratum": paper["assigned_sampling_stratum"],
                "coverage_sampling_stratum": paper["coverage_sampling_stratum"],
                "sampling_rank": int(paper["sampling_rank"]), "sampling_hash": paper["sampling_hash"],
                **blank_human_fields("paper"),
            })
        return items

    def _document_items(
        self, selected_papers: list[dict[str, Any]], documents: list[dict[str, Any]],
        nodes: list[dict[str, Any]], manifest_sha: str,
    ) -> list[dict[str, Any]]:
        docs_by_id: dict[str, list[dict[str, Any]]] = {}
        for document in documents:
            docs_by_id.setdefault(str(document["document_id"]), []).append(document)
        nodes_by_doc: dict[str, list[dict[str, Any]]] = {}
        for node in nodes:
            nodes_by_doc.setdefault(str(node["document_id"]), []).append(node)
        items: list[dict[str, Any]] = []
        selected_document_ids: set[str] = set()
        for paper in selected_papers:
            document_id = str(paper["document_id"])
            matches = docs_by_id.get(document_id, [])
            if len(matches) != 1 or document_id in selected_document_ids:
                raise ValueError(f"ambiguous paper/document relation for {paper['paper_id']}: {document_id}")
            selected_document_ids.add(document_id)
            document = matches[0]
            document_nodes = sorted(nodes_by_doc.get(document_id, []), key=lambda item: int(item["source_start_offset"]))
            front_nodes = [node for node in document_nodes if str(node.get("document_region") or "") == "front_matter"]
            source = "\n\n".join(str(node.get("source_text") or "") for node in (front_nodes or document_nodes[:2]))
            conflicts = list(document.get("document_warnings") or [])
            if document.get("document_reaction_family_conflict"):
                conflicts.append("document_reaction_family_conflict")
            items.append({
                **common_fields(self.calibration_run_name, self.cleanroom_run_name, manifest_sha, "sampling"),
                "item_type": "document", "calibration_item_id": make_document_item_id(document_id),
                "document_id": document_id, "paper_id": document["paper_id"],
                "document_ref": document["document_ref"],
                "document_body_sha256": document["document_body_sha256"],
                "document_genre": document["document_genre"],
                "document_reaction_family": document["document_reaction_family"],
                "document_conflicts": sorted(set(conflicts)),
                "front_matter_excerpt": bounded_excerpt(source, 700),
                "assigned_sampling_stratum": paper["assigned_sampling_stratum"],
                "coverage_sampling_stratum": paper["coverage_sampling_stratum"],
                "sampling_rank": int(paper["sampling_rank"]), "sampling_hash": paper["sampling_hash"],
                **blank_human_fields("document"),
            })
        return items

    def _link_items(
        self, selected: list[dict[str, Any]], semantics: list[dict[str, Any]], manifest_sha: str
    ) -> list[dict[str, Any]]:
        spans = {str(span["cleanroom_span_id"]): span for span in semantics}
        items: list[dict[str, Any]] = []
        for link in selected:
            target_id = str(link["target_cleanroom_span_id"])
            evidence_id = str(link["evidence_cleanroom_span_id"])
            target = spans[target_id]
            evidence = spans[evidence_id]
            items.append({
                **common_fields(self.calibration_run_name, self.cleanroom_run_name, manifest_sha, "sampling"),
                "item_type": "link", "calibration_item_id": make_link_item_id(str(link["evidence_link_id"])),
                "evidence_link_id": link["evidence_link_id"], "paper_id": link["paper_id"],
                "target_span_id": target_id, "evidence_span_id": evidence_id,
                "target_source_node_id": target["source_node_id"],
                "evidence_source_node_id": evidence["source_node_id"],
                "link_role": link["link_role"], "link_roles": link.get("link_roles") or [],
                "target_claim_type": link["target_claim_type"],
                "evidence_claim_type": link["evidence_claim_type"],
                "target_primary_eligibility": link["target_primary_eligibility"],
                "evidence_provenance": link["evidence_provenance"],
                "source_eligibility": link.get("source_eligibility"),
                "is_context_only": bool(link.get("is_context_only")),
                "source_distance": int(link["source_distance"]),
                "source_distance_band": link["source_distance_band"],
                "needs_review": bool(link["needs_review"]),
                "target_excerpt": bounded_excerpt(str(target.get("source_text") or ""), 700),
                "evidence_excerpt": bounded_excerpt(str(evidence.get("source_text") or ""), 700),
                "same_paper": str(target["paper_id"]) == str(evidence["paper_id"]) == str(link["paper_id"]),
                "assigned_sampling_stratum": link["assigned_sampling_stratum"],
                "sampling_rank": int(link["sampling_rank"]), "sampling_hash": link["sampling_hash"],
                **blank_human_fields("link"),
            })
        return items

    def _write_outputs(
        self,
        spans: list[dict[str, Any]], papers: list[dict[str, Any]], documents: list[dict[str, Any]],
        links: list[dict[str, Any]], span_coverage: dict[str, dict[str, int]], link_coverage: dict[str, int],
        manifest_sha: str,
    ) -> None:
        frames = {"span": spans, "paper": papers, "document": documents, "link": links}
        for item_type, rows in frames.items():
            write_jsonl(self.run_dir / f"sampling/{item_type}_sampling_frame.jsonl", rows)
            write_csv(self.run_dir / f"review/{item_type}_review.csv", rows)
        adjudication = [
            {
                **common_fields(self.calibration_run_name, self.cleanroom_run_name, manifest_sha, "adjudication_template"),
                **{field: (row["calibration_item_id"] if field == "calibration_item_id" else item_type if field == "item_type" else "")
                   for field in ADJUDICATION_FIELDS},
            }
            for item_type, rows in frames.items() for row in rows
        ]
        write_csv(
            self.run_dir / "review/adjudication_template.csv", adjudication,
            (*COMMON_FIELDS, *ADJUDICATION_FIELDS),
        )
        report_common = common_fields(
            self.calibration_run_name, self.cleanroom_run_name, manifest_sha, "reporting"
        )
        coverage_rows = [
            {**report_common, "item_type": "span", "stratum": stratum, **counts}
            for stratum, counts in span_coverage.items()
        ] + [{**report_common, "item_type": "link", "stratum": "all_valid_links", **link_coverage}]
        write_csv(self.run_dir / "reports/stratum_coverage.csv", coverage_rows)
        summary = {
            **report_common,
            "selected_counts": {key: len(value) for key, value in frames.items()},
            "span_stratum_coverage": span_coverage,
            "link_sampling_coverage": link_coverage,
            "human_labels_filled": 0,
            "notice": "Blank review infrastructure only; no completed human audit or corpus-wide precision claim.",
        }
        write_json(self.run_dir / "reports/calibration_summary.json", summary)
        metrics_template = empty_metrics_template({key: len(value) for key, value in frames.items()})
        metrics_template.update(report_common)
        write_json(self.run_dir / "reports/calibration_metrics_template.json", metrics_template)
        write_json(self.run_dir / "manifests/calibration_manifest.json", {
            **common_fields(self.calibration_run_name, self.cleanroom_run_name, "pending", "manifest"),
            "status": "building", "warnings": [], "errors": [], "created_at_utc": _utc_now(),
        })
        write_json(self.run_dir / "reports/validation_summary.json", {
            **common_fields(
                self.calibration_run_name, self.cleanroom_run_name, manifest_sha, "validation"
            ),
            "result": "PENDING", "error_count": 0, "warning_count": 0,
            "errors": [], "warnings": [], "counts": {},
        })
        (self.run_dir / "previews").mkdir(parents=True, exist_ok=True)
        preview = _preview_markdown(spans[:5], papers[:3], documents[:3], links[:3])
        from enh3bench.calibration_schema import atomic_write_text
        atomic_write_text(self.run_dir / "previews/calibration_preview.md", preview)

    def _write_failed_manifest(self, exc: BaseException) -> None:
        try:
            path = self.run_dir / "manifests/calibration_manifest.json"
            existing: dict[str, Any] = {}
            if path.exists():
                try:
                    existing = read_json(path)
                except (OSError, ValueError, json.JSONDecodeError):
                    existing = {}
            source_manifest = self.cleanroom_run_dir / SOURCE_FILES["final_manifest"]
            source_sha = sha256_file(source_manifest) if source_manifest.is_file() else ""
            failed = {
                **existing,
                **common_fields(self.calibration_run_name, self.cleanroom_run_name, source_sha, "manifest"),
                "status": "failed", "errors": sorted(set(list(existing.get("errors") or []) + [f"{type(exc).__name__}: {exc}"])),
                "warnings": list(existing.get("warnings") or []),
                "created_at_utc": existing.get("created_at_utc") or _utc_now(),
            }
            write_json(path, failed)
        except OSError:
            pass


def bounded_excerpt(text: str, limit: int) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    suffix = "\n" + TRUNCATION_MARKER
    if limit <= len(suffix):
        return TRUNCATION_MARKER[:limit]
    return value[: limit - len(suffix)] + suffix


def tree_hash(root: str | Path) -> str:
    path = Path(root)
    if not path.exists():
        return hashlib.sha256(b"").hexdigest()
    lines: list[str] = []
    for file_path in sorted(item for item in path.rglob("*") if item.is_file()):
        relative = file_path.relative_to(path).as_posix()
        lines.append(f"{sha256_file(file_path)}  {relative}")
    return hashlib.sha256((("\n".join(lines) + "\n") if lines else "").encode("utf-8")).hexdigest()


def output_hashes(run_dir: str | Path) -> dict[str, str]:
    root = Path(run_dir)
    excluded = {"manifests/calibration_manifest.json"}
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(item for item in root.rglob("*") if item.is_file())
        if path.relative_to(root).as_posix() not in excluded
    }


def normalized_file_hash(path: str | Path) -> str:
    """Hash JSONL or CSV content after removing run/timestamp fields for reproducibility checks."""

    source = Path(path)
    ignored = {"calibration_run_name", "created_at_utc"}
    if source.suffix == ".jsonl":
        rows = read_jsonl(source)
    elif source.suffix == ".csv":
        from enh3bench.calibration_schema import read_csv
        rows = read_csv(source)
    else:
        raise ValueError(f"unsupported normalized hash file: {source}")
    normalized = [{key: value for key, value in row.items() if key not in ignored} for row in rows]
    payload = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for row in normalized) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _paper_document_relationships(papers: list[dict[str, Any]]) -> dict[str, Any]:
    by_paper: dict[str, set[str]] = {}
    by_document: dict[str, set[str]] = {}
    for paper in papers:
        paper_id, document_id = str(paper["paper_id"]), str(paper["document_id"])
        by_paper.setdefault(paper_id, set()).add(document_id)
        by_document.setdefault(document_id, set()).add(paper_id)
    return {
        "paper_count": len(by_paper), "document_count": len(by_document),
        "papers_with_multiple_documents": sorted(key for key, values in by_paper.items() if len(values) != 1),
        "documents_with_multiple_papers": sorted(key for key, values in by_document.items() if len(values) != 1),
    }


def _safe_remove_target(root: str | Path, target: str | Path) -> None:
    resolved_root = Path(root).resolve()
    unresolved = Path(target)
    is_junction = getattr(unresolved, "is_junction", lambda: False)
    if unresolved.is_symlink() or is_junction():
        raise ValueError(f"refusing symlink or junction calibration target: {unresolved}")
    resolved_target = unresolved.resolve()
    if resolved_target == resolved_root or resolved_target.parent != resolved_root:
        raise ValueError(f"refusing unsafe calibration deletion target: {resolved_target}")
    shutil.rmtree(resolved_target)


def _validate_root_separation(calibration_root: Path, cleanroom_root: Path) -> None:
    resolved_calibration = calibration_root.resolve()
    resolved_cleanroom = cleanroom_root.resolve()
    protected = {Path("data").resolve(), Path("data/gold").resolve(), resolved_cleanroom}
    if resolved_calibration in protected or any(
        protected_root in resolved_calibration.parents for protected_root in (Path("data/gold").resolve(), resolved_cleanroom)
    ):
        raise ValueError(f"calibration root overlaps a protected data root: {calibration_root}")


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"calibration run is locked: {path.name}") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        yield
    finally:
        os.close(descriptor)
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _preview_markdown(
    spans: list[dict[str, Any]], papers: list[dict[str, Any]],
    documents: list[dict[str, Any]], links: list[dict[str, Any]],
) -> str:
    lines = [
        "# v0.16 Round-1 Calibration Preview", "",
        "No human labels are filled.", "",
        "This preview is not a completed human audit.", "",
        "This sample does not establish corpus-wide precision.", "",
        "## Five bounded span examples", "",
    ]
    for item in spans:
        lines.extend((f"### {item['calibration_item_id']}", "", str(item["target_excerpt"]), ""))
    lines.extend(("## Three paper examples", ""))
    for item in papers:
        lines.append(f"- {item['calibration_item_id']}: {item['document_genre']} / {item['document_reaction_family']} / {item['paper_admissibility_status']}")
    lines.extend(("", "## Three document examples", ""))
    for item in documents:
        lines.extend((f"### {item['calibration_item_id']}", "", str(item["front_matter_excerpt"]), ""))
    lines.extend(("## Three link examples", ""))
    for item in links:
        lines.extend((f"### {item['calibration_item_id']} ({item['link_role']})", "", str(item["target_excerpt"]), "", str(item["evidence_excerpt"]), ""))
    return "\n".join(lines) + "\n"


def _positive_count(name: str, value: int) -> int:
    count = int(value)
    if count <= 0:
        raise ValueError(f"{name} must be positive")
    return count


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
