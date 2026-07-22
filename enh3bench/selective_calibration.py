"""Selective intermediate-anchor selection from the v0.16 calibration candidate pool."""

from __future__ import annotations

from collections import Counter
from typing import Any, Callable

from enh3bench.e2e_eval_schema import (
    ANCHOR_HUMAN_FIELDS,
    ANCHOR_TYPE_QUOTAS,
    QUESTION_TEMPLATE_VERSION,
    REVIEWER_IDS,
    SELECTIVE_EVAL_PROFILE,
    SELECTIVE_EVAL_SCHEMA_VERSION,
    deterministic_hash,
    make_anchor_id,
    paper_split,
)


Predicate = Callable[[dict[str, Any]], bool]


def _truthy(value: Any) -> bool:
    return value is True or str(value or "").strip().casefold() == "true"


def _contains(value: Any, expected: str) -> bool:
    return expected in (value if isinstance(value, list) else [])


def _span_specs() -> list[tuple[str, int, Predicate, str]]:
    return [
        ("primary_performance", 2, lambda row: row.get("assigned_primary_stratum") == "primary_performance", "assigned_primary_stratum=primary_performance"),
        ("quantification", 2, lambda row: row.get("assigned_primary_stratum") == "quantification", "assigned_primary_stratum=quantification"),
        ("validation", 2, lambda row: row.get("assigned_primary_stratum") == "validation", "assigned_primary_stratum=validation"),
        ("external_cited_claim", 1, lambda row: row.get("assigned_primary_stratum") == "external_cited_claim", "assigned_primary_stratum=external_cited_claim"),
        ("off_target", 1, lambda row: row.get("assigned_primary_stratum") == "off_target", "assigned_primary_stratum=off_target"),
        ("trap_only", 1, lambda row: row.get("assigned_primary_stratum") == "trap_only", "assigned_primary_stratum=trap_only"),
        ("unclear_mixed_family", 1, lambda row: row.get("assigned_primary_stratum") == "unclear_mixed_family", "assigned_primary_stratum=unclear_mixed_family"),
        ("high_risk_reservoir", 1, lambda row: row.get("selection_stratum") == "high_risk_reservoir", "selection_stratum=high_risk_reservoir"),
    ]


def _paper_specs() -> list[tuple[str, int, Predicate, str]]:
    return [
        ("active_primary_candidate", 1, lambda row: int(row.get("primary_eligible_count") or 0) > 0 and str(row.get("document_genre") or "") == "primary_research", "primary_eligible_count>0 and document_genre=primary_research"),
        ("no_primary_evidence", 1, lambda row: int(row.get("primary_eligible_count") or 0) == 0, "primary_eligible_count=0"),
        ("review_or_perspective", 1, lambda row: str(row.get("document_genre") or "") in {"review", "perspective"}, "runtime genres mapped to review/perspective"),
        ("unclear_or_off_target", 1, lambda row: str(row.get("document_reaction_family") or "").casefold() in {"unclear", "mixed", "linrr", "no2rr", "no3rr", "norr"}, "runtime families mapped to unclear/mixed/off-target"),
    ]


def _document_specs() -> list[tuple[str, int, Predicate, str]]:
    return [
        ("original_research", 1, lambda row: str(row.get("document_genre") or "") == "primary_research", "document_genre=primary_research"),
        ("review_or_perspective", 1, lambda row: str(row.get("document_genre") or "") in {"review", "perspective"}, "runtime genres mapped to review/perspective"),
        ("unclear_or_mixed_family", 1, lambda row: str(row.get("document_reaction_family") or "").casefold() in {"unclear", "mixed"}, "runtime families mapped to unclear/mixed"),
        ("off_target", 1, lambda row: str(row.get("document_reaction_family") or "").casefold() in {"linrr", "no2rr", "no3rr", "norr"}, "runtime families mapped to off-target"),
    ]


