"""Reaction-family profiles for eNH3 claim rights and planning."""

from __future__ import annotations

from copy import deepcopy
import re
from typing import Any


REACTION_FAMILIES = [
    "eNRR",
    "LiNRR",
    "NO3RR",
    "NO2RR",
    "NORR",
    "mixed",
    "unclear",
]

PROFILE_FIELDS = (
    "reaction_family",
    "nitrogen_source",
    "product_admission_gates",
    "required_controls",
    "boundary_fields",
    "family_hidden_taxes",
    "family_route_types",
    "experimental_demonstration_allowed",
    "notes",
)

REACTION_FAMILY_PROFILES: dict[str, dict[str, Any]] = {
    "eNRR": {
        "reaction_family": "eNRR",
        "nitrogen_source": "N2",
        "product_admission_gates": [
            "isotope_15N",
            "blank_control",
            "NOx_control",
            "contamination_control",
            "ammonia_quantification",
        ],
        "required_controls": [
            "15N2 isotope validation",
            "Ar blank",
            "N2-free blank",
            "NOx/nitrate/nitrite screening",
            "background NH3 control",
        ],
        "boundary_fields": [],
        "family_hidden_taxes": ["contamination_tax", "measurement_matrix_tax"],
        "family_route_types": ["validation_gap_closure", "contamination_control", "product_state_accounting"],
        "experimental_demonstration_allowed": False,
        "notes": "General N2-to-NH3 electrochemical nitrogen reduction profile.",
    },
    "LiNRR": {
        "reaction_family": "LiNRR",
        "nitrogen_source": "N2 mediated by Li/Li+",
        "product_admission_gates": [
            "isotope_15N",
            "blank_control",
            "NOx_control",
            "contamination_control",
            "ammonia_quantification",
            "operating_field_disclosure",
        ],
        "required_controls": [
            "15N2 isotope validation",
            "Ar blank",
            "N2-free blank",
            "NOx/nitrate/nitrite screening",
            "background NH3 control",
            "electrolyte blank",
            "gas/liquid product accounting",
            "voltage/current/runtime reporting",
        ],
        "boundary_fields": [
            "Li salt",
            "solvent",
            "proton_donor",
            "water_content",
            "SEI/interphase",
            "SSC/GDE",
            "gas_flow",
            "liquid_flow",
            "product_state",
            "HOR/H2 if used",
        ],
        "family_hidden_taxes": [
            "solvent_management_tax",
            "resistance_or_renewal_tax",
            "wetting_outlet_capture_tax",
            "hydrogen_logistics_tax",
            "contamination_tax",
            "measurement_matrix_tax",
        ],
        "family_route_types": [
            "baseline_repeatability",
            "validation_gap_closure",
            "contamination_control",
            "electrolyte_window",
            "water_content_window",
            "proton_donor_window",
            "salt_solvent_window",
            "operating_field_matrix",
            "interphase_resistance",
            "flow_wetting",
            "HOR_proton_economy",
            "outlet_product_split",
            "product_state_accounting",
            "stability_failure",
            "process_boundary_probe",
            "postmortem_failure_analysis",
        ],
        "experimental_demonstration_allowed": True,
        "notes": "Boundary-dense Li-mediated NRR profile used for the USTC wet-lab demonstration track.",
    },
    "NO3RR": {
        "reaction_family": "NO3RR",
        "nitrogen_source": "nitrate",
        "product_admission_gates": [
            "nitrate_source_defined",
            "nitrogen_balance",
            "ammonia_quantification",
            "competing_product_tracking",
        ],
        "required_controls": [
            "nitrate/nitrite source accounting",
            "background NH3 control",
            "electrolyte blank",
            "nitrogen mass balance",
        ],
        "boundary_fields": [],
        "family_hidden_taxes": ["contamination_tax", "measurement_matrix_tax"],
        "family_route_types": ["validation_gap_closure", "contamination_control"],
        "experimental_demonstration_allowed": False,
        "notes": "Nitrate-to-ammonia electroreduction profile; 15N2 validation is not the default gate.",
    },
    "NO2RR": {
        "reaction_family": "NO2RR",
        "nitrogen_source": "nitrite",
        "product_admission_gates": [
            "nitrite_source_defined",
            "nitrogen_balance",
            "ammonia_quantification",
            "competing_product_tracking",
        ],
        "required_controls": [
            "nitrate/nitrite source accounting",
            "background NH3 control",
            "electrolyte blank",
            "nitrogen mass balance",
        ],
        "boundary_fields": [],
        "family_hidden_taxes": ["contamination_tax", "measurement_matrix_tax"],
        "family_route_types": ["validation_gap_closure", "contamination_control"],
        "experimental_demonstration_allowed": False,
        "notes": "Nitrite-to-ammonia electroreduction profile; 15N2 validation is not the default gate.",
    },
    "NORR": {
        "reaction_family": "NORR",
        "nitrogen_source": "NO",
        "product_admission_gates": [
            "NO_source_defined",
            "NOx_balance",
            "ammonia_quantification",
            "competing_product_tracking",
        ],
        "required_controls": [
            "NO source purity",
            "NOx balance",
            "gas handling blank",
            "ammonia quantification",
        ],
        "boundary_fields": [],
        "family_hidden_taxes": ["contamination_tax", "measurement_matrix_tax"],
        "family_route_types": ["validation_gap_closure", "contamination_control"],
        "experimental_demonstration_allowed": False,
        "notes": "NO-to-ammonia electroreduction profile. Gas handling burdens remain audit notes until formalized.",
    },
    "mixed": {
        "reaction_family": "mixed",
        "nitrogen_source": "multiple or ambiguous nitrogen sources",
        "product_admission_gates": ["nitrogen_source_disambiguation", "nitrogen_balance", "ammonia_quantification"],
        "required_controls": ["nitrogen-source accounting", "clarify nitrogen source", "nitrogen mass balance"],
        "boundary_fields": ["nitrogen_source_disambiguation"],
        "family_hidden_taxes": ["contamination_tax", "measurement_matrix_tax"],
        "family_route_types": ["validation_gap_closure", "contamination_control"],
        "experimental_demonstration_allowed": False,
        "notes": "Mixed-source claims require source disambiguation before stronger claim rights.",
    },
    "unclear": {
        "reaction_family": "unclear",
        "nitrogen_source": "unclear",
        "product_admission_gates": ["nitrogen_source_disambiguation", "ammonia_quantification"],
        "required_controls": ["clarify nitrogen source"],
        "boundary_fields": ["nitrogen_source_disambiguation"],
        "family_hidden_taxes": ["contamination_tax", "measurement_matrix_tax"],
        "family_route_types": ["validation_gap_closure", "contamination_control"],
        "experimental_demonstration_allowed": False,
        "notes": "Conservative fallback when the source text does not identify the ammonia nitrogen source.",
    },
}


