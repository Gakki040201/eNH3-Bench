from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.final_workflow import check_final_output_status, render_final_output_check  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check final eNH3-TriageBench outputs for one run.")
    parser.add_argument("--run-name", default="final_pilot")
    parser.add_argument("--require-training", action="store_true")
    parser.add_argument("--require-models", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    checks = check_final_output_status(
        args.run_name,
        require_training=args.require_training,
        require_models=args.require_models,
    )
    print(render_final_output_check(checks))
    return 1 if any(item["required"] and not item["exists"] for item in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
