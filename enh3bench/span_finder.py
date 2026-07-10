"""Keyword-based candidate evidence span discovery."""

from __future__ import annotations

import re
from typing import Any

from enh3bench.front_matter import strip_conversion_front_matter
from enh3bench.section_context import extract_markdown_section_blocks, infer_section_confidence


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


def find_candidate_spans(
    document: dict[str, Any],
    paper_id: str | None = None,
    max_spans_per_document: int = 8,
) -> list[dict[str, Any]]:
    """Find candidate evidence spans in one loaded Markdown document."""

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
