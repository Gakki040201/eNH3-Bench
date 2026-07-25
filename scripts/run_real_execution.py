from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.provider_execution import run_real_execution  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run an approved B1B1 development plan. Default invocation fails closed; "
            "real execution requires both explicit authorization arguments."
        )
    )
    parser.add_argument("--generation-run-name", required=True)
    parser.add_argument("--pilot-root", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--execute-real-api", action="store_true")
    parser.add_argument("--authorization")
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_real_execution(
            generation_run_name=args.generation_run_name,
            generation_root=args.pilot_root,
            endpoint=args.endpoint,
            execute_real_api=args.execute_real_api,
            authorization=args.authorization,
            resume=args.resume,
        )
    except (OSError, ValueError) as exc:
        print(f"run_real_execution: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print("run_real_execution: PASS")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
