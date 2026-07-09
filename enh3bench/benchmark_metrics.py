"""Baseline metrics for eNH3-BoundaryBench."""

from __future__ import annotations

from collections import Counter
import json
from typing import Any

from enh3bench.benchmark_schema import (
    BENCHMARK_TASKS,
    BOUNDARY_LABELS,
    HIDDEN_TAX_LABELS,
    REQUIRED_CONTROL_LABELS,
    SOURCE_SPAN_LABELS,
    VALIDATION_GATE_FIELDS,
    VALIDATION_GATE_LABELS,
    normalize_multi_label,
)


BOUNDARY_RANK = {
    "unsupported_or_secondary": 0,
    "product_admissibility": 1,
    "cell_metric": 2,
    "reactor_legibility": 3,
    "process_partial": 4,
    "plant_facing_insufficient": 5,
}


def accuracy(y_true: list[Any], y_pred: list[Any]) -> float:
    """Compute accuracy safely."""

    if not y_true:
        return 0.0
    total = min(len(y_true), len(y_pred))
    if total <= 0:
        return 0.0
    return round(sum(1 for left, right in zip(y_true[:total], y_pred[:total]) if left == right) / total, 6)


def macro_f1(y_true: list[Any], y_pred: list[Any], labels: list[Any] | tuple[Any, ...] | None = None) -> float:
    """Compute macro F1, including labels absent from predictions."""

    if labels is None:
        labels = sorted({*map(str, y_true), *map(str, y_pred)})
    if not labels:
        return 0.0
    scores = [precision_recall_f1_for_label(y_true, y_pred, label)["f1"] for label in labels]
    return round(sum(scores) / len(scores), 6) if scores else 0.0


def precision_recall_f1_for_label(y_true: list[Any], y_pred: list[Any], label: Any) -> dict[str, float]:
    """Compute binary precision/recall/F1 for one label."""

    label = str(label)
    true = [str(item) for item in y_true]
    pred = [str(item) for item in y_pred]
    tp = sum(1 for left, right in zip(true, pred) if left == label and right == label)
    fp = sum(1 for left, right in zip(true, pred) if left != label and right == label)
    fn = sum(1 for left, right in zip(true, pred) if left == label and right != label)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 6), "recall": round(recall, 6), "f1": round(f1, 6)}


def multilabel_exact_match(y_true_lists: list[Any], y_pred_lists: list[Any]) -> float:
    """Compute exact set-match rate for multilabel rows."""

    if not y_true_lists:
        return 0.0
    total = min(len(y_true_lists), len(y_pred_lists))
    if total <= 0:
        return 0.0
    matches = 0
    for true, pred in zip(y_true_lists[:total], y_pred_lists[:total]):
        matches += int(_label_set(true) == _label_set(pred))
    return round(matches / total, 6)


def multilabel_jaccard_mean(y_true_lists: list[Any], y_pred_lists: list[Any]) -> float:
    """Compute mean multilabel Jaccard, treating empty-empty as 1.0."""

    if not y_true_lists:
        return 0.0
    total = min(len(y_true_lists), len(y_pred_lists))
    if total <= 0:
        return 0.0
    scores: list[float] = []
    for true, pred in zip(y_true_lists[:total], y_pred_lists[:total]):
        true_set = _label_set(true)
        pred_set = _label_set(pred)
        if not true_set and not pred_set:
            scores.append(1.0)
            continue
        union = true_set | pred_set
        scores.append(len(true_set & pred_set) / len(union) if union else 0.0)
    return round(sum(scores) / len(scores), 6)


def boundary_overclaim_underclaim(y_pred: str, y_true: str) -> dict[str, Any]:
    """Detect whether predicted boundary is more or less permissive than gold."""

    pred_rank = BOUNDARY_RANK.get(str(y_pred or "unsupported_or_secondary"), 0)
    true_rank = BOUNDARY_RANK.get(str(y_true or "unsupported_or_secondary"), 0)
    return {
        "pred_rank": pred_rank,
        "true_rank": true_rank,
        "overclaim": pred_rank > true_rank,
        "underclaim": pred_rank < true_rank,
    }


