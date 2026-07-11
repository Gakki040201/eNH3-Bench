"""Build eNH3-BoundaryBench tasks from reviewed human audit records."""

from __future__ import annotations

from collections import Counter
import csv
import json
from pathlib import Path
from typing import Any

from enh3bench.audit_schema import is_reviewed_record, validate_human_label_record
from enh3bench.benchmark_schema import (
    BENCHMARK_TASKS,
    HIDDEN_TAX_LABELS,
    REQUIRED_CONTROL_LABELS,
    VALIDATION_GATE_FIELDS,
    VALIDATION_GATE_LABELS,
    benchmark_record_id,
    normalize_label,
    normalize_multi_label,
    task_output_fields,
    validate_task_record,
)
from enh3bench.ledger_router import load_jsonl


PRIORITY_EXPERIMENT_DECISIONS = {"priority_experiment", "control_required", "negative_warning"}


def load_human_gold_records(run_name: str, base_dirs: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Load explicit human gold records, falling back to reviewed audit rows."""

    base_dirs = base_dirs or {}
    gold_dir = Path(base_dirs.get("gold", Path("data") / "gold"))
    human_audit_dir = Path(base_dirs.get("human_audit", Path("data") / "human_audit"))
    allow_reviewed_fallback = bool(base_dirs.get("allow_reviewed_fallback", True))

    gold_records = _valid_reviewed(load_jsonl(gold_dir / run_name / "human_gold_claim_rights.jsonl"))
    if gold_records:
        return gold_records
    if not allow_reviewed_fallback:
        return []
    return _valid_reviewed(load_jsonl(human_audit_dir / run_name / "reviewed_audit_records.jsonl"))


def build_source_span_task(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build source-span classification rows."""

    return [
        _task_record(record, "source_span_classification", {"gold_text_class": str(record.get("human_text_class") or "unknown")})
        for record in records
    ]


def build_validation_gate_task(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build validation-gate extraction rows."""

    rows: list[dict[str, Any]] = []
    for record in records:
        labels = {
            "rule_validation_isotope_15N": _rule_gate(record, "isotope_15N"),
            "rule_validation_blank_control": _rule_gate(record, "blank_control"),
            "rule_validation_NOx_control": _rule_gate(record, "NOx_control"),
            "rule_validation_contamination_control": _rule_gate(record, "contamination_control"),
            "rule_validation_quantification_method": _rule_gate(record, "quantification_method"),
            "gold_isotope_15N": _human_gate(record, "human_validation_isotope_15N"),
            "gold_blank_control": _human_gate(record, "human_validation_blank_control"),
            "gold_NOx_control": _human_gate(record, "human_validation_NOx_control"),
            "gold_contamination_control": _human_gate(record, "human_validation_contamination_control"),
            "gold_quantification_method": _human_gate(record, "human_validation_quantification_method"),
        }
        rows.append(_task_record(record, "validation_gate_extraction", labels))
    return rows


def build_claim_rights_task(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build claim-rights boundary classification rows."""

    return [
        _task_record(
            record,
            "claim_rights_boundary_classification",
            {
                "gold_maximum_supported_boundary": str(record.get("human_maximum_supported_boundary") or ""),
                "gold_admissibility_status": str(record.get("human_admissibility_status") or ""),
            },
        )
        for record in records
    ]


def build_hidden_tax_task(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build hidden-tax detection rows."""

    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            _task_record(
                record,
                "hidden_tax_detection",
                {
                    "detected_taxes": _normalize_hidden_taxes(record.get("detected_taxes") or record.get("hidden_tax")),
                    "hidden_tax": _normalize_hidden_taxes(record.get("hidden_tax")),
                    "llm_hidden_tax": _normalize_hidden_taxes(record.get("llm_hidden_tax")),
                    "gold_hidden_tax": _normalize_hidden_taxes(record.get("human_hidden_tax")),
                },
            )
        )
    return rows


def build_required_control_task(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build required-control prediction rows."""

    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            _task_record(
                record,
                "required_control_prediction",
                {
                    "missing_boundary_fields": normalize_multi_label(record.get("missing_boundary_fields")),
                    "required_controls": _normalize_required_controls(record.get("required_controls")),
                    "llm_required_controls": _normalize_required_controls(record.get("llm_required_controls")),
                    "gold_required_controls": _normalize_required_controls(record.get("human_required_controls")),
                },
            )
        )
    return rows


def build_experiment_decision_task(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build experiment-decision ranking rows."""

    rows: list[dict[str, Any]] = []
    for record in records:
        decision = str(record.get("human_experiment_decision") or "")
        rows.append(
            _task_record(
                record,
                "experiment_decision_ranking",
                {
                    "rule_claim_type": str(record.get("claim_type") or ""),
                    "overclaim_risk_flags": normalize_multi_label(record.get("overclaim_risk_flags")),
                    "required_controls": _normalize_required_controls(record.get("required_controls")),
                    "human_maximum_supported_boundary": str(record.get("human_maximum_supported_boundary") or ""),
                    "human_admissibility_status": str(record.get("human_admissibility_status") or ""),
                    "gold_experiment_decision": decision,
                    "gold_priority_binary": 1 if decision in PRIORITY_EXPERIMENT_DECISIONS else 0,
                },
            )
        )
    return rows


def build_all_benchmark_tasks(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Build all eNH3-BoundaryBench tasks."""

    return {
        "source_span_classification": build_source_span_task(records),
        "validation_gate_extraction": build_validation_gate_task(records),
        "claim_rights_boundary_classification": build_claim_rights_task(records),
        "hidden_tax_detection": build_hidden_tax_task(records),
        "required_control_prediction": build_required_control_task(records),
        "experiment_decision_ranking": build_experiment_decision_task(records),
    }


def export_benchmark_tasks(
    tasks: dict[str, list[dict[str, Any]]],
    run_name: str,
    output_dir: str | Path = "data/benchmarks",
) -> dict[str, Any]:
    """Export benchmark tasks as JSONL, CSV, and a manifest."""

    run_dir = Path(output_dir) / run_name
    task_outputs: dict[str, dict[str, Any]] = {}
    validation_errors: list[dict[str, Any]] = []
    for task_name in BENCHMARK_TASKS:
        records = tasks.get(task_name, [])
        prepared = []
        for record in records:
            row = dict(record)
            row["run_name"] = str(row.get("run_name") or run_name)
            valid, errors = validate_task_record(task_name, row)
            if not valid:
                validation_errors.append({"task_name": task_name, "benchmark_id": row.get("benchmark_id"), "errors": errors})
            prepared.append(row)
        if validation_errors:
            continue
        jsonl_path = run_dir / f"{task_name}.jsonl"
        csv_path = run_dir / f"{task_name}.csv"
        _write_jsonl(prepared, jsonl_path)
        _write_csv(prepared, csv_path, task_output_fields(task_name))
        task_outputs[task_name] = {"count": len(prepared), "jsonl": str(jsonl_path), "csv": str(csv_path)}

    if validation_errors:
        raise ValueError("invalid benchmark task records: " + json.dumps(validation_errors[:5], ensure_ascii=True))

    manifest = {
        "run_name": run_name,
        "dataset_name": "eNH3-BoundaryBench",
        "reviewed_records": len(next(iter(tasks.values()), [])),
        "tasks": task_outputs,
        "task_counts": {task_name: item["count"] for task_name, item in task_outputs.items()},
    }
    manifest_path = run_dir / "benchmark_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    return {"run_name": run_name, "manifest": str(manifest_path), "tasks": task_outputs}


def export_benchmark_summary(
    tasks: dict[str, list[dict[str, Any]]],
    run_name: str,
    output_dir: str | Path = "data/reports",
) -> str:
    """Write a BoundaryBench construction summary report."""

    output_path = Path(output_dir) / f"boundary_benchmark_summary.{run_name}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    source_rows = tasks.get("source_span_classification", [])
    claim_rows = tasks.get("claim_rights_boundary_classification", [])
    hidden_rows = tasks.get("hidden_tax_detection", [])
    control_rows = tasks.get("required_control_prediction", [])
    disagreement_rows = [
        row
        for row in claim_rows
        if _truthy(row.get("llm_more_permissive"))
        or _truthy(row.get("llm_more_conservative"))
        or _truthy(row.get("overall_needs_human_review"))
        or _truthy(row.get("needs_human_review"))
    ]

    lines = [
        f"# eNH3-BoundaryBench Summary: {run_name}",
        "",
        "## 1. What eNH3-BoundaryBench is",
        "",
        (
            "eNH3-BoundaryBench is a human-reviewed benchmark for eNH3-specific "
            "claim-rights adjudication: source class, validation gates, supported "
            "claim boundary, hidden taxes, required controls, and experiment decisions."
        ),
        "",
        "## 2. Number of reviewed records used",
        "",
        f"- Reviewed records: {len(source_rows)}",
        "",
        "## 3. Records per task",
        "",
        _counter_table(Counter({task_name: len(rows) for task_name, rows in tasks.items()}), "Task"),
        "",
        "## 4. Label distributions",
        "",
        _counter_table(_counter(source_rows, "gold_text_class"), "Source-span label"),
        "",
        "## 5. Provenance distribution",
        "",
        _counter_table(_counter(source_rows, "provenance_type"), "Provenance"),
        "",
        "## 6. Boundary distribution",
        "",
        _counter_table(_counter(claim_rows, "gold_maximum_supported_boundary"), "Boundary"),
        "",
        "## 7. Hidden-tax distribution",
        "",
        _counter_table(_list_counter(hidden_rows, "gold_hidden_tax"), "Hidden tax"),
        "",
        "## 8. Required-control distribution",
        "",
        _counter_table(_list_counter(control_rows, "gold_required_controls"), "Required control"),
        "",
        "## 9. LLM/rule disagreement coverage",
        "",
        f"- Rows with LLM/rule disagreement or review flags: {len(disagreement_rows)}",
        f"- Rows with LLM model: {sum(1 for row in claim_rows if row.get('llm_model'))}",
        f"- Rule review required: {sum(1 for row in claim_rows if _truthy(row.get('rule_needs_human_review')))}",
        f"- LLM review required: {sum(1 for row in claim_rows if _truthy(row.get('llm_needs_human_review')))}",
        f"- Overall review required: {sum(1 for row in claim_rows if _truthy(row.get('overall_needs_human_review')))}",
        "",
        "## 10. Limitations",
        "",
        (
            "The benchmark is only as complete as the imported human-reviewed rows. "
            "It does not train models, call APIs, or treat unreviewed rows as gold."
        ),
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return str(output_path)


def _valid_reviewed(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid_records: list[dict[str, Any]] = []
    for record in records:
        valid, _ = validate_human_label_record(record)
        if valid and is_reviewed_record(record):
            valid_records.append(record)
    return valid_records


def _task_record(record: dict[str, Any], task_name: str, labels: dict[str, Any]) -> dict[str, Any]:
    row = {
        "benchmark_id": benchmark_record_id(record, task_name),
        "task_name": task_name,
        "run_name": str(record.get("run_name") or ""),
        "paper_id": str(record.get("paper_id") or ""),
        "document_id": str(record.get("document_id") or ""),
        "doi": str(record.get("doi") or ""),
        "source_span_id": str(record.get("source_span_id") or record.get("span_id") or ""),
        "evidence_id": str(record.get("evidence_id") or ""),
        "source_text": str(record.get("source_text") or ""),
        "source_section": str(record.get("source_section") or ""),
        "provenance_type": str(record.get("provenance_type") or ""),
        "provenance_confidence": str(record.get("provenance_confidence") or ""),
        "rule_text_class": str(record.get("text_class") or record.get("rule_text_class") or ""),
        "rule_maximum_supported_boundary": str(
            record.get("maximum_supported_boundary") or record.get("rule_maximum_supported_boundary") or ""
        ),
        "support_hint_boundary": str(record.get("support_hint_boundary") or ""),
        "paired_body_required": bool(record.get("paired_body_required")),
        "caption_context_only": bool(record.get("caption_context_only")),
        "rule_admissibility_status": str(record.get("admissibility_status") or record.get("rule_admissibility_status") or ""),
        "llm_model": str(record.get("llm_model") or ""),
        "llm_text_class": str(record.get("llm_text_class") or ""),
        "llm_maximum_supported_boundary": str(record.get("llm_maximum_supported_boundary") or ""),
        "trusted_llm_maximum_supported_boundary": str(record.get("trusted_llm_maximum_supported_boundary") or ""),
        "llm_more_permissive": bool(record.get("llm_more_permissive")),
        "llm_more_conservative": bool(record.get("llm_more_conservative")),
        "rule_needs_human_review": bool(record.get("rule_needs_human_review")),
        "llm_needs_human_review": bool(record.get("llm_needs_human_review")),
        "overall_needs_human_review": bool(
            record.get("overall_needs_human_review")
            if "overall_needs_human_review" in record
            else record.get("needs_human_review")
        ),
        "review_priority_band": str(record.get("review_priority_band") or "none"),
        "review_trigger_flags": record.get("review_trigger_flags") or [],
        "needs_human_review": bool(
            record.get("overall_needs_human_review")
            if "overall_needs_human_review" in record
            else record.get("needs_human_review")
        ),
        "human_reviewer_id": str(record.get("human_reviewer_id") or ""),
        "human_notes": str(record.get("human_notes") or ""),
        "validation_gates": record.get("validation_gates") or {},
        "raw_rule_record": record.get("raw_rule_record") or "",
        "raw_llm_record": record.get("raw_llm_record") or "",
    }
    row.update(labels)
    return row


def _human_gate(record: dict[str, Any], field: str) -> str:
    return normalize_label(str(record.get(field) or ""), VALIDATION_GATE_LABELS, default="unclear")


def _rule_gate(record: dict[str, Any], field: str) -> str:
    output_field = "NOx_control" if field == "NOx_control" else field
    explicit_key = f"rule_validation_{output_field}"
    if str(record.get(explicit_key) or "").strip():
        return _normalize_gate_value(record.get(explicit_key))

    validation = record.get("validation_gates")
    if isinstance(validation, str):
        try:
            validation = json.loads(validation)
        except json.JSONDecodeError:
            validation = {}
    if not isinstance(validation, dict):
        validation = {}
    keys = [field]
    if field == "NOx_control":
        keys.extend(["nox_control", "NOx_control"])
    for key in keys:
        if key in validation:
            return _normalize_gate_value(validation.get(key))
    return "unclear"


def _normalize_gate_value(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if text in {"explicit", "yes", "true", "present", "reported"}:
        return "explicit"
    if text in {"missing", "no", "false", "absent", "not reported", "not_reported"}:
        return "missing"
    if text in {"secondary_only", "secondary"}:
        return "secondary_only"
    if text in {"not_applicable", "not applicable", "n/a", "na"}:
        return "not_applicable"
    return "unclear"


def _normalize_hidden_taxes(value: Any) -> list[str]:
    return [item for item in normalize_multi_label(value) if item in HIDDEN_TAX_LABELS]


def _normalize_required_controls(value: Any) -> list[str]:
    normalized: list[str] = []
    for item in normalize_multi_label(value):
        canonical = _canonical_required_control(item)
        if canonical and canonical not in normalized:
            normalized.append(canonical)
    return normalized


def _canonical_required_control(value: str) -> str:
    text = str(value or "").strip()
    if text in REQUIRED_CONTROL_LABELS:
        return text
    lower = text.casefold()
    if "15n" in lower or "isotope" in lower:
        return "15N2 isotope validation"
    if "blank" in lower or "n2-free" in lower or "ar/" in lower:
        return "Ar/N2-free blank"
    if "nox" in lower or "nitrate" in lower or "nitrite" in lower:
        return "NOx/nitrate/nitrite screening"
    if "contamination" in lower or "background" in lower:
        return "contamination/background NH3 control"
    if "h2-off" in lower or "hor" in lower or "hydrogen" in lower:
        return "H2-off/HOR-off control"
    if "gas/liquid" in lower or "gas-liquid" in lower or "product accounting" in lower:
        return "gas/liquid product accounting"
    if "wetting" in lower or "flooding" in lower:
        return "wetting/flooding diagnosis"
    if "voltage" in lower or "current" in lower or "runtime" in lower:
        return "voltage/current/runtime reporting"
    if "capture" in lower or "outlet" in lower or "product state" in lower:
        return "product capture accounting"
    if "solvent" in lower or "recycle" in lower or "electrolyte" in lower:
        return "solvent inventory/recycle reporting"
    if "crosscheck" in lower:
        return "isotope/product-state crosscheck"
    if "primary body" in lower or "body text" in lower or "pair" in lower:
        return "primary body text pairing"
    return ""


def _write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":")))
            handle.write("\n")


def _write_csv(records: list[dict[str, Any]], output_path: Path, preferred: list[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _fieldnames(records, preferred)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: _csv_value(record.get(field)) for field in fieldnames})


def _fieldnames(records: list[dict[str, Any]], preferred: list[str]) -> list[str]:
    names = set(preferred)
    for record in records:
        names.update(record)
    ordered = [field for field in preferred if field in names]
    ordered.extend(sorted(name for name in names if name not in set(ordered)))
    return ordered


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple, set)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return str(value)


def _counter(records: list[dict[str, Any]], key: str) -> Counter[str]:
    return Counter(str(record.get(key) or "missing") for record in records)


def _list_counter(records: list[dict[str, Any]], key: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for record in records:
        values = normalize_multi_label(record.get(key))
        if values:
            counter.update(values)
    return counter


def _counter_table(counter: Counter[str], label: str) -> str:
    if not counter:
        return "No records."
    rows = [[key, count] for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))]
    return _markdown_table([label, "Records"], rows)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_escape_cell(value) for value in row) + " |")
    return "\n".join(lines)


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"true", "1", "yes", "y"}
