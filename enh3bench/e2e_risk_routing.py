"""Deterministic, explainable risk scoring and routing for selective evaluation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from enh3bench.e2e_eval_schema import RISK_MODEL_VERSION


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() == "true"


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


CORRELATION_GROUPS = {
    "span_needs_review": ("span_eligibility", 28),
    "span_not_primary_eligible": ("span_eligibility", 28),
    "span_hard_gate_failures": ("span_eligibility", 28),
    "span_low_semantic_confidence": ("span_semantic_ambiguity", 28),
    "span_medium_semantic_confidence": ("span_semantic_ambiguity", 28),
    "span_unclear_or_mixed_family": ("span_semantic_ambiguity", 28),
    "span_unclear_ownership": ("span_semantic_ambiguity", 28),
    "span_off_target_family": ("span_scope_alignment", 22),
    "span_external_or_context_ownership": ("span_scope_alignment", 22),
    "span_context_insufficient": ("span_evidence_availability", 30),
    "span_expected_evidence_link_absent": ("span_evidence_availability", 30),
    "span_validation_gate_conflict": ("span_evidence_availability", 30),
    "paper_admissibility_needs_review": ("paper_review_metadata", 18),
    "paper_limitations_present": ("paper_review_metadata", 18),
    "paper_no_primary_eligible_evidence": ("paper_evidence_gap", 32),
    "paper_validation_evidence_missing": ("paper_evidence_gap", 32),
    "paper_quantification_evidence_missing": ("paper_evidence_gap", 32),
    "paper_non_primary_or_unclear_genre": ("paper_classification", 24),
    "paper_unclear_or_off_target_family": ("paper_classification", 24),
    "document_genre_conflict": ("document_structured_conflict", 30),
    "document_family_conflict": ("document_structured_conflict", 30),
    "document_non_primary_or_unclear_genre": ("document_classification", 25),
    "document_unclear_or_mixed_family": ("document_classification", 25),
    "document_off_target_family": ("document_classification", 25),
    "link_context_only": ("link_source_admissibility", 28),
    "link_source_not_primary_eligible": ("link_source_admissibility", 28),
    "link_contextual_provenance": ("link_source_admissibility", 28),
    "link_needs_review": ("link_ambiguity", 20),
    "link_role_ambiguity": ("link_ambiguity", 20),
    "link_far_endpoint_distance": ("link_endpoint_quality", 24),
    "link_target_evidence_claim_conflict": ("link_endpoint_quality", 24),
}


def _add(reasons: list[dict[str, Any]], code: str, weight: int, detail: Any = None) -> None:
    group, cap = CORRELATION_GROUPS.get(code, (code, weight))
    reasons.append({
        "code": code,
        "raw_weight": weight,
        "weight": weight,
        "correlation_group": group,
        "correlation_group_cap": cap,
        "detail": detail,
    })


def _apply_correlation_caps(reasons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cap correlated signals while retaining every triggered reason for audit."""
    contributed: dict[str, int] = defaultdict(int)
    for reason in reasons:
        group = str(reason["correlation_group"])
        cap = int(reason["correlation_group_cap"])
        remaining = max(0, cap - contributed[group])
        applied = min(int(reason["raw_weight"]), remaining)
        reason["weight"] = applied
        contributed[group] += applied
    return reasons


def risk_tier(score: int) -> str:
    if score >= 70:
        return "T3"
    if score >= 40:
        return "T2"
    if score >= 20:
        return "T1"
    return "T0"


def routes_for_tier(tier: str) -> tuple[str, str]:
    return {
        "T0": ("auto_validate_only", "deterministic_validation"),
        "T1": ("final_output_review", "standard_generation_checks"),
        "T2": ("intermediate_anchor_and_final_review", "enhanced_generation_checks"),
        "T3": ("abstain_then_review", "abstention_recommended"),
    }[tier]