def evaluate_rule_baseline_for_task(task_name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate rule-derived fields against gold task labels."""

    if task_name == "source_span_classification":
        return _evaluate_single_label(
            task_name,
            records,
            [record.get("gold_text_class") for record in records],
            [record.get("rule_text_class") for record in records],
            SOURCE_SPAN_LABELS,
            "rule",
        )
    if task_name == "validation_gate_extraction":
        return _evaluate_validation_gates(records, "rule")
    if task_name == "claim_rights_boundary_classification":
        return _evaluate_boundary(records, "rule", "rule_maximum_supported_boundary")
    if task_name == "hidden_tax_detection":
        return _evaluate_multilabel(records, "rule", "gold_hidden_tax", "detected_taxes", HIDDEN_TAX_LABELS)
    if task_name == "required_control_prediction":
        result = _evaluate_multilabel(records, "rule", "gold_required_controls", "required_controls", REQUIRED_CONTROL_LABELS)
        result.update(_key_control_recalls(records, "required_controls"))
        return result
    if task_name == "experiment_decision_ranking":
        gold = [_int(record.get("gold_priority_binary")) for record in records]
        pred = [_rule_priority(record) for record in records]
        metrics = precision_recall_f1_for_label(gold, pred, 1)
        return {
            "task_name": task_name,
            "baseline": "rule",
            "records_evaluated": len(records),
            "accuracy": accuracy(gold, pred),
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
        }
    return {"task_name": task_name, "baseline": "rule", "records_evaluated": 0}


def evaluate_llm_baseline_for_task(task_name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate optional LLM-derived fields when present."""

    if task_name == "source_span_classification":
        selected = [record for record in records if str(record.get("llm_text_class") or "").strip()]
        return _evaluate_single_label(
            task_name,
            selected,
            [record.get("gold_text_class") for record in selected],
            [record.get("llm_text_class") for record in selected],
            SOURCE_SPAN_LABELS,
            "llm",
        )
    if task_name == "claim_rights_boundary_classification":
        selected = [record for record in records if str(record.get("llm_maximum_supported_boundary") or "").strip()]
        return _evaluate_boundary(selected, "llm", "llm_maximum_supported_boundary")
    if task_name == "hidden_tax_detection":
        selected = [record for record in records if normalize_multi_label(record.get("llm_hidden_tax"))]
        return _evaluate_multilabel(selected, "llm", "gold_hidden_tax", "llm_hidden_tax", HIDDEN_TAX_LABELS)
    if task_name == "required_control_prediction":
        selected = [record for record in records if normalize_multi_label(record.get("llm_required_controls"))]
        result = _evaluate_multilabel(selected, "llm", "gold_required_controls", "llm_required_controls", REQUIRED_CONTROL_LABELS)
        result.update(_key_control_recalls(selected, "llm_required_controls"))
        return result
    if task_name == "experiment_decision_ranking":
        selected = [record for record in records if str(record.get("llm_maximum_supported_boundary") or "").strip()]
        gold = [_int(record.get("gold_priority_binary")) for record in selected]
        pred = [_llm_priority(record) for record in selected]
        metrics = precision_recall_f1_for_label(gold, pred, 1)
        return {
            "task_name": task_name,
            "baseline": "llm",
            "records_evaluated": len(selected),
            "accuracy": accuracy(gold, pred),
            "precision": metrics["precision"],
            "recall": metrics["recall"],
            "f1": metrics["f1"],
        }
    return {"task_name": task_name, "baseline": "llm", "records_evaluated": 0}


def evaluate_all_tasks(tasks: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, dict[str, Any]]]:
    """Evaluate rule and LLM baselines for all known tasks."""

    results: dict[str, dict[str, dict[str, Any]]] = {}
    for task_name in BENCHMARK_TASKS:
        records = tasks.get(task_name, [])
        results[task_name] = {
            "rule": evaluate_rule_baseline_for_task(task_name, records),
            "llm": evaluate_llm_baseline_for_task(task_name, records),
        }
    return results


