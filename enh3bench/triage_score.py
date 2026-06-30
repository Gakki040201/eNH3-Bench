"""Evidence-gated experiment triage scoring for eNH3-TriageBench."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any


RECOMMENDATIONS = {
    "priority_follow_up",
    "conditional_follow_up",
    "insufficient_evidence",
    "deprioritize",
}

PERFORMANCE_CLASSES = {"primary_performance", "primary_performance_with_validation"}
NON_PERFORMANCE_CLASSES = {
    "protocol_guideline",
    "review_table",
    "figure_caption",
    "reference_list",
    "contamination_detection_evidence",
    "contamination_reassignment_evidence",
    "computational_screening",
    "background_context",
    "unknown",
}


def score_performance_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a triage-scored copy of one primary performance record."""

    if not is_performance_triage_eligible(record):
        text_class = str(record.get("text_class") or record.get("source_section") or "unknown")
        raise ValueError(f"Record is not eligible for performance triage scoring: {text_class}")

    scored = dict(record)
    metric_score = metric_completeness_score(record)
    validation_score = validation_completeness_score(record)
    source_score = source_grounding_score(record)
    engineering_score, flags = engineering_relevance_score(record)
    penalty = contamination_risk_penalty(record)
    raw_score = (
        0.25 * metric_score
        + 0.30 * validation_score
        + 0.20 * source_score
        + 0.25 * engineering_score
        - penalty
    )
    final_score = _clamp(raw_score)
    recommendation, recommendation_reasons = _recommendation(
        record,
        metric_score,
        validation_score,
        source_score,
        engineering_score,
        penalty,
        final_score,
    )

    scored.update(
        {
            "metric_completeness_score": round(metric_score, 3),
            "validation_completeness_score": round(validation_score, 3),
            "source_grounding_score": round(source_score, 3),
            "engineering_relevance_score": round(engineering_score, 3),
            "engineering_flags": flags,
            "contamination_risk_penalty": round(penalty, 3),
            "final_triage_score": round(final_score, 3),
            "recommendation": recommendation,
            "recommendation_reasons": recommendation_reasons,
        }
    )
    return scored


def score_performance_records(
    records: list[dict[str, Any]],
    include_ineligible: bool = False,
) -> list[dict[str, Any]]:
    """Score eligible primary performance records."""

    scored: list[dict[str, Any]] = []
    for record in records:
        if is_performance_triage_eligible(record):
            scored.append(score_performance_record(record))
        elif include_ineligible:
            ineligible = dict(record)
            ineligible.update(
                {
                    "triage_ineligible_reason": "non-primary-performance source class",
                    "recommendation": "insufficient_evidence",
                }
            )
            scored.append(ineligible)
    scored.sort(key=lambda item: (-float(item.get("final_triage_score") or 0.0), str(item.get("evidence_id") or item.get("span_id") or "")))
    return scored


def is_performance_triage_eligible(record: dict[str, Any]) -> bool:
    """Return whether a record can receive a performance triage score."""

    text_class = str(record.get("text_class") or "").strip()
    if text_class:
        return text_class in PERFORMANCE_CLASSES
    source_section = str(record.get("source_section") or "").casefold()
    evidence_type = str(record.get("evidence_type") or "").casefold()
    if source_section in {"review_table", "reference_list", "figure_caption"}:
        return False
    if evidence_type in {"review_summary", "negative_result", "reassessment"}:
        return False
    return _has_any_metric(record)


def metric_completeness_score(record: dict[str, Any]) -> float:
    """Score whether performance metrics are complete enough for triage."""

    score = 0.0
    if _has_float(record, "faradaic_efficiency_percent", "FE_percent"):
        score += 0.25
    if _has_float(record, "nh3_yield_value", "NH3_yield", "nh3_yield"):
        score += 0.25
    if _has_float(record, "potential_value"):
        score += 0.20
    if _has_float(record, "current_density_mA_cm2", "current_density"):
        score += 0.20
    if _has_float(record, "energy_efficiency_percent", "EE_percent"):
        score += 0.10
    return _clamp(score)


