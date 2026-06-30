from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.ledger_router import load_jsonl  # noqa: E402
from enh3bench.triage_score import export_triage_outputs, score_performance_records  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export eNH3-TriageBench experiment triage report.")
    parser.add_argument("--run-name", default="final_pilot")
    parser.add_argument("--performance-ledger", type=Path, default=None)
    parser.add_argument("--triage-scores", type=Path, default=None)
    parser.add_argument("--report-dir", type=Path, default=Path("data") / "reports")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    triage_scores_path = args.triage_scores or args.report_dir / f"experiment_triage_scores.{args.run_name}.jsonl"
    if triage_scores_path.exists():
        scored_records = load_jsonl(triage_scores_path)
    else:
        performance_ledger = args.performance_ledger or Path("data") / "ledgers" / args.run_name / "performance_ledger.jsonl"
        performance_records = load_jsonl(performance_ledger)
        scored_records = score_performance_records(performance_records)
    ledger_counts = _ledger_counts(args.run_name)
    outputs = export_triage_outputs(scored_records, args.run_name, args.report_dir, ledger_counts=ledger_counts)
    print(f"Wrote triage report to {outputs['triage_report_md']}")
    print(f"Wrote triage table to {outputs['triage_table_csv']}")
    return 0


def _ledger_counts(run_name: str) -> dict[str, int]:
    ledgers_dir = Path("data") / "ledgers" / run_name
    counts: dict[str, int] = {}
    for path in ledgers_dir.glob("*_ledger.jsonl"):
        counts[path.stem] = _jsonl_count(path)
    context = ledgers_dir / "rejected_or_context.jsonl"
    if context.exists():
        counts[context.stem] = _jsonl_count(context)
    return counts


def _jsonl_count(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


if __name__ == "__main__":
    raise SystemExit(main())
