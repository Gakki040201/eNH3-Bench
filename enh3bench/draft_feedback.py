"""Rule-based feedback for machine-drafted evidence records."""

from __future__ import annotations

import re
from typing import Any


def generate_feedback(
    draft: dict[str, Any],
    grounding_result: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate machine feedback items for one draft record."""

    grounding_by_field = _grounding_by_field(grounding_result)
    feedback: list[dict[str, Any]] = []

    if draft.get("faradaic_efficiency_percent") is not None and not _explicit(grounding_by_field, "faradaic_efficiency_percent"):
        feedback.append(_item("high", "faradaic_efficiency_percent", "FE extracted but no explicit FE pattern found.", "Verify FE value and source wording."))

    if draft.get("isotope_validation") == "yes" and not _explicit(grounding_by_field, "isotope_validation"):
        feedback.append(_item("high", "isotope_validation", "isotope_validation=yes but no explicit 15N/isotope marker found.", "Downgrade to unclear unless the source explicitly supports isotope validation."))

    if draft.get("blank_control") == "yes" and not _explicit(grounding_by_field, "blank_control"):
        feedback.append(_item("medium", "blank_control", "blank_control=yes but no explicit blank/control wording found.", "Verify blank-control support."))

    if draft.get("contamination_control") == "yes" and not _explicit(grounding_by_field, "contamination_control"):
        feedback.append(_item("high", "contamination_control", "contamination_control=yes but no explicit contamination-control wording found.", "Verify contamination-control support."))

    if _review_like(str(draft.get("source_span", ""))) and draft.get("evidence_type") == "primary_claim":
        feedback.append(_item("medium", "evidence_type", "review-like wording detected; verify evidence_type.", "Use review_summary if the span summarizes other work."))

    if draft.get("nh3_yield_value") is not None and not draft.get("nh3_yield_unit"):
        feedback.append(_item("medium", "nh3_yield_unit", "NH3 yield value exists but unit is missing.", "Check and fill the reported yield unit."))

    if draft.get("reaction_family") == "unclear":
        feedback.append(_item("medium", "reaction_family", "reaction_family is unclear.", "Verify whether the span supports eNRR, LiNRR, NO3RR, NO2RR, NORR, mixed, or unclear."))

    if draft.get("nitrogen_source") == "unknown":
        feedback.append(_item("medium", "nitrogen_source", "nitrogen_source is unknown.", "Verify whether the source identifies N2, 15N2, NO3-, NO2-, NO, NOx, or impurity source."))

    if draft.get("reliability_label") == "A" and draft.get("isotope_validation") != "yes":
        feedback.append(_item("high", "reliability_label", "reliability_label=A but isotope_validation is not yes.", "Review the reliability label under the eNH3 rubric."))

    if draft.get("evidence_type") == "review_summary" and draft.get("reliability_label") == "A":
        feedback.append(_item("high", "reliability_label", "review_summary evidence should not normally receive reliability_label A.", "Downgrade or justify in gold_notes."))

    return feedback


def summarize_feedback(feedback: list[dict[str, Any]]) -> dict[str, int]:
    """Return severity counts for feedback items."""

    summary = {"low": 0, "medium": 0, "high": 0}
    for item in feedback:
        severity = str(item.get("severity", "low"))
        if severity in summary:
            summary[severity] += 1
    return summary


def _grounding_by_field(grounding_result: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not grounding_result:
        return {}
    return {str(item.get("field")): item for item in grounding_result.get("grounding", [])}


def _explicit(grounding_by_field: dict[str, dict[str, Any]], field: str) -> bool:
    item = grounding_by_field.get(field)
    return item is not None and item.get("grounding_status") == "explicit"


def _item(severity: str, field: str | None, message: str, suggested_action: str) -> dict[str, Any]:
    return {
        "severity": severity,
        "field": field,
        "message": message,
        "suggested_action": suggested_action,
    }


def _review_like(text: str) -> bool:
    return re.search(r"\b(review|summarized|reported by|table|literature)\b", text, flags=re.IGNORECASE) is not None
