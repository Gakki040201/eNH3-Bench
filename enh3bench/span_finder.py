"""Keyword-based candidate evidence span discovery."""

from __future__ import annotations

import re
from typing import Any

from enh3bench.document_loader import split_into_paragraphs
from enh3bench.front_matter import strip_conversion_front_matter


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

    for paragraph_index, paragraph in enumerate(split_into_paragraphs(source_text), start=1):
        matched_keywords = _matched_keywords(paragraph)
        if not matched_keywords:
            continue
        score = _score_keywords(matched_keywords)
        candidates.append(
            {
                "span_id": f"{document_id}_S{paragraph_index:03d}",
                "paper_id": resolved_paper_id,
                "document_id": document_id,
                "source_section": "unknown",
                "text": paragraph,
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