def normalize_reaction_family(value: str) -> str:
    """Normalize a reaction-family label to a supported family."""

    text = re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")
    aliases = {
        "": "unclear",
        "unknown": "unclear",
        "not_specified": "unclear",
        "ambiguous": "unclear",
        "mixed_source": "mixed",
        "multiple": "mixed",
        "nrr": "eNRR",
        "enrr": "eNRR",
        "e_nrr": "eNRR",
        "electrochemical_nrr": "eNRR",
        "electrochemical_nitrogen_reduction": "eNRR",
        "li_nrr": "LiNRR",
        "linrr": "LiNRR",
        "li_mediated_nrr": "LiNRR",
        "lithium_mediated_nrr": "LiNRR",
        "lithium_mediated": "LiNRR",
        "no3rr": "NO3RR",
        "no3_rr": "NO3RR",
        "nitrate_reduction": "NO3RR",
        "nitrate_rr": "NO3RR",
        "no2rr": "NO2RR",
        "no2_rr": "NO2RR",
        "nitrite_reduction": "NO2RR",
        "nitrite_rr": "NO2RR",
        "norr": "NORR",
        "no_rr": "NORR",
        "nitric_oxide_reduction": "NORR",
    }
    candidate = aliases.get(text)
    if candidate:
        return candidate
    for family in REACTION_FAMILIES:
        if text == family.casefold():
            return family
    return "unclear"


def infer_reaction_family_from_text(text: str, default: str = "unclear") -> str:
    """Infer a conservative reaction-family label from source text."""

    return infer_reaction_family_detailed(text=text, default=default)["reaction_family"]

    normalized_default = normalize_reaction_family(default)
    source = re.sub(r"\s+", " ", str(text or "").casefold()).strip()
    if not source:
        return normalized_default

    signals: set[str] = set()
    if _contains_any(source, ["mixed nitrogen source", "multiple nitrogen sources", "nitrate and n2", "nitrite and n2"]):
        signals.add("mixed")
    if _contains_any(source, ["no3rr", "nitrate reduction", "nitrate electroreduction", "nitrate-to-ammonia", "nitrate to ammonia"]):
        signals.add("NO3RR")
    if re.search(r"\bno3\s*(?:-|−|rr|\b)|\bno3-\b|\bno3−\b", source):
        signals.add("NO3RR")
    if _contains_any(source, ["no2rr", "nitrite reduction", "nitrite electroreduction", "nitrite-to-ammonia", "nitrite to ammonia"]):
        signals.add("NO2RR")
    if re.search(r"\bno2\s*(?:-|−|rr|\b)|\bno2-\b|\bno2−\b", source):
        signals.add("NO2RR")
    if _contains_any(source, ["norr", "nitric oxide reduction", "nitric oxide electroreduction", "no-to-ammonia", "no to ammonia", "no-to-nh3", "no to nh3"]):
        signals.add("NORR")
    if re.search(r"\bno\s+(?:electro)?reduction\b", source) and _contains_any(source, ["ammonia", "nh3"]):
        signals.add("NORR")
    if _contains_any(
        source,
        [
            "lithium-mediated",
            "lithium mediated",
            "li-mediated",
            "li mediated",
            "linrr",
            "li-nrr",
            "li nrr",
            "li salt",
            "lithium salt",
            "liclo4",
            "litfsi",
            "lipf6",
            "tetrahydrofuran",
            "thf",
            "solid electrolyte interphase",
            "sei",
        ],
    ):
        signals.add("LiNRR")
    if _contains_any(source, ["n2 reduction", "nitrogen reduction", "dinitrogen", "n2-to-nh3", "n2 to nh3", "15n2"]):
        signals.add("eNRR")
    if re.search(r"\bnrr\b", source) and "LiNRR" not in signals:
        signals.add("eNRR")

    if "mixed" in signals:
        return "mixed"
    if "LiNRR" in signals and signals <= {"LiNRR", "eNRR"}:
        return "LiNRR"
    if len(signals) > 1:
        return "mixed"
    if signals:
        return next(iter(signals))
    return normalized_default


