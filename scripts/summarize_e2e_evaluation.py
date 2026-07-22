from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.e2e_eval_metrics import summarize_e2e  # noqa: E402
from enh3bench.e2e_eval_schema import resolve_run_target, write_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize E2E evaluation without fabricating unavailable metrics.")
    parser.add_argument("--selective-eval-run-name", required=True)
    parser.add_argument("--selective-eval-root", type=Path, default=Path("data/selective_eval"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        run_dir = resolve_run_target(args.selective_eval_root, args.selective_eval_run_name)
        result = summarize_e2e(run_dir)
        if args.output:
            write_json(args.output, result)
    except (OSError, ValueError) as exc:
        print(f"e2e_evaluation_summary: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print("e2e_evaluation_summary: " + str(result["status"]))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
