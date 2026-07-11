"""Closed-loop evaluation for planned and imported eNH3 experiments."""

from __future__ import annotations

from collections import Counter
import csv
import json
import re
import statistics
from pathlib import Path
from typing import Any

from enh3bench.experiment_result_importer import MEASUREMENT_TO_RESULT_FIELD, load_experiment_routes
from enh3bench.experiment_planner import apply_stage_gates, next_actionable_route, rank_routes
from enh3bench.ledger_router import load_jsonl


NO_RESULTS_MESSAGE = (
    "No imported experiment results found. Run export_experiment_result_template, perform experiments, then import_experiment_results."
)


def load_routes_and_results(run_name: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load ranked routes and imported experiment results for a run."""

    routes = load_experiment_routes(run_name)
    results = load_jsonl(Path("data") / "experiment_results" / run_name / "experiment_results_imported.jsonl")
    return routes, results


def evaluate_route_prediction(route: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate one route against imported results."""

    route_id = str(route.get("route_id") or "")
    matched = [result for result in results if str(result.get("route_id") or "") == route_id]
    statuses = Counter(str(result.get("success_status") or "missing") for result in matched)
    controls_failed = [item for result in matched for item in _list_values(result.get("controls_failed"))]
    hidden_tax_targeted = _list_values(route.get("hidden_tax_targeted"))
    success_or_partial = statuses.get("success", 0) + statuses.get("partial", 0)
    return {
        "route_id": route_id,
        "route_type": route.get("route_type") or "",
        "priority_label": route.get("priority_label") or "",
        "execution_stage": route.get("execution_stage") or "",
        "stage_rank": route.get("stage_rank"),
        "stage_gate_status": route.get("stage_gate_status") or "",
        "blocked_by_route_ids": route.get("blocked_by_route_ids") or [],
        "results_count": len(matched),
        "success_count": statuses.get("success", 0),
        "partial_count": statuses.get("partial", 0),
        "failed_count": statuses.get("failed", 0),
        "invalid_count": statuses.get("invalid", 0),
        "required_control_failures": controls_failed,
        "hidden_tax_confirmed": hidden_tax_targeted if success_or_partial else [],
        "hidden_tax_not_observed": hidden_tax_targeted if statuses.get("failed", 0) else [],
        "prediction_hit": bool(success_or_partial),
    }


def evaluate_baseline_gate(
    routes: list[dict[str, Any]],
    results: list[dict[str, Any]],
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate independent baseline completeness and optional repeatability thresholds."""

    baseline_route = next((route for route in routes if route.get("route_type") == "baseline_repeatability"), None)
    if baseline_route is None:
        return _empty_baseline_gate("not_started")
    route_id = str(baseline_route.get("route_id") or "")
    rows = [result for result in results if str(result.get("route_id") or "") == route_id]
    minimum = max(
        1,
        _int_value(
            _first_defined(
                _profile_value(profile or {}, "minimum_valid_baseline_replicates"),
                baseline_route.get("minimum_valid_baseline_replicates"),
                baseline_route.get("minimum_valid_replicates"),
                3,
            ),
            3,
        ),
    )
    if not rows:
        gate = _empty_baseline_gate("not_started")
        gate["minimum_valid_replicates"] = minimum
        return gate

    required_controls = _list_values(baseline_route.get("required_controls"))
    mandatory_measurements = _list_values(baseline_route.get("mandatory_measurements")) or _list_values(
        baseline_route.get("required_measurements")
    )
    seen_executions: set[str] = set()
    seen_replicates: set[tuple[str, str]] = set()
    seen_assemblies: set[tuple[str, str]] = set()
    valid_rows: list[dict[str, Any]] = []
    replicate_table: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for row in rows:
        execution_id = str(row.get("execution_id") or row.get("experiment_id") or "").strip()
        replicate_key = (str(row.get("condition_id") or "baseline"), str(row.get("replicate_id") or ""))
        reasons: list[str] = []
        category = "valid"
        if not execution_id or execution_id in seen_executions:
            category = "duplicate_execution_or_timepoint"
            reasons.append("execution identity was already counted")
        elif replicate_key in seen_replicates:
            category = "duplicate_replicate_identity"
            reasons.append("condition/replicate identity was already counted")
        else:
            seen_executions.add(execution_id)
            seen_replicates.add(replicate_key)

        if category == "valid" and not _truthy(row.get("independent_replicate")):
            category = "non_independent"
            reasons.append("row does not establish an independent replicate")
        if category == "valid" and _truthy(baseline_route.get("independent_assembly_required")):
            for field in ("assembly_id", "cell_build_id"):
                value = str(row.get(field) or "").strip()
                identity = (field, value)
                if not value or identity in seen_assemblies:
                    category = "non_independent"
                    reasons.append(f"{field} is missing or reused")
                else:
                    seen_assemblies.add(identity)

        status = str(row.get("success_status") or "").strip()
        failed_controls = _list_values(row.get("controls_failed"))
        completed_controls = set(_list_values(row.get("controls_completed")))
        missing_controls = [control for control in required_controls if control not in completed_controls]
        missing_measurements = [
            measurement
            for measurement in mandatory_measurements
            if not str(row.get(MEASUREMENT_TO_RESULT_FIELD.get(measurement, measurement)) or "").strip()
        ]
        if category == "valid" and (failed_controls or missing_controls):
            category = "invalid_controls"
            reasons.extend([f"failed control: {item}" for item in failed_controls])
            reasons.extend([f"missing control: {item}" for item in missing_controls])
        if category == "valid" and missing_measurements:
            category = "incomplete_measurements"
            reasons.extend([f"missing measurement: {item}" for item in missing_measurements])
        if category == "valid" and status == "failed":
            category = "failed_operationally"
            reasons.append("result status is failed")
        elif category == "valid" and status == "invalid":
            category = "invalid_result"
            reasons.append(str(row.get("invalid_reason") or "result status is invalid"))
        elif category == "valid" and status in {"inconclusive", ""}:
            category = "inconclusive"
            reasons.append("result did not establish a valid baseline outcome")
        elif category == "valid" and status not in {"success", "partial"}:
            category = "inconclusive"
            reasons.append(f"unsupported result status: {status}")

        counts[category] += 1
        if category == "valid":
            valid_rows.append(row)
        replicate_table.append(
            {
                "execution_id": execution_id,
                "condition_id": row.get("condition_id") or "",
                "replicate_id": row.get("replicate_id") or "",
                "timepoint_id": row.get("timepoint_id") or "",
                "category": category,
                "reasons": reasons,
            }
        )

    statistics_payload = {
        "FE": _descriptive_statistics(_numeric_values(valid_rows, "FE")),
        "NH3_yield": _descriptive_statistics(_numeric_values(valid_rows, "NH3_yield")),
    }
    human_approval = any(_truthy(row.get("human_baseline_approval")) for row in rows)
    human_notes = _dedupe(row.get("human_baseline_notes") for row in rows)
    data_complete = len(valid_rows) >= minimum
    threshold_results = {"FE": "not_evaluated", "NH3_yield": "not_evaluated"}

    if counts["invalid_controls"]:
        status = "invalid_controls"
    elif counts["incomplete_measurements"]:
        status = "incomplete_measurements"
    elif counts["failed_operationally"] or counts["invalid_result"]:
        status = "failed"
    elif not data_complete:
        status = "insufficient_replicates"
    else:
        fe_threshold = _optional_number(
            _first_defined(
                _profile_value(profile or {}, "baseline_FE_CV_threshold_optional"),
                baseline_route.get("baseline_FE_CV_threshold_optional"),
            )
        )
        yield_threshold = _optional_number(
            _first_defined(
                _profile_value(profile or {}, "baseline_yield_CV_threshold_optional"),
                baseline_route.get("baseline_yield_CV_threshold_optional"),
            )
        )
        threshold_results = {
            "FE": _threshold_result(statistics_payload["FE"], fe_threshold),
            "NH3_yield": _threshold_result(statistics_payload["NH3_yield"], yield_threshold),
        }
        if any(value == "failed" for value in threshold_results.values()):
            status = "failed"
        elif all(value == "passed" for value in threshold_results.values() if value != "not_configured") and (
            all(value != "not_configured" for value in threshold_results.values()) or human_approval
        ):
            status = "passed"
        else:
            status = "passed" if human_approval else "awaiting_human_approval"

    return {
        "baseline_route_id": route_id,
        "baseline_gate_status": status,
        "minimum_valid_replicates": minimum,
        "valid_independent_replicates": len(valid_rows),
        "baseline_data_completeness": data_complete,
        "human_baseline_approval": human_approval,
        "human_baseline_notes": human_notes,
        "result_category_counts": dict(sorted(counts.items())),
        "repeatability_statistics": statistics_payload,
        "threshold_results": threshold_results,
        "baseline_replicate_table": replicate_table,
    }


def evaluate_closed_loop(
    run_name: str,
    output_dir: str | Path = "data/closed_loop",
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate planned routes against imported results and write machine-readable outputs."""

    routes, results = load_routes_and_results(run_name)
    if not results:
        raise ValueError(NO_RESULTS_MESSAGE)
    baseline_gate = evaluate_baseline_gate(routes, results, profile=profile)
    baseline_route_id = str(baseline_gate.get("baseline_route_id") or "")
    evaluated_results = []
    for original in results:
        result = dict(original)
        if baseline_route_id and str(result.get("route_id") or "") == baseline_route_id:
            result["baseline_gate_status"] = baseline_gate.get("baseline_gate_status")
        evaluated_results.append(result)
    completed_route_ids = _completed_route_ids(routes, results, baseline_gate)
    documented_failure = any(str(result.get("success_status") or "") in {"failed", "invalid"} for result in results)
    routes = rank_routes(
        apply_stage_gates(
            routes,
            {
                "completed_route_ids": completed_route_ids,
                "documented_failure": documented_failure,
                "baseline_satisfied": baseline_gate.get("baseline_gate_status") == "passed",
            },
        )
    )
    next_route = next_actionable_route(routes)
    route_evaluations = [evaluate_route_prediction(route, results) for route in routes]
    status_counts = Counter(str(result.get("success_status") or "missing") for result in results)
    executed_route_ids = {str(result.get("route_id") or "") for result in results if str(result.get("route_id") or "")}
    priority_route_ids = {str(route.get("route_id") or "") for route in routes if route.get("priority_label") == "priority_experiment"}
    hit_count = sum(1 for item in route_evaluations if item.get("prediction_hit"))
    executed_evaluations = [item for item in route_evaluations if item.get("route_id") in executed_route_ids]
    evaluation = {
        "run_name": run_name,
        "routes_generated": len(routes),
        "routes_executed": len(executed_route_ids),
        "priority_routes_executed": len(priority_route_ids & executed_route_ids),
        "success_count": status_counts.get("success", 0),
        "partial_count": status_counts.get("partial", 0),
        "failed_count": status_counts.get("failed", 0),
        "invalid_count": status_counts.get("invalid", 0),
        "hidden_tax_confirmed": _dedupe(item for route in route_evaluations for item in route.get("hidden_tax_confirmed", [])),
        "hidden_tax_not_observed": _dedupe(item for route in route_evaluations for item in route.get("hidden_tax_not_observed", [])),
        "required_control_failures": _dedupe(item for route in route_evaluations for item in route.get("required_control_failures", [])),
        "prediction_hit_rate": round(hit_count / len(executed_evaluations), 3) if executed_evaluations else 0.0,
        "invalid_due_to_controls_count": sum(1 for result in results if result.get("success_status") == "invalid" and _list_values(result.get("controls_failed"))),
        "route_revision_recommendations": _revision_recommendations(route_evaluations),
        "schema_version": "0.13",
        "baseline_gate_status": baseline_gate.get("baseline_gate_status"),
        "baseline_gate": baseline_gate,
        "completed_route_ids": completed_route_ids,
        "next_actionable_route": next_route or {},
        "unlocked_route_ids": [
            str(route.get("route_id") or "")
            for route in routes
            if str(route.get("stage_gate_status") or "") in {"actionable", "event_triggered", "waived"}
            and not route.get("is_route_group")
        ],
        "next_round_suggestions": propose_next_round_adjustments({"route_evaluations": route_evaluations}),
        "route_evaluations": route_evaluations,
    }
    run_dir = Path(output_dir) / run_name
    json_path = run_dir / "closed_loop_evaluation.json"
    csv_path = run_dir / "closed_loop_evaluation.csv"
    regenerated_routes_path = run_dir / "regenerated_experiment_routes.jsonl"
    evaluated_results_path = run_dir / "evaluated_experiment_results.jsonl"
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(evaluation, ensure_ascii=True, indent=2, sort_keys=True, default=str), encoding="utf-8", newline="\n")
    _write_csv([evaluation], csv_path)
    _write_jsonl(routes, regenerated_routes_path)
    _write_jsonl(evaluated_results, evaluated_results_path)
    evaluation["json"] = str(json_path)
    evaluation["csv"] = str(csv_path)
    evaluation["regenerated_routes"] = str(regenerated_routes_path)
    evaluation["evaluated_results"] = str(evaluated_results_path)
    return evaluation


def export_closed_loop_report(
    evaluation: dict[str, Any],
    run_name: str,
    output_dir: str | Path = "data/reports",
) -> str:
    """Write a closed-loop Markdown report."""

    output_path = Path(output_dir) / f"closed_loop_report.{run_name}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Closed-Loop Report: {run_name}",
        "",
        "## 1. What was planned",
        "",
        f"- Routes generated: {evaluation.get('routes_generated', 0)}",
        "",
        "## 2. What was executed",
        "",
        f"- Routes executed: {evaluation.get('routes_executed', 0)}",
        f"- Priority routes executed: {evaluation.get('priority_routes_executed', 0)}",
        "",
        "## 3. Baseline gate",
        "",
        f"- Gate status: {evaluation.get('baseline_gate_status') or 'not_started'}",
        f"- Valid independent replicates: {(evaluation.get('baseline_gate') or {}).get('valid_independent_replicates', 0)}",
        f"- Minimum valid replicates: {(evaluation.get('baseline_gate') or {}).get('minimum_valid_replicates', 3)}",
        f"- Data completeness: {(evaluation.get('baseline_gate') or {}).get('baseline_data_completeness', False)}",
        f"- Human approval: {(evaluation.get('baseline_gate') or {}).get('human_baseline_approval', False)}",
        "",
        _baseline_table((evaluation.get("baseline_gate") or {}).get("baseline_replicate_table") or []),
        "",
        "Repeatability statistics:",
        "",
        "```json",
        json.dumps((evaluation.get("baseline_gate") or {}).get("repeatability_statistics") or {}, ensure_ascii=True, indent=2, sort_keys=True),
        "```",
        "",
        "## 4. Prediction-vs-experiment summary",
        "",
        f"- Prediction hit rate: {evaluation.get('prediction_hit_rate', 0)}",
        "",
        "## 5. Successful routes",
        "",
        f"- Success count: {evaluation.get('success_count', 0)}",
        f"- Partial count: {evaluation.get('partial_count', 0)}",
        "",
        "## 6. Failed or invalid routes",
        "",
        f"- Failed count: {evaluation.get('failed_count', 0)}",
        f"- Invalid count: {evaluation.get('invalid_count', 0)}",
        "",
        "## 7. Hidden taxes confirmed",
        "",
        _bullet_list(evaluation.get("hidden_tax_confirmed")),
        "",
        "## 8. Control failures",
        "",
        _bullet_list(evaluation.get("required_control_failures")),
        "",
        "## 9. What rules should change",
        "",
        _bullet_list(evaluation.get("route_revision_recommendations")),
        "",
        "## 10. Route unlocking",
        "",
        f"- Unlocked routes: {', '.join(evaluation.get('unlocked_route_ids') or []) or 'none'}",
        f"- Next actionable route: {(evaluation.get('next_actionable_route') or {}).get('route_id') or 'none'}",
        "",
        _route_blocker_table(evaluation.get("route_evaluations") or []),
        "",
        "## 11. Next-round route recommendations",
        "",
        _bullet_list(item.get("recommendation") if isinstance(item, dict) else item for item in evaluation.get("next_round_suggestions") or []),
        "",
        "## 12. Limitations",
        "",
        "Closed-loop evaluation reflects imported result fields only. It does not infer scientific conclusions beyond provided measurements and controls.",
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return str(output_path)


def propose_next_round_adjustments(evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    """Suggest next-round changes from route-level evaluation."""

    suggestions: list[dict[str, Any]] = []
    for route in evaluation.get("route_evaluations") or []:
        route_id = route.get("route_id") or ""
        if route.get("invalid_count"):
            suggestions.append({"route_id": route_id, "recommendation": "repeat mandatory controls before interpreting route outcome"})
        elif route.get("failed_count"):
            suggestions.append({"route_id": route_id, "recommendation": "revise route variables toward observed failure mode"})
        elif route.get("success_count") or route.get("partial_count"):
            suggestions.append({"route_id": route_id, "recommendation": "consider boundary-complete follow-up with stricter controls"})
    return suggestions


def _revision_recommendations(route_evaluations: list[dict[str, Any]]) -> list[str]:
    recommendations: list[str] = []
    for route in route_evaluations:
        if route.get("invalid_count"):
            recommendations.append(f"{route.get('route_id')}: control failures must block success labels.")
        if route.get("failed_count"):
            recommendations.append(f"{route.get('route_id')}: failure should update route variable selection.")
    return recommendations


def _completed_route_ids(
    routes: list[dict[str, Any]],
    results: list[dict[str, Any]],
    baseline_gate: dict[str, Any],
) -> list[str]:
    completed: list[str] = []
    for route in routes:
        route_id = str(route.get("route_id") or "")
        if route.get("route_type") == "baseline_repeatability":
            if baseline_gate.get("baseline_gate_status") == "passed":
                completed.append(route_id)
            continue
        matched = [result for result in results if str(result.get("route_id") or "") == route_id]
        valid_outcomes = [result for result in matched if _result_is_valid_for_route(route, result)]
        minimum = max(1, int(route.get("minimum_valid_replicates") or 1))
        if len(valid_outcomes) >= minimum:
            completed.append(route_id)
    return completed


def _result_is_valid_for_route(route: dict[str, Any], result: dict[str, Any]) -> bool:
    if str(result.get("success_status") or "") not in {"success", "partial"}:
        return False
    if _list_values(result.get("validation_errors")) or _list_values(result.get("controls_failed")):
        return False
    completed_controls = set(_list_values(result.get("controls_completed")))
    if any(control not in completed_controls for control in _list_values(route.get("required_controls"))):
        return False
    mandatory = _list_values(route.get("mandatory_measurements")) or _list_values(route.get("required_measurements"))
    return all(
        str(result.get(MEASUREMENT_TO_RESULT_FIELD.get(measurement, measurement)) or "").strip()
        for measurement in mandatory
    )


def _empty_baseline_gate(status: str) -> dict[str, Any]:
    return {
        "baseline_route_id": "",
        "baseline_gate_status": status,
        "minimum_valid_replicates": 3,
        "valid_independent_replicates": 0,
        "baseline_data_completeness": False,
        "human_baseline_approval": False,
        "human_baseline_notes": [],
        "result_category_counts": {},
        "repeatability_statistics": {"FE": _descriptive_statistics([]), "NH3_yield": _descriptive_statistics([])},
        "threshold_results": {"FE": "not_evaluated", "NH3_yield": "not_evaluated"},
        "baseline_replicate_table": [],
    }


def _numeric_values(rows: list[dict[str, Any]], field: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        match = re.search(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(row.get(field) or ""))
        if match:
            values.append(float(match.group(0)))
    return values


def _descriptive_statistics(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "standard_deviation": None, "coefficient_of_variation": None, "min": None, "max": None}
    mean = statistics.fmean(values)
    standard_deviation = statistics.stdev(values) if len(values) >= 2 else None
    coefficient = standard_deviation / abs(mean) if standard_deviation is not None and mean != 0 else None
    return {
        "count": len(values),
        "mean": mean,
        "standard_deviation": standard_deviation,
        "coefficient_of_variation": coefficient,
        "min": min(values),
        "max": max(values),
    }


def _threshold_result(statistics_payload: dict[str, Any], threshold: float | None) -> str:
    if threshold is None:
        return "not_configured"
    coefficient = statistics_payload.get("coefficient_of_variation")
    if coefficient is None:
        return "not_evaluable"
    return "passed" if float(coefficient) <= threshold else "failed"


def _first_defined(*values: Any) -> Any:
    for value in values:
        if value is not None and str(value).strip() != "":
            return value
    return None


def _profile_value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for child in value.values():
            found = _profile_value(child, key)
            if found is not None:
                return found
    return None


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(value)
        return number / 100.0 if number > 1.0 else number
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"true", "1", "yes", "y", "approved", "pass", "passed"}


def _baseline_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No baseline results."
    lines = [
        "| Execution | Condition | Replicate | Timepoint | Category | Reasons |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        reasons = "; ".join(_list_values(row.get("reasons")))
        values = [
            row.get("execution_id") or "",
            row.get("condition_id") or "",
            row.get("replicate_id") or "",
            row.get("timepoint_id") or "",
            row.get("category") or "",
            reasons,
        ]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in values) + " |")
    return "\n".join(lines)


def _route_blocker_table(routes: list[dict[str, Any]]) -> str:
    if not routes:
        return "No routes."
    lines = ["| Route | Stage | Gate status | Blocked by |", "| --- | --- | --- | --- |"]
    for route in routes:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(route.get("route_id") or ""),
                    str(route.get("execution_stage") or ""),
                    str(route.get("stage_gate_status") or ""),
                    ", ".join(_list_values(route.get("blocked_by_route_ids"))) or "none",
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _list_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return _list_values(parsed)
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def _bullet_list(value: Any) -> str:
    values = list(value) if not isinstance(value, str) and value is not None else _list_values(value)
    if not values:
        return "- none"
    return "\n".join(f"- {item}" for item in values)


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _write_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for record in records for key in record})
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow({field: _csv_value(record.get(field)) for field in fieldnames})


def _write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, default=str, separators=(",", ":")))
            handle.write("\n")


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple, set)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return str(value)