def _evaluate_single_label(
    task_name: str,
    records: list[dict[str, Any]],
    gold: list[Any],
    pred: list[Any],
    labels: tuple[str, ...],
    baseline: str,
) -> dict[str, Any]:
    return {
        "task_name": task_name,
        "baseline": baseline,
        "records_evaluated": len(records),
        "accuracy": accuracy([str(item or "") for item in gold], [str(item or "") for item in pred]),
        "macro_f1": macro_f1([str(item or "") for item in gold], [str(item or "") for item in pred], labels),
    }


def _evaluate_validation_gates(records: list[dict[str, Any]], baseline: str) -> dict[str, Any]:
    field_metrics: dict[str, Any] = {
        "task_name": "validation_gate_extraction",
        "baseline": baseline,
        "records_evaluated": len(records),
    }
    accuracies: list[float] = []
    f1_scores: list[float] = []
    for field in VALIDATION_GATE_FIELDS:
        output_field = f"gold_{field}"
        pred_field = f"rule_validation_{field}"
        gold = [str(record.get(output_field) or "") for record in records]
        pred = [_validation_prediction(record, pred_field, field) for record in records]
        field_accuracy = accuracy(gold, pred)
        field_f1 = macro_f1(gold, pred, VALIDATION_GATE_LABELS)
        field_metrics[f"{field}_accuracy"] = field_accuracy
        field_metrics[f"{field}_macro_f1"] = field_f1
        accuracies.append(field_accuracy)
        f1_scores.append(field_f1)
    field_metrics["accuracy"] = round(sum(accuracies) / len(accuracies), 6) if accuracies else 0.0
    field_metrics["macro_f1"] = round(sum(f1_scores) / len(f1_scores), 6) if f1_scores else 0.0
    return field_metrics


def _evaluate_boundary(records: list[dict[str, Any]], baseline: str, pred_field: str) -> dict[str, Any]:
    gold = [str(record.get("gold_maximum_supported_boundary") or "") for record in records]
    pred = [str(record.get(pred_field) or "") for record in records]
    overclaims = 0
    underclaims = 0
    for predicted, true in zip(pred, gold):
        comparison = boundary_overclaim_underclaim(predicted, true)
        overclaims += int(comparison["overclaim"])
        underclaims += int(comparison["underclaim"])
    total = len(records)
    return {
        "task_name": "claim_rights_boundary_classification",
        "baseline": baseline,
        "records_evaluated": total,
        "accuracy": accuracy(gold, pred),
        "macro_f1": macro_f1(gold, pred, BOUNDARY_LABELS),
        "overclaim_rate": round(overclaims / total, 6) if total else 0.0,
        "underclaim_rate": round(underclaims / total, 6) if total else 0.0,
    }


def _evaluate_multilabel(
    records: list[dict[str, Any]],
    baseline: str,
    gold_field: str,
    pred_field: str,
    labels: tuple[str, ...],
) -> dict[str, Any]:
    gold = [normalize_multi_label(record.get(gold_field)) for record in records]
    pred = [normalize_multi_label(record.get(pred_field)) for record in records]
    metrics: dict[str, Any] = {
        "task_name": _task_name_for_multilabel(gold_field),
        "baseline": baseline,
        "records_evaluated": len(records),
        "exact_match": multilabel_exact_match(gold, pred),
        "jaccard_mean": multilabel_jaccard_mean(gold, pred),
    }
    for label in labels:
        true_binary = [label in row for row in gold]
        pred_binary = [label in row for row in pred]
        label_metrics = precision_recall_f1_for_label(true_binary, pred_binary, True)
        safe = label.replace("/", "_").replace(" ", "_").replace("-", "_")
        metrics[f"{safe}_precision"] = label_metrics["precision"]
        metrics[f"{safe}_recall"] = label_metrics["recall"]
        metrics[f"{safe}_f1"] = label_metrics["f1"]
    return metrics