def score_reaction_families(
    text: str,
    section_type: str | None = None,
    title: str | None = None,
    abstract: str | None = None,
) -> dict[str, int]:
    """Score reaction-family evidence without selecting a final label."""

    scores, _signals, _context = _score_reaction_context(text, section_type=section_type, title=title, abstract=abstract)
    return scores


def infer_reaction_family_detailed(
    text: str | None = None,
    section_type: str | None = None,
    title: str | None = None,
    abstract: str | None = None,
    record: dict[str, Any] | None = None,
    default: str = "unclear",
) -> dict[str, Any]:
    """Infer a conservative reaction-family label with scores and evidence signals."""

    record = record or {}
    source_text = str(text if text is not None else _record_text(record))
    resolved_section_type = str(section_type or record.get("section_type") or record.get("provenance_type") or record.get("source_section") or "")
    resolved_title = title if title is not None else _first_text(record, "title", "paper_title")
    resolved_abstract = abstract if abstract is not None else _first_text(record, "abstract", "paper_abstract")
    scores, signals, context = _score_reaction_context(
        source_text,
        section_type=resolved_section_type,
        title=resolved_title,
        abstract=resolved_abstract,
    )
    normalized_default = normalize_reaction_family(default)
    existing_family = normalize_reaction_family(str(record.get("reaction_family") or ""))
    existing_scope = str(record.get("reaction_family_scope") or "").strip()
    existing_confidence = str(record.get("reaction_family_confidence") or "").strip()
    confidence_values = {"high", "medium", "low", "unclear"}
    scope_values = {"explicit_span", "section_context", "paper_consensus", "fallback"}

    if existing_family != "unclear":
        if existing_scope != "paper_consensus":
            scores[existing_family] = max(scores.get(existing_family, 0), 8)
            signals.append(f"explicit_record_reaction_family:{existing_family}")
        top_text_family, top_text_score = _top_family(scores)
        conflict = bool(record.get("reaction_family_conflict"))
        if top_text_family not in {"unclear", existing_family} and top_text_score >= 6:
            conflict = True
            signals.append(f"reaction_family_conflict:{existing_family}_vs_{top_text_family}")
        return _reaction_result(
            existing_family,
            existing_confidence if existing_confidence in confidence_values else "high",
            scores,
            signals,
            existing_scope if existing_scope in scope_values else "explicit_span",
            conflict,
        )

    top_family, top_score = _top_family(scores)
    second_family, second_score = _second_family(scores, top_family)
    if top_score >= 6 and second_score >= 6 and top_family != second_family and abs(top_score - second_score) <= 3:
        signals.append(f"reaction_family_conflict:{top_family}_vs_{second_family}")
        return _reaction_result("mixed", "medium", scores, signals, _scope_from_context(context, explicit=True), True)
    if top_score >= 6:
        return _reaction_result(top_family, "high", scores, signals, _scope_from_context(context, explicit=True), False)
    if top_score >= 4:
        return _reaction_result(top_family, "medium", scores, signals, _scope_from_context(context, explicit=False), False)
    if normalized_default != "unclear":
        return _reaction_result(normalized_default, "low", scores, [*signals, "fallback_default_reaction_family"], "fallback", False)
    return _reaction_result("unclear", "unclear", scores, signals or ["no_reaction_family_signal"], "fallback", False)


