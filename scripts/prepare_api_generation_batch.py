from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.e2e_holdout import (  # noqa: E402
    read_generation_parameters,
    select_generation_rows,
    validate_freeze_manifest,
    validate_generation_batch_rows,
    write_holdout_release,
)
from enh3bench.e2e_eval_schema import (  # noqa: E402
    read_json,
    read_jsonl,
    resolve_run_target,
    write_jsonl,
)
from enh3bench.e2e_eval_validation import validate_selective_eval_package  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an API generation batch without making an API call.")
    parser.add_argument("--selective-eval-run-name", required=True)
    parser.add_argument("--selective-eval-root", type=Path, default=Path("data/selective_eval"))
    parser.add_argument("--source-calibration-root", type=Path, default=Path("data/calibration"))
    parser.add_argument("--split", choices=("development", "holdout"), default="development")
    parser.add_argument("--freeze-manifest", type=Path)
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--generation-parameters-json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        run_dir = resolve_run_target(args.selective_eval_root, args.selective_eval_run_name)
        validation = validate_selective_eval_package(
            selective_eval_run_name=args.selective_eval_run_name,
            selective_eval_root=args.selective_eval_root,
            source_calibration_root=args.source_calibration_root,
            check_source_package=False,
        )
        if validation["result"] != "PASS":
            raise ValueError("package validation failed: " + "; ".join(validation["errors"][:12]))
        batch = read_jsonl(run_dir / "cases/api_generation_batch.jsonl")
        cases = read_jsonl(run_dir / "cases/e2e_case_frame.jsonl")
        package_manifest = read_json(run_dir / "manifests/selective_eval_manifest.json")
        errors = validate_generation_batch_rows(batch, cases)
        if errors:
            raise ValueError("; ".join(errors[:12]))
        if args.split == "holdout":
            if args.freeze_manifest is None:
                raise ValueError("holdout export requires --freeze-manifest")
            if args.prompt_file is None or args.generation_parameters_json is None:
                raise ValueError(
                    "holdout export requires --prompt-file and --generation-parameters-json"
                )
            if args.output is None:
                raise ValueError("holdout export requires --output")
            freeze = read_json(args.freeze_manifest)
            if not isinstance(freeze, dict):
                raise ValueError("freeze manifest must be a JSON object")
            parameters = read_generation_parameters(args.generation_parameters_json)
            freeze_errors = validate_freeze_manifest(
                freeze, package_manifest, cases, run_dir=run_dir,
                prompt_file=args.prompt_file, generation_parameters=parameters,
            )
            if freeze_errors:
                raise ValueError("; ".join(freeze_errors[:12]))
        rows = select_generation_rows(batch, cases, split=args.split)
        output = None
        already_released = False
        if args.output:
            output = args.output.resolve()
            if args.split == "development":
                if output.exists():
                    raise FileExistsError(f"refusing to overwrite: {output}")
                write_jsonl(output, rows)
            else:
                release_status, _, _ = write_holdout_release(
                    output, rows, freeze_manifest=args.freeze_manifest,
                    selective_eval_run_name=args.selective_eval_run_name,
                )
                already_released = release_status == "already_released"
    except (OSError, ValueError) as exc:
        print(f"api_generation_batch_export: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print(
        f"api_generation_batch_export: PASS\nsplit: {args.split}\ncases: {len(rows)}"
        f"\nrelease_status: {'already_released' if already_released else 'released' if args.split == 'holdout' else 'not_applicable'}"
        f"\nnetwork_calls: 0\noutput: {output or '<not written>'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
