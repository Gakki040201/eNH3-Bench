"""Ledger routing for classified eNH3-TriageBench source spans."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from enh3bench.reaction_profiles import propagate_paper_family_to_unclear_spans
from enh3bench.source_span_classifier import classify_span_record


LEDGER_FILES = {
    "performance": "performance_ledger",
    "negative": "negative_evidence_ledger",
    "protocol": "validation_protocol_ledger",
    "secondary": "secondary_review_ledger",
    "context": "rejected_or_context",
    "reject": "rejected_or_context",
}

CLASSIFIED_SPANS_BASENAME = "classified_spans"


def classify_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach classification fields to each span record."""

    classified = [classify_span_record(span) for span in spans]
    return propagate_paper_family_to_unclear_spans(classified)


def write_classified_spans(
    records: list[dict[str, Any]],
    run_name: str,
    base_dir: str | Path = Path("data") / "ledgers",
) -> dict[str, str]:
    """Write classified spans as JSONL and CSV."""

    run_dir = Path(base_dir) / run_name
    jsonl_path = run_dir / f"{CLASSIFIED_SPANS_BASENAME}.jsonl"
    csv_path = run_dir / f"{CLASSIFIED_SPANS_BASENAME}.csv"
    _write_jsonl(records, jsonl_path)
    _write_csv(records, csv_path)
    return {"jsonl": str(jsonl_path), "csv": str(csv_path)}


def route_classified_spans(
    records: list[dict[str, Any]],
    run_name: str,
    base_dir: str | Path = Path("data") / "ledgers",
) -> dict[str, Any]:
    """Route classified source spans into evidence ledgers and CSV exports."""

    run_dir = Path(base_dir) / run_name
    ledgers: dict[str, list[dict[str, Any]]] = {
        "performance_ledger": [],
        "negative_evidence_ledger": [],
        "validation_protocol_ledger": [],
        "secondary_review_ledger": [],
        "rejected_or_context": [],
    }

    for record in records:
        ledger_key = str(record.get("recommended_ledger") or "context")
        ledger_name = LEDGER_FILES.get(ledger_key, "rejected_or_context")
        ledgers[ledger_name].append(record)

    outputs: dict[str, dict[str, str | int]] = {}
    for ledger_name, ledger_records in ledgers.items():
        jsonl_path = run_dir / f"{ledger_name}.jsonl"
        csv_path = run_dir / f"{ledger_name}.csv"
        _write_jsonl(ledger_records, jsonl_path)
        _write_csv(ledger_records, csv_path)
        outputs[ledger_name] = {
            "jsonl": str(jsonl_path),
            "csv": str(csv_path),
            "count": len(ledger_records),
        }

    classified_paths = write_classified_spans(records, run_name, base_dir)
    return {
        "run_name": run_name,
        "classified_spans": classified_paths,
        "ledgers": outputs,
        "ledger_counts": {name: int(item["count"]) for name, item in outputs.items()},
    }


def classify_and_route_spans(
    spans: list[dict[str, Any]],
    run_name: str,
    base_dir: str | Path = Path("data") / "ledgers",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Classify source spans, write classified records, and route ledgers."""

    classified = classify_spans(spans)
    manifest = route_classified_spans(classified, run_name, base_dir)
    return classified, manifest


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Load JSONL records from a path."""

    records: list[dict[str, Any]] = []
    path = Path(path)
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


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
        "span_id",
        "evidence_id",
        "paper_id",
        "document_id",
        "source_section",
        "text",
        "source_text",
        "source_span",
        "reaction_family",
        "reaction_family_confidence",
        "reaction_family_scope",
        "paper_level_reaction_family",
        "reaction_family_conflict",
        "reaction_family_signals",
        "reaction_family_scores",
        "text_class",
        "confidence",
        "recommended_ledger",
        "allow_field_extraction",
        "allow_gold",
        "reasons",
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
