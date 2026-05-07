from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.rule_baseline import run_rule_extraction  # noqa: E402


DEFAULT_INPUT = ROOT / "data" / "spans" / "spans.example.jsonl"
DEFAULT_OUTPUT = ROOT / "data" / "predictions" / "rule_baseline.example.jsonl"


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number} of {path}") from exc


def run_baseline(input_path: Path, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for span_record in iter_jsonl(input_path):
            prediction = run_rule_extraction(span_record)
            handle.write(json.dumps(prediction, separators=(",", ":")))
            handle.write("\n")
            count += 1
    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the no-API rule baseline.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input span JSONL file.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output prediction JSONL file.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    count = run_baseline(args.input, args.output)
    print(f"Wrote {count} predictions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
