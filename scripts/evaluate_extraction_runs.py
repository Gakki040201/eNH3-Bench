"""Evaluate eNH3-ExtractBench method runs against gold JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.extraction_runs import list_run_methods, load_jsonl, load_method_records  # noqa: E402
from enh3bench.toolbench_evaluator import compare_methods, write_comparison_markdown  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate stored eNH3 extraction runs.")
    parser.add_argument("--gold", type=Path, default=Path("data/gold/gold.v0.2.reviewed.jsonl"))
    parser.add_argument("--run-name", default="v0.4_pilot")
    parser.add_argument("--run-dir", type=Path, default=None, help="Optional explicit run directory.")
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir or Path("data/extraction_runs") / args.run_name
    output_json = args.output_json or run_dir / "comparison_report.json"
    output_md = args.output_md or run_dir / "comparison_report.md"
    gold_records = load_jsonl(args.gold)
    methods = list_run_methods(args.run_name, run_dir.parent)
    runs_by_method = {
        method: load_method_records(args.run_name, method, run_dir.parent)
        for method in methods
    }
    results = compare_methods(gold_records, runs_by_method)
    _write_json(results, output_json)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(write_comparison_markdown(results), encoding="utf-8", newline="\n")
    print(f"Evaluated {len(methods)} methods against {len(gold_records)} gold records")
    print(f"Wrote JSON comparison to {output_json}")
    print(f"Wrote Markdown comparison to {output_md}")
    return 0


def _write_json(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
