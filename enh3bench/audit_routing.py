"""Context-aware routing for secondary evidence in human audit."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any, Iterable

from enh3bench.provenance_rules import normalize_provenance_type


REFERENCE_AUDIT_SAMPLE_RATE = 0.10
MAX_REFERENCE_SPANS_PER_PAPER_FOR_AUDIT = 1
REFERENCE_AUDIT_HASH_NAMESPACE = "reference-audit-routing-v1"
LEGACY_ROUTING_PROFILE = "legacy_v013"
SECONDARY_HARDENING_ROUTING_PROFILE = "secondary_hardening_v1"
ROUTING_PROFILES = (LEGACY_ROUTING_PROFILE, SECONDARY_HARDENING_ROUTING_PROFILE)

# Public configuration names mirror the pipeline/CLI vocabulary.
reference_audit_sample_rate = REFERENCE_AUDIT_SAMPLE_RATE
max_reference_spans_per_paper_for_audit = MAX_REFERENCE_SPANS_PER_PAPER_FOR_AUDIT

VALIDATION_GATE_NAMES = (
    "isotope_15N",
    "blank_control",
    "nox_control",
    "contamination_control",
    "quantification_method",
)

MECHANICAL_MISSING_AUDIT_REASONS = {
    "missing_blank_control",
    "missing_NOx_control",
    "missing_15N_for_N2_to_NH3_claim",
    "missing_contamination_control",
    "missing_quantification_method",
}

MANUAL_REVIEW_FIELDS = (
    "force_human_review",
    "manual_force_review",
    "human_force_review",
    "human_review_required",
    "force_review",
    "explicit_human_review",
    "manual_review_required",
    "human_override_needs_review",
    "review_override",
)


def secondary_validation_gates(record: dict[str, Any] | None = None, label: str = "secondary_only") -> dict[str, str]:
    """Return validation gates that do not describe secondary evidence as missing controls."""

    names = set(VALIDATION_GATE_NAMES)
    if record and isinstance(record.get("validation_gates"), dict):
        names.update(str(key) for key in record["validation_gates"])
    return {name: label for name in sorted(names)}


def reference_conflict_reasons(record: dict[str, Any]) -> list[str]:
    """Return reasons a reference span cannot use the stable auto-secondary route."""

    if normalize_provenance_type(str(record.get("provenance_type") or "unknown")) != "reference":
        return []
    reasons = _list_values(record.get("reference_conflict_reasons"))
    if str(record.get("text_class") or "").strip() != "reference_list":
        reasons.append("reference_list_unconfirmed")
    risk_flags = set(_list_values(record.get("overclaim_risk_flags")))
    if _truthy(record.get("text_class_provenance_conflict")) or "text_class_provenance_conflict" in risk_flags:
        reasons.append("text_class_provenance_conflict")
    if _truthy(record.get("reaction_family_conflict")):
        reasons.append("reaction_family_conflict")
    if _rule_llm_boundary_disagreement(record):
        reasons.append("rule_llm_boundary_disagreement")
    llm_flags = set(_list_values(record.get("llm_audit_flags")))
    if (
        str(record.get("llm_parse_error") or "").strip()
        or str(record.get("llm_schema_error") or "").strip()
        or str(record.get("llm_verification_parse_error") or "").strip()
        or "llm_parse_or_schema_error" in llm_flags
    ):
        reasons.append("llm_verification_error")
    if any(_truthy(record.get(field)) for field in MANUAL_REVIEW_FIELDS) or str(
        record.get("human_review_status") or ""
    ).strip() == "needs_second_reviewer":
        reasons.append("manual_human_review_required")
    return _dedupe(reasons)


def is_stable_reference(record: dict[str, Any]) -> bool:
    """Return True only for an unconflicted reference-list span."""

    return (
        normalize_provenance_type(str(record.get("provenance_type") or "unknown")) == "reference"
        and str(record.get("text_class") or "").strip() == "reference_list"
        and not reference_conflict_reasons(record)
    )


def apply_secondary_evidence_semantics(record: dict[str, Any]) -> dict[str, Any]:
    """Apply opt-in secondary hardening while preserving the source span."""

    routed = dict(record)
    provenance_type = normalize_provenance_type(str(routed.get("provenance_type") or "unknown"))
    text_class = str(routed.get("text_class") or "").strip()
    original_reference_conflicts = reference_conflict_reasons(routed) if provenance_type == "reference" else []

    routed.setdefault("auto_secondary_reference", False)
    routed.setdefault("reference_sampled_for_audit", False)
    routed.setdefault("reference_conflict_review", False)

    if provenance_type == "reference":
        routed["maximum_supported_boundary"] = "unsupported_or_secondary"
        routed["admissibility_status"] = "reject_or_low_trust_provenance"
        routed["validation_gates"] = secondary_validation_gates(routed)
        routed["missing_boundary_fields"] = ["primary body text"]
        routed["required_controls"] = []
        reasons = original_reference_conflicts
        routed["reference_conflict_reasons"] = reasons
        routed["reference_conflict_review"] = bool(reasons)
        routed["auto_secondary_reference"] = not reasons
        if not reasons:
            routed["detected_taxes"] = []
            routed["hidden_tax"] = []
            routed["hidden_tax_missing_measurements"] = ["primary_body_text_required"]
            routed["hidden_tax_required_controls"] = []
            routed["hidden_tax_severity"] = "none"
            routed["audit_priority_reasons"] = _without_mechanical_missing(routed.get("audit_priority_reasons"))
            routed["review_trigger_flags"] = _without_mechanical_missing(routed.get("review_trigger_flags"))
        return routed

    unpaired_caption = provenance_type in {"figure_caption", "scheme_caption"} and not (
        _truthy(routed.get("paired_body_evidence")) or _truthy(routed.get("paired_primary_body_evidence"))
    )
    if unpaired_caption:
        routed["maximum_supported_boundary"] = "unsupported_or_secondary"
        routed["admissibility_status"] = "context_only_caption"
        routed["validation_gates"] = secondary_validation_gates(routed)
        routed["paired_body_required"] = True
        routed["caption_context_only"] = True
        routed["missing_boundary_fields"] = ["primary body text pairing"]
        routed["audit_priority_reasons"] = _without_mechanical_missing(routed.get("audit_priority_reasons"))
        return routed

    if provenance_type == "review_table" or text_class == "review_table":
        routed["maximum_supported_boundary"] = "unsupported_or_secondary"
        routed["admissibility_status"] = "secondary_only"
        routed["validation_gates"] = secondary_validation_gates(routed)
        routed["missing_boundary_fields"] = ["primary body text", "source-specific validation evidence"]
        routed["audit_priority_reasons"] = _without_mechanical_missing(routed.get("audit_priority_reasons"))
        return routed

    return routed


def select_reference_spans_for_audit(
    records: Iterable[dict[str, Any]],
    *,
    seed: str = REFERENCE_AUDIT_HASH_NAMESPACE,
    sample_rate: float = REFERENCE_AUDIT_SAMPLE_RATE,
    max_per_paper: int = MAX_REFERENCE_SPANS_PER_PAPER_FOR_AUDIT,
) -> set[str]:
    """Select ordinary reference spans with a stable hash and per-paper cap."""

    rate = min(1.0, max(0.0, float(sample_rate)))
    limit = max(0, int(max_per_paper))
    if rate == 0.0 or limit == 0:
        return set()

    candidates: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for record in records:
        if not is_stable_reference(record):
            continue
        source_span_id = str(record.get("source_span_id") or record.get("span_id") or "").strip()
        if not source_span_id:
            continue
        score = _stable_hash_int(source_span_id, seed)
        if score / float(2**256) >= rate:
            continue
        paper_id = str(record.get("paper_id") or "<missing-paper-id>").strip() or "<missing-paper-id>"
        candidates[paper_id].append((score, source_span_id))

    selected: set[str] = set()
    for paper_candidates in candidates.values():
        paper_candidates.sort(key=lambda item: (item[0], item[1]))
        selected.update(source_span_id for _, source_span_id in paper_candidates[:limit])
    return selected


def apply_reference_audit_sampling(
    records: list[dict[str, Any]],
    *,
    seed: str = REFERENCE_AUDIT_HASH_NAMESPACE,
    sample_rate: float = REFERENCE_AUDIT_SAMPLE_RATE,
    max_per_paper: int = MAX_REFERENCE_SPANS_PER_PAPER_FOR_AUDIT,
) -> list[dict[str, Any]]:
    """Mark the deterministic ordinary-reference audit sample; conflicts stay routed separately."""

    selected = select_reference_spans_for_audit(records, seed=seed, sample_rate=sample_rate, max_per_paper=max_per_paper)
    output: list[dict[str, Any]] = []
    for original in records:
        record = dict(original)
        source_span_id = str(record.get("source_span_id") or record.get("span_id") or "").strip()
        sampled = source_span_id in selected and is_stable_reference(record)
        record["reference_sampled_for_audit"] = sampled
        if sampled:
            flags = _list_values(record.get("review_trigger_flags"))
            reasons = _list_values(record.get("audit_priority_reasons"))
            record["review_trigger_flags"] = _dedupe([*flags, "reference_audit_sample"])
            record["audit_priority_reasons"] = _dedupe([*reasons, "reference_audit_sample"])
            record["overall_needs_human_review"] = True
            record["needs_human_review"] = True
            record["review_priority_band"] = "medium"
        output.append(record)
    return output


def _stable_hash_int(source_span_id: str, seed: str) -> int:
    payload = f"{seed}\0{source_span_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest(), "big")


def _rule_llm_boundary_disagreement(record: dict[str, Any]) -> bool:
    explicit_agreement = _explicit_bool(record.get("boundary_agreement"))
    if explicit_agreement is not None:
        return not explicit_agreement
    rule_boundary = str(record.get("maximum_supported_boundary") or record.get("rule_maximum_supported_boundary") or "").strip()
    llm_boundary = str(record.get("llm_maximum_supported_boundary") or "").strip()
    return bool(rule_boundary and llm_boundary and rule_boundary != llm_boundary)


def _explicit_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().casefold()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    return None


def _without_mechanical_missing(value: Any) -> list[str]:
    return [item for item in _list_values(value) if item not in MECHANICAL_MISSING_AUDIT_REASONS]


def _list_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y", "required", "force", "forced"}


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