def validation_completeness_score(record: dict[str, Any]) -> float:
    """Score isotope, blank, contamination, NOx, and detection validation."""

    n2_like = _is_n2_family(record)
    score = 0.0
    if _value_is_yes(record.get("isotope_validation")):
        score += 0.35
    elif not n2_like and str(record.get("isotope_validation") or "").casefold() in {"not_applicable", "not applicable"}:
        score += 0.20
    if _value_is_yes(record.get("blank_control")):
        score += 0.20
    if _value_is_yes(record.get("contamination_control")):
        score += 0.20
    if _value_is_yes(record.get("nox_screening")):
        score += 0.15
    if _present(record.get("detection_method")):
        score += 0.10
    return _clamp(score)


def source_grounding_score(record: dict[str, Any]) -> float:
    """Score whether the record is grounded in primary extractable source text."""

    text_class = str(record.get("text_class") or "").strip()
    if text_class in NON_PERFORMANCE_CLASSES:
        return 0.0
    if record.get("allow_field_extraction") is False:
        return 0.0
    confidence = str(record.get("confidence") or "").casefold()
    if confidence == "high":
        base = 1.0
    elif confidence == "medium":
        base = 0.75
    elif confidence == "low":
        base = 0.50
    else:
        base = 0.65
    source_text = _source_text(record)
    if len(source_text) < 30:
        base -= 0.15
    if not source_text:
        base -= 0.35
    return _clamp(base)


def engineering_relevance_score(record: dict[str, Any]) -> tuple[float, list[str]]:
    """Score engineering relevance and return the contributing flags."""

    text = _source_text(record).casefold()
    flags: list[str] = []
    reactor = str(record.get("reactor_type") or "").casefold()

    if _contains_any(text, ["flow reactor", "flow cell", "gde", "gas diffusion electrode"]) or _contains_any(
        reactor,
        ["flow", "gde", "gas diffusion"],
    ):
        flags.append("flow_or_GDE_reactor")
    if _contains_any(text, ["hydrogen oxidation", "hor"]):
        flags.append("HOR_context")
    if _has_float(record, "energy_efficiency_percent", "EE_percent") or _contains_any(text, ["energy efficiency", "ee "]):
        flags.append("energy_efficiency_reported")
    stability = _first_float(record, "stability_hours")
    if stability is not None and stability >= 10:
        flags.append("long_runtime_or_stability")
    elif stability is not None and stability > 0:
        flags.append("stability_reported")
    if _contains_any(text, ["gas-phase ammonia", "gas phase ammonia", "gas-phase product", "gas phase product"]):
        flags.append("gas_phase_product")
    if _contains_any(text, ["aqueous nh3", "aqueous ammonia", "product state", "nh4+", "ammonium"]):
        flags.append("product_state_disclosed")
    if _has_float(record, "current_density_mA_cm2", "current_density"):
        flags.append("current_density_reported")

    weights = {
        "flow_or_GDE_reactor": 0.20,
        "HOR_context": 0.10,
        "energy_efficiency_reported": 0.15,
        "long_runtime_or_stability": 0.15,
        "stability_reported": 0.08,
        "gas_phase_product": 0.10,
        "product_state_disclosed": 0.10,
        "current_density_reported": 0.20,
    }
    score = sum(weights[flag] for flag in flags)
    return _clamp(score), flags


def contamination_risk_penalty(record: dict[str, Any]) -> float:
    """Return penalty for contamination uncertainty or reassignment risk."""

    text = _source_text(record).casefold()
    penalty = 0.0
    if str(record.get("text_class") or "") in {
        "contamination_detection_evidence",
        "contamination_reassignment_evidence",
    }:
        penalty += 0.40
    if _contains_any(
        text,
        [
            "false positive",
            "reassigned",
            "not from n2",
            "background ammonia accounted",
            "originated from contamination",
        ],
    ):
        penalty += 0.35
    if _contains_any(
        text,
        [
            "contamination uncertainty",
            "ambiguous contamination",
            "background ammonia",
            "nitrate contamination",
            "nitrite contamination",
            "nox contamination",
            "impurity",
        ],
    ):
        penalty += 0.20
    if _is_n2_family(record) and not _value_is_yes(record.get("contamination_control")):
        penalty += 0.12
    if _is_n2_family(record) and not _value_is_yes(record.get("nox_screening")):
        penalty += 0.08
    return min(0.60, penalty)


