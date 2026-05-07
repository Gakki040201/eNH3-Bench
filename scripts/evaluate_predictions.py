from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.evaluator import CATEGORICAL_FIELDS, NUMERIC_FIELDS, evaluate_all  # noqa: E402


DEFAULT_GOLD = ROOT / "data" / "gold" / "gold.example.jsonl"
DEFAULT_PRED = ROOT / "data" / "predictions" / "rule_baseline.example.jsonl"
DEFAULT_JSON_REPORT = ROOT / "data" / "reports" / "evaluation_report.example.json"
DEFAULT_MD_REPORT = ROOT / "data" / "reports" / "evaluation_report.example.md"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number} of {path}") from exc
    return records


def write_json_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_report(report), encoding="utf-8", newline="\n")


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# eNH3-Bench Evaluation Report",
        "",
        "## Field-Level Accuracy",
        "",
        "| Field | Accuracy | Correct | Total | Missing Predictions |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for field in CATEGORICAL_FIELDS:
        item = report["categorical"][field]
        lines.append(
            f"| `{field}` | {_format_percent(item['accuracy'])} | "
            f"{item['correct']} | {item['total']} | {item['missing_predictions']} |"
        )

    lines.extend(
        [
            "",
            "## Numeric Error Summary",
            "",
            "| Field | Accuracy | Within Tolerance | Gold Values | Missing Predictions | MAE | Max Error |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for field in NUMERIC_FIELDS:
        item = report["numeric"][field]
        lines.append(
            f"| `{field}` | {_format_percent(item['accuracy'])} | "
            f"{item['within_tolerance']} | {item['total_gold_values']} | "
            f"{item['missing_predictions']} | {_format_optional_float(item['mean_absolute_error'])} | "
            f"{_format_optional_float(item['max_absolute_error'])} |"
        )

    lines.extend(
        [
            "",
            "## Grounding Diagnostics",
            "",
            f"- Hallucination rate: {_format_percent(report['hallucination_rate'])}",
            f"- Missing field rate: {_format_percent(report['missing_field_rate'])}",
            "",
            "## Brief Interpretation",
            "",
            _interpret(report),
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate eNH3-Bench predictions.")
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD, help="Gold EvidenceRecord JSONL.")
    parser.add_argument("--pred", type=Path, default=DEFAULT_PRED, help="Prediction JSONL.")
    parser.add_argument(
        "--json-output",
        type=Path,
        default=DEFAULT_JSON_REPORT,
        help="Output JSON report path.",
    )
    parser.add_argument(
        "--md-output",
        type=Path,
        default=DEFAULT_MD_REPORT,
        help="Output Markdown report path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gold_records = load_jsonl(args.gold)
    pred_records = load_jsonl(args.pred)
    report = evaluate_all(gold_records, pred_records)
    write_json_report(report, args.json_output)
    write_markdown_report(report, args.md_output)
    print(f"Wrote JSON report to {args.json_output}")
    print(f"Wrote Markdown report to {args.md_output}")
    return 0


def _format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.4g}"


def _interpret(report: dict[str, Any]) -> str:
    categorical_values = [item["accuracy"] for item in report["categorical"].values()]
    mean_categorical = sum(categorical_values) / len(categorical_values)
    hallucination = report["hallucination_rate"]
    missing = report["missing_field_rate"]
    return (
        "This report summarizes local no-API prediction quality against the gold examples. "
        f"Mean categorical accuracy is {_format_percent(mean_categorical)}, "
        f"with hallucination rate {_format_percent(hallucination)} and missing field rate "
        f"{_format_percent(missing)}. Inspect low-accuracy fields before using the baseline "
        "as a comparison point for benchmark-paper experiments."
    )


if __name__ == "__main__":
    raise SystemExit(main())
