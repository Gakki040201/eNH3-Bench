"""Calibration metrics for human-reviewed BoundaryLedger audit records."""

from __future__ import annotations

from collections import Counter
import csv
import json
from pathlib import Path
from typing import Any

from enh3bench.audit_schema import is_reviewed_record, normalize_list_field, validate_human_label_record
from enh3bench.boundary_schema import boundary_rank
from enh3bench.ledger_router import load_jsonl


def load_reviewed_audit_records(run_name: str, base_dir: str | Path = "data/human_audit") -> list[dict[str, Any]]:
    """Load validated reviewed audit records."""

    return load_jsonl(Path(base_dir) / run_name / "reviewed_audit_records.jsonl")


def boundary_overclaim_underclaim(rule_boundary: str, human_boundary: str) -> dict[str, Any]:
    """Compare rule and human boundary ranks."""

    rule_rank = boundary_rank(str(rule_boundary or "unsupported_or_secondary"))
    human_rank = boundary_rank(str(human_boundary or "unsupported_or_secondary"))
    return {
        "rule_rank": rule_rank,
        "human_rank": human_rank,
        "overclaim": rule_rank > human_rank,
        "underclaim": rule_rank < human_rank,
    }


def compute_rule_human_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute rule BoundaryLedger agreement against human labels."""

    reviewed = _reviewed_records(records)
    total = len(reviewed)
    boundary_correct = 0
    text_correct = 0
    admissibility_correct = 0
    overclaims = 0
    underclaims = 0
    exact_matches = 0

    for record in reviewed:
        boundary_match = str(record.get("maximum_supported_boundary") or "") == str(
            record.get("human_maximum_supported_boundary") or ""
        )
        text_match = str(record.get("text_class") or "") == str(record.get("human_text_class") or "")
        status_match = str(record.get("admissibility_status") or "") == str(record.get("human_admissibility_status") or "")
        comparison = boundary_overclaim_underclaim(
            str(record.get("maximum_supported_boundary") or ""),
            str(record.get("human_maximum_supported_boundary") or ""),
        )

        boundary_correct += int(boundary_match)
        text_correct += int(text_match)
        admissibility_correct += int(status_match)
        overclaims += int(comparison["overclaim"])
        underclaims += int(comparison["underclaim"])
        exact_matches += int(boundary_match and text_match and status_match)

    return {
        "reviewed_records": total,
        "rule_boundary_accuracy": _rate(boundary_correct, total),
        "rule_text_class_accuracy": _rate(text_correct, total),
        "rule_admissibility_accuracy": _rate(admissibility_correct, total),
        "rule_boundary_overclaim_rate": _rate(overclaims, total),
        "rule_boundary_underclaim_rate": _rate(underclaims, total),
        "rule_exact_match_count": exact_matches,
        "rule_needs_revision_count": total - exact_matches,
    }


def compute_llm_human_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute optional LLM verification agreement against human labels."""

    reviewed = _reviewed_records(records)
    llm_records = [record for record in reviewed if str(record.get("llm_maximum_supported_boundary") or "").strip()]
    total = len(llm_records)
    boundary_correct = 0
    text_total = 0
    text_correct = 0
    overclaims = 0
    underclaims = 0
    parse_errors = 0

    for record in llm_records:
        human_boundary = str(record.get("human_maximum_supported_boundary") or "")
        llm_boundary = str(record.get("llm_maximum_supported_boundary") or "")
        boundary_correct += int(llm_boundary == human_boundary)
        comparison = boundary_overclaim_underclaim(llm_boundary, human_boundary)
        overclaims += int(comparison["overclaim"])
        underclaims += int(comparison["underclaim"])
        parse_errors += int(bool(record.get("llm_parse_error")))
        llm_text_class = _llm_text_class(record)
        if llm_text_class:
            text_total += 1
            text_correct += int(llm_text_class == str(record.get("human_text_class") or ""))

    return {
        "llm_records_available": total,
        "llm_boundary_accuracy": _rate(boundary_correct, total),
        "llm_text_class_accuracy": _rate(text_correct, text_total),
        "llm_boundary_overclaim_rate": _rate(overclaims, total),
        "llm_boundary_underclaim_rate": _rate(underclaims, total),
        "llm_more_permissive_than_human_count": overclaims,
        "llm_more_conservative_than_human_count": underclaims,
        "llm_parse_error_count": parse_errors,
    }


