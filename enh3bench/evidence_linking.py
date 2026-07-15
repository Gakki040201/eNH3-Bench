"""Paper-scoped evidence linking with legacy and hierarchical profiles."""

from __future__ import annotations

import re
from typing import Any

from enh3bench.claim_typing import has_ammonia_quantification_signal
from enh3bench.reaction_profiles import normalize_reaction_family
from enh3bench.span_identity import normalize_section_path, parse_legacy_span_order


KEYWORD_LINKING_PROFILE = "keyword_linking_v1"
HIERARCHICAL_LINKING_PROFILE = "hierarchical_docling_v1"
ORDERED_SOURCE_PROFILE = "ordered_source_v1"
LINK_TYPES = (
    "performance", "validation", "quantification", "reactor", "process",
    "negative_or_contradicting", "context_hint",
)
POSITIVE_LINK_TYPES = {"performance", "validation", "quantification", "reactor", "process"}
DEFAULT_LINK_LIMITS = {
    "maximum_per_category": 2,
    "maximum_total_links": 12,
    "adjacent_before": 1,
    "adjacent_after": 1,
    "same_section_maximum": 4,
}
DEFAULT_MINIMUM_LINK_SCORE = 0.60
LINK_WEIGHTS = {
    "explicit_structured_field_match": 0.35,
    "explicit_category_phrase": 0.25,
    "same_or_adjacent_paragraph": 0.15,
    "same_section": 0.08,
    "primary_admissible_provenance": 0.10,
    "reaction_family_match": 0.07,
    "reaction_family_mismatch": -0.35,
    "reaction_family_conflict": -0.25,
    "context_only_provenance": -0.30,
    "generic_keyword_only": -0.25,
}

SIGNALS = {
    "performance": (
        "faradaic efficiency", "nh3 yield", "ammonia yield", "current density", "runtime",
    ),
    "validation": (
        "15n", "isotope", "ar blank", "argon blank", "n2-free", "nox screening",
        "nox control", "nitrate/nitrite impurity", "contamination control", "impurity screening",
    ),
    "quantification": (
        "ion chromatography", "nmr", "uv-vis", "uv vis", "colorimetric",
        "ammonia calibration", "nh3 calibration", "ammonia quantification",
    ),
    "reactor": (
        "flow cell", "gde", "gas diffusion electrode", "mea", "ssc", "active area",
        "flow rate", "outlet", "wetting", "flooding",
    ),
    "process": (
        "capture", "separation", "solvent inventory", "electrolyte recycle", "replacement",
        "hydrogen source", "auxiliary load", "energy boundary",
    ),
    "negative_or_contradicting": (
        "false positive", "extraneous ammonia", "reassignment", "negative evidence",
        "background ammonia", "ammonia contamination",
    ),
}
LEGACY_SIGNALS = {
    "performance": (
        "faradaic efficiency", "nh3 yield", "ammonia yield", "current density", "potential",
        "voltage", "runtime", "stability",
    ),
    "validation": (
        "15n", "isotope", "ar blank", "argon blank", "n2-free", "nox screening",
        "nitrate/nitrite impurity", "contamination control",
    ),
    "quantification": (
        "ion chromatography", "nmr", "uv-vis", "uv vis", "colorimetric", "calibration",
        "ammonia quantification",
    ),
    "reactor": (
        "flow cell", "gde", "gas diffusion electrode", "mea", "ssc", "active area",
        "flow rate", "outlet", "wetting", "flooding", "stability",
    ),
    "process": (
        "capture", "separation", "solvent inventory", "electrolyte recycle", "replacement",
        "hydrogen source", "hor", "auxiliary load", "energy boundary",
    ),
    "negative_or_contradicting": (
        "false positive", "contamination", "extraneous ammonia", "reassignment", "negative evidence",
        "background ammonia",
    ),
}
GENERIC_TERMS = {
    "ammonia", "nitrogen", "electrochemical", "potential", "voltage", "stability", "reactor",
    "background", "contamination", "nitrate", "nitrite", "lithium", "li salt",
}
STRUCTURED_FIELDS = {
    "performance": ("faradaic_efficiency_percent", "FE_percent", "nh3_yield_value", "current_density"),
    "validation": ("validation_gates", "isotope_label", "blank_control", "contamination_control"),
    "quantification": ("quantification_method", "calibration_method", "ammonia_quantification"),
    "reactor": ("reactor_type", "active_area", "flow_rate", "outlet_condition"),
    "process": ("process_boundary", "separation_method", "electrolyte_recycle", "auxiliary_load"),
    "negative_or_contradicting": ("negative_evidence", "contradiction_type", "reassignment"),
}
LOW_TRUST_PROVENANCE = {"reference", "bibliography", "figure_caption", "scheme_caption", "review_table"}
LOW_TRUST_TEXT_CLASSES = {"reference_list", "figure_caption", "scheme_caption", "review_table", "background_context"}
PRIMARY_PROVENANCE = {"body", "methods", "results", "discussion", "supplementary"}


