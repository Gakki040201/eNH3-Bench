from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.benchmark_metrics import evaluate_all_tasks, flatten_metrics, metric_summary_counts  # noqa: E402
from enh3bench.benchmark_schema import BENCHMARK_TASKS  # noqa: E402
from enh3bench.ledger_router import load_jsonl  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate eNH3-BoundaryBench rule and LLM baselines.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--split", choices=("train", "dev", "test", "all"), default="all")
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "benchmarks")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tasks = _load_tasks(args.run_name, args.output_dir, args.split)
    if not any(tasks.values()):
        print(f"No benchmark task records found for run {args.run_name}. Run build_boundary_benchmark first.")
        return 1
    results = evaluate_all_tasks(tasks)
    paths = _export_evaluation(results, tasks, args.run_name, args.output_dir)
    summary = metric_summary_counts(tasks)

    print(f"tasks_evaluated: {len([name for name, rows in tasks.items() if rows])}")
    print(f"reviewed_records: {summary['reviewed_records']}")
    for row in flatten_metrics(results):
        if row.get("baseline") == "rule":
            metric = row.get("accuracy", row.get("exact_match", ""))
            print(f"{row['task_name']}.rule: records={row.get('records_evaluated', 0)} metric={metric}")
    print(f"metrics_csv: {paths['csv']}")
    print(f"metrics_json: {paths['json']}")
    print(f"report: {paths['report']}")
    return 0


def _load_tasks(run_name: str, output_dir: Path, split: str) -> dict[str, list[dict[str, Any]]]:
    run_dir = output_dir / run_name
    tasks: dict[str, list[dict[str, Any]]] = {}
    for task_name in BENCHMARK_TASKS:
        if split == "all":
            path = run_dir / f"{task_name}.jsonl"
        else:
            path = run_dir / "splits" / f"{task_name}.{split}.jsonl"
        tasks[task_name] = load_jsonl(path)
    return tasks


def _export_evaluation(
    results: dict[str, dict[str, dict[str, Any]]],
    tasks: dict[str, list[dict[str, Any]]],
    run_name: str,
    output_dir: Path,
) -> dict[str, str]:
    eval_dir = output_dir / run_name / "evaluation"
    eval_dir.mkdir(parents=True, exist_ok=True)
    rows = flatten_metrics(results)
    csv_path = eval_dir / "benchmark_eval_metrics.csv"
    json_path = eval_dir / "benchmark_eval_metrics.json"
    report_path = Path("data") / "reports" / f"boundary_benchmark_evaluation.{run_name}.md"
    _write_csv(rows, csv_path)
    json_path.write_text(json.dumps(results, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(results, tasks, run_name), encoding="utf-8", newline="\n")
    return {"csv": str(csv_path), "json": str(json_path), "report": str(report_path)}


def _render_report(
    results: dict[str, dict[str, dict[str, Any]]],
    tasks: dict[str, list[dict[str, Any]]],
    run_name: str,
) -> str:
    summary = metric_summary_counts(tasks)
    rows = flatten_metrics(results)
    return "\n".join(
        [
            f"# eNH3-BoundaryBench Evaluation: {run_name}",
            "",
            "## 1. Tasks evaluated",
            "",
            _markdown_table(["Task", "Records"], [[name, len(records)] for name, records in tasks.items()]),
            "",
            "## 2. Reviewed records",
            "",
            f"- Reviewed records represented per full task: {summary['reviewed_records']}",
            "",
            "## 3. Rule baseline metrics",
            "",
            _metrics_table([row for row in rows if row.get("baseline") == "rule"]),
            "",
            "## 4. LLM baseline metrics if available",
            "",
            _metrics_table([row for row in rows if row.get("baseline") == "llm"]),
            "",
            "## 5. Boundary overclaim/underclaim",
            "",
            _boundary_line(results),
            "",
            "## 6. Required-control prediction",
            "",
            _task_line(results, "required_control_prediction"),
            "",
            "## 7. Hidden-tax detection",
            "",
            _task_line(results, "hidden_tax_detection"),
            "",
            "## 8. Experiment-decision ranking",
            "",
            _task_line(results, "experiment_decision_ranking"),
            "",
            "## 9. Records needing improvement",
            "",
            "Use low rule accuracy, low Jaccard, overclaim rows, and required-control misses to select rule refinements.",
            "",
            "## 10. Limitations",
            "",
            "Metrics depend on imported human-reviewed records. LLM baselines are reported only where LLM fields are present.",
            "",
        ]
    )


def _boundary_line(results: dict[str, dict[str, dict[str, Any]]]) -> str:
    rule = results.get("claim_rights_boundary_classification", {}).get("rule", {})
    llm = results.get("claim_rights_boundary_classification", {}).get("llm", {})
    return (
        f"- Rule overclaim rate: {rule.get('overclaim_rate', 0)}\n"
        f"- Rule underclaim rate: {rule.get('underclaim_rate', 0)}\n"
        f"- LLM overclaim rate: {llm.get('overclaim_rate', 0)}\n"
        f"- LLM underclaim rate: {llm.get('underclaim_rate', 0)}"
    )


def _task_line(results: dict[str, dict[str, dict[str, Any]]], task_name: str) -> str:
    rule = results.get(task_name, {}).get("rule", {})
    llm = results.get(task_name, {}).get("llm", {})
    return (
        f"- Rule records: {rule.get('records_evaluated', 0)}\n"
        f"- Rule exact/accuracy: {rule.get('exact_match', rule.get('accuracy', 0))}\n"
        f"- Rule Jaccard/F1: {rule.get('jaccard_mean', rule.get('f1', 0))}\n"
        f"- LLM records: {llm.get('records_evaluated', 0)}"
    )


def _metrics_table(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No metrics."
    selected = []
    for row in rows:
        selected.append(
            [
                row.get("task_name", ""),
                row.get("records_evaluated", 0),
                row.get("accuracy", row.get("exact_match", "")),
                row.get("macro_f1", row.get("jaccard_mean", row.get("f1", ""))),
                row.get("overclaim_rate", ""),
                row.get("underclaim_rate", ""),
            ]
        )
    return _markdown_table(["Task", "Records", "Accuracy/Exact", "F1/Jaccard", "Overclaim", "Underclaim"], selected)


def _write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames or ["metric"])
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple, set)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return str(value)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "No records."
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in row) + " |")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