def score_span(row: dict[str, Any]) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    if _truthy(row.get("needs_review")):
        _add(reasons, "span_needs_review", 12)
    confidence = str(row.get("semantic_confidence") or "").casefold()
    if confidence == "low":
        _add(reasons, "span_low_semantic_confidence", 22)
    elif confidence == "medium":
        _add(reasons, "span_medium_semantic_confidence", 10)
    family = str(row.get("effective_reaction_family") or "").casefold()
    if family in {"unclear", "mixed"}:
        _add(reasons, "span_unclear_or_mixed_family", 18, family)
    elif family in {"linrr", "no2rr", "no3rr", "norr"}:
        _add(reasons, "span_off_target_family", 14, family)
    ownership = str(row.get("claim_ownership") or "").casefold()
    if ownership in {"external_or_cited_authors", "general_literature", "secondary_context"}:
        _add(reasons, "span_external_or_context_ownership", 14, ownership)
    elif ownership == "unclear":
        _add(reasons, "span_unclear_ownership", 10)
    stratum = str(row.get("assigned_primary_stratum") or "")
    selection = str(row.get("selection_stratum") or "")
    if stratum == "trap_only":
        _add(reasons, "span_trap_only", 18)
    if selection == "high_risk_reservoir":
        _add(reasons, "span_high_risk_reservoir", 4)
    if stratum == "structured_text_conflict" or selection == "structured_text_conflict":
        _add(reasons, "span_structured_text_conflict", 70)
    if not _truthy(row.get("primary_semantic_eligibility")):
        _add(reasons, "span_not_primary_eligible", 8)
    claim_type = str(row.get("semantic_claim_type") or "")
    matching = {str(value) for value in _list(row.get("all_matching_strata"))}
    if ("quantification" in matching) != (claim_type == "ammonia_quantification_claim"):
        _add(reasons, "span_quantification_claim_signal_conflict", 14)
    gates = row.get("validation_gate_decisions") if isinstance(row.get("validation_gate_decisions"), dict) else {}
    if claim_type == "validation_claim" and gates and not any(_truthy(value) for value in gates.values()):
        _add(reasons, "span_validation_gate_conflict", 18)
    failures = _list(row.get("hard_gate_failures"))
    if failures:
        _add(reasons, "span_hard_gate_failures", min(24, 8 + 4 * len(failures)), failures)
    if not str(row.get("previous_context_excerpt") or "") and not str(row.get("next_context_excerpt") or ""):
        _add(reasons, "span_context_insufficient", 8)
    linked_ids = _list(row.get("linked_evidence_ids"))
    if claim_type in {"performance_result_claim", "ammonia_quantification_claim", "validation_claim"} and not linked_ids:
        _add(reasons, "span_expected_evidence_link_absent", 12)
    return reasons


def score_paper(row: dict[str, Any]) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    if str(row.get("paper_admissibility_status") or "") == "needs_review":
        _add(reasons, "paper_admissibility_needs_review", 18)
    if int(row.get("primary_eligible_count") or 0) == 0:
        _add(reasons, "paper_no_primary_eligible_evidence", 20)
    limitations = _list(row.get("limitations"))
    if limitations:
        _add(reasons, "paper_limitations_present", min(8, 2 + 2 * len(limitations)), limitations)
    genre = str(row.get("document_genre") or "").casefold()
    family = str(row.get("document_reaction_family") or "").casefold()
    if genre in {"review", "perspective", "mixed", "unclear"}:
        _add(reasons, "paper_non_primary_or_unclear_genre", 14, genre)
    if family in {"unclear", "mixed", "linrr", "no2rr", "no3rr", "norr"}:
        _add(reasons, "paper_unclear_or_off_target_family", 14, family)
    if not _truthy(row.get("has_validation_evidence")):
        _add(reasons, "paper_validation_evidence_missing", 10)
    if not _truthy(row.get("has_quantification_evidence")):
        _add(reasons, "paper_quantification_evidence_missing", 10)
    return reasons


def score_document(row: dict[str, Any]) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    conflicts = _list(row.get("document_conflicts"))
    for conflict in conflicts:
        code = "document_genre_conflict" if "genre" in str(conflict) else "document_family_conflict"
        _add(reasons, code, 24, conflict)
    genre = str(row.get("document_genre") or "").casefold()
    family = str(row.get("document_reaction_family") or "").casefold()
    if genre in {"review", "perspective", "mixed", "unclear"}:
        _add(reasons, "document_non_primary_or_unclear_genre", 15, genre)
    if family in {"unclear", "mixed"}:
        _add(reasons, "document_unclear_or_mixed_family", 20, family)
    elif family in {"linrr", "no2rr", "no3rr", "norr"}:
        _add(reasons, "document_off_target_family", 15, family)
    front = str(row.get("front_matter_excerpt") or "")
    if len(front.strip()) < 80:
        _add(reasons, "document_front_matter_scope_insufficient", 15, len(front.strip()))
    return reasons


