"""Document-first, source-grounded v0.15 clean-room pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from contextlib import contextmanager

from enh3bench.claim_ownership import assess_claim_ownership
from enh3bench.claim_typing import classify_claim_type
from enh3bench.cleanroom_candidates import generate_candidate_spans, summarize_candidates
from enh3bench.cleanroom_schema import (
    CLEANROOM_PROFILE,
    CLEANROOM_SCHEMA_VERSION,
    CLEANROOM_STAGES,
    atomic_write_text,
    canonical_json,
    common_fields,
    make_evidence_link_id,
    make_source_node_id,
    read_jsonl,
    resolve_clean_target,
    sha256_bytes,
    sha256_file,
    validate_compare_run_name,
    validate_run_name,
    write_csv,
    write_json,
    write_jsonl,
)
from enh3bench.document_scope import (
    PRIMARY_RESEARCH_GENRE,
    assess_document_genre,
    assess_document_scope,
    build_document_genre_context,
)
from enh3bench.paper_aggregation import aggregate_paper_records
from enh3bench.reaction_profiles import (
    assess_document_reaction_family,
    build_document_reaction_family_context,
    infer_reaction_family_detailed,
    normalize_reaction_family,
)
from enh3bench.source_ledger import OrderedSourceLedger, build_ordered_source_ledger
from enh3bench.validation_gates import detect_validation_gate


DEFAULT_RUN_NAME = "enrr_cleanroom_v015_20260718"
DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": CLEANROOM_SCHEMA_VERSION,
    "pipeline_profile": CLEANROOM_PROFILE,
    "semantic_confidence_threshold": "medium",
    "max_candidate_characters": 3000,
    "review_sample_size": 130,
    "review_seed": 13,
}
GATES = (
    "ammonia_quantification",
    "isotope_15N",
    "blank_control",
    "contamination_control",
    "NOx_control",
    "nitrogen_balance",
    "NOx_balance",
    "nitrate_source_defined",
    "nitrite_source_defined",
    "NO_source_defined",
    "nitrogen_source_disambiguation",
)
SUPPORTING_TYPES = {
    "performance_result_claim",
    "ammonia_quantification_claim",
    "validation_claim",
    "reactor_claim",
    "process_claim",
    "protocol_claim",
    "mechanism_claim",
}
class CleanroomPipeline:
    """Run a deterministic staged pipeline without legacy runtime dependencies."""

    def __init__(
        self,
        *,
        markdown_dir: str | Path,
        run_name: str = DEFAULT_RUN_NAME,
        cleanroom_root: str | Path = "data/cleanroom",
        profile: str = CLEANROOM_PROFILE,
        config_path: str | Path | None = None,
        review_sample_size: int = 130,
        review_seed: int = 13,
        compare_run: str | None = None,
    ) -> None:
        self.markdown_dir = Path(markdown_dir).resolve()
        self.run_name = validate_run_name(run_name)
        if profile != CLEANROOM_PROFILE:
            raise ValueError(f"unsupported clean-room profile: {profile}")
        self.profile = profile
        self.cleanroom_root = Path(cleanroom_root).resolve()
        self.run_dir = resolve_clean_target(self.cleanroom_root, self.run_name)
        self.lock_path = self.cleanroom_root / f".{self.run_name}.lock"
        self.compare_run = validate_compare_run_name(compare_run) if compare_run else None
        self.config = dict(DEFAULT_CONFIG)
        if config_path:
            loaded = json.loads(Path(config_path).read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("clean-room config must be a JSON object")
            self.config.update(loaded)
        self.config.update({
            "schema_version": CLEANROOM_SCHEMA_VERSION,
            "pipeline_profile": profile,
            "review_sample_size": int(review_sample_size),
            "review_seed": int(review_seed),
        })
        if int(self.config["review_sample_size"]) < 0:
            raise ValueError("review sample size must be non-negative")
        if int(self.config["max_candidate_characters"]) <= 0:
            raise ValueError("max_candidate_characters must be positive")
        if str(self.config["semantic_confidence_threshold"]) not in {"low", "medium", "high"}:
            raise ValueError("semantic_confidence_threshold must be low, medium, or high")
        self.config_sha256 = sha256_bytes(canonical_json(self.config).encode("utf-8"))
        self.manifest_path = self.run_dir / "manifests" / "stage_manifest.json"
        self.final_manifest_path = self.run_dir / "manifests" / "final_manifest.json"
        self._ledger: OrderedSourceLedger | None = None

    def clean(self, *, dry_run: bool = False, emit: Callable[[str], None] = print) -> Path:
        target = resolve_clean_target(self.cleanroom_root, self.run_name)
        emit(f"clean target: {target}")
        self.cleanroom_root.mkdir(parents=True, exist_ok=True)
        with _exclusive_run_lock(self.lock_path):
            if not dry_run and target.exists():
                shutil.rmtree(target)
        return target

    def run(
        self,
        *,
        resume: bool = False,
        from_stage: str | None = None,
        to_stage: str | None = None,
    ) -> dict[str, Any]:
        self.cleanroom_root.mkdir(parents=True, exist_ok=True)
        with _exclusive_run_lock(self.lock_path):
            return self._run_locked(resume=resume, from_stage=from_stage, to_stage=to_stage)

    def _run_locked(
        self,
        *,
        resume: bool = False,
        from_stage: str | None = None,
        to_stage: str | None = None,
    ) -> dict[str, Any]:
        if not self.markdown_dir.is_dir():
            raise FileNotFoundError(f"Markdown directory not found: {self.markdown_dir}")
        start = _stage_index(from_stage) if from_stage else 0
        end = _stage_index(to_stage) if to_stage else len(CLEANROOM_STAGES) - 1
        if start > end:
            raise ValueError("--from-stage must not follow --to-stage")
        if start > 0 and not resume:
            raise ValueError("--from-stage requires --resume so upstream outputs can be verified")
        self.run_dir.mkdir(parents=True, exist_ok=True)
        resolved_config = {**self.config, "run_name": self.run_name}
        write_json(self.run_dir / "config" / "resolved_config.json", resolved_config)
        manifest = self._load_or_initialize_manifest()
        handlers = {
            "ingest": self._stage_ingest,
            "documents": self._stage_documents,
            "source_nodes": self._stage_source_nodes,
            "candidates": self._stage_candidates,
            "semantics": self._stage_semantics,
            "links": self._stage_links,
            "papers": self._stage_papers,
            "review": self._stage_review,
            "validate": self._stage_validate,
        }
        selected = set(CLEANROOM_STAGES[start:end + 1])
        if resume:
            self._invalidate_changed_stages(manifest)
        if start > 0:
            incomplete_upstream = [
                stage for stage in CLEANROOM_STAGES[:start]
                if manifest["stages"][stage]["status"] != "completed"
            ]
            if incomplete_upstream:
                raise ValueError(f"cannot start at {CLEANROOM_STAGES[start]}; upstream stages are not reusable: {incomplete_upstream}")
        # Replace any prior completed marker before work begins so an interruption
        # cannot leave a stale success claim for a now-running or invalidated run.
        self._write_final_manifest(manifest, "running")
        for stage in CLEANROOM_STAGES:
            if stage not in selected:
                continue
            state = manifest["stages"][stage]
            if resume and self._stage_reusable(stage, state):
                continue
            self._mark_stage(manifest, stage, "running")
            try:
                output_paths, counts, warnings = handlers[stage]()
                state.update({
                    "status": "completed",
                    "finished_at": _utc_now(),
                    "input_files": self._stage_input_files(stage),
                    "input_sha256": self._stage_input_hashes(stage),
                    "config_sha256": self.config_sha256,
                    "output_files": [self._relative(path) for path in output_paths],
                    "output_sha256": {self._relative(path): sha256_file(path) for path in output_paths},
                    "record_counts": counts,
                    "warnings": warnings,
                    "errors": [],
                })
                self._write_stage_manifest(manifest)
            except BaseException as exc:
                state.update({"status": "failed", "finished_at": _utc_now(), "errors": [f"{type(exc).__name__}: {exc}"]})
                self._write_stage_manifest(manifest)
                self._write_final_manifest(manifest, "failed")
                raise
        completed = all(manifest["stages"][stage]["status"] == "completed" for stage in CLEANROOM_STAGES)
        self._write_final_manifest(manifest, "completed" if completed else "partial")
        return json.loads(self.final_manifest_path.read_text(encoding="utf-8"))

    def _stage_ingest(self) -> tuple[list[Path], dict[str, int], list[str]]:
        paths = sorted(path for path in self.markdown_dir.glob("*.md") if path.name != ".gitkeep")
        if not paths:
            raise ValueError(f"no Markdown documents found in {self.markdown_dir}")
        records = [{
            "document_ref": f"input_markdown/{path.name}",
            "file_sha256": sha256_file(path),
            "file_size": path.stat().st_size,
        } for path in paths]
        output = self.run_dir / "ingest" / "input_manifest.json"
        write_json(output, {
            **common_fields(self.run_name, "ingest", self.profile),
            "markdown_document_count": len(records),
            "documents": records,
        })
        return [output], {"document_count": len(records)}, []

    def _build_ledger(self) -> OrderedSourceLedger:
        if self._ledger is None:
            self._ledger = build_ordered_source_ledger(self.markdown_dir)
        return self._ledger

    def _stage_documents(self) -> tuple[list[Path], dict[str, int], list[str]]:
        ledger = self._build_ledger()
        documents: list[dict[str, Any]] = []
        for source in sorted(ledger.documents_by_id.values(), key=lambda item: str(item["document_id"])):
            document_id = str(source["document_id"])
            sections = ledger.sections_by_document[document_id]
            pseudo_records = [_document_front_record(source, sections)]
            genre_context = build_document_genre_context(source, pseudo_records, sections)
            genre = assess_document_genre(genre_context)
            family_context = build_document_reaction_family_context(source, pseudo_records, sections)
            family = assess_document_reaction_family(family_context)
            documents.append({
                **common_fields(self.run_name, "documents", self.profile),
                "paper_id": source["paper_id"],
                "document_id": document_id,
                "document_ref": f"input_markdown/{document_id}.md",
                "document_body_sha256": source["document_body_sha256"],
                "document_character_count": source["document_character_count"],
                "section_count": source["section_count"],
                "paragraph_count": source["paragraph_count"],
                "document_genre": genre["document_genre"],
                "document_genre_confidence": genre["document_genre_confidence"],
                "document_genre_signals": genre["document_genre_signals"],
                "document_reaction_family": family["document_reaction_family"],
                "document_reaction_family_confidence": family["document_reaction_family_confidence"],
                "document_reaction_family_signals": family["document_reaction_family_signals"],
                "document_reaction_family_conflict": family["document_reaction_family_conflict"],
                "front_matter_signals": source.get("front_matter_signals") or [],
                "document_warnings": [warning for warning in ledger.warnings if warning.endswith(f":{document_id}")],
                "document_assessment_call_count": 1,
            })
        jsonl = self.run_dir / "documents" / "document_ledger.jsonl"
        csv_path = self.run_dir / "documents" / "document_ledger.csv"
        write_jsonl(jsonl, documents)
        write_csv(csv_path, documents)
        return [jsonl, csv_path], {"document_count": len(documents), "document_assessment_call_count": len(documents)}, list(ledger.warnings)

    def _stage_source_nodes(self) -> tuple[list[Path], dict[str, int], list[str]]:
        ledger = self._build_ledger()
        documents = {str(item["document_id"]): item for item in self._documents()}
        section_records: list[dict[str, Any]] = []
        paragraph_records: list[dict[str, Any]] = []
        for document_id in sorted(ledger.documents_by_id):
            for section in ledger.sections_by_document[document_id]:
                section_records.append({**common_fields(self.run_name, "source_nodes", self.profile), **section})
            for paragraph in ledger.paragraphs_by_document[document_id]:
                source = ledger.documents_by_id[document_id]
                provenance, maximum = _source_boundary(paragraph, documents[document_id])
                text = str(paragraph["text"])
                paragraph_records.append({
                    **common_fields(self.run_name, "source_nodes", self.profile),
                    "source_node_id": make_source_node_id(
                        str(source["document_body_sha256"]),
                        int(paragraph["source_start_offset"]),
                        int(paragraph["source_end_offset"]),
                    ),
                    "paper_id": paragraph["paper_id"],
                    "document_id": document_id,
                    "section_uid": paragraph["section_uid"],
                    "paragraph_uid": paragraph["paragraph_uid"],
                    "source_start_offset": paragraph["source_start_offset"],
                    "source_end_offset": paragraph["source_end_offset"],
                    "source_locator": paragraph["source_locator"],
                    "source_order_key": paragraph["source_order_key"],
                    "raw_heading": paragraph["raw_heading"],
                    "direct_section_type": paragraph["direct_section_type"],
                    "effective_section_type": paragraph["effective_section_type"],
                    "document_region": paragraph["document_region"],
                    "source_text": text,
                    "source_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "provenance_type": provenance,
                    "maximum_support_role": maximum,
                    "previous_paragraph_uid": paragraph["previous_paragraph_uid"],
                    "next_paragraph_uid": paragraph["next_paragraph_uid"],
                })
        sections_path = self.run_dir / "source_nodes" / "section_nodes.jsonl"
        paragraphs_path = self.run_dir / "source_nodes" / "paragraph_nodes.jsonl"
        nodes_path = self.run_dir / "source_nodes" / "source_nodes.jsonl"
        write_jsonl(sections_path, section_records)
        write_jsonl(paragraphs_path, paragraph_records)
        write_jsonl(nodes_path, paragraph_records)
        return [sections_path, paragraphs_path, nodes_path], {
            "section_count": len(section_records),
            "paragraph_count": len(paragraph_records),
            "source_node_count": len(paragraph_records),
        }, []

    def _stage_candidates(self) -> tuple[list[Path], dict[str, int], list[str]]:
        nodes = self._source_nodes()
        documents = {str(item["document_id"]): item for item in self._documents()}
        candidates = generate_candidate_spans(
            nodes,
            documents,
            run_name=self.run_name,
            profile=self.profile,
            max_candidate_characters=int(self.config["max_candidate_characters"]),
        )
        summary = summarize_candidates(candidates, nodes, len(documents))
        violations = {key: value for key, value in summary.items() if key in {
            "duplicate_offset_count", "cross_paragraph_candidate_count", "candidate_id_collision_count",
            "unresolved_source_mapping_count",
        } and value}
        if violations:
            raise ValueError(f"candidate safety violations: {violations}")
        jsonl = self.run_dir / "candidates" / "candidate_spans.jsonl"
        csv_path = self.run_dir / "candidates" / "candidate_spans.csv"
        write_jsonl(jsonl, candidates)
        write_csv(csv_path, candidates)
        return [jsonl, csv_path], summary, []

    def _stage_semantics(self) -> tuple[list[Path], dict[str, int], list[str]]:
        documents = {str(item["document_id"]): item for item in self._documents()}
        semantics: list[dict[str, Any]] = []
        for candidate in self._candidates():
            document = documents[str(candidate["document_id"])]
            base = {**candidate, **{
                "document_genre": document["document_genre"],
                "document_genre_confidence": document["document_genre_confidence"],
                "document_genre_signals": document["document_genre_signals"],
                "document_reaction_family": document["document_reaction_family"],
                "document_reaction_family_confidence": document["document_reaction_family_confidence"],
                "document_reaction_family_signals": document["document_reaction_family_signals"],
                "document_reaction_family_conflict": document["document_reaction_family_conflict"],
            }}
            scope = assess_document_scope(base)
            base.update(scope)
            ownership = assess_claim_ownership(base, scope)
            base.update(ownership)
            family = _effective_family_from_cached_document(base)
            base.update(family)
            typing = classify_claim_type(base)
            base.update(typing)
            decisions = {gate: detect_validation_gate(gate, str(base["source_text"]), base, text_source="target_text") for gate in GATES}
            failures = _hard_gate_failures(base, decisions, self.config)
            primary = not failures
            uncertain_reasons = _needs_review_reasons(base, failures)
            if primary:
                outcome = "primary_eligible"
            elif base.get("maximum_support_role") != "primary_support" or base.get("document_genre") != PRIMARY_RESEARCH_GENRE:
                outcome = "secondary_context"
            elif uncertain_reasons:
                outcome = "needs_review"
            else:
                outcome = "unsupported"
            semantics.append({
                **base,
                **common_fields(self.run_name, "semantics", self.profile),
                "validation_gate_decisions": decisions,
                "primary_semantic_eligibility": primary,
                "hard_gate_failures": failures,
                "semantic_outcome": outcome,
                "semantic_warnings": sorted(set(
                    (["context_only_source"] if base.get("maximum_support_role") != "primary_support" else [])
                    + (["document_family_conflict"] if document["document_reaction_family_conflict"] else [])
                )),
                "needs_review": bool(uncertain_reasons),
                "needs_review_reasons": uncertain_reasons,
                "semantic_claim_type_score": _confidence_score(str(base.get("semantic_claim_type_confidence"))),
            })
        jsonl = self.run_dir / "semantics" / "semantic_spans.jsonl"
        csv_path = self.run_dir / "semantics" / "semantic_spans.csv"
        write_jsonl(jsonl, semantics)
        write_csv(csv_path, semantics)
        return [jsonl, csv_path], {
            "semantic_span_count": len(semantics),
            "primary_eligible_count": sum(bool(item["primary_semantic_eligibility"]) for item in semantics),
            "needs_review_count": sum(bool(item["needs_review"]) for item in semantics),
            "unclear_family_count": sum(item["effective_reaction_family"] == "unclear" for item in semantics),
        }, []

    def _stage_links(self) -> tuple[list[Path], dict[str, int], list[str]]:
        semantics = self._semantics()
        by_paper: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in semantics:
            by_paper[str(record["paper_id"])].append(record)
        links: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for paper_id, records in sorted(by_paper.items()):
            targets = [item for item in records if item.get("performance_result_evidence")]
            evidence = [item for item in records if item.get("semantic_claim_type") in {
                "ammonia_quantification_claim", "validation_claim", "gas_purification_or_capture_claim", "protocol_claim"
            }]
            for target in targets:
                for candidate in evidence:
                    target_id = str(target["cleanroom_span_id"])
                    evidence_id = str(candidate["cleanroom_span_id"])
                    if target_id == evidence_id or (target_id, evidence_id) in seen:
                        continue
                    if abs(int(target["source_start_offset"]) - int(candidate["source_start_offset"])) > 12000:
                        continue
                    seen.add((target_id, evidence_id))
                    roles = _link_roles(candidate)
                    context_only = candidate.get("maximum_support_role") != "primary_support"
                    links.append({
                        **common_fields(self.run_name, "links", self.profile),
                        "evidence_link_id": make_evidence_link_id(paper_id, target_id, evidence_id),
                        "target_cleanroom_span_id": target_id,
                        "evidence_cleanroom_span_id": evidence_id,
                        "paper_id": paper_id,
                        "link_roles": roles,
                        "link_score": round(max(0.1, 1.0 - abs(int(target["source_start_offset"]) - int(candidate["source_start_offset"])) / 12000), 4),
                        "link_signals": ["same_paper", "bounded_source_distance", *roles],
                        "source_eligibility": "primary_admissible" if not context_only else "context_only",
                        "is_context_only": context_only,
                        "link_warnings": ["link_does_not_upgrade_ownership_or_provenance"] + (["context_hint_only"] if context_only else []),
                    })
        links.sort(key=lambda item: (item["paper_id"], item["target_cleanroom_span_id"], item["evidence_cleanroom_span_id"]))
        index: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for link in links:
            index[str(link["target_cleanroom_span_id"])].append({
                "evidence_cleanroom_span_id": link["evidence_cleanroom_span_id"],
                "link_roles": link["link_roles"],
                "is_context_only": link["is_context_only"],
            })
        jsonl = self.run_dir / "links" / "evidence_links.jsonl"
        index_path = self.run_dir / "links" / "evidence_link_index.json"
        write_jsonl(jsonl, links)
        write_json(index_path, dict(sorted(index.items())))
        counts = _link_diagnostics(links, semantics)
        if any(counts[key] for key in ("cross_paper_link_count", "self_link_count", "duplicate_link_count", "context_only_primary_upgrade_count")):
            raise ValueError(f"evidence-link safety violations: {counts}")
        return [jsonl, index_path], counts, []

    def _stage_papers(self) -> tuple[list[Path], dict[str, int], list[str]]:
        papers = aggregate_paper_records(
            self._documents(), self._candidates(), self._semantics(), self._links(),
            run_name=self.run_name, profile=self.profile,
        )
        jsonl = self.run_dir / "papers" / "paper_records.jsonl"
        csv_path = self.run_dir / "papers" / "paper_records.csv"
        write_jsonl(jsonl, papers)
        write_csv(csv_path, papers)
        return [jsonl, csv_path], {
            "paper_record_count": len(papers),
            "paper_admissibility_distribution": dict(sorted(Counter(str(item["paper_admissibility_status"]) for item in papers).items())),
        }, []

    def _stage_review(self) -> tuple[list[Path], dict[str, int], list[str]]:
        semantics = self._semantics()
        papers = {str(item["paper_id"]): item for item in self._papers()}
        nodes = self._source_nodes()
        node_by_id = {str(item["source_node_id"]): item for item in nodes}
        paragraph_by_uid = {str(item["paragraph_uid"]): item for item in nodes}
        links_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for link in self._links():
            links_by_target[str(link["target_cleanroom_span_id"])].append(link)
        selected = _deterministic_review_sample(
            semantics, int(self.config["review_sample_size"]), int(self.config["review_seed"])
        )
        rows: list[dict[str, Any]] = []
        for record in selected:
            node = node_by_id[str(record["source_node_id"])]
            previous = paragraph_by_uid.get(str(node.get("previous_paragraph_uid") or ""), {})
            following = paragraph_by_uid.get(str(node.get("next_paragraph_uid") or ""), {})
            paper = papers[str(record["paper_id"])]
            rows.append({
                "run_name": self.run_name,
                "cleanroom_span_id": record["cleanroom_span_id"],
                "paper_id": record["paper_id"],
                "document_ref": paper["document_ref"],
                "review_stratum": _review_stratum(record),
                "target_text": record["source_text"],
                "previous_paragraph": previous.get("source_text", ""),
                "following_paragraph": following.get("source_text", ""),
                "linked_evidence_span_ids": [item["evidence_cleanroom_span_id"] for item in links_by_target.get(str(record["cleanroom_span_id"]), [])],
                "paper_admissibility_status": paper["paper_admissibility_status"],
                "semantic_claim_type": record["semantic_claim_type"],
                "effective_reaction_family": record["effective_reaction_family"],
                "primary_semantic_eligibility": record["primary_semantic_eligibility"],
                "needs_review": record["needs_review"],
                "human_scope_correct": "",
                "human_ownership_correct": "",
                "human_claim_type_correct": "",
                "human_family_correct": "",
                "human_primary_eligibility_correct": "",
                "human_notes": "",
            })
        csv_path = self.run_dir / "review" / "semantic_review_sample.csv"
        md_path = self.run_dir / "review" / "semantic_review_sample.md"
        write_csv(csv_path, rows)
        blocks = [
            "# v0.15 Clean-Room Semantic Review Sample",
            "",
            "This deterministic sample belongs to a new clean-room run and is not a completed human review.",
            "",
        ]
        for index, row in enumerate(rows, 1):
            blocks.extend([
                f"## {index}. {row['cleanroom_span_id']}", "",
                f"- Paper: `{row['paper_id']}`", f"- Document: `{row['document_ref']}`",
                f"- Stratum: `{row['review_stratum']}`", f"- Paper status: `{row['paper_admissibility_status']}`", "",
                "Target:", "", str(row["target_text"]), "", "Previous paragraph:", "",
                str(row["previous_paragraph"]), "", "Following paragraph:", "", str(row["following_paragraph"]), "",
                f"Linked evidence IDs: `{canonical_json(row['linked_evidence_span_ids'])}`", "",
            ])
        atomic_write_text(md_path, "\n".join(blocks).rstrip() + "\n")
        return [md_path, csv_path], {"review_sample_count": len(rows)}, []

    def _stage_validate(self) -> tuple[list[Path], dict[str, int], list[str]]:
        from enh3bench.cleanroom_output_check import validate_cleanroom_run

        papers = self._papers()
        database_jsonl = self.run_dir / "database" / "final_database.jsonl"
        database_csv = self.run_dir / "database" / "final_database.csv"
        write_jsonl(database_jsonl, papers)
        write_csv(database_csv, papers)
        summary = validate_cleanroom_run(self.run_dir, require_completed=False)
        if summary["error_count"]:
            raise ValueError(f"clean-room validation failed: {summary['errors'][:5]}")
        summary_path = self.run_dir / "reports" / "cleanroom_validation_summary.json"
        report_path = self.run_dir / "reports" / "cleanroom_validation_report.md"
        write_json(summary_path, summary)
        atomic_write_text(report_path, _validation_markdown(summary))
        outputs = [database_jsonl, database_csv, summary_path, report_path]
        if self.compare_run:
            comparison = self._legacy_comparison_report()
            outputs.append(comparison)
        return outputs, summary["counts"], summary["warnings"]

    def _legacy_comparison_report(self) -> Path:
        """Read legacy data only in explicit comparison mode and never alter semantics."""

        compare_root = self.cleanroom_root.parent
        matches = sorted(compare_root.glob(f"*/{self.compare_run}/*.jsonl"))
        output = self.run_dir / "reports" / "legacy_comparison.json"
        write_json(output, {
            "compare_run": self.compare_run,
            "comparison_only": True,
            "legacy_jsonl_files": [
                path.relative_to(compare_root.parent).as_posix()
                for path in matches
                if path.is_relative_to(compare_root.parent)
            ],
            "legacy_semantics_imported": False,
        })
        return output

    def _documents(self) -> list[dict[str, Any]]:
        return read_jsonl(self.run_dir / "documents" / "document_ledger.jsonl")

    def _source_nodes(self) -> list[dict[str, Any]]:
        return read_jsonl(self.run_dir / "source_nodes" / "source_nodes.jsonl")

    def _candidates(self) -> list[dict[str, Any]]:
        return read_jsonl(self.run_dir / "candidates" / "candidate_spans.jsonl")

    def _semantics(self) -> list[dict[str, Any]]:
        return read_jsonl(self.run_dir / "semantics" / "semantic_spans.jsonl")

    def _links(self) -> list[dict[str, Any]]:
        return read_jsonl(self.run_dir / "links" / "evidence_links.jsonl")

    def _papers(self) -> list[dict[str, Any]]:
        return read_jsonl(self.run_dir / "papers" / "paper_records.jsonl")

    def _load_or_initialize_manifest(self) -> dict[str, Any]:
        if self.manifest_path.exists():
            value = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if value.get("schema_version") == CLEANROOM_SCHEMA_VERSION and value.get("pipeline_profile") == self.profile:
                return value
        return {
            "schema_version": CLEANROOM_SCHEMA_VERSION,
            "pipeline_profile": self.profile,
            "run_name": self.run_name,
            "stages": {stage: _empty_stage(stage, self.profile) for stage in CLEANROOM_STAGES},
        }

    def _mark_stage(self, manifest: dict[str, Any], stage: str, status: str) -> None:
        state = manifest["stages"][stage]
        state.update({"status": status, "started_at": _utc_now(), "finished_at": None, "errors": []})
        self._write_stage_manifest(manifest)

    def _write_stage_manifest(self, manifest: dict[str, Any]) -> None:
        write_json(self.manifest_path, manifest)

    def _write_final_manifest(self, manifest: dict[str, Any], status: str) -> None:
        failed = [stage for stage, state in manifest["stages"].items() if state["status"] == "failed"]
        value = {
            "schema_version": CLEANROOM_SCHEMA_VERSION,
            "pipeline_profile": self.profile,
            "run_name": self.run_name,
            "pipeline_status": status if not failed else "failed",
            "failed_stages": failed,
            "completed_stages": [stage for stage, state in manifest["stages"].items() if state["status"] == "completed"],
            "created_at": _utc_now(),
            "stage_manifest": "manifests/stage_manifest.json",
        }
        write_json(self.final_manifest_path, value)

    def _stage_reusable(self, stage: str, state: dict[str, Any]) -> bool:
        if state.get("status") != "completed" or state.get("config_sha256") != self.config_sha256:
            return False
        if state.get("input_sha256") != self._stage_input_hashes(stage):
            return False
        for relative, expected in (state.get("output_sha256") or {}).items():
            path = self.run_dir / relative
            if not path.is_file() or sha256_file(path) != expected:
                return False
        return bool(state.get("output_sha256"))

    def _invalidate_changed_stages(self, manifest: dict[str, Any]) -> None:
        invalidating = False
        for stage in CLEANROOM_STAGES:
            state = manifest["stages"][stage]
            if not invalidating and state.get("status") == "completed" and not self._stage_reusable(stage, state):
                invalidating = True
            if invalidating and state.get("status") in {"completed", "failed", "running"}:
                state["status"] = "invalidated"
        self._write_stage_manifest(manifest)

    def _stage_input_files(self, stage: str) -> list[str]:
        index = _stage_index(stage)
        if stage == "ingest":
            return [f"input_markdown/{path.name}" for path in sorted(self.markdown_dir.glob("*.md")) if path.name != ".gitkeep"]
        previous = CLEANROOM_STAGES[index - 1]
        state = json.loads(self.manifest_path.read_text(encoding="utf-8"))["stages"][previous]
        return list(state.get("output_files") or [])

    def _stage_input_hashes(self, stage: str) -> dict[str, str]:
        if stage == "ingest":
            return {f"input_markdown/{path.name}": sha256_file(path) for path in sorted(self.markdown_dir.glob("*.md")) if path.name != ".gitkeep"}
        index = _stage_index(stage)
        previous = CLEANROOM_STAGES[index - 1]
        state = self._load_or_initialize_manifest()["stages"][previous]
        return dict(state.get("output_sha256") or {})

    def _relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.run_dir).as_posix()


def prepare_markdown_input(
    *,
    markdown_dir: str | Path | None,
    input_dir: str | Path | None,
    converter: str | None,
    skip_conversion: bool,
) -> Path:
    if markdown_dir:
        return Path(markdown_dir)
    if not input_dir:
        raise ValueError("one of --markdown-dir or --input-dir is required")
    source = Path(input_dir)
    if skip_conversion:
        return source
    markdown_files = list(source.glob("*.md"))
    non_markdown = [path for path in source.iterdir() if path.is_file() and path.suffix.casefold() != ".md"]
    if markdown_files and not non_markdown:
        return source
    if not converter:
        raise ValueError("raw input requires an explicit --converter command")
    destination = Path("input_markdown")
    command = converter.format(input_dir=str(source), markdown_dir=str(destination))
    subprocess.run(command, shell=True, check=True)
    return destination


def _source_boundary(node: dict[str, Any], document: dict[str, Any]) -> tuple[str, str]:
    section_type = str(node.get("effective_section_type") or "unknown")
    region = str(node.get("document_region") or "unknown")
    text = str(node.get("text") or "")
    if section_type in {"references", "reference"} or region == "references":
        return "reference", "context_only"
    if re.match(r"^\s*(?:figure|fig\.|scheme)\s*\d+", text, re.IGNORECASE):
        return "figure_or_scheme_caption", "context_only"
    if "|" in text and document.get("document_genre") in {"review", "perspective"}:
        return "review_table", "context_only"
    if region in {"title", "abstract", "front_matter"}:
        return "front_matter", "non_evidence"
    if document.get("document_genre") != PRIMARY_RESEARCH_GENRE:
        return "secondary_document_body", "context_only"
    if section_type in {"introduction", "background", "related_work", "literature_review"}:
        return "background", "context_only"
    return "primary_body", "primary_support"


def _document_front_record(document: dict[str, Any], sections: list[dict[str, Any]]) -> dict[str, Any]:
    body = str(document.get("full_body_text") or "")
    title_section = next((item for item in sections if item.get("document_region") == "title"), None)
    abstract_section = next((item for item in sections if item.get("document_region") == "abstract"), None)
    title = str(title_section.get("heading_text") or "") if title_section else ""
    if not title:
        first_heading = next((str(item.get("heading_text") or "") for item in sections if item.get("heading_text")), "")
        title = first_heading or str(document["document_id"]).replace("_", " ")
    abstract = ""
    if abstract_section:
        abstract = body[int(abstract_section["section_start_offset"]):int(abstract_section["section_end_offset"])]
    return {"paper_title": title, "paper_abstract": abstract, "source_text": body[:5000]}


def _hard_gate_failures(record: dict[str, Any], decisions: dict[str, Any], config: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    checks = (
        (record.get("document_genre") == PRIMARY_RESEARCH_GENRE, "document_genre_not_primary_research"),
        (record.get("span_claim_scope") == "target_document", "span_scope_not_target_document"),
        (record.get("document_scope") == "target_document", "document_scope_not_target_document"),
        (record.get("claim_ownership") == "target_authors", "claim_ownership_not_target_authors"),
        (record.get("maximum_support_role") == "primary_support", "provenance_not_primary_admissible"),
        (record.get("semantic_claim_type") in SUPPORTING_TYPES, "semantic_type_not_primary_supporting"),
        (record.get("effective_reaction_family") not in {"unclear", "mixed"}, "effective_reaction_family_unclear_or_mixed"),
        (not record.get("document_reaction_family_conflict"), "document_reaction_family_conflict"),
        (not record.get("document_target_reaction_family_conflict"), "local_primary_family_conflict"),
        (not any(value.get("gate_conflict") for value in decisions.values()), "structured_text_gate_conflict"),
        (_confidence_score(str(record.get("semantic_claim_type_confidence"))) >= _confidence_score(str(config["semantic_confidence_threshold"])), "semantic_confidence_below_threshold"),
    )
    failures.extend(message for passed, message in checks if not passed)
    if record.get("semantic_claim_type") == "performance_result_claim" and not record.get("performance_result_evidence"):
        failures.append("performance_result_without_target_outcome_and_result")
    if record.get("semantic_claim_type") == "ammonia_quantification_claim" and not record.get("ammonia_quantification_signal"):
        failures.append("quantification_without_analytical_measurement")
    if record.get("gas_purification_trap_signal") and not record.get("ammonia_quantification_signal"):
        failures.append("trap_only_not_quantification")
    return sorted(set(failures))


def _needs_review_reasons(record: dict[str, Any], failures: list[str]) -> list[str]:
    reasons: list[str] = []
    if record.get("effective_reaction_family") in {"unclear", "mixed"}:
        reasons.append("reaction_family_unclear_or_mixed")
    if record.get("claim_ownership") == "unclear":
        reasons.append("claim_ownership_unclear")
    if record.get("span_claim_scope") == "unclear":
        reasons.append("span_claim_scope_unclear")
    reasons.extend(item for item in failures if "conflict" in item)
    return sorted(set(reasons))


def _effective_family_from_cached_document(record: dict[str, Any]) -> dict[str, Any]:
    """Resolve local family against the one cached document assessment without recomputing it."""

    document_family = normalize_reaction_family(str(record.get("document_reaction_family") or "unclear"))
    document_confidence = str(record.get("document_reaction_family_confidence") or "unclear")
    local = infer_reaction_family_detailed(text=str(record.get("source_text") or ""))
    local_family = normalize_reaction_family(str(local.get("reaction_family") or "unclear"))
    local_explicit = bool(
        local_family not in {"unclear", "mixed"}
        and local.get("reaction_family_confidence") == "high"
        and local.get("reaction_family_scope") == "explicit_span"
    )
    document_specific = document_family not in {"unclear", "mixed"}
    conflict = bool(local_explicit and document_specific and local_family != document_family)
    if local_explicit:
        effective = local_family
        source = "explicit_high_confidence_target_span"
    elif document_specific:
        effective = document_family
        source = "cached_document_assessment"
    else:
        effective = document_family
        source = "cached_document_uncertainty"
    return {
        "document_reaction_family": document_family,
        "document_reaction_family_confidence": document_confidence,
        "document_reaction_family_signals": list(record.get("document_reaction_family_signals") or []),
        "document_reaction_family_conflict": bool(record.get("document_reaction_family_conflict")),
        "legacy_reaction_family": "unclear",
        "effective_reaction_family": effective,
        "effective_reaction_family_source": source,
        "reaction_family_correction": False,
        "document_target_reaction_family_conflict": conflict,
        "target_explicit_reaction_family": local_family if local_explicit else "unclear",
        "target_explicit_reaction_family_signals": list(local.get("reaction_family_signals") or []),
    }


def _link_roles(record: dict[str, Any]) -> list[str]:
    roles: list[str] = []
    if record.get("ammonia_quantification_signal"):
        roles.append("quantification_support")
    decisions = record.get("validation_gate_decisions") or {}
    if any(value.get("satisfied") for key, value in decisions.items() if key != "ammonia_quantification"):
        roles.append("validation_support")
    if record.get("gas_purification_trap_signal"):
        roles.append("gas_handling_context")
    return roles or ["context_hint"]


def _link_diagnostics(links: list[dict[str, Any]], semantics: list[dict[str, Any]]) -> dict[str, int]:
    paper_by_id = {str(item["cleanroom_span_id"]): str(item["paper_id"]) for item in semantics}
    pairs = [(str(item["target_cleanroom_span_id"]), str(item["evidence_cleanroom_span_id"])) for item in links]
    return {
        "evidence_link_count": len(links),
        "cross_paper_link_count": sum(paper_by_id.get(left) != paper_by_id.get(right) for left, right in pairs),
        "self_link_count": sum(left == right for left, right in pairs),
        "duplicate_link_count": len(pairs) - len(set(pairs)),
        "context_only_primary_upgrade_count": 0,
    }


def _deterministic_review_sample(records: list[dict[str, Any]], size: int, seed: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[_review_stratum(record)].append(record)
    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    for stratum in sorted(grouped):
        values = sorted(grouped[stratum], key=lambda item: str(item["cleanroom_span_id"]))
        rng.shuffle(values)
        selected.append(values[0])
    selected_ids = {str(item["cleanroom_span_id"]) for item in selected}
    remainder = [item for item in sorted(records, key=lambda item: str(item["cleanroom_span_id"])) if str(item["cleanroom_span_id"]) not in selected_ids]
    rng.shuffle(remainder)
    selected.extend(remainder[:max(0, size - len(selected))])
    return selected[:size]


def _review_stratum(record: dict[str, Any]) -> str:
    if record.get("needs_review"):
        return "needs_review"
    if record.get("document_genre") in {"review", "perspective"}:
        return "review_or_perspective"
    if record.get("claim_ownership") == "external_or_cited_authors":
        return "external_cited_claim"
    if record.get("effective_reaction_family") == "unclear":
        return "unclear_family"
    if record.get("gas_purification_trap_signal") and not record.get("ammonia_quantification_signal"):
        return "trap_only"
    semantic_type = str(record.get("semantic_claim_type") or "")
    if record.get("primary_semantic_eligibility") and semantic_type == "performance_result_claim":
        return "primary_performance"
    if record.get("primary_semantic_eligibility") and semantic_type == "ammonia_quantification_claim":
        return "primary_quantification"
    if record.get("primary_semantic_eligibility") and semantic_type == "validation_claim":
        return "primary_validation"
    if semantic_type in {"reactor_claim", "process_claim"}:
        return "reactor_or_process"
    return "secondary_or_background"


def _validation_markdown(summary: dict[str, Any]) -> str:
    lines = ["# Clean-Room Validation Report", "", f"Result: **{summary['result']}**", "", "## Counts", ""]
    lines.extend(f"- `{key}`: {value}" for key, value in sorted(summary["counts"].items()))
    lines.extend(["", "## Errors", ""])
    lines.extend(f"- {value}" for value in summary["errors"] or ["None"])
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {value}" for value in summary["warnings"] or ["None"])
    return "\n".join(lines) + "\n"


def _confidence_score(value: str) -> int:
    return {"unclear": 0, "low": 1, "medium": 2, "high": 3}.get(value, 0)


def _stage_index(stage: str | None) -> int:
    if stage not in CLEANROOM_STAGES:
        raise ValueError(f"unknown clean-room stage: {stage}")
    return CLEANROOM_STAGES.index(str(stage))


def _empty_stage(stage: str, profile: str) -> dict[str, Any]:
    return {
        "stage_name": stage,
        "status": "not_started",
        "started_at": None,
        "finished_at": None,
        "input_files": [],
        "input_sha256": {},
        "config_sha256": "",
        "output_files": [],
        "output_sha256": {},
        "record_counts": {},
        "warnings": [],
        "errors": [],
        "code_commit": _git_commit(),
        "schema_version": CLEANROOM_SCHEMA_VERSION,
        "pipeline_profile": profile,
    }


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@contextmanager
def _exclusive_run_lock(path: Path):
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.fsync(descriptor)
        yield
    except FileExistsError as exc:
        raise RuntimeError(f"clean-room run is already active or has a stale lock: {path}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
            try:
                path.unlink()
            except FileNotFoundError:
                pass
