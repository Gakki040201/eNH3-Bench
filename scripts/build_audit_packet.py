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

from enh3bench.audit_packet import (  # noqa: E402
    REVIEW_SHEET_COLUMNS,
    build_audit_packet,
    build_review_sheet_rows,
)


DEFAULT_SPANS = ROOT / "data" / "candidates" / "candidate_spans.v0.2.jsonl"
DEFAULT_DRAFTS = ROOT / "data" / "drafts" / "draft_evidence.v0.2.jsonl"
DEFAULT_OUTPUT_MD = ROOT / "data" / "audit" / "audit_packet.v0.2.md"
DEFAULT_OUTPUT_CSV = ROOT / "data" / "audit" / "review_sheet.v0.2.csv"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number} of {path}") from exc
    return records


def write_review_sheet(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_SHEET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build human audit packet and review sheet.")
    parser.add_argument("--spans", type=Path, default=DEFAULT_SPANS, help="Candidate span JSONL.")
    parser.add_argument("--drafts", type=Path, default=DEFAULT_DRAFTS, help="Draft evidence JSONL.")
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD, help="Audit packet Markdown.")
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV, help="Review sheet CSV.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spans = load_jsonl(args.spans)
    drafts = load_jsonl(args.drafts)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(build_audit_packet(spans, drafts), encoding="utf-8", newline="\n")
    write_review_sheet(build_review_sheet_rows(spans, drafts), args.output_csv)
    print(f"Wrote audit packet to {args.output_md}")
    print(f"Wrote review sheet to {args.output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
