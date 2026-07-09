"""Hidden-tax detection for eNH3-BoundaryLedger records."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from enh3bench.boundary_schema import HIDDEN_TAX_TYPES, coerce_float, has_any_value
from enh3bench.document_provenance import infer_provenance_for_record
from enh3bench.provenance_rules import is_reject_or_low_trust, normalize_provenance_type


def detect_hidden_taxes(record: dict[str, Any]) -> dict[str, Any]:
    """Detect process and measurement burdens hidden behind a claim."""

    merged = _merged_record(record)
    _ensure_provenance_fields(merged)
    text = _normalized_text(merged)
    provenance_type = str(merged.get("provenance_type") or "unknown")
    detected: list[str] = []
    hidden_assumptions: list[str] = []
    missing_measurements: list[str] = []
    required_controls: list[str] = []
    reasoning: list[str] = []

    if _contains_any(text, ["electrolyte", "solvent", "donor", "additive", "water", "li salt", "lithium salt", "thf"]):
        detected.append("solvent_management_tax")
        hidden_assumptions.append("solvent, electrolyte, donor, and additive inventories remain stable or are replenished without cost.")
        missing_measurements.extend(["solvent inventory", "electrolyte replacement or recycle", "donor/additive consumption"])
        required_controls.append("track electrolyte composition and inventory before and after operation")
        reasoning.append("solvent/electrolyte terms imply an unclosed material-management burden.")

    if _contains_any(text, ["sei", "interphase", "passivation", "resistance", "impedance", "renewal"]):
        detected.append("resistance_or_renewal_tax")
        hidden_assumptions.append("interphase, impedance, and renewal burdens do not degrade sustained operation.")
        missing_measurements.extend(["impedance over runtime", "renewal schedule", "passivation or failure onset"])
        required_controls.append("report impedance or renewal behavior over the same runtime as performance")
        reasoning.append("interphase/resistance language implies a renewal or durability burden.")

    if _contains_any(text, ["flow", "gde", "ssc", "gas diffusion", "outlet", "flooding", "wetting", "capture"]):
        detected.append("wetting_outlet_capture_tax")
        hidden_assumptions.append("reactor outlet, wetting, flooding, and capture losses are negligible or disclosed.")
        missing_measurements.extend(["outlet product state", "gas/liquid product split", "wetting or flooding diagnosis", "capture efficiency"])
        required_controls.append("measure gas/liquid product accounting and wetting/flooding diagnostics")
        reasoning.append("flow/GDE/outlet terms imply capture and wetting burdens.")

    if _contains_any(text, [" hor", "hydrogen oxidation", " h2 ", "h2,", "h2.", "h2 feed", "proton economy"]):
        detected.append("hydrogen_logistics_tax")
        hidden_assumptions.append("hydrogen source, HOR coupling, and proton economy are already inside the claimed boundary.")
        missing_measurements.extend(["hydrogen source boundary", "H2 consumption", "HOR-off control"])
        required_controls.append("run H2-off/HOR-off controls and report hydrogen source logistics")
        reasoning.append("HOR/H2 language implies an unclosed hydrogen logistics boundary.")

    if _contains_any(
        text,
        ["contamination", "nox", "nitrate", "nitrite", "background ammonia", "false positive", "impurity"],
    ):
        detected.append("contamination_tax")
        hidden_assumptions.append("nitrogen-containing impurities and background ammonia do not explain the NH3 signal.")
        missing_measurements.extend(["NOx/nitrate/nitrite screen", "background ammonia", "blank controls"])
        required_controls.append("screen NOx/nitrate/nitrite and background ammonia with blanks")
        reasoning.append("contamination terms directly create a source-attribution burden.")

    if _has_fe(merged, text) and _measurement_matrix_missing(merged, text):
        detected.append("measurement_matrix_tax")
        hidden_assumptions.append("Faradaic efficiency alone is enough to compare performance across systems.")
        missing_measurements.extend(_missing_measurement_matrix(merged, text))
        required_controls.append("report FE with NH3 yield, voltage, current density, runtime, energy efficiency, and product state")
        reasoning.append("FE appears without the full metric matrix needed for boundary comparison.")

    if provenance_type in {"reference", "bibliography", "review_table", "figure_caption", "scheme_caption", "table"}:
        hidden_assumptions.append("secondary_or_context_text_cannot_establish_primary_boundary")
        reasoning.append(f"{provenance_type} provenance cannot establish a primary boundary by itself.")
        if provenance_type in {"figure_caption", "scheme_caption", "table", "review_table"}:
            missing_measurements.append("primary_body_text_pairing_required")
            required_controls.append("pair context/table/caption evidence with primary body text")
    if is_reject_or_low_trust(provenance_type) and _has_fe(merged, text):
        detected.append("measurement_matrix_tax")
        reasoning.append("low-trust provenance makes reported metrics non-admissible without primary body text.")
    if is_reject_or_low_trust(provenance_type) and _contains_any(
        text,
        ["contamination", "nox", "nitrate", "nitrite", "background ammonia", "false positive", "impurity"],
    ):
        detected.append("contamination_tax")
        reasoning.append("low-trust provenance cannot resolve contamination attribution.")

    detected = _dedupe([tax for tax in detected if tax in HIDDEN_TAX_TYPES])
    return {
        "tax_record_id": _tax_record_id(merged),
        "paper_id": str(merged.get("paper_id") or ""),
        "source_span_id": str(merged.get("source_span_id") or merged.get("span_id") or ""),
        "evidence_id": str(merged.get("evidence_id") or ""),
        "text_class": str(merged.get("text_class") or "unknown"),
        "provenance_type": provenance_type,
        "provenance_confidence": str(merged.get("provenance_confidence") or "low"),
        "detected_taxes": detected,
        "main_gain": _main_gain(merged, text),
        "hidden_assumptions": _dedupe(hidden_assumptions),
        "missing_measurements": _dedupe(missing_measurements),
        "required_controls": _dedupe(required_controls),
        "severity": _severity(detected, merged, text),
        "reasoning": _dedupe(reasoning),
        "source_text": _source_text(merged),
    }


def detect_hidden_taxes_many(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect hidden taxes for many records."""

    return [detect_hidden_taxes(record) for record in records]


