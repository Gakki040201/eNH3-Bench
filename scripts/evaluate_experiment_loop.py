from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.closed_loop import NO_RESULTS_MESSAGE, evaluate_closed_loop, export_closed_loop_report  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the closed-loop experiment cycle.")
    parser.add_argument("--run-name", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        evaluation = evaluate_closed_loop(args.run_name)
    except ValueError as exc:
        if str(exc) == NO_RESULTS_MESSAGE:
            print(str(exc))
            return 1
        raise
    report = export_closed_loop_report(evaluation, args.run_name)
    print(f"routes_generated: {evaluation['routes_generated']}")
    print(f"routes_executed: {evaluation['routes_executed']}")
    print(f"success_count: {evaluation['success_count']}")
    print(f"partial_count: {evaluation['partial_count']}")
    print(f"failed_count: {evaluation['failed_count']}")
    print(f"invalid_count: {evaluation['invalid_count']}")
    print(f"json: {evaluation['json']}")
    print(f"csv: {evaluation['csv']}")
    print(f"report: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
