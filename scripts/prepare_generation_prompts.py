from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.generation_pilot import prepare_generation_prompts  # noqa: E402


DEFAULT_PILOT_ROOT = Path(r"F:\eNH3_Bench_API\v016_b1b0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile seven provider-neutral B1B0 prompt instances.")
    parser.add_argument("--generation-run-name", required=True)
    parser.add_argument("--pilot-root", type=Path, default=DEFAULT_PILOT_ROOT)
    args = parser.parse_args(argv)
    try:
        result = prepare_generation_prompts(
            generation_run_name=args.generation_run_name,
            generation_root=args.pilot_root,
        )
    except (OSError, ValueError) as exc:
        print(f"generation_prompt_prepare: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print("generation_prompt_prepare: PASS")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
