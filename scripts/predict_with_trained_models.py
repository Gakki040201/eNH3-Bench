from __future__ import annotations

import argparse
import csv
import importlib.util
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.ledger_router import load_jsonl  # noqa: E402
from enh3bench.trainers import missing_dependency_message, triage_feature_dict  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Predict source classes and recommendations with local trained models.")
    parser.add_argument("--run-name", default="final_pilot")
    parser.add_argument("--source-model", type=Path, default=None)
    parser.add_argument("--triage-model", type=Path, default=None)
    parser.add_argument("--classified-spans", type=Path, default=None)
    parser.add_argument("--triage-scores", type=Path, default=None)
    parser.add_argument("--output-csv", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    if importlib.util.find_spec("joblib") is None:
        print(missing_dependency_message())
        return 1
    import joblib  # type: ignore[import-not-found]

    args = parse_args()
    source_model_path = args.source_model or Path("models") / f"source_span_classifier.{args.run_name}.joblib"
    triage_model_path = args.triage_model or Path("models") / f"triage_ranker.{args.run_name}.joblib"
    if not source_model_path.exists() or not triage_model_path.exists():
        print(f"Missing model: {source_model_path if not source_model_path.exists() else triage_model_path}")
        return 1

    source_bundle = joblib.load(source_model_path)
    triage_bundle = joblib.load(triage_model_path)
    classified_path = args.classified_spans or Path("data") / "ledgers" / args.run_name / "classified_spans.jsonl"
    triage_path = args.triage_scores or Path("data") / "reports" / f"experiment_triage_scores.{args.run_name}.jsonl"
    classified_spans = load_jsonl(classified_path)
    triage_records = load_jsonl(triage_path)
    triage_by_id = _index_by_id(triage_records)

    source_model = source_bundle["model"]
    triage_model = triage_bundle["model"]
    rows: list[dict[str, str]] = []
    for span in classified_spans:
        span_id = str(span.get("span_id") or "")
        evidence_id = str(span.get("evidence_id") or "")
        source_text = str(span.get("source_text") or span.get("source_span") or span.get("text") or "")
        model_text_class = str(source_model.predict([source_text])[0]) if source_text else ""
        triage_record = triage_by_id.get(evidence_id) or triage_by_id.get(span_id) or {}
        model_recommendation = ""
        if triage_record:
            model_recommendation = str(triage_model.predict([triage_feature_dict(_prediction_feature_row(triage_record))])[0])
        rows.append(
            {
                "span_id": span_id,
                "record_id": evidence_id,
                "paper_id": str(span.get("paper_id") or ""),
                "machine_text_class": str(span.get("text_class") or ""),
                "model_text_class": model_text_class,
                "machine_recommendation": str(triage_record.get("recommendation") or ""),
                "model_recommendation": model_recommendation,
            }
        )

    output_csv = args.output_csv or Path("data") / "reports" / f"model_predictions.{args.run_name}.csv"
    output_md = args.output_md or Path("data") / "reports" / f"model_predictions.{args.run_name}.md"
    _write_csv(rows, output_csv)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_render_prediction_report(rows, args.run_name), encoding="utf-8", newline="\n")
    print(f"Wrote model predictions to {output_csv}")
    print(f"Wrote model prediction report to {output_md}")
    return 0


def _prediction_feature_row(record: dict[str, Any]) -> dict[str, Any]:
    row = dict(record)
    row["FE_percent"] = row.get("FE_percent") or row.get("faradaic_efficiency_percent")
    row["EE_percent"] = row.get("EE_percent") or row.get("energy_efficiency_percent")
    row["NH3_yield"] = row.get("NH3_yield") or row.get("nh3_yield_value")
    return row


def _index_by_id(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for record in records:
        for key in ["evidence_id", "record_id", "span_id"]:
            value = str(record.get(key) or "").strip()
            if value:
                indexed[value] = record
    return indexed


def _write_csv(rows: list[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "span_id",
        "record_id",
        "paper_id",
        "machine_text_class",
        "model_text_class",
        "machine_recommendation",
        "model_recommendation",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _render_prediction_report(rows: list[dict[str, str]], run_name: str) -> str:
    text_counts = Counter(row["model_text_class"] for row in rows if row["model_text_class"])
    recommendation_counts = Counter(row["model_recommendation"] for row in rows if row["model_recommendation"])
    return "\n".join(
        [
            f"# Model Predictions: {run_name}",
            "",
            f"- Rows: {len(rows)}",
            f"- Predicted text classes: {dict(sorted(text_counts.items()))}",
            f"- Predicted recommendations: {dict(sorted(recommendation_counts.items()))}",
            "",
            "These predictions come from small local models trained on the exported CSVs, not from an LLM.",
            "",
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