def _link_specs() -> list[tuple[str, int, Predicate, str]]:
    return [
        ("primary_support", 1, lambda row: _truthy(row.get("target_primary_eligibility")) and str(row.get("source_eligibility") or "") == "primary_admissible", "runtime mapping: target_primary_eligibility=true and source_eligibility=primary_admissible"),
        ("validation_support", 1, lambda row: _contains(row.get("link_roles"), "validation_support"), "runtime mapping: link_roles contains validation_support"),
        ("quantification_support", 1, lambda row: _contains(row.get("link_roles"), "quantification_support"), "runtime mapping: link_roles contains quantification_support"),
        ("context_only_or_high_risk", 1, lambda row: _truthy(row.get("is_context_only")) or _truthy(row.get("needs_review")), "runtime mapping: context-only or needs_review"),
    ]


SPECS = {
    "span": _span_specs,
    "paper": _paper_specs,
    "document": _document_specs,
    "link": _link_specs,
}


def _diversity_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("paper_id") or ""),
        str(row.get("document_genre") or ""),
        str(row.get("effective_reaction_family") or row.get("document_reaction_family") or ""),
    )


def _choose_for_specs(
    item_type: str,
    rows: list[dict[str, Any]],
    risk_by_id: dict[str, dict[str, Any]],
    seed: int,
) -> list[tuple[dict[str, Any], str, str, int]]:
    specs = SPECS[item_type]()
    eligibility = {
        category: [row for row in rows if predicate(row)]
        for category, _, predicate, _ in specs
    }
    if any(not candidates for candidates in eligibility.values()):
        missing = [category for category, candidates in eligibility.items() if not candidates]
        raise ValueError(f"anchor categories unavailable for {item_type}: {missing}")
    expanded: list[tuple[int, str, Predicate, str]] = []
    for category, quota, predicate, mapping in specs:
        expanded.extend((len(eligibility[category]), category, predicate, mapping) for _ in range(quota))
    expanded.sort(key=lambda value: (value[0], value[1]))
    selected: list[tuple[dict[str, Any], str, str, int]] = []
    used: set[str] = set()
    diversity_counts: Counter[tuple[str, str, str]] = Counter()
    for rarity, category, predicate, mapping in expanded:
        candidates = [row for row in rows if predicate(row) and row["calibration_item_id"] not in used]
        if not candidates:
            raise ValueError(f"anchor quota cannot be filled: {item_type}:{category}")
        candidates.sort(key=lambda row: (
            -int(risk_by_id[row["calibration_item_id"]]["risk_score"]),
            diversity_counts[_diversity_key(row)],
            deterministic_hash(seed, f"anchor:{item_type}:{category}", str(row["calibration_item_id"])),
        ))
        chosen = candidates[0]
        used.add(str(chosen["calibration_item_id"]))
        diversity_counts[_diversity_key(chosen)] += 1
        selected.append((chosen, category, mapping, rarity))
    return selected


def _source_snapshot(item_type: str, row: dict[str, Any]) -> dict[str, Any]:
    human = {"reviewer_id", "review_status"}
    human.update(key for key in row if key.startswith("human_"))
    snapshot = {key: value for key, value in row.items() if key not in human}
    snapshot["item_type"] = item_type
    return snapshot


