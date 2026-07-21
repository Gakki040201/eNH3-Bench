from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.e2e_eval_package import build_selective_eval_package  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a blank v0.16 selective-human E2E evaluation package.")
    parser.add_argument("--source-calibration-run-name", default="enrr_calibration_v016_round1_20260719")
    parser.add_argument("--source-calibration-root", type=Path, default=Path("data/calibration"))
    parser.add_argument("--selective-eval-run-name", required=True)
    parser.add_argument("--selective-eval-root", type=Path, default=Path("data/selective_eval"))
    parser.add_argument("--anchor-count", type=int, default=24)
    parser.add_argument("--e2e-case-count", type=int, default=48)
    parser.add_argument("--development-case-count", type=int, default=36)
    parser.add_argument("--seed", type=int, default=16)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = build_selective_eval_package(
            source_calibration_run_name=args.source_calibration_run_name,
            source_calibration_root=args.source_calibration_root,
            selective_eval_run_name=args.selective_eval_run_name,
            selective_eval_root=args.selective_eval_root,
            anchor_count=args.anchor_count,
            e2e_case_count=args.e2e_case_count,
            development_case_count=args.development_case_count,
            seed=args.seed,
            clean=args.clean,
            dry_run=args.dry_run,
        )
    except (OSError, ValueError) as exc:
        print(f"selective_eval_build: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print(f"selective_eval_build: {result['result']}")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