def classify_link_type(record: dict[str, Any]) -> str:
    roles = _link_types(record)
    return roles[0] if roles else "context_hint"


def score_link(target: dict[str, Any], candidate: dict[str, Any]) -> float:
    """Return a normalized hierarchical score in [0, 1]."""

    if str(target.get("paper_id") or "") != str(candidate.get("paper_id") or ""):
        return float("-inf")
    roles = _link_types(candidate)
    role = next((item for item in roles if item != "context_hint"), "context_hint")
    return _score_link_detailed(target, candidate, role)[0]


def link_supporting_evidence(
    target: dict[str, Any],
    paper_records: list[dict[str, Any]],
    limits: dict[str, int] | None = None,
    *,
    profile: str = KEYWORD_LINKING_PROFILE,
    minimum_link_score: float = DEFAULT_MINIMUM_LINK_SCORE,
) -> dict[str, Any]:
    if profile == KEYWORD_LINKING_PROFILE:
        return _legacy_keyword_links(target, paper_records, limits)
    if profile not in {HIERARCHICAL_LINKING_PROFILE, ORDERED_SOURCE_PROFILE}:
        raise ValueError(f"unknown context linking profile: {profile}")
    ordered_source = profile == ORDERED_SOURCE_PROFILE
    if ordered_source and not _has_source_coordinates(target):
        raise ValueError(f"ordered source target lacks source coordinates: {_span_id(target)}")
    settings = dict(DEFAULT_LINK_LIMITS)
    if limits:
        settings.update({key: int(value) for key, value in limits.items() if key in settings})
    threshold = max(0.0, min(1.0, float(minimum_link_score)))
    target_id = _span_id(target)
    target_paper = str(target.get("paper_id") or "")
    eligible: dict[str, list[tuple[float, dict[str, Any], list[str]]]] = {role: [] for role in LINK_TYPES}
    diagnostics = {
        "candidate_link_count": 0,
        "accepted_link_count": 0,
        "links_below_threshold": 0,
        "family_mismatch_rejected_count": 0,
        "low_trust_rejected_count": 0,
        "self_link_count": 0,
        "self_candidate_rejected_count": 0,
        "cross_paper_link_count": 0,
    }
    warnings: list[str] = []
    for candidate in paper_records:
        candidate_id = _span_id(candidate)
        if not candidate_id:
            continue
        if candidate_id == target_id:
            diagnostics["self_candidate_rejected_count"] += 1
            continue
        if str(candidate.get("paper_id") or "") != target_paper:
            diagnostics["cross_paper_link_count"] += 1
            warnings.append(f"cross_paper_candidate_rejected:{candidate_id}")
            continue
        if ordered_source and not _has_source_coordinates(candidate):
            warnings.append(f"source_coordinates_missing:{candidate_id}")
            continue
        roles = _link_types(candidate)
        for role in roles:
            diagnostics["candidate_link_count"] += 1
            score, signals = _score_link_detailed(target, candidate, role, ordered_source=ordered_source)
            if role in POSITIVE_LINK_TYPES and _is_context_only(candidate):
                diagnostics["low_trust_rejected_count"] += 1
                continue
            if "reaction_family_mismatch" in signals and normalize_reaction_family(
                str(target.get("reaction_family") or "unclear")
            ) not in {"unclear", "mixed"}:
                diagnostics["family_mismatch_rejected_count"] += 1
                continue
            if role != "context_hint" and not _has_strong_signal(signals):
                diagnostics["links_below_threshold"] += 1
                continue
            if score < threshold:
                diagnostics["links_below_threshold"] += 1
                continue
            eligible[role].append((score, candidate, signals))

    role_selected: dict[str, list[tuple[float, dict[str, Any], list[str]]]] = {}
    per_category = max(0, settings["maximum_per_category"])
    for role, candidates in eligible.items():
        limit = min(per_category, 2) if role == "context_hint" else per_category
        role_selected[role] = sorted(candidates, key=_rank_key(target))[:limit]

    by_span: dict[str, dict[str, Any]] = {}
    for role in LINK_TYPES:
        for score, candidate, signals in role_selected[role]:
            span_id = _span_id(candidate)
            item = by_span.setdefault(span_id, {"candidate": candidate, "roles": [], "scores": [], "signals": []})
            item["roles"].append(role)
            item["scores"].append(score)
            item["signals"].extend(signals)
    ranked_unique = sorted(
        by_span.items(),
        key=lambda pair: (-max(pair[1]["scores"]), abs(_span_order(pair[1]["candidate"]) - _span_order(target)), pair[0]),
    )[:max(0, settings["maximum_total_links"])]
    allowed_ids = {span_id for span_id, _item in ranked_unique}
    selected: dict[str, list[dict[str, Any]]] = {role: [] for role in LINK_TYPES}
    for span_id, item in ranked_unique:
        for role in LINK_TYPES:
            if role not in item["roles"]:
                continue
            role_position = item["roles"].index(role)
            selected[role].append(_linked_record(
                target, item["candidate"], role, item["scores"][role_position], item["signals"]
            ))
    diagnostics["accepted_link_count"] = sum(len(records) for records in selected.values())
    linking_signals = [
        f"{span_id}:{signal}" for span_id, item in ranked_unique for signal in _dedupe(item["signals"])
    ]
    return {
        **selected,
        "linking_signals": _dedupe(linking_signals),
        "warnings": _dedupe(warnings),
        "total_links": len(allowed_ids),
        "diagnostics": diagnostics,
    }


