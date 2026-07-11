"""Import and validate experiment results for closed-loop route evaluation."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from enh3bench.experiment_schema import (
    EXECUTION_UNIT,
    EXPERIMENT_SCHEMA_VERSION,
    RESULT_STATUS_LABELS,
    expand_routes_to_result_rows,
)
from enh3bench.ledger_router import load_jsonl


RESULT_FIELDS = (
    "schema_version",
    "execution_unit",
    "execution_id",
    "experiment_id",
    "route_id",
    "run_name",
    "date",
    "operator",
    "condition_id",
    "condition_label",
    "condition_values_json",
    "replicate_id",
    "replicate_index",
    "independent_replicate",
    "replicate_type",
    "independent_assembly_required",
    "assembly_id",
    "cell_build_id",
    "electrolyte_batch_id",
    "electrode_batch_id",
    "gas_batch_id",
    "experiment_start_utc",
    "experiment_end_utc",
    "timepoint_id",
    "technical_repeat_id",
    "experimental_matrix_value",
    "FE",
    "NH3_yield",
    "current_density",
    "OCV",
    "pump_speed",
    "full_cell_voltage",
    "anode_potential",
    "cathode_potential",
    "runtime_hours",
    "water_content",
    "water_content_before",
    "water_content_mid",
    "water_content_after",
    "EIS_summary",
    "electrolyte_resistance_before",
    "electrolyte_resistance_after",
    "gas_phase_NH3",
    "liquid_NH4",
    "IC_NH4",
    "HCl_trap_NH4",
    "SSC_soak_solution_NH4",
    "nitrate",
    "nitrite",
    "NOx",
    "gas_phase_NOx",
    "feed_gas_impurity",
    "H2_observation",
    "product_state_split",
    "electrolyte_color",
    "photo_record",
    "SSC_photo_before",
    "SSC_photo_after",
    "PtAuSSC_photo_before",
    "PtAuSSC_photo_after",
    "gas_line_status",
    "liquid_line_status",
    "leak_status",
    "back_suction_status",
    "pump_status",
    "failure_mode",
    "SOP_deviation",
    "operator_failure_note",
    "controls_completed",
    "controls_failed",
    "required_controls",
    "required_measurements",
    "success_status",
    "invalid_reason",
    "notes",
)

MEASUREMENT_TO_RESULT_FIELD = {
    "FE": "FE",
    "NH3_yield": "NH3_yield",
    "current_density": "current_density",
    "OCV": "OCV",
    "pump_speed": "pump_speed",
    "full_cell_voltage": "full_cell_voltage",
    "anode_potential": "anode_potential",
    "cathode_potential": "cathode_potential",
    "runtime": "runtime_hours",
    "EIS": "EIS_summary",
    "CV": "notes",
    "water_content": "water_content",
    "water_content_before": "water_content_before",
    "water_content_mid": "water_content_mid",
    "water_content_after": "water_content_after",
    "electrolyte_resistance_before": "electrolyte_resistance_before",
    "electrolyte_resistance_after": "electrolyte_resistance_after",
    "gas_phase_NH3": "gas_phase_NH3",
    "liquid_NH4": "liquid_NH4",
    "IC_NH4": "IC_NH4",
    "HCl_trap_NH4": "HCl_trap_NH4",
    "SSC_soak_solution_NH4": "SSC_soak_solution_NH4",
    "nitrate": "nitrate",
    "nitrite": "nitrite",
    "NOx": "NOx",
    "gas_phase_NOx": "gas_phase_NOx",
    "feed_gas_impurity": "feed_gas_impurity",
    "H2": "H2_observation",
    "H2_observation": "H2_observation",
    "product_state_split": "product_state_split",
    "electrolyte_color": "electrolyte_color",
    "photo_before_after": "photo_record",
    "SSC_photo_before": "SSC_photo_before",
    "SSC_photo_after": "SSC_photo_after",
    "PtAuSSC_photo_before": "PtAuSSC_photo_before",
    "PtAuSSC_photo_after": "PtAuSSC_photo_after",
    "gas_line_status": "gas_line_status",
    "liquid_line_status": "liquid_line_status",
    "leak_status": "leak_status",
    "back_suction_status": "back_suction_status",
    "pump_status": "pump_status",
    "failure_mode": "failure_mode",
    "operator_failure_note": "operator_failure_note",
}


def load_experiment_routes(run_name: str, base_dir: str | Path = "data/experiment_routes") -> list[dict[str, Any]]:
    return load_jsonl(Path(base_dir) / run_name / "ranked_experiment_routes.jsonl")


def export_experiment_result_template(
    routes: list[dict[str, Any]],
    run_name: str,
    output_dir: str | Path = "data/experiment_results",
    baseline_replicates: int = 3,
    default_replicates: int = 1,
    expand_matrix: bool = True,
) -> dict[str, Any]:
    """Export editable result templates for planned routes."""

    run_dir = Path(output_dir) / run_name
    rows = expand_routes_to_result_rows(
        routes,
        baseline_replicates=baseline_replicates,
        default_replicates=default_replicates,
        expand_matrix=expand_matrix,
    )
    csv_path = run_dir / "experiment_results_template.csv"
    jsonl_path = run_dir / "experiment_results_template.jsonl"
    manifest_path = run_dir / "experiment_execution_manifest.json"
    summary_path = run_dir / "route_execution_summary.csv"
    _write_csv(rows, csv_path)
    _write_jsonl(rows, jsonl_path)
    manifest = {
        "schema_version": EXPERIMENT_SCHEMA_VERSION,
        "execution_unit": EXECUTION_UNIT,
        "run_name": run_name,
        "expand_matrix": expand_matrix,
        "baseline_replicates": baseline_replicates,
        "default_replicates": default_replicates,
        "execution_count": len(rows),
        "executions": [
            {
                key: row.get(key)
                for key in (
                    "execution_id",
                    "route_id",
                    "condition_id",
                    "condition_label",
                    "replicate_id",
                    "replicate_index",
                    "independent_replicate",
                )
            }
            for row in rows
        ],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    summary_rows = _route_execution_summary(routes, rows)
    _write_mapping_csv(summary_rows, summary_path)
    return {
        "run_name": run_name,
        "count": len(rows),
        "csv": str(csv_path),
        "jsonl": str(jsonl_path),
        "manifest": str(manifest_path),
        "summary_csv": str(summary_path),
    }


def import_experiment_results(
    path: str | Path,
    run_name: str,
    output_dir: str | Path = "data/experiment_results",
) -> dict[str, Any]:
    """Import CSV/JSONL experiment results and write validation outputs."""

    input_path = Path(path)
    rows = _read_records(input_path)
    imported: list[dict[str, Any]] = []
    row_errors: list[list[str]] = []
    row_warnings: list[list[str]] = []
    for index, row in enumerate(rows, start=2):
        migrated, migration_warnings = _migrate_legacy_result_row(row, index)
        normalized = {field: str(migrated.get(field) or "") for field in RESULT_FIELDS}
        normalized["run_name"] = normalized.get("run_name") or run_name
        _, validation_errors = validate_experiment_result(normalized)
        row_errors.append(validation_errors)
        row_warnings.append(migration_warnings)
        imported.append(normalized)

    _validate_result_identities(imported, row_errors)
    _validate_independent_assemblies(imported, row_errors, row_warnings)

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for offset, normalized in enumerate(imported):
        validation_errors = row_errors[offset]
        validation_warnings = row_warnings[offset]
        normalized["validation_errors"] = validation_errors
        normalized["validation_warnings"] = validation_warnings
        if validation_errors:
            errors.append(_validation_issue_row(offset + 2, normalized, validation_errors, "errors"))
        if validation_warnings:
            warnings.append(_validation_issue_row(offset + 2, normalized, validation_warnings, "warnings"))

    run_dir = Path(output_dir) / run_name
    imported_csv = run_dir / "experiment_results_imported.csv"
    imported_jsonl = run_dir / "experiment_results_imported.jsonl"
    errors_csv = run_dir / "experiment_result_errors.csv"
    warnings_csv = run_dir / "experiment_result_warnings.csv"
    _write_csv(imported, imported_csv)
    _write_jsonl(imported, imported_jsonl)
    _write_csv(errors, errors_csv)
    _write_csv(warnings, warnings_csv)
    return {
        "run_name": run_name,
        "rows_read": len(rows),
        "valid_results": len(rows) - len(errors),
        "invalid_results": len(errors),
        "warning_results": len(warnings),
        "imported_csv": str(imported_csv),
        "imported_jsonl": str(imported_jsonl),
        "errors_csv": str(errors_csv),
        "warnings_csv": str(warnings_csv),
    }


def validate_experiment_result(record: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate one experiment result row without computing scientific conclusions."""

    errors: list[str] = []
    for field in ("experiment_id", "execution_id", "route_id", "condition_id", "replicate_id", "run_name", "success_status"):
        if not str(record.get(field) or "").strip():
            errors.append(f"missing {field}")
    status = str(record.get("success_status") or "").strip()
    if status and status not in RESULT_STATUS_LABELS:
        errors.append(f"invalid success_status: {status}")
    controls_failed = _list_values(record.get("controls_failed"))
    if status == "success" and controls_failed:
        errors.append("failed mandatory controls cannot be marked success")
    required_measurements = _list_values(record.get("required_measurements"))
    if status in {"success", "partial"}:
        for measurement in required_measurements:
            result_field = MEASUREMENT_TO_RESULT_FIELD.get(measurement)
            if result_field and not str(record.get(result_field) or "").strip():
                errors.append(f"missing required measurement: {measurement}")
    if status == "invalid" and not str(record.get("invalid_reason") or "").strip():
        errors.append("invalid results require invalid_reason")
    return not errors, errors


