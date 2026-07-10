"""Closed-loop evaluation for planned and imported eNH3 experiments."""

from __future__ import annotations

from collections import Counter
import csv
import json
from pathlib import Path
from typing import Any

from enh3bench.experiment_result_importer import load_experiment_routes
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


def evaluate_closed_loop(run_name: str, output_dir: str | Path = "data/closed_loop") -> dict[str, Any]:
    """Evaluate planned routes against imported results and write machine-readable outputs."""

    routes, results = load_routes_and_results(run_name)
    if not results:
        raise ValueError(NO_RESULTS_MESSAGE)
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
        "next_round_suggestions": propose_next_round_adjustments({"route_evaluations": route_evaluations}),
        "route_evaluations": route_evaluations,
    }
    run_dir = Path(output_dir) / run_name
    json_path = run_dir / "closed_loop_evaluation.json"
    csv_path = run_dir / "closed_loop_evaluation.csv"
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(evaluation, ensure_ascii=True, indent=2, sort_keys=True, default=str), encoding="utf-8", newline="\n")
    _write_csv([evaluation], csv_path)
    evaluation["json"] = str(json_path)
    evaluation["csv"] = str(csv_path)
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
        "## 3. Prediction-vs-experiment summary",
        "",
        f"- Prediction hit rate: {evaluation.get('prediction_hit_rate', 0)}",
        "",
        "## 4. Successful routes",
        "",
        f"- Success count: {evaluation.get('success_count', 0)}",
        f"- Partial count: {evaluation.get('partial_count', 0)}",
        "",
        "## 5. Failed or invalid routes",
        "",
        f"- Failed count: {evaluation.get('failed_count', 0)}",
        f"- Invalid count: {evaluation.get('invalid_count', 0)}",
        "",
        "## 6. Hidden taxes confirmed",
        "",
        _bullet_list(evaluation.get("hidden_tax_confirmed")),
        "",
        "## 7. Control failures",
        "",
        _bullet_list(evaluation.get("required_control_failures")),
        "",
        "## 8. What rules should change",
        "",
        _bullet_list(evaluation.get("route_revision_recommendations")),
        "",
        "## 9. Next-round route recommendations",
        "",
        _bullet_list(item.get("recommendation") if isinstance(item, dict) else item for item in evaluation.get("next_round_suggestions") or []),
        "",
        "## 10. Limitations",
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


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple, set)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return str(value)
