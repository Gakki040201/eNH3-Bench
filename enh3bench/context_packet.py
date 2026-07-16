"""Build and export source-grounded Evidence Context Packets."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from enh3bench.claim_ownership import assess_claim_ownership
from enh3bench.claim_typing import (
    classify_claim_type,
    has_ammonia_quantification_signal,
    is_fe_material_only_false_performance,
)
from enh3bench.document_context import (
    DocumentContextIndex,
    get_local_paragraph_context,
    get_section_chunk,
    resolve_document_for_span,
    resolve_span_mapping,
)
from enh3bench.document_scope import (
    PRIMARY_RESEARCH_GENRE,
    TARGET_DOCUMENT_SCOPE,
    assess_document_genre,
    assess_document_scope,
    build_document_genre_context,
)
from enh3bench.evidence_linking import (
    DEFAULT_LINK_LIMITS,
    DEFAULT_MINIMUM_LINK_SCORE,
    HIERARCHICAL_LINKING_PROFILE,
    KEYWORD_LINKING_PROFILE,
    ORDERED_SOURCE_PROFILE,
    LINK_TYPES,
    link_supporting_evidence,
)
from enh3bench.reaction_profiles import (
    assess_document_reaction_family,
    assess_effective_reaction_family,
    build_document_reaction_family_context,
    get_reaction_profile,
    infer_reaction_family_detailed,
    normalize_reaction_family,
)
from enh3bench.validation_gates import (
    detect_validation_gate,
    has_generic_isotope_without_15n,
    has_negated_no_source,
    has_negated_nox_balance,
)
from enh3bench.source_ledger import (
    OrderedSourceLedger,
    attach_source_coordinates_to_spans,
    sort_spans_by_source_order,
)
from enh3bench.span_context import (
    build_document_span_index,
    get_next_spans,
    get_previous_spans,
    get_same_section_spans,
    validate_no_cross_paper_links,
)


CONTEXT_PACKET_SCHEMA_VERSION = "1.1"
ORDERED_CONTEXT_PACKET_SCHEMA_VERSION = "1.4"
LEGACY_CONTEXT_PACKET_SCHEMA_VERSION = "1.0"
LOCATION_FIELDS = (
    "document_id", "source_start_offset", "source_end_offset", "section_start_offset",
    "section_end_offset", "section_level", "section_type", "section_confidence",
    "section_signals", "source_section", "path",
)
LEGACY_PACKET_FIELDS = (
    "context_packet_schema_version", "context_packet_id", "run_name", "paper_id", "paper_title",
    "paper_abstract", "paper_level_reaction_family", "paper_level_reaction_family_confidence",
    "target_span_id", "target_stable_span_uid", "target_span_order", "target_text",
    "target_text_class", "target_provenance_type", "target_section_heading", "target_section_path",
    "target_reaction_family", "target_span_boundary", "target_admissibility_status", "previous_spans",
    "next_spans", "same_section_spans", "linked_performance_spans", "linked_validation_spans",
    "linked_quantification_spans", "linked_reactor_spans", "linked_process_spans",
    "linked_negative_or_contradicting_spans", "context_hint_spans", "context_sufficient",
    "context_missing_types", "context_confidence", "linking_signals", "warnings",
)
PACKET_FIELDS = (
    "context_packet_schema_version", "context_profile", "context_packet_id", "run_name", "paper_id",
    "document_id", "document_ref", "document_body_sha256", "full_document_available", "paper_title",
    "paper_abstract", "paper_level_reaction_family", "paper_level_reaction_family_confidence",
    "target_span_id", "target_stable_span_uid", "target_stable_span_uid_method", "target_text",
    "target_text_class", "target_provenance_type", "target_reaction_family", "target_span_boundary",
    "target_admissibility_status", "target_mapping", "local_context", "evidence_items",
    "evidence_role_index", "classification_context_sufficient", "claim_support_context_sufficient",
    "context_purpose", "context_sufficient", "context_missing_types", "context_confidence",
    "linking_signals", "linking_diagnostics", "warnings",
)
ORDERED_PACKET_FIELDS = (
    "context_packet_schema_version", "context_profile", "context_packet_id", "run_name",
    "paper_id", "document_id", "document_ref", "document_body_sha256",
    "target_span_id", "target_stable_span_uid", "target_source_locator", "target_source_order_key",
    "target_section_uid", "target_section_outline_label", "target_section_heading", "target_raw_heading",
    "target_direct_section_type", "target_effective_section_type", "target_section_type_source",
    "target_section_type",
    "target_paragraph_uid", "target_paragraph_global_index", "target_paragraph_index_in_section",
    "target_document_relative_position", "target_section_relative_position",
    "target_source_start_offset", "target_source_end_offset", "target_text", "target_text_class",
    "target_provenance_type", "target_reaction_family", "target_span_boundary",
    "target_admissibility_status", "target_claim_type", "target_mapping",
    "legacy_reaction_family", "document_reaction_family", "document_reaction_family_confidence",
    "document_reaction_family_signals", "document_reaction_family_conflict",
    "effective_reaction_family", "effective_reaction_family_source", "reaction_family_correction",
    "document_target_reaction_family_conflict", "target_explicit_reaction_family",
    "target_explicit_reaction_family_signals",
    "semantic_eligibility_schema_version", "document_genre", "document_genre_confidence",
    "document_genre_signals", "document_genre_primary_applicable",
    "span_claim_scope", "span_claim_scope_confidence", "span_claim_scope_signals",
    "span_claim_scope_primary_applicable", "document_scope", "document_scope_confidence",
    "document_scope_signals", "document_scope_primary_applicable", "claim_ownership",
    "claim_ownership_confidence", "claim_ownership_signals", "claim_ownership_primary_applicable",
    "semantic_claim_type", "semantic_claim_type_confidence", "semantic_claim_type_conflict",
    "legacy_claim_type", "semantic_claim_type_signals", "ammonia_quantification_signal",
    "performance_evidence_strength", "performance_evidence_signals", "performance_result_evidence",
    "quantitative_performance_evidence",
    "gas_purification_trap_signal", "mass_spectrometry_quantification_signal",
    "enzymatic_quantification_signal", "primary_applicability_hard_gate_failures",
    "base_claim_support_applicable", "primary_semantic_eligibility",
    "target_is_primary_admissible", "target_is_secondary_or_context",
    "target_is_reject_or_low_trust",
    "previous_paragraph", "target_paragraph", "next_paragraph",
    "section_context", "document_outline", "evidence_items", "evidence_role_index",
    "classification_context_sufficient", "claim_support_applicable", "claim_support_context_sufficient",
    "packet_local_context_applicable", "packet_local_context_sufficient",
    "packet_local_context_status", "packet_local_missing_types", "family_gate_coverage",
    "family_gate_coverage_any_source", "family_gate_coverage_primary_admissible",
    "paper_gate_coverage_observed", "paper_gate_coverage_missing", "paper_gate_coverage_status",
    "paper_gate_coverage_any_source_observed", "paper_gate_coverage_any_source_missing",
    "paper_gate_coverage_any_source_status", "paper_gate_coverage_primary_admissible_observed",
    "paper_gate_coverage_primary_admissible_missing", "paper_gate_coverage_primary_admissible_status",
    "local_reaction_family_conflict", "local_reaction_family_conflict_any_source",
    "local_reaction_family_conflict_primary_admissible", "local_reaction_family_conflict_span_ids",
    "local_reaction_family_conflict_signals", "local_off_target_reaction_conflict",
    "local_off_target_reaction_conflict_signals",
    "context_purpose", "context_sufficient",
    "context_missing_types", "context_confidence", "linking_signals", "linking_diagnostics", "warnings",
)
LINK_PACKET_FIELDS = {
    "performance": "linked_performance_spans",
    "validation": "linked_validation_spans",
    "quantification": "linked_quantification_spans",
    "reactor": "linked_reactor_spans",
    "process": "linked_process_spans",
    "negative_or_contradicting": "linked_negative_or_contradicting_spans",
    "context_hint": "context_hint_spans",
}
LOW_TRUST_PROVENANCE = {"reference", "bibliography", "figure_caption", "scheme_caption", "review_table"}
LOW_TRUST_TEXT_CLASSES = {"reference_list", "figure_caption", "scheme_caption", "review_table", "background_context"}
PRIMARY_SEMANTIC_CLAIM_TYPES = {
    "performance_result_claim", "validation_claim", "ammonia_quantification_claim", "reactor_claim", "process_claim",
}
AMMONIA_REACTION_FAMILIES = {"eNRR", "LiNRR", "NO3RR", "NO2RR", "NORR"}
_OFF_TARGET_REACTION_PATTERNS = (
    ("CO2RR", re.compile(r"\bco2rr\b|\bcarbon dioxide reduction\b", re.IGNORECASE)),
    ("ORR", re.compile(r"\borr\b|\boxygen reduction\b", re.IGNORECASE)),
    ("OER", re.compile(r"\boer\b|\boxygen evolution\b", re.IGNORECASE)),
    ("HER", re.compile(r"\bher\b|\bhydrogen evolution\b", re.IGNORECASE)),
    ("water_splitting", re.compile(r"\bwater splitting\b", re.IGNORECASE)),
    ("Zn_air_battery", re.compile(r"\bzn[- ]air batter(?:y|ies)\b|\bzinc[- ]air batter(?:y|ies)\b", re.IGNORECASE)),
    ("fuel_cell", re.compile(r"\bfuel cells?\b|\bpemfc\b", re.IGNORECASE)),
    ("lithium_sulfur_battery", re.compile(r"\blithium[- ]sulfur batter(?:y|ies)\b|\bli[- ]s batter(?:y|ies)\b", re.IGNORECASE)),
    ("methanol_oxidation", re.compile(r"\bmethanol oxidation\b", re.IGNORECASE)),
    ("formic_acid_oxidation", re.compile(r"\bformic acid oxidation\b", re.IGNORECASE)),
)
_AMMONIA_REACTION_SUBJECT = re.compile(
    r"\b(?:enrr|linrr|no3rr|no2rr|norr|nitrogen reduction|n2 reduction|nitrate reduction|"
    r"nitrite reduction|nitric oxide reduction|no reduction|nitrogen fixation|ammonia (?:synthesis|"
    r"electrosynthesis|production)|lithium[- ]mediated (?:nitrogen reduction|nrr))\b",
    re.IGNORECASE,
)
BOUNDARY_RANK = {
    "unsupported_or_secondary": 0, "product_admissibility": 1, "cell_metric": 2,
    "reactor_legibility": 3, "process_partial": 4, "plant_facing_insufficient": 5,
}


def promote_document_location(
    record: dict[str, Any], raw_record: dict[str, Any] | None, provenance_record: dict[str, Any] | None
) -> dict[str, Any]:
    """Return a copy with location fields promoted by explicit precedence."""

    promoted = dict(record)
    raw = raw_record if isinstance(raw_record, dict) else {}
    provenance = provenance_record if isinstance(provenance_record, dict) else {}
    warnings = _list_values(record.get("location_warnings"))
    sources = (("explicit_bundle", record), ("raw_record", raw), ("provenance", provenance))
    source_pair, source_pair_source = _select_location_pair(sources, "source_start_offset", "source_end_offset")
    section_pair, section_pair_source = _select_location_pair(sources, "section_start_offset", "section_end_offset")
    document_id, document_id_source = _select_location_value(sources, "document_id")
    metadata_fields = ("section_level", "section_type", "section_confidence", "section_signals", "source_section", "path")
    metadata, metadata_source = _select_location_metadata(sources, metadata_fields)
    promoted["source_start_offset"], promoted["source_end_offset"] = source_pair
    promoted["section_start_offset"], promoted["section_end_offset"] = section_pair
    promoted["document_id"] = document_id
    for field in metadata_fields:
        promoted[field] = _copy_value(metadata.get(field)) if field in metadata else None
    promoted["location_sources"] = {
        "source_offset_pair": source_pair_source,
        "section_offset_pair": section_pair_source,
        "document_id": document_id_source,
        "section_metadata": metadata_source,
    }
    source_names = [source_pair_source, section_pair_source, document_id_source, metadata_source]
    promoted["location_source"] = next((name for name in source_names if name != "unresolved"), "unresolved")
    if all(name == "unresolved" for name in source_names):
        warnings.append("document_location_unresolved")
    if any(name == "unresolved" for name in source_names):
        warnings.append("partial_document_location")
    promoted["location_warnings"] = _dedupe(warnings)
    return promoted


def merge_context_sources(
    evidence_bundles: list[dict[str, Any]],
    claim_rights: list[dict[str, Any]] | None = None,
    hidden_tax: list[dict[str, Any]] | None = None,
    provenance: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Merge context inputs by source_span_id without mutating any ledger."""

    claim_index = _index_by_span(claim_rights or [])
    tax_index = _index_by_span(hidden_tax or [])
    provenance_index = _index_by_span(provenance or [])
    merged: list[dict[str, Any]] = []
    for bundle in evidence_bundles:
        record = dict(bundle)
        span_id = _span_id(record)
        extracted = record.get("extracted_fields")
        if isinstance(extracted, dict):
            for key, value in extracted.items():
                record.setdefault(key, _copy_value(value))
        raw = record.get("raw_record") if isinstance(record.get("raw_record"), dict) else {}
        for key in (
            "paper_title", "title", "paper_abstract", "abstract", "article_type", "paper_article_type", "section_path",
            "section_heading", "span_order", "candidate_score", "matched_keywords",
        ):
            if _present(raw.get(key)):
                record.setdefault(key, _copy_value(raw[key]))
        claim = claim_index.get(span_id, {})
        tax = tax_index.get(span_id, {})
        provenance_record = provenance_index.get(span_id, {})
        for key, value in claim.items():
            if key not in {"paper_id", "source_span_id", "source_text"} or not record.get(key):
                record[key] = _copy_value(value)
        if tax:
            record["detected_taxes"] = _copy_value(tax.get("detected_taxes") or [])
            record["hidden_tax_missing_measurements"] = _copy_value(tax.get("missing_measurements") or [])
            record["hidden_tax_required_controls"] = _copy_value(tax.get("required_controls") or [])
            record["hidden_tax_severity"] = tax.get("severity") or ""
        record = promote_document_location(record, raw, provenance_record)
        for key in (
            "section_path", "section_heading", "provenance_type",
            "provenance_confidence", "is_primary_admissible", "is_secondary_or_context", "is_reject_or_low_trust",
        ):
            if _present(provenance_record.get(key)):
                record[key] = _copy_value(provenance_record[key])
        record["source_span_id"] = span_id
        merged.append(record)
    return merged


