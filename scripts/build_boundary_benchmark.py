from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.benchmark_builder import (  # noqa: E402
    build_all_benchmark_tasks,
    export_benchmark_summary,
    export_benchmark_tasks,
    load_human_gold_records,
)


NO_RECORDS_MESSAGE = "No reviewed human records found. Run Phase D import_human_audit_sheet first."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build eNH3-BoundaryBench task datasets.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "benchmarks")
    parser.add_argument("--allow-reviewed-fallback", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--fail-if-no-gold", action="store_true", default=False)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_human_gold_records(
        args.run_name,
        {
            "gold": Path("data") / "gold",
            "human_audit": Path("data") / "human_audit",
            "allow_reviewed_fallback": args.allow_reviewed_fallback,
        },
    )
    if not records:
        print(NO_RECORDS_MESSAGE)
        return 1

    for record in records:
        record["run_name"] = str(record.get("run_name") or args.run_name)
    tasks = build_all_benchmark_tasks(records)
    outputs = export_benchmark_tasks(tasks, args.run_name, output_dir=args.output_dir)
    summary_path = export_benchmark_summary(tasks, args.run_name)

    print(f"reviewed_records: {len(records)}")
    for task_name, rows in tasks.items():
        print(f"{task_name}: {len(rows)}")
    print(f"manifest: {outputs['manifest']}")
    print(f"summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