def _score_link_detailed(
    target: dict[str, Any], candidate: dict[str, Any], link_type: str, *, ordered_source: bool = False
) -> tuple[float, list[str]]:
    if str(target.get("paper_id") or "") != str(candidate.get("paper_id") or ""):
        return float("-inf"), ["cross_paper_rejected"]
    score = 0.0
    signals: list[str] = ["same_paper"]
    if _structured_match(candidate, link_type):
        score += LINK_WEIGHTS["explicit_structured_field_match"]
        signals.append("explicit_structured_field_match")
    text = _normalized_record_text(candidate)
    explicit_phrase = link_type == "context_hint" or _has_signal(text, link_type)
    if explicit_phrase and link_type != "context_hint":
        score += LINK_WEIGHTS["explicit_category_phrase"]
        signals.append(f"explicit_{link_type}_phrase")
    adjacent_source = _same_or_adjacent_paragraph(target, candidate, ordered_source=ordered_source)
    if adjacent_source:
        score += LINK_WEIGHTS["same_or_adjacent_paragraph"]
        signals.append("same_or_adjacent_paragraph")
    target_section = normalize_section_path(target.get("section_path") or target.get("section_heading") or target.get("source_section"))
    candidate_section = normalize_section_path(candidate.get("section_path") or candidate.get("section_heading") or candidate.get("source_section"))
    same_source_section = bool(
        (target_section and target_section == candidate_section)
        or (ordered_source and target.get("section_uid") and target.get("section_uid") == candidate.get("section_uid"))
    )
    if same_source_section:
        score += LINK_WEIGHTS["same_section"]
        signals.append("same_section")
    if _primary_admissible(candidate):
        score += LINK_WEIGHTS["primary_admissible_provenance"]
        signals.append("primary_admissible_provenance")
    else:
        score += LINK_WEIGHTS["context_only_provenance"]
        signals.append("context_only_provenance")
    target_family = normalize_reaction_family(str(target.get("reaction_family") or "unclear"))
    candidate_family = normalize_reaction_family(str(candidate.get("reaction_family") or "unclear"))
    if target_family not in {"unclear", "mixed"} and candidate_family not in {"unclear", "mixed"}:
        if target_family == candidate_family:
            score += LINK_WEIGHTS["reaction_family_match"]
            signals.append("reaction_family_match")
        else:
            score += LINK_WEIGHTS["reaction_family_mismatch"]
            signals.append("reaction_family_mismatch")
    if bool(candidate.get("reaction_family_conflict")):
        score += LINK_WEIGHTS["reaction_family_conflict"]
        signals.append("reaction_family_conflict")
    if _explicit_relation(candidate, link_type):
        signals.append("explicit_relation")
    if link_type == "negative_or_contradicting" and _negative_strong_signal(text):
        signals.append("negative_ammonia_false_positive_relation")
    if explicit_phrase and not _specific_phrase(text, link_type) and not _structured_match(candidate, link_type):
        score += LINK_WEIGHTS["generic_keyword_only"]
        signals.append("generic_keyword_only")
    if link_type == "context_hint" and _is_context_only(candidate):
        if adjacent_source:
            score = max(score, 0.65)
            signals.append("adjacent_context_hint_provenance")
        elif same_source_section:
            score = max(score, 0.60)
            signals.append("same_section_context_hint_provenance")
    return round(max(0.0, min(1.0, score)), 4), _dedupe(signals)


