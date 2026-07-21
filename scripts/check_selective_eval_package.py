from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.e2e_eval_validation import validate_selective_eval_package  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a v0.16 selective-human E2E evaluation package.")
    parser.add_argument("--selective-eval-run-name", required=True)
    parser.add_argument("--selective-eval-root", type=Path, default=Path("data/selective_eval"))
    parser.add_argument("--source-calibration-root", type=Path, default=Path("data/calibration"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = validate_selective_eval_package(
            selective_eval_run_name=args.selective_eval_run_name,
            selective_eval_root=args.selective_eval_root,
            source_calibration_root=args.source_calibration_root,
        )
    except (OSError, ValueError) as exc:
        print(f"selective_eval_validation: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print(f"selective_eval_validation: {result['result']}")
    print("counts: " + json.dumps(result["counts"], sort_keys=True))
    for warning in result["warnings"]:
        print(f"- WARNING: {warning}")
    for error in result["errors"]:
        print(f"- ERROR: {error}")
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
