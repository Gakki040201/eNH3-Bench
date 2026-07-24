from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.provider_execution import check_real_execution  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate B1B1 execution artifacts offline without credential access."
    )
    parser.add_argument("--generation-run-name", required=True)
    parser.add_argument("--pilot-root", type=Path, required=True)
    parser.add_argument("--require-completed", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = check_real_execution(
            generation_run_name=args.generation_run_name,
            generation_root=args.pilot_root,
            require_completed=args.require_completed,
        )
    except (OSError, ValueError) as exc:
        print(f"check_real_execution: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print("check_real_execution: " + result["result"])
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
