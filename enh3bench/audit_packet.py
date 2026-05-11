"""Human audit packet generation for machine-drafted evidence."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


REVIEW_SHEET_COLUMNS = [
    "evidence_id",
    "paper_id",
    "human_decision",
    "fields_to_check",
    "correction_notes",
    "reliability_override",
    "include_in_gold",
]

EXTRACTED_FIELDS = [
    "reaction_family",
    "nitrogen_source",
    "faradaic_efficiency_percent",
    "nh3_yield_value",
    "nh3_yield_unit",
    "potential_value",
    "potential_reference",
    "current_density_mA_cm2",
    "stability_hours",
    "detection_method",
    "isotope_validation",
    "blank_control",
    "contamination_control",
    "nox_screening",
    "reliability_label",
    "evidence_type",
    "draft_confidence",
]


def build_audit_packet(
    spans: Iterable[dict[str, Any]],
    drafts: Iterable[dict[str, Any]],
    grounding_records: Iterable[dict[str, Any]] | None = None,
    feedback_records: Iterable[dict[str, Any]] | None = None,
) -> str:
    """Build a Markdown audit packet for human verification."""

    span_by_id = {str(span.get("span_id", "")): span for span in spans}
    grounding_by_id = {str(item.get("evidence_id", "")): item for item in grounding_records or []}
    feedback_by_id = {str(item.get("evidence_id", "")): item for item in feedback_records or []}
    lines = ["# eNH3-Bench Human Audit Packet", ""]

    for draft in drafts:
        evidence_id = str(draft.get("evidence_id", ""))
        span = span_by_id.get(str(draft.get("span_id", "")), {})
        grounding_record = grounding_by_id.get(evidence_id)
        feedback_record = feedback_by_id.get(evidence_id)
        lines.extend(
            [
                f"## {draft.get('evidence_id', '<missing evidence_id>')}",
                "",
                f"- evidence_id: `{draft.get('evidence_id', '')}`",
                f"- paper_id: `{draft.get('paper_id', '')}`",
                f"- candidate score: `{span.get('candidate_score', 'n/a')}`",
                f"- matched keywords: {_format_keywords(span.get('matched_keywords', []))}",
                "",
                "### Source Span",
                "",
                _blockquote(str(draft.get("source_span", ""))),
                "",
                "### Extracted Fields",
                "",
                _field_table(draft),
                "",
                "### Risk Flags",
                "",
                *_risk_flag_lines(draft),
                "",
                "### Field Grounding",
                "",
                _grounding_table(grounding_record),
                "",
                "### Machine Feedback",
                "",
                "Machine feedback; human verification required.",
                "",
                *_feedback_lines(feedback_record),
                "",
                "### Human Action Checklist",
                "",
                "- Verify the source span supports every non-empty extracted field.",
                "- Correct reliability label if validation evidence is over- or under-stated.",
                "- Mark `include_in_gold` true only after source-grounded review.",
                "- Add concise correction notes for unresolved ambiguity.",
                "",
            ]
        )

    return "\n".join(lines)


def build_review_sheet_rows(
    spans: Iterable[dict[str, Any]],
    drafts: Iterable[dict[str, Any]],
) -> list[dict[str, str]]:
    """Build rows for the minimal CSV human review sheet."""

    span_by_id = {str(span.get("span_id", "")): span for span in spans}
    rows: list[dict[str, str]] = []
    for draft in drafts:
        span = span_by_id.get(str(draft.get("span_id", "")), {})
        fields_to_check = _fields_to_check(draft, span)
        rows.append(
            {
                "evidence_id": str(draft.get("evidence_id", "")),
                "paper_id": str(draft.get("paper_id", "")),
                "human_decision": "",
                "fields_to_check": fields_to_check,
                "correction_notes": "",
                "reliability_override": "",
                "include_in_gold": "",
            }
        )
    return rows


def _field_table(draft: dict[str, Any]) -> str:
    lines = ["| Field | Draft value |", "| --- | --- |"]
    for field in EXTRACTED_FIELDS:
        lines.append(f"| `{field}` | {_format_value(draft.get(field))} |")
    return "\n".join(lines)


def _grounding_table(grounding_record: dict[str, Any] | None) -> str:
    if not grounding_record:
        return "No field grounding output available."
    lines = ["| Field | Status | Risk flag |", "| --- | --- | --- |"]
    for item in grounding_record.get("grounding", []):
        field = _format_value(item.get("field"))
        status = _format_value(item.get("grounding_status"))
        risk = _format_value(item.get("risk_flag"))
        lines.append(f"| `{field}` | {status} | {risk} |")
    return "\n".join(lines)


def _feedback_lines(feedback_record: dict[str, Any] | None) -> list[str]:
    if not feedback_record or not feedback_record.get("feedback"):
        return ["- None detected by rule feedback."]
    lines: list[str] = []
    for item in feedback_record.get("feedback", []):
        severity = item.get("severity", "")
        field = item.get("field") or "record"
        message = item.get("message", "")
        action = item.get("suggested_action", "")
        lines.append(f"- `{severity}` `{field}`: {message} Suggested action: {action}")
    return lines


def _risk_flag_lines(draft: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if not str(draft.get("source_span", "")).strip():
        flags.append("Empty source span.")
    if draft.get("draft_confidence") == "low":
        flags.append("Low draft confidence.")
    if draft.get("reaction_family") in {"eNRR", "LiNRR"} and draft.get("isotope_validation") != "yes":
        flags.append("N2-reduction-like claim lacks detected isotope validation.")
    if draft.get("reliability_label") == "A" and draft.get("evidence_type") == "review_summary":
        flags.append("Review summary should not normally receive reliability label A.")
    if not flags:
        flags.append("None detected by rule audit.")
    return [f"- {flag}" for flag in flags]


def _fields_to_check(draft: dict[str, Any], span: dict[str, Any]) -> str:
    fields = [
        "reaction_family",
        "nitrogen_source",
        "metrics",
        "validation_controls",
        "reliability_label",
        "source_grounding",
    ]
    if draft.get("draft_confidence") == "low":
        fields.append("low_confidence_draft")
    if span.get("candidate_score") in {None, "", 0}:
        fields.append("candidate_score")
    return ";".join(fields)


def _format_keywords(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(f"`{keyword}`" for keyword in value) if value else "`none`"
    return f"`{value}`"


def _format_value(value: Any) -> str:
    if value is None or value == "":
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _blockquote(text: str) -> str:
    if not text.strip():
        return "> "
    return "\n".join(f"> {line}" for line in text.splitlines())