def _attach_document_genre_assessments(
    records: list[dict[str, Any]], source_ledger: OrderedSourceLedger
) -> list[dict[str, Any]]:
    """Compute document genre/family once, then attach additive effective families."""

    records_by_document: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        records_by_document[str(record.get("document_id") or "")].append(record)
    assessments: dict[str, dict[str, Any]] = {}
    for document_id, document_records in records_by_document.items():
        document = source_ledger.documents_by_id.get(document_id, {"document_id": document_id})
        genre_context = build_document_genre_context(
            document,
            document_records,
            source_ledger.sections_by_document.get(document_id, []),
        )
        family_context = build_document_reaction_family_context(
            document,
            document_records,
            source_ledger.sections_by_document.get(document_id, []),
        )
        assessments[document_id] = {
            **assess_document_genre(genre_context),
            **assess_document_reaction_family(family_context),
        }
    attached: list[dict[str, Any]] = []
    for record in records:
        document_id = str(record.get("document_id") or "")
        document_record = {**record, **assessments[document_id]}
        attached.append({**document_record, **assess_effective_reaction_family(document_record)})
    return attached


def build_context_packets(
    evidence_bundles: list[dict[str, Any]],
    claim_rights: list[dict[str, Any]] | None,
    hidden_tax: list[dict[str, Any]] | None,
    provenance: list[dict[str, Any]] | None,
    *,
    run_name: str,
    context_profile: str = KEYWORD_LINKING_PROFILE,
    document_context_index: DocumentContextIndex | None = None,
    source_ledger: OrderedSourceLedger | None = None,
    minimum_link_score: float = DEFAULT_MINIMUM_LINK_SCORE,
    adjacent_before: int = 1,
    adjacent_after: int = 1,
    same_section_maximum: int = 4,
    maximum_per_category: int = 2,
    maximum_total_links: int = 12,
    local_paragraphs_before: int = 1,
    local_paragraphs_after: int = 1,
    section_chunk_max_characters: int = 12000,
) -> list[dict[str, Any]]:
    merged = merge_context_sources(evidence_bundles, claim_rights, hidden_tax, provenance)
    if context_profile == ORDERED_SOURCE_PROFILE:
        if source_ledger is None:
            raise ValueError("ordered_source_v1 requires source_ledger")
        merged = attach_source_coordinates_to_spans(merged, source_ledger)
        merged = sort_spans_by_source_order(merged)
        merged = _attach_document_genre_assessments(merged, source_ledger)
    index = build_document_span_index(merged)
    limits = {
        **DEFAULT_LINK_LIMITS, "adjacent_before": adjacent_before, "adjacent_after": adjacent_after,
        "same_section_maximum": same_section_maximum, "maximum_per_category": maximum_per_category,
        "maximum_total_links": maximum_total_links,
    }
    packets: list[dict[str, Any]] = []
    for span_id, target in index.records_by_id.items():
        paper_records = index.paper_records[str(target["paper_id"])]
        links = link_supporting_evidence(
            target, paper_records, limits, profile=context_profile, minimum_link_score=minimum_link_score
        )
        if context_profile == KEYWORD_LINKING_PROFILE:
            packet = _legacy_packet(
                target, span_id, index, links, run_name, adjacent_before, adjacent_after, same_section_maximum
            )
        elif context_profile == HIERARCHICAL_LINKING_PROFILE:
            packet = _hierarchical_packet(
                target, span_id, index.records_by_id, links, run_name, document_context_index,
                local_paragraphs_before, local_paragraphs_after, section_chunk_max_characters,
                maximum_total_links,
            )
        elif context_profile == ORDERED_SOURCE_PROFILE:
            packet = _ordered_packet(
                target, span_id, index.records_by_id, links, run_name, source_ledger,
                maximum_total_links,
            )
        else:
            raise ValueError(f"unknown context profile: {context_profile}")
        validate_no_cross_paper_links(packet)
        packets.append(packet)
    return packets


def _legacy_packet(
    target: dict[str, Any], span_id: str, index: Any, links: dict[str, Any], run_name: str,
    adjacent_before: int, adjacent_after: int, same_section_maximum: int,
) -> dict[str, Any]:
    packet_links = {field: links[role] for role, field in LINK_PACKET_FIELDS.items()}
    missing, sufficient, confidence = _legacy_context_sufficiency(target, packet_links)
    warnings = [*target.get("span_identity_warnings", []), *links["warnings"]]
    if bool(target.get("reaction_family_conflict")):
        warnings.append("target_reaction_family_conflict")
    return {
        "context_packet_schema_version": LEGACY_CONTEXT_PACKET_SCHEMA_VERSION,
        "context_packet_id": _packet_id(run_name, target), "run_name": run_name,
        "paper_id": str(target.get("paper_id") or ""),
        "paper_title": _first_value(target, "paper_title", "title"),
        "paper_abstract": _first_value(target, "paper_abstract", "abstract"),
        "paper_level_reaction_family": str(target.get("paper_level_reaction_family") or "unclear"),
        "paper_level_reaction_family_confidence": str(target.get("paper_level_reaction_family_confidence") or "unclear"),
        "target_span_id": span_id, "target_stable_span_uid": str(target.get("stable_span_uid") or ""),
        "target_span_order": target.get("span_order"), "target_text": str(target.get("source_text") or ""),
        "target_text_class": str(target.get("text_class") or "unknown"),
        "target_provenance_type": str(target.get("provenance_type") or "unknown"),
        "target_section_heading": str(target.get("section_heading") or ""),
        "target_section_path": target.get("section_path") or [],
        "target_reaction_family": str(target.get("reaction_family") or "unclear"),
        "target_span_boundary": str(target.get("maximum_supported_boundary") or "unsupported_or_secondary"),
        "target_admissibility_status": str(target.get("admissibility_status") or ""),
        "previous_spans": get_previous_spans(index, span_id, adjacent_before),
        "next_spans": get_next_spans(index, span_id, adjacent_after),
        "same_section_spans": get_same_section_spans(index, span_id, same_section_maximum),
        **packet_links, "context_sufficient": sufficient, "context_missing_types": missing,
        "context_confidence": confidence, "linking_signals": links["linking_signals"],
        "warnings": _dedupe(warnings),
    }


def _hierarchical_packet(
    target: dict[str, Any], span_id: str, records_by_id: dict[str, dict[str, Any]], links: dict[str, Any],
    run_name: str, document_index: DocumentContextIndex | None, local_before: int, local_after: int,
    section_max: int, maximum_total_links: int,
) -> dict[str, Any]:
    mapping = resolve_span_mapping(target, document_index) if document_index else _unresolved_target_mapping()
    document = resolve_document_for_span(target, document_index) if document_index else None
    local = get_local_paragraph_context(target, document_index, local_before, local_after) if document_index else {
        "previous_paragraphs": [], "target_paragraph": None, "next_paragraphs": []
    }
    section_chunk = get_section_chunk(target, document_index, section_max) if document_index else {
        "section_chunk": "", "section_chunk_start_offset": None, "section_chunk_end_offset": None
    }
    local_context = {**local, **section_chunk}
    evidence_items, role_index = _unique_evidence_items(links, records_by_id, document_index)
    classification, claim_support, purpose, missing, confidence = _context_sufficiency_v11(target, evidence_items)
    warnings = [
        *target.get("span_identity_warnings", []), *target.get("stable_span_uid_warnings", []),
        *target.get("location_warnings", []), *links.get("warnings", []), *mapping.get("warnings", []),
    ]
    if bool(target.get("reaction_family_conflict")):
        warnings.append("target_reaction_family_conflict")
    diagnostics = dict(links.get("diagnostics") or {})
    diagnostics.update({
        "unique_evidence_count": len(evidence_items),
        "role_assignment_count": sum(len(item["link_roles"]) for item in evidence_items),
        "duplicate_serialized_span_count": len(evidence_items) - len({item["span_id"] for item in evidence_items}),
        "multi_role_span_count": sum(len(item["link_roles"]) > 1 for item in evidence_items),
        "maximum_total_links": maximum_total_links,
    })
    return {
        "context_packet_schema_version": CONTEXT_PACKET_SCHEMA_VERSION,
        "context_profile": HIERARCHICAL_LINKING_PROFILE,
        "context_packet_id": _packet_id(run_name, target), "run_name": run_name,
        "paper_id": str(target.get("paper_id") or ""),
        "document_id": str(document.get("document_id") if document else target.get("document_id") or ""),
        "document_ref": str(document.get("relative_markdown_path") if document else ""),
        "document_body_sha256": str(document.get("body_text_sha256") if document else ""),
        "full_document_available": bool(document),
        "paper_title": _first_value(target, "paper_title", "title"),
        "paper_abstract": _first_value(target, "paper_abstract", "abstract"),
        "paper_level_reaction_family": str(target.get("paper_level_reaction_family") or "unclear"),
        "paper_level_reaction_family_confidence": str(target.get("paper_level_reaction_family_confidence") or "unclear"),
        "target_span_id": span_id, "target_stable_span_uid": str(target.get("stable_span_uid") or ""),
        "target_stable_span_uid_method": str(target.get("stable_span_uid_method") or ""),
        "target_text": str(target.get("source_text") or ""),
        "target_text_class": str(target.get("text_class") or "unknown"),
        "target_provenance_type": str(target.get("provenance_type") or "unknown"),
        "target_reaction_family": str(target.get("reaction_family") or "unclear"),
        "target_span_boundary": str(target.get("maximum_supported_boundary") or "unsupported_or_secondary"),
        "target_admissibility_status": str(target.get("admissibility_status") or ""),
        "target_mapping": mapping, "local_context": local_context, "evidence_items": evidence_items,
        "evidence_role_index": role_index,
        "classification_context_sufficient": classification,
        "claim_support_context_sufficient": claim_support,
        "context_purpose": purpose, "context_sufficient": claim_support,
        "context_missing_types": missing, "context_confidence": confidence,
        "linking_signals": links.get("linking_signals") or [], "linking_diagnostics": diagnostics,
        "warnings": _dedupe(warnings),
    }