def build_document_reaction_family_context(
    document: dict[str, Any],
    records: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate document-level family inputs without copying full document text."""

    document_id = str(document.get("document_id") or document.get("paper_id") or "")
    title = next((_first_text(record, "paper_title", "title") for record in records
                  if _first_text(record, "paper_title", "title")), "")
    if not title:
        title = document_id.replace("_", " ")
    abstract = next((_first_text(record, "paper_abstract", "abstract") for record in records
                     if _first_text(record, "paper_abstract", "abstract")), "")
    explicit_span_signals: list[dict[str, str]] = []
    for record in records:
        family = normalize_reaction_family(str(record.get("reaction_family") or "unclear"))
        if (
            family not in {"unclear", "mixed"}
            and str(record.get("reaction_family_confidence") or "") == "high"
            and str(record.get("reaction_family_scope") or "") == "explicit_span"
        ):
            explicit_span_signals.append({
                "source_span_id": str(record.get("source_span_id") or record.get("span_id") or ""),
                "reaction_family": family,
            })
    return {
        "document_id": document_id,
        "paper_title": title,
        "paper_abstract": abstract,
        "document_headings": [str(section.get("heading_text") or "") for section in sections],
        "article_type": next((_first_text(record, "article_type", "paper_article_type") for record in records
                              if _first_text(record, "article_type", "paper_article_type")), ""),
        "explicit_high_confidence_span_family_signals": explicit_span_signals,
    }


def assess_document_reaction_family(record: dict[str, Any]) -> dict[str, Any]:
    """Infer one document family, prioritizing title/abstract over span voting."""

    explicit = normalize_reaction_family(str(record.get("document_reaction_family") or "unclear"))
    if explicit != "unclear":
        return _document_family_result(
            explicit,
            str(record.get("document_reaction_family_confidence") or "high"),
            _list_values(record.get("document_reaction_family_signals")) or ["explicit_document_reaction_family"],
            bool(record.get("document_reaction_family_conflict")),
        )

    title = _first_text(record, "paper_title", "title", "document_title")
    abstract = _first_text(record, "paper_abstract", "abstract", "document_abstract")
    headings_value = record.get("document_headings") or record.get("headings") or []
    headings = " ".join(str(value) for value in headings_value) if isinstance(headings_value, list) else str(headings_value)
    title_family = _strong_document_family(title)
    abstract_family = _strong_document_family(abstract)
    heading_family = _strong_document_family(headings)
    span_families = {
        normalize_reaction_family(str(item.get("reaction_family") or "unclear"))
        for item in record.get("explicit_high_confidence_span_family_signals") or []
        if isinstance(item, dict)
    } - {"unclear"}

    if title_family != "unclear":
        conflicts = {
            family for family in {abstract_family, heading_family, *span_families}
            if family not in {"unclear", title_family}
        }
        return _document_family_result(
            title_family,
            "high",
            [f"strong_title_family:{title_family}", *[f"document_family_disagreement:{title_family}_vs_{value}" for value in sorted(conflicts)]],
            bool(conflicts),
        )
    if abstract_family != "unclear":
        conflicts = {family for family in {heading_family, *span_families} if family not in {"unclear", abstract_family}}
        return _document_family_result(
            abstract_family,
            "high",
            [f"strong_abstract_family:{abstract_family}", *[f"document_family_disagreement:{abstract_family}_vs_{value}" for value in sorted(conflicts)]],
            bool(conflicts),
        )
    if heading_family != "unclear":
        return _document_family_result(heading_family, "medium", [f"document_heading_family:{heading_family}"], False)
    if len(span_families) == 1:
        family = next(iter(span_families))
        return _document_family_result(family, "medium", [f"unique_explicit_span_family:{family}"], False)
    if len(span_families) > 1:
        return _document_family_result(
            "mixed", "medium", [f"conflicting_explicit_span_families:{','.join(sorted(span_families))}"], True
        )
    return _document_family_result("unclear", "unclear", ["no_document_reaction_family_signal"], False)


def assess_effective_reaction_family(record: dict[str, Any]) -> dict[str, Any]:
    """Choose an additive effective family without overwriting the legacy family."""

    legacy = normalize_reaction_family(str(record.get("reaction_family") or "unclear"))
    document = assess_document_reaction_family(record)
    document_family = normalize_reaction_family(str(document["document_reaction_family"]))
    target_inferred = infer_reaction_family_detailed(text=_record_text(record))
    target_family = normalize_reaction_family(str(target_inferred.get("reaction_family") or "unclear"))
    target_explicit = bool(
        target_family not in {"unclear", "mixed"}
        and target_inferred.get("reaction_family_confidence") == "high"
        and target_inferred.get("reaction_family_scope") == "explicit_span"
    )
    document_high = bool(
        document_family not in {"unclear", "mixed"}
        and document.get("document_reaction_family_confidence") == "high"
    )

    if target_explicit:
        effective = target_family
        source = "explicit_high_confidence_target_span"
    elif document_high:
        effective = document_family
        source = "high_confidence_document"
    elif legacy != "unclear":
        effective = legacy
        source = "existing_reaction_family"
    else:
        effective = "unclear"
        source = "unclear"

    target_document_conflict = bool(
        document_high
        and legacy not in {"unclear", "mixed", document_family}
        and not target_explicit
    )
    correction = bool(legacy not in {"unclear", effective} and effective != "unclear")
    return {
        **document,
        "legacy_reaction_family": legacy,
        "effective_reaction_family": effective,
        "effective_reaction_family_source": source,
        "reaction_family_correction": correction,
        "document_target_reaction_family_conflict": target_document_conflict,
        "target_explicit_reaction_family": target_family if target_explicit else "unclear",
        "target_explicit_reaction_family_signals": target_inferred.get("reaction_family_signals") or [],
    }


def aggregate_paper_reaction_family(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate a conservative paper-level reaction-family consensus."""

    aggregate_scores = _empty_scores()
    signals: list[str] = []
    used_records = 0
    for record in records:
        if not _eligible_for_paper_consensus(record):
            continue
        detailed = infer_reaction_family_detailed(record=record)
        family = str(detailed.get("reaction_family") or "unclear")
        confidence = str(detailed.get("reaction_family_confidence") or "unclear")
        if family in {"unclear", "mixed"} or confidence not in {"high", "medium"}:
            continue
        weight = _paper_record_weight(record, detailed)
        score = int((detailed.get("reaction_family_scores") or {}).get(family, 0))
        aggregate_scores[family] += max(score, 4) + weight
        used_records += 1
        span_id = str(record.get("source_span_id") or record.get("span_id") or record.get("evidence_id") or used_records)
        signals.append(f"paper_consensus_record:{span_id}:{family}:{confidence}")

    top_family, top_score = _top_family(aggregate_scores)
    second_family, second_score = _second_family(aggregate_scores, top_family)
    if not used_records or top_score < 6:
        return _reaction_result("unclear", "unclear", aggregate_scores, signals or ["no_primary_family_consensus"], "fallback", False)
    if second_score >= 6 and top_family != second_family and top_score - second_score <= 3:
        signals.append(f"paper_reaction_family_conflict:{top_family}_vs_{second_family}")
        result = _reaction_result("mixed", "medium", aggregate_scores, signals, "paper_consensus", True)
        result["paper_consensus_record_count"] = used_records
        return result
    confidence = "high" if top_score >= 10 and top_score - second_score >= 4 else "medium"
    result = _reaction_result(top_family, confidence, aggregate_scores, signals, "paper_consensus", False)
    result["paper_consensus_record_count"] = used_records
    return result


def propagate_paper_family_to_unclear_spans(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach paper-level consensus and fill only unclear low-information spans."""

    by_paper: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        paper_id = str(record.get("paper_id") or "").strip()
        if paper_id:
            by_paper.setdefault(paper_id, []).append(record)

    paper_consensus = {paper_id: aggregate_paper_reaction_family(items) for paper_id, items in by_paper.items()}
    propagated: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        detailed = _existing_or_inferred_family(item)
        paper_id = str(item.get("paper_id") or "").strip()
        consensus = paper_consensus.get(paper_id, _reaction_result("unclear", "unclear", _empty_scores(), [], "fallback", False))
        consensus_family = str(consensus.get("reaction_family") or "unclear")
        item["paper_level_reaction_family"] = consensus_family

        current_family = str(detailed.get("reaction_family") or "unclear")
        current_confidence = str(detailed.get("reaction_family_confidence") or "unclear")
        can_propagate = (
            consensus_family not in {"unclear", "mixed"}
            and str(consensus.get("reaction_family_confidence") or "") in {"high", "medium"}
            and current_family == "unclear"
            and current_confidence in {"unclear", "low"}
            and _low_information_family_record(item, detailed)
            and not _low_trust_family_context(item)
        )
        if can_propagate:
            detailed = _reaction_result(
                consensus_family,
                "medium" if consensus.get("reaction_family_confidence") == "high" else "low",
                detailed.get("reaction_family_scores") or _empty_scores(),
                _dedupe([*(detailed.get("reaction_family_signals") or []), f"paper_consensus:{consensus_family}"]),
                "paper_consensus",
                False,
            )
        elif (
            consensus_family not in {"unclear", "mixed", current_family}
            and current_family not in {"unclear", "mixed"}
            and current_confidence in {"high", "medium"}
            and str(consensus.get("reaction_family_confidence") or "") in {"high", "medium"}
        ):
            detailed["reaction_family_conflict"] = True
            detailed["reaction_family_signals"] = _dedupe(
                [*(detailed.get("reaction_family_signals") or []), f"paper_consensus_conflict:{current_family}_vs_{consensus_family}"]
            )

        _copy_reaction_fields(item, detailed)
        item["paper_level_reaction_family"] = consensus_family
        propagated.append(item)
    return propagated


def get_reaction_profile(family: str) -> dict[str, Any]:
    """Return a copy of the reaction-family profile."""

    normalized = normalize_reaction_family(family)
    return deepcopy(REACTION_FAMILY_PROFILES[normalized])


def profile_required_controls(family: str) -> list[str]:
    return list(get_reaction_profile(family)["required_controls"])


def profile_hidden_taxes(family: str) -> list[str]:
    return list(get_reaction_profile(family)["family_hidden_taxes"])


def profile_route_types(family: str) -> list[str]:
    return list(get_reaction_profile(family)["family_route_types"])


def experimental_demonstration_allowed(family: str, lab_profile: dict[str, Any] | None = None) -> bool:
    """Return whether this family is in the current wet-lab demonstration scope."""

    normalized = normalize_reaction_family(family)
    profile_allowed = bool(REACTION_FAMILY_PROFILES[normalized]["experimental_demonstration_allowed"])
    if lab_profile is None:
        return profile_allowed
    demonstrations = lab_profile.get("reaction_family_demonstrations")
    if isinstance(demonstrations, dict) and normalized in demonstrations:
        return bool(demonstrations[normalized])
    allowed_families = lab_profile.get("allowed_reaction_families")
    if isinstance(allowed_families, list) and allowed_families:
        return normalized in {normalize_reaction_family(str(item)) for item in allowed_families}
    return profile_allowed


def _score_reaction_context(
    text: str,
    section_type: str | None = None,
    title: str | None = None,
    abstract: str | None = None,
) -> tuple[dict[str, int], list[str], dict[str, bool]]:
    scores = _empty_scores()
    signals: list[str] = []
    context = {"span_explicit": False, "context_only": False}
    _score_text_fragment(str(text or ""), "span", scores, signals, multiplier=1, context=context)
    if title:
        context["context_only"] = True
        _score_text_fragment(str(title), "title", scores, signals, multiplier=1, context=context)
    if abstract:
        context["context_only"] = True
        _score_text_fragment(str(abstract), "abstract", scores, signals, multiplier=2, context=context)
    if str(section_type or "").casefold() == "abstract" and any(scores[family] for family in ("eNRR", "LiNRR", "NO3RR", "NO2RR", "NORR")):
        signals.append("abstract_section_context")
    if scores["LiNRR"] >= 6 and scores["eNRR"] >= 6:
        scores["eNRR"] = min(scores["eNRR"], 3)
        signals.append("generic_n2_signal_subsumed_by_lithium_mediated_mechanism")
    return scores, _dedupe(signals), context


def _score_text_fragment(
    text: str,
    label: str,
    scores: dict[str, int],
    signals: list[str],
    multiplier: int,
    context: dict[str, bool],
) -> None:
    source = _normalize_text(text)
    if not source:
        return

    nitrate_context = _negative_nitrate_context(source)
    nitrite_context = _negative_nitrite_context(source)
    n2_external_comparison = _n2_external_comparison_inside_nitrate_target(source)
    if nitrate_context:
        signals.append(f"{label}:nitrate_context_not_feed")
    if nitrite_context:
        signals.append(f"{label}:nitrite_context_not_feed")

    def add(family: str, points: int, signal: str, explicit: bool = True) -> None:
        scores[family] += points * multiplier
        signals.append(f"{label}:{signal}")
        if label == "span" and explicit:
            context["span_explicit"] = True

    if _contains_any(source, ["mixed nitrogen source", "multiple nitrogen sources", "nitrate and n2", "nitrite and n2"]):
        add("mixed", 8, "mixed_nitrogen_source")

    if _contains_any(source, ["linrr", "li-nrr", "li nrr", "lithium-mediated nitrogen reduction", "lithium mediated nitrogen reduction", "li-mediated nrr", "li mediated nrr"]):
        add("LiNRR", 9, "explicit_linnr_or_lithium_mediated_nrr")
    if _contains_any(source, ["lithium-mediated", "lithium mediated", "li-mediated", "li mediated"]) and _contains_any(
        source, ["n2", "nitrogen reduction", "nrr", "dinitrogen", "ammonia", "nh3"]
    ):
        add("LiNRR", 8, "lithium_mediated_n2_reduction")
    if _contains_any(source, ["li plating", "lithium plating", "li deposition", "lithium deposition"]) and _contains_any(
        source, ["nitridation", "protonation", "lithium nitride", "li3n"]
    ):
        add("LiNRR", 8, "li_plating_nitridation_protonation")
    if _n2_reaction_signal(source) and _li_salt_signal(source) and _nonaqueous_or_interphase_signal(source):
        add("LiNRR", 7, "n2_li_salt_nonaqueous_interphase_reaction")
    if _li_salt_signal(source):
        add("LiNRR", 1, "li_salt_context", explicit=False)
    if _contains_any(source, ["tetrahydrofuran", " thf ", " thf.", " thf,", " thf)"]):
        add("LiNRR", 1, "thf_context", explicit=False)
    if _nonaqueous_or_interphase_signal(source):
        add("LiNRR", 1, "nonaqueous_or_interphase_context", explicit=False)

    if not n2_external_comparison and _contains_any(source, ["enrr", "e-nrr", "electrochemical nrr"]):
        add("eNRR", 8, "explicit_enrr")
    if not n2_external_comparison and _contains_any(source, ["n2-to-nh3", "n2 to nh3", "dinitrogen to ammonia", "dinitrogen-to-ammonia"]):
        add("eNRR", 8, "n2_to_ammonia")
    if not n2_external_comparison and _contains_any(source, ["n2 feed", "n2 gas feed", "nitrogen gas feed", "n2 as nitrogen source", "n2 as the nitrogen source"]):
        add("eNRR", 7, "n2_feed_or_source")
    if not n2_external_comparison and _contains_any(source, ["electrochemical nitrogen reduction under n2", "nitrogen reduction under n2"]):
        add("eNRR", 7, "nitrogen_reduction_under_n2")
    if not n2_external_comparison and _contains_any(source, ["15n2", "15 n2"]):
        add("eNRR", 7, "15n2_nitrogen_source")
    if not n2_external_comparison and _n2_reaction_signal(source):
        add("eNRR", 6, "n2_reduction_reaction")
    if not n2_external_comparison and re.search(r"\bnrr\b", source) and scores["LiNRR"] < 6:
        add("eNRR", 6, "nrr_without_lithium_mediation")
    if n2_external_comparison:
        signals.append(f"{label}:external_n2_comparison_not_target_family")

    if not nitrate_context:
        if re.search(r"\bno3rr\b|\bno3\s*rr\b", source):
            add("NO3RR", 9, "explicit_no3rr")
        if _contains_any(source, ["nitrate-to-ammonia", "nitrate to ammonia", "no3- to nh3", "no3 to nh3"]):
            add("NO3RR", 8, "nitrate_to_ammonia")
        if _contains_any(source, ["nitrate reduction reaction", "nitrate electroreduction", "nitrate reduction to ammonia"]):
            add("NO3RR", 8, "nitrate_reduction_reaction")
        if re.search(r"\b(?:electrochemical|electrocatalytic) nitrate reduction\b", source):
            add("NO3RR", 8, "explicit_electrochemical_nitrate_reduction")
        if re.search(r"\bno3\s*-+\s*to\s*-?\s*nh3\b", source):
            add("NO3RR", 8, "no3_to_nh3")
        if _feed_source_signal(source, "nitrate", "no3"):
            add("NO3RR", 7, "nitrate_feed_or_source")

    if not nitrite_context:
        if re.search(r"\bno2rr\b|\bno2\s*rr\b", source):
            add("NO2RR", 9, "explicit_no2rr")
        if _contains_any(source, ["nitrite-to-ammonia", "nitrite to ammonia", "no2- to nh3", "no2 to nh3"]):
            add("NO2RR", 8, "nitrite_to_ammonia")
        if re.search(r"\bno2\s*-?\s+reduction\s+to\s+(?:ammonia|nh3)\b", source):
            add("NO2RR", 8, "no2_reduction_to_ammonia")
        if _contains_any(source, ["nitrite reduction reaction", "nitrite electroreduction", "nitrite reduction to ammonia"]):
            add("NO2RR", 8, "nitrite_reduction_reaction")
        if _feed_source_signal(source, "nitrite", "no2"):
            add("NO2RR", 7, "nitrite_feed_or_source")

    if re.search(r"\bnorr\b|\bno\s*rr\b", source):
        add("NORR", 9, "explicit_norr")
    if _contains_any(source, ["nitric oxide reduction", "nitric oxide electroreduction", "no-to-ammonia", "no to ammonia", "no-to-nh3", "no to nh3"]):
        add("NORR", 8, "no_to_ammonia_or_reduction")
    if re.search(r"\bno\s+reduction\s+to\s+(?:ammonia|nh3)\b", source):
        add("NORR", 8, "no_reduction_to_ammonia")
    if _no_feed_source_signal(source):
        add("NORR", 7, "no_feed_or_source")


def _reaction_result(
    family: str,
    confidence: str,
    scores: dict[str, int],
    signals: list[str],
    scope: str,
    conflict: bool,
) -> dict[str, Any]:
    normalized = normalize_reaction_family(family)
    return {
        "reaction_family": normalized,
        "reaction_family_confidence": confidence if confidence in {"high", "medium", "low", "unclear"} else "unclear",
        "reaction_family_scores": {key: int(scores.get(key, 0)) for key in REACTION_FAMILIES},
        "reaction_family_signals": _dedupe(signals),
        "reaction_family_scope": scope if scope in {"explicit_span", "section_context", "paper_consensus", "fallback"} else "fallback",
        "reaction_family_conflict": bool(conflict),
    }


def _existing_or_inferred_family(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("reaction_family") and record.get("reaction_family_confidence") and record.get("reaction_family_scope"):
        scores = record.get("reaction_family_scores") if isinstance(record.get("reaction_family_scores"), dict) else _empty_scores()
        return _reaction_result(
            str(record.get("reaction_family") or "unclear"),
            str(record.get("reaction_family_confidence") or "unclear"),
            scores,
            _list_values(record.get("reaction_family_signals")),
            str(record.get("reaction_family_scope") or "fallback"),
            bool(record.get("reaction_family_conflict")),
        )
    return infer_reaction_family_detailed(record=record)


def _copy_reaction_fields(record: dict[str, Any], detailed: dict[str, Any]) -> None:
    for key in (
        "reaction_family",
        "reaction_family_confidence",
        "reaction_family_scores",
        "reaction_family_signals",
        "reaction_family_scope",
        "reaction_family_conflict",
    ):
        record[key] = detailed.get(key)


def _eligible_for_paper_consensus(record: dict[str, Any]) -> bool:
    provenance_type = str(record.get("provenance_type") or record.get("source_section") or record.get("section_type") or "").strip()
    provenance = re.sub(r"[^a-z0-9]+", "_", provenance_type.casefold()).strip("_")
    if provenance in {"reference", "references", "bibliography", "front_matter", "metadata", "copyright_note"}:
        return False
    if provenance in {"review_table", "table", "figure_caption", "scheme_caption", "secondary_review", "supplementary"}:
        return False
    text_class = str(record.get("text_class") or "").strip()
    if text_class in {"reference_list", "review_table", "figure_caption"}:
        return False
    if record.get("is_reject_or_low_trust"):
        return False
    if record.get("is_primary_admissible") is True:
        return True
    return provenance in {"abstract", "results", "methods", "discussion", "body", "introduction", ""}


def _paper_record_weight(record: dict[str, Any], detailed: dict[str, Any]) -> int:
    provenance = str(record.get("provenance_type") or record.get("section_type") or record.get("source_section") or "").casefold()
    weight = 0
    if provenance == "abstract":
        weight += 4
    elif provenance in {"results", "methods", "discussion", "body"}:
        weight += 2
    if detailed.get("reaction_family_scope") == "explicit_span":
        weight += 3
    if detailed.get("reaction_family_confidence") == "high":
        weight += 2
    return weight


def _low_information_family_record(record: dict[str, Any], detailed: dict[str, Any]) -> bool:
    scores = detailed.get("reaction_family_scores") or {}
    max_score = max([int(value) for value in scores.values()] or [0])
    if max_score >= 4:
        return False
    text = _normalize_text(_record_text(record))
    if not text:
        return True
    return not any(token in text for token in ["n2", "nitrate", "nitrite", "no3", "no2", "nitric oxide", "nrr", "linrr", "enrr"])


def _low_trust_family_context(record: dict[str, Any]) -> bool:
    provenance = re.sub(r"[^a-z0-9]+", "_", str(record.get("provenance_type") or record.get("source_section") or "").casefold()).strip("_")
    return provenance in {"reference", "references", "bibliography", "front_matter", "metadata", "copyright_note"}


def _scope_from_context(context: dict[str, bool], explicit: bool) -> str:
    if explicit and context.get("span_explicit"):
        return "explicit_span"
    if context.get("context_only"):
        return "section_context"
    return "explicit_span" if explicit else "section_context"


def _top_family(scores: dict[str, int]) -> tuple[str, int]:
    candidates = [(family, int(scores.get(family, 0))) for family in REACTION_FAMILIES if family != "unclear"]
    if not candidates:
        return "unclear", 0
    family, score = max(candidates, key=lambda item: (item[1], -REACTION_FAMILIES.index(item[0])))
    return (family, score) if score > 0 else ("unclear", 0)


def _second_family(scores: dict[str, int], top_family: str) -> tuple[str, int]:
    candidates = [(family, int(scores.get(family, 0))) for family in REACTION_FAMILIES if family not in {"unclear", top_family}]
    if not candidates:
        return "unclear", 0
    family, score = max(candidates, key=lambda item: (item[1], -REACTION_FAMILIES.index(item[0])))
    return (family, score) if score > 0 else ("unclear", 0)


def _empty_scores() -> dict[str, int]:
    return {family: 0 for family in REACTION_FAMILIES}


def _negative_nitrate_context(text: str) -> bool:
    if _feed_source_signal(text, "nitrate", "no3") or _contains_any(text, ["nitrate-to-ammonia", "nitrate to ammonia", "no3rr"]):
        return False
    return _contains_any(
        text,
        [
            "nitrate screening",
            "screening nitrate",
            "nitrate impurity",
            "nitrate contamination",
            "exclude nitrate",
            "excluded nitrate",
            "background nitrate",
            "nox contamination",
            "background nox",
        ],
    )


def _negative_nitrite_context(text: str) -> bool:
    if _feed_source_signal(text, "nitrite", "no2") or _contains_any(text, ["nitrite-to-ammonia", "nitrite to ammonia", "no2rr"]):
        return False
    return _contains_any(
        text,
        [
            "nitrite screening",
            "screening nitrite",
            "nitrite impurity",
            "nitrite contamination",
            "exclude nitrite",
            "excluded nitrite",
            "background nitrite",
            "nox contamination",
            "background nox",
        ],
    )


def _n2_reaction_signal(text: str) -> bool:
    return _contains_any(
        text,
        [
            "n2 reduction",
            "nitrogen reduction",
            "dinitrogen reduction",
            "n2-to-nh3",
            "n2 to nh3",
            "nitrogen-to-ammonia",
            "nitrogen to ammonia",
        ],
    )


def _li_salt_signal(text: str) -> bool:
    return _contains_any(text, ["li salt", "lithium salt", "liclo4", "litfsi", "lipf6", "liotf", "li triflate", "li+"])


def _nonaqueous_or_interphase_signal(text: str) -> bool:
    return _contains_any(
        text,
        [
            "nonaqueous",
            "non-aqueous",
            "tetrahydrofuran",
            " thf ",
            "diglyme",
            "glyme",
            "ether",
            "solid electrolyte interphase",
            " sei ",
            "interphase",
        ],
    )


def _feed_source_signal(text: str, word: str, formula: str) -> bool:
    return bool(
        re.search(rf"\b{word}\b.{0,45}\b(?:feed|reactant|substrate|nitrogen source|source)\b", text)
        or re.search(rf"\b(?:feed|reactant|substrate|nitrogen source|source)\b.{0,45}\b{word}\b", text)
        or re.search(rf"\b{formula}\s*-?\b.{0,45}\b(?:feed|reactant|substrate|source)\b", text)
        or re.search(rf"\b(?:feed|reactant|substrate|source)\b.{0,45}\b{formula}\s*-?\b", text)
    )


def _no_feed_source_signal(text: str) -> bool:
    return bool(
        re.search(r"\b(?:no|nitric oxide)\b.{0,45}\b(?:feed|reactant|substrate|nitrogen source|source)\b", text)
        or re.search(r"\b(?:feed|reactant|substrate|nitrogen source|source)\b.{0,45}\b(?:no|nitric oxide)\b", text)
    ) and "nox" not in text


def _record_text(record: dict[str, Any]) -> str:
    for key in ("source_text", "target_text", "source_span", "text"):
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _first_text(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _normalize_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", str(text or "").casefold()).strip()
    return f" {normalized} " if normalized else ""


def _list_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _strong_document_family(text: str) -> str:
    source = " ".join(str(text or "").replace("_", " ").split())
    if not source:
        return "unclear"
    families: set[str] = set()
    patterns = (
        ("NO3RR", r"\b(?:NO3RR|nitrate (?:electro)?reduction|nitrate[- ]to[- ]ammonia)\b"),
        ("NO2RR", r"\b(?:NO2RR|nitrite (?:electro)?reduction|nitrite[- ]to[- ]ammonia)\b"),
        ("NORR", r"\b(?:NORR|nitric[- ]oxide (?:electro)?reduction|NO[- ]to[- ]ammonia)\b"),
        ("LiNRR", r"\b(?:LiNRR|lithium[- ]mediated (?:nitrogen reduction|N2 reduction|NRR))\b"),
        ("eNRR", r"\b(?:eNRR|dinitrogen (?:electro)?reduction|N2 (?:electro)?reduction|nitrogen reduction reaction|NRR)\b"),
    )
    for family, pattern in patterns:
        if re.search(pattern, source, re.IGNORECASE):
            families.add(family)
    if "LiNRR" in families and "eNRR" in families:
        families.remove("eNRR")
    if len(families) == 1:
        return next(iter(families))
    if len(families) > 1:
        return "mixed"
    return "unclear"


def _n2_external_comparison_inside_nitrate_target(text: str) -> bool:
    """Treat cited/comparative N2 benchmarks as local context in a nitrate target span."""

    nitrate_target = bool(
        re.search(r"\bnitrate (?:electro)?reduction\b", text)
        or re.search(r"\bno3\s*-{0,2}\s*(?:to|reduction)\b", text)
        or "kno3" in text
    )
    if not nitrate_target:
        return False
    return bool(
        re.search(r"\breported\s+n2[- ]to[- ]nh3\s+conversions?\b", text)
        or re.search(r"\bdifferent from n2 reduction studies\b", text)
        or re.search(r"\b(?:compared|comparison|benchmark(?:ed)?)\b.{0,120}\bn2[- ](?:to[- ]nh3|reduction)\b", text)
    )


def _document_family_result(family: str, confidence: str, signals: list[str], conflict: bool) -> dict[str, Any]:
    return {
        "document_reaction_family": normalize_reaction_family(family),
        "document_reaction_family_confidence": confidence if confidence in {"high", "medium", "low", "unclear"} else "unclear",
        "document_reaction_family_signals": _dedupe(signals),
        "document_reaction_family_conflict": bool(conflict),
    }
