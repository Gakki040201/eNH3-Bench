"""Conservative paper-level aggregation for clean-room semantic spans."""

from __future__ import annotations

from collections import Counter
from typing import Any

from enh3bench.cleanroom_schema import common_fields


def aggregate_paper_records(
    documents: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    semantics: list[dict[str, Any]],
    links: list[dict[str, Any]],
    *,
    run_name: str,
    profile: str,
) -> list[dict[str, Any]]:
    """Produce one explainable record per document, including documents with no candidates."""

    records: list[dict[str, Any]] = []
    for document in sorted(documents, key=lambda item: str(item["paper_id"])):
        paper_id = str(document["paper_id"])
        paper_candidates = [item for item in candidates if str(item["paper_id"]) == paper_id]
        paper_semantics = [item for item in semantics if str(item["paper_id"]) == paper_id]
        paper_links = [item for item in links if str(item["paper_id"]) == paper_id]
        primary = [item for item in paper_semantics if item.get("primary_semantic_eligibility")]
        results = [item for item in primary if item.get("performance_result_evidence")]
        secondary = [item for item in paper_semantics if item.get("semantic_outcome") == "secondary_context"]
        needs_review = [item for item in paper_semantics if item.get("needs_review")]
        conflicts = list(document.get("document_warnings") or [])
        if document.get("document_reaction_family_conflict"):
            conflicts.append("document_reaction_family_conflict")
        gate_names = sorted({key for item in paper_semantics for key in (item.get("validation_gate_decisions") or {})})
        gate_summary = {
            name: sum(bool((item.get("validation_gate_decisions") or {}).get(name, {}).get("satisfied")) for item in primary)
            for name in gate_names
        }
        required_control_count = sum(gate_summary.get(name, 0) > 0 for name in (
            "ammonia_quantification", "blank_control", "contamination_control", "isotope_15N"
        ))
        if conflicts or needs_review or document.get("document_reaction_family") in {"unclear", "mixed"}:
            status = "needs_review"
            reasons = ["critical_conflict_or_uncertainty"]
        elif not results:
            status = "insufficient_evidence"
            reasons = ["no_primary_eligible_result_bearing_evidence"]
        elif required_control_count < 2:
            status = "partially_supported"
            reasons = ["primary_result_present_but_validation_controls_incomplete"]
        else:
            status = "supported_with_limitations"
            reasons = ["primary_result_and_source_grounded_controls_present", "scientific_comparability_not_established"]
        claim_counts = Counter(str(item.get("semantic_claim_type") or "untyped_claim") for item in primary)
        best_ids = [str(item["cleanroom_span_id"]) for item in sorted(
            primary, key=lambda item: (-float(item.get("semantic_claim_type_score") or 0), int(item["source_start_offset"])))
        ][:10]
        records.append({
            **common_fields(run_name, "papers", profile),
            "paper_id": paper_id,
            "document_id": document["document_id"],
            "document_record_id": document["document_id"],
            "document_ref": document["document_ref"],
            "document_genre": document["document_genre"],
            "document_reaction_family": document["document_reaction_family"],
            "document_conflicts": sorted(set(conflicts)),
            "candidate_span_count": len(paper_candidates),
            "semantic_span_count": len(paper_semantics),
            "primary_eligible_span_count": len(primary),
            "primary_claim_counts": dict(sorted(claim_counts.items())),
            "secondary_context_count": len(secondary),
            "evidence_link_count": len(paper_links),
            "validation_gate_summary": gate_summary,
            "quantification_summary": {
                "primary_quantification_span_count": sum(bool(item.get("ammonia_quantification_signal")) for item in primary),
                "trap_only_span_count": sum(bool(item.get("gas_purification_trap_signal")) and not bool(item.get("ammonia_quantification_signal")) for item in paper_semantics),
            },
            "performance_summary": {
                "primary_result_span_count": len(results),
                "quantitative_result_span_count": sum(bool(item.get("quantitative_performance_evidence")) for item in results),
            },
            "reactor_process_summary": {
                "reactor_span_count": sum(item.get("semantic_claim_type") == "reactor_claim" for item in paper_semantics),
                "process_span_count": sum(item.get("semantic_claim_type") == "process_claim" for item in paper_semantics),
            },
            "paper_admissibility_status": status,
            "paper_admissibility_reasons": reasons,
            "best_evidence_span_ids": best_ids,
            "review_priority": "high" if status == "needs_review" else "medium" if status == "partially_supported" else "normal",
            "paper_warnings": ["paper_level_record_is_limited_aggregation", "scientific_comparability_not_established"],
        })
    return records
