"""Rule-based, paper-scoped linking of evidence spans for context packets."""

from __future__ import annotations

import re
from typing import Any

from enh3bench.span_identity import normalize_section_path, parse_legacy_span_order


LINK_TYPES = (
    "performance",
    "validation",
    "quantification",
    "reactor",
    "process",
    "negative_or_contradicting",
    "context_hint",
)

DEFAULT_LINK_LIMITS = {
    "maximum_per_category": 2,
    "maximum_total_links": 12,
    "adjacent_before": 1,
    "adjacent_after": 1,
    "same_section_maximum": 4,
}

SIGNALS = {
    "performance": (
        "faradaic efficiency", "nh3 yield", "ammonia yield", "current density", "potential", "voltage", "runtime", "stability"
    ),
    "validation": (
        "15n", "isotope", "ar blank", "argon blank", "n2-free", "nox screening", "nitrate/nitrite impurity", "contamination control"
    ),
    "quantification": (
        "ion chromatography", "nmr", "uv-vis", "uv vis", "colorimetric", "calibration", "gas trap", "ammonia quantification"
    ),
    "reactor": (
        "flow cell", "gde", "gas diffusion electrode", "mea", "ssc", "active area", "flow rate", "outlet", "wetting", "flooding", "stability"
    ),
    "process": (
        "capture", "separation", "solvent inventory", "electrolyte recycle", "replacement", "hydrogen source", "hor", "auxiliary load", "energy boundary"
    ),
    "negative_or_contradicting": (
        "false positive", "contamination", "extraneous ammonia", "reassignment", "negative evidence", "background ammonia"
    ),
}

LOW_TRUST_PROVENANCE = {"reference", "bibliography", "figure_caption", "scheme_caption", "review_table"}
LOW_TRUST_TEXT_CLASSES = {"reference_list", "figure_caption", "review_table", "background_context"}
PRIMARY_PROVENANCE = {"body", "methods", "results", "discussion", "supplementary"}


def classify_link_type(record: dict[str, Any]) -> str:
    """Return the highest-priority link type for one record."""

    return _link_types(record)[0]


def score_link(target: dict[str, Any], candidate: dict[str, Any]) -> float:
    """Score a candidate; cross-paper candidates are ineligible."""

    return _score_link_detailed(target, candidate, classify_link_type(candidate))[0]