def _legacy_keyword_links(
    target: dict[str, Any], paper_records: list[dict[str, Any]], limits: dict[str, int] | None
) -> dict[str, Any]:
    settings = dict(DEFAULT_LINK_LIMITS)
    if limits:
        settings.update({key: int(value) for key, value in limits.items() if key in settings})
    target_id = _span_id(target)
    target_paper = str(target.get("paper_id") or "")
    candidates: dict[str, list[tuple[float, dict[str, Any], list[str]]]] = {role: [] for role in LINK_TYPES}
    warnings: list[str] = []
    for candidate in paper_records:
        candidate_id = _span_id(candidate)
        if not candidate_id or candidate_id == target_id:
            continue
        if str(candidate.get("paper_id") or "") != target_paper:
            warnings.append(f"cross_paper_candidate_rejected:{candidate_id}")
            continue
        for role in _legacy_link_types(candidate):
            score, signals = _legacy_raw_score(target, candidate, role)
            candidates[role].append((score, candidate, signals))
    selected: dict[str, list[dict[str, Any]]] = {role: [] for role in LINK_TYPES}
    total = 0
    for role in LINK_TYPES:
        for score, candidate, signals in sorted(candidates[role], key=_rank_key(target))[:max(0, settings["maximum_per_category"])]:
            if total >= max(0, settings["maximum_total_links"]):
                break
            selected[role].append(_linked_record(target, candidate, role, score, signals))
            total += 1
    return {
        **selected,
        "linking_signals": _dedupe(
            [f"{item['span_id']}:{signal}" for records in selected.values() for item in records for signal in item["linking_signals"]]
        ),
        "warnings": _dedupe(warnings),
        "total_links": total,
        "diagnostics": {
            "candidate_link_count": sum(len(items) for items in candidates.values()),
            "accepted_link_count": total,
            "links_below_threshold": 0,
            "family_mismatch_rejected_count": 0,
            "low_trust_rejected_count": 0,
            "self_link_count": 0,
            "self_candidate_rejected_count": 0,
            "cross_paper_link_count": len(warnings),
        },
    }


def _legacy_raw_score(target: dict[str, Any], candidate: dict[str, Any], role: str) -> tuple[float, list[str]]:
    score = 10.0
    signals = ["same_paper"]
    target_section = normalize_section_path(target.get("section_path") or target.get("section_heading") or target.get("source_section"))
    candidate_section = normalize_section_path(candidate.get("section_path") or candidate.get("section_heading") or candidate.get("source_section"))
    if target_section and target_section == candidate_section:
        score += 4.0; signals.append("same_section")
    distance = abs(_span_order(candidate) - _span_order(target))
    score += max(0.0, 4.0 - min(float(distance), 4.0))
    if distance <= 1: signals.append("adjacent_span")
    if _primary_admissible(candidate):
        score += 5.0; signals.append("primary_admissible_provenance")
    else:
        score -= 2.0; signals.append("context_only_provenance")
    if role in _legacy_link_types(candidate):
        score += 5.0; signals.append(f"explicit_{role}_signal")
    target_family = str(target.get("reaction_family") or "unclear")
    candidate_family = str(candidate.get("reaction_family") or "unclear")
    if target_family not in {"", "unclear"} and candidate_family not in {"", "unclear"}:
        if target_family == candidate_family:
            score += 3.0; signals.append("reaction_family_match")
        else:
            score -= 4.0; signals.append("reaction_family_mismatch")
    if bool(candidate.get("reaction_family_conflict")):
        score -= 4.0; signals.append("candidate_reaction_family_conflict")
    if role == "negative_or_contradicting":
        score += 2.0; signals.append("negative_evidence_relation")
    return score, signals


