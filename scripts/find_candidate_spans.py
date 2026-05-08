from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.document_loader import load_markdown_documents  # noqa: E402
from enh3bench.span_finder import find_candidate_spans  # noqa: E402


DEFAULT_INPUT_DIR = ROOT / "input_markdown"
DEFAULT_OUTPUT = ROOT / "data" / "candidates" / "candidate_spans.v0.2.jsonl"


def write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")))
            handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find candidate evidence spans in Markdown files.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR, help="Input Markdown directory.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output candidate JSONL.")
    parser.add_argument(
        "--max-spans-per-document",
        type=int,
        default=8,
        help="Maximum candidate spans per Markdown document.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    candidates: list[dict[str, Any]] = []
    for document in load_markdown_documents(args.input_dir):
        candidates.extend(
            find_candidate_spans(
                document,
                max_spans_per_document=args.max_spans_per_document,
            )
        )
    write_jsonl(candidates, args.output)
    print(f"Wrote {len(candidates)} candidate spans to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
