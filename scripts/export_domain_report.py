from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.domain_report import render_domain_report, render_domain_summary_table  # noqa: E402


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export eNH3 domain summary report.")
    parser.add_argument("--gold", type=Path, default=Path("data/gold/gold.v0.2.reviewed.jsonl"))
    parser.add_argument("--output-md", type=Path, default=Path("data/reports/domain_report.v0.2.md"))
    parser.add_argument("--output-table", type=Path, default=Path("paper/tables/domain_summary.v0.2.md"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_jsonl(args.gold)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_table.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(render_domain_report(records), encoding="utf-8", newline="\n")
    args.output_table.write_text(render_domain_summary_table(records), encoding="utf-8", newline="\n")
    print(f"Wrote domain report to {args.output_md}")
    print(f"Wrote domain summary table to {args.output_table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
