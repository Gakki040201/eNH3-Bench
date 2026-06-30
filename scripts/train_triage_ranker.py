from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.trainers import missing_dependency_message, train_triage_ranker  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a local eNH3-TriageBench recommendation ranker.")
    parser.add_argument("--run-name", default="final_pilot")
    parser.add_argument("--training-csv", type=Path, default=None)
    parser.add_argument("--model-output", type=Path, default=None)
    parser.add_argument("--report-output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    training_csv = args.training_csv or Path("data") / "training" / f"triage_training.{args.run_name}.csv"
    model_output = args.model_output or Path("models") / f"triage_ranker.{args.run_name}.joblib"
    report_output = args.report_output or Path("data") / "reports" / f"triage_ranker_training.{args.run_name}.md"
    try:
        result = train_triage_ranker(training_csv, model_output, report_output)
    except RuntimeError:
        print(missing_dependency_message())
        return 1
    except (OSError, ValueError) as exc:
        print(f"Training failed: {exc}")
        return 1
    print(f"Trained triage ranker: {result['model_path']}")
    print(f"Training report: {result['report_path']}")
    if result["smoke_warning"]:
        print("Warning: fewer than 20 labeled rows or one label class; this is a smoke model only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
