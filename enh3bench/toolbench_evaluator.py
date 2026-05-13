"""ToolBench-style method comparison for eNH3-ExtractBench."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from math import isclose
from statistics import mean
from typing import Any


CATEGORICAL_FIELDS = [
    "reaction_family",
    "nitrogen_source",
    "isotope_validation",
    "blank_control",
    "contamination_control",
    "nox_screening",
    "reliability_label",
]

NUMERIC_FIELDS = [
    "FE_percent",
    "EE_percent",
    "NH3_yield",
    "potential",
    "stability",
]

VALIDATION_FIELDS = [
    "isotope_validation",
    "blank_control",
    "contamination_control",
    "nox_screening",
]


def evaluate_method(
    gold_records: Iterable[Mapping[str, Any]],
    pred_records: Iterable[Mapping[str, Any]],
    method_name: str,
) -> dict[str, Any]:
    """Evaluate one extraction method against gold records."""

    gold_list = [_normalize_record(record) for record in gold_records]
    pred_list = [_normalize_record(record) for record in pred_records]
    pred_by_id = _index_by_id(pred_list)
    categorical = {
        field: _categorical_accuracy(gold_list, pred_by_id, field)
        for field in CATEGORICAL_FIELDS
    }
    numeric = {
        field: _numeric_accuracy(gold_list, pred_by_id, field, _abs_tolerance(field), _rel_tolerance(field))
        for field in NUMERIC_FIELDS
    }
    return {
        "method_name": method_name,
        "gold_records": len(gold_list),
        "pred_records": len(pred_list),
        "categorical": categorical,
        "numeric": numeric,
        "missing_rate": _missing_rate(gold_list, pred_by_id),
        "unsupported_validation_yes_rate": _unsupported_validation_yes_rate(gold_list, pred_list),
        "reliability_label_agreement": categorical["reliability_label"]["accuracy"],
        "source_grounding_coverage": _source_grounding_coverage(pred_list),
    }


def compare_methods(
    gold_records: Iterable[Mapping[str, Any]],
    runs_by_method: Mapping[str, Iterable[Mapping[str, Any]]],
) -> dict[str, Any]:
    """Evaluate multiple extraction methods using the same gold set."""

    gold_list = list(gold_records)
    method_results = {
        method_name: evaluate_method(gold_list, records, method_name)
        for method_name, records in sorted(runs_by_method.items())
    }
    return {
        "method_count": len(method_results),
        "methods": method_results,
    }


def write_comparison_markdown(results: Mapping[str, Any]) -> str:
    """Render comparison results as Markdown."""

    methods = results.get("methods", {})
    lines = [
        "# eNH3-ExtractBench Method Comparison",
        "",
        "## Method Summary",
        "",
        "| method | gold records | predictions | missing rate | unsupported validation yes rate | reliability agreement | grounding coverage |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for method_name, result in methods.items():
        lines.append(
            "| {method} | {gold} | {pred} | {missing:.3f} | {unsupported:.3f} | {reliability:.3f} | {grounding:.3f} |".format(
                method=method_name,
                gold=result.get("gold_records", 0),
                pred=result.get("pred_records", 0),
                missing=float(result.get("missing_rate", 0.0)),
                unsupported=float(result.get("unsupported_validation_yes_rate", 0.0)),
                reliability=float(result.get("reliability_label_agreement", 0.0)),
                grounding=float(result.get("source_grounding_coverage", 0.0)),
            )
        )

    lines.extend(["", "## Field Performance", ""])
    for method_name, result in methods.items():
        lines.extend(
            [
                f"### {method_name}",
                "",
                "| field | type | accuracy | total |",
                "| --- | --- | ---: | ---: |",
            ]
        )
        for field, metric in result.get("categorical", {}).items():
            lines.append(f"| {field} | categorical | {metric.get('accuracy', 0.0):.3f} | {metric.get('total', 0)} |")
        for field, metric in result.get("numeric", {}).items():
            lines.append(f"| {field} | numeric | {metric.get('accuracy', 0.0):.3f} | {metric.get('total_gold_values', 0)} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _categorical_accuracy(
    gold_records: list[dict[str, Any]],
    pred_by_id: dict[str, dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    correct = 0
    missing_predictions = 0
    for gold in gold_records:
        pred = pred_by_id.get(str(gold.get("record_id", "")))
        if pred is None:
            missing_predictions += 1
            continue
        if _norm(gold.get(field)) == _norm(pred.get(field)):
            correct += 1
    total = len(gold_records)
    return {
        "field": field,
        "total": total,
        "correct": correct,
        "accuracy": _rate(correct, total),
        "missing_predictions": missing_predictions,
    }


def _numeric_accuracy(
    gold_records: list[dict[str, Any]],
    pred_by_id: dict[str, dict[str, Any]],
    field: str,
    tolerance_abs: float,
    tolerance_rel: float,
) -> dict[str, Any]:
    total_gold_values = 0
    within_tolerance = 0
    missing_predictions = 0
    errors: list[float] = []
    for gold in gold_records:
        gold_value = gold.get(field)
        if _is_missing(gold_value):
            continue
        total_gold_values += 1
        pred = pred_by_id.get(str(gold.get("record_id", "")))
        pred_value = None if pred is None else pred.get(field)
        if _is_missing(pred_value):
            missing_predictions += 1
            continue
        try:
            gold_float = float(gold_value)
            pred_float = float(pred_value)
        except (TypeError, ValueError):
            missing_predictions += 1
            continue
        errors.append(abs(gold_float - pred_float))
        if isclose(gold_float, pred_float, abs_tol=tolerance_abs, rel_tol=tolerance_rel):
            within_tolerance += 1
    return {
        "field": field,
        "total_gold_values": total_gold_values,
        "within_tolerance": within_tolerance,
        "accuracy": _rate(within_tolerance, total_gold_values),
        "missing_predictions": missing_predictions,
        "mean_absolute_error": mean(errors) if errors else None,
        "max_absolute_error": max(errors) if errors else None,
    }


def _missing_rate(gold_records: list[dict[str, Any]], pred_by_id: dict[str, dict[str, Any]]) -> float:
    fields = CATEGORICAL_FIELDS + NUMERIC_FIELDS
    total = 0
    missing = 0
    for gold in gold_records:
        pred = pred_by_id.get(str(gold.get("record_id", "")))
        for field in fields:
            if _is_missing(gold.get(field)):
                continue
            total += 1
            if pred is None or _is_missing(pred.get(field)):
                missing += 1
    return _rate(missing, total)


def _unsupported_validation_yes_rate(
    gold_records: list[dict[str, Any]],
    pred_records: list[dict[str, Any]],
) -> float:
    gold_by_id = _index_by_id(gold_records)
    predicted_yes = 0
    unsupported = 0
    for pred in pred_records:
        gold = gold_by_id.get(str(pred.get("record_id", "")), {})
        for field in VALIDATION_FIELDS:
            if pred.get(field) != "yes":
                continue
            predicted_yes += 1
            if gold.get(field) != "yes":
                unsupported += 1
    return _rate(unsupported, predicted_yes)


def _source_grounding_coverage(records: list[dict[str, Any]]) -> float:
    if not records:
        return 0.0
    grounded = sum(1 for record in records if record.get("source_grounding_status") in {"explicit", "mixed"})
    return grounded / len(records)


def _normalize_record(record: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    if "record_id" not in normalized:
        normalized["record_id"] = normalized.get("evidence_id")
    field_map = {
        "faradaic_efficiency_percent": "FE_percent",
        "energy_efficiency_percent": "EE_percent",
        "nh3_yield_value": "NH3_yield",
        "nh3_yield_unit": "NH3_yield_unit",
        "potential_value": "potential",
        "stability_hours": "stability",
    }
    for source, target in field_map.items():
        if target not in normalized and source in normalized:
            normalized[target] = normalized[source]
    return normalized


def _index_by_id(records: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = str(record.get("record_id", "")).strip()
        if record_id:
            index[record_id] = record
    return index


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().casefold().split())


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _abs_tolerance(field: str) -> float:
    if field in {"FE_percent", "EE_percent"}:
        return 0.1
    if field == "potential":
        return 0.01
    return 1e-9


def _rel_tolerance(field: str) -> float:
    if field in {"NH3_yield", "stability"}:
        return 0.01
    return 0.0
