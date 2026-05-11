"""Domain summary reports for reviewed eNH3-Bench gold records."""

from __future__ import annotations

from collections import Counter
from typing import Any


def summarize_domain_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize reviewed gold records by eNH3-specific dimensions."""

    return {
        "evidence_records": len(records),
        "unique_papers": len({record.get("paper_id") for record in records if record.get("paper_id")}),
        "reaction_family": _count(records, "reaction_family"),
        "evidence_type": _count(records, "evidence_type"),
        "reliability_label": _count(records, "reliability_label"),
        "validation_controls": {
            "isotope_validation": _count(records, "isotope_validation"),
            "blank_control": _count(records, "blank_control"),
            "contamination_control": _count(records, "contamination_control"),
            "nox_screening": _count(records, "nox_screening"),
        },
        "metric_availability": {
            "FE present": _present(records, "faradaic_efficiency_percent"),
            "EE present": _present(records, "energy_efficiency_percent"),
            "NH3 yield present": _present(records, "nh3_yield_value"),
            "stability present": _present(records, "stability_hours"),
            "potential present": _present(records, "potential_value"),
        },
        "high_risk": high_risk_records(records),
    }


def high_risk_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return conservative high-risk evidence records."""

    high_risk: list[dict[str, Any]] = []
    for record in records:
        reasons: list[str] = []
        if record.get("reliability_label") in {"D", "Reject"}:
            reasons.append(f"reliability_label={record.get('reliability_label')}")
        for field in ["isotope_validation", "blank_control", "contamination_control", "nox_screening"]:
            if record.get(field) == "unclear":
                reasons.append(f"{field}=unclear")
        if _review_like(str(record.get("source_span", ""))) and record.get("evidence_type") == "primary_claim":
            reasons.append("review-like source wording with primary_claim evidence_type")
        if reasons:
            high_risk.append(
                {
                    "evidence_id": record.get("evidence_id"),
                    "paper_id": record.get("paper_id"),
                    "reasons": reasons,
                }
            )
    return high_risk


def candidate_interpretation_bullets(summary: dict[str, Any]) -> list[str]:
    """Generate conservative, data-driven interpretation bullets."""

    records = max(1, int(summary.get("evidence_records", 0)))
    bullets: list[str] = []
    nox_unclear = summary["validation_controls"]["nox_screening"].get("unclear", 0)
    if nox_unclear / records >= 0.5:
        bullets.append("A large fraction of accepted records lack explicit NOx screening.")
    contamination_unclear = summary["validation_controls"]["contamination_control"].get("unclear", 0)
    if contamination_unclear / records >= 0.5:
        bullets.append("Contamination-control reporting is frequently unclear in the reviewed records.")
    families = summary.get("reaction_family", {})
    if any(family in families for family in ["LiNRR", "NO3RR"]):
        bullets.append("LiNRR and NO3RR records should not be directly compared without nitrogen-source stratification.")
    if not bullets:
        bullets.append("Reviewed records are too limited for broad scientific trend claims.")
    return bullets


def render_domain_report(records: list[dict[str, Any]]) -> str:
    """Render a Markdown domain report."""

    summary = summarize_domain_records(records)
    lines = [
        "# eNH3-Bench Domain Report",
        "",
        f"- Evidence records: {summary['evidence_records']}",
        f"- Unique papers: {summary['unique_papers']}",
        "",
        "## Records By Reaction Family",
        "",
        _count_table(summary["reaction_family"], "reaction_family"),
        "",
        "## Records By Evidence Type",
        "",
        _count_table(summary["evidence_type"], "evidence_type"),
        "",
        "## Reliability Label Distribution",
        "",
        _count_table(summary["reliability_label"], "reliability_label"),
        "",
        "## Validation Control Coverage",
        "",
        *_validation_tables(summary["validation_controls"]),
        "",
        "## Metric Availability",
        "",
        _count_table(summary["metric_availability"], "metric"),
        "",
        "## High-Risk Evidence",
        "",
        _high_risk_table(summary["high_risk"]),
        "",
        "## Candidate Scientific Interpretation",
        "",
        *[f"- {bullet}" for bullet in candidate_interpretation_bullets(summary)],
        "",
    ]
    return "\n".join(lines)


def render_domain_summary_table(records: list[dict[str, Any]]) -> str:
    """Render a compact manuscript table."""

    summary = summarize_domain_records(records)
    rows = [
        ["Evidence records", summary["evidence_records"]],
        ["Unique papers", summary["unique_papers"]],
        ["High-risk records", len(summary["high_risk"])],
        ["FE present", summary["metric_availability"]["FE present"]],
        ["NH3 yield present", summary["metric_availability"]["NH3 yield present"]],
    ]
    return _markdown_table(["Summary item", "Value"], rows)


def _count(records: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(record.get(field, "<missing>")) for record in records).items()))


def _present(records: list[dict[str, Any]], field: str) -> int:
    return sum(1 for record in records if record.get(field) not in {None, ""})


def _count_table(counts: dict[str, int], column_name: str) -> str:
    return _markdown_table([column_name, "Count"], [[f"`{key}`", value] for key, value in counts.items()])


def _validation_tables(validation: dict[str, dict[str, int]]) -> list[str]:
    lines: list[str] = []
    for field, counts in validation.items():
        lines.extend([f"### `{field}`", "", _count_table(counts, field), ""])
    return lines


def _high_risk_table(high_risk: list[dict[str, Any]]) -> str:
    if not high_risk:
        return "No high-risk evidence records detected by domain rules."
    rows = [
        [item.get("evidence_id", ""), item.get("paper_id", ""), "; ".join(item.get("reasons", []))]
        for item in high_risk
    ]
    return _markdown_table(["evidence_id", "paper_id", "reasons"], rows)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_cell(value) for value in row) + " |")
    return "\n".join(lines)


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _review_like(text: str) -> bool:
    lowered = text.casefold()
    return any(word in lowered for word in ["review", "summarized", "reported by", "literature", "table"])