def compute_required_control_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute required-control agreement and targeted recall."""

    reviewed = _reviewed_records(records)
    total = len(reviewed)
    exact = 0
    recall_hits = {"15N": 0, "blank": 0, "NOx": 0}
    recall_denominators = {"15N": 0, "blank": 0, "NOx": 0}

    for record in reviewed:
        rule_controls = _normalized_set(record.get("required_controls"))
        human_controls = _normalized_set(record.get("human_required_controls"))
        exact += int(rule_controls == human_controls)
        for label, needles in {
            "15N": ("15n", "isotope"),
            "blank": ("blank",),
            "NOx": ("nox", "nitrate", "nitrite"),
        }.items():
            human_has = _contains_any(human_controls, needles)
            if human_has:
                recall_denominators[label] += 1
                recall_hits[label] += int(_contains_any(rule_controls, needles))

    return {
        "required_control_exact_match_rate": _rate(exact, total),
        "missing_15N_control_recall": _rate(recall_hits["15N"], recall_denominators["15N"]),
        "missing_blank_control_recall": _rate(recall_hits["blank"], recall_denominators["blank"]),
        "missing_NOx_control_recall": _rate(recall_hits["NOx"], recall_denominators["NOx"]),
    }


def compute_hidden_tax_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute hidden-tax agreement metrics."""

    reviewed = _reviewed_records(records)
    total = len(reviewed)
    exact = 0
    jaccard_sum = 0.0
    rule_counts: Counter[str] = Counter()
    human_counts: Counter[str] = Counter()

    for record in reviewed:
        rule_taxes = _tax_set(record)
        human_taxes = _normalized_set(record.get("human_hidden_tax"))
        rule_counts.update(rule_taxes)
        human_counts.update(human_taxes)
        exact += int(rule_taxes == human_taxes)
        jaccard_sum += _jaccard(rule_taxes, human_taxes)

    return {
        "hidden_tax_exact_match_rate": _rate(exact, total),
        "hidden_tax_jaccard_mean": _rate(jaccard_sum, total),
        "tax_type_counts_rule": dict(sorted(rule_counts.items())),
        "tax_type_counts_human": dict(sorted(human_counts.items())),
    }


def export_calibration_outputs(
    records: list[dict[str, Any]],
    run_name: str,
    output_dir: str | Path = "data/calibration",
) -> dict[str, Any]:
    """Export calibration CSVs and return metric payloads."""

    reviewed = _reviewed_records(records)
    run_dir = Path(output_dir) / run_name
    metrics = {
        "rule_human": compute_rule_human_metrics(reviewed),
        "llm_human": compute_llm_human_metrics(reviewed),
        "required_controls": compute_required_control_metrics(reviewed),
        "hidden_tax": compute_hidden_tax_metrics(reviewed),
        "human_review_requirements": _review_requirement_metrics(reviewed),
    }
    revision_records = _records_for_rule_revision(reviewed)
    metrics["revision_examples"] = revision_records[:10]

    paths = {
        "boundary_calibration_metrics_csv": str(run_dir / "boundary_calibration_metrics.csv"),
        "boundary_confusion_matrix_csv": str(run_dir / "boundary_confusion_matrix.csv"),
        "text_class_confusion_matrix_csv": str(run_dir / "text_class_confusion_matrix.csv"),
        "required_control_metrics_csv": str(run_dir / "required_control_metrics.csv"),
        "hidden_tax_metrics_csv": str(run_dir / "hidden_tax_metrics.csv"),
        "records_for_rule_revision_csv": str(run_dir / "records_for_rule_revision.csv"),
    }

    _write_key_value_csv(
        metrics["rule_human"] | metrics["llm_human"] | metrics["human_review_requirements"],
        Path(paths["boundary_calibration_metrics_csv"]),
    )
    _write_rows(_confusion_rows(reviewed, "maximum_supported_boundary", "human_maximum_supported_boundary", "rule_boundary", "human_boundary"), Path(paths["boundary_confusion_matrix_csv"]))
    _write_rows(_confusion_rows(reviewed, "text_class", "human_text_class", "rule_text_class", "human_text_class"), Path(paths["text_class_confusion_matrix_csv"]))
    _write_key_value_csv(metrics["required_controls"], Path(paths["required_control_metrics_csv"]))
    _write_key_value_csv(metrics["hidden_tax"], Path(paths["hidden_tax_metrics_csv"]))
    _write_rows(revision_records, Path(paths["records_for_rule_revision_csv"]))

    return {"run_name": run_name, "reviewed_records": len(reviewed), "metrics": metrics, "paths": paths}


