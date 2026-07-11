from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.experiment_planner import (  # noqa: E402
    export_experiment_routes,
    filter_routes,
    identify_actionable_gaps,
    load_boundary_inputs,
    merge_planning_records,
    propose_rule_based_routes,
)
from enh3bench.lab_profile import load_lab_profile, validate_lab_profile  # noqa: E402
from enh3bench.llm_clients import OpenAICompatibleClient  # noqa: E402
from enh3bench.llm_experiment_planner import refine_routes_with_llm  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate lab-constrained experiment routes.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--lab-profile", required=True, type=Path)
    parser.add_argument("--reaction-family", default="LiNRR")
    parser.add_argument("--include-families")
    parser.add_argument("--lab-demo-only", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--require-baseline-first", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-sop-fields", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--respect-stage-gates", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--include-blocked-routes", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--only-actionable-routes", action="store_true")
    parser.add_argument("--llm-model")
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--max-routes", type=int)
    parser.add_argument("--priority-only", action="store_true")
    parser.add_argument("--min-score", type=int)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "experiment_routes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = load_lab_profile(args.lab_profile)
    valid, errors = validate_lab_profile(profile)
    if not valid:
        print("Invalid lab profile:")
        for error in errors:
            print(f"- {error}")
        return 2
    inputs = load_boundary_inputs(args.run_name, model=args.llm_model)
    records = merge_planning_records(inputs)
    gaps = identify_actionable_gaps(records)
    routes = propose_rule_based_routes(
        gaps,
        profile,
        args.run_name,
        reaction_family=args.reaction_family,
        include_families=_parse_families(args.include_families),
        lab_demo_only=args.lab_demo_only,
        require_baseline_first=args.require_baseline_first,
        include_sop_fields=args.include_sop_fields,
        respect_stage_gates=args.respect_stage_gates,
    )
    routes = filter_routes(
        routes,
        min_score=args.min_score,
        priority_only=args.priority_only,
        include_blocked_routes=args.include_blocked_routes,
        only_actionable_routes=args.only_actionable_routes,
    )
    if args.max_routes is not None:
        routes = routes[: max(0, args.max_routes)]
    llm_failures = []
    if args.use_llm:
        client = OpenAICompatibleClient(model=args.llm_model)
        available, message = client.verify_available()
        if available:
            routes, llm_failures = refine_routes_with_llm(routes, profile, client, model=args.llm_model)
        else:
            llm_failures = [{"error_type": "llm_unavailable", "error": message}]
    outputs = export_experiment_routes(routes, args.run_name, output_dir=args.output_dir)

    print(f"records_loaded: {len(records)}")
    print(f"actionable_gaps: {len(gaps)}")
    print(f"reaction_family: {args.reaction_family}")
    print(f"include_families: {args.include_families or ''}")
    print(f"lab_demo_only: {args.lab_demo_only}")
    print(f"require_baseline_first: {args.require_baseline_first}")
    print(f"include_sop_fields: {args.include_sop_fields}")
    print(f"respect_stage_gates: {args.respect_stage_gates}")
    print(f"include_blocked_routes: {args.include_blocked_routes}")
    print(f"only_actionable_routes: {args.only_actionable_routes}")
    print(f"routes_generated: {len(routes)}")
    print(f"priority_routes: {outputs['priority_routes']}")
    print(f"deferred_routes: {outputs['deferred_routes']}")
    print(f"llm_failures: {len(llm_failures)}")
    print(f"JSONL: {outputs['jsonl']}")
    print(f"CSV: {outputs['csv']}")
    print(f"Summary: {outputs['summary_json']}")
    return 0


def _parse_families(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
