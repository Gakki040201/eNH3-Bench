from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.benchmark_schema import BENCHMARK_TASKS  # noqa: E402
from enh3bench.benchmark_splitter import export_splits, split_tasks_by_group  # noqa: E402
from enh3bench.ledger_router import load_jsonl  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split eNH3-BoundaryBench tasks by paper/document group.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--group-key", default="paper_id")
    parser.add_argument("--train-frac", type=float, default=0.7)
    parser.add_argument("--dev-frac", type=float, default=0.15)
    parser.add_argument("--test-frac", type=float, default=0.15)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "benchmarks")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tasks = _load_tasks(args.run_name, args.output_dir)
    if not any(tasks.values()):
        print(f"No benchmark task files found for run {args.run_name}. Run build_boundary_benchmark first.")
        return 1
    split_tasks = split_tasks_by_group(
        tasks,
        seed=args.seed,
        group_key=args.group_key,
        train_frac=args.train_frac,
        dev_frac=args.dev_frac,
        test_frac=args.test_frac,
    )
    outputs = export_splits(split_tasks, args.run_name, output_dir=args.output_dir)
    for task_name, splits in split_tasks.items():
        print(
            f"{task_name}: train={len(splits['train'])} dev={len(splits['dev'])} test={len(splits['test'])}"
        )
    print(f"split_manifest: {outputs['manifest']}")
    for warning in outputs.get("warnings", []):
        print(f"warning: {warning}")
    return 0


def _load_tasks(run_name: str, output_dir: Path) -> dict[str, list[dict]]:
    run_dir = output_dir / run_name
    return {task_name: load_jsonl(run_dir / f"{task_name}.jsonl") for task_name in BENCHMARK_TASKS}


if __name__ == "__main__":
    raise SystemExit(main())
