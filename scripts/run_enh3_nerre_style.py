"""Run offline eNH3-NERRE-style JSON extraction on candidate spans."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.extraction_runs import write_method_records  # noqa: E402
from enh3bench.nerre_style_extractor import run_rule_nerre_style  # noqa: E402


DEFAULT_SPANS = Path("data/candidates/candidate_spans.v0.2.jsonl")
DEFAULT_METHOD = "enh3_nerre_rule"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline eNH3-NERRE-style extraction.")
    parser.add_argument("--spans", type=Path, default=DEFAULT_SPANS, help="Candidate spans JSONL.")
    parser.add_argument("--run-name", default="v0.4_pilot", help="Extraction run name.")
    parser.add_argument("--method-name", default=DEFAULT_METHOD, help="Method output file stem.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spans = _load_jsonl(args.spans)
    records = [run_rule_nerre_style(span) for span in spans]
    for record in records:
        record["method_name"] = args.method_name
    output = write_method_records(records, args.run_name, args.method_name)
    print(f"Wrote {len(records)} eNH3-NERRE-style rule records to {output}")
    print("Prompt template for future optional API use:")
    print("- prompts/enh3_nerre_json_schema_prompt.md")
    return 0


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


if __name__ == "__main__":
    raise SystemExit(main())
