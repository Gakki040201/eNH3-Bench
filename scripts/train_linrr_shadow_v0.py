#!/usr/bin/env python
"""Train (or refuse to train) LiNRR literature shadow predictor v0."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.linrr_predictor import load_jsonl, secondary_target_assessment, train_grouped_models, write_training_outputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(r"F:\eNH3_Bench_Work\02_Data\Experiment_Records\LiNRR_Training_v0\model_eligible_records.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path(r"F:\eNH3_Bench_Work\02_Data\Modeling\LiNRR_Shadow_v0"))
    args = parser.parse_args()
    records = load_jsonl(args.dataset)
    result = train_grouped_models(records)
    result["secondary_target_gate"] = secondary_target_assessment(records, result["gate"]["passed"])
    write_training_outputs(result, args.output_dir, args.dataset, ROOT)
    print(json.dumps({"gate": result["gate"], "a_only_gate": result.get("a_only_gate"), "metrics": result["metrics"], "output_dir": str(args.output_dir)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
