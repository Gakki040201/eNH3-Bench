"""Evaluation metrics for eNH3-Bench predictions."""

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
    "evidence_type",
]

NUMERIC_FIELDS = [
    "faradaic_efficiency_percent",
    "nh3_yield_value",
    "energy_efficiency_percent",
    "stability_hours",
    "potential_value",
]


def exact_match(gold: Mapping[str, Any], pred: Mapping[str, Any], field: str) -> bool:
    """Return whether a field exactly matches after string normalization."""

    return normalized_string_match(gold.get(field), pred.get(field))


def normalized_string_match(a: Any, b: Any) -> bool:
    """Compare two scalar values with whitespace and case normalization."""

    if _is_missing(a) and _is_missing(b):
        return True
    if _is_missing(a) or _is_missing(b):
        return False
    return _normalize_string(a) == _normalize_string(b)


def numeric_within_tolerance(
    gold_value: Any,
    pred_value: Any,
    tolerance_abs: float | None = None,
    tolerance_rel: float | None = None,
) -> bool:
    """Return whether two numeric values match within absolute or relative tolerance."""

    if _is_missing(gold_value) and _is_missing(pred_value):
        return True
    if _is_missing(gold_value) or _is_missing(pred_value):
        return False
    try:
        gold_float = float(gold_value)
        pred_float = float(pred_value)
    except (TypeError, ValueError):
        return False

    abs_tol = 0.0 if tolerance_abs is None else tolerance_abs
    rel_tol = 0.0 if tolerance_rel is None else tolerance_rel
    return isclose(pred_float, gold_float, abs_tol=abs_tol, rel_tol=rel_tol)


def evaluate_categorical_field(
    gold_records: Iterable[Mapping[str, Any]],
    pred_records: Iterable[Mapping[str, Any]],
    field: str,
) -> dict[str, Any]:
    """Evaluate normalized exact-match accuracy for one categorical field."""

    gold_list = list(gold_records)
    pred_by_id = _index_by_evidence_id(pred_records)
    correct = 0
    missing_predictions = 0

    for gold in gold_list:
        pred = pred_by_id.get(str(gold.get("evidence_id", "")))
        if pred is None:
            missing_predictions += 1
            continue
        if exact_match(gold, pred, field):
            correct += 1

    total = len(gold_list)
    return {
        "field": field,
        "total": total,
        "correct": correct,
        "accuracy": _safe_rate(correct, total),
        "missing_predictions": missing_predictions,
    }


def evaluate_numeric_field(
    gold_records: Iterable[Mapping[str, Any]],
    pred_records: Iterable[Mapping[str, Any]],
    field: str,
    tolerance_abs: float | None = None,
    tolerance_rel: float | None = None,
) -> dict[str, Any]:
    """Evaluate tolerance-aware numeric extraction for one field."""

    pred_by_id = _index_by_evidence_id(pred_records)
    total_gold_values = 0
    within_tolerance = 0
    missing_predictions = 0
    absolute_errors: list[float] = []

    for gold in gold_records:
        gold_value = gold.get(field)
        if _is_missing(gold_value):
            continue
        total_gold_values += 1
        pred = pred_by_id.get(str(gold.get("evidence_id", "")))
        pred_value = None if pred is None else pred.get(field)
        if _is_missing(pred_value):
            missing_predictions += 1
            continue
        try:
            error = abs(float(pred_value) - float(gold_value))
        except (TypeError, ValueError):
            missing_predictions += 1
            continue
        absolute_errors.append(error)
        if numeric_within_tolerance(gold_value, pred_value, tolerance_abs, tolerance_rel):
            within_tolerance += 1

    return {
        "field": field,
        "total_gold_values": total_gold_values,
        "within_tolerance": within_tolerance,
        "accuracy": _safe_rate(within_tolerance, total_gold_values),
        "missing_predictions": missing_predictions,
        "mean_absolute_error": mean(absolute_errors) if absolute_errors else None,
        "max_absolute_error": max(absolute_errors) if absolute_errors else None,
    }


def evaluate_all(
    gold_records: Iterable[Mapping[str, Any]],
    pred_records: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate all benchmark categorical and numeric fields."""

    gold_list = list(gold_records)
    pred_list = list(pred_records)
    all_fields = CATEGORICAL_FIELDS + NUMERIC_FIELDS
    return {
        "categorical": {
            field: evaluate_categorical_field(gold_list, pred_list, field)
            for field in CATEGORICAL_FIELDS
        },
        "numeric": {
            field: evaluate_numeric_field(
                gold_list,
                pred_list,
                field,
                tolerance_abs=_default_abs_tolerance(field),
                tolerance_rel=_default_rel_tolerance(field),
            )
            for field in NUMERIC_FIELDS
        },
        "hallucination_rate": hallucination_rate(gold_list, pred_list, all_fields),
        "missing_field_rate": missing_field_rate(gold_list, pred_list, all_fields),
    }


def hallucination_rate(
    gold_records: Iterable[Mapping[str, Any]],
    pred_records: Iterable[Mapping[str, Any]],
    fields: Iterable[str],
) -> float:
    """Return the rate of non-empty predictions where gold is empty."""

    gold_by_id = _index_by_evidence_id(gold_records)
    unsupported = 0
    predicted_values = 0

    for pred in pred_records:
        gold = gold_by_id.get(str(pred.get("evidence_id", "")))
        for field in fields:
            pred_value = pred.get(field)
            if _is_missing(pred_value):
                continue
            predicted_values += 1
            gold_value = None if gold is None else gold.get(field)
            if _is_missing(gold_value):
                unsupported += 1

    return _safe_rate(unsupported, predicted_values)


def missing_field_rate(
    gold_records: Iterable[Mapping[str, Any]],
    pred_records: Iterable[Mapping[str, Any]],
    fields: Iterable[str],
) -> float:
    """Return the rate of gold-supported fields missing from predictions."""

    pred_by_id = _index_by_evidence_id(pred_records)
    missing = 0
    gold_values = 0

    for gold in gold_records:
        pred = pred_by_id.get(str(gold.get("evidence_id", "")))
        for field in fields:
            gold_value = gold.get(field)
            if _is_missing(gold_value):
                continue
            gold_values += 1
            pred_value = None if pred is None else pred.get(field)
            if _is_missing(pred_value):
                missing += 1

    return _safe_rate(missing, gold_values)


def _index_by_evidence_id(records: Iterable[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    for record in records:
        evidence_id = str(record.get("evidence_id", "")).strip()
        if evidence_id:
            index[evidence_id] = record
    return index


def _normalize_string(value: Any) -> str:
    return " ".join(str(value).strip().casefold().split())


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _default_abs_tolerance(field: str) -> float:
    if field == "potential_value":
        return 0.01
    if field in {"faradaic_efficiency_percent", "energy_efficiency_percent"}:
        return 0.1
    return 1e-9


def _default_rel_tolerance(field: str) -> float:
    if field in {"nh3_yield_value", "stability_hours"}:
        return 0.01
    return 0.0
