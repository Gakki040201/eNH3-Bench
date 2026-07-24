from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.provider_execution import (  # noqa: E402
    ExecutionBudget,
    ProviderConfiguration,
    prepare_real_execution,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare an offline, development-only B1B1 real-execution plan."
    )
    parser.add_argument("--generation-run-name", required=True)
    parser.add_argument("--pilot-root", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--temperature", type=float, required=True)
    parser.add_argument("--top-p", type=float, required=True)
    parser.add_argument("--max-output-tokens-per-request", type=int, required=True)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--response-format", choices=("json_schema", "json_object"), required=True)
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high"))
    parser.add_argument("--max-requests", type=int, required=True)
    parser.add_argument("--max-network-attempts", type=int, required=True)
    parser.add_argument("--max-input-tokens", type=int, required=True)
    parser.add_argument("--max-output-tokens", type=int, required=True)
    parser.add_argument("--max-total-tokens", type=int, required=True)
    parser.add_argument("--timeout-seconds", type=float, required=True)
    parser.add_argument("--max-retries", type=int, required=True)
    parser.add_argument("--max-estimated-cost", type=float)
    parser.add_argument("--currency")
    parser.add_argument("--resume", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configuration = ProviderConfiguration(
        endpoint=args.endpoint,
        model_id=args.model_id,
        temperature=args.temperature,
        top_p=args.top_p,
        max_output_tokens=args.max_output_tokens_per_request,
        seed=args.seed,
        response_format=args.response_format,
        reasoning_effort=args.reasoning_effort,
    )
    budget = ExecutionBudget(
        max_requests=args.max_requests,
        max_network_attempts=args.max_network_attempts,
        max_input_tokens=args.max_input_tokens,
        max_output_tokens=args.max_output_tokens,
        max_total_tokens=args.max_total_tokens,
        timeout_seconds=args.timeout_seconds,
        max_retries=args.max_retries,
        max_estimated_cost=args.max_estimated_cost,
        currency=args.currency,
    )
    try:
        result = prepare_real_execution(
            generation_run_name=args.generation_run_name,
            generation_root=args.pilot_root,
            configuration=configuration,
            budget=budget,
            resume=args.resume,
        )
    except (OSError, ValueError) as exc:
        print(f"prepare_real_execution: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print("prepare_real_execution: PASS")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
