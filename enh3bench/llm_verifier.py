"""Optional LLM verification layer for eNH3-BoundaryLedger outputs."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from enh3bench.boundary_schema import boundary_rank
from enh3bench.ledger_router import load_jsonl
from enh3bench.llm_clients.base import BaseLLMClient, LLMClientError, sanitize_model_name_for_path
from enh3bench.provenance_rules import is_low_trust_provenance, low_trust_reason, normalize_provenance_type


REQUIRED_LLM_TOP_LEVEL_KEYS = [
    "text_class",
    "field_support",
    "maximum_supported_boundary",
    "missing_boundary_fields",
    "hidden_tax",
    "required_controls",
    "overclaim_risk",
    "recommended_experiment",
    "reasoning",
]

REQUIRED_FIELD_SUPPORT_KEYS = [
    "FE",
    "NH3_yield",
    "EE",
    "current_density",
    "potential_or_voltage",
    "runtime",
    "isotope_15N",
    "blank_control",
    "NOx_control",
    "reactor_type",
    "HOR",
    "product_state",
    "capture_route",
    "solvent_inventory",
    "failure_mode",
]

ALLOWED_FIELD_SUPPORT_VALUES = [
    "explicit",
    "missing",
    "unclear",
    "secondary_only",
]

ALLOWED_LLM_BOUNDARIES = [
    "unsupported_or_secondary",
    "product_admissibility",
    "cell_metric",
    "reactor_legibility",
    "process_partial",
    "plant_facing_insufficient",
]

FIELD_SUPPORT_KEYS = tuple(REQUIRED_FIELD_SUPPORT_KEYS)


def load_claim_rights_records(run_name: str, base_dir: str | Path = "data/boundary_ledger") -> list[dict[str, Any]]:
    """Load claim-rights records, falling back to evidence bundles."""

    run_dir = Path(base_dir) / run_name
    records = load_jsonl(run_dir / "claim_rights_ledger.jsonl")
    if records:
        return records
    return load_jsonl(run_dir / "evidence_bundles.jsonl")


def build_verification_prompt(record: dict[str, Any]) -> list[dict[str, str]]:
    """Build a strict source-grounded verification prompt for one record."""

    system = (
        "You are an evidence verifier for electrochemical ammonia synthesis literature.\n"
        "You must verify only what is explicitly supported by the provided source text.\n"
        "Do not use outside knowledge.\n"
        "Do not upgrade claims beyond the evidence.\n"
        "Do not treat review tables, references, captions, metadata, or supplementary text as primary experimental body evidence unless explicitly paired with primary body text.\n"
        "Captions are context-only unless paired with primary body text. For unpaired captions, maximum_supported_boundary must remain unsupported_or_secondary.\n"
        "If a caption contains FE, yield, 15N, flow, or reactor information, describe the needed primary body pairing in required_controls rather than upgrading the boundary.\n"
        "Return strict JSON only."
    )
    rule_payload = {
        "source_text": str(record.get("source_text") or record.get("source_span") or record.get("text") or ""),
        "text_class": str(record.get("text_class") or "unknown"),
        "provenance_type": str(record.get("provenance_type") or "unknown"),
        "rule_claim_type": str(record.get("claim_type") or ""),
        "rule_maximum_supported_boundary": str(record.get("maximum_supported_boundary") or ""),
        "rule_support_hint_boundary": str(record.get("support_hint_boundary") or ""),
        "caption_context_only": bool(record.get("caption_context_only")),
        "paired_body_required": bool(record.get("paired_body_required")),
        "rule_admissibility_status": str(record.get("admissibility_status") or ""),
        "rule_missing_boundary_fields": record.get("missing_boundary_fields") or [],
        "rule_hidden_tax": record.get("hidden_tax") or record.get("detected_taxes") or [],
        "rule_required_controls": record.get("required_controls") or [],
        "rule_overclaim_risk": record.get("overclaim_risk_flags") or [],
        "rule_recommended_experiment": record.get("recommended_experiment") or [],
    }
    expected_schema = {
        "text_class": "string",
        "field_support": {key: "explicit|missing|unclear|secondary_only" for key in FIELD_SUPPORT_KEYS},
        "maximum_supported_boundary": (
            "unsupported_or_secondary|product_admissibility|cell_metric|reactor_legibility|"
            "process_partial|plant_facing_insufficient"
        ),
        "missing_boundary_fields": ["string"],
        "hidden_tax": ["string"],
        "required_controls": ["string"],
        "overclaim_risk": ["string"],
        "recommended_experiment": "string",
        "reasoning": "string, <=120 words, source-grounded",
    }
    user = (
        "Record to verify:\n"
        f"{json.dumps(rule_payload, ensure_ascii=True, indent=2, sort_keys=True)}\n"
        "Return strict JSON with exactly these top-level keys:\n"
        f"{json.dumps(expected_schema, ensure_ascii=True, indent=2, sort_keys=True)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_llm_json_response(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse strict JSON, allowing surrounding markdown code fences."""

    cleaned = str(text or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return None, f"json_parse_error: {exc.msg}"
    valid, schema_messages = validate_llm_verification_schema(parsed)
    if not valid:
        return None, f"schema_invalid: {'; '.join(schema_messages)}"
    return parsed, None


def validate_llm_verification_schema(obj: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate the strict LLM verification response schema."""

    messages: list[str] = []
    if not isinstance(obj, dict):
        return False, ["object_must_be_dict"]

    missing_top_level = [key for key in REQUIRED_LLM_TOP_LEVEL_KEYS if key not in obj]
    messages.extend(f"missing_top_level_key:{key}" for key in missing_top_level)

    field_support = obj.get("field_support")
    if not isinstance(field_support, dict):
        messages.append("field_support_must_be_dict")
    else:
        missing_field_keys = [key for key in REQUIRED_FIELD_SUPPORT_KEYS if key not in field_support]
        messages.extend(f"missing_field_support_key:{key}" for key in missing_field_keys)
        for key, value in field_support.items():
            if key in REQUIRED_FIELD_SUPPORT_KEYS and value not in ALLOWED_FIELD_SUPPORT_VALUES:
                messages.append(f"invalid_field_support_value:{key}={value}")

    boundary = obj.get("maximum_supported_boundary")
    if boundary not in ALLOWED_LLM_BOUNDARIES:
        messages.append(f"invalid_maximum_supported_boundary:{boundary}")

    for key in ("missing_boundary_fields", "hidden_tax", "required_controls", "overclaim_risk"):
        if key in obj and not isinstance(obj.get(key), list):
            messages.append(f"{key}_must_be_list")

    for key in ("recommended_experiment", "reasoning"):
        if key in obj and not isinstance(obj.get(key), str):
            messages.append(f"{key}_must_be_string")

    warnings: list[str] = []
    reasoning = obj.get("reasoning")
    if isinstance(reasoning, str) and len(re.findall(r"\S+", reasoning)) > 150:
        warnings.append("reasoning_too_long")

    invalid_messages = [message for message in messages if message != "reasoning_too_long"]
    return not invalid_messages, invalid_messages or warnings


def verify_record_with_llm(
    record: dict[str, Any],
    client: BaseLLMClient,
    model: str | None = None,
) -> dict[str, Any]:
    """Verify a rule record and return the original record plus LLM audit fields."""

    messages = build_verification_prompt(record)
    raw_response = client.chat(
        messages,
        model=model,
        temperature=float(getattr(client, "temperature", 0)),
        max_tokens=int(getattr(client, "max_tokens", 1200)),
        response_format={"type": "json_object"},
        timeout=int(getattr(client, "timeout", 60)),
    )
    parsed, parse_error = parse_llm_json_response(raw_response)
    verified = dict(record)
    verified["llm_model"] = model or getattr(client, "model", None) or "unknown"
    verified["llm_verification"] = parsed
    verified["llm_raw_response"] = raw_response
    verified["llm_parse_error"] = parse_error
    verified["verification_timestamp_utc"] = _utc_now()
    low_trust = _low_trust_provenance(record)
    rule_boundary = _rule_boundary(record)
    verified["low_trust_provenance"] = low_trust
    verified["low_trust_provenance_reason"] = low_trust_reason(str(record.get("provenance_type") or "unknown")) if low_trust else ""

    if parsed is None:
        verified.update(
            {
                "boundary_agreement": False,
                "text_class_agreement": False,
                "llm_more_permissive": False,
                "llm_more_conservative": False,
                "missing_field_disagreement": [],
                "required_control_disagreement": [],
                "needs_human_review": True,
                "llm_audit_flags": ["llm_parse_or_schema_error"],
                "trusted_llm_maximum_supported_boundary": rule_boundary,
                "trusted_llm_boundary_reason": "LLM response could not be parsed or schema-validated.",
            }
        )
        return verified

    comparison = compare_rule_and_llm(record, parsed)
    verified.update(comparison)
    return verified


def verify_records_with_llm(
    records: list[dict[str, Any]],
    client: BaseLLMClient,
    model: str | None = None,
    max_records: int | None = None,
    fail_fast: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Verify records and return successful result rows plus failure rows."""

    selected = records[:max_records] if max_records is not None else records
    results: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for record in selected:
        try:
            verified = verify_record_with_llm(record, client, model=model)
        except LLMClientError as exc:
            failures.append(
                _failure_record(
                    record,
                    model or getattr(client, "model", None),
                    str(exc),
                    error_type="llm_client_error",
                )
            )
            if fail_fast:
                break
            continue
        results.append(verified)
        if verified.get("llm_parse_error"):
            error_message = str(verified.get("llm_parse_error"))
            failures.append(
                _failure_record(
                    record,
                    verified.get("llm_model"),
                    error_message,
                    error_type=_parse_or_schema_error_type(error_message),
                    llm_raw_response=str(verified.get("llm_raw_response") or ""),
                )
            )
            if fail_fast:
                break
    return results, failures


def compare_rule_and_llm(record: dict[str, Any], llm_result: dict[str, Any]) -> dict[str, Any]:
    """Compare rule BoundaryLedger output with LLM verification output."""

    rule_boundary = str(record.get("maximum_supported_boundary") or "unsupported_or_secondary")
    llm_boundary = str(llm_result.get("maximum_supported_boundary") or "unsupported_or_secondary")
    rule_rank = boundary_rank(rule_boundary)
    llm_rank = boundary_rank(llm_boundary)
    rule_text_class = str(record.get("text_class") or "")
    llm_text_class = str(llm_result.get("text_class") or "")
    missing_disagreement = _symmetric_difference(record.get("missing_boundary_fields") or [], llm_result.get("missing_boundary_fields") or [])
    required_disagreement = _symmetric_difference(record.get("required_controls") or [], llm_result.get("required_controls") or [])
    flags: list[str] = []

    llm_more_permissive = llm_rank > rule_rank
    llm_more_conservative = llm_rank < rule_rank
    needs_human_review = False
    if llm_more_permissive:
        needs_human_review = True
        flags.append("llm_more_permissive_than_rule")
    if llm_more_conservative:
        needs_human_review = True
        flags.append("llm_more_conservative_than_rule")
    if missing_disagreement:
        needs_human_review = True
        flags.append("missing_boundary_field_disagreement")
    if required_disagreement:
        needs_human_review = True
        flags.append("required_control_disagreement")

    provenance_type = normalize_provenance_type(str(record.get("provenance_type") or "unknown"))
    low_trust = _low_trust_provenance(record)
    low_trust_provenance_reason = low_trust_reason(provenance_type) if low_trust else ""
    trusted_boundary = llm_boundary
    trusted_boundary_reason = "No low-trust provenance cap applied."
    if low_trust and llm_rank > rule_rank:
        needs_human_review = True
        flags.append("llm_overrode_low_trust_provenance")
        flags.append("trusted_boundary_capped_by_provenance")
        trusted_boundary = rule_boundary
        trusted_boundary_reason = "LLM output was more permissive than a low-trust provenance-constrained rule boundary."
    elif low_trust:
        trusted_boundary_reason = "LLM output did not exceed low-trust provenance constraint."

    if _unpaired_caption(record) and llm_rank > boundary_rank("unsupported_or_secondary"):
        needs_human_review = True
        flags.append("llm_upgraded_unpaired_caption")
        trusted_boundary = "unsupported_or_secondary"
        trusted_boundary_reason = "Unpaired caption cannot establish primary boundary."

    field_support = llm_result.get("field_support") if isinstance(llm_result.get("field_support"), dict) else {}
    isotope_support = str(field_support.get("isotope_15N") or "").casefold()
    if isotope_support == "explicit" and not _source_mentions_isotope(str(record.get("source_text") or "")):
        needs_human_review = True
        flags.append("possible_unsupported_isotope_claim")

    text_class_agreement = rule_text_class == llm_text_class
    if not text_class_agreement:
        flags.append("text_class_disagreement")

    return {
        "boundary_agreement": rule_boundary == llm_boundary,
        "text_class_agreement": text_class_agreement,
        "llm_more_permissive": llm_more_permissive,
        "llm_more_conservative": llm_more_conservative,
        "missing_field_disagreement": missing_disagreement,
        "required_control_disagreement": required_disagreement,
        "needs_human_review": needs_human_review,
        "llm_audit_flags": _dedupe(flags),
        "trusted_llm_maximum_supported_boundary": trusted_boundary,
        "trusted_llm_boundary_reason": trusted_boundary_reason,
        "low_trust_provenance": low_trust,
        "low_trust_provenance_reason": low_trust_provenance_reason,
    }


def export_llm_verification_results(
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    run_name: str,
    model: str,
    output_dir: str | Path = "data/llm_verification",
) -> dict[str, Any]:
    """Export LLM verification result and failure ledgers."""

    run_dir = Path(output_dir) / run_name / sanitize_model_name_for_path(model)
    jsonl_path = run_dir / "llm_verified_claims.jsonl"
    csv_path = run_dir / "llm_verified_claims.csv"
    failures_path = run_dir / "llm_failures.jsonl"
    _write_jsonl(results, jsonl_path)
    _write_csv(results, csv_path)
    _write_jsonl(failures, failures_path)
    return {
        "run_name": run_name,
        "model": model,
        "count": len(results),
        "failures": len(failures),
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
        "failures_jsonl": str(failures_path),
    }


def load_llm_verification_results(
    run_name: str,
    model: str,
    output_dir: str | Path = "data/llm_verification",
) -> list[dict[str, Any]]:
    """Load exported LLM verification result records."""

    path = Path(output_dir) / run_name / sanitize_model_name_for_path(model) / "llm_verified_claims.jsonl"
    return load_jsonl(path)


def _failure_record(
    record: dict[str, Any],
    model: str | None,
    error: str,
    error_type: str = "llm_error",
    llm_raw_response: str = "",
) -> dict[str, Any]:
    return {
        "llm_model": model or "unknown",
        "claim_id": record.get("claim_id") or "",
        "paper_id": record.get("paper_id") or "",
        "source_span_id": record.get("source_span_id") or record.get("span_id") or "",
        "evidence_id": record.get("evidence_id") or "",
        "error_type": error_type,
        "error_message": error,
        "error": error,
        "llm_raw_response": llm_raw_response,
        "verification_timestamp_utc": _utc_now(),
    }


def _parse_or_schema_error_type(error: str) -> str:
    if error.startswith("schema_invalid:"):
        return "schema_invalid"
    if error.startswith("json_parse_error:"):
        return "json_parse_error"
    return "llm_parse_or_schema_error"


def _rule_boundary(record: dict[str, Any]) -> str:
    return str(record.get("maximum_supported_boundary") or "unsupported_or_secondary")


def _low_trust_provenance(record: dict[str, Any]) -> bool:
    provenance_type = str(record.get("provenance_type") or "unknown")
    return _truthy(record.get("is_reject_or_low_trust")) or is_low_trust_provenance(provenance_type)


def _unpaired_caption(record: dict[str, Any]) -> bool:
    provenance_type = normalize_provenance_type(str(record.get("provenance_type") or "unknown"))
    if provenance_type not in {"figure_caption", "scheme_caption"}:
        return False
    return not (_truthy(record.get("paired_body_evidence")) or _truthy(record.get("paired_primary_body_evidence")))


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"true", "1", "yes", "y"}


def _symmetric_difference(left: list[Any], right: list[Any]) -> list[str]:
    left_set = {str(item) for item in left}
    right_set = {str(item) for item in right}
    return sorted(left_set.symmetric_difference(right_set))


def _source_mentions_isotope(source_text: str) -> bool:
    text = source_text.casefold()
    return bool(re.search(r"\b15\s*n(?:2|h3|h4)?\b", text)) or "isotope" in text or "isotopic" in text


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            deduped.append(item)
    return deduped


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, default=str, separators=(",", ":")))
            handle.write("\n")


def _write_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _fieldnames(records)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: _csv_value(record.get(field)) for field in fieldnames})


def _fieldnames(records: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "claim_id",
        "paper_id",
        "source_span_id",
        "evidence_id",
        "text_class",
        "provenance_type",
        "claim_type",
        "maximum_supported_boundary",
        "support_hint_boundary",
        "paired_body_required",
        "caption_context_only",
        "admissibility_status",
        "llm_model",
        "llm_verification",
        "llm_raw_response",
        "llm_parse_error",
        "trusted_llm_maximum_supported_boundary",
        "trusted_llm_boundary_reason",
        "low_trust_provenance",
        "low_trust_provenance_reason",
        "boundary_agreement",
        "text_class_agreement",
        "llm_more_permissive",
        "llm_more_conservative",
        "needs_human_review",
        "llm_audit_flags",
        "missing_field_disagreement",
        "required_control_disagreement",
        "verification_timestamp_utc",
        "source_text",
    ]
    names: set[str] = set(preferred)
    for record in records:
        names.update(record)
    ordered = [name for name in preferred if name in names]
    ordered.extend(sorted(name for name in names if name not in set(ordered)))
    return ordered


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return str(value)