def export_calibration_report(
    metrics: dict[str, Any],
    run_name: str,
    output_dir: str | Path = "data/reports",
) -> str:
    """Write a Markdown calibration report."""

    output_path = Path(output_dir) / f"calibration_report.{run_name}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rule = metrics.get("rule_human", {})
    llm = metrics.get("llm_human", {})
    controls = metrics.get("required_controls", {})
    taxes = metrics.get("hidden_tax", {})
    review = metrics.get("human_review_requirements", {})
    examples = metrics.get("revision_examples") or []

    lines = [
        f"# Calibration Report: {run_name}",
        "",
        "## 1. Reviewed record count",
        "",
        f"- Reviewed records: {rule.get('reviewed_records', 0)}",
        f"- Rule review required: {review.get('rule_review_count', 0)}",
        f"- LLM review required: {review.get('llm_review_count', 0)}",
        f"- Overall review required: {review.get('overall_review_count', 0)}",
        f"- Rule-only review: {review.get('rule_only_review_count', 0)}",
        f"- LLM-only review: {review.get('llm_only_review_count', 0)}",
        f"- Priority bands: {json.dumps(review.get('review_priority_band_counts', {}), ensure_ascii=True, sort_keys=True)}",
        "",
        "## 2. Rule vs human boundary metrics",
        "",
        f"- Boundary accuracy: {rule.get('rule_boundary_accuracy', 0)}",
        f"- Text-class accuracy: {rule.get('rule_text_class_accuracy', 0)}",
        f"- Admissibility accuracy: {rule.get('rule_admissibility_accuracy', 0)}",
        f"- Exact match count: {rule.get('rule_exact_match_count', 0)}",
        "",
        "## 3. LLM vs human boundary metrics",
        "",
        f"- LLM records available: {llm.get('llm_records_available', 0)}",
        f"- Boundary accuracy: {llm.get('llm_boundary_accuracy', 0)}",
        f"- Text-class accuracy: {llm.get('llm_text_class_accuracy', 0)}",
        f"- Parse errors: {llm.get('llm_parse_error_count', 0)}",
        "",
        "## 4. Overclaim / underclaim analysis",
        "",
        f"- Rule overclaim rate: {rule.get('rule_boundary_overclaim_rate', 0)}",
        f"- Rule underclaim rate: {rule.get('rule_boundary_underclaim_rate', 0)}",
        f"- LLM overclaim rate: {llm.get('llm_boundary_overclaim_rate', 0)}",
        f"- LLM underclaim rate: {llm.get('llm_boundary_underclaim_rate', 0)}",
        "",
        "## 5. Required controls analysis",
        "",
        f"- Exact match rate: {controls.get('required_control_exact_match_rate', 0)}",
        f"- Missing 15N control recall: {controls.get('missing_15N_control_recall', 0)}",
        f"- Missing blank control recall: {controls.get('missing_blank_control_recall', 0)}",
        f"- Missing NOx control recall: {controls.get('missing_NOx_control_recall', 0)}",
        "",
        "## 6. Hidden-tax analysis",
        "",
        f"- Exact match rate: {taxes.get('hidden_tax_exact_match_rate', 0)}",
        f"- Jaccard mean: {taxes.get('hidden_tax_jaccard_mean', 0)}",
        f"- Rule tax counts: {json.dumps(taxes.get('tax_type_counts_rule', {}), ensure_ascii=True, sort_keys=True)}",
        f"- Human tax counts: {json.dumps(taxes.get('tax_type_counts_human', {}), ensure_ascii=True, sort_keys=True)}",
        "",
        "## 7. High-impact failure examples",
        "",
        _markdown_table(
            ["Audit", "Paper", "Rule boundary", "Human boundary", "Revision reasons"],
            [
                [
                    item.get("audit_id") or "",
                    item.get("paper_id") or "",
                    item.get("maximum_supported_boundary") or "",
                    item.get("human_maximum_supported_boundary") or "",
                    item.get("revision_reasons") or "",
                ]
                for item in examples
            ],
        ),
        "",
        "## 8. Recommended rule refinements",
        "",
        (
            "Prioritize rules that repeatedly overclaim low-trust provenance, underclaim primary "
            "validated spans, or disagree with human-required controls and hidden-tax labels."
        ),
        "",
        "## 9. Limitations",
        "",
        (
            "Calibration metrics are meaningful only after independent human review. LLM outputs are "
            "comparators, not gold labels, and no rule ledger is overwritten by calibration exports."
        ),
        "",
    ]
    output_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return str(output_path)


def _reviewed_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reviewed: list[dict[str, Any]] = []
    for record in records:
        valid, _ = validate_human_label_record(record)
        if valid and is_reviewed_record(record):
            reviewed.append(record)
    return reviewed