def _legacy_link_types(record: dict[str, Any]) -> list[str]:
    if _is_context_only(record):
        return ["context_hint"]
    text = _normalized_record_text(record)
    roles = []
    for role in ("negative_or_contradicting", "validation", "quantification", "reactor", "process", "performance"):
        if _legacy_has_signal(text, role):
            roles.append(role)
    return roles or ["context_hint"]


def _legacy_has_signal(text: str, role: str) -> bool:
    if role == "performance" and re.search(r"\bfe\b", text): return True
    if role == "quantification" and has_ammonia_quantification_signal(text): return True
    return any(signal in text for signal in LEGACY_SIGNALS[role])


def _link_types(record: dict[str, Any]) -> list[str]:
    if _is_context_only(record):
        return ["context_hint"]
    text = _normalized_record_text(record)
    return [role for role in LINK_TYPES[:-1] if _has_signal(text, role) or _structured_match(record, role)]


def _linked_record(
    target: dict[str, Any], candidate: dict[str, Any], link_type: str, score: float, signals: list[str]
) -> dict[str, Any]:
    context_only = _is_context_only(candidate) or link_type == "context_hint"
    paragraph_distance = _paragraph_distance(target, candidate)
    target_start = _source_start(target)
    candidate_start = _source_start(candidate)
    direction = "same" if candidate_start == target_start else ("before" if candidate_start < target_start else "after")
    return {
        "span_id": _span_id(candidate),
        "stable_span_uid": str(candidate.get("stable_span_uid") or ""),
        "paper_id": str(candidate.get("paper_id") or ""),
        "document_id": str(candidate.get("document_id") or ""),
        "source_start_offset": candidate.get("source_start_offset"),
        "source_end_offset": candidate.get("source_end_offset"),
        "verified_source_start_offset": candidate.get("verified_source_start_offset"),
        "verified_source_end_offset": candidate.get("verified_source_end_offset"),
        "source_locator": candidate.get("source_locator"),
        "source_order_key": candidate.get("source_order_key"),
        "paragraph_uid": candidate.get("paragraph_uid"),
        "paragraph_global_index": candidate.get("paragraph_global_index"),
        "paragraph_index_in_section": candidate.get("paragraph_index_in_section"),
        "section_uid": candidate.get("section_uid"),
        "section_outline_label": candidate.get("section_outline_label"),
        "span_order": candidate.get("span_order"),
        "section_path": candidate.get("section_path") or [],
        "section_heading": str(candidate.get("section_heading") or ""),
        "text_class": str(candidate.get("text_class") or "unknown"),
        "provenance_type": str(candidate.get("provenance_type") or "unknown"),
        "reaction_family": str(candidate.get("reaction_family") or "unclear"),
        "source_text": str(candidate.get("source_text") or candidate.get("text") or ""),
        "distance_from_target": _span_order(candidate) - _span_order(target),
        "relationship": f"linked_{link_type}",
        "link_type": link_type,
        "normalized_link_score": round(max(0.0, min(1.0, score)), 4),
        "link_score": round(score, 4),
        "linking_signals": _dedupe(signals),
        "context_only": context_only,
        "primary_support": bool(_primary_admissible(candidate) and not context_only and link_type in POSITIVE_LINK_TYPES),
        "source_paragraph_distance": paragraph_distance,
        "same_source_section": bool(target.get("section_uid") and target.get("section_uid") == candidate.get("section_uid")),
        "same_parent_section": bool(target.get("parent_section_uid") and target.get("parent_section_uid") == candidate.get("parent_section_uid")),
        "source_direction": direction,
    }


