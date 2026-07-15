"""Keyword-based candidate evidence span discovery."""

from __future__ import annotations

import re
from typing import Any

from enh3bench.front_matter import strip_conversion_front_matter
from enh3bench.section_context import extract_markdown_section_blocks, infer_section_confidence
from enh3bench.source_ledger import OrderedSourceLedger, sort_spans_by_priority, sort_spans_by_source_order


KEYWORDS = [
    "FE",
    "Faradaic efficiency",
    "NH3",
    "ammonia yield",
    "yield rate",
    "15N",
    "isotope",
    "blank",
    "Ar",
    "control",
    "NOx",
    "nitrate",
    "nitrite",
    "electrolyte",
    "potential",
    "RHE",
    "Li-mediated",
    "lithium-mediated",
    "THF",
    "Li+",
    "flow cell",
    "reactor",
]
LEGACY_SELECTION_PROFILE = "legacy_keyword_topk_v1"
ORDERED_SELECTION_PROFILE = "ordered_source_v1"


def find_candidate_spans(
    document: dict[str, Any],
    paper_id: str | None = None,
    max_spans_per_document: int = 8,
    *,
    selection_profile: str = LEGACY_SELECTION_PROFILE,
    output_order: str | None = None,
    source_ledger: OrderedSourceLedger | None = None,
) -> list[dict[str, Any]]:
    """Find candidate evidence spans in one loaded Markdown document."""

    if selection_profile == ORDERED_SELECTION_PROFILE:
        if source_ledger is None:
            raise ValueError("ordered_source_v1 requires source_ledger")
        return _find_ordered_candidates(
            document, paper_id, max_spans_per_document, output_order or "source", source_ledger
        )
    if selection_profile != LEGACY_SELECTION_PROFILE:
        raise ValueError(f"unknown span selection profile: {selection_profile}")

    document_id = str(document.get("document_id", "")).strip()
    resolved_paper_id = paper_id or document_id
    candidates: list[dict[str, Any]] = []
    text = str(document.get("text", ""))
    isolation = strip_conversion_front_matter(text)
    source_text = isolation["body_text"]

    section_blocks = list(document.get("section_blocks") or extract_markdown_section_blocks(source_text))
    for paragraph_index, paragraph_block in enumerate(_paragraph_blocks(source_text), start=1):
        paragraph = paragraph_block["text"]
        matched_keywords = _matched_keywords(paragraph)
        if not matched_keywords:
            continue
        score = _score_keywords(matched_keywords)
        section_context = _section_context_for_offset(section_blocks, paragraph_block["start"], len(source_text))
        provenance_confidence, rationale = infer_section_confidence(section_context)
        candidates.append(
            {
                "span_id": f"{document_id}_S{paragraph_index:03d}",
                "paper_id": resolved_paper_id,
                "document_id": document_id,
                "source_section": _source_section_from_context(section_context),
                "text": paragraph,
                "source_start_offset": paragraph_block["start"],
                "source_end_offset": paragraph_block["end"],
                "section_heading": section_context.get("section_heading", ""),
                "section_path": section_context.get("section_path", []),
                "section_level": section_context.get("section_level", 0),
                "section_type": section_context.get("section_type", "unknown"),
                "section_start_offset": section_context.get("section_start_offset", 0),
                "section_end_offset": section_context.get("section_end_offset", len(source_text)),
                "section_confidence": section_context.get("section_confidence", provenance_confidence),
                "section_signals": section_context.get("section_signals", []),
                "section_confidence_rationale": rationale,
                "candidate_score": score,
                "matched_keywords": matched_keywords,
                "annotation_status": "machine_drafted",
                "notes": "Auto-selected candidate span.",
            }
        )

    candidates.sort(key=lambda item: (-int(item["candidate_score"]), str(item["span_id"])))
    return candidates[:max_spans_per_document]


