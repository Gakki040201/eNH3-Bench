from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from enh3bench.cleanroom_schema import make_evidence_link_id, write_json, write_jsonl


def fixture_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:20].upper()}"


def create_cleanroom_fixture(
    root: Path,
    run_name: str = "cleanroom_fixture",
    *,
    paper_count: int = 12,
    spans_per_paper: int = 5,
    link_count: int = 30,
) -> Path:
    run_dir = root / run_name
    documents: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    semantics: list[dict[str, Any]] = []
    papers: list[dict[str, Any]] = []
    genres = ("primary_research", "review", "perspective", "mixed")
    families = ("eNRR", "NO3RR", "unclear", "mixed", "LiNRR")
    claim_types = (
        "performance_result_claim", "ammonia_quantification_claim", "validation_claim",
        "reactor_claim", "secondary_context_claim", "mechanism_claim",
    )
    for paper_index in range(paper_count):
        paper_id = f"P{paper_index:04d}_fixture"
        document_id = paper_id
        genre = genres[paper_index % len(genres)]
        family = families[paper_index % len(families)]
        body_sha = hashlib.sha256(f"body:{document_id}".encode()).hexdigest()
        documents.append({
            "schema_version": "0.15-cleanroom.1", "pipeline_profile": "document_first_cleanroom_v1",
            "run_name": run_name, "record_created_by_stage": "documents",
            "paper_id": paper_id, "document_id": document_id,
            "document_ref": f"input_markdown/{paper_id}.md", "document_body_sha256": body_sha,
            "document_character_count": 10000, "section_count": 1,
            "paragraph_count": spans_per_paper, "document_genre": genre,
            "document_genre_confidence": "high", "document_genre_signals": [],
            "document_reaction_family": family, "document_reaction_family_confidence": "high",
            "document_reaction_family_signals": [], "document_reaction_family_conflict": family == "mixed",
            "front_matter_signals": [], "document_warnings": [],
        })
        paper_spans: list[dict[str, Any]] = []
        for span_index in range(spans_per_paper):
            token = f"{paper_id}:{span_index}"
            node_id = fixture_id("CRN15", token)
            span_id = fixture_id("CR15", token)
            start = span_index * 1000
            text = f"Fixture evidence {token}. " + ("scientific text " * (20 + span_index))
            end = start + len(text)
            previous_uid = f"PAR{span_index - 1:03d}" if span_index else ""
            next_uid = f"PAR{span_index + 1:03d}" if span_index + 1 < spans_per_paper else ""
            node = {
                "schema_version": "0.15-cleanroom.1", "pipeline_profile": "document_first_cleanroom_v1",
                "run_name": run_name, "record_created_by_stage": "source_nodes",
                "source_node_id": node_id, "paper_id": paper_id, "document_id": document_id,
                "section_uid": "SEC001", "paragraph_uid": f"PAR{span_index:03d}",
                "source_start_offset": start, "source_end_offset": end,
                "source_locator": f"{paper_id}::SEC001::PAR{span_index:03d}",
                "source_order_key": [paper_index, span_index], "raw_heading": "Results",
                "direct_section_type": "results", "effective_section_type": "results",
                "document_region": "front_matter" if span_index == 0 else "body",
                "source_text": text, "source_text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "provenance_type": "target_document_body", "maximum_support_role": "primary_support",
                "previous_paragraph_uid": previous_uid, "next_paragraph_uid": next_uid,
            }
            nodes.append(node)
            claim_type = claim_types[(paper_index + span_index) % len(claim_types)]
            primary = claim_type in {"performance_result_claim", "ammonia_quantification_claim", "validation_claim"} and genre == "primary_research" and family == "eNRR"
            semantic = {
                **node,
                "record_created_by_stage": "semantics", "cleanroom_span_id": span_id,
                "candidate_kind": "performance_signal", "candidate_priority": "normal",
                "candidate_score": 1, "generation_method": "fixture", "trigger_signals": [],
                "document_genre": genre, "document_reaction_family": family,
                "document_reaction_family_conflict": family == "mixed",
                "effective_reaction_family": family, "span_claim_scope": "target_document",
                "document_scope": "target_document", "claim_ownership": "target_authors" if paper_index % 3 else "external_or_cited_authors",
                "semantic_claim_type": claim_type, "semantic_claim_type_confidence": "high",
                "performance_result_evidence": claim_type == "performance_result_claim",
                "quantitative_performance_evidence": claim_type == "performance_result_claim",
                "target_ammonia_reaction_outcome_anchor": family == "eNRR",
                "ammonia_quantification_signal": claim_type == "ammonia_quantification_claim",
                "gas_purification_trap_signal": span_index == 4,
                "validation_gate_decisions": {"blank_control": {"satisfied": claim_type == "validation_claim"}},
                "primary_semantic_eligibility": primary, "hard_gate_failures": [] if primary else ["fixture_gate"],
                "semantic_warnings": [], "needs_review": not primary,
                "needs_review_reasons": [] if primary else ["fixture_review"],
                "semantic_outcome": "primary_eligible" if primary else "needs_review",
                "semantic_claim_type_score": 3,
                "structured_gate_text_conflict": paper_index == paper_count - 1 and span_index == spans_per_paper - 1,
                "semantic_claim_type_conflict": False,
            }
            semantics.append(semantic)
            candidates.append({key: semantic[key] for key in semantic if key not in {
                "primary_semantic_eligibility", "hard_gate_failures", "validation_gate_decisions"
            }})
            paper_spans.append(semantic)
        primary_spans = [item for item in paper_spans if item["primary_semantic_eligibility"]]
        papers.append({
            "schema_version": "0.15-cleanroom.1", "pipeline_profile": "document_first_cleanroom_v1",
            "run_name": run_name, "record_created_by_stage": "papers",
            "paper_id": paper_id, "document_id": document_id, "document_record_id": document_id,
            "document_ref": f"input_markdown/{paper_id}.md", "document_genre": genre,
            "document_reaction_family": family, "document_conflicts": [],
            "candidate_span_count": len(paper_spans), "semantic_span_count": len(paper_spans),
            "primary_eligible_span_count": len(primary_spans), "primary_claim_counts": {},
            "secondary_context_count": 0, "evidence_link_count": 0,
            "validation_gate_summary": {}, "quantification_summary": {}, "performance_summary": {},
            "reactor_process_summary": {}, "paper_admissibility_status": "needs_review",
            "paper_admissibility_reasons": ["fixture"],
            "best_evidence_span_ids": [item["cleanroom_span_id"] for item in primary_spans[:3]],
            "review_priority": "high", "paper_warnings": ["fixture_only"],
        })
    links: list[dict[str, Any]] = []
    for paper_index in range(paper_count):
        paper_id = f"P{paper_index:04d}_fixture"
        paper_spans = [item for item in semantics if item["paper_id"] == paper_id]
        for target in paper_spans:
            for evidence in paper_spans:
                if target["cleanroom_span_id"] == evidence["cleanroom_span_id"] or len(links) >= link_count:
                    continue
                link_id = make_evidence_link_id(paper_id, target["cleanroom_span_id"], evidence["cleanroom_span_id"])
                links.append({
                    "schema_version": "0.15-cleanroom.1", "pipeline_profile": "document_first_cleanroom_v1",
                    "run_name": run_name, "record_created_by_stage": "links",
                    "evidence_link_id": link_id, "target_cleanroom_span_id": target["cleanroom_span_id"],
                    "evidence_cleanroom_span_id": evidence["cleanroom_span_id"], "paper_id": paper_id,
                    "link_roles": ["validation_support"], "link_score": 0.9,
                    "link_signals": ["same_paper"], "source_eligibility": "primary_admissible",
                    "is_context_only": False, "link_warnings": [],
                })
            if len(links) >= link_count:
                break
        if len(links) >= link_count:
            break
    for paper in papers:
        paper["evidence_link_count"] = sum(link["paper_id"] == paper["paper_id"] for link in links)
    write_jsonl(run_dir / "documents/document_ledger.jsonl", documents)
    write_jsonl(run_dir / "source_nodes/source_nodes.jsonl", nodes)
    write_jsonl(run_dir / "candidates/candidate_spans.jsonl", candidates)
    write_jsonl(run_dir / "semantics/semantic_spans.jsonl", semantics)
    write_jsonl(run_dir / "links/evidence_links.jsonl", links)
    write_jsonl(run_dir / "papers/paper_records.jsonl", papers)
    write_json(run_dir / "manifests/final_manifest.json", {
        "schema_version": "0.15-cleanroom.1", "pipeline_profile": "document_first_cleanroom_v1",
        "run_name": run_name, "pipeline_status": "completed", "completed_stages": ["validate"],
        "failed_stages": [], "created_at": "2026-01-01T00:00:00Z",
    })
    write_json(run_dir / "reports/cleanroom_validation_summary.json", {
        "result": "PASS", "error_count": 0, "warning_count": 0, "errors": [], "warnings": [],
    })
    return run_dir
