"""Heuristic document-provenance rules for eNH3-BoundaryLedger."""

from __future__ import annotations

import re
from typing import Any

from enh3bench.front_matter import (
    is_repository_cover_page_text,
    split_yaml_front_matter,
    strip_conversion_front_matter,
)
from enh3bench.section_context import classify_section_heading, infer_section_confidence


PROVENANCE_TYPES = (
    "body",
    "abstract",
    "methods",
    "results",
    "discussion",
    "table",
    "review_table",
    "figure_caption",
    "scheme_caption",
    "reference",
    "bibliography",
    "supplementary",
    "front_matter",
    "metadata",
    "copyright_note",
    "unknown",
)

PRIMARY_ADMISSIBLE_PROVENANCE = (
    "body",
    "abstract",
    "methods",
    "results",
    "discussion",
)

SECONDARY_OR_CONTEXT_PROVENANCE = (
    "table",
    "review_table",
    "figure_caption",
    "scheme_caption",
    "supplementary",
)

REJECT_OR_LOW_TRUST_PROVENANCE = (
    "reference",
    "bibliography",
    "front_matter",
    "metadata",
    "copyright_note",
)


def normalize_provenance_type(value: str) -> str:
    """Normalize a provenance label to a supported value."""

    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").casefold()).strip("_")
    aliases = {
        "": "unknown",
        "text": "body",
        "paragraph": "body",
        "section": "body",
        "main_text": "body",
        "result": "results",
        "experimental": "methods",
        "experimental_section": "methods",
        "method": "methods",
        "materials_and_methods": "methods",
        "fig": "figure_caption",
        "figure": "figure_caption",
        "caption": "figure_caption",
        "picture": "figure_caption",
        "scheme": "scheme_caption",
        "table_caption": "table",
        "references": "reference",
        "citation": "reference",
        "literature_cited": "bibliography",
        "bib": "bibliography",
        "supporting_information": "supplementary",
        "si": "supplementary",
        "supplement": "supplementary",
        "frontmatter": "front_matter",
        "front": "front_matter",
        "copyright": "copyright_note",
    }
    candidate = aliases.get(normalized, normalized)
    if candidate in PROVENANCE_TYPES:
        return candidate
    return "unknown"


def is_primary_admissible(provenance_type: str) -> bool:
    return normalize_provenance_type(provenance_type) in PRIMARY_ADMISSIBLE_PROVENANCE


def is_secondary_or_context(provenance_type: str) -> bool:
    return normalize_provenance_type(provenance_type) in SECONDARY_OR_CONTEXT_PROVENANCE


def is_low_trust_provenance(provenance_type: str) -> bool:
    """Return True when provenance cannot establish primary evidence by itself."""

    normalized = normalize_provenance_type(provenance_type)
    if normalized in REJECT_OR_LOW_TRUST_PROVENANCE:
        return True
    if normalized != "unknown":
        return False
    raw = str(provenance_type or "").casefold()
    return any(
        signal in raw
        for signal in (
            "reference",
            "bibliography",
            "front_matter",
            "front matter",
            "metadata",
            "copyright",
        )
    )


def low_trust_reason(provenance_type: str) -> str:
    """Explain why a provenance type is constrained as low trust."""

    if not is_low_trust_provenance(provenance_type):
        return ""
    normalized = normalize_provenance_type(provenance_type)
    if normalized == "reference":
        return "Reference-list text cannot establish a primary experimental boundary."
    if normalized == "bibliography":
        return "Bibliography text cannot establish a primary experimental boundary."
    if normalized == "front_matter":
        return "Front-matter text cannot establish a primary experimental boundary."
    if normalized == "metadata":
        return "Metadata text cannot establish a primary experimental boundary."
    if normalized == "copyright_note":
        return "Copyright or conversion-note text cannot establish a primary experimental boundary."
    return "Explicit low-trust provenance signal cannot establish a primary experimental boundary."


def is_reject_or_low_trust(provenance_type: str) -> bool:
    return is_low_trust_provenance(provenance_type)