def score_link(row: dict[str, Any]) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    if _truthy(row.get("is_context_only")):
        _add(reasons, "link_context_only", 22)
    if _truthy(row.get("needs_review")):
        _add(reasons, "link_needs_review", 18)
    roles = _list(row.get("link_roles"))
    if len(roles) != 1:
        _add(reasons, "link_role_ambiguity", 14, roles)
    if str(row.get("source_eligibility") or "") != "primary_admissible":
        _add(reasons, "link_source_not_primary_eligible", 20, row.get("source_eligibility"))
    provenance = str(row.get("evidence_provenance") or "")
    if provenance in {"figure_or_scheme_caption", "secondary_document_body", "background"}:
        _add(reasons, "link_contextual_provenance", 18, provenance)
    distance = str(row.get("source_distance_band") or "")
    if distance == "far":
        _add(reasons, "link_far_endpoint_distance", 10)
    target = str(row.get("target_claim_type") or "")
    evidence = str(row.get("evidence_claim_type") or "")
    expected = {
        "performance_result_claim": {"ammonia_quantification_claim", "validation_claim", "protocol_claim"},
        "ammonia_quantification_claim": {"ammonia_quantification_claim", "protocol_claim"},
        "validation_claim": {"validation_claim", "protocol_claim", "ammonia_quantification_claim"},
    }
    if target in expected and evidence not in expected[target]:
        _add(reasons, "link_target_evidence_claim_conflict", 16, {"target": target, "evidence": evidence})
    return reasons


SCORERS = {"span": score_span, "paper": score_paper, "document": score_document, "link": score_link}


def score_item(item_type: str, row: dict[str, Any]) -> dict[str, Any]:
    reasons = _apply_correlation_caps(SCORERS[item_type](row))
    score = min(100, sum(int(reason["weight"]) for reason in reasons))
    tier = risk_tier(score)
    human_route, machine_route = routes_for_tier(tier)
    return {
        "risk_model_version": RISK_MODEL_VERSION,
        "risk_score": score,
        "risk_tier": tier,
        "risk_reasons": reasons,
        "human_route": human_route,
        "machine_route": machine_route,
    }


def build_risk_ledger(frames: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    ledger: list[dict[str, Any]] = []
    for item_type in ("span", "paper", "document", "link"):
        for row in frames[item_type]:
            result = score_item(item_type, row)
            ledger.append({
                "calibration_item_id": str(row["calibration_item_id"]),
                "item_type": item_type,
                "paper_id": str(row["paper_id"]),
                "document_id": str(row.get("document_id") or ""),
                "source_sampling_hash": str(row.get("sampling_hash") or ""),
                **result,
            })
    return ledger


def aggregate_case_risk(
    case_type: str, paper_id: str, ledger: Iterable[dict[str, Any]], *, has_citable_span: bool,
) -> dict[str, Any]:
    relevant = [row for row in ledger if row["paper_id"] == paper_id]
    scores = [int(row["risk_score"]) for row in relevant]
    base = round(sum(scores) / len(scores)) if scores else 45
    maximum = max(scores, default=45)
    reasons: list[dict[str, Any]] = [{
        "code": "mean_source_item_risk", "weight": base,
        "detail": {"source_item_count": len(scores), "maximum_source_item_risk": maximum},
    }]
    modifier = 0
    if maximum >= 70:
        modifier += 10
        reasons.append({"code": "high_risk_source_item_present", "weight": 10, "detail": maximum})
    if not has_citable_span:
        modifier += 30
        reasons.append({"code": "case_has_no_citable_sampled_span", "weight": 30, "detail": None})
    if case_type in {"primary_evidence_sufficiency", "ammonia_quantification_assessment", "validation_reliability_assessment"}:
        modifier += 8
        reasons.append({"code": "case_requires_strong_evidentiary_support", "weight": 8, "detail": case_type})
    score = min(100, base + modifier)
    tier = risk_tier(score)
    human_route, machine_route = routes_for_tier(tier)
    return {
        "automatic_case_risk_score": score,
        "automatic_case_risk_tier": tier,
        "automatic_case_risk_reasons": reasons,
        "human_route": human_route,
        "machine_route": machine_route,
    }


def summarize_risk(ledger: Iterable[dict[str, Any]]) -> dict[str, Any]:
    by_tier: dict[str, int] = defaultdict(int)
    by_type: dict[str, int] = defaultdict(int)
    by_route: dict[str, int] = defaultdict(int)
    rows = list(ledger)
    for row in rows:
        by_tier[row["risk_tier"]] += 1
        by_type[row["item_type"]] += 1
        by_route[row["human_route"]] += 1
    return {
        "total_items": len(rows),
        "risk_tier_counts": {tier: by_tier[tier] for tier in ("T0", "T1", "T2", "T3")},
        "item_type_counts": {item_type: by_type[item_type] for item_type in ("span", "paper", "document", "link")},
        "human_route_counts": dict(sorted(by_route.items())),
        "risk_scores_are_probabilities": False,
    }