def select_anchors(
    frames: dict[str, list[dict[str, Any]]],
    risk_ledger: list[dict[str, Any]],
    *,
    seed: int,
    anchor_count: int = 24,
) -> list[dict[str, Any]]:
    if anchor_count != sum(ANCHOR_TYPE_QUOTAS.values()):
        raise ValueError(f"v0.16 profile requires exactly 24 anchors, got {anchor_count}")
    risk_by_id = {row["calibration_item_id"]: row for row in risk_ledger}
    selected: list[tuple[str, dict[str, Any], str, str, int]] = []
    for item_type in ("span", "paper", "document", "link"):
        for row, category, mapping, rarity in _choose_for_specs(item_type, frames[item_type], risk_by_id, seed):
            selected.append((item_type, row, category, mapping, rarity))

    selected_span_ids = {str(row["calibration_item_id"]) for typ, row, *_ in selected if typ == "span"}
    sentinel_candidates = [
        row for row in frames["span"] if str(row["calibration_item_id"]) not in selected_span_ids
    ]
    sentinel_candidates.sort(key=lambda row: deterministic_hash(seed, "anchor:span:random_sentinel", str(row["calibration_item_id"])))
    if not sentinel_candidates:
        raise ValueError("no span remains for random sentinel")
    sentinel = sentinel_candidates[0]
    selected.append(("span", sentinel, "random_sentinel", "fixed SHA-256 random sentinel from remaining spans", len(sentinel_candidates)))

    anchors: list[dict[str, Any]] = []
    for item_type, source, category, mapping, rarity in selected:
        risk = risk_by_id[str(source["calibration_item_id"])]
        split, split_hash = paper_split(seed, str(source["paper_id"]))
        anchors.append({
            "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
            "profile": SELECTIVE_EVAL_PROFILE,
            "anchor_id": make_anchor_id(item_type, str(source["calibration_item_id"])),
            "anchor_type": item_type,
            "source_calibration_item_id": str(source["calibration_item_id"]),
            "paper_id": str(source["paper_id"]),
            "document_id": str(source.get("document_id") or ""),
            "split": split,
            "split_hash_sha256": split_hash,
            "anchor_usage": "development_error_analysis" if split == "development" else "sealed_holdout_anchor",
            "selection_category": category,
            "runtime_category_mapping": mapping,
            "category_candidate_count": rarity,
            "selection_risk_score": int(risk["risk_score"]),
            "selection_risk_tier": str(risk["risk_tier"]),
            "selection_risk_reasons": risk["risk_reasons"],
            "selection_rank_sha256": deterministic_hash(seed, f"anchor:{item_type}:{category}", str(source["calibration_item_id"])),
            "question_template_version": QUESTION_TEMPLATE_VERSION,
            "source_snapshot": _source_snapshot(item_type, source),
        })
    anchors.sort(key=lambda row: (row["anchor_type"], row["selection_category"], row["anchor_id"]))
    counts = Counter(row["anchor_type"] for row in anchors)
    if dict(counts) != ANCHOR_TYPE_QUOTAS:
        raise ValueError(f"anchor type quotas not met: {dict(counts)}")
    if len({row["source_calibration_item_id"] for row in anchors}) != anchor_count:
        raise ValueError("anchor selection contains duplicate source items")
    return anchors


ANCHOR_REVIEW_COLUMNS = (
    "schema_version", "profile", "anchor_id", "anchor_type", "source_calibration_item_id",
    "paper_id", "document_id", "split", "anchor_usage", "selection_category", "reviewer_slot",
    *ANCHOR_HUMAN_FIELDS,
)


def make_anchor_review_rows(anchors: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for anchor in anchors:
        for index, reviewer_id in enumerate(REVIEWER_IDS, 1):
            rows.append({
                "schema_version": SELECTIVE_EVAL_SCHEMA_VERSION,
                "profile": SELECTIVE_EVAL_PROFILE,
                "anchor_id": str(anchor["anchor_id"]),
                "anchor_type": str(anchor["anchor_type"]),
                "source_calibration_item_id": str(anchor["source_calibration_item_id"]),
                "paper_id": str(anchor["paper_id"]),
                "document_id": str(anchor["document_id"]),
                "split": str(anchor["split"]),
                "anchor_usage": str(anchor["anchor_usage"]),
                "selection_category": str(anchor["selection_category"]),
                "reviewer_slot": f"reviewer_{index}",
                "reviewer_id": reviewer_id,
                "review_status": "",
                "human_automatic_assertions_correct": "",
                "human_context_sufficient": "",
                "human_error_category": "",
                "human_notes": "",
            })
    return rows