def _task_name_for_multilabel(gold_field: str) -> str:
    if gold_field == "gold_hidden_tax":
        return "hidden_tax_detection"
    return "required_control_prediction"


def _key_control_recalls(records: list[dict[str, Any]], pred_field: str) -> dict[str, float]:
    keys = {
        "15N": ("15n", "isotope"),
        "blank": ("blank",),
        "NOx": ("nox", "nitrate", "nitrite"),
        "HOR_off": ("hor", "h2-off", "hydrogen"),
        "gas_liquid_accounting": ("gas/liquid", "gas-liquid", "accounting"),
    }
    output: dict[str, float] = {}
    gold_rows = [normalize_multi_label(record.get("gold_required_controls")) for record in records]
    pred_rows = [normalize_multi_label(record.get(pred_field)) for record in records]
    for label, needles in keys.items():
        denominator = 0
        hits = 0
        for gold, pred in zip(gold_rows, pred_rows):
            if _contains_any(gold, needles):
                denominator += 1
                hits += int(_contains_any(pred, needles))
        output[f"{label}_recall"] = round(hits / denominator, 6) if denominator else 0.0
    return output


def _validation_prediction(record: dict[str, Any], pred_field: str, gate_field: str) -> str:
    direct = str(record.get(pred_field) or "").strip()
    if direct:
        return direct
    validation = record.get("validation_gates")
    if isinstance(validation, str):
        try:
            validation = json.loads(validation)
        except json.JSONDecodeError:
            validation = {}
    if isinstance(validation, dict):
        value = validation.get(gate_field)
        if value is None and gate_field == "NOx_control":
            value = validation.get("nox_control")
        return _normalize_gate_value(value)
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


def _rule_priority(record: dict[str, Any]) -> int:
    boundary = str(record.get("rule_maximum_supported_boundary") or "")
    if boundary in {"reactor_legibility", "process_partial"}:
        return 1
    if normalize_multi_label(record.get("overclaim_risk_flags")):
        return 1
    if normalize_multi_label(record.get("required_controls")):
        return 1
    return 0


def _llm_priority(record: dict[str, Any]) -> int:
    boundary = str(record.get("llm_maximum_supported_boundary") or "")
    if boundary in {"reactor_legibility", "process_partial"}:
        return 1
    if str(record.get("needs_human_review") or "").casefold() in {"true", "1", "yes"} or record.get("needs_human_review") is True:
        return 1
    return 0


def _label_set(value: Any) -> set[str]:
    return {str(item) for item in normalize_multi_label(value)}


def _contains_any(values: list[str], needles: tuple[str, ...]) -> bool:
    lowered = [str(value).casefold() for value in values]
    return any(any(needle in value for needle in needles) for value in lowered)


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def flatten_metrics(results: dict[str, dict[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    """Flatten evaluate_all_tasks output for CSV export."""

    rows: list[dict[str, Any]] = []
    for task_name, baselines in results.items():
        for baseline, metrics in baselines.items():
            row = {"task_name": task_name, "baseline": baseline}
            row.update(metrics)
            rows.append(row)
    return rows


def metric_summary_counts(tasks: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Return compact counts for reports."""

    return {
        "tasks": {task_name: len(records) for task_name, records in tasks.items()},
        "reviewed_records": max((len(records) for records in tasks.values()), default=0),
        "llm_rows": sum(1 for records in tasks.values() for record in records if record.get("llm_model")),
        "needs_human_review_rows": sum(1 for records in tasks.values() for record in records if record.get("needs_human_review")),
        "task_names": list(tasks),
    }
