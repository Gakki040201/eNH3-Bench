from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.e2e_eval_schema import write_json  # noqa: E402
from enh3bench.generation_pilot import (  # noqa: E402
    resolve_external_run_target,
    validate_generation_pilot,
)


DEFAULT_PILOT_ROOT = Path(r"F:\eNH3_Bench_API\v016_b1b0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the offline-only seven-case B1B0 pilot.")
    parser.add_argument("--generation-run-name", required=True)
    parser.add_argument("--pilot-root", type=Path, default=DEFAULT_PILOT_ROOT)
    parser.add_argument("--selective-eval-root", type=Path, default=Path("data/selective_eval"))
    parser.add_argument("--source-calibration-root", type=Path, default=Path("data/calibration"))
    args = parser.parse_args(argv)
    result = validate_generation_pilot(
        generation_run_name=args.generation_run_name,
        generation_root=args.pilot_root,
        selective_eval_root=args.selective_eval_root,
        source_calibration_root=args.source_calibration_root,
        check_source_package=True,
    )
    run_dir = resolve_external_run_target(args.pilot_root, args.generation_run_name)
    write_json(run_dir / "reports/pilot_validation.json", result)
    print(f"generation_pilot_validation: {result['result']}")
    print(f"counts: {json.dumps(result['counts'], sort_keys=True)}")
    print(f"normalized_hashes: {json.dumps(result.get('normalized_hashes', {}), sort_keys=True)}")
    for error in result["errors"]:
        print(f"- {error}")
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
