from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.demo_v017 import (  # noqa: E402
    DEFAULT_DEMO_ROOT,
    DEFAULT_GENERATION_RUN_NAME,
    DEFAULT_HOST,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MODEL_ID,
    DEFAULT_PILOT_ROOT,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT_SECONDS,
    DemoConfig,
    DemoConfigurationError,
    USTC_LLM_GATEWAY_ENDPOINT,
    serve_demo,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the local M017 seven-case evidence-grounded demonstration.",
    )
    parser.add_argument("--pilot-root", type=Path, default=DEFAULT_PILOT_ROOT)
    parser.add_argument("--generation-run-name", default=DEFAULT_GENERATION_RUN_NAME)
    parser.add_argument("--demo-root", type=Path, default=DEFAULT_DEMO_ROOT)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--endpoint", default=USTC_LLM_GATEWAY_ENDPOINT)
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument(
        "--enable-live-api",
        action="store_true",
        help="Enable explicit live preflight and one-case API runs; disabled by default.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = DemoConfig(
        pilot_root=args.pilot_root,
        generation_run_name=args.generation_run_name,
        demo_root=args.demo_root,
        host=args.host,
        port=args.port,
        endpoint=args.endpoint,
        model_id=args.model_id,
        timeout_seconds=args.timeout_seconds,
        max_output_tokens=args.max_output_tokens,
        live_enabled=args.enable_live_api,
        repository_root=ROOT,
    )
    try:
        config.validate()
        serve_demo(config)
    except DemoConfigurationError as exc:
        print(f"M017 demo startup failed: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