def _ordered_packet(
    target: dict[str, Any], span_id: str, records_by_id: dict[str, dict[str, Any]],
    links: dict[str, Any], run_name: str, source_ledger: OrderedSourceLedger,
    maximum_total_links: int,
) -> dict[str, Any]:
    document_id = str(target.get("document_id") or "")
    document = source_ledger.documents_by_id.get(document_id, {})
    paragraph_uid = str(target.get("paragraph_uid") or "")
    paragraph = source_ledger.paragraphs_by_uid.get(paragraph_uid)
    previous_paragraph = source_ledger.paragraphs_by_uid.get(str(paragraph.get("previous_paragraph_uid") or "")) if paragraph else None
    next_paragraph = source_ledger.paragraphs_by_uid.get(str(paragraph.get("next_paragraph_uid") or "")) if paragraph else None
    section_uid = str(target.get("section_uid") or "")
    section = next(
        (item for item in source_ledger.sections_by_document.get(document_id, []) if item["section_uid"] == section_uid),
        None,
    )
    evidence_items, role_index = _unique_evidence_items(links, records_by_id, None)
    assessment = _packet_local_assessment(
        target, paragraph, previous_paragraph, next_paragraph, section, evidence_items
    )
    semantic_target = {**target, **assessment}
    target_primary_admissible = (
        assessment["applicable"]
        and assessment["target_is_primary_admissible"]
        and not assessment["target_is_secondary_or_context"]
        and not assessment["target_is_reject_or_low_trust"]
    )
    family_coverage_any, paper_observed_any, paper_missing_any, paper_status_any = _family_gate_coverage(
        semantic_target,
        evidence_items,
        previous_paragraph,
        paragraph,
        next_paragraph,
        applicable=assessment["base_applicable"],
    )
    family_coverage_primary, paper_observed_primary, paper_missing_primary, paper_status_primary = _family_gate_coverage(
        semantic_target,
        evidence_items,
        previous_paragraph,
        paragraph,
        next_paragraph,
        applicable=assessment["applicable"],
        primary_admissible_only=True,
        target_primary_admissible=target_primary_admissible,
    )
    diagnostics = dict(links.get("diagnostics") or {})
    diagnostics.update({
        "unique_evidence_count": len(evidence_items),
        "role_assignment_count": sum(len(item["link_roles"]) for item in evidence_items),
        "duplicate_serialized_span_count": len(evidence_items) - len({item["span_id"] for item in evidence_items}),
        "multi_role_span_count": sum(len(item["link_roles"]) > 1 for item in evidence_items),
        "maximum_total_links": maximum_total_links,
    })
    target_mapping = {
        "method": target.get("source_mapping_method") or "unresolved",
        "confidence": target.get("source_mapping_confidence") or "unresolved",
        "source_start_offset": target.get("verified_source_start_offset"),
        "source_end_offset": target.get("verified_source_end_offset"),
        "paragraph_id": target.get("paragraph_uid"),
        "section_heading": target.get("section_heading") or "",
        "section_path": target.get("section_path") or [],
        "direct_section_type": target.get("direct_section_type") or "unknown",
        "effective_section_type": target.get("effective_section_type") or target.get("section_type") or "unknown",
        "section_type_source": _section_type_source(target),
        "warnings": target.get("source_mapping_warnings") or [],
    }
    warnings = _dedupe([
        *(target.get("source_mapping_warnings") or []), *(target.get("span_identity_warnings") or []),
        *(target.get("stable_span_uid_warnings") or []), *(links.get("warnings") or []),
    ])
    return {
        "context_packet_schema_version": ORDERED_CONTEXT_PACKET_SCHEMA_VERSION,
        "context_profile": ORDERED_SOURCE_PROFILE,
        "context_packet_id": _packet_id(run_name, target), "run_name": run_name,
        "paper_id": str(target.get("paper_id") or ""), "document_id": document_id,
        "document_ref": str(document.get("document_ref") or ""),
        "document_body_sha256": str(document.get("document_body_sha256") or ""),
        "target_span_id": span_id, "target_stable_span_uid": str(target.get("stable_span_uid") or ""),
        "target_stable_span_uid_method": str(target.get("stable_span_uid_method") or ""),
        "target_source_locator": target.get("source_locator"),
        "target_source_order_key": target.get("source_order_key"),
        "target_section_uid": target.get("section_uid"),
        "target_section_outline_label": target.get("section_outline_label") or "",
        "target_section_heading": target.get("section_heading") or "",
        "target_raw_heading": target.get("raw_heading") or target.get("section_heading") or "",
        "target_direct_section_type": target.get("direct_section_type") or "unknown",
        "target_effective_section_type": target.get("effective_section_type") or target.get("section_type") or "unknown",
        "target_section_type_source": _section_type_source(target),
        "target_section_type": target.get("section_type") or "unknown",
        "target_paragraph_uid": target.get("paragraph_uid"),
        "target_paragraph_global_index": target.get("paragraph_global_index"),
        "target_paragraph_index_in_section": target.get("paragraph_index_in_section"),
        "target_document_relative_position": target.get("document_relative_position"),
        "target_section_relative_position": target.get("section_relative_position"),
        "target_source_start_offset": target.get("verified_source_start_offset"),
        "target_source_end_offset": target.get("verified_source_end_offset"),
        "target_text": str(target.get("source_text") or ""),
        "target_text_class": str(target.get("text_class") or "unknown"),
        "target_provenance_type": str(target.get("provenance_type") or "unknown"),
        "target_reaction_family": str(target.get("reaction_family") or "unclear"),
        "target_span_boundary": str(target.get("maximum_supported_boundary") or "unsupported_or_secondary"),
        "target_admissibility_status": str(target.get("admissibility_status") or ""),
        "target_claim_type": str(target.get("claim_type") or ""),
        "target_mapping": target_mapping,
        "legacy_reaction_family": assessment["legacy_reaction_family"],
        "document_reaction_family": assessment["document_reaction_family"],
        "document_reaction_family_confidence": assessment["document_reaction_family_confidence"],
        "document_reaction_family_signals": assessment["document_reaction_family_signals"],
        "document_reaction_family_conflict": assessment["document_reaction_family_conflict"],
        "effective_reaction_family": assessment["effective_reaction_family"],
        "effective_reaction_family_source": assessment["effective_reaction_family_source"],
        "reaction_family_correction": assessment["reaction_family_correction"],
        "document_target_reaction_family_conflict": assessment["document_target_reaction_family_conflict"],
        "target_explicit_reaction_family": assessment["target_explicit_reaction_family"],
        "target_explicit_reaction_family_signals": assessment["target_explicit_reaction_family_signals"],
        "semantic_eligibility_schema_version": assessment["semantic_eligibility_schema_version"],
        "document_genre": assessment["document_genre"],
        "document_genre_confidence": assessment["document_genre_confidence"],
        "document_genre_signals": assessment["document_genre_signals"],
        "document_genre_primary_applicable": assessment["document_genre_primary_applicable"],
        "span_claim_scope": assessment["span_claim_scope"],
        "span_claim_scope_confidence": assessment["span_claim_scope_confidence"],
        "span_claim_scope_signals": assessment["span_claim_scope_signals"],
        "span_claim_scope_primary_applicable": assessment["span_claim_scope_primary_applicable"],
        "document_scope": assessment["document_scope"],
        "document_scope_confidence": assessment["document_scope_confidence"],
        "document_scope_signals": assessment["document_scope_signals"],
        "document_scope_primary_applicable": assessment["document_scope_primary_applicable"],
        "claim_ownership": assessment["claim_ownership"],
        "claim_ownership_confidence": assessment["claim_ownership_confidence"],
        "claim_ownership_signals": assessment["claim_ownership_signals"],
        "claim_ownership_primary_applicable": assessment["claim_ownership_primary_applicable"],
        "semantic_claim_type": assessment["semantic_claim_type"],
        "semantic_claim_type_confidence": assessment["semantic_claim_type_confidence"],
        "semantic_claim_type_conflict": assessment["semantic_claim_type_conflict"],
        "legacy_claim_type": assessment["legacy_claim_type"],
        "semantic_claim_type_signals": assessment["semantic_claim_type_signals"],
        "performance_evidence_strength": assessment["performance_evidence_strength"],
        "performance_evidence_signals": assessment["performance_evidence_signals"],
        "performance_result_evidence": assessment["performance_result_evidence"],
        "quantitative_performance_evidence": assessment["quantitative_performance_evidence"],
        "ammonia_quantification_signal": assessment["ammonia_quantification_signal"],
        "gas_purification_trap_signal": assessment["gas_purification_trap_signal"],
        "mass_spectrometry_quantification_signal": assessment["mass_spectrometry_quantification_signal"],
        "enzymatic_quantification_signal": assessment["enzymatic_quantification_signal"],
        "primary_applicability_hard_gate_failures": assessment["hard_gate_failures"],
        "base_claim_support_applicable": assessment["base_applicable"],
        "primary_semantic_eligibility": assessment["applicable"],
        "target_is_primary_admissible": assessment["target_is_primary_admissible"],
        "target_is_secondary_or_context": assessment["target_is_secondary_or_context"],
        "target_is_reject_or_low_trust": assessment["target_is_reject_or_low_trust"],
        "previous_paragraph": _compact_paragraph(previous_paragraph),
        "target_paragraph": _compact_paragraph(paragraph),
        "next_paragraph": _compact_paragraph(next_paragraph),
        "section_context": _compact_section_context(section, source_ledger, document_id),
        "document_outline": [
            {"section_uid": item["section_uid"], "outline_label": item["outline_label"],
             "heading": item["heading_text"],
             "direct_section_type": item.get("direct_section_type") or "unknown",
             "effective_section_type": item.get("effective_section_type") or item["section_type"],
             "section_type_source": _section_type_source(item),
             "section_type": item["section_type"]}
            for item in source_ledger.sections_by_document.get(document_id, [])
        ],
        "evidence_items": evidence_items, "evidence_role_index": role_index,
        "classification_context_sufficient": assessment["classification_sufficient"],
        "claim_support_applicable": assessment["applicable"],
        "claim_support_context_sufficient": assessment["sufficient"],
        "packet_local_context_applicable": assessment["applicable"],
        "packet_local_context_sufficient": assessment["sufficient"],
        "packet_local_context_status": assessment["status"],
        "packet_local_missing_types": assessment["missing"],
        # Compatibility fields retain the pre-1.4 any-source observational meaning.
        "family_gate_coverage": family_coverage_any,
        "family_gate_coverage_any_source": family_coverage_any,
        "family_gate_coverage_primary_admissible": family_coverage_primary,
        "paper_gate_coverage_observed": paper_observed_any,
        "paper_gate_coverage_missing": paper_missing_any,
        "paper_gate_coverage_status": paper_status_any,
        "paper_gate_coverage_any_source_observed": paper_observed_any,
        "paper_gate_coverage_any_source_missing": paper_missing_any,
        "paper_gate_coverage_any_source_status": paper_status_any,
        "paper_gate_coverage_primary_admissible_observed": paper_observed_primary,
        "paper_gate_coverage_primary_admissible_missing": paper_missing_primary,
        "paper_gate_coverage_primary_admissible_status": paper_status_primary,
        "local_reaction_family_conflict": assessment["local_reaction_family_conflict"],
        "local_reaction_family_conflict_any_source": assessment["local_reaction_family_conflict_any_source"],
        "local_reaction_family_conflict_primary_admissible": assessment["local_reaction_family_conflict_primary_admissible"],
        "local_reaction_family_conflict_span_ids": assessment["local_reaction_family_conflict_span_ids"],
        "local_reaction_family_conflict_signals": assessment["local_reaction_family_conflict_signals"],
        "local_off_target_reaction_conflict": assessment["local_off_target_reaction_conflict"],
        "local_off_target_reaction_conflict_signals": assessment["local_off_target_reaction_conflict_signals"],
        "context_purpose": assessment["purpose"], "context_sufficient": assessment["sufficient"],
        "context_missing_types": assessment["missing"], "context_confidence": assessment["confidence"],
        "linking_signals": links.get("linking_signals") or [], "linking_diagnostics": diagnostics,
        "warnings": warnings,
    }


def _unique_evidence_items(
    links: dict[str, Any], records_by_id: dict[str, dict[str, Any]], document_index: DocumentContextIndex | None
) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    combined: dict[str, dict[str, Any]] = {}
    role_index: dict[str, list[str]] = {role: [] for role in LINK_TYPES}
    for role in LINK_TYPES:
        for linked in links.get(role) or []:
            span_id = str(linked.get("span_id") or "")
            if not span_id:
                continue
            original = records_by_id.get(span_id, {})
            semantic_record = {**original, **linked}
            semantic_record["source_text"] = str(linked.get("source_text") or original.get("source_text") or "")
            document_genre = assess_document_genre(semantic_record)
            document_scope = assess_document_scope(semantic_record)
            claim_ownership = assess_claim_ownership(semantic_record, document_scope)
            family_assessment = assess_effective_reaction_family(semantic_record)
            semantic_record.update({
                **document_genre,
                **document_scope,
                **claim_ownership,
                **family_assessment,
            })
            claim_typing = classify_claim_type(semantic_record)
            provenance_flags = _provenance_flags(original or semantic_record)
            provenance_primary = provenance_flags["is_primary_admissible"]
            off_target = _off_target_reaction_assessment(semantic_record)
            gate_source_primary = bool(
                linked.get("primary_support")
                and provenance_primary
                and not provenance_flags["is_secondary_or_context"]
                and not provenance_flags["is_reject_or_low_trust"]
                and document_genre["document_genre"] == PRIMARY_RESEARCH_GENRE
                and document_scope["span_claim_scope"] == TARGET_DOCUMENT_SCOPE
                and claim_ownership["claim_ownership_primary_applicable"]
                and not family_assessment["document_target_reaction_family_conflict"]
                and not linked.get("context_only")
                and not off_target["local_off_target_reaction_conflict"]
            )
            mapping = resolve_span_mapping(original, document_index) if document_index else {
                "confidence": original.get("source_mapping_confidence") or "unresolved"
            }
            item = combined.setdefault(span_id, {
                "span_id": span_id, "stable_span_uid": str(linked.get("stable_span_uid") or ""),
                "text": str(linked.get("source_text") or ""), "paper_id": str(linked.get("paper_id") or ""),
                "document_id": str(linked.get("document_id") or original.get("document_id") or ""),
                "source_start_offset": linked.get("source_start_offset"),
                "source_end_offset": linked.get("source_end_offset"),
                "verified_source_start_offset": linked.get("verified_source_start_offset"),
                "verified_source_end_offset": linked.get("verified_source_end_offset"),
                "source_locator": linked.get("source_locator"),
                "source_order_key": linked.get("source_order_key"),
                "paragraph_uid": linked.get("paragraph_uid"),
                "paragraph_global_index": linked.get("paragraph_global_index"),
                "paragraph_index_in_section": linked.get("paragraph_index_in_section"),
                "section_uid": linked.get("section_uid"),
                "section_outline_label": linked.get("section_outline_label"),
                "section_heading": str(linked.get("section_heading") or ""),
                "section_path": linked.get("section_path") or [],
                "provenance_type": str(linked.get("provenance_type") or "unknown"),
                "text_class": str(linked.get("text_class") or "unknown"),
                "reaction_family": str(linked.get("reaction_family") or "unclear"),
                "legacy_reaction_family": family_assessment["legacy_reaction_family"],
                "document_reaction_family": family_assessment["document_reaction_family"],
                "document_reaction_family_confidence": family_assessment["document_reaction_family_confidence"],
                "effective_reaction_family": family_assessment["effective_reaction_family"],
                "effective_reaction_family_source": family_assessment["effective_reaction_family_source"],
                "reaction_family_correction": family_assessment["reaction_family_correction"],
                "document_target_reaction_family_conflict": family_assessment["document_target_reaction_family_conflict"],
                "reaction_family_confidence": str(original.get("reaction_family_confidence") or "unclear"),
                "reaction_family_scope": str(original.get("reaction_family_scope") or "fallback"),
                "is_primary_admissible": provenance_primary,
                "is_secondary_or_context": provenance_flags["is_secondary_or_context"],
                "is_reject_or_low_trust": provenance_flags["is_reject_or_low_trust"],
                "document_genre": document_genre["document_genre"],
                "document_genre_primary_applicable": document_genre["document_genre_primary_applicable"],
                "span_claim_scope": document_scope["span_claim_scope"],
                "span_claim_scope_primary_applicable": document_scope["span_claim_scope_primary_applicable"],
                "document_scope": document_scope["document_scope"],
                "document_scope_primary_applicable": document_scope["document_scope_primary_applicable"],
                "claim_ownership": claim_ownership["claim_ownership"],
                "claim_ownership_primary_applicable": claim_ownership["claim_ownership_primary_applicable"],
                "semantic_claim_type": claim_typing["semantic_claim_type"],
                "semantic_claim_type_confidence": claim_typing["semantic_claim_type_confidence"],
                "performance_evidence_strength": claim_typing["performance_evidence_strength"],
                "performance_result_evidence": claim_typing["performance_result_evidence"],
                "quantitative_performance_evidence": claim_typing["quantitative_performance_evidence"],
                "validation_gates": _copy_value(original.get("validation_gates") or {}),
                "ammonia_quantification_signal": claim_typing["ammonia_quantification_signal"],
                "gas_purification_trap_signal": claim_typing["gas_purification_trap_signal"],
                "local_off_target_reaction_conflict": off_target["local_off_target_reaction_conflict"],
                "primary_admissible_gate_source": gate_source_primary,
                "link_roles": [], "normalized_link_score": 0.0, "linking_signals": [],
                "context_only": bool(linked.get("context_only")), "primary_support": False,
                "mapping_confidence": str(mapping.get("confidence") or "unresolved"),
            })
            item["link_roles"].append(role)
            item["normalized_link_score"] = max(float(item["normalized_link_score"]), float(linked.get("normalized_link_score") or 0.0))
            item["linking_signals"] = _dedupe([*item["linking_signals"], *(linked.get("linking_signals") or [])])
            item["context_only"] = bool(item["context_only"] or linked.get("context_only"))
            item["primary_support"] = bool(item["primary_support"] or linked.get("primary_support"))
            role_index[role].append(span_id)
    for item in combined.values():
        item["link_roles"] = [role for role in LINK_TYPES if role in item["link_roles"]]
        if item["context_only"]:
            item["primary_support"] = False
        item["primary_support"] = bool(
            item["primary_support"] and item.get("primary_admissible_gate_source")
        )
    if document_index is None:
        ordered_items = sorted(
            combined.values(),
            key=lambda item: (
                _sortable_offset(item.get("verified_source_start_offset"), item.get("source_start_offset")),
                _sortable_offset(item.get("verified_source_end_offset"), item.get("source_end_offset")),
                str(item.get("span_id") or ""),
            ),
        )
    else:
        ordered_items = [combined[key] for key in sorted(combined)]
    return ordered_items, {role: _dedupe(ids) for role, ids in role_index.items()}


