"""Section-heading context helpers for Markdown and Docling records."""

from __future__ import annotations

import re
from typing import Any


SECTION_LABELS = {
    "title",
    "abstract",
    "introduction",
    "methods",
    "experimental",
    "results",
    "discussion",
    "results_and_discussion",
    "conclusion",
    "supplementary",
    "references",
    "unknown",
}

INHERITABLE_SECTION_LABELS = SECTION_LABELS - {"title", "abstract", "unknown"}


def normalize_heading(text: str) -> str:
    """Normalize a section heading while preserving human-readable words."""

    value = str(text or "").strip()
    value = re.sub(r"^\s{0,3}#{1,6}\s*", "", value)
    value = re.sub(r"\s+#{1,6}\s*$", "", value)
    value = re.sub(r"^[*_`]+|[*_`]+$", "", value.strip())
    value = re.sub(r"^\s*(?:section\s+)?(?:\d+(?:\.\d+)*|[ivxlcdm]+)[.)]?\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" \t\r\n:.;")
    tokens = [token.strip(" .") for token in value.split()]
    if len(tokens) >= 3 and all(len(token) == 1 and token.isalpha() for token in tokens):
        value = "".join(tokens)
    return re.sub(r"\s+", " ", value.casefold()).strip(" \t\r\n:.;")


def classify_section_heading(text: str) -> str:
    """Classify a normalized section heading into a supported section label."""

    normalized = normalize_heading(text)
    if not normalized:
        return "unknown"
    if normalized in {"title", "paper title", "article title"}:
        return "title"
    if normalized in {"abstract", "summary"} or normalized.startswith("abstract "):
        return "abstract"
    if normalized in {"introduction", "background"} or normalized.startswith("introduction "):
        return "introduction"
    if re.search(r"\bresults?\s+(?:and|&)\s+discussion\b", normalized):
        return "results_and_discussion"
    if re.search(r"\bdiscussion\s+(?:and|&)\s+results?\b", normalized):
        return "results_and_discussion"
    if normalized in {"results", "result"} or normalized.startswith(("results ", "result ")):
        return "results"
    if normalized in {"discussion", "discussions"} or normalized.startswith("discussion "):
        return "discussion"
    if normalized in {
        "experimental",
        "experiment",
        "methods",
        "method",
        "materials and methods",
        "experimental section",
        "experimental methods",
        "methods and materials",
    }:
        return "methods"
    if normalized.startswith(("experimental ", "methods ", "materials and methods ")):
        return "methods"
    if normalized in {"conclusion", "conclusions", "concluding remarks"}:
        return "conclusion"
    if normalized.startswith(("conclusion ", "conclusions ")):
        return "conclusion"
    if normalized in {"references", "reference", "bibliography", "literature cited"}:
        return "references"
    if normalized.startswith(("references ", "bibliography ", "literature cited ")):
        return "references"
    if normalized in {
        "supporting information",
        "supplementary",
        "supplemental",
        "supplementary information",
        "supplemental information",
    }:
        return "supplementary"
    if normalized.startswith(("supporting information ", "supplementary ", "supplemental ")):
        return "supplementary"
    return "unknown"


def extract_markdown_section_blocks(markdown_text: str) -> list[dict[str, Any]]:
    """Return section blocks inferred from Markdown headings and plain section lines."""

    source = str(markdown_text or "")
    headings = _markdown_headings(source)
    if not headings:
        return apply_section_type_inheritance([
            {
                "section_heading": "",
                "section_path": [],
                "section_level": 0,
                "section_type": "unknown",
                "section_start_offset": 0,
                "section_end_offset": len(source),
                "section_confidence": "low",
                "section_signals": ["no_markdown_heading"],
            }
        ])

    blocks: list[dict[str, Any]] = []
    if headings[0]["start"] > 0:
        blocks.append(
            {
                "section_heading": "",
                "section_path": [],
                "section_level": 0,
                "section_type": "unknown",
                "section_start_offset": 0,
                "section_end_offset": headings[0]["start"],
                "section_confidence": "low",
                "section_signals": ["pre_heading_text"],
            }
        )

    stack: list[dict[str, Any]] = []
    for index, heading in enumerate(headings):
        level = int(heading["level"])
        while stack and int(stack[-1]["level"]) >= level:
            stack.pop()
        section_type = str(heading["section_type"])
        if index == 0 and level == 1 and section_type == "unknown":
            section_type = "title"
        stack.append({"level": level, "heading": heading["heading"], "section_type": section_type})
        path = [str(item["heading"]) for item in stack if str(item.get("heading") or "").strip()]
        end_offset = int(headings[index + 1]["start"]) if index + 1 < len(headings) else len(source)
        signals = list(heading["signals"])
        if section_type != "unknown":
            signals.append(f"recognized_section:{section_type}")
        blocks.append(
            {
                "section_heading": heading["heading"],
                "section_path": path,
                "section_level": level,
                "section_type": section_type,
                "section_start_offset": int(heading["start"]),
                "section_end_offset": end_offset,
                "section_confidence": _section_block_confidence(section_type, signals),
                "section_signals": signals,
            }
        )
    return apply_section_type_inheritance(blocks)


def apply_section_type_inheritance(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Layer direct and effective section types using only the heading hierarchy.

    Unknown child headings may inherit from the nearest recognized semantic
    ancestor.  Same-level headings, unheaded preambles, and broken Markdown
    level jumps never inherit.  Title and abstract are deliberately excluded
    from inheritance so that front matter cannot leak into the main body.
    """

    layered: list[dict[str, Any]] = []
    heading_stack: list[int] = []
    semantic_origin: dict[int, tuple[int, int]] = {}
    for source_index, original in enumerate(blocks):
        block = dict(original)
        heading = str(block.get("section_heading") or block.get("raw_heading") or "")
        level = int(block.get("section_level") or 0)
        direct = str(block.get("direct_section_type") or block.get("section_type") or "unknown")
        if direct not in SECTION_LABELS:
            direct = classify_section_heading(heading)
        direct_confidence = str(
            block.get("direct_section_type_confidence")
            or block.get("section_confidence")
            or _section_block_confidence(direct, _list_values(block.get("section_signals")))
        )
        warnings = _list_values(block.get("section_inheritance_warnings"))

        while heading_stack and int(layered[heading_stack[-1]].get("section_level") or 0) >= level:
            heading_stack.pop()
        parent_index = heading_stack[-1] if heading and level > 0 and heading_stack else None

        inherited = None
        inherited_from_index = None
        distance = None
        effective = direct
        effective_confidence = direct_confidence
        if direct == "unknown" and heading and level > 0 and parent_index is not None:
            parent = layered[parent_index]
            parent_level = int(parent.get("section_level") or 0)
            if level != parent_level + 1:
                warnings.append("section_inheritance_unresolved")
            else:
                parent_effective = str(parent.get("effective_section_type") or "unknown")
                if parent_effective in INHERITABLE_SECTION_LABELS:
                    origin_index, parent_distance = semantic_origin.get(parent_index, (parent_index, 0))
                    inherited = parent_effective
                    inherited_from_index = origin_index
                    distance = parent_distance + 1
                    effective = inherited
                    effective_confidence = "medium" if distance == 1 else "low"

        block.update(
            {
                "raw_heading": heading,
                "normalized_heading": normalize_heading(heading),
                "direct_section_type": direct,
                "direct_section_type_confidence": direct_confidence,
                "inherited_section_type": inherited,
                "inherited_from_source_section_index": inherited_from_index,
                "inheritance_distance": distance,
                "effective_section_type": effective,
                "effective_section_type_confidence": effective_confidence,
                "section_type": effective,
                "section_inheritance_warnings": _dedupe(warnings),
            }
        )
        layered.append(block)

        current_index = len(layered) - 1
        if direct in INHERITABLE_SECTION_LABELS:
            semantic_origin[current_index] = (current_index, 0)
        elif effective in INHERITABLE_SECTION_LABELS and inherited_from_index is not None:
            semantic_origin[current_index] = (inherited_from_index, int(distance or 0))
        if heading and level > 0:
            heading_stack.append(current_index)
    return layered


def attach_section_context_to_records(
    records: list[dict[str, Any]],
    markdown_by_document: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Attach nearest section context to records, preferring explicit Docling data."""

    markdown_by_document = markdown_by_document or {}
    block_cache = {str(key): extract_markdown_section_blocks(value) for key, value in markdown_by_document.items()}
    attached: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        context = _explicit_record_section_context(item)
        if context is None:
            context = _markdown_record_section_context(item, markdown_by_document, block_cache)
        if context is not None:
            _copy_section_context(item, context)
        confidence, rationale = infer_section_confidence(item)
        item.setdefault("section_confidence", confidence)
        item.setdefault("section_signals", [])
        if rationale:
            item["section_confidence_rationale"] = rationale
        attached.append(item)
    return attached


def infer_section_confidence(record: dict[str, Any]) -> tuple[str, list[str]]:
    """Infer confidence contributed by section context."""

    section_type = str(record.get("section_type") or "")
    if section_type not in SECTION_LABELS or section_type == "unknown":
        section_type = classify_section_heading(_first_text(record, "section_heading", "source_section", "section"))
    signals = _list_values(record.get("section_signals"))
    rationale: list[str] = []
    if section_type == "unknown":
        rationale.append("body_without_section_context")
        return "low", rationale

    explicit = any(
        "docling" in signal
        or "markdown_heading" in signal
        or "plain_heading" in signal
        or "record_section_label" in signal
        for signal in signals
    )
    inherited = any("inherited_markdown_section" in signal for signal in signals)
    if section_type == "abstract":
        rationale.append("abstract_section_context")
        return ("high" if explicit or inherited else "medium"), rationale
    if section_type in {"results", "methods", "discussion", "results_and_discussion"}:
        rationale.append(f"{section_type}_section_context")
        return ("high" if explicit or inherited else "medium"), rationale
    if section_type in {"introduction", "conclusion", "supplementary", "title", "experimental"}:
        rationale.append(f"recognized_{section_type}_section_context")
        return "medium", rationale
    rationale.append("recognized_section_context")
    return "medium", rationale


def _markdown_headings(source: str) -> list[dict[str, Any]]:
    lines = source.splitlines(keepends=True)
    headings: list[dict[str, Any]] = []
    offset = 0
    consumed_setext_lines: set[int] = set()
    for index, line in enumerate(lines):
        raw_line = line.rstrip("\r\n")
        stripped = raw_line.strip()
        if index in consumed_setext_lines:
            offset += len(line)
            continue
        atx = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", raw_line)
        if atx:
            headings.append(_heading_record(atx.group(2), len(atx.group(1)), offset, "markdown_heading"))
            offset += len(line)
            continue
        if index + 1 < len(lines) and re.match(r"^\s*(?:=+|-+)\s*$", lines[index + 1].strip()):
            if _plain_heading_candidate(stripped):
                underline = lines[index + 1].strip()
                headings.append(_heading_record(stripped, 1 if underline.startswith("=") else 2, offset, "setext_heading"))
                consumed_setext_lines.add(index + 1)
            offset += len(line)
            continue
        if _plain_heading_candidate(stripped):
            headings.append(_heading_record(stripped, 2, offset, "plain_heading"))
        offset += len(line)
    return headings


def _heading_record(heading: str, level: int, start: int, signal: str) -> dict[str, Any]:
    return {
        "heading": _clean_heading_text(heading),
        "level": level,
        "start": start,
        "section_type": classify_section_heading(heading),
        "signals": [signal],
    }


def _plain_heading_candidate(line: str) -> bool:
    if not line or len(line) > 140:
        return False
    if "|" in line or line.startswith((">", "-", "*", "+")):
        return False
    if line.endswith(".") and classify_section_heading(line) not in {"references"}:
        return False
    if len(line.split()) > 12:
        return False
    return classify_section_heading(line) != "unknown"


def _section_block_confidence(section_type: str, signals: list[str]) -> str:
    if section_type == "unknown":
        return "low"
    if section_type in {"abstract", "methods", "results", "discussion", "results_and_discussion"}:
        return "high"
    if any(signal in {"markdown_heading", "plain_heading", "setext_heading"} for signal in signals):
        return "medium"
    return "low"


def _explicit_record_section_context(record: dict[str, Any]) -> dict[str, Any] | None:
    path = _section_path(record)
    heading = _first_text(record, "section_heading", "section_title", "heading")
    if not heading and path:
        heading = path[-1]
    if not heading:
        source_section = _first_text(record, "source_section", "section")
        if source_section and source_section.casefold() not in {"unknown", "body"}:
            heading = source_section
    section_type = str(record.get("section_type") or "").strip()
    if section_type not in SECTION_LABELS:
        section_type = classify_section_heading(heading)
    if not heading and section_type == "unknown":
        return None

    signals = _list_values(record.get("section_signals"))
    if path or any(key in record for key in ("hierarchy", "parent", "section_title", "heading")):
        signals.append("docling_hierarchy")
    elif heading:
        signals.append("record_section_label")
    if section_type != "unknown":
        signals.append(f"recognized_section:{section_type}")
    context = {
        "section_heading": heading,
        "section_path": path or ([heading] if heading else []),
        "section_level": _section_level(record, path),
        "section_type": section_type,
        "section_start_offset": record.get("section_start_offset"),
        "section_end_offset": record.get("section_end_offset"),
        "section_signals": _dedupe(signals),
    }
    context["section_confidence"], rationale = infer_section_confidence(context)
    context["section_confidence_rationale"] = rationale
    return apply_section_type_inheritance([context])[0]


def _markdown_record_section_context(
    record: dict[str, Any],
    markdown_by_document: dict[str, str],
    block_cache: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    key = _document_key(record, markdown_by_document)
    if not key:
        return None
    blocks = block_cache.get(key) or []
    markdown = markdown_by_document.get(key, "")
    if not blocks:
        return None
    start = _record_start_offset(record, markdown)
    if start is None:
        return None
    for block in blocks:
        block_start = int(block.get("section_start_offset") or 0)
        block_end = int(block.get("section_end_offset") or len(markdown))
        if block_start <= start < block_end:
            context = dict(block)
            signals = _list_values(context.get("section_signals"))
            signals.append("inherited_markdown_section")
            context["section_signals"] = _dedupe(signals)
            context["section_confidence"], rationale = infer_section_confidence(context)
            context["section_confidence_rationale"] = rationale
            return context
    return None


def _document_key(record: dict[str, Any], markdown_by_document: dict[str, str]) -> str:
    for key in ("document_id", "paper_id", "path"):
        value = str(record.get(key) or "").strip()
        if value in markdown_by_document:
            return value
    if len(markdown_by_document) == 1:
        return next(iter(markdown_by_document))
    return ""


def _record_start_offset(record: dict[str, Any], markdown: str) -> int | None:
    for key in ("source_start_offset", "start_offset", "char_start", "start"):
        value = record.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value)
    text = _first_text(record, "source_text", "source_span", "text")
    if text:
        index = markdown.find(text)
        if index >= 0:
            record.setdefault("source_start_offset", index)
            record.setdefault("source_end_offset", index + len(text))
            return index
    return None


def _section_path(record: dict[str, Any]) -> list[str]:
    value = record.get("section_path") or record.get("hierarchy") or record.get("parent")
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict):
        pieces: list[str] = []
        for key in ("section", "title", "name", "heading"):
            text = str(value.get(key) or "").strip()
            if text:
                pieces.append(text)
        return pieces
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in re.split(r"\s*>\s*|\s*/\s*", value) if part.strip()]
    return []


def _section_level(record: dict[str, Any], path: list[str]) -> int:
    value = record.get("section_level") or record.get("level")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return len(path) if path else 0


def _copy_section_context(target: dict[str, Any], context: dict[str, Any]) -> None:
    for key in (
        "section_heading",
        "raw_heading",
        "normalized_heading",
        "section_path",
        "section_level",
        "direct_section_type",
        "direct_section_type_confidence",
        "inherited_section_type",
        "inherited_from_source_section_index",
        "inheritance_distance",
        "effective_section_type",
        "effective_section_type_confidence",
        "section_type",
        "section_inheritance_warnings",
        "section_start_offset",
        "section_end_offset",
        "section_confidence",
        "section_signals",
        "section_confidence_rationale",
    ):
        if key in context and context.get(key) not in (None, ""):
            target[key] = context[key]


def _first_text(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _clean_heading_text(text: str) -> str:
    value = str(text or "").strip()
    value = re.sub(r"^\s{0,3}#{1,6}\s*", "", value)
    value = re.sub(r"\s+#{1,6}\s*$", "", value)
    return value.strip(" \t\r\n")


def _list_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value]
    return []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
