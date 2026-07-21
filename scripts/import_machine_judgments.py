from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.e2e_eval_metrics import validate_machine_judgment  # noqa: E402
from enh3bench.e2e_eval_schema import read_jsonl, resolve_run_target, write_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and import existing machine judgments; never calls a judge API.")
    parser.add_argument("--selective-eval-run-name", required=True)
    parser.add_argument("--selective-eval-root", type=Path, default=Path("data/selective_eval"))
    parser.add_argument("--input-jsonl", type=Path, required=True)
    parser.add_argument("--output-jsonl", type=Path)
    args = parser.parse_args()
    try:
        run_dir = resolve_run_target(args.selective_eval_root, args.selective_eval_run_name)
        templates = read_jsonl(run_dir / "cases/machine_judgment_template.jsonl")
        template_by_id = {str(row["machine_judgment_id"]): row for row in templates}
        cases = read_jsonl(run_dir / "cases/e2e_case_frame.jsonl")
        case_by_id = {str(row["case_id"]): row for row in cases}
        imported_outputs_path = run_dir / "cases/api_outputs.jsonl"
        if not imported_outputs_path.is_file():
            raise ValueError("machine judgments require previously imported API outputs")
        imported_output_by_id = {
            str(row.get("api_output_id") or ""): row for row in read_jsonl(imported_outputs_path)
        }
        rows = read_jsonl(args.input_jsonl)
        seen_ids: set[str] = set()
        seen_observations: set[tuple[str, str]] = set()
        errors: list[str] = []
        for index, row in enumerate(rows, 1):
            judgment_id = str(row.get("machine_judgment_id") or "")
            template = template_by_id.get(judgment_id)
            if template is None:
                errors.append(f"row_{index}:unknown_judgment:{judgment_id}")
                continue
            case_id = str(row.get("source_case_id") or "")
            if case_id not in case_by_id:
                errors.append(f"row_{index}:unknown_case:{case_id}")
                continue
            output_id = str(row.get("source_api_output_id") or "")
            if output_id not in imported_output_by_id:
                errors.append(f"row_{index}:unknown_api_output:{row.get('source_api_output_id')}")
                continue
            observation = (str(row.get("source_case_id") or ""), str(row.get("judge_id") or ""))
            if judgment_id in seen_ids or observation in seen_observations:
                errors.append(f"row_{index}:duplicate_machine_judgment:{observation}")
            seen_ids.add(judgment_id)
            seen_observations.add(observation)
            errors.extend(
                f"row_{index}:{error}"
                for error in validate_machine_judgment(
                    row, template, case_by_id[case_id], imported_output_by_id[output_id]
                )
            )
        if errors:
            raise ValueError("; ".join(errors[:12]))
        output = args.output_jsonl.resolve() if args.output_jsonl else run_dir / "cases/machine_judgments.jsonl"
        if output.exists():
            raise FileExistsError(f"refusing to overwrite existing machine judgments: {output}")
        write_jsonl(output, rows)
    except (OSError, ValueError) as exc:
        print(f"machine_judgment_import: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print(f"machine_judgment_import: PASS\njudgments: {len(rows)}\njudge_calls: 0\noutput: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
