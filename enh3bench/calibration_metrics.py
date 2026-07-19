"""Human-review completeness, agreement, and calibration metric framework."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable

from enh3bench.calibration_schema import (
    HUMAN_FIELDS_BY_TYPE,
    LABEL_FIELDS_BY_TYPE,
    NOTE_FIELD_BY_TYPE,
    validate_review_row,
)


CORRECTNESS_FIELD_MAPPINGS = {
    "human_document_genre_correct": ["document_genre"],
    "human_document_family_correct": ["document_reaction_family"],
    "human_effective_family_correct": ["effective_reaction_family"],
    "human_claim_ownership_correct": ["claim_ownership"],
    "human_claim_type_correct": ["semantic_claim_type"],
    "human_primary_eligibility_correct": ["primary_semantic_eligibility"],
    "human_quantification_correct": ["ammonia_quantification_signal", "semantic_claim_type"],
    "human_validation_gate_correct": ["validation_gate_decisions"],
    "human_paper_status_correct": ["paper_admissibility_status"],
    "human_link_relevant": ["evidence_link_id", "target_span_id", "evidence_span_id"],
    "human_link_role_correct": ["link_role", "link_roles"],
}

CALIBRATION_METRIC_SCHEMA_VERSION = "0.16-calibration-metrics.1"


def summarize_reviews(rows_by_type: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Summarize blank or completed review sheets without inventing unavailable metrics."""

    validation_errors: list[str] = []
    distributions: Counter[str] = Counter()
    field_distributions: dict[str, Counter[str]] = defaultdict(Counter)
    stratum_totals: Counter[str] = Counter()
    stratum_errors: Counter[str] = Counter()
    total_rows = completed_rows = 0
    nonempty_labels = 0
    all_rows: list[tuple[str, dict[str, Any]]] = []
    unique_items: set[tuple[str, str]] = set()
    reviewed_items: set[tuple[str, str]] = set()
    rows_per_reviewer: Counter[str] = Counter()
    completed_rows_per_reviewer: Counter[str] = Counter()
    for item_type, rows in rows_by_type.items():
        if item_type not in HUMAN_FIELDS_BY_TYPE:
            validation_errors.append(f"unknown_item_type:{item_type}")
            continue
        for index, row in enumerate(rows, 2):
            all_rows.append((item_type, row))
            total_rows += 1
            errors = validate_review_row(item_type, row)
            validation_errors.extend(f"{item_type}:row_{index}:{error}" for error in errors)
            status = str(row.get("review_status") or "").strip()
            item_id = str(row.get("calibration_item_id") or "").strip()
            reviewer_id = str(row.get("reviewer_id") or "").strip()
            if item_id:
                unique_items.add((item_type, item_id))
            if reviewer_id:
                rows_per_reviewer[reviewer_id] += 1
            if status == "completed":
                completed_rows += 1
                if item_id:
                    reviewed_items.add((item_type, item_id))
                if reviewer_id:
                    completed_rows_per_reviewer[reviewer_id] += 1
            labels = [str(row.get(field) or "").strip() for field in LABEL_FIELDS_BY_TYPE[item_type]]
            for value in labels:
                if value:
                    distributions[value] += 1
                    nonempty_labels += 1
            for field in LABEL_FIELDS_BY_TYPE[item_type]:
                value = str(row.get(field) or "").strip()
                if value:
                    field_distributions[field][value] += 1
            stratum = str(row.get("assigned_primary_stratum") or row.get("assigned_sampling_stratum") or "<missing>")
            stratum_totals[stratum] += sum(value in {"yes", "no"} for value in labels)
            stratum_errors[stratum] += sum(value == "no" for value in labels)
    agreement = reviewer_agreement(all_rows)
    validation_errors.extend(agreement.get("validation_errors", []))
    binary = _correctness_metrics(distributions)
    denominator = nonempty_labels
    row_completeness = {
        "total_review_rows": total_rows,
        "completed_review_rows": completed_rows,
        "incomplete_review_rows": max(0, total_rows - completed_rows),
        "completion_rate": _rate(completed_rows, total_rows),
    }
    item_coverage = {
        "total_unique_items": len(unique_items),
        "reviewed_unique_items": len(reviewed_items),
        "missing_unique_items": max(0, len(unique_items) - len(reviewed_items)),
        "coverage_rate": _rate(len(reviewed_items), len(unique_items)),
    }
    reviewer_coverage = {
        "reviewer_count": len(rows_per_reviewer),
        "rows_per_reviewer": dict(sorted(rows_per_reviewer.items())),
        "completed_rows_per_reviewer": dict(sorted(completed_rows_per_reviewer.items())),
    }
    return {
        "metric_schema_version": CALIBRATION_METRIC_SCHEMA_VERSION,
        "metric_semantics": {
            "correctness_metrics": "human yes/no evaluates whether an automatic assertion is correct",
            "class_label_metrics": "requires adjudicated corrected class labels and is not inferred from yes/no correctness",
        },
        "correctness_field_mappings": CORRECTNESS_FIELD_MAPPINGS,
        "row_completeness": row_completeness,
        "item_coverage": item_coverage,
        "reviewer_coverage": reviewer_coverage,
        "completeness": {**row_completeness, "nonempty_label_count": nonempty_labels},
        "label_distribution": dict(sorted(distributions.items())),
        "label_distribution_by_field": {
            field: dict(sorted(values.items())) for field, values in sorted(field_distributions.items())
        },
        "uncertain_rate": _rate(distributions["uncertain"], denominator),
        "not_applicable_rate": _rate(distributions["not_applicable"], denominator),
        "reviewer_agreement": agreement,
        "correctness_metrics": binary,
        "auto_vs_human_confusion_counts": {
            "automatic_assertion_correct": distributions["yes"],
            "automatic_assertion_incorrect": distributions["no"],
            "uncertain": distributions["uncertain"],
            "not_applicable": distributions["not_applicable"],
        },
        "class_label_metrics": {
            "status": "not_available",
            "precision": None,
            "recall": None,
            "macro_f1": None,
            "reason": "corrected class labels are unavailable; correctness labels are not class labels",
        },
        "per_stratum_error_rate": {
            key: _rate(stratum_errors[key], stratum_totals[key]) for key in sorted(stratum_totals)
        },
        "validation_errors": validation_errors,
        "status": "not_available" if nonempty_labels == 0 else ("invalid" if validation_errors else "available"),
        "missing_reviewed_records": item_coverage["missing_unique_items"],
    }