def _context_sufficiency_v11(
    target: dict[str, Any], evidence_items: list[dict[str, Any]]
) -> tuple[bool, bool, str, list[str], str]:
    text = str(target.get("source_text") or "")
    provenance = str(target.get("provenance_type") or "unknown").casefold()
    text_class = str(target.get("text_class") or "unknown").casefold()
    classification = bool(text.strip() and provenance != "unknown" and text_class != "unknown")
    context_only = provenance in LOW_TRUST_PROVENANCE or text_class in LOW_TRUST_TEXT_CLASSES
    if context_only:
        return classification, False, "classification", [], "high" if classification else "low"
    primary = text_class in {"primary_performance", "primary_performance_with_validation"} or str(
        target.get("claim_type") or ""
    ) in {"performance_claim", "validation_claim", "reactor_claim", "process_claim"}
    if not primary:
        return classification, False, "classification", [], "medium" if classification else "low"
    family = normalize_reaction_family(str(target.get("reaction_family") or "unclear"))
    missing: list[str] = []
    if family in {"unclear", "mixed"} or bool(target.get("reaction_family_conflict")):
        missing.append("reaction_family")
    if not _contains_performance_metric(text, target):
        missing.append("performance_metric")
    positive_text = " ".join(
        [text, *[str(item.get("text") or "") for item in evidence_items if item.get("primary_support")]]
    )
    profile = get_reaction_profile(family)
    for gate in profile.get("product_admission_gates") or []:
        if not _family_gate_satisfied(str(gate), positive_text, target):
            missing.append(_missing_name(str(gate)))
    boundary = str(target.get("maximum_supported_boundary") or "unsupported_or_secondary")
    rank = BOUNDARY_RANK.get(boundary, 0)
    roles = {role for item in evidence_items if item.get("primary_support") for role in item.get("link_roles") or []}
    if rank >= BOUNDARY_RANK["reactor_legibility"] and "reactor" not in roles and not _reactor_signal(positive_text):
        missing.append("reactor_details")
    if rank >= BOUNDARY_RANK["process_partial"] and "process" not in roles and not _process_signal(positive_text):
        missing.append("process_boundary")
    if _negative_target(text) and "negative_or_contradicting" not in roles:
        missing.append("negative_evidence_resolution")
    missing = _dedupe(missing)
    claim_support = classification and not missing
    confidence = "high" if claim_support else ("medium" if classification and len(missing) <= 2 else "low")
    return classification, claim_support, "both", missing, confidence


def _family_gate_satisfied(gate: str, text: str, target: dict[str, Any]) -> bool:
    return bool(detect_validation_gate(gate, text, target)["satisfied"])