def _migrate_legacy_result_row(row: dict[str, Any], row_number: int) -> tuple[dict[str, Any], list[str]]:
    migrated = dict(row)
    warnings: list[str] = []
    route_id = str(migrated.get("route_id") or "TODO")
    if not str(migrated.get("condition_id") or "").strip():
        migrated["condition_id"] = "legacy"
        warnings.append("legacy template missing condition_id; migrated to legacy")
    if not str(migrated.get("replicate_id") or "").strip():
        migrated["replicate_id"] = "rep_01"
        migrated["replicate_index"] = "1"
        warnings.append("legacy template missing replicate identity; migrated to rep_01")
    if not str(migrated.get("execution_id") or "").strip():
        migrated["execution_id"] = str(migrated.get("experiment_id") or f"EXEC_{route_id}_legacy_rep_01_row_{row_number}")
        warnings.append("legacy template missing execution_id; derived during migration")
    if "independent_replicate" not in migrated or not str(migrated.get("independent_replicate") or "").strip():
        migrated["independent_replicate"] = "false"
        warnings.append("legacy template did not establish an independent replicate")
    migrated.setdefault("condition_label", str(migrated.get("condition_id") or "legacy"))
    migrated.setdefault("condition_values_json", "{}")
    migrated.setdefault("schema_version", EXPERIMENT_SCHEMA_VERSION)
    migrated.setdefault("execution_unit", EXECUTION_UNIT)
    return migrated, warnings


