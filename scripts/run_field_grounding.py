from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.field_grounding import ground_record, summarize_grounding  # noqa: E402


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")))
            handle.write("\n")


def run_field_grounding(drafts_path: Path, output_path: Path) -> list[dict[str, Any]]:
    outputs = []
    for draft in load_jsonl(drafts_path):
        grounding = ground_record(draft)
        outputs.append(
            {
                "evidence_id": draft.get("evidence_id"),
                "paper_id": draft.get("paper_id"),
                "grounding": grounding,
                "summary": summarize_grounding(grounding),
            }
        )
    write_jsonl(outputs, output_path)
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run field-level grounding checks.")
    parser.add_argument("--drafts", type=Path, default=Path("data/drafts/draft_evidence.v0.2.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/drafts/field_grounding.v0.2.jsonl"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = run_field_grounding(args.drafts, args.output)
    print(f"Wrote grounding checks for {len(outputs)} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