def _packet_local_assessment(
    target: dict[str, Any],
    target_paragraph: dict[str, Any] | None,
    previous_paragraph: dict[str, Any] | None,
    next_paragraph: dict[str, Any] | None,
    section: dict[str, Any] | None,
    evidence_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assess only evidence visible at the target and its local paragraph window."""

    text = str(target.get("source_text") or "")
    provenance = str(target.get("provenance_type") or "unknown").casefold()
    text_class = str(target.get("text_class") or "unknown").casefold()
    classification = bool(text.strip() and provenance != "unknown" and text_class != "unknown")
    base_applicable = _claim_support_applicable(target)
    document_genre = assess_document_genre(target)
    document_scope = assess_document_scope(target)
    claim_ownership = assess_claim_ownership(target, document_scope)
    family_assessment = assess_effective_reaction_family(target)
    semantic_target = {
        **target,
        **document_genre,
        **document_scope,
        **claim_ownership,
        **family_assessment,
    }
    claim_typing = classify_claim_type(semantic_target)
    provenance_flags = _provenance_flags(target)
    off_target = _off_target_reaction_assessment(semantic_target)
    preliminary_primary = bool(
        provenance_flags["is_primary_admissible"]
        and not provenance_flags["is_secondary_or_context"]
        and not provenance_flags["is_reject_or_low_trust"]
    )
    local_family = _local_reaction_family_assessment(
        semantic_target,
        evidence_items or [],
        [previous_paragraph, target_paragraph, next_paragraph],
        target_primary_admissible=preliminary_primary,
    )
    hard_gate_failures: list[str] = []
    if document_genre["document_genre"] != PRIMARY_RESEARCH_GENRE:
        hard_gate_failures.append("document_genre_not_primary_research")
    if document_scope["span_claim_scope"] != TARGET_DOCUMENT_SCOPE:
        hard_gate_failures.append("span_claim_scope_not_target_document")
    if not claim_ownership["claim_ownership_primary_applicable"]:
        hard_gate_failures.append("claim_not_owned_by_target_authors")
    if not provenance_flags["is_primary_admissible"]:
        hard_gate_failures.append("target_not_primary_admissible")
    if provenance_flags["is_secondary_or_context"]:
        hard_gate_failures.append("target_is_secondary_or_context")
    if provenance_flags["is_reject_or_low_trust"]:
        hard_gate_failures.append("target_is_reject_or_low_trust")
    if claim_typing["semantic_claim_type_confidence"] not in {"high", "medium"}:
        hard_gate_failures.append("semantic_claim_type_confidence_not_high_or_medium")
    if claim_typing["semantic_claim_type"] not in PRIMARY_SEMANTIC_CLAIM_TYPES:
        hard_gate_failures.append("semantic_claim_type_not_primary_eligible")
    if family_assessment["document_target_reaction_family_conflict"]:
        hard_gate_failures.append("document_target_reaction_family_conflict")
    if off_target["local_off_target_reaction_conflict"]:
        hard_gate_failures.append("local_off_target_reaction_conflict")
    hard_gate_failures = _dedupe(hard_gate_failures)
    applicable = not hard_gate_failures
    semantic = {
        **document_genre,
        **document_scope,
        **claim_ownership,
        **family_assessment,
        **claim_typing,
        **local_family,
        **off_target,
        "base_applicable": base_applicable,
        "hard_gate_failures": hard_gate_failures,
        "target_is_primary_admissible": provenance_flags["is_primary_admissible"],
        "target_is_secondary_or_context": provenance_flags["is_secondary_or_context"],
        "target_is_reject_or_low_trust": provenance_flags["is_reject_or_low_trust"],
    }
    if not applicable:
        return {
            **semantic,
            "classification_sufficient": classification,
            "applicable": False,
            "sufficient": False,
            "status": "not_applicable",
            "missing": [],
            "purpose": "classification",
            "confidence": "high" if classification else "low",
        }

    missing: list[str] = []
    mapping_method = str(target.get("source_mapping_method") or "unresolved")
    mapping_confidence = str(target.get("source_mapping_confidence") or "unresolved")
    if mapping_method == "unresolved" or mapping_confidence != "high" or not bool(target.get("offset_text_match")):
        missing.append("verified_target_mapping")

    raw_family = str(family_assessment.get("effective_reaction_family") or "").strip()
    family = normalize_reaction_family(raw_family)
    family_token = re.sub(r"[^a-z0-9]+", "_", raw_family.casefold()).strip("_")
    explicit_unclear = family == "unclear" and family_token in {
        "unclear", "unknown", "not_specified", "ambiguous"
    }
    if not raw_family or (family == "unclear" and not explicit_unclear):
        missing.append("reaction_family")
    if local_family["local_reaction_family_conflict_primary_admissible"]:
        missing.append("reaction_family_conflict")

    paragraphs = [previous_paragraph, target_paragraph, next_paragraph]
    local_text = " ".join(str(item.get("text") or "") for item in paragraphs if item)
    if not target_paragraph or not str(target_paragraph.get("text") or "").strip() or section is None:
        missing.append("readable_local_context")

    claim_type = str(claim_typing.get("semantic_claim_type") or "").casefold()
    if claim_type == "validation_claim":
        if _negative_target(text):
            missing.append("positive_validation_evidence")
    elif claim_type == "ammonia_quantification_claim":
        if not claim_typing["ammonia_quantification_signal"]:
            missing.append("ammonia_quantification_signal")
    elif claim_type == "reactor_claim":
        if not _reactor_signal(local_text):
            missing.append("reactor_signal")
    elif claim_type == "process_claim":
        if not _process_signal(local_text):
            missing.append("process_signal")
    elif claim_type == "performance_result_claim":
        if not claim_typing["performance_result_evidence"]:
            missing.append("quantitative_or_comparative_performance_result")

    missing = _dedupe(missing)
    sufficient = classification and not missing
    return {
        **semantic,
        "classification_sufficient": classification,
        "applicable": True,
        "sufficient": sufficient,
        "status": "sufficient" if sufficient else "insufficient",
        "missing": missing,
        "purpose": "both",
        "confidence": "high" if sufficient else ("medium" if classification and len(missing) <= 2 else "low"),
    }


def _local_reaction_family_assessment(
    target: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    paragraphs: list[dict[str, Any] | None],
    *,
    target_primary_admissible: bool,
) -> dict[str, Any]:
    """Detect family disagreements only within the packet's local evidence window."""

    target_family = normalize_reaction_family(str(
        target.get("effective_reaction_family") or target.get("reaction_family") or "unclear"
    ))
    any_conflict = False
    primary_conflict = False
    conflict_span_ids: list[str] = []
    signals: list[str] = []
    if target_family in {"unclear", "mixed"}:
        return {
            "local_reaction_family_conflict": False,
            "local_reaction_family_conflict_any_source": False,
            "local_reaction_family_conflict_primary_admissible": False,
            "local_reaction_family_conflict_span_ids": [],
            "local_reaction_family_conflict_signals": [],
        }

    recorded_signals = [str(value) for value in target.get("reaction_family_signals") or []]
    recorded_scope = str(target.get("reaction_family_scope") or "fallback")
    locally_recorded_conflict = (
        bool(target.get("reaction_family_conflict"))
        and recorded_scope != "paper_consensus"
        and (
        not recorded_signals
        or any(
            value.startswith("reaction_family_conflict:")
            and not value.startswith("paper_reaction_family_conflict:")
            and not value.startswith("paper_consensus_conflict:")
            for value in recorded_signals
        )
        )
    )
    if locally_recorded_conflict:
        any_conflict = True
        primary_conflict = target_primary_admissible
        target_id = _span_id(target)
        if target_id:
            conflict_span_ids.append(target_id)
        signals.append("target_explicit_local_reaction_family_conflict")

    target_inferred = _conflicting_inferred_family(str(target.get("source_text") or ""), target_family)
    if target_inferred:
        any_conflict = True
        primary_conflict = primary_conflict or target_primary_admissible
        target_id = _span_id(target)
        if target_id:
            conflict_span_ids.append(target_id)
        signals.append(f"target_text_family_conflict:{target_family}_vs_{target_inferred}")

    paragraph_ids = {str(item.get("paragraph_uid") or "") for item in paragraphs if item}
    for paragraph in paragraphs:
        if not paragraph:
            continue
        inferred = _conflicting_inferred_family(str(paragraph.get("text") or ""), target_family)
        if inferred:
            any_conflict = True
            locator = str(paragraph.get("source_locator") or paragraph.get("paragraph_uid") or "unknown")
            signals.append(f"local_paragraph_family_conflict:{locator}:{target_family}_vs_{inferred}")

    for item in evidence_items:
        paragraph_uid = str(item.get("paragraph_uid") or "")
        if paragraph_ids and paragraph_uid not in paragraph_ids:
            continue
        item_family = normalize_reaction_family(str(
            item.get("effective_reaction_family") or item.get("reaction_family") or "unclear"
        ))
        explicit_mismatch = (
            item_family not in {"unclear", "mixed"}
            and item_family != target_family
            and str(item.get("reaction_family_scope") or "") in {"explicit_span", "section_context"}
            and str(item.get("reaction_family_confidence") or "") in {"high", "medium"}
        )
        inferred = _conflicting_inferred_family(str(item.get("text") or ""), target_family)
        conflict_family = item_family if explicit_mismatch else inferred
        if not conflict_family:
            continue
        any_conflict = True
        span_id = str(item.get("span_id") or "")
        if span_id:
            conflict_span_ids.append(span_id)
        if bool(item.get("primary_admissible_gate_source")):
            primary_conflict = True
        signals.append(f"local_evidence_family_conflict:{span_id or 'unknown'}:{target_family}_vs_{conflict_family}")

    return {
        "local_reaction_family_conflict": primary_conflict,
        "local_reaction_family_conflict_any_source": any_conflict,
        "local_reaction_family_conflict_primary_admissible": primary_conflict,
        "local_reaction_family_conflict_span_ids": _dedupe(conflict_span_ids),
        "local_reaction_family_conflict_signals": _dedupe(signals),
    }


def _provenance_flags(record: dict[str, Any]) -> dict[str, bool]:
    provenance = str(record.get("provenance_type") or "unknown").casefold()
    text_class = str(record.get("text_class") or "unknown").casefold()
    admissibility = str(record.get("admissibility_status") or "").casefold()
    low_trust_context = provenance in LOW_TRUST_PROVENANCE or text_class in LOW_TRUST_TEXT_CLASSES
    if "is_secondary_or_context" in record:
        secondary = bool(record.get("is_secondary_or_context"))
    else:
        secondary = low_trust_context or any(token in admissibility for token in ("secondary", "context_only"))
    if "is_reject_or_low_trust" in record:
        reject = bool(record.get("is_reject_or_low_trust"))
    else:
        reject = (
            provenance in {"reference", "bibliography", "front_matter", "metadata", "copyright_note"}
            or any(token in admissibility for token in ("reject", "low_trust"))
        )
    if "is_primary_admissible" in record:
        primary = bool(record.get("is_primary_admissible"))
    else:
        primary = not secondary and not reject and provenance in {
            "abstract", "body", "methods", "results", "discussion", "supplementary", "protocol",
        }
    return {
        "is_primary_admissible": primary,
        "is_secondary_or_context": secondary,
        "is_reject_or_low_trust": reject,
    }


def _off_target_reaction_assessment(record: dict[str, Any]) -> dict[str, Any]:
    explicit = bool(record.get("local_off_target_reaction_conflict"))
    text = str(record.get("source_text") or record.get("target_text") or "")
    family = normalize_reaction_family(str(
        record.get("effective_reaction_family") or record.get("reaction_family") or "unclear"
    ))
    signals = [str(value) for value in record.get("local_off_target_reaction_conflict_signals") or []]
    hits = [name for name, pattern in _OFF_TARGET_REACTION_PATTERNS if pattern.search(text)]
    inferred = bool(family in AMMONIA_REACTION_FAMILIES and hits and not _AMMONIA_REACTION_SUBJECT.search(text))
    if inferred:
        signals.extend(f"off_target_system:{name}" for name in hits)
        signals.append(f"ammonia_family_without_ammonia_subject:{family}")
    if explicit and not signals:
        signals.append("explicit_local_off_target_reaction_conflict")
    return {
        "local_off_target_reaction_conflict": bool(explicit or inferred),
        "local_off_target_reaction_conflict_signals": _dedupe(signals),
    }


def _conflicting_inferred_family(text: str, target_family: str) -> str:
    if not str(text or "").strip():
        return ""
    inferred = infer_reaction_family_detailed(text=str(text))
    family = normalize_reaction_family(str(inferred.get("reaction_family") or "unclear"))
    confidence = str(inferred.get("reaction_family_confidence") or "unclear")
    if family not in {"unclear", "mixed", target_family} and confidence in {"high", "medium"}:
        return family
    return ""


def _family_gate_coverage(
    target: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    previous_paragraph: dict[str, Any] | None,
    target_paragraph: dict[str, Any] | None,
    next_paragraph: dict[str, Any] | None,
    *,
    applicable: bool,
    primary_admissible_only: bool = False,
    target_primary_admissible: bool = False,
) -> tuple[dict[str, dict[str, Any]], list[str], list[str], str]:
    """Return any-source or primary-admissible observational gate coverage."""

    family = normalize_reaction_family(str(
        target.get("effective_reaction_family") or target.get("reaction_family") or "unclear"
    ))
    gates = [str(gate) for gate in get_reaction_profile(family).get("product_admission_gates") or []]
    coverage: dict[str, dict[str, Any]] = {}
    source_eligibility = "primary_admissible" if primary_admissible_only else "any_source"
    if not applicable:
        for gate in gates:
            coverage[gate] = {
                "status": "not_applicable", "supporting_span_ids": [],
                "source_eligibility": source_eligibility,
                "gate_detection_source": "", "gate_conflict": False,
                "gate_detection_signals": [],
            }
        return coverage, [], [], "not_evaluated"

    target_text = str(target.get("source_text") or target.get("target_text") or "")
    local_paragraphs = [previous_paragraph, target_paragraph, next_paragraph]
    local_text = " ".join(str(item.get("text") or "") for item in local_paragraphs if item)
    target_id = _span_id(target)
    paragraph_ids = {str(item.get("paragraph_uid") or "") for item in local_paragraphs if item}
    eligible_items = [
        item for item in evidence_items
        if not primary_admissible_only or bool(item.get("primary_admissible_gate_source"))
    ]
    observed: list[str] = []
    missing: list[str] = []
    for gate in gates:
        status = "missing"
        supporting_ids: list[str] = []
        detection = {"gate_detection_source": "", "gate_conflict": False, "gate_detection_signals": []}
        target_eligible = not primary_admissible_only or target_primary_admissible
        target_detection = detect_validation_gate(
            gate, target_text, target, text_source="target_text"
        ) if target_eligible else {"satisfied": False, **detection}
        if target_detection["gate_conflict"]:
            status = "conflict_in_target"
            supporting_ids = [target_id] if target_id else []
            detection = target_detection
        elif target_detection["satisfied"]:
            status = "observed_in_target"
            supporting_ids = [target_id] if target_id else []
            detection = target_detection
        else:
            local_detection = detect_validation_gate(
                gate, local_text, {}, text_source="local_text"
            ) if not primary_admissible_only else {"satisfied": False, **detection}
            if local_detection["satisfied"]:
                status = "observed_in_local_context"
                supporting_ids = _supporting_local_span_ids(gate, evidence_items, local_paragraphs)
                detection = local_detection
            else:
                linked_detections = [
                    (
                        item,
                        detect_validation_gate(
                            gate,
                            str(item.get("text") or ""),
                            item,
                            text_source="linked_primary_evidence",
                        ),
                    )
                    for item in eligible_items
                ]
                linked_conflicts = [(item, result) for item, result in linked_detections if result["gate_conflict"]]
                linked_matches = [(item, result) for item, result in linked_detections if result["satisfied"]]
                if linked_conflicts:
                    status = "conflict_in_linked_evidence"
                    supporting_ids = _dedupe([str(item.get("span_id") or "") for item, _ in linked_conflicts])
                    detection = linked_conflicts[0][1]
                elif linked_matches:
                    local_matches = [
                        (item, result) for item, result in linked_matches
                        if str(item.get("paragraph_uid") or "") in paragraph_ids
                    ]
                    selected = local_matches or linked_matches
                    status = "observed_in_local_context" if local_matches else "observed_in_linked_evidence"
                    supporting_ids = _dedupe([str(item.get("span_id") or "") for item, _ in selected])
                    detection = selected[0][1]
        coverage[gate] = {
            "status": status,
            "supporting_span_ids": supporting_ids,
            "source_eligibility": source_eligibility,
            "gate_detection_source": detection["gate_detection_source"],
            "gate_conflict": detection["gate_conflict"],
            "gate_detection_signals": detection["gate_detection_signals"],
        }
        (observed if status.startswith("observed_in_") else missing).append(gate)
    status = "apparently_complete_in_packet" if not missing else "partial_observed"
    return coverage, observed, missing, status


def _supporting_local_span_ids(
    gate: str, evidence_items: list[dict[str, Any]], paragraphs: list[dict[str, Any] | None]
) -> list[str]:
    paragraph_ids = {str(item.get("paragraph_uid") or "") for item in paragraphs if item}
    return _dedupe([
        str(item.get("span_id") or "")
        for item in evidence_items
        if str(item.get("paragraph_uid") or "") in paragraph_ids
        and detect_validation_gate(
            gate, str(item.get("text") or ""), item, text_source="local_text"
        )["satisfied"]
    ])


def _target_primary_gate_nonprimary_support_count(packets: list[dict[str, Any]]) -> int:
    """Count primary-gate support references that violate source eligibility."""

    invalid: set[tuple[str, str, str]] = set()
    for packet in packets:
        packet_id = str(packet.get("context_packet_id") or packet.get("target_span_id") or "")
        target_id = str(packet.get("target_span_id") or "")
        items = {
            str(item.get("span_id") or ""): item
            for item in packet.get("evidence_items") or []
            if str(item.get("span_id") or "")
        }
        for gate, gate_result in (packet.get("family_gate_coverage_primary_admissible") or {}).items():
            status = str((gate_result or {}).get("status") or "")
            if not status.startswith("observed_in_"):
                continue
            for source_id in (gate_result or {}).get("supporting_span_ids") or []:
                source_id = str(source_id or "")
                eligible = (
                    _packet_primary_gate_target_eligible(packet)
                    if source_id == target_id
                    else _evidence_primary_gate_source_eligible(items.get(source_id, {}))
                )
                if not eligible:
                    invalid.add((packet_id, str(gate), source_id or "missing_source_id"))
    return len(invalid)


def _packet_primary_gate_target_eligible(packet: dict[str, Any]) -> bool:
    return bool(
        packet.get("primary_semantic_eligibility")
        and packet.get("target_is_primary_admissible")
        and not packet.get("target_is_secondary_or_context")
        and not packet.get("target_is_reject_or_low_trust")
        and str(packet.get("document_genre") or "") == PRIMARY_RESEARCH_GENRE
        and str(packet.get("span_claim_scope") or packet.get("document_scope") or "") == TARGET_DOCUMENT_SCOPE
        and str(packet.get("claim_ownership") or "") == "target_authors"
        and not packet.get("document_target_reaction_family_conflict")
        and not packet.get("local_off_target_reaction_conflict")
    )


def _evidence_primary_gate_source_eligible(item: dict[str, Any]) -> bool:
    return bool(
        item.get("primary_support")
        and item.get("primary_admissible_gate_source")
        and item.get("is_primary_admissible")
        and not item.get("is_secondary_or_context")
        and not item.get("is_reject_or_low_trust")
        and str(item.get("document_genre") or "") == PRIMARY_RESEARCH_GENRE
        and str(item.get("span_claim_scope") or item.get("document_scope") or "") == TARGET_DOCUMENT_SCOPE
        and str(item.get("claim_ownership") or "") == "target_authors"
        and not item.get("document_target_reaction_family_conflict")
        and not item.get("local_off_target_reaction_conflict")
    )


def _explicit_validation_role(target: dict[str, Any]) -> bool:
    if str(target.get("claim_type") or "").casefold() == "validation_claim":
        return True
    if "validation" in str(target.get("text_class") or "").casefold():
        return True
    if str(target.get("validation_role") or "").strip():
        return True
    gates = target.get("validation_gates") if isinstance(target.get("validation_gates"), dict) else {}
    return any(str(value or "").casefold() in {"yes", "explicit", "pass", "present"} for value in gates.values())


def _section_type_source(record: dict[str, Any]) -> str:
    direct = str(record.get("direct_section_type") or "unknown")
    effective = str(record.get("effective_section_type") or record.get("section_type") or "unknown")
    if direct != "unknown":
        return "direct"
    if effective != "unknown" and (record.get("inherited_section_type") or record.get("inherited_from_section_uid")):
        return "inherited"
    return "unknown"


def summarize_context_packets(
    packets: list[dict[str, Any]], run_name: str, *, legacy_keyword_linking_comparison: dict[str, Any] | None = None
) -> dict[str, Any]:
    if not packets or str(packets[0].get("context_packet_schema_version")) == LEGACY_CONTEXT_PACKET_SCHEMA_VERSION:
        return _legacy_summary(packets, run_name)
    missing = Counter()
    role_distribution = Counter()
    mapping_methods = Counter()
    mapping_confidence = Counter()
    stable_methods = Counter()
    unique_counts: list[int] = []
    diagnostics = Counter()
    paper_ids: set[str] = set()
    low_trust = Counter()
    duplicate_serialized = 0
    hint_overlap = 0
    family_missing: dict[str, Counter[str]] = defaultdict(Counter)
    packet_local_status = Counter()
    paper_gate_status = Counter()
    paper_gate_primary_status = Counter()
    document_genre_span_distribution = Counter()
    document_genres_by_id: dict[str, set[str]] = defaultdict(set)
    document_reaction_families_by_id: dict[str, set[str]] = defaultdict(set)
    effective_reaction_family_distribution = Counter()
    span_claim_scope_distribution = Counter()
    document_scope_distribution = Counter()
    claim_ownership_distribution = Counter()
    semantic_claim_type_distribution = Counter()
    hard_gate_failures = Counter()
    for packet in packets:
        paper_ids.add(str(packet.get("paper_id") or ""))
        missing_types = packet.get("context_missing_types") or []
        missing.update(missing_types)
        family = normalize_reaction_family(str(
            packet.get("effective_reaction_family") or packet.get("target_reaction_family") or "unclear"
        ))
        family_missing[family].update(missing_types)
        effective_reaction_family_distribution[family] += 1
        packet_local_status[str(packet.get("packet_local_context_status") or "not_reported")] += 1
        paper_gate_status[str(packet.get("paper_gate_coverage_status") or "not_reported")] += 1
        paper_gate_primary_status[str(
            packet.get("paper_gate_coverage_primary_admissible_status") or "not_reported"
        )] += 1
        document_genre = str(packet.get("document_genre") or "not_reported")
        document_genre_span_distribution[document_genre] += 1
        document_id = str(packet.get("document_id") or packet.get("paper_id") or "")
        if document_id:
            document_genres_by_id[document_id].add(document_genre)
            document_reaction_families_by_id[document_id].add(normalize_reaction_family(str(
                packet.get("document_reaction_family") or "unclear"
            )))
        span_claim_scope_distribution[str(
            packet.get("span_claim_scope") or packet.get("document_scope") or "not_reported"
        )] += 1
        document_scope_distribution[str(packet.get("document_scope") or "not_reported")] += 1
        claim_ownership_distribution[str(packet.get("claim_ownership") or "not_reported")] += 1
        semantic_claim_type_distribution[str(packet.get("semantic_claim_type") or "not_reported")] += 1
        hard_gate_failures.update(packet.get("primary_applicability_hard_gate_failures") or [])
        mapping = packet.get("target_mapping") or {}
        mapping_methods[str(mapping.get("method") or "unresolved")] += 1
        mapping_confidence[str(mapping.get("confidence") or "unresolved")] += 1
        stable_methods[str(packet.get("target_stable_span_uid_method") or "unknown")] += 1
        items = packet.get("evidence_items") or []
        ids = [str(item.get("span_id") or "") for item in items]
        unique_counts.append(len(set(ids)))
        duplicate_serialized += len(ids) - len(set(ids))
        for item in items:
            for role in item.get("link_roles") or []:
                role_distribution[str(role)] += 1
            provenance = str(item.get("provenance_type") or "").casefold()
            text_class = str(item.get("text_class") or "").casefold()
            if item.get("primary_support"):
                if provenance in {"reference", "bibliography"} or text_class == "reference_list": low_trust["reference"] += 1
                if provenance == "figure_caption" or text_class == "figure_caption": low_trust["figure_caption"] += 1
                if provenance == "scheme_caption" or text_class == "scheme_caption": low_trust["scheme_caption"] += 1
                if provenance == "review_table" or text_class == "review_table": low_trust["review_table"] += 1
            if "context_hint" in (item.get("link_roles") or []) and item.get("primary_support"):
                hint_overlap += 1
        diagnostics.update(packet.get("linking_diagnostics") or {})
    packet_count = len(packets)
    profile_name = str(packets[0].get("context_profile") or HIERARCHICAL_LINKING_PROFILE) if packets else HIERARCHICAL_LINKING_PROFILE
    applicability_enabled = profile_name == ORDERED_SOURCE_PROFILE
    applicable_packets = (
        [packet for packet in packets if bool(packet.get("claim_support_applicable"))]
        if applicability_enabled else packets
    )
    applicable_sufficient = sum(bool(packet.get("claim_support_context_sufficient")) for packet in applicable_packets)
    role_total = sum(role_distribution.values())
    unique_total = sum(unique_counts)
    document_genre_inconsistent_document_count = sum(
        len(genres) > 1 for genres in document_genres_by_id.values()
    )
    document_genre_by_id = {
        document_id: sorted(genres)[0]
        for document_id, genres in document_genres_by_id.items()
        if genres
    }
    document_reaction_family_by_id = {
        document_id: (sorted(families)[0] if len(families) == 1 else "mixed")
        for document_id, families in document_reaction_families_by_id.items()
        if families
    }
    conflict_packets = [packet for packet in packets if bool(packet.get("semantic_claim_type_conflict"))]
    conflict_matrix: dict[str, Counter[str]] = defaultdict(Counter)
    for packet in conflict_packets:
        legacy = str(packet.get("legacy_claim_type") or "untyped_claim")
        semantic = str(packet.get("semantic_claim_type") or "untyped_claim")
        conflict_matrix[legacy][semantic] += 1
    conflict_by_genre = Counter(str(packet.get("document_genre") or "not_reported") for packet in conflict_packets)
    conflict_by_family = Counter(
        normalize_reaction_family(str(
            packet.get("effective_reaction_family") or packet.get("target_reaction_family") or "unclear"
        ))
        for packet in conflict_packets
    )
    primary_packets = [packet for packet in packets if bool(packet.get("primary_semantic_eligibility"))]
    primary_by_genre = Counter(str(packet.get("document_genre") or "not_reported") for packet in primary_packets)
    primary_by_semantic_type = Counter(
        str(packet.get("semantic_claim_type") or "untyped_claim") for packet in primary_packets
    )
    for claim_type in {
        *PRIMARY_SEMANTIC_CLAIM_TYPES,
        "performance_context_claim", "mechanism_claim", "protocol_claim", "secondary_context_claim",
        "gas_purification_or_capture_claim", "untyped_claim",
    }:
        primary_by_semantic_type.setdefault(claim_type, 0)
    primary_by_family = Counter(
        normalize_reaction_family(str(packet.get("target_reaction_family") or "unclear"))
        for packet in primary_packets
    )
    primary_by_effective_family = Counter(
        normalize_reaction_family(str(
            packet.get("effective_reaction_family") or packet.get("target_reaction_family") or "unclear"
        ))
        for packet in primary_packets
    )
    primary_by_provenance = Counter(
        str(packet.get("target_provenance_type") or "unknown") for packet in primary_packets
    )
    primary_by_ownership_confidence = Counter(
        str(packet.get("claim_ownership_confidence") or "unknown") for packet in primary_packets
    )
    primary_by_semantic_confidence = Counter(
        str(packet.get("semantic_claim_type_confidence") or "unknown") for packet in primary_packets
    )
    summary = {
        "run_name": run_name, "context_profile": profile_name,
        "packet_count": packet_count, "paper_count": len(paper_ids),
        "classification_context_sufficient_count": sum(bool(p.get("classification_context_sufficient")) for p in packets),
        "classification_context_insufficient_count": sum(not bool(p.get("classification_context_sufficient")) for p in packets),
        "claim_support_context_sufficient_count": sum(bool(p.get("claim_support_context_sufficient")) for p in packets),
        "claim_support_context_insufficient_count": len(applicable_packets) - applicable_sufficient,
        "claim_support_applicable_count": len(applicable_packets),
        "claim_support_not_applicable_count": packet_count - len(applicable_packets) if applicability_enabled else 0,
        "claim_support_sufficient_among_applicable": applicable_sufficient,
        "claim_support_insufficient_among_applicable": len(applicable_packets) - applicable_sufficient,
        "claim_support_rate_among_applicable": round(applicable_sufficient / len(applicable_packets), 6) if applicable_packets else 0.0,
        "packet_local_applicable_count": packet_local_status["sufficient"] + packet_local_status["insufficient"],
        "packet_local_sufficient_count": packet_local_status["sufficient"],
        "packet_local_insufficient_count": packet_local_status["insufficient"],
        "packet_local_not_applicable_count": packet_local_status["not_applicable"],
        "packet_local_sufficiency_rate": round(
            packet_local_status["sufficient"]
            / (packet_local_status["sufficient"] + packet_local_status["insufficient"]), 6
        ) if packet_local_status["sufficient"] + packet_local_status["insufficient"] else 0.0,
        "packet_local_status_distribution": dict(sorted(packet_local_status.items())),
        "packet_local_missing_reason_distribution": dict(sorted(missing.items())),
        "paper_gate_coverage_apparently_complete_count": paper_gate_status["apparently_complete_in_packet"],
        "paper_gate_coverage_partial_count": paper_gate_status["partial_observed"],
        "paper_gate_coverage_not_evaluated_count": paper_gate_status["not_evaluated"],
        "paper_gate_coverage_status_distribution": dict(sorted(paper_gate_status.items())),
        "paper_gate_primary_admissible_apparently_complete_count": paper_gate_primary_status["apparently_complete_in_packet"],
        "paper_gate_primary_admissible_partial_count": paper_gate_primary_status["partial_observed"],
        "paper_gate_primary_admissible_not_evaluated_count": paper_gate_primary_status["not_evaluated"],
        "paper_gate_primary_admissible_status_distribution": dict(sorted(paper_gate_primary_status.items())),
        "document_genre_distribution": dict(sorted(Counter(document_genre_by_id.values()).items())),
        "document_reaction_family_distribution": dict(sorted(
            Counter(document_reaction_family_by_id.values()).items()
        )),
        "effective_reaction_family_distribution": dict(sorted(effective_reaction_family_distribution.items())),
        "reaction_family_correction_count": sum(bool(packet.get("reaction_family_correction")) for packet in packets),
        "document_target_family_conflict_count": sum(
            bool(packet.get("document_target_reaction_family_conflict")) for packet in packets
        ),
        "document_genre_inconsistent_document_count": document_genre_inconsistent_document_count,
        "document_genre_span_distribution": dict(sorted(document_genre_span_distribution.items())),
        "span_claim_scope_distribution": dict(sorted(span_claim_scope_distribution.items())),
        "document_scope_distribution": dict(sorted(document_scope_distribution.items())),
        "claim_ownership_distribution": dict(sorted(claim_ownership_distribution.items())),
        "semantic_claim_type_distribution": dict(sorted(semantic_claim_type_distribution.items())),
        "semantic_claim_type_conflict_count": len(conflict_packets),
        "semantic_claim_type_conflict_matrix": {
            legacy: dict(sorted(transitions.items()))
            for legacy, transitions in sorted(conflict_matrix.items())
        },
        "semantic_claim_type_conflict_by_document_genre": dict(sorted(conflict_by_genre.items())),
        "semantic_claim_type_conflict_by_reaction_family": dict(sorted(conflict_by_family.items())),
        "semantic_claim_type_conflict_primary_eligible_count": sum(
            bool(packet.get("primary_semantic_eligibility")) for packet in conflict_packets
        ),
        "semantic_claim_type_conflict_not_applicable_count": sum(
            str(packet.get("packet_local_context_status") or "") == "not_applicable"
            for packet in conflict_packets
        ),
        "primary_semantic_eligibility_count": len(primary_packets),
        "primary_semantic_eligible_by_document_genre": dict(sorted(primary_by_genre.items())),
        "primary_semantic_eligible_by_semantic_claim_type": dict(sorted(primary_by_semantic_type.items())),
        "primary_semantic_eligible_by_reaction_family": dict(sorted(primary_by_family.items())),
        "primary_eligible_by_effective_family": dict(sorted(primary_by_effective_family.items())),
        "primary_eligible_unclear_family_count": primary_by_effective_family["unclear"],
        "primary_semantic_eligible_by_provenance_type": dict(sorted(primary_by_provenance.items())),
        "primary_semantic_eligible_by_ownership_confidence": dict(
            sorted(primary_by_ownership_confidence.items())
        ),
        "primary_semantic_eligible_by_semantic_type_confidence": dict(
            sorted(primary_by_semantic_confidence.items())
        ),
        "review_primary_semantic_eligible_count": primary_by_genre["review"],
        "perspective_primary_semantic_eligible_count": primary_by_genre["perspective"],
        "mixed_primary_semantic_eligible_count": primary_by_genre["mixed"],
        "unclear_genre_primary_semantic_eligible_count": primary_by_genre["unclear"],
        "off_target_primary_semantic_eligible_count": sum(
            bool(packet.get("local_off_target_reaction_conflict")) for packet in primary_packets
        ),
        "non_primary_provenance_primary_semantic_eligible_count": sum(
            not bool(packet.get("target_is_primary_admissible")) for packet in primary_packets
        ),
        "secondary_context_primary_semantic_eligible_count": sum(
            bool(packet.get("target_is_secondary_or_context")) for packet in primary_packets
        ),
        "reject_or_low_trust_primary_semantic_eligible_count": sum(
            bool(packet.get("target_is_reject_or_low_trust")) for packet in primary_packets
        ),
        "hard_gate_failure_distribution": dict(sorted(hard_gate_failures.items())),
        "primary_applicability_hard_gate_failure_distribution": dict(sorted(hard_gate_failures.items())),
        "off_target_reaction_conflict_count": sum(
            bool(packet.get("local_off_target_reaction_conflict")) for packet in packets
        ),
        "review_removed_from_primary_count": sum(
            str(packet.get("document_genre") or "") == "review"
            and not bool(packet.get("primary_semantic_eligibility"))
            for packet in packets
        ),
        "perspective_removed_from_primary_count": sum(
            str(packet.get("document_genre") or "") == "perspective"
            and not bool(packet.get("primary_semantic_eligibility"))
            for packet in packets
        ),
        "external_attribution_removed_count": sum(
            (
                str(packet.get("span_claim_scope") or packet.get("document_scope") or "")
                == "external_or_cited_work"
                or str(packet.get("claim_ownership") or "") == "external_or_cited_authors"
            )
            and not bool(packet.get("primary_semantic_eligibility"))
            for packet in packets
        ),
        "target_primary_gate_complete_count": paper_gate_primary_status["apparently_complete_in_packet"],
        "any_source_gate_complete_count": paper_gate_status["apparently_complete_in_packet"],
        "target_primary_gate_supported_by_nonprimary_count": _target_primary_gate_nonprimary_support_count(packets),
        "local_reaction_family_conflict_any_source_count": sum(
            bool(packet.get("local_reaction_family_conflict_any_source")) for packet in packets
        ),
        "local_reaction_family_conflict_primary_admissible_count": sum(
            bool(packet.get("local_reaction_family_conflict_primary_admissible")) for packet in packets
        ),
        "ammonia_quantification_semantic_count": sum(
            bool(packet.get("ammonia_quantification_signal")) for packet in packets
        ),
        "quantification_signal_count": sum(
            bool(packet.get("ammonia_quantification_signal")) for packet in packets
        ),
        "gas_purification_trap_semantic_count": sum(
            bool(packet.get("gas_purification_trap_signal")) for packet in packets
        ),
        "gas_trap_only_count": sum(
            bool(packet.get("gas_purification_trap_signal"))
            and not bool(packet.get("ammonia_quantification_signal"))
            for packet in packets
        ),
        "mass_spec_quantification_count": sum(
            bool(packet.get("mass_spectrometry_quantification_signal")) for packet in packets
        ),
        "enzymatic_quantification_count": sum(
            bool(packet.get("enzymatic_quantification_signal")) for packet in packets
        ),
        "performance_result_claim_count": semantic_claim_type_distribution["performance_result_claim"],
        "performance_context_claim_count": semantic_claim_type_distribution["performance_context_claim"],
        "quantitative_performance_primary_count": sum(
            bool(packet.get("primary_semantic_eligibility"))
            and str(packet.get("semantic_claim_type") or "") == "performance_result_claim"
            and bool(packet.get("quantitative_performance_evidence"))
            for packet in packets
        ),
        "performance_context_quantitative_primary_count": sum(
            bool(packet.get("primary_semantic_eligibility"))
            and str(packet.get("semantic_claim_type") or "") == "performance_context_claim"
            and bool(packet.get("quantitative_performance_evidence"))
            for packet in packets
        ),
        "primary_performance_without_result_evidence_count": sum(
            bool(packet.get("primary_semantic_eligibility"))
            and str(packet.get("semantic_claim_type") or "") == "performance_result_claim"
            and not bool(packet.get("performance_result_evidence"))
            for packet in packets
        ),
        "FeS_false_performance_count": sum(
            is_fe_material_only_false_performance({
                **packet,
                "source_text": packet.get("target_text") or "",
            })
            and str(packet.get("semantic_claim_type") or "") == "performance_result_claim"
            for packet in packets
        ),
        "generic_isotope_false_15N_count": sum(
            has_generic_isotope_without_15n(str(packet.get("target_text") or ""))
            and str(((packet.get("family_gate_coverage_any_source") or {}).get("isotope_15N") or {}).get("status") or "")
            == "observed_in_target"
            for packet in packets
        ),
        "NO_negation_false_source_count": sum(
            has_negated_no_source(str(packet.get("target_text") or ""))
            and str(((packet.get("family_gate_coverage_any_source") or {}).get("NO_source_defined") or {}).get("status") or "")
            == "observed_in_target"
            for packet in packets
        ),
        "NOx_balance_negation_false_positive_count": sum(
            has_negated_nox_balance(str(packet.get("target_text") or ""))
            and str(((packet.get("family_gate_coverage_any_source") or {}).get("NOx_balance") or {}).get("status") or "")
            == "observed_in_target"
            for packet in packets
        ),
        "conflicted_gate_counted_as_observed_count": sum(
            bool(gate_result.get("gate_conflict"))
            and str(gate_result.get("status") or "").startswith("observed_in_")
            for packet in packets
            for coverage_name in (
                "family_gate_coverage_any_source",
                "family_gate_coverage_primary_admissible",
            )
            for gate_result in (packet.get(coverage_name) or {}).values()
            if isinstance(gate_result, dict)
        ),
        "unique_evidence_total": unique_total, "role_assignment_total": role_total,
        "mean_unique_evidence_per_packet": round(statistics.mean(unique_counts), 4) if unique_counts else 0.0,
        "median_unique_evidence_per_packet": round(statistics.median(unique_counts), 4) if unique_counts else 0.0,
        "p75_unique_evidence_per_packet": _percentile(unique_counts, 0.75),
        "p90_unique_evidence_per_packet": _percentile(unique_counts, 0.90),
        "p95_unique_evidence_per_packet": _percentile(unique_counts, 0.95),
        "packets_at_unique_limit": sum(
            len(p.get("evidence_items") or []) >= int((p.get("linking_diagnostics") or {}).get("maximum_total_links") or 12)
            for p in packets
        ),
        "packets_with_zero_evidence": sum(not (p.get("evidence_items") or []) for p in packets),
        "candidate_link_count": diagnostics["candidate_link_count"],
        "accepted_link_count": diagnostics["accepted_link_count"],
        "links_below_threshold": diagnostics["links_below_threshold"],
        "family_mismatch_rejected_count": diagnostics["family_mismatch_rejected_count"],
        "low_trust_rejected_count": diagnostics["low_trust_rejected_count"],
        "duplicate_serialized_span_count": duplicate_serialized,
        "self_link_count": diagnostics["self_link_count"],
        "cross_paper_link_count": diagnostics["cross_paper_link_count"],
        "context_hint_positive_overlap_count": hint_overlap,
        "mapping_method_distribution": dict(sorted(mapping_methods.items())),
        "mapping_confidence_distribution": dict(sorted(mapping_confidence.items())),
        "unresolved_mapping_count": mapping_methods["unresolved"],
        "multiple_exact_match_count": sum(
            "multiple_exact_matches" in ((p.get("target_mapping") or {}).get("warnings") or []) for p in packets
        ),
        "stable_span_uid_method_distribution": dict(sorted(stable_methods.items())),
        "duplicate_stable_uid_count": packet_count - len({p.get("target_stable_span_uid") for p in packets}),
        "evidence_role_distribution": dict(sorted(role_distribution.items())),
        "missing_type_distribution": dict(sorted(missing.items())),
        "family_specific_missing_gates": {family: dict(sorted(values.items())) for family, values in sorted(family_missing.items())},
        "reference_primary_support_count": low_trust["reference"],
        "figure_caption_primary_support_count": low_trust["figure_caption"],
        "scheme_caption_primary_support_count": low_trust["scheme_caption"],
        "caption_primary_support_count": low_trust["figure_caption"] + low_trust["scheme_caption"],
        "review_table_primary_support_count": low_trust["review_table"],
        "warnings_count": sum(len(p.get("warnings") or []) for p in packets),
        "legacy_keyword_linking_comparison": legacy_keyword_linking_comparison or {},
    }
    return summary


def export_context_packets(
    packets: list[dict[str, Any]], run_name: str, *, output_dir: str | Path = "data/context_packets",
    report_dir: str | Path = "data/reports", context_profile: str | None = None,
    legacy_keyword_linking_comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = context_profile or (
        str(packets[0].get("context_profile") or KEYWORD_LINKING_PROFILE)
        if packets else KEYWORD_LINKING_PROFILE
    )
    base = Path(output_dir)
    if profile in {HIERARCHICAL_LINKING_PROFILE, ORDERED_SOURCE_PROFILE}:
        if base.name == profile:
            run_dir = base
        elif base.name == run_name:
            run_dir = base / profile
        else:
            run_dir = base / run_name / profile
        report_path = Path(report_dir) / f"context_packet_report.{run_name}.{profile}.md"
    else:
        run_dir = base / run_name
        report_path = Path(report_dir) / f"context_packet_report.{run_name}.md"
    jsonl_path = run_dir / "context_packets.jsonl"
    csv_path = run_dir / "context_packets.csv"
    summary_path = run_dir / "context_packet_summary.json"
    summary = summarize_context_packets(
        packets, run_name, legacy_keyword_linking_comparison=legacy_keyword_linking_comparison
    )
    _write_jsonl(packets, jsonl_path)
    fields = LEGACY_PACKET_FIELDS if profile == KEYWORD_LINKING_PROFILE else (
        ORDERED_PACKET_FIELDS if profile == ORDERED_SOURCE_PROFILE else PACKET_FIELDS
    )
    _write_csv(packets, csv_path, fields)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(summary), encoding="utf-8", newline="\n")
    return {
        "run_name": run_name, "count": len(packets), "jsonl": str(jsonl_path), "csv": str(csv_path),
        "summary": str(summary_path), "report": str(report_path), "summary_data": summary,
    }


def export_semantic_sample(
    packets: list[dict[str, Any]], run_name: str, *, report_dir: str | Path = "data/reports", seed: int = 13
) -> str:
    """Write a deterministic 60-packet semantic review sample without claiming precision."""

    quotas = (("eNRR", 10), ("LiNRR", 10), ("NO3RR", 10), ("NO2RR_or_NORR", 6),
              ("mixed_or_unclear", 6), ("low_trust", 6), ("negative", 6), ("reactor_or_process", 6))
    selected: list[tuple[str, dict[str, Any]]] = []
    used: set[str] = set()
    for category, count in quotas:
        candidates = [p for p in packets if _sample_category(p, category) and p.get("context_packet_id") not in used]
        candidates.sort(key=lambda p: hashlib.sha256(f"{seed}\0{p.get('context_packet_id')}".encode()).hexdigest())
        for packet in candidates[:count]:
            selected.append((category, packet)); used.add(str(packet.get("context_packet_id")))
    if len(selected) < 60:
        remaining = [p for p in packets if p.get("context_packet_id") not in used]
        remaining.sort(key=lambda p: hashlib.sha256(f"{seed}\0{p.get('context_packet_id')}".encode()).hexdigest())
        selected.extend(("deterministic_fill", packet) for packet in remaining[:60 - len(selected)])
    path = Path(report_dir) / f"context_packet_semantic_sample.{run_name}.md"
    lines = [f"# Context Packet Semantic Sample: {run_name}", "", f"- Seed: {seed}",
             f"- Samples: {len(selected)}", "- Purpose: manual semantic review; precision is not automatically asserted.", ""]
    for number, (category, packet) in enumerate(selected, 1):
        local = packet.get("local_context") or {}
        lines.extend([
            f"## {number}. {packet.get('target_span_id')} ({category})", "",
            f"- Target: {str(packet.get('target_text') or '')[:1000]}",
            f"- Section: {(packet.get('target_mapping') or {}).get('section_heading') or ''}",
            f"- Local paragraph context: {json.dumps(local, ensure_ascii=False, sort_keys=True)[:3000]}",
            f"- Evidence items: {json.dumps(packet.get('evidence_items') or [], ensure_ascii=False, sort_keys=True)[:5000]}",
            f"- Classification sufficient: {packet.get('classification_context_sufficient')}",
            f"- Claim-support sufficient: {packet.get('claim_support_context_sufficient')}",
            f"- Missing gates: {', '.join(packet.get('context_missing_types') or []) or 'none'}", "",
        ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return str(path)


def _legacy_context_sufficiency(
    target: dict[str, Any], packet_links: dict[str, list[dict[str, Any]]]
) -> tuple[list[str], bool, str]:
    text = str(target.get("source_text") or "").casefold()
    provenance = str(target.get("provenance_type") or "unknown").casefold()
    text_class = str(target.get("text_class") or "unknown").casefold()
    if provenance in LOW_TRUST_PROVENANCE or text_class in LOW_TRUST_TEXT_CLASSES:
        sufficient = bool(text and provenance != "unknown" and text_class != "unknown")
        return ([] if sufficient else ["primary_body_text"], sufficient, "high" if sufficient else "low")
    family = normalize_reaction_family(str(target.get("reaction_family") or "unclear"))
    missing = [] if family not in {"unclear", "mixed"} else ["reaction_family"]
    primary = text_class in {"primary_performance", "primary_performance_with_validation"} or str(target.get("claim_type") or "") in {"performance_claim", "validation_claim", "reactor_claim", "process_claim"}
    if not primary:
        return missing, bool(text) and not missing, "medium" if text else "low"
    if not _contains_performance_metric(text, target): missing.append("performance_metric")
    rank = BOUNDARY_RANK.get(str(target.get("maximum_supported_boundary") or "unsupported_or_secondary"), 0)
    linked_validation = _linked_text(packet_links.get("linked_validation_spans", []))
    linked_quant = _linked_text(packet_links.get("linked_quantification_spans", []))
    gates = target.get("validation_gates") if isinstance(target.get("validation_gates"), dict) else {}
    if rank >= BOUNDARY_RANK["cell_metric"]:
        if family in {"eNRR", "LiNRR"} and not _legacy_gate(gates, "isotope_15N", text + linked_validation, ("15n", "isotope")): missing.append("isotope_validation")
        if not _legacy_gate(gates, "blank_control", text + linked_validation, ("blank", "n2-free", "argon")): missing.append("blank_control")
        if not _legacy_gate(gates, "nox_control", text + linked_validation, ("nox", "nitrate", "nitrite")): missing.append("NOx_control")
        if not _legacy_gate(gates, "contamination_control", text + linked_validation, ("contamination control", "impurity screen")): missing.append("contamination_control")
        if not _legacy_gate(gates, "quantification_method", text + linked_quant, ("chromatography", "nmr", "colorimetric", "uv-vis", "calibration")): missing.append("quantification_method")
    missing = _dedupe(missing)
    return missing, not missing, "high" if not missing else ("medium" if len(missing) <= 2 else "low")


def _legacy_summary(packets: list[dict[str, Any]], run_name: str) -> dict[str, Any]:
    missing = Counter(); linked = Counter(); total = 0; maximum = 0; low = Counter(); cross = 0
    for packet in packets:
        missing.update(packet.get("context_missing_types") or [])
        try: validate_no_cross_paper_links(packet)
        except ValueError: cross += 1
        count = 0
        for role, field in LINK_PACKET_FIELDS.items():
            records = packet.get(field) or []; linked[role] += len(records); count += len(records)
            for item in records:
                if not item.get("primary_support"): continue
                provenance = str(item.get("provenance_type") or "").casefold(); text_class = str(item.get("text_class") or "").casefold()
                if provenance in {"reference", "bibliography"} or text_class == "reference_list": low["reference"] += 1
                if provenance in {"figure_caption", "scheme_caption"} or "caption" in text_class: low["caption"] += 1
                if provenance == "review_table" or text_class == "review_table": low["review_table"] += 1
        total += count; maximum = max(maximum, count)
    return {
        "run_name": run_name, "packet_count": len(packets),
        "paper_count": len({str(p.get("paper_id") or "") for p in packets}),
        "packets_with_context_sufficient": sum(bool(p.get("context_sufficient")) for p in packets),
        "packets_with_context_insufficient": sum(not bool(p.get("context_sufficient")) for p in packets),
        "missing_type_distribution": dict(sorted(missing.items())), "linked_span_distribution": dict(sorted(linked.items())),
        "average_links_per_packet": round(total / len(packets), 4) if packets else 0.0,
        "maximum_links_per_packet": maximum, "cross_paper_link_count": cross,
        "reference_primary_support_count": low["reference"], "caption_primary_support_count": low["caption"],
        "review_table_primary_support_count": low["review_table"],
        "warnings_count": sum(len(p.get("warnings") or []) for p in packets),
    }


def _render_report(summary: dict[str, Any]) -> str:
    lines = [f"# Evidence Context Packet Report: {summary['run_name']}", ""]
    for key in (
        "context_profile", "packet_count", "paper_count", "classification_context_sufficient_count",
        "classification_context_insufficient_count", "claim_support_context_sufficient_count",
        "claim_support_context_insufficient_count", "claim_support_applicable_count",
        "claim_support_not_applicable_count", "claim_support_sufficient_among_applicable",
        "claim_support_insufficient_among_applicable", "claim_support_rate_among_applicable",
        "packet_local_applicable_count", "packet_local_sufficient_count",
        "packet_local_insufficient_count", "packet_local_not_applicable_count",
        "packet_local_sufficiency_rate", "paper_gate_coverage_apparently_complete_count",
        "paper_gate_coverage_partial_count", "paper_gate_coverage_not_evaluated_count",
        "unique_evidence_total", "role_assignment_total",
        "mean_unique_evidence_per_packet", "median_unique_evidence_per_packet", "p90_unique_evidence_per_packet",
        "p95_unique_evidence_per_packet", "packets_at_unique_limit", "packets_with_zero_evidence",
        "links_below_threshold", "unresolved_mapping_count", "multiple_exact_match_count",
        "duplicate_serialized_span_count", "self_link_count", "cross_paper_link_count",
        "context_hint_positive_overlap_count", "reference_primary_support_count", "caption_primary_support_count",
        "review_table_primary_support_count", "paper_gate_primary_admissible_apparently_complete_count",
        "paper_gate_primary_admissible_partial_count", "paper_gate_primary_admissible_not_evaluated_count",
        "local_reaction_family_conflict_any_source_count",
        "local_reaction_family_conflict_primary_admissible_count", "ammonia_quantification_semantic_count",
        "gas_purification_trap_semantic_count", "semantic_claim_type_conflict_count",
        "primary_semantic_eligibility_count", "off_target_reaction_conflict_count",
        "review_removed_from_primary_count", "perspective_removed_from_primary_count",
        "external_attribution_removed_count", "target_primary_gate_complete_count",
        "any_source_gate_complete_count", "quantification_signal_count", "gas_trap_only_count",
        "mass_spec_quantification_count", "enzymatic_quantification_count",
        "performance_result_claim_count", "performance_context_claim_count",
        "quantitative_performance_primary_count", "FeS_false_performance_count",
        "performance_context_quantitative_primary_count",
        "primary_performance_without_result_evidence_count",
        "generic_isotope_false_15N_count", "NO_negation_false_source_count",
        "NOx_balance_negation_false_positive_count", "conflicted_gate_counted_as_observed_count",
        "document_genre_distribution", "document_genre_span_distribution", "span_claim_scope_distribution",
        "document_reaction_family_distribution", "effective_reaction_family_distribution",
        "reaction_family_correction_count", "document_target_family_conflict_count",
        "claim_ownership_distribution", "semantic_claim_type_distribution",
        "document_genre_inconsistent_document_count", "semantic_claim_type_conflict_matrix",
        "semantic_claim_type_conflict_by_document_genre",
        "semantic_claim_type_conflict_by_reaction_family",
        "semantic_claim_type_conflict_primary_eligible_count",
        "semantic_claim_type_conflict_not_applicable_count",
        "primary_semantic_eligible_by_document_genre",
        "primary_semantic_eligible_by_semantic_claim_type",
        "primary_semantic_eligible_by_reaction_family",
        "primary_eligible_by_effective_family", "primary_eligible_unclear_family_count",
        "primary_semantic_eligible_by_provenance_type",
        "primary_semantic_eligible_by_ownership_confidence",
        "primary_semantic_eligible_by_semantic_type_confidence",
        "review_primary_semantic_eligible_count", "perspective_primary_semantic_eligible_count",
        "mixed_primary_semantic_eligible_count", "unclear_genre_primary_semantic_eligible_count",
        "off_target_primary_semantic_eligible_count",
        "non_primary_provenance_primary_semantic_eligible_count",
        "secondary_context_primary_semantic_eligible_count",
        "reject_or_low_trust_primary_semantic_eligible_count",
        "target_primary_gate_supported_by_nonprimary_count", "hard_gate_failure_distribution",
    ):
        if key in summary: lines.append(f"- {key}: {summary[key]}")
    lines.extend(["", "## Missing context", "", *[f"- {k}: {v}" for k, v in summary.get("missing_type_distribution", {}).items()],
                  "", "## Mapping", "", *[f"- {k}: {v}" for k, v in summary.get("mapping_method_distribution", {}).items()],
                  "", "## Legacy keyword linking comparison", "", f"```json\n{json.dumps(summary.get('legacy_keyword_linking_comparison', {}), indent=2, sort_keys=True)}\n```", ""])
    return "\n".join(lines)


def _sample_category(packet: dict[str, Any], category: str) -> bool:
    family = normalize_reaction_family(str(
        packet.get("effective_reaction_family") or packet.get("target_reaction_family") or "unclear"
    ))
    if category in {"eNRR", "LiNRR", "NO3RR"}: return family == category
    if category == "NO2RR_or_NORR": return family in {"NO2RR", "NORR"}
    if category == "mixed_or_unclear": return family in {"mixed", "unclear"}
    if category == "low_trust": return str(packet.get("target_provenance_type") or "").casefold() in LOW_TRUST_PROVENANCE or str(packet.get("target_text_class") or "").casefold() in LOW_TRUST_TEXT_CLASSES
    roles = {role for item in packet.get("evidence_items") or [] for role in item.get("link_roles") or []}
    if category == "negative": return "negative_or_contradicting" in roles
    if category == "reactor_or_process": return bool(roles & {"reactor", "process"})
    return False


def _claim_support_applicable(target: dict[str, Any]) -> bool:
    text_class = str(target.get("text_class") or "unknown").casefold()
    provenance = str(target.get("provenance_type") or "unknown").casefold()
    if provenance in LOW_TRUST_PROVENANCE or text_class in {
        "reference_list", "figure_caption", "scheme_caption", "review_table",
        "background_context", "protocol_guideline", "metadata",
    }:
        return False
    semantic_type = str(classify_claim_type(target).get("semantic_claim_type") or "")
    return semantic_type in PRIMARY_SEMANTIC_CLAIM_TYPES


def _compact_paragraph(paragraph: dict[str, Any] | None) -> dict[str, Any] | None:
    if paragraph is None:
        return None
    return {
        "paragraph_uid": paragraph.get("paragraph_uid"),
        "source_locator": paragraph.get("source_locator"),
        "paragraph_global_index": paragraph.get("paragraph_global_index"),
        "paragraph_index_in_section": paragraph.get("paragraph_index_in_section"),
        "source_start_offset": paragraph.get("source_start_offset"),
        "source_end_offset": paragraph.get("source_end_offset"),
        "section_uid": paragraph.get("section_uid"),
        "text": paragraph.get("text") or "",
    }


def _compact_section_context(
    section: dict[str, Any] | None, source_ledger: OrderedSourceLedger, document_id: str
) -> dict[str, Any] | None:
    if section is None:
        return None
    paragraph_count = sum(
        paragraph.get("section_uid") == section.get("section_uid")
        for paragraph in source_ledger.paragraphs_by_document.get(document_id, [])
    )
    return {
        "section_uid": section.get("section_uid"), "outline_label": section.get("outline_label"),
        "heading": section.get("heading_text"), "raw_heading": section.get("raw_heading"),
        "normalized_heading": section.get("normalized_heading"),
        "direct_section_type": section.get("direct_section_type"),
        "direct_section_type_confidence": section.get("direct_section_type_confidence"),
        "inherited_section_type": section.get("inherited_section_type"),
        "inherited_from_section_uid": section.get("inherited_from_section_uid"),
        "inheritance_distance": section.get("inheritance_distance"),
        "effective_section_type": section.get("effective_section_type"),
        "effective_section_type_confidence": section.get("effective_section_type_confidence"),
        "section_type_source": _section_type_source(section),
        "section_type": section.get("section_type"),
        "document_region": section.get("document_region"),
        "section_start_offset": section.get("section_start_offset"),
        "section_end_offset": section.get("section_end_offset"), "paragraph_count": paragraph_count,
    }


def _missing_name(gate: str) -> str:
    return {"isotope_15N": "isotope_validation", "ammonia_quantification": "quantification_method"}.get(gate, gate)


def _unresolved_target_mapping() -> dict[str, Any]:
    return {"method": "unresolved", "confidence": "unresolved", "document_id": None,
            "source_start_offset": None, "source_end_offset": None, "paragraph_id": None,
            "paragraph_order": None, "section_heading": "", "section_path": [],
            "candidate_offsets": [], "warnings": ["document_context_not_available"]}


def _percentile(values: list[int], quantile: float) -> float:
    if not values: return 0.0
    ordered = sorted(values); position = (len(ordered) - 1) * quantile
    lower = math.floor(position); upper = math.ceil(position)
    if lower == upper: return float(ordered[lower])
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 4)


def _contains_performance_metric(text: str, target: dict[str, Any]) -> bool:
    if any(target.get(key) not in (None, "", [], {}) for key in ("faradaic_efficiency_percent", "FE_percent", "nh3_yield_value", "current_density", "potential_value", "voltage", "runtime", "stability_hours")): return True
    folded = text.casefold()
    return bool(re.search(r"\b(?:faradaic efficiency|nh3 yield|ammonia yield|current density|runtime)\b|\bfe\s*(?:=|of|was|:)?\s*\d", folded))


def _reactor_signal(text: str) -> bool:
    return any(term in text for term in ("flow cell", "gas diffusion electrode", "gde", "active area", "flow rate", "outlet"))


def _process_signal(text: str) -> bool:
    return any(term in text for term in ("capture", "separation", "electrolyte recycle", "hydrogen source", "auxiliary load"))


def _negative_target(text: str) -> bool:
    folded = text.casefold()
    return (
        any(term in folded for term in (
            "false positive", "background ammonia", "extraneous ammonia", "ammonia contamination"
        ))
        or bool(re.search(
            r"\bno\s+(?:nh3|ammonia)\b|\b(?:nh3|ammonia)\b.{0,40}"
            r"\b(?:not detected|undetected|absent|below (?:the )?detection limit)\b",
            folded,
        ))
    )


def _legacy_gate(gates: dict[str, Any], key: str, text: str, signals: tuple[str, ...]) -> bool:
    return str(gates.get(key) or "").casefold() in {"yes", "explicit"} or any(signal in text for signal in signals)


def _linked_text(records: list[dict[str, Any]]) -> str:
    return " ".join(str(record.get("source_text") or "").casefold() for record in records)


def _index_by_span(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for record in records:
        span_id = _span_id(record)
        if span_id and span_id not in result: result[span_id] = record
    return result


def _span_id(record: dict[str, Any]) -> str:
    return str(record.get("source_span_id") or record.get("span_id") or record.get("legacy_span_id") or "").strip()


def _packet_id(run_name: str, target: dict[str, Any]) -> str:
    payload = f"{run_name}\0{target.get('paper_id')}\0{target.get('stable_span_uid')}".encode()
    return "CP_" + hashlib.sha256(payload).hexdigest()[:32]


def _first_value(record: dict[str, Any], *keys: str) -> str:
    return next((str(record[key]).strip() for key in keys if str(record.get(key) or "").strip()), "")


def _write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records: handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n")


def _write_csv(records: list[dict[str, Any]], path: Path, fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields)); writer.writeheader()
        for record in records: writer.writerow({field: _csv_value(record.get(field)) for field in fields})


def _csv_value(value: Any) -> str:
    if isinstance(value, (list, dict)): return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if isinstance(value, bool): return "true" if value else "false"
    return "" if value is None else str(value)


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != []


def _sortable_offset(primary: Any, fallback: Any) -> int:
    for value in (primary, fallback):
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 10**18


def _select_location_pair(
    sources: tuple[tuple[str, dict[str, Any]], ...], start_field: str, end_field: str
) -> tuple[tuple[Any, Any], str]:
    for name, source in sources:
        if _present(source.get(start_field)) and _present(source.get(end_field)):
            return ((_copy_value(source[start_field]), _copy_value(source[end_field])), name)
    return ((None, None), "unresolved")


def _select_location_value(
    sources: tuple[tuple[str, dict[str, Any]], ...], field: str
) -> tuple[Any, str]:
    for name, source in sources:
        if _present(source.get(field)):
            return (_copy_value(source[field]), name)
    return (None, "unresolved")


def _select_location_metadata(
    sources: tuple[tuple[str, dict[str, Any]], ...], fields: tuple[str, ...]
) -> tuple[dict[str, Any], str]:
    for name, source in sources:
        if any(_present(source.get(field)) for field in fields):
            return ({field: _copy_value(source.get(field)) for field in fields if _present(source.get(field))}, name)
    return ({}, "unresolved")


def _copy_value(value: Any) -> Any:
    if isinstance(value, dict): return {key: _copy_value(item) for key, item in value.items()}
    if isinstance(value, list): return [_copy_value(item) for item in value]
    return value


def _list_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)): return [str(item) for item in value if str(item)]
    return [str(value)] if str(value or "") else []


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))