def _find_ordered_candidates(
    document: dict[str, Any], paper_id: str | None, maximum: int, output_order: str,
    source_ledger: OrderedSourceLedger,
) -> list[dict[str, Any]]:
    document_id = str(document.get("document_id") or "").strip()
    resolved_paper_id = str(paper_id or document_id)
    paragraphs = source_ledger.paragraphs_by_document.get(document_id)
    if paragraphs is None:
        raise KeyError(f"document not found in source ledger: {document_id}")
    section_index = {
        str(section["section_uid"]): section
        for section in source_ledger.sections_by_document.get(document_id, [])
    }
    all_candidates: list[dict[str, Any]] = []
    for paragraph in paragraphs:
        text = str(paragraph["text"])
        matched_keywords = _matched_keywords(text)
        if not matched_keywords:
            continue
        section = section_index.get(str(paragraph["section_uid"]), {})
        source_span_id = f"{document_id}_S{int(paragraph['paragraph_global_index']):03d}"
        order_key = str(paragraph["source_order_key"])
        if order_key.endswith("000000"):
            order_key = order_key[:-6] + "000001"
        all_candidates.append({
            "span_id": source_span_id, "source_span_id": source_span_id,
            "legacy_span_id": source_span_id, "paper_id": resolved_paper_id,
            "document_id": document_id, "source_locator": f"{paragraph['source_locator']}::ANCHOR01",
            "source_order_key": order_key, "paragraph_uid": paragraph["paragraph_uid"],
            "section_uid": paragraph["section_uid"],
            "paragraph_global_index": paragraph["paragraph_global_index"],
            "paragraph_index_in_section": paragraph["paragraph_index_in_section"],
            "section_outline_label": paragraph["section_outline_label"],
            "section_type": paragraph["section_type"], "section_heading": paragraph["section_heading"],
            "source_section": _source_section_from_context(paragraph), "text": text,
            "source_start_offset": paragraph["source_start_offset"],
            "source_end_offset": paragraph["source_end_offset"],
            "section_start_offset": section.get("section_start_offset"),
            "section_end_offset": section.get("section_end_offset"),
            "section_level": section.get("section_level", 0),
            "section_path": list(paragraph.get("section_path") or (
                [paragraph["section_heading"]] if paragraph.get("section_heading") else []
            )),
            "section_confidence": "high" if paragraph.get("section_heading") else "low",
            "section_signals": ["ordered_source_ledger"],
            "candidate_score": _score_keywords(matched_keywords), "matched_keywords": matched_keywords,
            "annotation_status": "machine_drafted", "notes": "Auto-selected candidate span.",
            "selected_by_priority": True, "selection_reason": "top_k_keyword_score_then_source_order",
            "document_relative_position": paragraph["document_relative_position"],
            "section_relative_position": paragraph["section_relative_position"],
        })
    priority = sorted(
        all_candidates,
        key=lambda item: (-int(item["candidate_score"]), int(item["source_start_offset"])),
    )
    for rank, candidate in enumerate(priority, start=1):
        candidate["candidate_priority_rank"] = rank
    selected = priority[:max(0, int(maximum))]
    if output_order == "source":
        return sort_spans_by_source_order(selected)
    if output_order == "priority":
        return sort_spans_by_priority(selected)
    raise ValueError(f"unknown output_order: {output_order}")


def _matched_keywords(text: str) -> list[str]:
    return [keyword for keyword in KEYWORDS if _keyword_matches(text, keyword)]


def _keyword_matches(text: str, keyword: str) -> bool:
    if keyword.isalnum():
        pattern = rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    return re.search(re.escape(keyword), text, flags=re.IGNORECASE) is not None


def _score_keywords(matched_keywords: list[str]) -> int:
    strong = {
        "Faradaic efficiency",
        "ammonia yield",
        "yield rate",
        "15N",
        "isotope",
        "blank",
        "control",
        "NOx",
        "nitrate",
        "nitrite",
        "Li-mediated",
        "lithium-mediated",
        "flow cell",
        "reactor",
    }
    return sum(2 if keyword in strong else 1 for keyword in matched_keywords)


def _paragraph_blocks(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for match in re.finditer(r"\S(?:.*?)(?=\n\s*\n+|\Z)", text, flags=re.DOTALL):
        paragraph = match.group(0).strip()
        if not paragraph:
            continue
        leading = len(match.group(0)) - len(match.group(0).lstrip())
        trailing = len(match.group(0).rstrip())
        blocks.append(
            {
                "text": paragraph,
                "start": match.start() + leading,
                "end": match.start() + trailing,
            }
        )
    return blocks


def _section_context_for_offset(section_blocks: list[dict[str, Any]], offset: int, text_length: int) -> dict[str, Any]:
    for block in section_blocks:
        start = int(block.get("section_start_offset") or 0)
        end = int(block.get("section_end_offset") or text_length)
        if start <= offset < end:
            item = dict(block)
            signals = [str(signal) for signal in item.get("section_signals") or []]
            if "inherited_markdown_section" not in signals:
                signals.append("inherited_markdown_section")
            item["section_signals"] = signals
            return item
    return {
        "section_heading": "",
        "section_path": [],
        "section_level": 0,
        "section_type": "unknown",
        "section_start_offset": 0,
        "section_end_offset": text_length,
        "section_confidence": "low",
        "section_signals": ["no_markdown_heading"],
    }


def _source_section_from_context(section_context: dict[str, Any]) -> str:
    section_type = str(section_context.get("section_type") or "unknown")
    if section_type == "results_and_discussion":
        return "results"
    if section_type in {"abstract", "methods", "results", "discussion", "supplementary"}:
        return section_type
    return "unknown"
