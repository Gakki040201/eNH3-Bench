"""Deterministic single-paper E2E case, blank output, judge, and review generation."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Callable

from enh3bench.e2e_eval_schema import (
    ADJUDICATION_FIELDS,
    ANSWER_CONTRACT_VERSION,
    CASE_TYPE_QUOTAS,
    E2E_CASE_PROFILE,
    FINAL_HUMAN_FIELDS,
    HOLDOUT_CASE_TYPE_QUOTAS,
    HUMAN_REVIEW_TEMPLATE_VERSION,
    JUDGE_DIMENSIONS,
    JUDGE_SLOTS,
    JUDGE_TEMPLATE_VERSION,
    QUESTION_TEMPLATES,
    QUESTION_TEMPLATE_VERSION,
    REQUIRED_ANSWER_SECTIONS,
    REVIEWER_IDS,
    SELECTIVE_EVAL_PROFILE,
    SELECTIVE_EVAL_SCHEMA_VERSION,
    deterministic_hash,
    make_case_id,
    make_human_review_id,
    make_judgment_id,
    make_output_id,
    paper_split,
)
from enh3bench.e2e_risk_routing import aggregate_case_risk


Group = dict[str, list[dict[str, Any]]]
Predicate = Callable[[Group], bool]

GENERATION_BATCH_FIELDS = frozenset({
    "schema_version", "profile", "case_id", "paper_id", "question",
    "expected_answer_contract", "required_answer_sections", "allowed_source_span_ids",
    "allowed_evidence_link_ids", "bounded_source_context", "abstention_allowed",
    "generation_status", "network_call_performed", "source_manifest_sha256",
})
EVALUATOR_ONLY_CASE_FIELDS = frozenset({
    "automatic_case_risk_score", "automatic_case_risk_tier", "automatic_case_risk_reasons",
    "automatic_signal_stratum", "answerability_status", "answerability_reasons",
    "abstention_expected", "human_route", "machine_route", "split", "holdout",
    "evaluator_expected_verdict",
})


def _groups(frames: dict[str, list[dict[str, Any]]]) -> dict[str, Group]:
    result: dict[str, Group] = defaultdict(lambda: defaultdict(list))
    for item_type, rows in frames.items():
        for row in rows:
            result[str(row["paper_id"])][item_type].append(row)
    return result


def _document_id(group: Group) -> str:
    values = {
        str(row.get("document_id") or "")
        for item_type in ("paper", "document", "span")
        for row in group.get(item_type, [])
        if str(row.get("document_id") or "")
    }
    if len(values) > 1:
        raise ValueError(f"case paper maps to multiple documents: {sorted(values)}")
    return next(iter(values), "")


def _case_predicates() -> dict[str, Predicate]:
    base = lambda group: bool(group.get("paper") or group.get("document") or group.get("span"))
    return {case_type: base for case_type in CASE_TYPE_QUOTAS}


def _group_features(group: Group) -> tuple[str, str]:
    records = group.get("document", []) + group.get("paper", []) + group.get("span", [])
    genre = next((str(row.get("document_genre")) for row in records if row.get("document_genre")), "")
    family = next((str(row.get("document_reaction_family") or row.get("effective_reaction_family")) for row in records if row.get("document_reaction_family") or row.get("effective_reaction_family")), "")
    return genre, family


def _truthy(value: Any) -> bool:
    return value is True or str(value or "").strip().casefold() == "true"


def _relevant_spans(group: Group, case_type: str) -> list[dict[str, Any]]:
    claims = {
        "primary_evidence_sufficiency": {"performance_result_claim"},
        "ammonia_quantification_assessment": {"ammonia_quantification_claim"},
        "validation_reliability_assessment": {"validation_claim"},
        "reactor_process_extraction": {"reactor_claim"},
    }.get(case_type)
    if claims is None:
        return list(group.get("span", []))
    return [row for row in group.get("span", []) if str(row.get("semantic_claim_type") or "") in claims]


def case_signal_stratum(group: Group, case_type: str) -> str:
    """Return an automatic diversity stratum, never a reference answer or human truth."""
    genre, family = (value.casefold() for value in _group_features(group))
    paper = (group.get("paper") or [{}])[0]
    if case_type in {"paper_scope_classification", "reaction_family_identification"}:
        if family in {"unclear", "mixed", ""}:
            return "uncertain_signal"
        if family in {"linrr", "no2rr", "no3rr", "norr"} or genre in {"review", "perspective"}:
            return "negative_signal"
        return "positive_signal"
    if case_type == "primary_evidence_sufficiency":
        return "positive_signal" if int(paper.get("primary_eligible_count") or 0) > 0 else "negative_signal"
    if case_type == "ammonia_quantification_assessment":
        return "positive_signal" if _truthy(paper.get("has_quantification_evidence")) else "negative_signal"
    if case_type == "validation_reliability_assessment":
        return "positive_signal" if _truthy(paper.get("has_validation_evidence")) else "negative_signal"
    if case_type == "reactor_process_extraction":
        return "positive_signal" if _relevant_spans(group, case_type) else "negative_signal"
    ownership = {str(row.get("claim_ownership") or "").casefold() for row in group.get("span", [])}
    if "unclear" in ownership or not ownership:
        return "uncertain_signal"
    if ownership & {"external_or_cited_authors", "general_literature", "secondary_context"}:
        return "negative_signal"
    return "positive_signal"


def assess_case_answerability(
    group: Group, case_type: str, context: list[dict[str, Any]],
) -> tuple[str, list[str]]:
    """Assess whether this specific bounded question is answerable without using risk tier."""
    has_context = any(str(item.get("excerpt") or "").strip() for item in context)
    if not has_context:
        return "insufficient_evidence", ["bounded_context_empty"]
    if case_type == "paper_scope_classification":
        if any(item.get("context_role") == "document_front_matter" for item in context):
            return "answerable", ["document_front_matter_available", "off_target_scope_is_answerable_as_negative"]
        return "partially_answerable", ["sampled_spans_available", "front_matter_scope_missing"]
    if case_type == "reaction_family_identification":
        _, family = _group_features(group)
        if family.casefold() in {"", "unclear", "mixed"}:
            return "partially_answerable", ["reaction_family_ambiguous", "bounded_text_available"]
        return "answerable", ["reaction_family_signal_present", "bounded_text_available"]
    relevant = _relevant_spans(group, case_type)
    relevant_ids = {str(row.get("cleanroom_span_id") or "") for row in relevant}
    context_ids = {str(item.get("source_span_id") or "") for item in context}
    relevant_in_context = bool(relevant_ids & context_ids)
    if case_type == "primary_evidence_sufficiency":
        if not relevant_in_context:
            return "insufficient_evidence", ["no_primary_performance_evidence_in_bounded_context"]
        if any(_truthy(row.get("primary_semantic_eligibility")) for row in relevant):
            return "answerable", ["primary_performance_evidence_available"]
        return "answerable", ["performance_evidence_available", "negative_primary_sufficiency_assessment_possible"]
    if case_type == "ammonia_quantification_assessment":
        if not relevant_in_context:
            return "insufficient_evidence", ["no_quantification_evidence_in_bounded_context"]
        paper = (group.get("paper") or [{}])[0]
        if _truthy(paper.get("has_quantification_evidence")):
            return "answerable", ["quantification_evidence_available"]
        return "partially_answerable", ["quantification_evidence_fragment_available", "quantification_workflow_incomplete"]
    if case_type == "validation_reliability_assessment":
        if not relevant_in_context:
            return "insufficient_evidence", ["no_validation_evidence_in_bounded_context"]
        paper = (group.get("paper") or [{}])[0]
        if _truthy(paper.get("has_validation_evidence")):
            return "answerable", ["validation_evidence_available"]
        return "partially_answerable", ["validation_fragment_available", "validation_controls_incomplete"]
    if case_type == "reactor_process_extraction":
        if not relevant_in_context:
            return "insufficient_evidence", ["no_reactor_process_evidence_in_bounded_context"]
        return "partially_answerable", ["reported_reactor_parameters_extractable", "unreported_parameters_must_remain_missing"]
    if not group.get("span"):
        return "insufficient_evidence", ["no_claim_span_for_ownership"]
    ownership = {str(row.get("claim_ownership") or "").casefold() for row in group.get("span", [])}
    if ownership and ownership <= {"unclear", ""}:
        return "partially_answerable", ["claim_ownership_ambiguous"]
    return "answerable", ["claim_ownership_signal_available"]


def _select_case_assignments(
    frames: dict[str, list[dict[str, Any]]],
    risk_ledger: list[dict[str, Any]],
    *,
    seed: int,
    e2e_case_count: int,
    development_case_count: int,
) -> list[tuple[str, str, str]]:
    if e2e_case_count != sum(CASE_TYPE_QUOTAS.values()):
        raise ValueError(f"v0.16 profile requires exactly 48 E2E cases, got {e2e_case_count}")
    if development_case_count != 36:
        raise ValueError(f"v0.16 profile requires exactly 36 development cases, got {development_case_count}")
    groups = _groups(frames)
    predicates = _case_predicates()
    risk_by_id = {str(row["calibration_item_id"]): row for row in risk_ledger}
    candidate_metadata: dict[tuple[str, str], tuple[str, str]] = {}
    for paper_id, group in groups.items():
        for case_type in CASE_TYPE_QUOTAS:
            context = _bounded_context(group, case_type, risk_by_id)
            status, _ = assess_case_answerability(group, case_type, context)
            candidate_metadata[(paper_id, case_type)] = (status, case_signal_stratum(group, case_type))

    tasks: list[tuple[int, str, str, str, str]] = []
    for case_type, total in CASE_TYPE_QUOTAS.items():
        holdout = HOLDOUT_CASE_TYPE_QUOTAS[case_type]
        for split, count in (("development", total - holdout), ("holdout", holdout)):
            coverage_targets = [
                ("answerable", "positive_signal"),
                ("answerable", "negative_signal"),
                ("partially_answerable", "uncertain_signal"),
                ("insufficient_evidence", "any"),
            ] if split == "development" else []
            for index in range(count):
                desired_status, desired_signal = coverage_targets[index] if index < len(coverage_targets) else ("any", "any")
                eligible_count = sum(
                    1 for paper_id, group in groups.items()
                    if _document_id(group) and paper_split(seed, paper_id)[0] == split
                    and predicates[case_type](group)
                    and (desired_status == "any" or candidate_metadata[(paper_id, case_type)][0] == desired_status)
                    and (desired_signal == "any" or candidate_metadata[(paper_id, case_type)][1] == desired_signal)
                )
                tasks.append((eligible_count, case_type, split, desired_status, desired_signal))
    tasks.sort(key=lambda value: (value[0], value[1], value[2], value[3], value[4]))
    used_papers: set[str] = set()
    feature_counts: Counter[tuple[str, str]] = Counter()
    answerability_counts: Counter[str] = Counter()
    signal_counts: Counter[str] = Counter()
    selected: list[tuple[str, str, str]] = []
    for eligible_count, case_type, split, desired_status, desired_signal in tasks:
        candidates = [
            paper_id for paper_id, group in groups.items()
            if paper_id not in used_papers
            and _document_id(group)
            and paper_split(seed, paper_id)[0] == split
            and predicates[case_type](group)
        ]
        if not candidates:
            raise ValueError(f"cannot fill E2E case quota: {case_type}:{split}")
        candidates.sort(key=lambda paper_id: (
            candidate_metadata[(paper_id, case_type)][0] != desired_status if desired_status != "any" else False,
            candidate_metadata[(paper_id, case_type)][1] != desired_signal if desired_signal != "any" else False,
            answerability_counts[candidate_metadata[(paper_id, case_type)][0]],
            signal_counts[candidate_metadata[(paper_id, case_type)][1]],
            feature_counts[_group_features(groups[paper_id])],
            deterministic_hash(seed, f"case:{case_type}:{split}", paper_id),
        ))
        paper_id = candidates[0]
        used_papers.add(paper_id)
        feature_counts[_group_features(groups[paper_id])] += 1
        answerability_counts[candidate_metadata[(paper_id, case_type)][0]] += 1
        signal_counts[candidate_metadata[(paper_id, case_type)][1]] += 1
        selected.append((paper_id, case_type, split))
    return selected


def _bounded_context(group: Group, case_type: str, risk_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    context: list[dict[str, Any]] = []
    for row in group.get("document", [])[:1]:
        excerpt = str(row.get("front_matter_excerpt") or "")[:700]
        if excerpt:
            context.append({
                "context_role": "document_front_matter", "source_span_id": "",
                "source_node_id": "", "evidence_link_id": "", "excerpt": excerpt,
            })
    spans = sorted(
        group.get("span", []),
        key=lambda row: (
            -int(risk_by_id.get(str(row["calibration_item_id"]), {}).get("risk_score", 0)),
            deterministic_hash(0, f"context:{case_type}", str(row["calibration_item_id"])),
        ),
    )
    preferred_claim = {
        "primary_evidence_sufficiency": "performance_result_claim",
        "ammonia_quantification_assessment": "ammonia_quantification_claim",
        "validation_reliability_assessment": "validation_claim",
        "reactor_process_extraction": "reactor_claim",
    }.get(case_type)
    if preferred_claim:
        spans.sort(key=lambda row: row.get("semantic_claim_type") != preferred_claim)
    for row in spans:
        excerpt = str(row.get("target_excerpt") or "")[:700]
        if excerpt:
            context.append({
                "context_role": "sampled_semantic_span",
                "source_span_id": str(row.get("cleanroom_span_id") or ""),
                "source_node_id": str(row.get("source_node_id") or ""),
                "evidence_link_id": "", "excerpt": excerpt,
            })
        if len(context) >= 5:
            break
    for row in group.get("link", []):
        for role, span_field, node_field, excerpt_field in (
            ("link_target", "target_span_id", "target_source_node_id", "target_excerpt"),
            ("linked_evidence", "evidence_span_id", "evidence_source_node_id", "evidence_excerpt"),
        ):
            excerpt = str(row.get(excerpt_field) or "")[:700]
            if excerpt:
                context.append({
                    "context_role": role,
                    "source_span_id": str(row.get(span_field) or ""),
                    "source_node_id": str(row.get(node_field) or ""),
                    "evidence_link_id": str(row.get("evidence_link_id") or ""),
                    "excerpt": excerpt,
                })
            if len(context) >= 6:
                break
        if len(context) >= 6:
            break
    return context[:6]


def _answer_contract(case_type: str) -> dict[str, Any]:
    return {
        "contract_version": ANSWER_CONTRACT_VERSION,
        "case_type": case_type,
        "answer_must_distinguish_observation_from_inference": True,
        "every_scientific_claim_requires_allowlisted_citation": True,
        "cross_paper_synthesis_allowed": False,
        "must_state_missing_or_ambiguous_evidence": True,
        "may_abstain_when_evidence_is_insufficient": True,
        "reference_answer_text_provided": False,
    }


def generate_cases(
    frames: dict[str, list[dict[str, Any]]],
    risk_ledger: list[dict[str, Any]],
    *,
    source_manifest_sha256: str,
    seed: int,
    e2e_case_count: int = 48,
    development_case_count: int = 36,
) -> list[dict[str, Any]]:
    groups = _groups(frames)
    risk_by_id = {str(row["calibration_item_id"]): row for row in risk_ledger}
    assignments = _select_case_assignments(
        frames, risk_ledger, seed=seed, e2e_case_count=e2e_case_count,
        development_case_count=development_case_count,
    )
    cases: list[dict[str, Any]] = []
    for paper_id, case_type, split in assignments:
        group = groups[paper_id]
        document_id = _document_id(group)
        context = _bounded_context(group, case_type, risk_by_id)
        allowed_spans = sorted({str(item["source_span_id"]) for item in context if item["source_span_id"]})
        allowed_links = sorted({str(item["evidence_link_id"]) for item in context if item["evidence_link_id"]})
        risk = aggregate_case_risk(case_type, paper_id, risk_ledger, has_citable_span=bool(allowed_spans))
        answerability_status, answerability_reasons = assess_case_answerability(group, case_type, context)
        expected_abstention = answerability_status in {"insufficient_evidence", "out_of_scope"}
        if expected_abstention:
            risk["human_route"] = "abstain_then_review"
            risk["machine_route"] = "abstention_recommended"
        elif risk["automatic_case_risk_tier"] == "T3":
            risk["human_route"] = "manual_escalation"
            risk["machine_route"] = "enhanced_generation_checks"
        elif risk["automatic_case_risk_tier"] == "T2":
            risk["human_route"] = "intermediate_anchor_and_final_review"
        else:
            risk["human_route"] = "final_output_review"
        split_check, split_hash = paper_split(seed, paper_id)
        if split_check != split:
            raise ValueError(f"paper split changed during case generation: {paper_id}")
        cases.append({
            "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
            "profile": SELECTIVE_EVAL_PROFILE,
            "e2e_case_profile": E2E_CASE_PROFILE,
            "case_id": make_case_id(paper_id, document_id, case_type),
            "paper_id": paper_id,
            "document_id": document_id,
            "split": split,
            "split_hash_sha256": split_hash,
            "case_type": case_type,
            "question_template_version": QUESTION_TEMPLATE_VERSION,
            "question": QUESTION_TEMPLATES[case_type],
            "expected_answer_contract": _answer_contract(case_type),
            "required_answer_sections": list(REQUIRED_ANSWER_SECTIONS),
            "allowed_source_span_ids": allowed_spans,
            "allowed_evidence_link_ids": allowed_links,
            "bounded_source_context": context,
            **risk,
            "automatic_signal_stratum": case_signal_stratum(group, case_type),
            "answerability_status": answerability_status,
            "answerability_reasons": answerability_reasons,
            "abstention_allowed": True,
            "abstention_expected": expected_abstention,
            "generation_status": "pending",
            "source_manifest_sha256": source_manifest_sha256,
            "human_fields": {"human_case_review_status": "", "human_case_notes": ""},
        })
    cases.sort(key=lambda row: (row["split"], row["case_type"], row["case_id"]))
    if Counter(row["case_type"] for row in cases) != Counter(CASE_TYPE_QUOTAS):
        raise ValueError("E2E case type quotas not met")
    if len({row["paper_id"] for row in cases}) != e2e_case_count:
        raise ValueError("E2E cases do not use unique papers")
    return cases


def make_api_generation_batch(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
        "profile": SELECTIVE_EVAL_PROFILE,
        "case_id": case["case_id"],
        "paper_id": case["paper_id"],
        "question": case["question"],
        "expected_answer_contract": case["expected_answer_contract"],
        "required_answer_sections": case["required_answer_sections"],
        "allowed_source_span_ids": case["allowed_source_span_ids"],
        "allowed_evidence_link_ids": case["allowed_evidence_link_ids"],
        "bounded_source_context": case["bounded_source_context"],
        "abstention_allowed": case["abstention_allowed"],
        "generation_status": "pending",
        "network_call_performed": False,
        "source_manifest_sha256": case["source_manifest_sha256"],
    } for case in cases]


def make_api_output_templates(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{
        "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
        "profile": SELECTIVE_EVAL_PROFILE,
        "api_output_id": make_output_id(str(case["case_id"])),
        "source_case_id": case["case_id"],
        "source_manifest_sha256": case["source_manifest_sha256"],
        "answer_text": "", "answer_status": "", "confidence_statement": "",
        "claims": [], "citations": [], "limitations": [], "abstention_reason": "",
        "generation_model": "", "generation_prompt_version": "", "generation_parameters": {},
        "generation_status": "pending", "api_call_performed": False,
    } for case in cases]


def _blank_dimension() -> dict[str, Any]:
    return {
        "score": None, "verdict": "", "confidence": None, "rationale": "", "evidence": [],
        "judge_model": "", "judge_prompt_version": "",
    }


def make_machine_judgment_templates(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        for judge_slot in JUDGE_SLOTS:
            rows.append({
                "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
                "profile": SELECTIVE_EVAL_PROFILE,
                "machine_judgment_id": make_judgment_id(str(case["case_id"]), judge_slot),
                "source_case_id": case["case_id"],
                "source_api_output_id": make_output_id(str(case["case_id"])),
                "source_manifest_sha256": case["source_manifest_sha256"],
                "judge_slot": judge_slot, "judge_id": "", "judgment_status": "pending",
                "dimensions": {dimension: _blank_dimension() for dimension in JUDGE_DIMENSIONS},
                "judge_disagreement_status": "not_available", "human_truth_claimed": False,
                "judge_call_performed": False,
            })
    return rows


E2E_REVIEW_COLUMNS = (
    "schema_version", "profile", "human_review_id", "case_id", "api_output_id", "paper_id",
    "document_id", "split", "case_type", "reviewer_slot", *FINAL_HUMAN_FIELDS,
)


def make_e2e_human_review_rows(cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for case in cases:
        for index, reviewer_id in enumerate(REVIEWER_IDS, 1):
            reviewer_slot = f"reviewer_{index}"
            row = {
                "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
                "profile": SELECTIVE_EVAL_PROFILE,
                "human_review_id": make_human_review_id(str(case["case_id"]), reviewer_slot),
                "case_id": str(case["case_id"]),
                "api_output_id": make_output_id(str(case["case_id"])),
                "paper_id": str(case["paper_id"]), "document_id": str(case["document_id"]),
                "split": str(case["split"]), "case_type": str(case["case_type"]),
                "reviewer_slot": reviewer_slot, "reviewer_id": reviewer_id, "review_status": "",
            }
            row.update({field: "" for field in FINAL_HUMAN_FIELDS if field not in row})
            rows.append(row)
    return rows


ADJUDICATION_COLUMNS = (
    "schema_version", "profile", "case_id", "api_output_id", "paper_id", "split",
    "reviewer_1_id", "reviewer_2_id", "reviewer_1_summary", "reviewer_2_summary",
    *ADJUDICATION_FIELDS,
)


def make_adjudication_rows(cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{
        "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
        "profile": SELECTIVE_EVAL_PROFILE,
        "case_id": str(case["case_id"]), "api_output_id": make_output_id(str(case["case_id"])),
        "paper_id": str(case["paper_id"]), "split": str(case["split"]),
        "reviewer_1_id": "", "reviewer_2_id": "", "reviewer_1_summary": "",
        "reviewer_2_summary": "", **{field: "" for field in ADJUDICATION_FIELDS},
    } for case in cases]
