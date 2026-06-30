"""Training-dataset builders for human-reviewed eNH3-TriageBench outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


SOURCE_SPAN_COLUMNS = [
    "span_id",
    "paper_id",
    "source_text",
    "machine_text_class",
    "human_text_class",
    "label_source",
    "allow_field_extraction",
    "allow_gold",
]

TRIAGE_COLUMNS = [
    "record_id",
    "paper_id",
    "reaction_family",
    "FE_percent",
    "EE_percent",
    "NH3_yield",
    "isotope_validation",
    "blank_control",
    "contamination_control",
    "nox_screening",
    "reactor_type",
    "engineering_flags",
    "machine_recommendation",
    "human_recommendation",
    "label_source",
]


def build_training_datasets(
    run_name: str,
    classified_spans_path: str | Path | None = None,
    human_review_sheet_path: str | Path | None = None,
    reviewed_gold_path: str | Path | None = None,
    triage_scores_path: str | Path | None = None,
    output_dir: str | Path = Path("data") / "training",
) -> dict[str, Any]:
    """Build source-span and triage training CSVs for one run."""

    classified_spans_path = classified_spans_path or Path("data") / "ledgers" / run_name / "classified_spans.jsonl"
    human_review_sheet_path = human_review_sheet_path or Path("data") / "audit" / f"review_sheet.{run_name}.csv"
    reviewed_gold_path = reviewed_gold_path or Path("data") / "gold" / f"gold.{run_name}.reviewed.jsonl"
    triage_scores_path = triage_scores_path or Path("data") / "reports" / f"experiment_triage_scores.{run_name}.jsonl"

    classified_spans = _load_jsonl(Path(classified_spans_path))
    review_rows = _load_csv_if_exists(Path(human_review_sheet_path))
    reviewed_gold = _load_jsonl(Path(reviewed_gold_path))
    triage_records = _load_jsonl(Path(triage_scores_path))

    review_by_id = _index_review_rows(review_rows)
    gold_by_id = _index_by_any_id(reviewed_gold)

    source_rows = build_source_span_training_rows(classified_spans, review_by_id)
    triage_rows = build_triage_training_rows(triage_records, review_by_id, gold_by_id)

    output_dir = Path(output_dir)
    source_path = output_dir / f"source_span_training.{run_name}.csv"
    triage_path = output_dir / f"triage_training.{run_name}.csv"
    _write_csv(source_rows, source_path, SOURCE_SPAN_COLUMNS)
    _write_csv(triage_rows, triage_path, TRIAGE_COLUMNS)

    return {
        "run_name": run_name,
        "source_span_training_csv": str(source_path),
        "triage_training_csv": str(triage_path),
        "source_span_rows": len(source_rows),
        "triage_rows": len(triage_rows),
        "human_review_rows": len(review_rows),
        "reviewed_gold_rows": len(reviewed_gold),
    }


def build_source_span_training_rows(
    classified_spans: list[dict[str, Any]],
    review_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Build rows for source span classification training."""

    review_by_id = review_by_id or {}
    rows: list[dict[str, str]] = []
    for record in classified_spans:
        span_id = str(record.get("span_id") or "")
        evidence_id = str(record.get("evidence_id") or "")
        review = review_by_id.get(span_id) or review_by_id.get(evidence_id) or {}
        machine_class = str(record.get("text_class") or "unknown")
        human_class = _first_non_empty(
            review,
            ["human_text_class", "corrected_text_class", "accepted_text_class", "text_class"],
        )
        label_source = "human_review" if human_class else "weak_rule_label"
        rows.append(
            {
                "span_id": span_id,
                "paper_id": str(record.get("paper_id") or ""),
                "source_text": _source_text(record),
                "machine_text_class": machine_class,
                "human_text_class": human_class or machine_class,
                "label_source": label_source,
                "allow_field_extraction": str(bool(record.get("allow_field_extraction"))).lower(),
                "allow_gold": str(bool(record.get("allow_gold"))).lower(),
            }
        )
    return rows


def build_triage_training_rows(
    triage_records: list[dict[str, Any]],
    review_by_id: dict[str, dict[str, Any]] | None = None,
    gold_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Build rows for recommendation/ranking training."""

    review_by_id = review_by_id or {}
    gold_by_id = gold_by_id or {}
    rows: list[dict[str, str]] = []
    for record in triage_records:
        record_id = str(record.get("evidence_id") or record.get("record_id") or record.get("span_id") or "")
        span_id = str(record.get("span_id") or "")
        review = review_by_id.get(record_id) or review_by_id.get(span_id) or {}
        gold = gold_by_id.get(record_id) or gold_by_id.get(span_id) or {}
        machine_recommendation = str(record.get("recommendation") or "insufficient_evidence")
        human_recommendation = _first_non_empty(
            review,
            ["human_recommendation", "recommendation_override", "accepted_recommendation"],
        ) or _first_non_empty(gold, ["human_recommendation", "recommendation"])
        label_source = "human_review" if human_recommendation else "weak_rule_label"
        rows.append(
            {
                "record_id": record_id,
                "paper_id": str(record.get("paper_id") or ""),
                "reaction_family": str(record.get("reaction_family") or ""),
                "FE_percent": _string_value(record.get("faradaic_efficiency_percent") or record.get("FE_percent")),
                "EE_percent": _string_value(record.get("energy_efficiency_percent") or record.get("EE_percent")),
                "NH3_yield": _string_value(record.get("nh3_yield_value") or record.get("NH3_yield")),
                "isotope_validation": str(record.get("isotope_validation") or ""),
                "blank_control": str(record.get("blank_control") or ""),
                "contamination_control": str(record.get("contamination_control") or ""),
                "nox_screening": str(record.get("nox_screening") or ""),
                "reactor_type": str(record.get("reactor_type") or ""),
                "engineering_flags": _string_value(record.get("engineering_flags")),
                "machine_recommendation": machine_recommendation,
                "human_recommendation": human_recommendation or machine_recommendation,
                "label_source": label_source,
            }
        )
    return rows


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _load_csv_if_exists(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(rows: list[dict[str, str]], path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _index_review_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        for key in ["span_id", "evidence_id", "record_id"]:
            value = str(row.get(key) or "").strip()
            if value:
                indexed[value] = row
    return indexed


def _index_by_any_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        for key in ["span_id", "evidence_id", "record_id"]:
            value = str(record.get(key) or "").strip()
            if value:
                indexed[value] = record
    return indexed


def _first_non_empty(record: dict[str, Any], fields: list[str]) -> str:
    for field in fields:
        value = str(record.get(field) or "").strip()
        if value:
            return value
    return ""


def _source_text(record: dict[str, Any]) -> str:
    return str(record.get("source_text") or record.get("source_span") or record.get("text") or "")


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)
