"""Markdown report tables for eNH3-Bench evaluation outputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Render a GitHub-flavored Markdown table."""

    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join("---" for _ in headers) + " |"
    row_lines = [
        "| " + " | ".join(_escape_cell(value) for value in row) + " |"
        for row in rows
    ]
    return "\n".join([header_line, separator_line, *row_lines])


def generate_method_comparison_table(
    evaluation: Mapping[str, Any],
    method_name: str = "rule_baseline",
) -> str:
    """Generate a compact method-level comparison table."""

    categorical_mean = _mean_accuracy(evaluation.get("categorical", {}).values(), "accuracy")
    numeric_mean = _mean_accuracy(
        [
            item
            for item in evaluation.get("numeric", {}).values()
            if int(item.get("total_gold_values", 0)) > 0
        ],
        "accuracy",
    )
    rows = [
        [
            method_name,
            _format_percent(categorical_mean),
            _format_percent(numeric_mean),
            _format_percent(float(evaluation.get("hallucination_rate", 0.0))),
            _format_percent(float(evaluation.get("missing_field_rate", 0.0))),
        ]
    ]
    return markdown_table(
        [
            "Method",
            "Mean categorical accuracy",
            "Mean numeric accuracy",
            "Hallucination rate",
            "Missing field rate",
        ],
        rows,
    )


def generate_field_performance_table(evaluation: Mapping[str, Any]) -> str:
    """Generate field-level categorical and numeric performance table."""

    rows: list[list[Any]] = []
    for field, item in sorted(evaluation.get("categorical", {}).items()):
        rows.append(
            [
                f"`{field}`",
                "categorical",
                _format_percent(float(item.get("accuracy", 0.0))),
                f"{item.get('correct', 0)}/{item.get('total', 0)}",
                item.get("missing_predictions", 0),
                "exact match",
            ]
        )
    for field, item in sorted(evaluation.get("numeric", {}).items()):
        rows.append(
            [
                f"`{field}`",
                "numeric",
                _format_percent(float(item.get("accuracy", 0.0))),
                f"{item.get('within_tolerance', 0)}/{item.get('total_gold_values', 0)}",
                item.get("missing_predictions", 0),
                _format_error_summary(item),
            ]
        )
    return markdown_table(
        ["Field", "Type", "Accuracy", "Support", "Missing predictions", "Criterion"],
        rows,
    )


def generate_error_taxonomy_table(evaluation: Mapping[str, Any]) -> str:
    """Generate a table of observed error categories from evaluation metrics."""

    categorical = evaluation.get("categorical", {})
    numeric = evaluation.get("numeric", {})
    low_categorical = [
        field
        for field, item in sorted(categorical.items())
        if float(item.get("accuracy", 0.0)) < 1.0
    ]
    low_numeric = [
        field
        for field, item in sorted(numeric.items())
        if int(item.get("total_gold_values", 0)) > 0
        and float(item.get("accuracy", 0.0)) < 1.0
    ]
    missing_fields = [
        field
        for field, item in sorted({**categorical, **numeric}.items())
        if int(item.get("missing_predictions", 0)) > 0
    ]
    rows = [
        [
            "Categorical disagreement",
            _field_list(low_categorical),
            "Gold and prediction labels differ after normalization.",
        ],
        [
            "Numeric extraction error",
            _field_list(low_numeric),
            "Predicted numeric values are missing or outside tolerance.",
        ],
        [
            "Unsupported filled field",
            _format_percent(float(evaluation.get("hallucination_rate", 0.0))),
            "Prediction fills fields that are empty in gold.",
        ],
        [
            "Omitted supported field",
            _format_percent(float(evaluation.get("missing_field_rate", 0.0))),
            "Prediction leaves fields empty even though gold contains support.",
        ],
        [
            "Missing prediction entry",
            _field_list(missing_fields),
            "Aligned prediction record or field value is absent.",
        ],
    ]
    return markdown_table(["Error category", "Signal", "Interpretation"], rows)


def generate_reliability_label_summary(evaluation: Mapping[str, Any]) -> str:
    """Generate a focused summary table for reliability label performance."""

    item = evaluation.get("categorical", {}).get("reliability_label", {})
    rows = [
        ["Accuracy", _format_percent(float(item.get("accuracy", 0.0)))],
        ["Correct labels", item.get("correct", 0)],
        ["Total records", item.get("total", 0)],
        ["Missing predictions", item.get("missing_predictions", 0)],
    ]
    return markdown_table(["Reliability-label metric", "Value"], rows)


def generate_main_results_markdown(
    evaluation: Mapping[str, Any],
    method_name: str = "rule_baseline",
) -> str:
    """Generate the main results Markdown artifact for paper tables."""

    return "\n\n".join(
        [
            "# Main Results Tables",
            "## Method Comparison",
            generate_method_comparison_table(evaluation, method_name),
            "## Field Performance",
            generate_field_performance_table(evaluation),
            "## Reliability Label Summary",
            generate_reliability_label_summary(evaluation),
            "",
        ]
    )


def generate_error_taxonomy_markdown(evaluation: Mapping[str, Any]) -> str:
    """Generate the error taxonomy Markdown artifact for paper tables."""

    return "\n\n".join(
        [
            "# Error Taxonomy",
            generate_error_taxonomy_table(evaluation),
            "",
        ]
    )


def _mean_accuracy(items: Sequence[Mapping[str, Any]], key: str) -> float:
    values = [float(item.get(key, 0.0)) for item in items]
    if not values:
        return 0.0
    return sum(values) / len(values)


def _format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _format_error_summary(item: Mapping[str, Any]) -> str:
    mean_error = item.get("mean_absolute_error")
    max_error = item.get("max_absolute_error")
    if mean_error is None and max_error is None:
        return "within tolerance"
    return f"MAE={_format_float(mean_error)}, max={_format_float(max_error)}"


def _format_float(value: Any) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.4g}"


def _field_list(fields: Sequence[str]) -> str:
    if not fields:
        return "none observed"
    return ", ".join(f"`{field}`" for field in fields)


def _escape_cell(value: Any) -> str:
    text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")
