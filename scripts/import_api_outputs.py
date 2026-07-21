from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.e2e_eval_metrics import validate_api_output  # noqa: E402
from enh3bench.e2e_eval_schema import (  # noqa: E402
    install_jsonl_with_validation,
    read_jsonl,
    resolve_run_target,
    write_jsonl,
)
from enh3bench.e2e_eval_validation import validate_selective_eval_package  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and import existing API outputs; never calls an API.")
    parser.add_argument("--selective-eval-run-name", required=True)
    parser.add_argument("--selective-eval-root", type=Path, default=Path("data/selective_eval"))
    parser.add_argument("--input-jsonl", type=Path, required=True)
    parser.add_argument("--output-jsonl", type=Path)
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--source-calibration-root", type=Path)
    args = parser.parse_args()
    try:
        run_dir = resolve_run_target(args.selective_eval_root, args.selective_eval_run_name)
        cases = read_jsonl(run_dir / "cases/e2e_case_frame.jsonl")
        case_by_id = {str(row["case_id"]): row for row in cases}
        rows = read_jsonl(args.input_jsonl)
        seen_outputs: set[str] = set()
        seen_cases: set[str] = set()
        errors: list[str] = []
        for index, row in enumerate(rows, 1):
            case_id = str(row.get("source_case_id") or "")
            output_id = str(row.get("api_output_id") or "")
            if case_id not in case_by_id:
                errors.append(f"row_{index}:unknown_case:{case_id}")
                continue
            if output_id in seen_outputs or case_id in seen_cases:
                errors.append(f"row_{index}:duplicate_api_output:{case_id}:{output_id}")
            seen_outputs.add(output_id)
            seen_cases.add(case_id)
            errors.extend(f"row_{index}:{error}" for error in validate_api_output(row, case_by_id[case_id]))
        if errors:
            raise ValueError("; ".join(errors[:12]))
        standard_output = (run_dir / "cases/api_outputs.jsonl").resolve()
        output = args.output_jsonl.resolve() if args.output_jsonl else standard_output
        if args.export_only:
            if args.output_jsonl is None:
                raise ValueError("--export-only requires --output-jsonl")
            if output == standard_output:
                raise ValueError("--export-only output must be outside the package standard path")
            if output.exists():
                raise FileExistsError(f"refusing to overwrite existing export: {output}")
            write_jsonl(output, rows)
            import_mode = "export_only"
        else:
            if output != standard_output:
                raise ValueError("package import output must be cases/api_outputs.jsonl; use --export-only for external paths")
            source_root = (
                args.source_calibration_root.resolve() if args.source_calibration_root
                else args.selective_eval_root.resolve().parent / "calibration"
            )
            install_jsonl_with_validation(
                standard_output, rows,
                lambda: validate_selective_eval_package(
                    selective_eval_run_name=args.selective_eval_run_name,
                    selective_eval_root=args.selective_eval_root,
                    source_calibration_root=source_root,
                    check_source_package=False,
                ),
            )
            import_mode = "package"
    except (OSError, ValueError) as exc:
        print(f"api_output_import: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print(
        f"api_output_import: PASS\nimport_mode: {import_mode}\noutputs: {len(rows)}"
        f"\napi_calls: 0\noutput: {output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