def _review_requirement_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    rule_count = sum(1 for record in records if _truthy(record.get("rule_needs_human_review")))
    llm_count = sum(1 for record in records if _truthy(record.get("llm_needs_human_review")))
    return {
        "rule_review_count": rule_count,
        "llm_review_count": llm_count,
        "overall_review_count": sum(1 for record in records if _truthy(record.get("overall_needs_human_review"))),
        "rule_only_review_count": sum(
            1 for record in records if _truthy(record.get("rule_needs_human_review")) and not _truthy(record.get("llm_needs_human_review"))
        ),
        "llm_only_review_count": sum(
            1 for record in records if _truthy(record.get("llm_needs_human_review")) and not _truthy(record.get("rule_needs_human_review"))
        ),
        "review_priority_band_counts": dict(Counter(str(record.get("review_priority_band") or "none") for record in records)),
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"true", "1", "yes", "y"}


def _llm_text_class(record: dict[str, Any]) -> str:
    value = str(record.get("llm_text_class") or "").strip()
    if value:
        return value
    raw = record.get("raw_llm_record")
    if not raw:
        return ""
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        return ""
    verification = parsed.get("llm_verification") if isinstance(parsed, dict) else None
    if isinstance(verification, dict):
        return str(verification.get("text_class") or "").strip()
    return ""


def _normalized_set(value: Any) -> set[str]:
    return {item.casefold() for item in normalize_list_field(value)}


def _tax_set(record: dict[str, Any]) -> set[str]:
    detected = normalize_list_field(record.get("detected_taxes"))
    if detected:
        return {item.casefold() for item in detected}
    return {item.casefold() for item in normalize_list_field(record.get("hidden_tax"))}


def _contains_any(values: set[str], needles: tuple[str, ...]) -> bool:
    return any(any(needle in value for needle in needles) for value in values)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _rate(numerator: float, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 6)


def _records_for_rule_revision(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records:
        reasons: list[str] = []
        if str(record.get("maximum_supported_boundary") or "") != str(record.get("human_maximum_supported_boundary") or ""):
            comparison = boundary_overclaim_underclaim(
                str(record.get("maximum_supported_boundary") or ""),
                str(record.get("human_maximum_supported_boundary") or ""),
            )
            reasons.append("boundary_overclaim" if comparison["overclaim"] else "boundary_underclaim")
        if str(record.get("text_class") or "") != str(record.get("human_text_class") or ""):
            reasons.append("text_class_mismatch")
        if str(record.get("admissibility_status") or "") != str(record.get("human_admissibility_status") or ""):
            reasons.append("admissibility_mismatch")
        if _normalized_set(record.get("required_controls")) != _normalized_set(record.get("human_required_controls")):
            reasons.append("required_control_mismatch")
        if _tax_set(record) != _normalized_set(record.get("human_hidden_tax")):
            reasons.append("hidden_tax_mismatch")
        if not reasons:
            continue
        rows.append(
            {
                "audit_id": record.get("audit_id") or "",
                "paper_id": record.get("paper_id") or "",
                "source_span_id": record.get("source_span_id") or "",
                "evidence_id": record.get("evidence_id") or "",
                "text_class": record.get("text_class") or "",
                "human_text_class": record.get("human_text_class") or "",
                "maximum_supported_boundary": record.get("maximum_supported_boundary") or "",
                "human_maximum_supported_boundary": record.get("human_maximum_supported_boundary") or "",
                "admissibility_status": record.get("admissibility_status") or "",
                "human_admissibility_status": record.get("human_admissibility_status") or "",
                "revision_reasons": "; ".join(reasons),
                "source_text": _preview(record.get("source_text") or ""),
            }
        )
    return rows


def _confusion_rows(
    records: list[dict[str, Any]],
    rule_field: str,
    human_field: str,
    rule_label: str,
    human_label: str,
) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str]] = Counter()
    for record in records:
        counter[(str(record.get(rule_field) or ""), str(record.get(human_field) or ""))] += 1
    return [
        {rule_label: rule_value, human_label: human_value, "count": count}
        for (rule_value, human_value), count in sorted(counter.items())
    ]


def _write_key_value_csv(values: dict[str, Any], path: Path) -> None:
    rows = [{"metric": key, "value": _csv_value(value)} for key, value in values.items()]
    _write_rows(rows, path)


def _write_rows(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = _fieldnames(rows)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})


def _fieldnames(rows: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for row in rows:
        for key in row:
            if key not in names:
                names.append(key)
    return names or ["metric", "value"]


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict, set, tuple)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return str(value)


def _preview(value: Any, limit: int = 400) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "No records."
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in row) + " |")
    return "\n".join(lines)
