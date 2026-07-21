from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.e2e_eval_schema import read_json, read_jsonl, resolve_run_target, write_json  # noqa: E402
from enh3bench.e2e_eval_validation import validate_selective_eval_package  # noqa: E402
from enh3bench.e2e_holdout import (  # noqa: E402
    build_freeze_manifest,
    path_is_within,
    read_generation_parameters,
    validate_development_freeze_outputs,
    validate_freeze_manifest,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create an auditable holdout freeze from validated development artifacts."
    )
    parser.add_argument("--selective-eval-run-name", required=True)
    parser.add_argument("--selective-eval-root", type=Path, default=Path("data/selective_eval"))
    parser.add_argument("--source-calibration-root", type=Path, default=Path("data/calibration"))
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--generation-parameters-json", type=Path, required=True)
    parser.add_argument("--generation-model-family", required=True)
    parser.add_argument("--prompt-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        run_dir = resolve_run_target(args.selective_eval_root, args.selective_eval_run_name)
        output = args.output.resolve()
        if path_is_within(output, run_dir):
            raise ValueError("freeze_manifest_output_inside_runtime")
        if output.exists():
            raise FileExistsError(f"refusing to overwrite: {output}")
        validation = validate_selective_eval_package(
            selective_eval_run_name=args.selective_eval_run_name,
            selective_eval_root=args.selective_eval_root,
            source_calibration_root=args.source_calibration_root,
            check_source_package=True,
        )
        api_outputs_path = run_dir / "cases/api_outputs.jsonl"
        if not api_outputs_path.is_file():
            raise ValueError("holdout freeze requires cases/api_outputs.jsonl")
        cases = read_jsonl(run_dir / "cases/e2e_case_frame.jsonl")
        package_manifest = read_json(run_dir / "manifests/selective_eval_manifest.json")
        parameters = read_generation_parameters(args.generation_parameters_json)
        outputs = read_jsonl(api_outputs_path)
        gate_errors, _ = validate_development_freeze_outputs(
            outputs, cases, generation_model_family=args.generation_model_family,
            prompt_version=args.prompt_version, generation_parameters=parameters,
        )
        if gate_errors:
            raise ValueError("; ".join(gate_errors[:12]))
        if validation["result"] != "PASS":
            raise ValueError("package validation failed: " + "; ".join(validation["errors"][:12]))
        freeze = build_freeze_manifest(
            package_manifest, cases, run_dir=run_dir, prompt_file=args.prompt_file,
            generation_parameters=parameters, prompt_version=args.prompt_version,
            generation_model_family=args.generation_model_family,
        )
        errors = validate_freeze_manifest(
            freeze, package_manifest, cases, run_dir=run_dir,
            prompt_file=args.prompt_file, generation_parameters=parameters,
        )
        if errors:
            raise ValueError("freeze validation failed: " + "; ".join(errors[:12]))
        write_json(output, freeze)
    except (OSError, ValueError) as exc:
        print(f"holdout_freeze_creation: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print(
        "holdout_freeze_creation: PASS"
        f"\ndevelopment_outputs: {freeze['development_api_output_count']}"
        f"\nnetwork_calls: 0\noutput: {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
