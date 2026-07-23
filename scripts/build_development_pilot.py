from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.generation_pilot import build_development_pilot  # noqa: E402


DEFAULT_PILOT_ROOT = Path(r"F:\eNH3_Bench_API\v016_b1b0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the offline-only seven-case v0.16 B1B0 pilot.")
    parser.add_argument("--selective-eval-run-name", required=True)
    parser.add_argument("--selective-eval-root", type=Path, default=Path("data/selective_eval"))
    parser.add_argument("--source-calibration-root", type=Path, default=Path("data/calibration"))
    parser.add_argument("--generation-run-name", required=True)
    parser.add_argument("--pilot-root", type=Path, default=DEFAULT_PILOT_ROOT)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = build_development_pilot(
            selective_eval_run_name=args.selective_eval_run_name,
            selective_eval_root=args.selective_eval_root,
            source_calibration_root=args.source_calibration_root,
            generation_run_name=args.generation_run_name,
            generation_root=args.pilot_root,
            clean=args.clean,
        )
    except (OSError, ValueError) as exc:
        print(f"development_pilot_build: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print("development_pilot_build: PASS")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
