from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.experiment_result_importer import export_experiment_result_template, load_experiment_routes  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export editable experiment result templates.")
    parser.add_argument("--run-name", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    routes = load_experiment_routes(args.run_name)
    outputs = export_experiment_result_template(routes, args.run_name)
    print(f"routes_loaded: {len(routes)}")
    print(f"templates_exported: {outputs['count']}")
    print(f"csv: {outputs['csv']}")
    print(f"jsonl: {outputs['jsonl']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