def export_hidden_tax_ledger(
    records: list[dict[str, Any]],
    run_name: str,
    output_dir: str | Path = "data/boundary_ledger",
) -> dict[str, Any]:
    """Write hidden-tax records as JSONL and CSV."""

    detected = detect_hidden_taxes_many(records)
    run_dir = Path(output_dir) / run_name
    jsonl_path = run_dir / "hidden_tax_ledger.jsonl"
    csv_path = run_dir / "hidden_tax_ledger.csv"
    _write_jsonl(detected, jsonl_path)
    _write_csv(detected, csv_path)
    return {
        "run_name": run_name,
        "count": len(detected),
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
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


def _tax_record_id(record: dict[str, Any]) -> str:
    for key in ("evidence_id", "source_span_id", "span_id"):
        value = str(record.get(key) or "").strip()
        if value:
            return f"HT_{value}"
    return "HT_TODO"


def _ensure_provenance_fields(record: dict[str, Any]) -> None:
    if record.get("provenance_type"):
        record["provenance_type"] = normalize_provenance_type(str(record.get("provenance_type") or "unknown"))
        record.setdefault("provenance_confidence", "low")
        return
    provenance = infer_provenance_for_record(record)
    record["provenance_type"] = provenance.get("provenance_type") or "unknown"
    record["provenance_confidence"] = provenance.get("provenance_confidence") or "low"
    record["provenance_signals"] = provenance.get("provenance_signals") or []
    record["is_primary_admissible"] = provenance.get("is_primary_admissible", False)
    record["is_secondary_or_context"] = provenance.get("is_secondary_or_context", False)
    record["is_reject_or_low_trust"] = provenance.get("is_reject_or_low_trust", False)


def _source_text(record: dict[str, Any]) -> str:
    for key in ("source_text", "source_span", "text"):
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _normalized_text(record: dict[str, Any]) -> str:
    return re.sub(r"\s+", " ", _source_text(record).casefold()).strip()


def _has_fe(record: dict[str, Any], text: str) -> bool:
    if any(coerce_float(record.get(key)) is not None for key in ("faradaic_efficiency_percent", "FE_percent", "fe_percent")):
        return True
    boundary_present = record.get("boundary_fields_present")
    if isinstance(boundary_present, dict) and "faradaic_efficiency" in boundary_present.get("cell_metric", []):
        return True
    return bool(re.search(r"\b(?:faradaic efficiency|fe)\b", text)) and ("%" in text or "percent" in text)


def _measurement_matrix_missing(record: dict[str, Any], text: str) -> bool:
    return bool(_missing_measurement_matrix(record, text))


def _missing_measurement_matrix(record: dict[str, Any], text: str) -> list[str]:
    missing: list[str] = []
    if not _has_yield(record, text):
        missing.append("NH3 yield")
    if not _has_energy_efficiency(record, text):
        missing.append("energy efficiency")
    if not _has_voltage(record, text):
        missing.append("voltage or potential")
    if not _has_current_density(record, text):
        missing.append("current density")
    if not _has_runtime(record, text):
        missing.append("runtime or stability")
    if not _has_product_state(record, text):
        missing.append("product state")
    return missing


def _has_yield(record: dict[str, Any], text: str) -> bool:
    return any(coerce_float(record.get(key)) is not None for key in ("nh3_yield_value", "NH3_yield", "nh3_yield")) or _contains_any(
        text, ["nh3 yield", "ammonia yield", "yield rate", "production rate"]
    )


def _has_energy_efficiency(record: dict[str, Any], text: str) -> bool:
    return any(coerce_float(record.get(key)) is not None for key in ("energy_efficiency_percent", "EE_percent")) or _contains_any(
        text, ["energy efficiency", " ee "]
    )


def _has_voltage(record: dict[str, Any], text: str) -> bool:
    return any(coerce_float(record.get(key)) is not None for key in ("potential_value", "voltage", "cell_voltage")) or _contains_any(
        text, ["potential", "voltage", " v vs", "vvs", "two-electrode"]
    )


def _has_current_density(record: dict[str, Any], text: str) -> bool:
    return any(coerce_float(record.get(key)) is not None for key in ("current_density_mA_cm2", "current_density")) or _contains_any(
        text, ["current density", " ma cm", "ma/cm"]
    )


def _has_runtime(record: dict[str, Any], text: str) -> bool:
    return any(coerce_float(record.get(key)) is not None for key in ("runtime", "runtime_hours", "stability_hours")) or _contains_any(
        text, ["runtime", "stability", "hours", "electrolysis"]
    )


def _has_product_state(record: dict[str, Any], text: str) -> bool:
    return has_any_value(record, "outlet_product_state", "product_state") or _contains_any(
        text,
        ["gas-phase ammonia", "gas phase ammonia", "aqueous ammonia", "aqueous nh3", "nh4+", "ammonium", "acid trap", "outlet"],
    )


def _main_gain(record: dict[str, Any], text: str) -> str:
    if _has_fe(record, text):
        return "reported Faradaic efficiency or selectivity gain"
    if _has_yield(record, text):
        return "reported ammonia yield or production gain"
    if _contains_any(text, ["flow", "reactor", "gde", "gas diffusion"]):
        return "reported reactor or transport gain"
    if _contains_any(text, ["contamination", "nox", "background ammonia"]):
        return "reported source-attribution or contamination finding"
    return "unspecified claim gain"


def _severity(detected_taxes: list[str], record: dict[str, Any], text: str) -> str:
    if not detected_taxes:
        return "low"
    fe_value = _first_float(record, "faradaic_efficiency_percent", "FE_percent", "fe_percent")
    if "measurement_matrix_tax" in detected_taxes and fe_value is not None and fe_value >= 50.0:
        return "high"
    if "contamination_tax" in detected_taxes and "measurement_matrix_tax" in detected_taxes:
        return "high"
    if len(detected_taxes) >= 3:
        return "high"
    if len(detected_taxes) >= 2 or _contains_any(text, ["false positive", "reassigned", "not from n2"]):
        return "medium"
    return "medium"


def _first_float(record: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = coerce_float(record.get(key))
        if value is not None:
            return value
    return None


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


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
        "tax_record_id",
        "paper_id",
        "source_span_id",
        "evidence_id",
        "text_class",
        "provenance_type",
        "provenance_confidence",
        "detected_taxes",
        "main_gain",
        "hidden_assumptions",
        "missing_measurements",
        "required_controls",
        "severity",
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