def _validate_result_identities(records: list[dict[str, Any]], errors: list[list[str]]) -> None:
    execution_ids: dict[str, int] = {}
    replicate_keys: dict[tuple[str, str, str], int] = {}
    for index, record in enumerate(records):
        execution_id = str(record.get("execution_id") or "").strip()
        if execution_id in execution_ids:
            _append_unique(errors[index], f"duplicate execution_id: {execution_id}")
        else:
            execution_ids[execution_id] = index
        key = (
            str(record.get("route_id") or "").strip(),
            str(record.get("condition_id") or "").strip(),
            str(record.get("replicate_id") or "").strip(),
        )
        if key in replicate_keys:
            _append_unique(errors[index], f"duplicate route/condition/replicate identity: {'/'.join(key)}")
        else:
            replicate_keys[key] = index


def _validate_independent_assemblies(
    records: list[dict[str, Any]], errors: list[list[str]], warnings: list[list[str]]
) -> None:
    seen: dict[tuple[str, str, str, str], int] = {}
    for index, record in enumerate(records):
        if not _truthy(record.get("independent_assembly_required")):
            continue
        for field in ("assembly_id", "cell_build_id"):
            value = str(record.get(field) or "").strip()
            if not value:
                _append_unique(warnings[index], f"{field} is required to verify independent baseline assembly")
                continue
            key = (str(record.get("route_id") or ""), str(record.get("condition_id") or ""), field, value)
            if key in seen:
                _append_unique(errors[index], f"independent baseline replicates reuse {field}: {value}")
            else:
                seen[key] = index


def _validation_issue_row(row_number: int, record: dict[str, Any], messages: list[str], field: str) -> dict[str, Any]:
    return {
        "row_number": row_number,
        "route_id": record.get("route_id") or "",
        "execution_id": record.get("execution_id") or "",
        "experiment_id": record.get("experiment_id") or "",
        field: "; ".join(messages),
    }


def _route_execution_summary(routes: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    route_by_id = {str(route.get("route_id") or ""): route for route in routes}
    route_ids = list(dict.fromkeys(str(row.get("route_id") or "") for row in rows))
    return [
        {
            "route_id": route_id,
            "route_type": str(route_by_id.get(route_id, {}).get("route_type") or ""),
            "condition_count": len({str(row.get("condition_id") or "") for row in rows if row.get("route_id") == route_id}),
            "execution_count": sum(1 for row in rows if row.get("route_id") == route_id),
            "minimum_valid_replicates": route_by_id.get(route_id, {}).get("minimum_valid_replicates") or 1,
            "independent_assembly_required": bool(route_by_id.get(route_id, {}).get("independent_assembly_required")),
        }
        for route_id in route_ids
    ]


def _read_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return load_jsonl(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _list_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text or text.casefold() in {"none", "null", "nan", "n/a", "na", "[]"}:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return _list_values(parsed)
    return [part.strip() for part in text.replace("|", ",").replace(";", ",").split(",") if part.strip()]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"true", "1", "yes", "y"}


def _append_unique(values: list[str], message: str) -> None:
    if message not in values:
        values.append(message)


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
        writer.writerows(records)


def _write_mapping_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(dict.fromkeys(key for record in records for key in record))
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            writer.writerows(records)


def _fieldnames(records: list[dict[str, Any]]) -> list[str]:
    names = set(RESULT_FIELDS)
    for record in records:
        names.update(record)
    ordered = [field for field in RESULT_FIELDS if field in names]
    ordered.extend(sorted(name for name in names if name not in set(ordered)))
    return ordered