def infer_provenance_from_text(
    text: str,
    section: str | None = None,
    raw_record: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Infer document provenance from text, section labels, and optional record metadata."""

    raw_record = raw_record or {}
    source_text = str(text or "")
    normalized = _normalize(source_text)
    section_text = _normalize(
        section
        or raw_record.get("section_heading")
        or raw_record.get("source_section")
        or raw_record.get("section")
        or ""
    )
    signals: list[str] = []

    explicit = _explicit_record_provenance(raw_record)
    if explicit:
        signals.append("explicit record provenance")
        return _result(explicit, "high", signals, ["explicit_record_provenance"])

    if contains_mixed_front_matter_and_body(source_text):
        stripped = strip_conversion_front_matter(source_text)
        body_text = str(stripped.get("body_text") or "").strip()
        if body_text:
            body_result = infer_provenance_from_text(body_text, section, {key: value for key, value in raw_record.items() if key != "provenance_type"})
            body_result["signals"] = ["mixed_front_matter_body_detected", *body_result.get("signals", [])]
            return body_result

    yaml_metadata, yaml_body = split_yaml_front_matter(source_text)
    if yaml_metadata is not None and not yaml_body.strip():
        return _result("metadata", "high", ["isolated YAML/Docling metadata"], ["isolated_metadata"])

    if is_repository_cover_page_text(source_text) and not strip_conversion_front_matter(source_text).get("body_text"):
        return _result("front_matter", "high", ["isolated repository front matter"], ["isolated_front_matter"])

    if _copyright_note(normalized, raw_record):
        signals.append("copyright or conversion-use note")
        return _result("copyright_note", "high", signals, ["copyright_or_conversion_note"])

    metadata_score, metadata_signals = _metadata_score(source_text, normalized, raw_record)
    if metadata_score >= 3:
        signals.extend(metadata_signals)
        provenance_type = "front_matter" if _near_beginning_or_front_matter(source_text, raw_record) else "metadata"
        return _result(provenance_type, "high", signals, ["metadata_score_high"])
    if metadata_score >= 1 and _near_beginning_or_front_matter(source_text, raw_record):
        signals.extend(metadata_signals)
        return _result("front_matter", "medium", signals, ["metadata_score_near_beginning"])

    reference_score, reference_signals = _reference_score(source_text, normalized, section_text)
    if reference_score >= 4:
        signals.extend(reference_signals)
        provenance_type = "bibliography" if "bibliography" in section_text or "literature cited" in section_text else "reference"
        return _result(provenance_type, "high", signals, ["reference_section_or_list_signal"])
    if reference_score >= 2 and "reference" in section_text:
        signals.extend(reference_signals)
        return _result("reference", "high", signals, ["reference_section_label"])

    caption_type, caption_confidence, caption_signals = _caption_signal(source_text, normalized)
    if caption_type:
        signals.extend(caption_signals)
        return _result(caption_type, caption_confidence, signals, ["caption_signal"])

    table_score, table_signals = _table_score(source_text, normalized)
    if table_score >= 2:
        signals.extend(table_signals)
        if _looks_like_review_table(source_text, normalized):
            signals.append("literature-comparison table")
            return _result("review_table", "high", signals, ["review_table_signal"])
        return _result("table", "high" if table_score >= 3 else "medium", signals, ["table_signal"])

    if _supplementary_signal(normalized, section_text):
        signals.append("supplementary or supporting-information signal")
        return _result("supplementary", "medium", signals, ["supplementary_signal"])

    section_type = _section_provenance(section_text, normalized, raw_record)
    if section_type != "unknown":
        signals.append(f"section signal: {section_text or section_type}")
        section_record = dict(raw_record)
        section_record.setdefault("section_type", section_type)
        if section and not section_record.get("section_heading"):
            section_record["section_heading"] = section
        section_record.setdefault("section_signals", [])
        section_signals = list(section_record.get("section_signals") or [])
        if section_text and "record_section_label" not in section_signals:
            section_signals.append("record_section_label")
        section_record["section_signals"] = section_signals
        confidence, rationale = infer_section_confidence(section_record)
        return _result(_provenance_from_section_type(section_type), confidence, signals + rationale, rationale)

    if source_text.strip():
        signals.append("non-empty text without table/caption/reference metadata signal")
        return _result("body", "low", signals, ["body_without_section_context"])
    return _result("unknown", "low", ["empty source text"], ["empty_source_text"])


def contains_mixed_front_matter_and_body(text: str) -> bool:
    """Return True when conversion front matter is glued to scientific body text."""

    stripped = strip_conversion_front_matter(text)
    if not (stripped.get("metadata_removed") or stripped.get("repository_cover_removed")):
        return False
    body_text = str(stripped.get("body_text") or "").strip()
    if not body_text:
        return False
    metadata_text = str(stripped.get("metadata_text") or stripped.get("repository_cover_text") or "")
    if not metadata_text.strip():
        return False
    return _has_scientific_body_boundary(body_text)


def _result(
    provenance_type: str,
    confidence: str,
    signals: list[str],
    rationale: list[str] | None = None,
) -> dict[str, Any]:
    normalized = normalize_provenance_type(provenance_type)
    return {
        "provenance_type": normalized,
        "confidence": confidence if confidence in {"low", "medium", "high"} else "low",
        "signals": signals,
        "provenance_confidence_rationale": rationale or [],
        "is_primary_admissible": is_primary_admissible(normalized),
        "is_secondary_or_context": is_secondary_or_context(normalized),
        "is_reject_or_low_trust": is_reject_or_low_trust(normalized),
    }


def _explicit_record_provenance(record: dict[str, Any]) -> str:
    for key in ("provenance_type", "docling_label", "block_type", "label"):
        value = record.get(key)
        if value is None:
            continue
        normalized = normalize_provenance_type(str(value))
        if normalized not in {"unknown", "body"}:
            return normalized
    return ""


def _metadata_score(text: str, normalized: str, record: dict[str, Any]) -> tuple[int, list[str]]:
    signals: list[str] = []
    score = 0
    metadata_keys = [
        "source_file:",
        "conversion_method:",
        "human_verification_required",
        "copyright_note",
        "document_id:",
        "created_at:",
        "source_format:",
        "conversion_status:",
    ]
    hits = [key for key in metadata_keys if key in normalized]
    if hits:
        score += len(hits)
        signals.append("YAML/Docling metadata keys: " + ", ".join(hits[:5]))
    metadata_lines = sum(1 for line in text.splitlines() if re.match(r"^\s*[A-Za-z0-9_\-]+:\s*", line))
    if metadata_lines >= 3:
        score += 2
        signals.append("repeated metadata-like lines")
    if record.get("source_section") in {"front_matter", "metadata"}:
        score += 2
        signals.append("record source_section metadata/front_matter")
    return score, signals


def _near_beginning_or_front_matter(text: str, record: dict[str, Any]) -> bool:
    span_id = str(record.get("span_id") or record.get("source_span_id") or "")
    page = record.get("page")
    if str(page).strip() in {"1", "0"}:
        return True
    if re.search(r"(?:^|[_-])s?0{0,2}1$", span_id.casefold()):
        return True
    stripped = text.lstrip()
    return stripped.startswith("---") or stripped.startswith("{")


def _copyright_note(normalized: str, record: dict[str, Any]) -> bool:
    return "copyright_note" in normalized or "do not publish full copyrighted text" in normalized or record.get("provenance_type") == "copyright_note"


def _reference_score(text: str, normalized: str, section_text: str) -> tuple[int, list[str]]:
    signals: list[str] = []
    score = 0
    if any(label in section_text for label in ["references", "reference", "bibliography", "literature cited"]):
        score += 3
        signals.append("reference-like section label")
    doi_hits = len(re.findall(r"\bdoi\b|10\.\d{4,9}/", normalized))
    if doi_hits >= 2:
        score += 2
        signals.append("multiple DOI strings")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    numbered = sum(1 for line in lines if re.match(r"^(?:\[\d+\]|\d+[\).])\s+", line))
    if len(lines) >= 2 and numbered >= max(2, len(lines) // 3):
        score += 3
        signals.append("numbered reference-list lines")
    et_al_hits = normalized.count("et al")
    if et_al_hits >= 3:
        score += 2
        signals.append("repeated et al. citation patterns")
    journal_patterns = len(re.findall(r"\b(?:19|20)\d{2}\b[^.\n]{0,80}\b\d{1,4}\s*[-,]\s*\d{1,5}", normalized))
    if journal_patterns >= 2:
        score += 2
        signals.append("journal year-volume-page patterns")
    author_year = len(re.findall(r"\b[A-Z][A-Za-z-]+,\s+[A-Z].{0,80}\((?:19|20)\d{2}\)", text))
    if author_year >= 2:
        score += 2
        signals.append("author-year citation-list patterns")
    return score, signals


def _caption_signal(text: str, normalized: str) -> tuple[str, str, list[str]]:
    stripped = text.strip()
    signals: list[str] = []
    if re.match(r"^(?:fig\.?|figure|extended data fig\.?|supplementary fig\.?)\s*[A-Za-z0-9.\-:)]", stripped, re.IGNORECASE):
        signals.append("figure-caption prefix")
        return "figure_caption", "high", signals
    if re.match(r"^scheme\s*[A-Za-z0-9.\-:)]", stripped, re.IGNORECASE):
        signals.append("scheme-caption prefix")
        return "scheme_caption", "high", signals
    if any(needle in normalized[:120] for needle in ["fig. ", "figure ", "extended data fig", "supplementary fig"]):
        signals.append("caption-like figure signal near start")
        return "figure_caption", "medium", signals
    if "scheme " in normalized[:120]:
        signals.append("caption-like scheme signal near start")
        return "scheme_caption", "medium", signals
    return "", "low", signals


def _table_score(text: str, normalized: str) -> tuple[int, list[str]]:
    score = 0
    signals: list[str] = []
    pipe_lines = [line for line in text.splitlines() if line.count("|") >= 2]
    delimiter_rows = [line for line in pipe_lines if re.search(r"\|\s*:?-{2,}:?\s*\|", line)]
    if len(pipe_lines) >= 2:
        score += 2
        signals.append("markdown pipe-table syntax")
    if delimiter_rows:
        score += 1
        signals.append("markdown delimiter row")
    headers = [
        "reference",
        "catalyst",
        "reactant",
        "electrolyte",
        "fe",
        "faradaic efficiency",
        "yield",
        "potential",
        "cell voltage",
        "15n",
    ]
    header_hits = [header for header in headers if header in normalized]
    has_table_label = bool(re.search(r"\btable\s+s?\d+", normalized))
    if len(header_hits) >= 4 and (pipe_lines or has_table_label):
        score += 2
        signals.append("eNH3 table headers: " + ", ".join(header_hits[:6]))
    elif len(header_hits) >= 4:
        score += 1
        signals.append("eNH3 metric/header terms without table structure")
    if has_table_label:
        score += 1
        signals.append("table label")
    return score, signals


def _looks_like_review_table(text: str, normalized: str) -> bool:
    if any(needle in normalized for needle in ["review table", "literature summary", "previous reports", "reported in previous studies"]):
        return True
    lines = [line for line in text.splitlines() if line.strip()]
    citation_rows = sum(1 for line in lines if re.search(r"\b(?:19|20)\d{2}\b|\bet al\.?", line, re.IGNORECASE))
    reference_column = "reference" in normalized and any(header in normalized for header in ["catalyst", "electrolyte", "fe", "15n"])
    return reference_column and citation_rows >= 3


def _supplementary_signal(normalized: str, section_text: str) -> bool:
    return any(
        needle in f"{section_text} {normalized[:300]}"
        for needle in ["supplementary", "supporting information", "supplementary table", "supplementary fig", " si "]
    )


def _has_scientific_body_boundary(text: str) -> bool:
    normalized = _normalize(text[:2000])
    if any(
        needle in normalized
        for needle in [
            "abstract",
            "a b s t r a c t",
            "introduction",
            "keywords",
            "article history",
            "results",
            "experimental",
            "nh3",
            "ammonia",
            "faradaic",
        ]
    ):
        return True
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return len(lines) >= 2 and len(lines[0]) >= 12


def _section_provenance(section_text: str, normalized: str, raw_record: dict[str, Any]) -> str:
    explicit_type = str(raw_record.get("section_type") or "").strip()
    if explicit_type in {
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
    }:
        return explicit_type
    heading_type = classify_section_heading(
        str(raw_record.get("section_heading") or raw_record.get("section") or raw_record.get("source_section") or section_text)
    )
    if heading_type != "unknown":
        return heading_type
    first_line = normalized.splitlines()[0] if "\n" in normalized else normalized[:120]
    first_line_type = classify_section_heading(first_line)
    if first_line_type != "unknown":
        return first_line_type
    section_blob = f"{section_text} {normalized[:120]}"
    if "abstract" in section_blob:
        return "abstract"
    if any(needle in section_blob for needle in ["results and discussion", "result and discussion"]):
        return "results_and_discussion"
    if "results" in section_blob:
        return "results"
    if "discussion" in section_blob:
        return "discussion"
    if any(needle in section_blob for needle in ["experimental", "methods", "materials and methods"]):
        return "methods"
    if any(needle in section_blob for needle in ["introduction", "conclusion", "body"]):
        return "body"
    return "unknown"


def _provenance_from_section_type(section_type: str) -> str:
    if section_type == "results_and_discussion":
        return "results"
    if section_type in {"introduction", "conclusion", "title"}:
        return "body"
    if section_type == "references":
        return "reference"
    if section_type == "experimental":
        return "methods"
    return section_type


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()
