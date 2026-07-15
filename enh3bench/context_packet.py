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

from enh3bench.document_context import (
    DocumentContextIndex,
    get_local_paragraph_context,
    get_section_chunk,
    resolve_document_for_span,
    resolve_span_mapping,
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
from enh3bench.reaction_profiles import get_reaction_profile, normalize_reaction_family
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
ORDERED_CONTEXT_PACKET_SCHEMA_VERSION = "1.2"
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
    "target_section_uid", "target_section_outline_label", "target_section_heading", "target_section_type",
    "target_paragraph_uid", "target_paragraph_global_index", "target_paragraph_index_in_section",
    "target_document_relative_position", "target_section_relative_position",
    "target_source_start_offset", "target_source_end_offset", "target_text", "target_text_class",
    "target_provenance_type", "target_reaction_family", "target_span_boundary",
    "target_admissibility_status", "previous_paragraph", "target_paragraph", "next_paragraph",
    "section_context", "document_outline", "evidence_items", "evidence_role_index",
    "classification_context_sufficient", "claim_support_applicable",
    "claim_support_context_sufficient", "context_purpose", "context_sufficient",
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
            "paper_title", "title", "paper_abstract", "abstract", "section_path",
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
    classification, claim_support, purpose, missing, confidence = _context_sufficiency_v11(target, evidence_items)
    applicable = _claim_support_applicable(target)
    if not applicable:
        claim_support = False
        purpose = "classification"
        missing = []
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
        "target_mapping": target_mapping,
        "previous_paragraph": _compact_paragraph(previous_paragraph),
        "target_paragraph": _compact_paragraph(paragraph),
        "next_paragraph": _compact_paragraph(next_paragraph),
        "section_context": _compact_section_context(section, source_ledger, document_id),
        "document_outline": [
            {"section_uid": item["section_uid"], "outline_label": item["outline_label"],
             "heading": item["heading_text"], "section_type": item["section_type"]}
            for item in source_ledger.sections_by_document.get(document_id, [])
        ],
        "evidence_items": evidence_items, "evidence_role_index": role_index,
        "classification_context_sufficient": classification,
        "claim_support_applicable": applicable,
        "claim_support_context_sufficient": bool(applicable and claim_support),
        "context_purpose": purpose, "context_sufficient": bool(applicable and claim_support),
        "context_missing_types": missing, "context_confidence": confidence,
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
    ).casefold()
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
    gates = target.get("validation_gates") if isinstance(target.get("validation_gates"), dict) else {}
    aliases = {"ammonia_quantification": "quantification_method", "isotope_15N": "isotope_15N"}
    stored = gates.get(gate, gates.get(aliases.get(gate, "")))
    if str(stored or "").casefold() in {"yes", "explicit", "pass", "present"}:
        return True
    if gate == "isotope_15N":
        return bool(re.search(r"\b15\s*n(?:2)?\b|\bisotope(?:-label(?:l)?ed)?\b", text))
    if gate == "blank_control":
        return bool(re.search(r"\b(?:ar|argon|n2[- ]?free|electrolyte)\s+blank\b|\bblank control\b", text))
    if gate == "NOx_control":
        return bool(re.search(r"\bnox\s+(?:screening|control|impurit(?:y|ies)|analysis)\b|\bnitrate/nitrite impurity\b", text))
    if gate == "contamination_control":
        return bool(re.search(r"\b(?:ammonia )?contamination control\b|\bbackground (?:nh3|ammonia) control\b|\bimpurity screening\b", text))
    if gate == "ammonia_quantification":
        method = r"ion chromatography|\bic\b|nmr|uv[- ]?vis|colorimetric|gas trap"
        return bool(re.search(rf"(?:ammonia|nh3).{{0,80}}(?:{method})|(?:{method}).{{0,80}}(?:ammonia|nh3)", text))
    if gate == "operating_field_disclosure":
        return bool(re.search(r"\b(?:current density|cell voltage|applied potential|runtime|flow rate)\b", text))
    if gate == "nitrate_source_defined":
        return bool(re.search(r"\bnitrate\s+(?:feed|source|reactant|concentration|electrolyte)\b|\b(?:feed|source|reactant)\s+nitrate\b", text))
    if gate == "nitrite_source_defined":
        return bool(re.search(r"\bnitrite\s+(?:feed|source|reactant|concentration|electrolyte)\b|\b(?:feed|source|reactant)\s+nitrite\b", text))
    if gate == "NO_source_defined":
        return bool(re.search(r"\bno\s+(?:gas|feed|source|reactant|concentration)\b|\b(?:feed|source)\s+no\b", text))
    if gate == "nitrogen_balance":
        return bool(re.search(r"\bnitrogen (?:mass )?balance\b|\bn balance\b", text))
    if gate == "NOx_balance":
        return bool(re.search(r"\bnox balance\b|\bno mass balance\b", text))
    if gate == "competing_product_tracking":
        return bool(re.search(r"\b(?:competing|by[- ]?product|nitrite|nitrate|n2)\b.{0,60}\b(?:tracking|quantif|balance|analysis)\b", text))
    if gate == "nitrogen_source_disambiguation":
        return bool(re.search(r"\bnitrogen source\b.{0,40}\b(?:defined|identified|n2|nitrate|nitrite|no)\b", text))
    return False


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
    for packet in packets:
        paper_ids.add(str(packet.get("paper_id") or ""))
        missing_types = packet.get("context_missing_types") or []
        missing.update(missing_types)
        family = normalize_reaction_family(str(packet.get("target_reaction_family") or "unclear"))
        family_missing[family].update(missing_types)
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
        "unique_evidence_total", "role_assignment_total",
        "mean_unique_evidence_per_packet", "median_unique_evidence_per_packet", "p90_unique_evidence_per_packet",
        "p95_unique_evidence_per_packet", "packets_at_unique_limit", "packets_with_zero_evidence",
        "links_below_threshold", "unresolved_mapping_count", "multiple_exact_match_count",
        "duplicate_serialized_span_count", "self_link_count", "cross_paper_link_count",
        "context_hint_positive_overlap_count", "reference_primary_support_count", "caption_primary_support_count",
        "review_table_primary_support_count",
    ):
        if key in summary: lines.append(f"- {key}: {summary[key]}")
    lines.extend(["", "## Missing context", "", *[f"- {k}: {v}" for k, v in summary.get("missing_type_distribution", {}).items()],
                  "", "## Mapping", "", *[f"- {k}: {v}" for k, v in summary.get("mapping_method_distribution", {}).items()],
                  "", "## Legacy keyword linking comparison", "", f"```json\n{json.dumps(summary.get('legacy_keyword_linking_comparison', {}), indent=2, sort_keys=True)}\n```", ""])
    return "\n".join(lines)


def _sample_category(packet: dict[str, Any], category: str) -> bool:
    family = normalize_reaction_family(str(packet.get("target_reaction_family") or "unclear"))
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
    claim_type = str(target.get("claim_type") or "").casefold()
    if provenance in LOW_TRUST_PROVENANCE or text_class in {
        "reference_list", "figure_caption", "scheme_caption", "review_table",
        "background_context", "protocol_guideline", "metadata",
    }:
        return False
    return text_class in {"primary_performance", "primary_performance_with_validation"} or claim_type in {
        "performance_claim", "validation_claim", "reactor_claim", "process_claim",
    }


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
        "heading": section.get("heading_text"), "section_type": section.get("section_type"),
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
    folded = text.casefold(); return any(term in folded for term in ("false positive", "background ammonia", "extraneous ammonia", "ammonia contamination"))


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
