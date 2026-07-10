"""Evidence-bundle construction for eNH3-BoundaryLedger."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from enh3bench.boundary_schema import has_any_value
from enh3bench.document_provenance import infer_provenance_for_record
from enh3bench.ledger_router import load_jsonl


LEDGER_FILENAMES = (
    "performance_ledger.jsonl",
    "negative_evidence_ledger.jsonl",
    "validation_protocol_ledger.jsonl",
    "secondary_review_ledger.jsonl",
    "rejected_or_context.jsonl",
)

EXTRACTED_FIELD_NAMES = (
    "reaction_family",
    "nitrogen_source",
    "catalyst",
    "catalyst_class",
    "electrolyte",
    "reactor_type",
    "membrane",
    "potential_value",
    "potential_unit",
    "potential_reference",
    "voltage",
    "cell_voltage",
    "voltage_basis",
    "current_density_mA_cm2",
    "current_density",
    "faradaic_efficiency_percent",
    "FE_percent",
    "fe_percent",
    "nh3_yield_value",
    "NH3_yield",
    "nh3_yield",
    "nh3_yield_unit",
    "nh3_yield_normalized_value",
    "nh3_yield_normalized_unit",
    "energy_efficiency_percent",
    "EE_percent",
    "stability_hours",
    "runtime",
    "charge",
    "detection_method",
    "quantification_method",
    "ammonia_quantification",
    "isotope_validation",
    "isotope_15N",
    "blank_control",
    "contamination_control",
    "nox_screening",
    "nox_control",
    "reliability_label",
    "evidence_type",
    "flow_rate",
    "active_area",
    "electrode_area",
    "GDE_or_SSC",
    "HOR_or_anode_reaction",
    "anode_reaction",
    "outlet_product_state",
    "product_state",
    "wetting_or_failure_disclosure",
    "gas_liquid_product_split",
    "capture_route",
    "solvent_inventory",
    "electrolyte_replacement_or_recycle",
    "hydrogen_source_boundary",
    "hydrogen_source",
    "auxiliary_loads",
    "first_failure_signal",
)


def build_evidence_bundle(record: dict[str, Any]) -> dict[str, Any]:
    """Build one BoundaryLedger evidence bundle from a classified span record."""

    raw_record = dict(record)
    source_span_id = _first_text(record, "source_span_id", "span_id", "id")
    evidence_id = _first_text(record, "evidence_id") or _evidence_id(source_span_id)
    paper_id = _first_text(record, "paper_id")
    source_text = _source_text(record)
    bundle_id = _bundle_id(paper_id, evidence_id, source_span_id)
    provenance_info = _record_provenance_info(record)

    bundle: dict[str, Any] = {
        "bundle_id": bundle_id,
        "paper_id": paper_id,
        "document_id": _first_text(record, "document_id"),
        "doi": _first_text(record, "doi", "DOI"),
        "source_span_id": source_span_id,
        "evidence_id": evidence_id,
        "source_text": source_text,
        "text_class": _first_text(record, "text_class") or "unknown",
        "source_section": _first_text(record, "source_section") or "unknown",
        "recommended_ledger": _first_text(record, "recommended_ledger"),
        "allow_field_extraction": bool(record.get("allow_field_extraction", False)),
        "allow_gold": bool(record.get("allow_gold", False)),
        "provenance_type": provenance_info.get("provenance_type", "unknown"),
        "provenance_confidence": provenance_info.get("provenance_confidence", "low"),
        "provenance_signals": provenance_info.get("provenance_signals", []),
        "is_primary_admissible": bool(provenance_info.get("is_primary_admissible", False)),
        "is_secondary_or_context": bool(provenance_info.get("is_secondary_or_context", False)),
        "is_reject_or_low_trust": bool(provenance_info.get("is_reject_or_low_trust", False)),
        "extracted_fields": _extracted_fields(record),
        "provenance": _provenance(record, provenance_info),
        "grounding_status": _grounding_status(source_text),
        "raw_record": raw_record,
    }
    run_name = _first_text(record, "run_name")
    if run_name:
        bundle["run_name"] = run_name
        bundle["provenance"]["run_name"] = run_name
    support_hint_boundary = _first_text(record, "support_hint_boundary")
    if support_hint_boundary:
        bundle["support_hint_boundary"] = support_hint_boundary
    return bundle


def build_evidence_bundles(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build evidence bundles from many classified or ledger records."""

    return [build_evidence_bundle(record) for record in records]


