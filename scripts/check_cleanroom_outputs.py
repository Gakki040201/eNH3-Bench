from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.cleanroom_output_check import compare_normalized_runs, validate_cleanroom_run  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate clean-room outputs and compare normalized reproducibility.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--compare-run")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = ROOT / "data" / "cleanroom"
    validation = validate_cleanroom_run(root / args.run_name)
    print(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True))
    success = validation["result"] == "PASS"
    if args.compare_run:
        comparison = compare_normalized_runs(root / args.run_name, root / args.compare_run)
        print(json.dumps(comparison, ensure_ascii=False, indent=2, sort_keys=True))
        success = success and comparison["reproducibility_match"]
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
