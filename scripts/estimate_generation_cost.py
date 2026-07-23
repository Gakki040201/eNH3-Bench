from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.generation_pilot import estimate_generation_cost  # noqa: E402


DEFAULT_PILOT_ROOT = Path(r"F:\eNH3_Bench_API\v016_b1b0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Estimate B1B0 tokens and optional explicit-input cost offline.")
    parser.add_argument("--generation-run-name", required=True)
    parser.add_argument("--pilot-root", type=Path, default=DEFAULT_PILOT_ROOT)
    parser.add_argument("--estimated-output-tokens-per-case", type=int, default=1200)
    parser.add_argument("--pricing-input-per-million", type=float)
    parser.add_argument("--pricing-output-per-million", type=float)
    parser.add_argument("--currency", default="")
    parser.add_argument("--pricing-source", default="")
    parser.add_argument("--pricing-as-of", default="")
    args = parser.parse_args(argv)
    try:
        result = estimate_generation_cost(
            generation_run_name=args.generation_run_name,
            generation_root=args.pilot_root,
            estimated_output_tokens_per_case=args.estimated_output_tokens_per_case,
            pricing_input_per_million=args.pricing_input_per_million,
            pricing_output_per_million=args.pricing_output_per_million,
            currency=args.currency,
            pricing_source=args.pricing_source,
            pricing_as_of=args.pricing_as_of,
        )
    except (OSError, ValueError) as exc:
        print(f"generation_cost_estimate: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print("generation_cost_estimate: PASS")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
