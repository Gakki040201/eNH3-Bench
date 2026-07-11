from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.experiment_result_importer import import_experiment_results  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import reviewed experiment results.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--input", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = import_experiment_results(args.input, args.run_name)
    print(f"rows_read: {outputs['rows_read']}")
    print(f"valid_results: {outputs['valid_results']}")
    print(f"invalid_results: {outputs['invalid_results']}")
    print(f"warning_results: {outputs['warning_results']}")
    print(f"imported_csv: {outputs['imported_csv']}")
    print(f"imported_jsonl: {outputs['imported_jsonl']}")
    print(f"errors_csv: {outputs['errors_csv']}")
    print(f"warnings_csv: {outputs['warnings_csv']}")
    return 1 if outputs["invalid_results"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
