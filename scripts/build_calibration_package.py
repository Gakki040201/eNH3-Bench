from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.calibration_package import CalibrationPackageBuilder  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a blank v0.16 semantic calibration package.")
    parser.add_argument("--cleanroom-run-name", required=True)
    parser.add_argument("--calibration-run-name", required=True)
    parser.add_argument("--cleanroom-root", type=Path, default=Path("data/cleanroom"))
    parser.add_argument("--calibration-root", type=Path, default=Path("data/calibration"))
    parser.add_argument("--span-sample-size", type=int, default=300)
    parser.add_argument("--paper-sample-size", type=int, default=60)
    parser.add_argument("--link-sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=16)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        builder = CalibrationPackageBuilder(
            cleanroom_run_name=args.cleanroom_run_name,
            calibration_run_name=args.calibration_run_name,
            cleanroom_root=args.cleanroom_root,
            calibration_root=args.calibration_root,
            span_sample_size=args.span_sample_size,
            paper_sample_size=args.paper_sample_size,
            link_sample_size=args.link_sample_size,
            seed=args.seed,
        )
        result = builder.build(clean=args.clean, dry_run=args.dry_run)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"calibration_build: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print(f"calibration_build: {str(result.get('status') or '').upper()}")
    print(f"calibration_run_name: {args.calibration_run_name}")
    print(f"source_cleanroom_run_name: {args.cleanroom_run_name}")
    if result.get("selected_sample_counts"):
        print("selected_counts: " + json.dumps(result["selected_sample_counts"], sort_keys=True))
    if result.get("warnings"):
        print("warnings: " + json.dumps(result["warnings"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
