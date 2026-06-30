from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.training_dataset import build_training_datasets  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build local training CSVs from eNH3-TriageBench outputs.")
    parser.add_argument("--run-name", default="final_pilot")
    parser.add_argument("--classified-spans", type=Path, default=None)
    parser.add_argument("--human-review-sheet", type=Path, default=None)
    parser.add_argument("--reviewed-gold", type=Path, default=None)
    parser.add_argument("--triage-scores", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "training")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_training_datasets(
        run_name=args.run_name,
        classified_spans_path=args.classified_spans,
        human_review_sheet_path=args.human_review_sheet,
        reviewed_gold_path=args.reviewed_gold,
        triage_scores_path=args.triage_scores,
        output_dir=args.output_dir,
    )
    print(f"Source span training rows: {result['source_span_rows']}")
    print(f"Triage training rows: {result['triage_rows']}")
    print(f"Source span training CSV: {result['source_span_training_csv']}")
    print(f"Triage training CSV: {result['triage_training_csv']}")
    if result["human_review_rows"] == 0 and result["reviewed_gold_rows"] == 0:
        print("No human labels found; label_source=weak_rule_label was used.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
