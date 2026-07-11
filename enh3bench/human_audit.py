"""Human audit sheet export/import for eNH3-BoundaryLedger."""

from __future__ import annotations

from collections import Counter
import csv
import json
import re
from pathlib import Path
from typing import Any

from enh3bench.audit_schema import (
    AUDIT_SCHEMA_VERSION,
    HUMAN_FIELDS,
    REVIEW_REQUIREMENT_FIELDS,
    empty_human_fields_template,
    is_reviewed_record,
    normalize_list_field,
    validate_human_label_record,
)
from enh3bench.ledger_router import load_jsonl
from enh3bench.llm_clients.base import sanitize_model_name_for_path
from enh3bench.provenance_rules import (
    is_primary_admissible,
    is_reject_or_low_trust,
    is_secondary_or_context,
    normalize_provenance_type,
)


AUDIT_FIELD_ORDER = [
    "schema_version",
    "migration_warnings",
    "audit_id",
    "run_name",
    "paper_id",
    "document_id",
    "doi",
    "source_span_id",
    "evidence_id",
    "source_text",
    "source_section",
    "provenance_type",
    "provenance_confidence",
    "provenance_confidence_rationale",
    "section_heading",
    "section_path",
    "section_type",
    "section_confidence",
    "reaction_family",
    "reaction_family_confidence",
    "reaction_family_signals",
    "reaction_family_scope",
    "paper_level_reaction_family",
    "reaction_family_conflict",
    "text_class",
    "claim_type",
    "maximum_supported_boundary",
    "support_hint_boundary",
    "paired_body_required",
    "caption_context_only",
    "admissibility_status",
    "missing_boundary_fields",
    "required_controls",
    "hidden_tax",
    "detected_taxes",
    "overclaim_risk_flags",
    "llm_model",
    "llm_maximum_supported_boundary",
    "llm_missing_boundary_fields",
    "llm_required_controls",
    "llm_hidden_tax",
    "llm_overclaim_risk",
    "trusted_llm_maximum_supported_boundary",
    "trusted_llm_boundary_reason",
    "low_trust_provenance",
    "low_trust_provenance_reason",
    "boundary_agreement",
    "llm_more_permissive",
    "llm_more_conservative",
    *REVIEW_REQUIREMENT_FIELDS,
    "needs_human_review",
    "llm_audit_flags",
    "audit_priority_score",
    "audit_priority_reasons",
    *HUMAN_FIELDS,
]

CRITICAL_RULE_REVIEW_FLAGS = {
    "text_class_provenance_conflict_primary_vs_low_trust",
    "unsupported_or_missing_source_text",
    "reaction_family_conflict",
    "unpaired_caption_primary_claim",
    "process_or_reactor_claim_low_trust_provenance",
}

HIGH_RULE_REVIEW_FLAGS = {
    "n2_to_nh3_primary_claim_missing_isotope_attribution",
    "rule_boundary_potentially_overclaims_provenance",
    "high_priority_contamination_or_source_attribution_gap",
    "trusted_boundary_capped_by_provenance",
}

MEDIUM_RULE_REVIEW_FLAGS = {
    "missing_blank_or_nox_controls",
    "review_table_primary_pairing_required",
    "medium_confidence_family_or_section_conflict",
}

LOW_RULE_REVIEW_FLAGS = {
    "incomplete_metric_matrix",
    "optional_audit_note_only",
}

LLM_REVIEW_SCORE_FLAGS = {
    "llm_parse_or_schema_error": 8,
    "llm_more_permissive_than_rule": 5,
    "llm_more_conservative_than_rule": 4,
    "missing_boundary_field_disagreement": 4,
    "required_control_disagreement": 4,
    "llm_overrode_low_trust_provenance": 6,
    "llm_upgraded_unpaired_caption": 6,
    "possible_unsupported_isotope_claim": 5,
    "text_class_disagreement": 2,
}

PRIMARY_TEXT_CLASSES = {"primary_performance", "primary_performance_with_validation"}
LOW_TRUST_PROVENANCE_TYPES = {"reference", "bibliography", "front_matter", "metadata", "copyright_note"}
CAPTION_PROVENANCE_TYPES = {"figure_caption", "scheme_caption"}


def load_claim_rights(run_name: str, base_dir: str | Path = "data/boundary_ledger") -> list[dict[str, Any]]:
    """Load a BoundaryLedger claim-rights ledger."""

    return load_jsonl(Path(base_dir) / run_name / "claim_rights_ledger.jsonl")


def load_hidden_tax(run_name: str, base_dir: str | Path = "data/boundary_ledger") -> list[dict[str, Any]]:
    """Load a BoundaryLedger hidden-tax ledger if present."""

    return load_jsonl(Path(base_dir) / run_name / "hidden_tax_ledger.jsonl")


