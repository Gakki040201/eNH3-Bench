"""Claim-rights adjudication for eNH3-BoundaryLedger."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from enh3bench.boundary_schema import (
    BOUNDARY_FIELDS,
    SUPPORT_HINT_FIELD,
    boundary_rank,
    coerce_float,
    has_any_value,
    max_boundary,
    normalize_yes_no,
)
from enh3bench.document_provenance import infer_provenance_for_record
from enh3bench.provenance_rules import (
    is_reject_or_low_trust,
    is_secondary_or_context,
    normalize_provenance_type,
)


PRIMARY_CLASSES = {"primary_performance", "primary_performance_with_validation"}
NEGATIVE_CLASSES = {"contamination_detection_evidence", "contamination_reassignment_evidence"}


def classify_claim_rights(record: dict[str, Any]) -> dict[str, Any]:
    """Classify what boundary a source-grounded record is allowed to support."""

    merged = _merged_record(record)
    text_class = str(merged.get("text_class") or "unknown").strip() or "unknown"
    _ensure_provenance_fields(merged)
    provenance_type = str(merged.get("provenance_type") or "unknown")
    source_text = _source_text(merged)
    fields = _boundary_field_presence(merged)
    present, missing = _present_missing_by_boundary(fields)
    validation_gates = _validation_gates(merged)
    required_controls = _required_controls(merged, fields, validation_gates)
    risk_flags: list[str] = _provenance_risk_flags(text_class, provenance_type)
    reasoning: list[str] = []

    provenance_override = _provenance_override(
        merged,
        text_class,
        provenance_type,
        fields,
        present,
        missing,
        validation_gates,
        required_controls,
        risk_flags,
        source_text,
    )
    if provenance_override is not None:
        return provenance_override

    if provenance_type == "supplementary":
        risk_flags.append("supplementary_requires_crosscheck")
        reasoning.append("supplementary provenance allows extraction but requires source linkage to primary body evidence.")

    if text_class == "reference_list":
        reasoning.append("reference lists cannot support primary eNH3 claims.")
        return _result(
            merged,
            text_class,
            "unsupported_claim",
            "unsupported_or_secondary",
            "reject",
            present,
            missing,
            validation_gates,
            ["all primary boundary fields require source text outside the reference list"],
            risk_flags,
            required_controls,
            ["Use primary methods/results spans rather than references."],
            reasoning,
            source_text,
        )

    if text_class == "review_table":
        reasoning.append("review tables cannot become primary performance evidence.")
        return _result(
            merged,
            text_class,
            "secondary_summary_claim",
            "unsupported_or_secondary",
            "secondary_only",
            present,
            missing,
            validation_gates,
            ["primary source span", "source-specific validation evidence"],
            _dedupe([*risk_flags, "secondary_source_overclaim"]),
            required_controls,
            ["Trace the summarized entry to its primary source and rerun claim-rights adjudication."],
            reasoning,
            source_text,
        )

    if text_class == "protocol_guideline":
        reasoning.append("protocol text informs the validation rubric but not a performance claim.")
        return _result(
            merged,
            text_class,
            "protocol_claim",
            "product_admissibility",
            "protocol_only",
            present,
            missing,
            validation_gates,
            missing.get("product_admissibility", []),
            risk_flags,
            required_controls,
            ["Apply the protocol gates to a primary performance span."],
            reasoning,
            source_text,
        )

    if text_class in NEGATIVE_CLASSES:
        reasoning.append("contamination evidence can support negative or reassignment claims, not positive performance.")
        negative_controls = _missing_contamination_controls(validation_gates)
        return _result(
            merged,
            text_class,
            "negative_evidence_claim",
            "product_admissibility",
            "negative_evidence",
            present,
            missing,
            validation_gates,
            negative_controls,
            ["negative_evidence_blocks_positive_claim"],
            _dedupe([*required_controls, *negative_controls]),
            ["Resolve contamination origin before treating the ammonia signal as N2-derived."],
            reasoning,
            source_text,
        )

    if text_class == "computational_screening":
        reasoning.append("computational screening does not establish an electrochemical NH3 performance claim.")
        return _result(
            merged,
            text_class,
            "unsupported_claim",
            "unsupported_or_secondary",
            "computational_only",
            present,
            missing,
            validation_gates,
            ["experimental NH3 quantification", "validation controls"],
            risk_flags,
            required_controls,
            ["Pair screening claims with experimentally validated primary performance evidence."],
            reasoning,
            source_text,
        )

    if text_class not in PRIMARY_CLASSES:
        reasoning.append("source class is not primary performance evidence.")
        return _result(
            merged,
            text_class,
            "unsupported_claim",
            "unsupported_or_secondary",
            "insufficient_primary_support",
            present,
            missing,
            validation_gates,
            ["primary performance source class"],
            risk_flags,
            required_controls,
            ["Use primary performance or validated primary performance spans."],
            reasoning,
            source_text,
        )

    claim_type = _claim_type(merged, fields)
    boundary, boundary_reasons, primary_risk_flags = _primary_boundary(merged, text_class, fields, validation_gates)
    risk_flags = _dedupe([*risk_flags, *primary_risk_flags])
    reasoning.extend(boundary_reasons)
    admissibility_status = _admissibility_status(boundary, fields, validation_gates, source_text)
    if not source_text:
        admissibility_status = "weak_grounding"
        boundary = "unsupported_or_secondary"
        risk_flags.append("weak_source_grounding")
        reasoning.append("no source_text is available for source-grounded adjudication.")

    missing_boundary_fields = _missing_boundary_fields(boundary, missing, fields, merged)
    recommended_experiment = _recommended_experiment(boundary, required_controls, missing_boundary_fields, risk_flags)
    return _result(
        merged,
        text_class,
        claim_type,
        boundary,
        admissibility_status,
        present,
        missing,
        validation_gates,
        missing_boundary_fields,
        risk_flags,
        required_controls,
        recommended_experiment,
        reasoning,
        source_text,
    )


def classify_claim_rights_many(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Classify claim rights for many records."""

    return [classify_claim_rights(record) for record in records]