def export_triage_outputs(
    scored_records: list[dict[str, Any]],
    run_name: str,
    report_dir: str | Path = Path("data") / "reports",
    ledger_counts: dict[str, int] | None = None,
) -> dict[str, str]:
    """Write the Markdown triage report, CSV table, and JSONL score records."""

    report_dir = Path(report_dir)
    report_path = report_dir / f"experiment_triage_report.{run_name}.md"
    table_path = report_dir / f"experiment_triage_table.{run_name}.csv"
    scores_path = report_dir / f"experiment_triage_scores.{run_name}.jsonl"
    scores_csv_path = report_dir / f"experiment_triage_scores.{run_name}.csv"

    _write_jsonl(scored_records, scores_path)
    _write_csv(scored_records, scores_csv_path)
    _write_csv(scored_records, table_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_experiment_triage_report(scored_records, run_name, ledger_counts),
        encoding="utf-8",
        newline="\n",
    )
    return {
        "triage_report_md": str(report_path),
        "triage_table_csv": str(table_path),
        "triage_scores_jsonl": str(scores_path),
        "triage_scores_csv": str(scores_csv_path),
    }


def render_experiment_triage_report(
    scored_records: list[dict[str, Any]],
    run_name: str,
    ledger_counts: dict[str, int] | None = None,
) -> str:
    """Render the final experiment triage report with required sections."""

    ledger_counts = ledger_counts or {}
    recommendations = Counter(str(record.get("recommendation") or "insufficient_evidence") for record in scored_records)
    lines = [
        f"# eNH3-TriageBench Experiment Triage Report: {run_name}",
        "",
        "## 1. What this run produced",
        "",
        f"- Classified source spans: {sum(ledger_counts.values()) if ledger_counts else 'not provided'}",
        f"- Performance records scored: {len(scored_records)}",
        f"- Recommendation labels: {_counter_text(recommendations)}",
        "",
        "## 2. Evidence attrition",
        "",
        _attrition_table(ledger_counts, len(scored_records)),
        "",
        "## 3. Ledger distribution",
        "",
        _ledger_table(ledger_counts),
        "",
        "## 4. Metric completeness",
        "",
        _metric_completeness_table(scored_records),
        "",
        "## 5. Validation completeness",
        "",
        _validation_completeness_table(scored_records),
        "",
        "## 6. High-priority follow-up directions",
        "",
        _record_table(_records_by_recommendation(scored_records, "priority_follow_up")),
        "",
        "## 7. Conditional follow-up directions",
        "",
        _record_table(_records_by_recommendation(scored_records, "conditional_follow_up")),
        "",
        "## 8. Deprioritized/high-risk claims",
        "",
        _record_table(_records_by_recommendation(scored_records, "deprioritize")),
        "",
        "## 9. Negative evidence warnings",
        "",
        _negative_warning_text(scored_records),
        "",
        "## 10. Dataset-use warning for future ML prediction",
        "",
        (
            "This report is evidence triage, not catalyst-property prediction. Do not train "
            "future models on weak labels as if they were human-reviewed truth, and do not "
            "treat high FE without yield, operating conditions, and validation as a priority "
            "recommendation."
        ),
        "",
        "## 11. Suggested next experiments",
        "",
        _suggested_experiments(scored_records),
        "",
    ]
    return "\n".join(lines)


