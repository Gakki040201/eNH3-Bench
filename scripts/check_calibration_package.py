from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.calibration_validation import validate_calibration_package  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a v0.16 semantic calibration package.")
    parser.add_argument("--calibration-run-name", required=True)
    parser.add_argument("--calibration-root", type=Path, default=Path("data/calibration"))
    parser.add_argument("--cleanroom-root", type=Path, default=Path("data/cleanroom"))
    parser.add_argument("--require-blank-human-fields", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = validate_calibration_package(
            calibration_run_name=args.calibration_run_name,
            calibration_root=args.calibration_root,
            cleanroom_root=args.cleanroom_root,
            require_blank_human_fields=args.require_blank_human_fields,
        )
    except (OSError, ValueError) as exc:
        print(f"calibration_validation: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print(f"calibration_validation: {result['result']}")
    print("counts: " + json.dumps(result["counts"], sort_keys=True))
    print(f"warnings: {result['warning_count']}")
    for warning in result["warnings"]:
        print(f"- WARNING: {warning}")
    for error in result["errors"]:
        print(f"- ERROR: {error}")
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