def export_claim_rights_ledger(
    records: list[dict[str, Any]],
    run_name: str,
    output_dir: str | Path = "data/boundary_ledger",
) -> dict[str, Any]:
    """Write claim-rights records as JSONL and CSV."""

    classified = classify_claim_rights_many(records)
    run_dir = Path(output_dir) / run_name
    jsonl_path = run_dir / "claim_rights_ledger.jsonl"
    csv_path = run_dir / "claim_rights_ledger.csv"
    _write_jsonl(classified, jsonl_path)
    _write_csv(classified, csv_path)
    return {
        "run_name": run_name,
        "count": len(classified),
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
    }


def _result(
    record: dict[str, Any],
    text_class: str,
    claim_type: str,
    maximum_supported_boundary: str,
    admissibility_status: str,
    boundary_fields_present: dict[str, list[str]],
    boundary_fields_missing: dict[str, list[str]],
    validation_gates: dict[str, str],
    missing_boundary_fields: list[str],
    overclaim_risk_flags: list[str],
    required_controls: list[str],
    recommended_experiment: list[str],
    reasoning: list[str],
    source_text: str,
) -> dict[str, Any]:
    return {
        "claim_id": _claim_id(record),
        "paper_id": str(record.get("paper_id") or ""),
        "source_span_id": str(record.get("source_span_id") or record.get("span_id") or ""),
        "evidence_id": str(record.get("evidence_id") or ""),
        "text_class": text_class,
        "provenance_type": str(record.get("provenance_type") or "unknown"),
        "provenance_confidence": str(record.get("provenance_confidence") or "low"),
        "provenance_signals": record.get("provenance_signals") or [],
        "is_primary_admissible": bool(record.get("is_primary_admissible", False)),
        "is_secondary_or_context": bool(record.get("is_secondary_or_context", False)),
        "is_reject_or_low_trust": bool(record.get("is_reject_or_low_trust", False)),
        "provenance_constrained": bool(record.get("provenance_constrained", False)),
        "text_class_provenance_conflict": bool(record.get("text_class_provenance_conflict", False)),
        "claim_type": claim_type,
        "maximum_supported_boundary": maximum_supported_boundary,
        "admissibility_status": admissibility_status,
        SUPPORT_HINT_FIELD: str(record.get(SUPPORT_HINT_FIELD) or "unsupported_or_secondary"),
        "paired_body_required": _truthy(record.get("paired_body_required")),
        "caption_context_only": _truthy(record.get("caption_context_only")),
        "paired_caption_context": _truthy(record.get("paired_caption_context")),
        "missing_boundary_fields": _dedupe(missing_boundary_fields),
        "validation_gates": validation_gates,
        "boundary_fields_present": boundary_fields_present,
        "boundary_fields_missing": boundary_fields_missing,
        "overclaim_risk_flags": _dedupe(overclaim_risk_flags),
        "required_controls": _dedupe(required_controls),
        "recommended_experiment": _dedupe(recommended_experiment),
        "reasoning": _dedupe(reasoning),
        "source_text": source_text,
    }