def _recommendation(
    record: dict[str, Any],
    metric_score: float,
    validation_score: float,
    source_score: float,
    engineering_score: float,
    penalty: float,
    final_score: float,
) -> tuple[str, list[str]]:
    blockers = _priority_blockers(record)
    reasons: list[str] = []

    if penalty >= 0.35:
        return "deprioritize", ["high contamination or reassignment risk"]
    if metric_score < 0.30:
        return "insufficient_evidence", ["metric evidence is incomplete"]
    if validation_score < 0.25:
        return "insufficient_evidence", ["validation evidence is incomplete"]
    if final_score >= 0.72 and not blockers and metric_score >= 0.65 and validation_score >= 0.65 and source_score >= 0.70:
        reasons.append("complete metrics and validation with primary source grounding")
        if engineering_score >= 0.35:
            reasons.append("engineering-relevant operating context")
        return "priority_follow_up", reasons
    if blockers:
        reasons.extend(blockers)
    if final_score >= 0.42:
        if not reasons:
            reasons.append("some evidence is present but priority criteria are not met")
        return "conditional_follow_up", reasons
    return "insufficient_evidence", reasons or ["triage score below follow-up threshold"]


def _priority_blockers(record: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    has_fe = _has_float(record, "faradaic_efficiency_percent", "FE_percent")
    has_yield = _has_float(record, "nh3_yield_value", "NH3_yield", "nh3_yield")
    has_operating_load = _has_float(record, "potential_value") or _has_float(record, "current_density_mA_cm2", "current_density")
    if has_fe and (not has_yield or not has_operating_load):
        blockers.append("FE without NH3 yield and potential/current density is conditional at best")
    if _is_n2_family(record) and not _value_is_yes(record.get("isotope_validation")):
        blockers.append("N2-to-NH3 claim lacks explicit 15N validation")
    return blockers


def _is_n2_family(record: dict[str, Any]) -> bool:
    family = str(record.get("reaction_family") or "").casefold()
    source = str(record.get("nitrogen_source") or "").casefold()
    text = _source_text(record).casefold()
    return family in {"enrr", "linrr"} or source in {"n2", "15n2"} or "n2 reduction" in text or "nitrogen reduction" in text


def _has_any_metric(record: dict[str, Any]) -> bool:
    return any(
        _has_float(record, field)
        for field in [
            "faradaic_efficiency_percent",
            "FE_percent",
            "nh3_yield_value",
            "NH3_yield",
            "potential_value",
            "current_density_mA_cm2",
            "energy_efficiency_percent",
        ]
    )


def _has_float(record: dict[str, Any], *fields: str) -> bool:
    return _first_float(record, *fields) is not None


def _first_float(record: dict[str, Any], *fields: str) -> float | None:
    for field in fields:
        value = record.get(field)
        if value is None or value == "":
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric):
            return numeric
    return None


def _value_is_yes(value: Any) -> bool:
    return str(value or "").strip().casefold() in {"yes", "true", "confirmed", "present", "1"}


def _present(value: Any) -> bool:
    return value is not None and str(value).strip() not in {"", "none", "null", "unknown", "unclear"}


def _source_text(record: dict[str, Any]) -> str:
    return str(record.get("source_text") or record.get("source_span") or record.get("text") or "")


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


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
        for record in records:
            writer.writerow({field: _csv_value(record.get(field)) for field in fieldnames})


def _fieldnames(records: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "evidence_id",
        "span_id",
        "paper_id",
        "reaction_family",
        "nitrogen_source",
        "faradaic_efficiency_percent",
        "nh3_yield_value",
        "nh3_yield_unit",
        "potential_value",
        "current_density_mA_cm2",
        "energy_efficiency_percent",
        "stability_hours",
        "isotope_validation",
        "blank_control",
        "contamination_control",
        "nox_screening",
        "reactor_type",
        "text_class",
        "metric_completeness_score",
        "validation_completeness_score",
        "source_grounding_score",
        "engineering_relevance_score",
        "engineering_flags",
        "contamination_risk_penalty",
        "final_triage_score",
        "recommendation",
        "recommendation_reasons",
        "source_text",
        "source_span",
    ]
    names: set[str] = set(preferred)
    for record in records:
        names.update(record)
    ordered = [name for name in preferred if name in names]
    ordered.extend(sorted(name for name in names if name not in set(ordered)))
    return ordered


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)


def _counter_text(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in sorted(counter.items()))


def _attrition_table(ledger_counts: dict[str, int], scored_count: int) -> str:
    classified = sum(ledger_counts.values()) if ledger_counts else 0
    rows = [
        ["Classified spans", classified],
        ["Performance-ledger spans", ledger_counts.get("performance_ledger", 0)],
        ["Triage-scored records", scored_count],
    ]
    return _markdown_table(["Stage", "Count"], rows)


