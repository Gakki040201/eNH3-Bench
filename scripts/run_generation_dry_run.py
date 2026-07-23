from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.generation_pilot import run_generation_dry_run  # noqa: E402


DEFAULT_PILOT_ROOT = Path(r"F:\eNH3_Bench_API\v016_b1b0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit fixture-only B1B0 request envelopes and receipts.")
    parser.add_argument("--generation-run-name", required=True)
    parser.add_argument("--pilot-root", type=Path, default=DEFAULT_PILOT_ROOT)
    parser.add_argument("--backend", default="fixture")
    args = parser.parse_args(argv)
    try:
        result = run_generation_dry_run(
            generation_run_name=args.generation_run_name,
            generation_root=args.pilot_root,
            backend_name=args.backend,
        )
    except (OSError, ValueError) as exc:
        print(f"generation_dry_run: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print("generation_dry_run: PASS")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