def load_records_from_ledgers(run_name: str, base_dir: str | Path = "data/ledgers") -> list[dict[str, Any]]:
    """Load classified-span records for a run, falling back to routed ledgers."""

    base_path = Path(base_dir)
    run_dir = base_path / run_name
    classified_path = run_dir / "classified_spans.jsonl"
    records = load_jsonl(classified_path)
    if records:
        return _with_run_name(records, run_name)

    candidate_classified = Path("data") / "candidates" / f"classified_spans.{run_name}.jsonl"
    records = load_jsonl(candidate_classified)
    if records:
        return _with_run_name(records, run_name)

    ledger_records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for filename in LEDGER_FILENAMES:
        for record in load_jsonl(run_dir / filename):
            key = (
                str(record.get("paper_id") or ""),
                str(record.get("evidence_id") or ""),
                str(record.get("span_id") or record.get("source_span_id") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            ledger_records.append(record)
    return _with_run_name(ledger_records, run_name)


def export_evidence_bundles(
    bundles: list[dict[str, Any]],
    run_name: str,
    output_dir: str | Path = "data/boundary_ledger",
) -> dict[str, Any]:
    """Write evidence bundles as JSONL and CSV."""

    run_dir = Path(output_dir) / run_name
    jsonl_path = run_dir / "evidence_bundles.jsonl"
    csv_path = run_dir / "evidence_bundles.csv"
    _write_jsonl(bundles, jsonl_path)
    _write_csv(bundles, csv_path)
    return {
        "run_name": run_name,
        "count": len(bundles),
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
    }


def _with_run_name(records: list[dict[str, Any]], run_name: str) -> list[dict[str, Any]]:
    tagged: list[dict[str, Any]] = []
    for record in records:
        item = dict(record)
        item.setdefault("run_name", run_name)
        tagged.append(item)
    return tagged


def _source_text(record: dict[str, Any]) -> str:
    return _first_text(record, "source_text", "source_span", "text")


def _first_text(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _evidence_id(source_span_id: str) -> str:
    if source_span_id:
        return f"E_{source_span_id}"
    return "E_TODO"


def _bundle_id(paper_id: str, evidence_id: str, source_span_id: str) -> str:
    parts = [part for part in [paper_id, evidence_id, source_span_id] if part]
    if not parts:
        return "B_TODO"
    return "B_" + "_".join(parts)


def _extracted_fields(record: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key in EXTRACTED_FIELD_NAMES:
        if key in record and has_any_value(record, key):
            fields[key] = record[key]
    return fields


def _record_provenance_info(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("provenance_type"):
        return {
            "provenance_id": record.get("provenance_id"),
            "provenance_type": record.get("provenance_type"),
            "provenance_confidence": record.get("provenance_confidence") or "low",
            "provenance_signals": record.get("provenance_signals") or [],
            "is_primary_admissible": bool(record.get("is_primary_admissible", False)),
            "is_secondary_or_context": bool(record.get("is_secondary_or_context", False)),
            "is_reject_or_low_trust": bool(record.get("is_reject_or_low_trust", False)),
        }
    return infer_provenance_for_record(record)


def _provenance(record: dict[str, Any], provenance_info: dict[str, Any]) -> dict[str, Any]:
    provenance = {
        "source_record_keys": sorted(str(key) for key in record.keys()),
        "source_span_id": _first_text(record, "source_span_id", "span_id", "id"),
        "evidence_id": _first_text(record, "evidence_id"),
        "classification_confidence": _first_text(record, "confidence"),
        "classification_reasons": record.get("reasons") or [],
        "provenance_id": provenance_info.get("provenance_id") or "",
        "provenance_type": provenance_info.get("provenance_type") or "unknown",
        "provenance_confidence": provenance_info.get("provenance_confidence") or "low",
        "provenance_signals": provenance_info.get("provenance_signals") or [],
    }
    source_file = _first_text(record, "source_file")
    if source_file:
        provenance["source_file"] = source_file
    return provenance


def _grounding_status(source_text: str) -> str:
    text = str(source_text or "").strip()
    if not text:
        return "missing_source_text"
    if len(text) < 30:
        return "weak_source_text"
    return "explicit_source_text"


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
        "bundle_id",
        "run_name",
        "paper_id",
        "document_id",
        "doi",
        "source_span_id",
        "evidence_id",
        "source_text",
        "text_class",
        "source_section",
        "recommended_ledger",
        "allow_field_extraction",
        "allow_gold",
        "provenance_type",
        "provenance_confidence",
        "provenance_signals",
        "is_primary_admissible",
        "is_secondary_or_context",
        "is_reject_or_low_trust",
        "support_hint_boundary",
        "extracted_fields",
        "provenance",
        "grounding_status",
        "raw_record",
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