def _merged_record(record: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    raw_record = record.get("raw_record")
    if isinstance(raw_record, dict):
        merged.update(raw_record)
    extracted_fields = record.get("extracted_fields")
    if isinstance(extracted_fields, dict):
        merged.update(extracted_fields)
    merged.update(record)
    if not merged.get("source_text"):
        for key in ("source_span", "text"):
            if merged.get(key):
                merged["source_text"] = merged[key]
                break
    if not merged.get("span_id") and merged.get("source_span_id"):
        merged["span_id"] = merged["source_span_id"]
    return merged


def _ensure_provenance_fields(record: dict[str, Any]) -> None:
    if not record.get("provenance_type"):
        provenance = infer_provenance_for_record(record)
    else:
        provenance = record
    provenance_type = normalize_provenance_type(str(provenance.get("provenance_type") or "unknown"))
    record["provenance_type"] = provenance_type
    record["provenance_confidence"] = provenance.get("provenance_confidence") or provenance.get("confidence") or "low"
    record["provenance_signals"] = provenance.get("provenance_signals") or provenance.get("signals") or []
    record["is_primary_admissible"] = bool(provenance.get("is_primary_admissible", False))
    record["is_secondary_or_context"] = bool(provenance.get("is_secondary_or_context", is_secondary_or_context(provenance_type)))
    record["is_reject_or_low_trust"] = bool(provenance.get("is_reject_or_low_trust", is_reject_or_low_trust(provenance_type)))


def _provenance_risk_flags(text_class: str, provenance_type: str) -> list[str]:
    flags: list[str] = []
    normalized = normalize_provenance_type(provenance_type)
    if _text_class_provenance_conflict(text_class, normalized):
        flags.append("text_class_provenance_conflict")
    return flags


def _provenance_override(
    record: dict[str, Any],
    text_class: str,
    provenance_type: str,
    fields: dict[str, bool],
    present: dict[str, list[str]],
    missing: dict[str, list[str]],
    validation_gates: dict[str, str],
    required_controls: list[str],
    risk_flags: list[str],
    source_text: str,
) -> dict[str, Any] | None:
    normalized = normalize_provenance_type(provenance_type)
    if "text_class_provenance_conflict" in risk_flags:
        record["text_class_provenance_conflict"] = True

    if normalized in {"reference", "bibliography", "front_matter", "metadata", "copyright_note"}:
        record["provenance_constrained"] = True
        risk_flags = _dedupe([*risk_flags, "low_trust_provenance"])
        reasoning = [f"{normalized} provenance cannot establish primary eNH3 performance boundaries."]
        return _result(
            record,
            text_class,
            "unsupported_claim",
            "unsupported_or_secondary",
            "reject_or_low_trust_provenance",
            present,
            missing,
            validation_gates,
            ["primary body text"],
            risk_flags,
            required_controls,
            ["Use primary body/results/methods text before adjudicating performance claim rights."],
            reasoning,
            source_text,
        )

    if normalized == "review_table":
        record["provenance_constrained"] = True
        risk_flags = _dedupe([*risk_flags, "review_table_not_primary"])
        return _result(
            record,
            text_class,
            "secondary_summary_claim",
            "unsupported_or_secondary",
            "secondary_only",
            present,
            missing,
            validation_gates,
            ["primary body text", "source-specific validation evidence"],
            risk_flags,
            required_controls,
            ["Trace review-table rows to primary body text."],
            ["review-table provenance is secondary even when performance values are present."],
            source_text,
        )

    if normalized == "table":
        record["provenance_constrained"] = True
        if _own_result_table(record, fields):
            boundary = "cell_metric" if any(fields.get(name) for name in BOUNDARY_FIELDS["cell_metric"]) else "product_admissibility"
            return _result(
                record,
                text_class,
                "performance_claim",
                boundary,
                "table_metric_only_requires_body_pairing",
                present,
                missing,
                validation_gates,
                _missing_boundary_fields(boundary, missing, fields, record),
                _dedupe([*risk_flags, "table_requires_primary_body_pairing"]),
                _dedupe([*required_controls, "pair_with_primary_body_text"]),
                ["Pair original result table values with primary body text before stronger claim rights."],
                ["ordinary table provenance is capped at cell_metric without paired body evidence."],
                source_text,
            )
        return _result(
            record,
            text_class,
            "secondary_summary_claim",
            "unsupported_or_secondary",
            "secondary_only",
            present,
            missing,
            validation_gates,
            ["primary body text"],
            _dedupe([*risk_flags, "table_not_primary_body_text"]),
            _dedupe([*required_controls, "pair_with_primary_body_text"]),
            ["Pair table values with the paper's own body text."],
            ["table provenance is not primary body evidence unless clearly an original results table."],
            source_text,
        )

    if normalized in {"figure_caption", "scheme_caption"}:
        record["provenance_constrained"] = True
        paired = _truthy(record.get("paired_body_evidence")) or _truthy(record.get("paired_primary_body_evidence"))
        if paired:
            record["paired_caption_context"] = True
            return None
        record[SUPPORT_HINT_FIELD] = _caption_support_hint_boundary(record)
        record["paired_body_required"] = True
        record["caption_context_only"] = True
        return _result(
            record,
            text_class,
            _caption_claim_type(text_class),
            "unsupported_or_secondary",
            "context_only_caption",
            present,
            missing,
            validation_gates,
            ["primary body text pairing"],
            _dedupe([*risk_flags, "caption_not_primary_evidence", "pair_with_primary_body_text_required"]),
            _dedupe([*required_controls, "primary body text pairing", "pair_with_primary_body_text"]),
            ["Pair caption evidence with primary body text before performance claim-rights escalation."],
            ["Caption text is context only and cannot establish a primary boundary without paired body evidence."],
            source_text,
        )

    return None


def _claim_id(record: dict[str, Any]) -> str:
    for key in ("evidence_id", "source_span_id", "span_id"):
        value = str(record.get(key) or "").strip()
        if value:
            return f"CR_{value}"
    return "CR_TODO"


def _text_class_provenance_conflict(text_class: str, provenance_type: str) -> bool:
    if text_class in PRIMARY_CLASSES and (
        is_reject_or_low_trust(provenance_type) or provenance_type in {"review_table", "figure_caption", "scheme_caption"}
    ):
        return True
    if text_class in {"reference_list"} and provenance_type in {"body", "abstract", "methods", "results", "discussion"}:
        return True
    if text_class == "review_table" and provenance_type in {"body", "abstract", "methods", "results", "discussion"}:
        return True
    return False


def _own_result_table(record: dict[str, Any], fields: dict[str, bool]) -> bool:
    text = _normalized_text(record)
    if "review_table" == str(record.get("text_class") or ""):
        return False
    if _contains_any(text, ["previous reports", "previous studies", "literature summary", "review table"]):
        return False
    citation_hits = len(re.findall(r"\b(?:19|20)\d{2}\b|\bet al\.?", text))
    if "reference" in text and citation_hits >= 3:
        return False
    if _contains_any(text, ["this work", "our catalyst", "this study", "sample", "n-ov", "pristine"]):
        return True
    metric_present = any(fields.get(name) for name in BOUNDARY_FIELDS["cell_metric"])
    return metric_present and citation_hits < 3


def _caption_claim_type(text_class: str) -> str:
    if text_class == "protocol_guideline":
        return "protocol_claim"
    if text_class in NEGATIVE_CLASSES:
        return "negative_evidence_claim"
    if text_class in {"figure_caption", "background_context", "review_table"}:
        return "secondary_summary_claim"
    return "unsupported_claim"


def _caption_support_hint_boundary(record: dict[str, Any]) -> str:
    text = _normalized_text(record)
    candidates: list[str] = []
    if _contains_any(text, ["15n", "15 n", "isotope", "isotopic", "blank", "nox", "contamination", "contaminant"]):
        candidates.append("product_admissibility")
    if _caption_has_metric_terms(text):
        candidates.append("cell_metric")
    if _contains_any(
        text,
        [
            "flow",
            "gde",
            "gas diffusion",
            "hor",
            "hydrogen oxidation",
            "outlet",
            "runtime",
            "stability",
            "stable for",
        ],
    ):
        candidates.append("reactor_legibility")
    if _contains_any(
        text,
        [
            "capture",
            "solvent inventory",
            "electrolyte inventory",
            "recycle",
            "h2 source",
            "hydrogen source",
            "auxiliary",
            "tea",
            "technoeconomic",
        ],
    ):
        candidates.append("process_partial")
    return max_boundary(candidates)


def _caption_has_metric_terms(text: str) -> bool:
    return _contains_any(
        text,
        [
            "faradaic efficiency",
            "nh3 yield",
            "ammonia yield",
            "yield rate",
            "current density",
            "potential",
            "voltage",
            " v vs",
            "ma cm",
            "ma/cm",
        ],
    ) or bool(re.search(r"\bfe\b|\bfe\s*\(?%?\)?", text))


def _source_text(record: dict[str, Any]) -> str:
    for key in ("source_text", "source_span", "text"):
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _validation_gates(record: dict[str, Any]) -> dict[str, str]:
    text = _normalized_text(record)
    return {
        "isotope_15N": _gate(
            record,
            ("isotope_15N", "isotope_validation"),
            bool(re.search(r"\b15\s*n(?:2|h4|\b)", text)),
            bool(re.search(r"\bno\s+15\s*n|\bwithout\s+15\s*n", text)),
        ),
        "blank_control": _gate(
            record,
            ("blank_control",),
            _contains_any(text, ["blank control", "ar blank", "argon blank", "n2-free", "open circuit blank"]),
            bool(re.search(r"\bno\s+(?:specified\s+)?blank|\bwithout\s+blank", text)),
        ),
        "nox_control": _gate(
            record,
            ("nox_control", "nox_screening"),
            _contains_any(
                text,
                [
                    "nox screening",
                    "screening for nox",
                    "nitrate contamination",
                    "nitrite contamination",
                    "nitrate/nitrite",
                    "remove x-nh3 and nox",
                    "nox contaminants",
                ],
            ),
            False,
        ),
        "contamination_control": _gate(
            record,
            ("contamination_control",),
            _contains_any(
                text,
                [
                    "contamination control",
                    "contamination check",
                    "contamination checks",
                    "background ammonia",
                    "impurity",
                    "gas purification",
                    "scrubbed",
                    "contaminants",
                ],
            ),
            False,
        ),
        "quantification_method": _gate(
            record,
            ("quantification_method", "detection_method", "ammonia_quantification"),
            _contains_any(
                text,
                [
                    "indophenol",
                    "nessler",
                    "nmr",
                    "ion chromatography",
                    "colorimetric",
                    "calibration curve",
                    "standard addition",
                    "quantified",
                ],
            ),
            False,
        ),
    }


def _gate(record: dict[str, Any], keys: tuple[str, ...], text_yes: bool, text_no: bool) -> str:
    values = [normalize_yes_no(record.get(key)) for key in keys if key in record]
    if "yes" in values:
        return "yes"
    if text_yes:
        return "yes"
    if "no" in values or text_no:
        return "no"
    if "unclear" in values:
        return "unclear"
    return "missing"


def _boundary_field_presence(record: dict[str, Any]) -> dict[str, bool]:
    text = _normalized_text(record)
    gates = _validation_gates(record)
    fields = {
        "ammonia_quantification": gates["quantification_method"] == "yes",
        "isotope_15N": gates["isotope_15N"] == "yes",
        "blank_control": gates["blank_control"] == "yes",
        "nox_control": gates["nox_control"] == "yes",
        "contamination_control": gates["contamination_control"] == "yes",
        "faradaic_efficiency": _has_number(record, "faradaic_efficiency_percent", "FE_percent", "fe_percent")
        or _text_has_fe(text),
        "nh3_yield": _has_number(record, "nh3_yield_value", "NH3_yield", "nh3_yield")
        or _contains_any(text, ["nh3 yield", "ammonia yield", "yield rate", "production rate"]),
        "current_density": _has_number(record, "current_density_mA_cm2", "current_density")
        or _contains_any(text, ["current density", " ma cm", "ma/cm"]),
        "potential_or_voltage": _has_number(record, "potential_value", "voltage", "cell_voltage")
        or _contains_any(text, ["potential", "voltage", " v vs", "vvs", "two-electrode"]),
        "charge_or_runtime": _has_number(record, "charge", "runtime", "runtime_hours", "stability_hours")
        or _contains_any(text, [" charge", "coulomb", "runtime", "stability", "electrolysis", " for 2 h", " for 2 hours"]),
        "electrode_area": has_any_value(record, "electrode_area", "geometric_area")
        or _contains_any(text, ["cm-2", "cm^-2", "cm2", "surface area", "geometric area"]),
        "reactor_type": has_any_value(record, "reactor_type")
        or _contains_any(text, ["h-cell", "h cell", "divided cell", "flow cell", "reactor", "electrolyzer"]),
        "flow_rate": has_any_value(record, "flow_rate")
        or bool(re.search(r"\b\d+(?:\.\d+)?\s*m?l\s*min", text))
        or _contains_any(text, ["flow rate", "continuous flow"]),
        "active_area": has_any_value(record, "active_area")
        or _contains_any(text, ["active area", "geometric area", "electrode area"]),
        "GDE_or_SSC": has_any_value(record, "GDE_or_SSC", "gde", "solid_state_cell")
        or _contains_any(text, ["gde", "gas diffusion electrode", "ssc", "solid-state cell", "solid state cell"]),
        "HOR_or_anode_reaction": has_any_value(record, "HOR_or_anode_reaction", "anode_reaction")
        or _contains_any(text, [" hor", "hydrogen oxidation", "anode reaction", "h2 oxidation"]),
        "runtime_or_stability": has_any_value(record, "runtime_or_stability", "runtime", "runtime_hours", "stability_hours")
        or _contains_any(text, ["runtime", "stability", "stable for", "electrolysis process", "hours"]),
        "outlet_product_state": has_any_value(record, "outlet_product_state", "product_state")
        or _contains_any(
            text,
            ["gas-phase ammonia", "gas phase ammonia", "aqueous ammonia", "aqueous nh3", "nh4+", "ammonium", "acid trap", "outlet"],
        ),
        "wetting_or_failure_disclosure": has_any_value(record, "wetting_or_failure_disclosure", "failure_disclosure")
        or _contains_any(text, ["wetting", "flooding", "failure", "crossover", "water management"]),
        "gas_liquid_product_split": has_any_value(record, "gas_liquid_product_split", "product_split")
        or _contains_any(text, ["gas/liquid", "gas-liquid", "gas and liquid", "product accounting"]),
        "capture_route": has_any_value(record, "capture_route")
        or _contains_any(text, ["capture route", "acid trap", "scrubber", "outlet capture", "captured"]),
        "solvent_inventory": has_any_value(record, "solvent_inventory", "electrolyte_volume")
        or _contains_any(text, ["solvent inventory", "electrolyte volume", "electrolyte inventory", "thf", "water inventory"]),
        "electrolyte_replacement_or_recycle": has_any_value(record, "electrolyte_replacement_or_recycle")
        or _contains_any(text, ["electrolyte replacement", "electrolyte recycle", "recycle", "replenished"]),
        "hydrogen_source_boundary": has_any_value(record, "hydrogen_source_boundary", "hydrogen_source", "h2_source")
        or _contains_any(text, ["hydrogen source", "h2 supply", "h2 feed", "renewable hydrogen"]),
        "auxiliary_loads": has_any_value(record, "auxiliary_loads")
        or _contains_any(text, ["auxiliary load", "balance of plant", "compression", "pumping", "separation load"]),
        "voltage_basis": has_any_value(record, "voltage_basis")
        or _has_number(record, "potential_value", "voltage", "cell_voltage")
        or _contains_any(text, ["cell voltage", "voltage basis", "two-electrode", " v vs", "vvs"]),
        "first_failure_signal": has_any_value(record, "first_failure_signal")
        or _contains_any(text, ["first failure", "failure signal", "flooding", "wetting", "resistance increase", "passivation"]),
    }
    return fields


def _present_missing_by_boundary(fields: dict[str, bool]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    present: dict[str, list[str]] = {}
    missing: dict[str, list[str]] = {}
    for boundary, names in BOUNDARY_FIELDS.items():
        present[boundary] = [name for name in names if fields.get(name)]
        missing[boundary] = [name for name in names if not fields.get(name)]
    return present, missing


def _primary_boundary(
    record: dict[str, Any],
    text_class: str,
    fields: dict[str, bool],
    validation_gates: dict[str, str],
) -> tuple[str, list[str], list[str]]:
    reasons: list[str] = []
    risk_flags: list[str] = []
    candidates: list[str] = []
    metric_any = any(fields.get(name) for name in BOUNDARY_FIELDS["cell_metric"])
    metric_core = fields["faradaic_efficiency"] and fields["nh3_yield"] and (
        fields["potential_or_voltage"] or fields["current_density"]
    )
    validation_core = (
        validation_gates["isotope_15N"] == "yes"
        and validation_gates["blank_control"] == "yes"
        and (validation_gates["nox_control"] == "yes" or validation_gates["contamination_control"] == "yes")
    )

    if any(fields.get(name) for name in BOUNDARY_FIELDS["product_admissibility"]):
        candidates.append("product_admissibility")
    if metric_any:
        candidates.append("cell_metric")
        reasons.append("performance metrics are present, but claim rights depend on validation and metric completeness.")
    if metric_core and validation_core:
        candidates.append("cell_metric")
        reasons.append("FE/yield and potential/current are paired with core validation gates.")

    if _n2_claim(record) and validation_gates["isotope_15N"] != "yes":
        risk_flags.append("n2_claim_without_15n")
        reasons.append("N2-to-NH3 claims without explicit 15N cannot exceed cell_metric.")

    if fields["faradaic_efficiency"] and not (
        fields["nh3_yield"] and fields["charge_or_runtime"] and fields["potential_or_voltage"]
    ):
        risk_flags.append("fe_without_complete_measurement_matrix")
        reasons.append("FE is present without the yield/runtime/voltage matrix needed for stronger claims.")

    if text_class == "primary_performance_with_validation" and _reactor_ready(fields) and metric_any and validation_core:
        candidates.append("reactor_legibility")
        reasons.append("validated metrics are paired with enough reactor descriptors for reactor legibility.")

    if text_class == "primary_performance_with_validation" and _process_ready(fields) and metric_core and validation_core:
        candidates.append("process_partial")
        reasons.append("validated metrics are paired with a partial process boundary.")

    boundary = max_boundary(candidates)

    if _hor_claim(record) and not fields["hydrogen_source_boundary"]:
        risk_flags.append("hor_claim_missing_hydrogen_source")
        reasons.append("HOR claims without hydrogen source/logistics cannot exceed reactor_legibility.")
        if boundary_rank(boundary) > boundary_rank("reactor_legibility"):
            boundary = "reactor_legibility"

    if _flow_claim(record) and not (fields["outlet_product_state"] and fields["wetting_or_failure_disclosure"]):
        risk_flags.append("flow_claim_missing_outlet_or_wetting")
        reasons.append("flow claims need outlet product accounting and wetting/failure disclosure.")
        if boundary_rank(boundary) > boundary_rank("reactor_legibility"):
            boundary = "reactor_legibility"

    if _gas_phase_claim(record) and not fields["capture_route"]:
        risk_flags.append("gas_phase_nh3_without_capture_route")
        reasons.append("gas-phase NH3 claims need a capture route before process-level support.")
        if boundary_rank(boundary) > boundary_rank("reactor_legibility"):
            boundary = "reactor_legibility"

    if _plant_or_process_gesture(record) and not _process_ready(fields):
        risk_flags.append("plant_facing_without_process_closure")
        reasons.append("plant/process gestures lack recycle, auxiliary-load, or boundary closure.")
        if boundary_rank(boundary) >= boundary_rank("reactor_legibility") or _has_process_signal(fields):
            boundary = "plant_facing_insufficient"

    if boundary == "unsupported_or_secondary" and metric_any:
        boundary = "cell_metric"

    return boundary, reasons, risk_flags


def _claim_type(record: dict[str, Any], fields: dict[str, bool]) -> str:
    if _plant_or_process_gesture(record) or _has_process_signal(fields):
        return "process_claim"
    if _flow_claim(record) or _hor_claim(record) or any(fields.get(name) for name in BOUNDARY_FIELDS["reactor_legibility"]):
        return "reactor_claim"
    if any(fields.get(name) for name in BOUNDARY_FIELDS["product_admissibility"]) and not any(
        fields.get(name) for name in BOUNDARY_FIELDS["cell_metric"]
    ):
        return "validation_claim"
    return "performance_claim"


def _admissibility_status(
    boundary: str,
    fields: dict[str, bool],
    validation_gates: dict[str, str],
    source_text: str,
) -> str:
    if not source_text:
        return "weak_grounding"
    if boundary == "plant_facing_insufficient":
        return "plant_facing_incomplete"
    if boundary == "process_partial":
        return "process_partial"
    if boundary == "reactor_legibility":
        return "reactor_legible"
    if boundary == "cell_metric":
        validation_missing = any(
            validation_gates[gate] != "yes" for gate in ("isotope_15N", "blank_control", "nox_control")
        )
        matrix_incomplete = fields["faradaic_efficiency"] and not (
            fields["nh3_yield"] and fields["charge_or_runtime"] and fields["potential_or_voltage"]
        )
        if validation_missing or matrix_incomplete:
            return "metric_only_or_validation_incomplete"
        return "cell_metric_admissible"
    if boundary == "product_admissibility":
        return "product_admissible"
    return "insufficient_primary_support"


def _missing_boundary_fields(
    boundary: str,
    missing: dict[str, list[str]],
    fields: dict[str, bool],
    record: dict[str, Any],
) -> list[str]:
    if boundary == "unsupported_or_secondary":
        return missing.get("product_admissibility", [])

    selected: list[str] = []
    for candidate in ("product_admissibility", "cell_metric", "reactor_legibility", "process_partial"):
        if boundary_rank(candidate) <= boundary_rank(boundary):
            selected.extend(missing.get(candidate, []))
    if _plant_or_process_gesture(record) or _has_process_signal(fields):
        selected.extend(missing.get("process_partial", []))
    return _dedupe(selected)


def _required_controls(
    record: dict[str, Any],
    fields: dict[str, bool],
    validation_gates: dict[str, str],
) -> list[str]:
    controls: list[str] = []
    if _n2_claim(record) and validation_gates["isotope_15N"] != "yes":
        controls.append("15N2 isotope validation")
    if validation_gates["blank_control"] != "yes":
        controls.append("Ar/N2-free blank")
    if validation_gates["nox_control"] != "yes":
        controls.append("NOx/nitrate/nitrite screening")
    if validation_gates["contamination_control"] != "yes":
        controls.append("contamination-source accounting")
    if _hor_claim(record):
        controls.append("H2-off/HOR-off control")
    if _flow_claim(record):
        controls.append("gas/liquid product accounting and wetting/flooding diagnosis")
    if fields["faradaic_efficiency"] and not fields["nh3_yield"]:
        controls.append("NH3 yield paired with FE")
    return _dedupe(controls)


def _missing_contamination_controls(validation_gates: dict[str, str]) -> list[str]:
    controls: list[str] = []
    if validation_gates["nox_control"] != "yes":
        controls.append("NOx/nitrate/nitrite screening")
    if validation_gates["contamination_control"] != "yes":
        controls.append("contamination-source accounting")
    if validation_gates["blank_control"] != "yes":
        controls.append("Ar/N2-free blank")
    return controls


def _recommended_experiment(
    boundary: str,
    required_controls: list[str],
    missing_boundary_fields: list[str],
    risk_flags: list[str],
) -> list[str]:
    recommendations: list[str] = []
    if required_controls:
        recommendations.append("Run missing controls: " + "; ".join(required_controls))
    if missing_boundary_fields:
        recommendations.append("Report missing boundary fields: " + "; ".join(missing_boundary_fields[:8]))
    if "plant_facing_without_process_closure" in risk_flags:
        recommendations.append("Add process closure before making plant-facing claims.")
    if boundary in {"unsupported_or_secondary", "product_admissibility"} and not recommendations:
        recommendations.append("Collect primary source text with complete validation and metrics.")
    return recommendations


def _process_ready(fields: dict[str, bool]) -> bool:
    core = [
        "gas_liquid_product_split",
        "capture_route",
        "solvent_inventory",
        "hydrogen_source_boundary",
        "voltage_basis",
    ]
    return all(fields.get(name) for name in core)


def _reactor_ready(fields: dict[str, bool]) -> bool:
    if not fields["reactor_type"]:
        return False
    if not (fields["flow_rate"] or fields["GDE_or_SSC"] or fields["HOR_or_anode_reaction"]):
        return False
    if not fields["outlet_product_state"]:
        return False
    described = sum(
        bool(fields.get(name))
        for name in [
            "reactor_type",
            "flow_rate",
            "GDE_or_SSC",
            "HOR_or_anode_reaction",
            "runtime_or_stability",
            "outlet_product_state",
            "wetting_or_failure_disclosure",
        ]
    )
    return described >= 4


def _has_process_signal(fields: dict[str, bool]) -> bool:
    return any(fields.get(name) for name in BOUNDARY_FIELDS["process_partial"])


def _n2_claim(record: dict[str, Any]) -> bool:
    text = _normalized_text(record)
    family = str(record.get("reaction_family") or "").casefold()
    source = str(record.get("nitrogen_source") or "").casefold()
    return (
        family in {"enrr", "linrr"}
        or source in {"n2", "15n2"}
        or _contains_any(text, ["n2 reduction", "nitrogen reduction", "dinitrogen", "n2-to-nh3", "n2 to nh3"])
        or ("n2" in text and "nh3" in text)
    )


def _hor_claim(record: dict[str, Any]) -> bool:
    text = _normalized_text(record)
    return has_any_value(record, "HOR_or_anode_reaction") or _contains_any(
        text, [" hor", "hydrogen oxidation", "h2 oxidation"]
    )


def _flow_claim(record: dict[str, Any]) -> bool:
    text = _normalized_text(record)
    reactor = str(record.get("reactor_type") or "").casefold()
    return "flow" in reactor or _contains_any(text, ["flow cell", "flow reactor", "continuous flow", "gde", "gas diffusion"])


def _gas_phase_claim(record: dict[str, Any]) -> bool:
    text = _normalized_text(record)
    return _contains_any(text, ["gas-phase ammonia", "gas phase ammonia", "gas-phase nh3", "gas phase nh3"])


def _plant_or_process_gesture(record: dict[str, Any]) -> bool:
    text = _normalized_text(record)
    return _contains_any(
        text,
        [
            "plant",
            "industrial",
            "commercial",
            "process relevance",
            "scale-up",
            "scale up",
            "technoeconomic",
            "tea",
            "recycle",
            "auxiliary load",
            "balance of plant",
            "practical application",
        ],
    )


def _has_number(record: dict[str, Any], *keys: str) -> bool:
    return any(coerce_float(record.get(key)) is not None for key in keys)


def _text_has_fe(text: str) -> bool:
    return bool(re.search(r"\b(?:faradaic efficiency|fe)\b", text)) and (
        "%" in text or "percent" in text or bool(re.search(r"\bfe\s*\(?%?\)?", text))
    )


def _normalized_text(record: dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", _source_text(record).casefold()).strip()


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"true", "1", "yes", "y"}


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        text = str(item)
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(text)
    return deduped


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
        "provenance_confidence",
        "provenance_signals",
        "is_primary_admissible",
        "is_secondary_or_context",
        "is_reject_or_low_trust",
        "provenance_constrained",
        "text_class_provenance_conflict",
        "claim_type",
        "maximum_supported_boundary",
        "admissibility_status",
        SUPPORT_HINT_FIELD,
        "paired_body_required",
        "caption_context_only",
        "paired_caption_context",
        "missing_boundary_fields",
        "validation_gates",
        "boundary_fields_present",
        "boundary_fields_missing",
        "overclaim_risk_flags",
        "required_controls",
        "recommended_experiment",
        "reasoning",
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
