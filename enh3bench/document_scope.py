"""Deterministic document-scope semantics for Stage B evidence eligibility."""

from __future__ import annotations

import re
from typing import Any


SEMANTIC_ELIGIBILITY_SCHEMA_VERSION = "0.14-stage-b"

TARGET_DOCUMENT_SCOPE = "target_document"
EXTERNAL_DOCUMENT_SCOPE = "external_or_cited_work"
BACKGROUND_DOCUMENT_SCOPE = "background_or_review"
SECONDARY_DOCUMENT_SCOPE = "secondary_context"
UNCLEAR_DOCUMENT_SCOPE = "unclear"

PRIMARY_SECTIONS = {
    "abstract",
    "methods",
    "experimental",
    "results",
    "discussion",
    "conclusion",
    "conclusions",
    "supplementary",
}
LOW_TRUST_PROVENANCE = {
    "reference", "bibliography", "figure_caption", "scheme_caption", "review_table",
}
LOW_TRUST_TEXT_CLASSES = {
    "reference_list", "figure_caption", "scheme_caption", "review_table", "background_context",
}

_TARGET_CUE = re.compile(
    r"\b(?:in this (?:work|study|paper)|the present (?:work|study)|we (?:report(?:ed)?|show(?:ed)?|"
    r"demonstrat(?:e|ed)|find|found|observ(?:e|ed)|develop(?:ed)?|prepar(?:e|ed)|measur(?:e|ed)|quantif(?:y|ied))|"
    r"our (?:work|study|results?|measurements?|"
    r"experiments?|catalyst|cell)|here(?:in)? we)\b",
    re.IGNORECASE,
)
_EXTERNAL_ATTRIBUTION = re.compile(
    r"(?:\b(?:according to|as reported by|reported by|previously reported by)\b|"
    r"\b(?:[A-Z][A-Za-z'’\-]+\s+(?:and\s+co[- ]?workers|et\s+al\.?)|"
    r"previous (?:authors?|studies|work)|other (?:authors?|groups?|studies)|the literature)"
    r"[,;]?\s+(?:reported|demonstrated|showed|found|developed|achieved|observed|proposed)\b)",
)
_BACKGROUND_CUE = re.compile(
    r"\b(?:many|several|numerous|recent|earlier|prior) (?:studies|reports|works?)\b|"
    r"\b(?:it has|have) been (?:reported|shown|demonstrated)\b|"
    r"\bresearchers (?:have )?(?:reported|developed|focused|shown)\b",
    re.IGNORECASE,
)


def assess_document_scope(record: dict[str, Any]) -> dict[str, Any]:
    """Classify whether a span concerns the target document or another work.

    This is intentionally conservative.  A primary-looking claim in an
    introduction or an untyped body span is not assigned to the target paper
    unless current-work language establishes that scope.
    """

    explicit = str(record.get("document_scope") or "").strip()
    allowed = {
        TARGET_DOCUMENT_SCOPE, EXTERNAL_DOCUMENT_SCOPE, BACKGROUND_DOCUMENT_SCOPE,
        SECONDARY_DOCUMENT_SCOPE, UNCLEAR_DOCUMENT_SCOPE,
    }
    if explicit in allowed:
        return _result(
            explicit,
            "high",
            ["explicit_document_scope"],
        )

    text = _record_text(record)
    provenance = str(record.get("provenance_type") or "unknown").strip().casefold()
    text_class = str(record.get("text_class") or "unknown").strip().casefold()
    section = _section_type(record)

    if provenance in LOW_TRUST_PROVENANCE or text_class in LOW_TRUST_TEXT_CLASSES:
        return _result(SECONDARY_DOCUMENT_SCOPE, "high", ["secondary_context_provenance"])
    if _EXTERNAL_ATTRIBUTION.search(text):
        return _result(EXTERNAL_DOCUMENT_SCOPE, "high", ["explicit_external_attribution"])
    if _BACKGROUND_CUE.search(text):
        return _result(BACKGROUND_DOCUMENT_SCOPE, "high", ["background_or_literature_synthesis"])
    if _TARGET_CUE.search(text):
        return _result(TARGET_DOCUMENT_SCOPE, "high", ["explicit_current_work_cue"])
    if section in PRIMARY_SECTIONS or provenance in PRIMARY_SECTIONS:
        return _result(
            TARGET_DOCUMENT_SCOPE,
            "medium",
            [f"current_paper_section:{section if section != 'unknown' else provenance}"],
        )
    if section in {"introduction", "background", "related_work", "literature_review"}:
        return _result(UNCLEAR_DOCUMENT_SCOPE, "low", [f"unowned_background_section:{section}"])
    if provenance == "body" and section in {"unknown", "title"}:
        return _result(TARGET_DOCUMENT_SCOPE, "medium", [f"current_paper_{section}_body"])
    return _result(UNCLEAR_DOCUMENT_SCOPE, "low", ["no_document_scope_signal"])


def document_scope_allows_primary(record_or_assessment: dict[str, Any]) -> bool:
    """Return whether document scope permits primary claim applicability."""

    if "document_scope_primary_applicable" in record_or_assessment:
        return bool(record_or_assessment.get("document_scope_primary_applicable"))
    return assess_document_scope(record_or_assessment)["document_scope_primary_applicable"]


def classify_document_scope(record: dict[str, Any]) -> dict[str, Any]:
    """Compatibility-friendly classifier name for callers that prefer classify_* APIs."""

    return assess_document_scope(record)


def _result(scope: str, confidence: str, signals: list[str]) -> dict[str, Any]:
    return {
        "semantic_eligibility_schema_version": SEMANTIC_ELIGIBILITY_SCHEMA_VERSION,
        "document_scope": scope,
        "document_scope_confidence": confidence,
        "document_scope_signals": signals,
        "document_scope_primary_applicable": scope == TARGET_DOCUMENT_SCOPE,
    }


def _section_type(record: dict[str, Any]) -> str:
    for key in (
        "effective_section_type", "target_effective_section_type", "section_type",
        "target_section_type", "direct_section_type", "target_direct_section_type",
    ):
        value = str(record.get(key) or "").strip().casefold().replace(" ", "_")
        if value and value != "unknown":
            return value
    return "unknown"


def _record_text(record: dict[str, Any]) -> str:
    for key in ("source_text", "target_text", "text", "source_span"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return ""