def load_llm_verified_claims(
    run_name: str,
    model: str | None = None,
    base_dir: str | Path = "data/llm_verification",
) -> list[dict[str, Any]]:
    """Load optional LLM verification rows for one model or all exported models."""

    run_dir = Path(base_dir) / run_name
    if model:
        return load_jsonl(run_dir / sanitize_model_name_for_path(model) / "llm_verified_claims.jsonl")
    if not run_dir.exists():
        return []

    records: list[dict[str, Any]] = []
    for model_dir in sorted(path for path in run_dir.iterdir() if path.is_dir()):
        records.extend(load_jsonl(model_dir / "llm_verified_claims.jsonl"))
    return records


def merge_audit_sources(
    rule_records: list[dict[str, Any]],
    hidden_tax_records: list[dict[str, Any]] | None = None,
    llm_records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Merge rule, hidden-tax, and LLM rows into human-audit rows."""

    hidden_by_key = _index_by_evidence_or_span(hidden_tax_records or [])
    llm_by_key = _index_by_evidence_or_span(llm_records or [])
    merged_records: list[dict[str, Any]] = []

    for rule in rule_records:
        record = dict(rule)
        record["schema_version"] = AUDIT_SCHEMA_VERSION
        record.setdefault("migration_warnings", [])
        key = _record_key(rule)
        hidden = hidden_by_key.get(key, {})
        llm = llm_by_key.get(key, {})

        record.setdefault("audit_id", _audit_id(rule))
        record.setdefault("run_name", str(rule.get("run_name") or ""))
        record.setdefault("document_id", str(rule.get("document_id") or ""))
        record.setdefault("doi", str(rule.get("doi") or ""))
        record.setdefault("source_section", str(rule.get("source_section") or ""))
        record.setdefault("hidden_tax", rule.get("hidden_tax") or hidden.get("detected_taxes") or [])
        record["detected_taxes"] = hidden.get("detected_taxes") or rule.get("detected_taxes") or []
        if hidden:
            record["hidden_tax_severity"] = hidden.get("severity") or ""
            record["hidden_tax_required_controls"] = hidden.get("required_controls") or []
            record["hidden_tax_missing_measurements"] = hidden.get("missing_measurements") or []
            record["raw_hidden_tax_record"] = _compact_json(hidden)

        _attach_llm_fields(record, llm)
        record["raw_rule_record"] = _compact_json(rule)

        for field, value in empty_human_fields_template().items():
            record.setdefault(field, value)

        score = score_audit_priority(record)
        record.update(score)
        _apply_review_requirements(record)
        merged_records.append(record)

    return merged_records


def derive_rule_review_requirement(record: dict[str, Any]) -> dict[str, Any]:
    """Derive rule-only human-review requirements from provenance and claim signals."""

    flags: list[str] = []
    provenance_type = normalize_provenance_type(str(record.get("provenance_type") or "unknown"))
    risk_flags = _list_values(record.get("overclaim_risk_flags"))
    all_flags = risk_flags + _list_values(record.get("llm_audit_flags"))
    required_controls = _list_values(record.get("required_controls"))
    missing_fields = _list_values(record.get("missing_boundary_fields"))
    detected_taxes = _list_values(record.get("detected_taxes")) + _list_values(record.get("hidden_tax"))
    source_text = str(record.get("source_text") or "").strip()
    boundary = str(record.get("maximum_supported_boundary") or record.get("rule_maximum_supported_boundary") or "")
    claim_type = str(record.get("claim_type") or "")
    low_trust = _record_has_low_trust_provenance(record, provenance_type)
    primary_claim = _is_primary_claim_context(record, provenance_type)

    if (
        (_truthy(record.get("text_class_provenance_conflict")) or "text_class_provenance_conflict" in risk_flags)
        and primary_claim
        and provenance_type in LOW_TRUST_PROVENANCE_TYPES
    ):
        flags.append("text_class_provenance_conflict_primary_vs_low_trust")
    if not source_text or str(record.get("admissibility_status") or "") == "weak_grounding" or "weak_source_grounding" in all_flags:
        flags.append("unsupported_or_missing_source_text")
    if _truthy(record.get("reaction_family_conflict")):
        flags.append("reaction_family_conflict")
    if provenance_type in CAPTION_PROVENANCE_TYPES and _truthy(record.get("paired_body_required")) and primary_claim:
        flags.append("unpaired_caption_primary_claim")
    if low_trust and (claim_type in {"process_claim", "reactor_claim"} or boundary in {"process_partial", "reactor_legibility"}):
        flags.append("process_or_reactor_claim_low_trust_provenance")

    if primary_claim and _n2_to_nh3_claim(record) and not _gate_explicit(record, "isotope_15N"):
        flags.append("n2_to_nh3_primary_claim_missing_isotope_attribution")
    if _rule_boundary_overclaims_provenance(record, provenance_type, boundary):
        flags.append("rule_boundary_potentially_overclaims_provenance")
    if "trusted_boundary_capped_by_provenance" in all_flags:
        flags.append("trusted_boundary_capped_by_provenance")
    if _high_priority_contamination_or_source_gap(required_controls, missing_fields, detected_taxes, risk_flags):
        flags.append("high_priority_contamination_or_source_attribution_gap")

    if not _gate_explicit(record, "blank_control") or not _gate_explicit(record, "nox_control"):
        flags.append("missing_blank_or_nox_controls")
    if provenance_type in {"review_table", "table"} and _requires_primary_pairing(required_controls, missing_fields):
        flags.append("review_table_primary_pairing_required")
    if _medium_confidence_family_or_section_conflict(record, risk_flags):
        flags.append("medium_confidence_family_or_section_conflict")

    if _incomplete_metric_matrix(record, missing_fields, detected_taxes):
        flags.append("incomplete_metric_matrix")
    if _optional_audit_note(record):
        flags.append("optional_audit_note_only")

    flags = _dedupe(flags)
    score = _rule_review_score(flags)
    band = derive_review_priority_band(score, flags)
    return {
        "rule_needs_human_review": band in {"critical", "high", "medium"},
        "rule_review_priority_score": score,
        "rule_review_trigger_flags": flags,
        "review_priority_band": band,
        "review_trigger_flags": flags,
    }


def derive_review_priority_band(score: int, flags: list[str] | str | None) -> str:
    """Map review score and trigger flags into a stable priority band."""

    normalized_flags = set(_list_values(flags))
    if normalized_flags & CRITICAL_RULE_REVIEW_FLAGS or any(flag.startswith("critical:") for flag in normalized_flags):
        return "critical"
    if normalized_flags & HIGH_RULE_REVIEW_FLAGS or int(score or 0) >= 8:
        return "high"
    if normalized_flags & MEDIUM_RULE_REVIEW_FLAGS or 4 <= int(score or 0) <= 7:
        return "medium"
    if normalized_flags & LOW_RULE_REVIEW_FLAGS or 1 <= int(score or 0) <= 3:
        return "low"
    return "none"


def merge_review_requirements(rule_review: dict[str, Any], llm_review: dict[str, Any]) -> dict[str, Any]:
    """Merge rule-only and LLM-only review requirements into overall review fields."""

    rule_flags = _list_values(rule_review.get("review_trigger_flags")) + _list_values(rule_review.get("rule_review_trigger_flags"))
    llm_flags = _list_values(llm_review.get("review_trigger_flags")) + _list_values(llm_review.get("llm_review_trigger_flags"))
    flags = _dedupe([*rule_flags, *llm_flags])
    score = max(
        int(rule_review.get("audit_priority_score") or 0),
        int(rule_review.get("rule_review_priority_score") or 0) + int(llm_review.get("llm_review_priority_score") or 0),
        int(llm_review.get("audit_priority_score") or 0),
    )
    band = derive_review_priority_band(score, flags)
    rule_needed = _truthy(rule_review.get("rule_needs_human_review"))
    llm_needed = _truthy(llm_review.get("llm_needs_human_review"))
    overall_needed = band in {"critical", "high", "medium"} or llm_needed
    return {
        "rule_needs_human_review": rule_needed,
        "llm_needs_human_review": llm_needed,
        "overall_needs_human_review": overall_needed,
        "review_priority_band": band,
        "review_trigger_flags": flags,
        "needs_human_review": overall_needed,
    }


def score_audit_priority(record: dict[str, Any]) -> dict[str, Any]:
    """Score a record for human-review priority."""

    score = 0
    reasons: list[str] = []

    def add(points: int, reason: str) -> None:
        nonlocal score
        if reason not in reasons:
            score += points
            reasons.append(reason)

    flags = _list_values(record.get("overclaim_risk_flags")) + _list_values(record.get("llm_audit_flags"))
    provenance_type = normalize_provenance_type(str(record.get("provenance_type") or "unknown"))
    boundary = str(record.get("maximum_supported_boundary") or "")
    status = str(record.get("admissibility_status") or "")

    has_llm_signal = bool(record.get("llm_model") or record.get("llm_parse_error") or _list_values(record.get("llm_audit_flags")))
    if _truthy(record.get("llm_needs_human_review")) or (
        has_llm_signal and "llm_needs_human_review" not in record and _truthy(record.get("needs_human_review"))
    ):
        add(4, "llm_needs_human_review")
    if _truthy(record.get("llm_more_permissive")):
        add(5, "llm_more_permissive")
    if _truthy(record.get("llm_more_conservative")):
        add(3, "llm_more_conservative")
    if "llm_overrode_low_trust_provenance" in flags:
        add(6, "llm_overrode_low_trust_provenance")
    if "trusted_boundary_capped_by_provenance" in flags:
        add(5, "trusted_boundary_capped_by_provenance")
    if _truthy(record.get("provenance_constrained")):
        add(3, "provenance_constrained")
    if _truthy(record.get("text_class_provenance_conflict")) or "text_class_provenance_conflict" in flags:
        add(3, "text_class_provenance_conflict")
    if _truthy(record.get("is_reject_or_low_trust")) or is_reject_or_low_trust(provenance_type) or "low_trust_provenance" in flags:
        add(4, "low_trust_provenance")
    if (_truthy(record.get("low_trust_provenance")) or is_reject_or_low_trust(provenance_type)) and _llm_boundary_differs_from_rule(record):
        add(4, "low_trust_llm_boundary_differs_from_rule")
    if provenance_type == "review_table" or str(record.get("text_class") or "") == "review_table" or "review_table_not_primary" in flags:
        add(2, "review_table_not_primary")
    if status == "context_only_caption" or provenance_type in {"figure_caption", "scheme_caption"}:
        add(2, "context_only_caption")
    if _caption_has_support_hint(record, provenance_type):
        add(4, "caption_has_support_hint_requires_body_pairing")
    if _n2_to_nh3_claim(record) and not _gate_explicit(record, "isotope_15N"):
        add(4, "missing_15N_for_N2_to_NH3_claim")
    if not _gate_explicit(record, "blank_control"):
        add(2, "missing_blank_control")
    if not _gate_explicit(record, "nox_control"):
        add(2, "missing_NOx_control")
    if boundary == "process_partial" or str(record.get("claim_type") or "") == "process_claim":
        add(2, "process_partial_claim")
    if boundary == "reactor_legibility" or str(record.get("claim_type") or "") == "reactor_claim":
        add(1, "reactor_legibility_claim")
    if str(record.get("hidden_tax_severity") or "").casefold() == "high":
        add(3, "hidden_taxes_high_severity")
    if not str(record.get("source_text") or "").strip() or status == "weak_grounding" or "weak_source_grounding" in flags:
        add(3, "source_text_missing_or_weak_grounding")
    if _truthy(record.get("reaction_family_conflict")):
        add(8, "reaction_family_conflict")

    return {"audit_priority_score": score, "audit_priority_reasons": reasons}


def export_human_audit_sheet(
    records: list[dict[str, Any]],
    run_name: str,
    output_dir: str | Path = "data/human_audit",
    top_n: int | None = None,
    priority_only: bool = False,
) -> dict[str, Any]:
    """Write human-editable CSV and full JSONL audit sheets."""

    run_dir = Path(output_dir) / run_name
    output_records = []
    for record in records:
        row = migrate_audit_record(record)
        row["run_name"] = str(row.get("run_name") or run_name)
        if "audit_priority_score" not in row:
            row.update(score_audit_priority(row))
        _apply_review_requirements(row)
        output_records.append(row)

    output_records.sort(key=lambda item: (-int(item.get("audit_priority_score") or 0), str(item.get("audit_id") or "")))
    if priority_only:
        output_records = [
            record
            for record in output_records
            if int(record.get("audit_priority_score") or 0) > 0 or _truthy(record.get("overall_needs_human_review"))
        ]
    if top_n is not None:
        output_records = output_records[: max(0, int(top_n))]

    jsonl_path = run_dir / "human_audit_sheet.jsonl"
    csv_path = run_dir / "human_audit_sheet.csv"
    _write_jsonl(output_records, jsonl_path)
    _write_csv(output_records, csv_path, truncate_source_text=True)

    priority_count = sum(1 for record in output_records if int(record.get("audit_priority_score") or 0) > 0)
    return {
        "run_name": run_name,
        "count": len(output_records),
        "priority_records": priority_count,
        "rule_review_records": sum(1 for record in output_records if _truthy(record.get("rule_needs_human_review"))),
        "llm_review_records": sum(1 for record in output_records if _truthy(record.get("llm_needs_human_review"))),
        "overall_review_records": sum(1 for record in output_records if _truthy(record.get("overall_needs_human_review"))),
        "priority_band_counts": dict(Counter(str(record.get("review_priority_band") or "none") for record in output_records)),
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
    }


def migrate_audit_record(record: dict[str, Any]) -> dict[str, Any]:
    """Add v0.13 audit/review defaults with an explicit migration warning."""

    migrated = dict(record)
    warnings = _list_values(migrated.get("migration_warnings"))
    old_version = str(migrated.get("schema_version") or "legacy")
    if old_version != AUDIT_SCHEMA_VERSION:
        warnings.append(f"audit schema migrated from {old_version} to {AUDIT_SCHEMA_VERSION}")
    migrated["schema_version"] = AUDIT_SCHEMA_VERSION
    migrated["migration_warnings"] = _dedupe(warnings)
    migrated.setdefault("reaction_family", "unclear")
    migrated.setdefault("reaction_family_confidence", "unclear")
    migrated.setdefault("reaction_family_signals", [])
    migrated.setdefault("reaction_family_scope", "fallback")
    migrated.setdefault("paper_level_reaction_family", "unclear")
    migrated.setdefault("reaction_family_conflict", False)
    migrated.setdefault("section_type", "unknown")
    migrated.setdefault("section_confidence", "low")
    return migrated


def import_human_audit_sheet(
    path: str | Path,
    run_name: str,
    output_dir: str | Path = "data/human_audit",
    accept_as_gold: bool = False,
) -> dict[str, Any]:
    """Import a reviewed audit CSV and validate human labels."""

    input_path = Path(path)
    rows = _read_csv(input_path)
    run_dir = Path(output_dir) / run_name
    reviewed_valid: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    unreviewed = 0

    for index, row in enumerate(rows, start=2):
        cleaned = {str(key).lstrip("\ufeff"): value for key, value in row.items()}
        status = str(cleaned.get("human_review_status") or "").strip()
        valid, row_errors = validate_human_label_record(cleaned)
        if status != "reviewed":
            unreviewed += 1
            if row_errors and _has_any_human_label(cleaned):
                errors.append(_error_row(index, cleaned, row_errors))
            continue
        if not valid or not is_reviewed_record(cleaned):
            errors.append(_error_row(index, cleaned, row_errors or ["reviewed record is missing required human labels"]))
            continue

        normalized = migrate_audit_record(cleaned)
        normalized["human_required_controls"] = normalize_list_field(cleaned.get("human_required_controls"))
        normalized["human_hidden_tax"] = normalize_list_field(cleaned.get("human_hidden_tax"))
        normalized["human_label_validated"] = True
        reviewed_valid.append(normalized)

    reviewed_jsonl = run_dir / "reviewed_audit_records.jsonl"
    reviewed_csv = run_dir / "reviewed_audit_records.csv"
    errors_csv = run_dir / "human_label_errors.csv"
    _write_jsonl(reviewed_valid, reviewed_jsonl)
    _write_csv(reviewed_valid, reviewed_csv, truncate_source_text=True)
    _write_csv(errors, errors_csv, truncate_source_text=False)

    gold_jsonl = ""
    gold_csv = ""
    gold_written = 0
    if accept_as_gold:
        gold_dir = Path(output_dir).parent / "gold" / run_name
        gold_records = [dict(record, gold_source="human_review") for record in reviewed_valid]
        gold_jsonl_path = gold_dir / "human_gold_claim_rights.jsonl"
        gold_csv_path = gold_dir / "human_gold_claim_rights.csv"
        _write_jsonl(gold_records, gold_jsonl_path)
        _write_csv(gold_records, gold_csv_path, truncate_source_text=True)
        gold_jsonl = str(gold_jsonl_path)
        gold_csv = str(gold_csv_path)
        gold_written = len(gold_records)

    return {
        "run_name": run_name,
        "rows_read": len(rows),
        "reviewed_valid": len(reviewed_valid),
        "reviewed_invalid": len(errors),
        "unreviewed": unreviewed,
        "gold_written": gold_written,
        "reviewed_jsonl": str(reviewed_jsonl),
        "reviewed_csv": str(reviewed_csv),
        "errors_csv": str(errors_csv),
        "gold_jsonl": gold_jsonl,
        "gold_csv": gold_csv,
    }


def export_audit_report(
    records: list[dict[str, Any]],
    run_name: str,
    output_dir: str | Path = "data/reports",
) -> str:
    """Write a Phase D human-audit Markdown report."""

    prepared_records: list[dict[str, Any]] = []
    for original in records:
        record = migrate_audit_record(original)
        if "audit_priority_score" not in record:
            record.update(score_audit_priority(record))
        _apply_review_requirements(record)
        prepared_records.append(record)
    records = prepared_records

    output_path = Path(output_dir) / f"human_audit_report.{run_name}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    reason_counts = _list_counter(records, "audit_priority_reasons")
    reviewed_records = [record for record in records if is_reviewed_record(record)]
    reviewed_file = Path("data/human_audit") / run_name / "reviewed_audit_records.jsonl"
    reviewed_file_count = len(load_jsonl(reviewed_file)) if reviewed_file.exists() else 0
    total_reviewed = len(reviewed_records) or reviewed_file_count

    lines = [
        f"# Human Audit Report: {run_name}",
        "",
        "## 1. What Phase D adds",
        "",
        (
            "Phase D adds a human-audit and calibration layer above BoundaryLedger. "
            "It exports rule, hidden-tax, and optional LLM verification outputs into a "
            "review sheet without overwriting any source ledger."
        ),
        "",
        "## 2. Audit source counts",
        "",
        f"- Audit records: {len(records)}",
        f"- Schema version: {AUDIT_SCHEMA_VERSION}",
        f"- Records with migration warnings: {sum(1 for record in records if _list_values(record.get('migration_warnings')))}",
        f"- Records with hidden-tax fields: {sum(1 for record in records if _list_values(record.get('detected_taxes')))}",
        f"- Records with LLM verification: {sum(1 for record in records if record.get('llm_model'))}",
        "",
        "## 3. LLM/rule disagreement counts",
        "",
        f"- Boundary disagreements: {sum(1 for record in records if record.get('boundary_agreement') is False)}",
        f"- LLM more permissive: {sum(1 for record in records if _truthy(record.get('llm_more_permissive')))}",
        f"- LLM more conservative: {sum(1 for record in records if _truthy(record.get('llm_more_conservative')))}",
        "",
        "## 4. Provenance-constrained records",
        "",
        f"- Provenance-constrained: {sum(1 for record in records if _truthy(record.get('provenance_constrained')))}",
        f"- Low-trust provenance: {sum(1 for record in records if _truthy(record.get('is_reject_or_low_trust')))}",
        f"- Captions with support hints: {sum(1 for record in records if _caption_has_support_hint(record, str(record.get('provenance_type') or '')))}",
        "",
        "## 5. Caption support hints",
        "",
        _markdown_table(
            ["Support hint", "Records"],
            [[key, count] for key, count in _caption_hint_counter(records).most_common()],
        ),
        "",
        "## 6. Top audit priority reasons",
        "",
        _markdown_table(["Reason", "Records"], [[key, count] for key, count in reason_counts.most_common(12)]),
        "",
        "## 7. Records needing human review",
        "",
        f"- Rule review required: {sum(1 for record in records if _truthy(record.get('rule_needs_human_review')))}",
        f"- LLM review required: {sum(1 for record in records if _truthy(record.get('llm_needs_human_review')))}",
        f"- Overall review required: {sum(1 for record in records if _truthy(record.get('overall_needs_human_review')))}",
        f"- Rule-only review: {sum(1 for record in records if _truthy(record.get('rule_needs_human_review')) and not _truthy(record.get('llm_needs_human_review')))}",
        f"- LLM-only review: {sum(1 for record in records if _truthy(record.get('llm_needs_human_review')) and not _truthy(record.get('rule_needs_human_review')))}",
        f"- priority score > 0: {sum(1 for record in records if int(record.get('audit_priority_score') or 0) > 0)}",
        "",
        _markdown_table(
            ["Priority band", "Records"],
            [[key, count] for key, count in Counter(str(record.get("review_priority_band") or "none") for record in records).most_common()],
        ),
        "",
        "## 8. Human label completion status if reviewed records exist",
        "",
        f"- Reviewed records available: {total_reviewed}",
        "",
        "## 9. Next review instructions",
        "",
        (
            "Open data/human_audit/{run}/human_audit_sheet.csv, fill only the human_* "
            "columns, save a reviewed copy, then import it with scripts/import_human_audit_sheet.py."
        ).format(run=run_name),
        "",
        "## 10. Safety statement",
        "",
        (
            "Human labels do not overwrite rule outputs. They become gold only when a reviewed "
            "CSV is imported with --accept-as-gold after validation succeeds."
        ),
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return str(output_path)


def _attach_llm_fields(record: dict[str, Any], llm: dict[str, Any]) -> None:
    record.setdefault("llm_model", "")
    record.setdefault("llm_text_class", "")
    record.setdefault("llm_maximum_supported_boundary", "")
    record.setdefault("llm_missing_boundary_fields", [])
    record.setdefault("llm_required_controls", [])
    record.setdefault("llm_hidden_tax", [])
    record.setdefault("llm_overclaim_risk", [])
    record.setdefault("trusted_llm_maximum_supported_boundary", "")
    record.setdefault("trusted_llm_boundary_reason", "")
    record.setdefault("low_trust_provenance", False)
    record.setdefault("low_trust_provenance_reason", "")
    record.setdefault("boundary_agreement", "")
    record.setdefault("llm_more_permissive", False)
    record.setdefault("llm_more_conservative", False)
    record.setdefault("rule_needs_human_review", False)
    record.setdefault("llm_needs_human_review", False)
    record.setdefault("overall_needs_human_review", False)
    record.setdefault("review_priority_band", "none")
    record.setdefault("review_trigger_flags", [])
    record.setdefault("needs_human_review", False)
    record.setdefault("llm_audit_flags", [])

    if not llm:
        return
    verification = llm.get("llm_verification") if isinstance(llm.get("llm_verification"), dict) else {}
    record["llm_model"] = llm.get("llm_model") or ""
    record["llm_text_class"] = verification.get("text_class") or ""
    record["llm_maximum_supported_boundary"] = verification.get("maximum_supported_boundary") or ""
    record["llm_missing_boundary_fields"] = verification.get("missing_boundary_fields") or []
    record["llm_required_controls"] = verification.get("required_controls") or []
    record["llm_hidden_tax"] = verification.get("hidden_tax") or []
    record["llm_overclaim_risk"] = verification.get("overclaim_risk") or []
    record["trusted_llm_maximum_supported_boundary"] = llm.get("trusted_llm_maximum_supported_boundary") or ""
    record["trusted_llm_boundary_reason"] = llm.get("trusted_llm_boundary_reason") or ""
    record["low_trust_provenance"] = bool(llm.get("low_trust_provenance"))
    record["low_trust_provenance_reason"] = llm.get("low_trust_provenance_reason") or ""
    record["boundary_agreement"] = llm.get("boundary_agreement")
    record["llm_more_permissive"] = bool(llm.get("llm_more_permissive"))
    record["llm_more_conservative"] = bool(llm.get("llm_more_conservative"))
    record["llm_needs_human_review"] = bool(llm.get("llm_needs_human_review", llm.get("needs_human_review")))
    record["needs_human_review"] = record["llm_needs_human_review"]
    record["llm_audit_flags"] = llm.get("llm_audit_flags") or []
    record["llm_parse_error"] = llm.get("llm_parse_error")
    record["text_class_agreement"] = llm.get("text_class_agreement")
    record["raw_llm_record"] = _compact_json(llm)


def _index_by_evidence_or_span(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        key = _record_key(record)
        if key and key not in indexed:
            indexed[key] = record
    return indexed


def _record_key(record: dict[str, Any]) -> str:
    for key in ("evidence_id", "source_span_id", "span_id", "claim_id", "tax_record_id"):
        value = str(record.get(key) or "").strip()
        if value:
            value = re.sub(r"^(?:CR_|HT_)", "", value)
            return value
    return ""


def _audit_id(record: dict[str, Any]) -> str:
    for key in ("claim_id", "evidence_id", "source_span_id", "span_id"):
        value = str(record.get(key) or "").strip()
        if value:
            return f"AUD_{value}"
    return "AUD_TODO"


def _compact_json(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":"))


def _write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, default=str, separators=(",", ":")))
            handle.write("\n")


def _write_csv(records: list[dict[str, Any]], output_path: Path, truncate_source_text: bool) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _fieldnames(records)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: _csv_value(record.get(field), field, truncate_source_text) for field in fieldnames})


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _fieldnames(records: list[dict[str, Any]]) -> list[str]:
    names: set[str] = set(AUDIT_FIELD_ORDER)
    for record in records:
        names.update(record)
    ordered = [field for field in AUDIT_FIELD_ORDER if field in names]
    ordered.extend(sorted(name for name in names if name not in set(ordered)))
    return ordered


def _csv_value(value: Any, field: str, truncate_source_text: bool) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    else:
        text = str(value)
    if field == "source_text" and truncate_source_text and len(text) > 4000:
        return text[:3997] + "..."
    return text


def _error_row(row_number: int, row: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    return {
        "row_number": row_number,
        "audit_id": row.get("audit_id") or "",
        "paper_id": row.get("paper_id") or "",
        "source_span_id": row.get("source_span_id") or "",
        "evidence_id": row.get("evidence_id") or "",
        "human_review_status": row.get("human_review_status") or "",
        "errors": "; ".join(errors),
    }


def _has_any_human_label(row: dict[str, Any]) -> bool:
    for field in HUMAN_FIELDS:
        if field == "human_review_status":
            continue
        if str(row.get(field) or "").strip():
            return True
    return False


def _list_values(value: Any) -> list[str]:
    return normalize_list_field(value)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"true", "1", "yes", "y"}


def _gate_explicit(record: dict[str, Any], gate: str) -> bool:
    validation = record.get("validation_gates")
    if isinstance(validation, dict):
        value = str(validation.get(gate) or "").strip().casefold()
        return value in {"yes", "explicit", "true", "present"}
    for key in (gate, gate.lower(), gate.upper()):
        if str(record.get(key) or "").strip().casefold() in {"yes", "explicit", "true", "present"}:
            return True
    return False


def _n2_to_nh3_claim(record: dict[str, Any]) -> bool:
    text = str(record.get("source_text") or "").casefold()
    family = str(record.get("reaction_family") or "").casefold()
    source = str(record.get("nitrogen_source") or "").casefold()
    return (
        family in {"enrr", "linrr"}
        or source in {"n2", "15n2"}
        or "n2-to-nh3" in text
        or "n2 to nh3" in text
        or "nitrogen reduction" in text
        or "dinitrogen" in text
        or ("n2" in text and "nh3" in text)
    )


def _llm_boundary_differs_from_rule(record: dict[str, Any]) -> bool:
    rule_boundary = str(record.get("maximum_supported_boundary") or record.get("rule_maximum_supported_boundary") or "")
    llm_boundary = str(record.get("llm_maximum_supported_boundary") or "")
    return bool(rule_boundary and llm_boundary and rule_boundary != llm_boundary)


def _caption_has_support_hint(record: dict[str, Any], provenance_type: str) -> bool:
    normalized = normalize_provenance_type(provenance_type)
    hint = str(record.get("support_hint_boundary") or "").strip()
    return normalized in {"figure_caption", "scheme_caption"} and hint not in {"", "unsupported_or_secondary"}


def _apply_review_requirements(record: dict[str, Any]) -> None:
    rule_review = derive_rule_review_requirement(record)
    rule_review["audit_priority_score"] = int(record.get("audit_priority_score") or 0)
    record.update(merge_review_requirements(rule_review, _derive_llm_review_requirement(record)))


def _derive_llm_review_requirement(record: dict[str, Any]) -> dict[str, Any]:
    flags = _list_values(record.get("llm_audit_flags"))
    if record.get("llm_parse_error") and "llm_parse_or_schema_error" not in flags:
        flags.append("llm_parse_or_schema_error")
    if _truthy(record.get("llm_more_permissive")) and "llm_more_permissive_than_rule" not in flags:
        flags.append("llm_more_permissive_than_rule")
    if _truthy(record.get("llm_more_conservative")) and "llm_more_conservative_than_rule" not in flags:
        flags.append("llm_more_conservative_than_rule")
    has_llm_signal = bool(record.get("llm_model") or record.get("llm_parse_error") or flags)
    needed = _truthy(record.get("llm_needs_human_review"))
    if "llm_needs_human_review" not in record and has_llm_signal:
        needed = _truthy(record.get("needs_human_review"))
    needed = needed or bool(set(flags) & set(LLM_REVIEW_SCORE_FLAGS))
    score = max((LLM_REVIEW_SCORE_FLAGS.get(flag, 0) for flag in flags), default=0)
    if needed and score == 0:
        score = 4
    return {
        "llm_needs_human_review": needed,
        "llm_review_priority_score": score,
        "llm_review_trigger_flags": _dedupe(flags),
    }


def _record_has_low_trust_provenance(record: dict[str, Any], provenance_type: str) -> bool:
    return (
        _truthy(record.get("low_trust_provenance"))
        or _truthy(record.get("is_reject_or_low_trust"))
        or is_reject_or_low_trust(provenance_type)
    )


def _is_primary_claim_context(record: dict[str, Any], provenance_type: str) -> bool:
    return (
        str(record.get("text_class") or "") in PRIMARY_TEXT_CLASSES
        or str(record.get("claim_type") or "") in {"performance_claim", "validation_claim", "process_claim", "reactor_claim"}
        or is_primary_admissible(provenance_type)
    )


def _rule_boundary_overclaims_provenance(record: dict[str, Any], provenance_type: str, boundary: str) -> bool:
    if boundary in {"", "unsupported_or_secondary"}:
        return False
    return _truthy(record.get("provenance_constrained")) or not is_primary_admissible(provenance_type)


def _high_priority_contamination_or_source_gap(
    required_controls: list[str], missing_fields: list[str], detected_taxes: list[str], risk_flags: list[str]
) -> bool:
    text = " ".join([*required_controls, *missing_fields, *detected_taxes, *risk_flags]).casefold()
    return any(term in text for term in ("contamination", "source_attribution", "isotope", "15n"))


def _requires_primary_pairing(required_controls: list[str], missing_fields: list[str]) -> bool:
    text = " ".join([*required_controls, *missing_fields]).casefold()
    return "primary" in text and ("pair" in text or "body" in text)


def _medium_confidence_family_or_section_conflict(record: dict[str, Any], risk_flags: list[str]) -> bool:
    if any("family" in flag or "section" in flag for flag in risk_flags if "conflict" in flag):
        return True
    family_confidence = str(record.get("reaction_family_confidence") or "").casefold()
    section_confidence = str(record.get("section_confidence") or "").casefold()
    return family_confidence == "medium" and section_confidence == "medium"


def _incomplete_metric_matrix(record: dict[str, Any], missing_fields: list[str], detected_taxes: list[str]) -> bool:
    if "measurement_matrix_tax" in detected_taxes:
        return True
    metric_fields = {"FE", "NH3_yield", "EE", "current_density", "potential_or_voltage", "runtime"}
    return str(record.get("maximum_supported_boundary") or "") == "cell_metric" and bool(metric_fields & set(missing_fields))


def _optional_audit_note(record: dict[str, Any]) -> bool:
    return any(str(record.get(key) or "").strip() for key in ("optional_audit_note", "audit_note", "audit_notes"))


def _rule_review_score(flags: list[str]) -> int:
    score = 0
    for flag in flags:
        if flag in CRITICAL_RULE_REVIEW_FLAGS:
            score = max(score, 10)
        elif flag in HIGH_RULE_REVIEW_FLAGS:
            score = max(score, 8)
        elif flag in MEDIUM_RULE_REVIEW_FLAGS:
            score = max(score, 4)
        elif flag in LOW_RULE_REVIEW_FLAGS:
            score = max(score, 1)
    return score


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _caption_hint_counter(records: list[dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for record in records:
        provenance_type = normalize_provenance_type(str(record.get("provenance_type") or ""))
        if provenance_type not in {"figure_caption", "scheme_caption"}:
            continue
        counter[str(record.get("support_hint_boundary") or "unsupported_or_secondary")] += 1
    return counter


def _list_counter(records: list[dict[str, Any]], key: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for record in records:
        counter.update(_list_values(record.get(key)))
    return counter


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "No records."
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_escape_cell(value) for value in row) + " |")
    return "\n".join(lines)


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
