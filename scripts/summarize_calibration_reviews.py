from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.calibration_metrics import classification_metrics, summarize_reviews  # noqa: E402
from enh3bench.calibration_schema import read_csv, write_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize future v0.16 human calibration reviews.")
    parser.add_argument("--calibration-run-name", required=True)
    parser.add_argument("--calibration-root", type=Path, default=Path("data/calibration"))
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--class-label-pairs-jsonl", type=Path,
        help="Optional adjudicated JSONL with predicted_label and corrected_label; never inferred from correctness labels.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.calibration_root / args.calibration_run_name
    try:
        rows = {
            item_type: read_csv(run_dir / f"review/{item_type}_review.csv")
            for item_type in ("span", "paper", "document", "link")
        }
        result = summarize_reviews(rows)
        first_row = next((row for values in rows.values() for row in values), {})
        result.update({
            "schema_version": first_row.get("schema_version", "0.16-calibration.1"),
            "calibration_profile": first_row.get("calibration_profile", "human_semantic_calibration_round1_v1"),
            "calibration_run_name": args.calibration_run_name,
            "source_cleanroom_run_name": first_row.get("source_cleanroom_run_name", ""),
            "source_cleanroom_manifest_sha256": first_row.get("source_cleanroom_manifest_sha256", ""),
            "record_created_by_stage": "metrics",
        })
        if args.class_label_pairs_jsonl:
            pairs = []
            with args.class_label_pairs_jsonl.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        value = json.loads(line)
                        pairs.append((str(value.get("predicted_label") or ""), str(value.get("corrected_label") or "")))
            result["class_label_metrics"] = classification_metrics(pairs)
        output = args.output or (run_dir / "reports/calibration_metrics_summary.json")
        write_json(output, result)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"calibration_metrics: FAIL\n- {exc}", file=sys.stderr)
        return 1
    print(f"calibration_metrics: {result['status']}")
    print("row_completeness: " + json.dumps(result["row_completeness"], sort_keys=True))
    print("item_coverage: " + json.dumps(result["item_coverage"], sort_keys=True))
    print("reviewer_coverage: " + json.dumps(result["reviewer_coverage"], sort_keys=True))
    print("reviewer_agreement: " + json.dumps(result["reviewer_agreement"], sort_keys=True))
    print("correctness_metrics: " + json.dumps(result["correctness_metrics"], sort_keys=True))
    print("class_label_metrics: " + json.dumps(result["class_label_metrics"], sort_keys=True))
    if result["validation_errors"]:
        for error in result["validation_errors"]:
            print(f"- ERROR: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