def reviewer_agreement(rows: Iterable[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """Compute agreement for the Phase A maximum of two reviewers per item and field."""

    grouped: dict[tuple[str, str, str], list[tuple[str, str]]] = defaultdict(list)
    for item_type, row in rows:
        item_id = str(row.get("calibration_item_id") or "")
        reviewer = str(row.get("reviewer_id") or "").strip()
        if not item_id or not reviewer:
            continue
        for field in LABEL_FIELDS_BY_TYPE[item_type]:
            label = str(row.get(field) or "").strip()
            if label:
                grouped[(item_type, item_id, field)].append((reviewer, label))
    pairs: list[tuple[str, str]] = []
    reviewer_limit_errors: list[str] = []
    for (item_type, item_id, field), values in grouped.items():
        unique_by_reviewer = dict(values)
        reviewers = sorted(unique_by_reviewer)
        if len(reviewers) > 2:
            reviewer_limit_errors.append(
                f"reviewer_count_exceeds_phase_a_limit:{item_type}:{item_id}:{field}:{len(reviewers)}"
            )
        elif len(reviewers) == 2:
            pairs.append((unique_by_reviewer[reviewers[0]], unique_by_reviewer[reviewers[1]]))
    if reviewer_limit_errors:
        return {
            "status": "invalid", "paired_label_count": 0,
            "observed_agreement": None, "cohen_kappa": None,
            "reason": "Phase A supports at most two reviewers per item and review field",
            "validation_errors": sorted(reviewer_limit_errors),
        }
    if not pairs:
        return {
            "status": "not_available", "paired_label_count": 0,
            "observed_agreement": None, "cohen_kappa": None,
            "reason": "at least two reviewers on the same item and field are required",
            "validation_errors": [],
        }
    observed = sum(left == right for left, right in pairs) / len(pairs)
    left_counts = Counter(left for left, _ in pairs)
    right_counts = Counter(right for _, right in pairs)
    labels = set(left_counts) | set(right_counts)
    expected = sum((left_counts[label] / len(pairs)) * (right_counts[label] / len(pairs)) for label in labels)
    kappa = None if expected == 1.0 else (observed - expected) / (1.0 - expected)
    return {
        "status": "available" if kappa is not None else "not_available",
        "paired_label_count": len(pairs),
        "observed_agreement": round(observed, 6),
        "cohen_kappa": None if kappa is None else round(kappa, 6),
        "reason": None if kappa is not None else "kappa is undefined when expected agreement is one",
        "validation_errors": [],
    }


def classification_metrics(pairs: Iterable[tuple[str, str]]) -> dict[str, Any]:
    """Compute per-class precision/recall/F1 and macro-F1 from predicted/corrected labels."""

    values = [(str(predicted), str(actual)) for predicted, actual in pairs if str(predicted) and str(actual)]
    if not values:
        return {"status": "not_available", "count": 0, "confusion_counts": {}, "per_class": {}, "macro_f1": None}
    labels = sorted({label for pair in values for label in pair})
    confusion = Counter(values)
    per_class: dict[str, dict[str, Any]] = {}
    for label in labels:
        tp = confusion[(label, label)]
        fp = sum(count for (predicted, actual), count in confusion.items() if predicted == label and actual != label)
        fn = sum(count for (predicted, actual), count in confusion.items() if predicted != label and actual == label)
        precision = _rate(tp, tp + fp)
        recall = _rate(tp, tp + fn)
        f1 = None if precision is None or recall is None or precision + recall == 0 else round(2 * precision * recall / (precision + recall), 6)
        per_class[label] = {"precision": precision, "recall": recall, "f1": f1, "support": tp + fn}
    f1_values = [value["f1"] for value in per_class.values() if value["f1"] is not None]
    return {
        "status": "available", "count": len(values),
        "confusion_counts": {f"{predicted} -> {actual}": count for (predicted, actual), count in sorted(confusion.items())},
        "per_class": per_class,
        "macro_f1": round(sum(f1_values) / len(f1_values), 6) if f1_values else None,
    }


def empty_metrics_template(expected_counts: dict[str, int]) -> dict[str, Any]:
    rows = {item_type: [{"calibration_item_id": f"blank-{index}"} for index in range(count)] for item_type, count in expected_counts.items()}
    summary = summarize_reviews(rows)
    summary["expected_item_counts"] = expected_counts
    return summary


def _correctness_metrics(distribution: Counter[str]) -> dict[str, Any]:
    evaluated = distribution["yes"] + distribution["no"]
    if evaluated == 0:
        return {
            "status": "not_available", "evaluated_assertions": 0, "correctness_rate": None,
            "precision": None, "recall": None, "macro_f1": None,
            "reason": "no yes/no human correctness labels are available",
        }
    correctness = _rate(distribution["yes"], evaluated)
    return {
        "status": "available", "evaluated_assertions": evaluated,
        "correctness_rate": correctness,
        "precision": correctness,
        "recall": None,
        "macro_f1": None,
        "reason": "precision denotes correctness of asserted automatic labels; recall and macro-F1 require corrected class labels",
    }


def _rate(numerator: int | float, denominator: int | float) -> float | None:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 6)
