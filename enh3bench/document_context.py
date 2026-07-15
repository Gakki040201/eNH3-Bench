"""Hierarchical, repository-local context over complete Docling Markdown documents."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from enh3bench.document_loader import load_markdown_documents
from enh3bench.section_context import extract_markdown_section_blocks
from enh3bench.span_identity import normalize_span_text


@dataclass
class DocumentContextIndex:
    documents_by_id: dict[str, dict[str, Any]]
    documents_by_paper: dict[str, list[dict[str, Any]]]
    paragraphs_by_document: dict[str, list[dict[str, Any]]]
    sections_by_document: dict[str, list[dict[str, Any]]]
    warnings: list[str]


def build_document_context_index(markdown_dir: str | Path) -> DocumentContextIndex:
    """Load each Markdown body once and derive paragraph offsets from that body."""

    root = Path(markdown_dir)
    documents_by_id: dict[str, dict[str, Any]] = {}
    documents_by_paper: dict[str, list[dict[str, Any]]] = {}
    paragraphs_by_document: dict[str, list[dict[str, Any]]] = {}
    sections_by_document: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []
    for loaded in load_markdown_documents(root):
        document_id = str(loaded["document_id"])
        if document_id in documents_by_id:
            raise ValueError(f"duplicate document_id: {document_id}")
        body = str(loaded.get("text") or "")
        sections = list(loaded.get("section_blocks") or extract_markdown_section_blocks(body))
        paragraphs = _paragraph_blocks(body, document_id, document_id, sections)
        path = Path(str(loaded.get("path") or root / f"{document_id}.md"))
        try:
            relative_path = path.resolve().relative_to(Path.cwd().resolve()).as_posix()
        except ValueError:
            relative_path = (root / path.name).as_posix()
        document = {
            "document_id": document_id,
            "paper_id": document_id,
            "relative_markdown_path": relative_path,
            "body_text_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
            "body_character_count": len(body),
            "section_blocks": sections,
            "paragraph_blocks": paragraphs,
            "front_matter_signals": list(loaded.get("front_matter_signals") or []),
            "body_text": body,
        }
        documents_by_id[document_id] = document
        documents_by_paper.setdefault(document_id, []).append(document)
        paragraphs_by_document[document_id] = paragraphs
        sections_by_document[document_id] = sections
        if not body:
            warnings.append(f"empty_document_body:{document_id}")
    return DocumentContextIndex(
        documents_by_id=documents_by_id,
        documents_by_paper=documents_by_paper,
        paragraphs_by_document=paragraphs_by_document,
        sections_by_document=sections_by_document,
        warnings=warnings,
    )


def resolve_document_for_span(record: dict[str, Any], index: DocumentContextIndex) -> dict[str, Any] | None:
    """Resolve a span only by exact document or paper identifiers."""

    document_id = str(record.get("document_id") or "").strip()
    if document_id and document_id in index.documents_by_id:
        document = index.documents_by_id[document_id]
        paper_id = str(record.get("paper_id") or "").strip()
        if not paper_id or paper_id == str(document.get("paper_id") or ""):
            return document
        return None
    paper_id = str(record.get("paper_id") or "").strip()
    matches = index.documents_by_paper.get(paper_id, [])
    return matches[0] if len(matches) == 1 else None


def resolve_span_mapping(record: dict[str, Any], index: DocumentContextIndex) -> dict[str, Any]:
    """Map a span to exact source offsets without fuzzy or first-match guessing."""

    document = resolve_document_for_span(record, index)
    warnings: list[str] = []
    if document is None:
        return _unresolved_mapping(["document_unresolved"])
    document_id = str(document["document_id"])
    body = str(document["body_text"])
    start = _offset(record.get("source_start_offset"))
    end = _offset(record.get("source_end_offset"))
    if start is not None or end is not None:
        if start is not None and end is not None and 0 <= start < end <= len(body):
            return _mapping_record(
                "explicit_offset", "high", start, end, document_id, index, warnings, []
            )
        warnings.append("invalid_explicit_offsets")

    source_text = str(record.get("source_text") or record.get("text") or "")
    if not normalize_span_text(source_text):
        return _unresolved_mapping([*warnings, "source_text_missing"], document_id=document_id)

    section_start = _offset(record.get("section_start_offset"))
    section_end = _offset(record.get("section_end_offset"))
    if section_start is not None and section_end is not None and 0 <= section_start < section_end <= len(body):
        matches = _normalized_matches(body, source_text, section_start, section_end)
        if len(matches) == 1:
            return _mapping_record(
                "section_constrained_exact", "medium", matches[0][0], matches[0][1], document_id, index, warnings, matches
            )
        if len(matches) > 1:
            return _unresolved_mapping(
                [*warnings, "multiple_exact_matches"], document_id=document_id, candidate_offsets=matches
            )

    matches = _normalized_matches(body, source_text, 0, len(body))
    if len(matches) == 1:
        return _mapping_record(
            "document_exact", "medium", matches[0][0], matches[0][1], document_id, index, warnings, matches
        )
    if len(matches) > 1:
        return _unresolved_mapping(
            [*warnings, "multiple_exact_matches"], document_id=document_id, candidate_offsets=matches
        )
    return _unresolved_mapping([*warnings, "exact_text_not_found"], document_id=document_id)


def get_local_paragraph_context(
    record: dict[str, Any], index: DocumentContextIndex, before: int = 1, after: int = 1
) -> dict[str, Any]:
    mapping = resolve_span_mapping(record, index)
    document_id = str(mapping.get("document_id") or "")
    paragraph_id = str(mapping.get("paragraph_id") or "")
    paragraphs = index.paragraphs_by_document.get(document_id, [])
    position = next((i for i, item in enumerate(paragraphs) if item["paragraph_id"] == paragraph_id), None)
    if position is None:
        return {"previous_paragraphs": [], "target_paragraph": None, "next_paragraphs": []}
    return {
        "previous_paragraphs": [dict(item) for item in paragraphs[max(0, position - max(0, before)):position]],
        "target_paragraph": dict(paragraphs[position]),
        "next_paragraphs": [dict(item) for item in paragraphs[position + 1:position + 1 + max(0, after)]],
    }


def get_section_chunk(
    record: dict[str, Any], index: DocumentContextIndex, maximum_characters: int = 12000
) -> dict[str, Any]:
    mapping = resolve_span_mapping(record, index)
    document = index.documents_by_id.get(str(mapping.get("document_id") or ""))
    if document is None or mapping.get("source_start_offset") is None:
        return {"section_chunk": "", "section_chunk_start_offset": None, "section_chunk_end_offset": None}
    body = str(document["body_text"])
    offset = int(mapping["source_start_offset"])
    section = _section_for_offset(document["section_blocks"], offset, len(body))
    if section is None:
        return {"section_chunk": "", "section_chunk_start_offset": None, "section_chunk_end_offset": None}
    start = int(section["section_start_offset"])
    end = min(int(section["section_end_offset"]), start + max(0, int(maximum_characters)))
    return {
        "section_chunk": body[start:end],
        "section_chunk_start_offset": start,
        "section_chunk_end_offset": end,
    }


def _paragraph_blocks(
    body: str, document_id: str, paper_id: str, sections: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for order, match in enumerate(re.finditer(r"\S(?:.*?)(?=\n\s*\n+|\Z)", body, flags=re.DOTALL)):
        raw = match.group(0)
        leading = len(raw) - len(raw.lstrip())
        trailing = len(raw.rstrip())
        start = match.start() + leading
        end = match.start() + trailing
        section = _section_for_offset(sections, start, len(body)) or {}
        blocks.append({
            "paragraph_id": f"{document_id}_P{order + 1:05d}",
            "document_id": document_id,
            "paper_id": paper_id,
            "paragraph_order": order + 1,
            "text": body[start:end],
            "start_offset": start,
            "end_offset": end,
            "section_heading": str(section.get("section_heading") or ""),
            "section_path": list(section.get("section_path") or []),
            "section_type": str(section.get("section_type") or "unknown"),
        })
    return blocks


def _mapping_record(
    method: str,
    confidence: str,
    start: int,
    end: int,
    document_id: str,
    index: DocumentContextIndex,
    warnings: list[str],
    candidate_offsets: list[tuple[int, int]],
) -> dict[str, Any]:
    paragraphs = index.paragraphs_by_document.get(document_id, [])
    paragraph = next((item for item in paragraphs if item["start_offset"] <= start < item["end_offset"]), None)
    sections = index.sections_by_document.get(document_id, [])
    document = index.documents_by_id[document_id]
    section = _section_for_offset(sections, start, int(document["body_character_count"])) or {}
    return {
        "method": method,
        "confidence": confidence,
        "document_id": document_id,
        "source_start_offset": start,
        "source_end_offset": end,
        "paragraph_id": paragraph.get("paragraph_id") if paragraph else None,
        "paragraph_order": paragraph.get("paragraph_order") if paragraph else None,
        "section_heading": str(section.get("section_heading") or ""),
        "section_path": list(section.get("section_path") or []),
        "candidate_offsets": [{"start_offset": a, "end_offset": b} for a, b in candidate_offsets],
        "warnings": list(dict.fromkeys(warnings)),
    }


def _unresolved_mapping(
    warnings: list[str], *, document_id: str = "", candidate_offsets: list[tuple[int, int]] | None = None
) -> dict[str, Any]:
    return {
        "method": "unresolved",
        "confidence": "unresolved",
        "document_id": document_id or None,
        "source_start_offset": None,
        "source_end_offset": None,
        "paragraph_id": None,
        "paragraph_order": None,
        "section_heading": "",
        "section_path": [],
        "candidate_offsets": [
            {"start_offset": start, "end_offset": end} for start, end in (candidate_offsets or [])
        ],
        "warnings": list(dict.fromkeys(warnings)),
    }


def _normalized_matches(body: str, source_text: str, start: int, end: int) -> list[tuple[int, int]]:
    tokens = normalize_span_text(source_text).split()
    if not tokens:
        return []
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    return [(start + match.start(), start + match.end()) for match in re.finditer(pattern, body[start:end])]


def _section_for_offset(
    sections: list[dict[str, Any]], offset: int, body_length: int
) -> dict[str, Any] | None:
    for section in sections:
        start = _offset(section.get("section_start_offset"))
        end = _offset(section.get("section_end_offset"))
        start = 0 if start is None else start
        end = body_length if end is None else end
        if start <= offset < end:
            return section
    return None


def _offset(value: Any) -> int | None:
    if value is None or isinstance(value, bool) or str(value).strip() == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None
