"""Front-matter isolation helpers for converted Markdown documents."""

from __future__ import annotations

import re
from typing import Any


KNOWN_METADATA_KEYS = (
    "source_file:",
    "source_format:",
    "conversion_method:",
    "copyright_note:",
    "document_id:",
    "created_at:",
    "human_verification_required:",
    "parser:",
    "converter:",
)

REPOSITORY_COVER_SIGNALS = (
    "research online",
    "university of wollongong",
    "downloaded from",
    "general rights",
    "copyright and moral rights",
    "link back to",
    "follow this and additional works",
    "see next page for additional authors",
    "recommended citation",
    "repository cover page",
)


def split_yaml_front_matter(text: str) -> tuple[str | None, str]:
    """Split recognized YAML-like conversion metadata from Markdown text."""

    source = str(text or "")
    if source.startswith("\ufeff"):
        source = source.lstrip("\ufeff")
    lines = source.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, text

    for index in range(1, len(lines)):
        if lines[index].strip() != "---":
            continue
        front_matter = "".join(lines[1:index])
        if not _contains_known_metadata_key(front_matter):
            return None, text
        body = "".join(lines[index + 1 :]).lstrip()
        return front_matter.rstrip(), body
    return None, text


def is_repository_cover_page_text(text: str) -> bool:
    """Return True when text has multiple repository/cover-page signals."""

    head = _normalize(str(text or "")[:5000])
    hits = [signal for signal in REPOSITORY_COVER_SIGNALS if signal in head]
    return len(hits) >= 2


def split_repository_cover_page(text: str) -> tuple[str | None, str]:
    """Split a repository cover page from the scientific body candidate."""

    source = str(text or "")
    if not is_repository_cover_page_text(source):
        return None, text

    boundary = _first_body_boundary(source)
    if boundary is None:
        return source.strip(), ""
    cover = source[:boundary].strip()
    body = source[boundary:].lstrip()
    return cover, body


def strip_conversion_front_matter(text: str) -> dict[str, Any]:
    """Isolate conversion metadata and repository cover text from body text."""

    metadata_text, body_after_metadata = split_yaml_front_matter(text)
    repository_cover_text, body_text = split_repository_cover_page(body_after_metadata)
    signals: list[str] = []
    if metadata_text is not None:
        signals.append("yaml_front_matter_removed")
    if repository_cover_text is not None:
        signals.append("repository_cover_page_removed")
    if metadata_text is not None and str(body_text or "").strip():
        signals.append("metadata_body_split")
    if repository_cover_text is not None and str(body_text or "").strip():
        signals.append("repository_cover_body_split")
    return {
        "metadata_text": metadata_text,
        "repository_cover_text": repository_cover_text,
        "body_text": body_text,
        "signals": signals,
        "metadata_removed": metadata_text is not None,
        "repository_cover_removed": repository_cover_text is not None,
    }


def make_front_matter_records(
    document_id: str,
    paper_id: str,
    metadata_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Create low-trust records for isolated metadata/front-matter text."""

    records: list[dict[str, Any]] = []
    metadata_text = metadata_result.get("metadata_text")
    if metadata_text:
        records.append(
            _front_matter_record(
                document_id,
                paper_id,
                "META",
                "metadata",
                str(metadata_text),
                "isolated_conversion_metadata",
            )
        )
    cover_text = metadata_result.get("repository_cover_text")
    if cover_text:
        records.append(
            _front_matter_record(
                document_id,
                paper_id,
                "FRONT",
                "front_matter",
                str(cover_text),
                "isolated_repository_front_matter",
            )
        )
    return records


def _front_matter_record(
    document_id: str,
    paper_id: str,
    prefix: str,
    provenance_type: str,
    source_text: str,
    blocked_reason: str,
) -> dict[str, Any]:
    source_span_id = f"{document_id}_{prefix}_001"
    return {
        "source_span_id": source_span_id,
        "span_id": source_span_id,
        "evidence_id": f"E_{source_span_id}",
        "paper_id": paper_id,
        "document_id": document_id,
        "source_text": source_text,
        "text": source_text,
        "source_section": provenance_type,
        "text_class": "background_context",
        "provenance_type": provenance_type,
        "provenance_confidence": "high",
        "provenance_signals": ["front_matter_isolation"],
        "is_reject_or_low_trust": True,
        "is_primary_admissible": False,
        "is_secondary_or_context": False,
        "extraction_blocked_reason": blocked_reason,
    }


def _contains_known_metadata_key(front_matter: str) -> bool:
    normalized = _normalize(front_matter)
    return any(key in normalized for key in KNOWN_METADATA_KEYS)


def _first_body_boundary(text: str) -> int | None:
    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)

    boundary_patterns = (
        r"^\s*abstract\s*$",
        r"^\s*a\s*b\s*s\s*t\s*r\s*a\s*c\s*t\s*$",
        r"^\s*1\.?\s+introduction\b",
        r"^\s*introduction\s*$",
        r"^\s*keywords?\s*:",
        r"^\s*article history\b",
    )
    for index, line in enumerate(lines):
        if any(re.match(pattern, line, flags=re.IGNORECASE) for pattern in boundary_patterns):
            return offsets[index]

    title_boundary = _title_author_boundary(lines, offsets)
    if title_boundary is not None:
        return title_boundary
    return None


def _title_author_boundary(lines: list[str], offsets: list[int]) -> int | None:
    for index in range(0, max(0, len(lines) - 1)):
        title = lines[index].strip()
        authors = lines[index + 1].strip()
        if not title or not authors:
            continue
        if _is_cover_signal_line(title) or _is_cover_signal_line(authors):
            continue
        if not (12 <= len(title) <= 180):
            continue
        if title.endswith(":") or re.match(r"^(?:recommended citation|abstract|keywords?)\b", title, re.IGNORECASE):
            continue
        if _looks_like_author_line(authors):
            return offsets[index]
    return None


def _looks_like_author_line(line: str) -> bool:
    if "," in line and len(line.split()) <= 30:
        return True
    if re.search(r"\b(?:and|&)\b", line, flags=re.IGNORECASE) and len(line.split()) <= 30:
        return True
    return bool(re.search(r"[A-Z][a-z]+(?:\s+[A-Z]\.?\s*)+[A-Z][a-z]+", line))


def _is_cover_signal_line(line: str) -> bool:
    normalized = _normalize(line)
    return any(signal in normalized for signal in REPOSITORY_COVER_SIGNALS)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()