def _has_strong_signal(signals: list[str]) -> bool:
    return any(
        signal in {"explicit_structured_field_match", "explicit_relation", "negative_ammonia_false_positive_relation"}
        or (signal == "same_or_adjacent_paragraph" and any(item.startswith("explicit_") and item.endswith("_phrase") for item in signals))
        or (signal.startswith("explicit_validation_") or signal.startswith("explicit_quantification_"))
        for signal in signals
    )


def _structured_match(record: dict[str, Any], role: str) -> bool:
    return any(record.get(field) not in (None, "", [], {}) for field in STRUCTURED_FIELDS.get(role, ()))


def _explicit_relation(record: dict[str, Any], role: str) -> bool:
    relation = str(record.get("link_relation") or record.get("evidence_relation") or "").casefold()
    return bool(relation and (role.replace("_or_contradicting", "") in relation or relation in {"supports", "contradicts"}))


def _same_or_adjacent_paragraph(
    target: dict[str, Any], candidate: dict[str, Any], *, ordered_source: bool = False
) -> bool:
    target_paragraph = target.get("paragraph_global_index")
    candidate_paragraph = candidate.get("paragraph_global_index")
    if target_paragraph is None or candidate_paragraph is None:
        target_paragraph = target.get("paragraph_order")
        candidate_paragraph = candidate.get("paragraph_order")
    if target_paragraph is not None and candidate_paragraph is not None:
        try:
            return abs(int(target_paragraph) - int(candidate_paragraph)) <= 1
        except (TypeError, ValueError):
            pass
    if ordered_source:
        return False
    return abs(_span_order(candidate) - _span_order(target)) <= 1


def _has_source_coordinates(record: dict[str, Any]) -> bool:
    return all(record.get(field) not in (None, "") for field in (
        "paragraph_uid", "paragraph_global_index", "section_uid", "source_order_key"
    ))


def _paragraph_distance(target: dict[str, Any], candidate: dict[str, Any]) -> int | None:
    try:
        return int(candidate.get("paragraph_global_index")) - int(target.get("paragraph_global_index"))
    except (TypeError, ValueError):
        return None


def _source_start(record: dict[str, Any]) -> int:
    for field in ("verified_source_start_offset", "source_start_offset"):
        try:
            return int(record.get(field))
        except (TypeError, ValueError):
            continue
    return 10**18


def _specific_phrase(text: str, role: str) -> bool:
    return any(phrase in text for phrase in SIGNALS.get(role, ()) if phrase not in GENERIC_TERMS)


def _negative_strong_signal(text: str) -> bool:
    return any(phrase in text for phrase in ("false positive", "extraneous ammonia", "background ammonia", "ammonia contamination", "negative evidence"))


def _primary_admissible(record: dict[str, Any]) -> bool:
    if _is_context_only(record):
        return False
    if "is_primary_admissible" in record:
        return bool(record.get("is_primary_admissible"))
    return str(record.get("provenance_type") or "unknown").casefold() in PRIMARY_PROVENANCE


def _is_context_only(record: dict[str, Any]) -> bool:
    provenance = str(record.get("provenance_type") or "unknown").casefold()
    text_class = str(record.get("text_class") or "unknown").casefold()
    return provenance in LOW_TRUST_PROVENANCE or text_class in LOW_TRUST_TEXT_CLASSES


def _normalized_record_text(record: dict[str, Any]) -> str:
    text = " ".join(str(record.get(key) or "") for key in (
        "source_text", "text", "claim_type", "admissibility_status", "detected_taxes", "overclaim_risk_flags"
    ))
    return " ".join(text.casefold().split())


def _has_signal(text: str, role: str) -> bool:
    if role == "performance" and re.search(r"\bfe\s*(?:=|of|was|:)?\s*\d", text):
        return True
    if role == "quantification" and has_ammonia_quantification_signal(text):
        return True
    return any(signal in text for signal in SIGNALS.get(role, ()))


def _rank_key(target: dict[str, Any]):
    return lambda item: (-item[0], abs(_span_order(item[1]) - _span_order(target)), _span_id(item[1]))


def _span_id(record: dict[str, Any]) -> str:
    return str(record.get("legacy_span_id") or record.get("source_span_id") or record.get("span_id") or "").strip()


def _span_order(record: dict[str, Any]) -> int:
    try:
        return int(record.get("span_order"))
    except (TypeError, ValueError):
        parsed = parse_legacy_span_order(_span_id(record))
        return parsed if parsed is not None else 10**9


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
