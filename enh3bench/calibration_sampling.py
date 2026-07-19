"""Deterministic sampling for v0.16 human semantic calibration."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from typing import Any

from enh3bench.calibration_schema import CALIBRATION_SCHEMA_VERSION


SPAN_STRATUM_QUOTAS = {
    "primary_performance": 50,
    "quantification": 40,
    "validation": 40,
    "reactor_process": 25,
    "external_cited_claim": 30,
    "review_perspective": 20,
    "off_target": 20,
    "trap_only": 20,
    "unclear_mixed_family": 35,
    "structured_text_conflict": 20,
}
SPAN_STRATUM_PRIORITY = tuple(SPAN_STRATUM_QUOTAS)
HIGH_RISK_RESERVOIR = "high_risk_reservoir"


def sampling_hash(seed: int, underlying_id: str) -> str:
    payload = f"{int(seed)}\n{CALIBRATION_SCHEMA_VERSION}\n{str(underlying_id)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def matching_span_strata(record: dict[str, Any]) -> list[str]:
    """Return every field-grounded matching stratum in documented priority order."""

    matches: list[str] = []
    claim_type = str(record.get("semantic_claim_type") or "")
    ownership = str(record.get("claim_ownership") or "")
    genre = str(record.get("document_genre") or "")
    family = str(record.get("effective_reaction_family") or "")
    document_family = str(record.get("document_reaction_family") or "")
    gates = record.get("validation_gate_decisions") or {}

    if bool(record.get("primary_semantic_eligibility")) and claim_type == "performance_result_claim":
        matches.append("primary_performance")
    if bool(record.get("ammonia_quantification_signal")) or claim_type == "ammonia_quantification_claim":
        matches.append("quantification")
    if claim_type == "validation_claim" or any(
        bool((decision or {}).get("satisfied")) for decision in gates.values() if isinstance(decision, dict)
    ):
        matches.append("validation")
    if claim_type in {"reactor_claim", "process_claim"}:
        matches.append("reactor_process")
    if ownership in {"external_or_cited_authors", "general_literature"}:
        matches.append("external_cited_claim")
    if genre in {"review", "perspective"}:
        matches.append("review_perspective")
    if family in {"LiNRR", "NO2RR", "NO3RR", "NORR"}:
        matches.append("off_target")
    if bool(record.get("gas_purification_trap_signal")) and not bool(record.get("ammonia_quantification_signal")):
        matches.append("trap_only")
    if family in {"unclear", "mixed"} or document_family in {"unclear", "mixed"}:
        matches.append("unclear_mixed_family")
    if any(bool(record.get(field)) for field in (
        "structured_gate_text_conflict", "semantic_claim_type_conflict", "document_reaction_family_conflict"
    )):
        matches.append("structured_text_conflict")
    return matches


def assign_primary_span_stratum(record: dict[str, Any]) -> tuple[str, list[str]]:
    matches = matching_span_strata(record)
    primary = next((name for name in SPAN_STRATUM_PRIORITY if name in matches), HIGH_RISK_RESERVOIR)
    return primary, matches


def sample_spans(
    records: list[dict[str, Any]], sample_size: int, seed: int
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    """Sample unique semantic spans by fixed quotas, then fill from a risk-ranked reservoir."""

    if len(records) < sample_size:
        raise ValueError(f"insufficient semantic spans: requested {sample_size}, available {len(records)}")
    prepared: list[dict[str, Any]] = []
    for record in records:
        primary, matches = assign_primary_span_stratum(record)
        item = dict(record)
        item["assigned_primary_stratum"] = primary
        item["all_matching_strata"] = matches
        item["sampling_hash"] = sampling_hash(seed, str(record.get("cleanroom_span_id") or ""))
        prepared.append(item)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in prepared:
        groups[str(item["assigned_primary_stratum"])].append(item)
    for values in groups.values():
        values.sort(key=lambda item: (item["sampling_hash"], str(item["cleanroom_span_id"])))

    quotas = _effective_span_quotas(sample_size)
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    coverage: dict[str, dict[str, int]] = {}
    for stratum, quota in quotas.items():
        available = groups.get(stratum, [])
        chosen = available[: min(quota, len(available))]
        for rank, item in enumerate(available, 1):
            item["sampling_rank"] = rank
        for item in chosen:
            item["selection_stratum"] = stratum
        selected.extend(chosen)
        selected_ids.update(str(item["cleanroom_span_id"]) for item in chosen)
        coverage[stratum] = {
            "requested": quota,
            "available": len(available),
            "selected": len(chosen),
            "shortage": max(0, quota - len(chosen)),
        }

    missing = sample_size - len(selected)
    if missing < 0:
        raise ValueError(f"span quotas exceed requested sample size: quotas={len(selected)}, requested={sample_size}")
    reservoir = [item for item in prepared if str(item["cleanroom_span_id"]) not in selected_ids]
    reservoir.sort(key=lambda item: (-_risk_score(item), item["sampling_hash"], str(item["cleanroom_span_id"])))
    if len(reservoir) < missing:
        raise ValueError(f"insufficient unique span reservoir: needed {missing}, available {len(reservoir)}")
    fill = reservoir[:missing]
    for rank, item in enumerate(reservoir, 1):
        if "sampling_rank" not in item:
            item["sampling_rank"] = rank
        if item in fill:
            item["quota_fill_source_stratum"] = str(item["assigned_primary_stratum"])
            item["selection_stratum"] = HIGH_RISK_RESERVOIR
    selected.extend(fill)
    coverage[HIGH_RISK_RESERVOIR] = {
        "requested": missing,
        "available": len(reservoir),
        "selected": len(fill),
        "shortage": max(0, missing - len(fill)),
    }
    selected.sort(key=lambda item: (SPAN_STRATUM_PRIORITY.index(item["selection_stratum"])
                                     if item["selection_stratum"] in SPAN_STRATUM_PRIORITY
                                     else len(SPAN_STRATUM_PRIORITY),
                                     int(item["sampling_rank"]), item["sampling_hash"]))
    if len(selected) != sample_size or len({item["cleanroom_span_id"] for item in selected}) != sample_size:
        raise AssertionError("span sampling did not produce the requested unique count")
    return selected, coverage


def _effective_span_quotas(sample_size: int) -> dict[str, int]:
    """Preserve the published 300-item quotas and scale smaller fixture runs deterministically."""

    quota_total = sum(SPAN_STRATUM_QUOTAS.values())
    if sample_size >= quota_total:
        return dict(SPAN_STRATUM_QUOTAS)
    exact = {name: quota * sample_size / quota_total for name, quota in SPAN_STRATUM_QUOTAS.items()}
    quotas = {name: int(value) for name, value in exact.items()}
    remainder = sample_size - sum(quotas.values())
    order = sorted(SPAN_STRATUM_PRIORITY, key=lambda name: (-(exact[name] - quotas[name]), SPAN_STRATUM_PRIORITY.index(name)))
    for name in order[:remainder]:
        quotas[name] += 1
    return quotas


def _risk_score(record: dict[str, Any]) -> int:
    return sum((
        6 * bool(record.get("needs_review")),
        5 * bool(record.get("hard_gate_failures")),
        4 * bool(record.get("structured_gate_text_conflict")),
        4 * bool(record.get("semantic_claim_type_conflict")),
        3 * (str(record.get("effective_reaction_family") or "") in {"unclear", "mixed"}),
        3 * (str(record.get("claim_ownership") or "") == "unclear"),
        2 * bool(record.get("document_reaction_family_conflict")),
        len(record.get("needs_review_reasons") or []),
    ))


def sample_papers(
    papers: list[dict[str, Any]], semantics: list[dict[str, Any]], sample_size: int, seed: int
) -> list[dict[str, Any]]:
    """Rare-first coverage followed by stable round-robin across observed combinations."""

    if len(papers) < sample_size:
        raise ValueError(f"insufficient papers: requested {sample_size}, available {len(papers)}")
    semantics_by_paper: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for span in semantics:
        semantics_by_paper[str(span.get("paper_id") or "")].append(span)

    prepared: list[dict[str, Any]] = []
    for paper in papers:
        item = dict(paper)
        paper_id = str(item.get("paper_id") or "")
        coverage_stratum = "|".join(str(item.get(field) or "<missing>") for field in (
            "document_reaction_family", "document_genre", "paper_admissibility_status"
        ))
        spans = semantics_by_paper.get(paper_id, [])
        needs_review_count = sum(bool(span.get("needs_review")) for span in spans)
        evidence_flags = {
            "V": any(span.get("semantic_claim_type") == "validation_claim" for span in spans),
            "Q": any(bool(span.get("ammonia_quantification_signal")) for span in spans),
            "P": any(bool(span.get("performance_result_evidence")) for span in spans),
            "R": any(span.get("semantic_claim_type") in {"reactor_claim", "process_claim"} for span in spans),
        }
        primary_band = "primary_zero" if int(item.get("primary_eligible_span_count") or 0) == 0 else "has_primary"
        review_band = "review_zero" if needs_review_count == 0 else "review_low" if needs_review_count <= 10 else "review_high"
        evidence_labels = "".join(key for key, present in evidence_flags.items() if present)
        evidence_band = f"evidence_{evidence_labels}" if evidence_labels else "evidence_none"
        stratum = "|".join((coverage_stratum, primary_band, review_band, evidence_band))
        item.update({
            "assigned_sampling_stratum": stratum,
            "coverage_sampling_stratum": coverage_stratum,
            "sampling_hash": sampling_hash(seed, paper_id),
            "needs_review_count": needs_review_count,
            "has_validation_evidence": evidence_flags["V"],
            "has_quantification_evidence": evidence_flags["Q"],
            "has_performance_evidence": evidence_flags["P"],
            "has_reactor_process_evidence": evidence_flags["R"],
        })
        prepared.append(item)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in prepared:
        groups[item["assigned_sampling_stratum"]].append(item)
    for values in groups.values():
        values.sort(key=lambda item: (item["sampling_hash"], str(item["paper_id"])))
        for rank, item in enumerate(values, 1):
            item["sampling_rank"] = rank
    order = sorted(groups, key=lambda key: (len(groups[key]), key))
    coverage_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in prepared:
        coverage_groups[item["coverage_sampling_stratum"]].append(item)
    for values in coverage_groups.values():
        values.sort(key=lambda item: (item["sampling_hash"], str(item["paper_id"])))

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()

    def add(item: dict[str, Any]) -> None:
        paper_id = str(item["paper_id"])
        if paper_id not in selected_ids and len(selected) < sample_size:
            selected.append(item)
            selected_ids.add(paper_id)

    # Explicit family coverage is independent of enum assumptions: values are discovered at runtime.
    for family in sorted({str(item.get("document_reaction_family") or "<missing>") for item in prepared}):
        candidates = [item for item in prepared if str(item.get("document_reaction_family") or "<missing>") == family]
        candidates.sort(key=lambda item: (len(groups[item["assigned_sampling_stratum"]]), item["sampling_hash"]))
        add(candidates[0])
    for key in sorted(coverage_groups, key=lambda value: (len(coverage_groups[value]), value)):
        add(coverage_groups[key][0])
    for key in order:
        add(groups[key][0])
    depth = 1
    while len(selected) < sample_size:
        changed = False
        for key in order:
            if depth < len(groups[key]):
                before = len(selected)
                add(groups[key][depth])
                changed |= len(selected) > before
                if len(selected) == sample_size:
                    break
        if not changed:
            break
        depth += 1
    if len(selected) != sample_size:
        raise ValueError(f"paper sampling failed closed: selected {len(selected)} of {sample_size}")
    return selected


def sample_links(
    links: list[dict[str, Any]], semantics: list[dict[str, Any]], sample_size: int, seed: int
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Validate endpoints and sample rare composite link strata deterministically."""

    spans = {str(item.get("cleanroom_span_id") or ""): item for item in semantics}
    seen_pairs: set[tuple[str, str]] = set()
    valid: list[dict[str, Any]] = []
    invalid_count = 0
    for link in links:
        target_id = str(link.get("target_cleanroom_span_id") or "")
        evidence_id = str(link.get("evidence_cleanroom_span_id") or "")
        target = spans.get(target_id)
        evidence = spans.get(evidence_id)
        pair = (target_id, evidence_id)
        if (
            target is None or evidence is None or target_id == evidence_id or pair in seen_pairs
            or str(target.get("paper_id") or "") != str(evidence.get("paper_id") or "")
            or str(link.get("paper_id") or "") != str(target.get("paper_id") or "")
        ):
            invalid_count += 1
            continue
        seen_pairs.add(pair)
        item = dict(link)
        distance = abs(int(target.get("source_start_offset") or 0) - int(evidence.get("source_start_offset") or 0))
        distance_band = "same_node" if target.get("source_node_id") == evidence.get("source_node_id") else "near" if distance <= 2000 else "mid" if distance <= 6000 else "far"
        roles = sorted(str(role) for role in (link.get("link_roles") or []))
        primary_role = roles[0] if roles else "untyped"
        needs_review = bool(target.get("needs_review")) or bool(evidence.get("needs_review"))
        stratum = "|".join((
            primary_role,
            str(target.get("semantic_claim_type") or "untyped"),
            str(evidence.get("semantic_claim_type") or "untyped"),
            "target_primary" if target.get("primary_semantic_eligibility") else "target_nonprimary",
            str(link.get("source_eligibility") or "unknown"),
            str(evidence.get("provenance_type") or "unknown_provenance"),
            distance_band,
            "needs_review" if needs_review else "no_review_flag",
        ))
        item.update({
            "assigned_sampling_stratum": stratum,
            "sampling_hash": sampling_hash(seed, str(link.get("evidence_link_id") or "")),
            "link_role": primary_role,
            "target_claim_type": target.get("semantic_claim_type"),
            "evidence_claim_type": evidence.get("semantic_claim_type"),
            "target_primary_eligibility": bool(target.get("primary_semantic_eligibility")),
            "evidence_provenance": evidence.get("provenance_type"),
            "source_distance": distance,
            "source_distance_band": distance_band,
            "needs_review": needs_review,
        })
        valid.append(item)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in valid:
        groups[item["assigned_sampling_stratum"]].append(item)
    for values in groups.values():
        values.sort(key=lambda item: (item["sampling_hash"], str(item["evidence_link_id"])))
        for rank, item in enumerate(values, 1):
            item["sampling_rank"] = rank
    order = sorted(groups, key=lambda key: (len(groups[key]), key))
    selected: list[dict[str, Any]] = []
    depth = 0
    target_count = min(sample_size, len(valid))
    while len(selected) < target_count:
        changed = False
        for key in order:
            if depth < len(groups[key]):
                selected.append(groups[key][depth])
                changed = True
                if len(selected) == target_count:
                    break
        if not changed:
            break
        depth += 1
    return selected, {
        "requested": sample_size,
        "available": len(valid),
        "selected": len(selected),
        "shortage": max(0, sample_size - len(selected)),
        "invalid": invalid_count,
        "strata": len(groups),
    }


def distribution(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(item.get(field) or "<missing>") for item in records).items()))
