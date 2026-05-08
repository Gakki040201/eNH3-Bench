from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.draft_extractor import draft_evidence_from_span  # noqa: E402


DEFAULT_SPANS = ROOT / "data" / "candidates" / "candidate_spans.v0.2.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "drafts" / "draft_evidence.v0.2.jsonl"


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


def write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")))
            handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run draft evidence extraction for candidate spans.")
    parser.add_argument("--spans", type=Path, default=DEFAULT_SPANS, help="Candidate span JSONL.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Draft evidence JSONL.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spans = load_jsonl(args.spans)
    drafts = [draft_evidence_from_span(span) for span in spans]
    write_jsonl(drafts, args.output)
    print(f"Wrote {len(drafts)} draft evidence records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
