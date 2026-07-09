from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.document_provenance import attach_existing_or_infer, load_provenance_records  # noqa: E402
from enh3bench.evidence_bundle import load_records_from_ledgers  # noqa: E402
from enh3bench.ledger_router import load_jsonl  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Attach provenance fields to classified spans or evidence bundles.")
    parser.add_argument("--run-name", default="final_pilot")
    parser.add_argument("--ledger-dir", type=Path, default=Path("data") / "ledgers")
    parser.add_argument("--boundary-dir", type=Path, default=Path("data") / "boundary_ledger")
    parser.add_argument("--provenance-dir", type=Path, default=Path("data") / "provenance")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records, source = _load_source_records(args.run_name, args.ledger_dir, args.boundary_dir)
    provenance_records = load_provenance_records(args.run_name, args.provenance_dir)
    attached = attach_existing_or_infer(records, provenance_records)
    run_dir = args.provenance_dir / args.run_name
    jsonl_path = run_dir / "classified_spans.with_provenance.jsonl"
    csv_path = run_dir / "classified_spans.with_provenance.csv"
    _write_jsonl(attached, jsonl_path)
    _write_csv(attached, csv_path)
    print(f"Loaded records: {len(records)}")
    print(f"Source: {source}")
    print(f"Provenance records used: {len(provenance_records)}")
    print(f"With provenance JSONL: {jsonl_path}")
    print(f"With provenance CSV: {csv_path}")
    return 0


def _load_source_records(run_name: str, ledger_dir: Path, boundary_dir: Path) -> tuple[list[dict[str, Any]], Path]:
    evidence_path = boundary_dir / run_name / "evidence_bundles.jsonl"
    records = load_jsonl(evidence_path)
    if records:
        return records, evidence_path
    return load_records_from_ledgers(run_name, ledger_dir), ledger_dir / run_name


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
        "source_span_id",
        "evidence_id",
        "paper_id",
        "document_id",
        "source_section",
        "text_class",
        "provenance_type",
        "provenance_confidence",
        "provenance_signals",
        "is_primary_admissible",
        "is_secondary_or_context",
        "is_reject_or_low_trust",
        "source_text",
        "text",
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
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
