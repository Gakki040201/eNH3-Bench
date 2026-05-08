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

from enh3bench.review_merge import merge_reviewed_gold  # noqa: E402


DEFAULT_DRAFTS = ROOT / "data" / "drafts" / "draft_evidence.v0.2.jsonl"
DEFAULT_REVIEW = ROOT / "data" / "audit" / "review_sheet.v0.2.csv"
DEFAULT_OUTPUT = ROOT / "data" / "gold" / "gold.v0.2.reviewed.jsonl"


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


def load_review_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")))
            handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge reviewed draft evidence into gold JSONL.")
    parser.add_argument("--drafts", type=Path, default=DEFAULT_DRAFTS, help="Draft evidence JSONL.")
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW, help="Human review sheet CSV.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Reviewed gold JSONL output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    drafts = load_jsonl(args.drafts)
    review_rows = load_review_rows(args.review)
    reviewed_gold = merge_reviewed_gold(drafts, review_rows)
    write_jsonl(reviewed_gold, args.output)
    print(f"Wrote {len(reviewed_gold)} reviewed gold records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
