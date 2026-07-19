"""Deterministic claim-ownership semantics for Stage B evidence eligibility."""

from __future__ import annotations

import re
from typing import Any

from enh3bench.document_scope import (
    BACKGROUND_DOCUMENT_SCOPE,
    EXTERNAL_DOCUMENT_SCOPE,
    SECONDARY_DOCUMENT_SCOPE,
    SEMANTIC_ELIGIBILITY_SCHEMA_VERSION,
    TARGET_DOCUMENT_SCOPE,
    assess_document_scope,
    has_external_attribution,
)


TARGET_AUTHORS = "target_authors"
EXTERNAL_AUTHORS = "external_or_cited_authors"
GENERAL_LITERATURE = "general_literature"
SECONDARY_OWNER = "secondary_context"
UNCLEAR_OWNER = "unclear"

_TARGET_OWNER_CUE = re.compile(
    r"\b(?:we|our|in this (?:work|study|paper)|the present (?:work|study)|here(?:in)? we)\b",
    re.IGNORECASE,
)


def assess_claim_ownership(
    record: dict[str, Any],
    document_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assign a claim to target authors, cited authors, or no safe owner."""

    explicit = str(record.get("claim_ownership") or record.get("claim_owner") or "").strip()
    allowed = {TARGET_AUTHORS, EXTERNAL_AUTHORS, GENERAL_LITERATURE, SECONDARY_OWNER, UNCLEAR_OWNER}
    if explicit in allowed:
        return _result(explicit, "high", ["explicit_claim_ownership"])

    text = _record_text(record)
    scope = document_scope or assess_document_scope(record)
    scope_value = str(scope.get("span_claim_scope") or scope.get("document_scope") or "unclear")

    # Citation syntax has precedence over current-document defaults.
    if has_external_attribution(text):
        return _result(EXTERNAL_AUTHORS, "high", ["explicit_external_claim_owner"])
    if scope_value == EXTERNAL_DOCUMENT_SCOPE:
        return _result(EXTERNAL_AUTHORS, "high", ["external_span_claim_scope"])
    if scope_value == BACKGROUND_DOCUMENT_SCOPE:
        return _result(GENERAL_LITERATURE, "high", ["background_span_claim_scope"])
    if scope_value == SECONDARY_DOCUMENT_SCOPE:
        return _result(SECONDARY_OWNER, "high", ["secondary_span_claim_scope"])
    if _TARGET_OWNER_CUE.search(text):
        return _result(TARGET_AUTHORS, "high", ["explicit_target_author_cue"])
    if scope_value == TARGET_DOCUMENT_SCOPE:
        return _result(TARGET_AUTHORS, "medium", ["target_document_span_claim_scope"])
    return _result(UNCLEAR_OWNER, "low", ["no_claim_owner_signal"])


def claim_ownership_allows_primary(record_or_assessment: dict[str, Any]) -> bool:
    """Return whether claim ownership permits primary claim applicability."""

    if "claim_ownership_primary_applicable" in record_or_assessment:
        return bool(record_or_assessment.get("claim_ownership_primary_applicable"))
    return assess_claim_ownership(record_or_assessment)["claim_ownership_primary_applicable"]


def classify_claim_ownership(record: dict[str, Any]) -> dict[str, Any]:
    """Compatibility-friendly classifier name for callers that prefer classify_* APIs."""

    return assess_claim_ownership(record)


def _result(owner: str, confidence: str, signals: list[str]) -> dict[str, Any]:
    return {
        "semantic_eligibility_schema_version": SEMANTIC_ELIGIBILITY_SCHEMA_VERSION,
        "claim_ownership": owner,
        "claim_ownership_confidence": confidence,
        "claim_ownership_signals": signals,
        "claim_ownership_primary_applicable": owner == TARGET_AUTHORS,
    }


def _record_text(record: dict[str, Any]) -> str:
    for key in ("source_text", "target_text", "text", "source_span"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return ""