def _ledger_table(ledger_counts: dict[str, int]) -> str:
    if not ledger_counts:
        return "Ledger counts were not provided."
    rows = [[name, count] for name, count in sorted(ledger_counts.items())]
    return _markdown_table(["Ledger", "Records"], rows)


def _metric_completeness_table(records: list[dict[str, Any]]) -> str:
    rows = [
        ["FE percent present", _count(records, lambda item: _has_float(item, "faradaic_efficiency_percent", "FE_percent"))],
        ["NH3 yield present", _count(records, lambda item: _has_float(item, "nh3_yield_value", "NH3_yield"))],
        ["Potential present", _count(records, lambda item: _has_float(item, "potential_value"))],
        ["Current density present", _count(records, lambda item: _has_float(item, "current_density_mA_cm2", "current_density"))],
        ["Energy efficiency present", _count(records, lambda item: _has_float(item, "energy_efficiency_percent", "EE_percent"))],
    ]
    return _markdown_table(["Metric signal", "Records"], rows)


def _validation_completeness_table(records: list[dict[str, Any]]) -> str:
    rows = [
        ["Explicit isotope validation", _count(records, lambda item: _value_is_yes(item.get("isotope_validation")))],
        ["Blank control", _count(records, lambda item: _value_is_yes(item.get("blank_control")))],
        ["Contamination control", _count(records, lambda item: _value_is_yes(item.get("contamination_control")))],
        ["NOx screening", _count(records, lambda item: _value_is_yes(item.get("nox_screening")))],
        ["Detection method", _count(records, lambda item: _present(item.get("detection_method")))],
    ]
    return _markdown_table(["Validation signal", "Records"], rows)


def _records_by_recommendation(records: list[dict[str, Any]], recommendation: str) -> list[dict[str, Any]]:
    return [record for record in records if record.get("recommendation") == recommendation]


def _record_table(records: list[dict[str, Any]], limit: int = 20) -> str:
    if not records:
        return "None in this run."
    rows: list[list[Any]] = []
    for record in records[:limit]:
        rows.append(
            [
                record.get("evidence_id") or record.get("span_id") or "",
                record.get("paper_id") or "",
                record.get("reaction_family") or "",
                record.get("faradaic_efficiency_percent") or record.get("FE_percent") or "",
                record.get("nh3_yield_value") or record.get("NH3_yield") or "",
                record.get("final_triage_score") or "",
                "; ".join(str(reason) for reason in record.get("recommendation_reasons", [])[:2]),
            ]
        )
    return _markdown_table(["Record", "Paper", "Family", "FE %", "NH3 yield", "Score", "Reason"], rows)


def _negative_warning_text(records: list[dict[str, Any]]) -> str:
    high_risk = [
        record
        for record in records
        if float(record.get("contamination_risk_penalty") or 0.0) >= 0.25
        or record.get("recommendation") == "deprioritize"
    ]
    if not high_risk:
        return "No high-risk contamination warnings were scored from the performance ledger."
    return _record_table(high_risk)


def _suggested_experiments(records: list[dict[str, Any]]) -> str:
    priority = _records_by_recommendation(records, "priority_follow_up")
    conditional = _records_by_recommendation(records, "conditional_follow_up")
    lines: list[str] = []
    if priority:
        lines.append("- Reproduce priority records with the same isotope, blank, contamination, and metric disclosures.")
    if conditional:
        lines.append("- For conditional records, add the missing NH3 yield, potential/current density, or validation controls before ranking them as priorities.")
    if not lines:
        lines.append("- Build more human-reviewed primary performance records before selecting follow-up experiments.")
    lines.append("- Treat contamination warnings as experiment-design constraints, not as positive performance evidence.")
    return "\n".join(lines)


def _count(records: list[dict[str, Any]], predicate: Any) -> int:
    return sum(1 for record in records if predicate(record))


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_escape_cell(value) for value in row) + " |")
    return "\n".join(lines)


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