def link_supporting_evidence(
    target: dict[str, Any],
    paper_records: list[dict[str, Any]],
    limits: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Link categorized evidence without changing target boundary or input records."""

    settings = dict(DEFAULT_LINK_LIMITS)
    if limits:
        settings.update({key: int(value) for key, value in limits.items() if key in settings})
    per_category = max(0, settings["maximum_per_category"])
    total_limit = max(0, settings["maximum_total_links"])
    target_paper = str(target.get("paper_id") or "")
    target_id = _span_id(target)
    candidates: dict[str, list[tuple[float, dict[str, Any], list[str]]]] = {link_type: [] for link_type in LINK_TYPES}
    warnings: list[str] = []

    for candidate in paper_records:
        candidate_id = _span_id(candidate)
        if not candidate_id or candidate_id == target_id:
            continue
        candidate_paper = str(candidate.get("paper_id") or "")
        if candidate_paper != target_paper:
            warnings.append(f"cross_paper_candidate_rejected:{candidate_id}")
            continue
        for link_type in _link_types(candidate):
            score, score_signals = _score_link_detailed(target, candidate, link_type)
            if score == float("-inf"):
                continue
            candidates[link_type].append((score, candidate, score_signals))

    selected: dict[str, list[dict[str, Any]]] = {link_type: [] for link_type in LINK_TYPES}
    linking_signals: list[str] = []
    total = 0
    for link_type in LINK_TYPES:
        ranked = sorted(
            candidates[link_type],
            key=lambda item: (-item[0], abs(_span_order(item[1]) - _span_order(target)), _span_id(item[1])),
        )
        for score, candidate, score_signals in ranked[:per_category]:
            if total >= total_limit:
                break
            linked = _linked_record(target, candidate, link_type, score, score_signals)
            selected[link_type].append(linked)
            linking_signals.extend(f"{_span_id(candidate)}:{signal}" for signal in score_signals)
            total += 1

    return {
        **selected,
        "linking_signals": _dedupe(linking_signals),
        "warnings": _dedupe(warnings),
        "total_links": total,
    }


def _link_types(record: dict[str, Any]) -> list[str]:
    provenance = str(record.get("provenance_type") or "unknown").casefold()
    text_class = str(record.get("text_class") or "unknown").casefold()
    if provenance in LOW_TRUST_PROVENANCE or text_class in LOW_TRUST_TEXT_CLASSES:
        return ["context_hint"]
    text = _normalized_record_text(record)
    types: list[str] = []
    for link_type in (
        "negative_or_contradicting",
        "validation",
        "quantification",
        "reactor",
        "process",
        "performance",
    ):
        if _has_signal(text, link_type):
            types.append(link_type)
    return types or ["context_hint"]


def _score_link_detailed(
    target: dict[str, Any], candidate: dict[str, Any], link_type: str
) -> tuple[float, list[str]]:
    if str(target.get("paper_id") or "") != str(candidate.get("paper_id") or ""):
        return float("-inf"), ["cross_paper_rejected"]
    score = 0.0
    signals = ["same_paper"]
    score += 10.0

    target_section = normalize_section_path(
        target.get("section_path") or target.get("section_heading") or target.get("source_section")
    )
    candidate_section = normalize_section_path(
        candidate.get("section_path") or candidate.get("section_heading") or candidate.get("source_section")
    )
    if target_section and target_section == candidate_section:
        score += 4.0
        signals.append("same_section")

    distance = abs(_span_order(candidate) - _span_order(target))
    distance_bonus = max(0.0, 4.0 - min(float(distance), 4.0))
    score += distance_bonus
    if distance <= 1:
        signals.append("adjacent_span")

    if _primary_admissible(candidate):
        score += 5.0
        signals.append("primary_admissible_provenance")
    else:
        score -= 2.0
        signals.append("context_only_provenance")

    if link_type in _link_types(candidate):
        score += 5.0
        signals.append(f"explicit_{link_type}_signal")

    target_family = str(target.get("reaction_family") or "unclear")
    candidate_family = str(candidate.get("reaction_family") or "unclear")
    if target_family not in {"", "unclear"} and candidate_family not in {"", "unclear"}:
        if target_family == candidate_family:
            score += 3.0
            signals.append("reaction_family_match")
        else:
            score -= 4.0
            signals.append("reaction_family_mismatch")
    if bool(candidate.get("reaction_family_conflict")):
        score -= 4.0
        signals.append("candidate_reaction_family_conflict")
    if link_type == "negative_or_contradicting":
        score += 2.0
        signals.append("negative_evidence_relation")
    return score, signals


def _linked_record(
    target: dict[str, Any],
    candidate: dict[str, Any],
    link_type: str,
    score: float,
    signals: list[str],
) -> dict[str, Any]:
    provenance = str(candidate.get("provenance_type") or "unknown")
    text_class = str(candidate.get("text_class") or "unknown")
    context_only = provenance.casefold() in LOW_TRUST_PROVENANCE or text_class.casefold() in LOW_TRUST_TEXT_CLASSES
    return {
        "span_id": _span_id(candidate),
        "stable_span_uid": str(candidate.get("stable_span_uid") or ""),
        "paper_id": str(candidate.get("paper_id") or ""),
        "span_order": candidate.get("span_order"),
        "section_path": candidate.get("section_path") or [],
        "section_heading": str(candidate.get("section_heading") or ""),
        "text_class": text_class,
        "provenance_type": provenance,
        "source_text": str(candidate.get("source_text") or candidate.get("text") or ""),
        "distance_from_target": _span_order(candidate) - _span_order(target),
        "relationship": f"linked_{link_type}",
        "link_type": link_type,
        "link_score": round(score, 3),
        "linking_signals": signals,
        "context_only": context_only,
        "primary_support": bool(_primary_admissible(candidate) and not context_only and link_type not in {"context_hint", "negative_or_contradicting"}),
    }


def _primary_admissible(record: dict[str, Any]) -> bool:
    provenance = str(record.get("provenance_type") or "unknown").casefold()
    text_class = str(record.get("text_class") or "unknown").casefold()
    if provenance in LOW_TRUST_PROVENANCE or text_class in LOW_TRUST_TEXT_CLASSES:
        return False
    if "is_primary_admissible" in record:
        return bool(record.get("is_primary_admissible"))
    return provenance in PRIMARY_PROVENANCE


def _normalized_record_text(record: dict[str, Any]) -> str:
    text = " ".join(
        str(record.get(key) or "")
        for key in ("source_text", "text", "claim_type", "admissibility_status", "detected_taxes", "overclaim_risk_flags")
    )
    return " ".join(text.casefold().split())


def _has_signal(text: str, link_type: str) -> bool:
    if link_type == "performance" and re.search(r"\bfe\b", text, flags=re.IGNORECASE):
        return True
    if link_type == "quantification" and re.search(r"\bic\b", text, flags=re.IGNORECASE):
        return True
    return any(signal in text for signal in SIGNALS[link_type])


def _span_id(record: dict[str, Any]) -> str:
    return str(record.get("legacy_span_id") or record.get("source_span_id") or record.get("span_id") or "").strip()


def _span_order(record: dict[str, Any]) -> int:
    value = record.get("span_order")
    try:
        return int(value)
    except (TypeError, ValueError):
        parsed = parse_legacy_span_order(_span_id(record))
        return parsed if parsed is not None else 10**9


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
