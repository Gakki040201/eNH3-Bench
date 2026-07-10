"""Import and validate experiment results for closed-loop route evaluation."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from enh3bench.experiment_schema import RESULT_STATUS_LABELS, empty_experiment_result_template
from enh3bench.ledger_router import load_jsonl


RESULT_FIELDS = (
    "experiment_id",
    "route_id",
    "run_name",
    "date",
    "operator",
    "condition_id",
    "experimental_matrix_value",
    "FE",
    "NH3_yield",
    "current_density",
    "full_cell_voltage",
    "anode_potential",
    "cathode_potential",
    "runtime_hours",
    "water_content",
    "EIS_summary",
    "gas_phase_NH3",
    "liquid_NH4",
    "nitrate",
    "nitrite",
    "NOx",
    "H2_observation",
    "product_state_split",
    "electrolyte_color",
    "photo_record",
    "failure_mode",
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
    "full_cell_voltage": "full_cell_voltage",
    "anode_potential": "anode_potential",
    "cathode_potential": "cathode_potential",
    "runtime": "runtime_hours",
    "EIS": "EIS_summary",
    "CV": "notes",
    "water_content": "water_content",
    "gas_phase_NH3": "gas_phase_NH3",
    "liquid_NH4": "liquid_NH4",
    "nitrate": "nitrate",
    "nitrite": "nitrite",
    "NOx": "NOx",
    "H2": "H2_observation",
    "product_state_split": "product_state_split",
    "electrolyte_color": "electrolyte_color",
    "photo_before_after": "photo_record",
    "failure_mode": "failure_mode",
}


def load_experiment_routes(run_name: str, base_dir: str | Path = "data/experiment_routes") -> list[dict[str, Any]]:
    return load_jsonl(Path(base_dir) / run_name / "ranked_experiment_routes.jsonl")


def export_experiment_result_template(
    routes: list[dict[str, Any]],
    run_name: str,
    output_dir: str | Path = "data/experiment_results",
) -> dict[str, Any]:
    """Export editable result templates for planned routes."""

    run_dir = Path(output_dir) / run_name
    rows = [empty_experiment_result_template(route) for route in routes]
    csv_path = run_dir / "experiment_results_template.csv"
    jsonl_path = run_dir / "experiment_results_template.jsonl"
    _write_csv(rows, csv_path)
    _write_jsonl(rows, jsonl_path)
    return {"run_name": run_name, "count": len(rows), "csv": str(csv_path), "jsonl": str(jsonl_path)}


def import_experiment_results(
    path: str | Path,
    run_name: str,
    output_dir: str | Path = "data/experiment_results",
) -> dict[str, Any]:
    """Import CSV/JSONL experiment results and write validation outputs."""

    input_path = Path(path)
    rows = _read_records(input_path)
    imported: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):
        normalized = {field: str(row.get(field) or "") for field in RESULT_FIELDS}
        normalized["run_name"] = normalized.get("run_name") or run_name
        valid, row_errors = validate_experiment_result(normalized)
        if not valid:
            errors.append(
                {
                    "row_number": index,
                    "route_id": normalized.get("route_id") or "",
                    "experiment_id": normalized.get("experiment_id") or "",
                    "errors": "; ".join(row_errors),
                }
            )
            if _list_values(normalized.get("controls_failed")) and normalized.get("success_status") == "success":
                normalized["success_status"] = "invalid"
                normalized["invalid_reason"] = "mandatory controls failed"
        normalized["validation_errors"] = row_errors
        imported.append(normalized)

    run_dir = Path(output_dir) / run_name
    imported_csv = run_dir / "experiment_results_imported.csv"
    imported_jsonl = run_dir / "experiment_results_imported.jsonl"
    errors_csv = run_dir / "experiment_result_errors.csv"
    _write_csv(imported, imported_csv)
    _write_jsonl(imported, imported_jsonl)
    _write_csv(errors, errors_csv)
    return {
        "run_name": run_name,
        "rows_read": len(rows),
        "valid_results": len(rows) - len(errors),
        "invalid_results": len(errors),
        "imported_csv": str(imported_csv),
        "imported_jsonl": str(imported_jsonl),
        "errors_csv": str(errors_csv),
    }


def validate_experiment_result(record: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate one experiment result row without computing scientific conclusions."""

    errors: list[str] = []
    for field in ("experiment_id", "route_id", "run_name", "success_status"):
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


def _fieldnames(records: list[dict[str, Any]]) -> list[str]:
    names = set(RESULT_FIELDS)
    for record in records:
        names.update(record)
    ordered = [field for field in RESULT_FIELDS if field in names]
    ordered.extend(sorted(name for name in names if name not in set(ordered)))
    return ordered
