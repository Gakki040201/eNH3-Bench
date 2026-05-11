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

from enh3bench.evaluator import evaluate_all  # noqa: E402
from enh3bench.markdown_converter import convert_directory  # noqa: E402
from enh3bench.minimal_pipeline import run_minimal_review_pipeline  # noqa: E402
from enh3bench.pipeline_config import PipelineConfig  # noqa: E402
from enh3bench.review_merge import merge_reviewed_gold  # noqa: E402
from enh3bench.rule_baseline import run_rule_extraction  # noqa: E402
from scripts.evaluate_predictions import render_markdown_report  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local eNH3-Scholar evidence workflow.")
    parser.add_argument("--input-dir", type=Path, default=Path("input_raw"))
    parser.add_argument("--markdown-dir", type=Path, default=Path("input_markdown"))
    parser.add_argument("--run-name", default="v0.2")
    parser.add_argument("--top-n", type=int, default=8)
    parser.add_argument("--max-per-paper", type=int, default=3)
    parser.add_argument("--skip-conversion", action="store_true")
    parser.add_argument("--stop-at", choices=["audit", "gold", "evaluation"], default="audit")
    parser.add_argument("--review-sheet", type=Path, default=None)
    parser.add_argument("--papers", type=Path, default=Path("data/papers/papers.v0.2.template.csv"))
    return parser.parse_args()


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    config = PipelineConfig(
        input_dir=str(args.input_dir),
        markdown_dir=str(args.markdown_dir),
        run_name=args.run_name,
        top_n=args.top_n,
        max_per_paper=args.max_per_paper,
        stop_at=args.stop_at,
        skip_conversion=args.skip_conversion,
        papers_path=str(args.papers) if args.papers else None,
    )

    conversion_results: list[dict[str, Any]] = []
    if not config.skip_conversion:
        conversion_results = convert_directory(config.input_dir, config.markdown_dir)

    manifest = run_minimal_review_pipeline(
        input_markdown_dir=config.markdown_dir,
        run_name=config.run_name,
        top_n=config.top_n,
        max_per_paper=config.max_per_paper,
    )
    manifest["conversion"] = {
        "skipped": config.skip_conversion,
        "results": conversion_results,
        "summary": _status_counts(conversion_results),
    }
    _write_json(manifest, Path("data/reports") / f"workflow_manifest.{config.run_name}.json")

    if config.stop_at == "audit":
        return manifest

    review_sheet = args.review_sheet or Path("data/audit") / f"review_sheet.{config.run_name}.csv"
    gold_path = Path("data/gold") / f"gold.{config.run_name}.reviewed.jsonl"
    gold_records = _merge_if_reviewed(
        drafts_path=Path("data/drafts") / f"draft_evidence.{config.run_name}.jsonl",
        review_sheet=review_sheet,
        gold_path=gold_path,
    )
    manifest["reviewed_gold"] = str(gold_path) if gold_records is not None else None
    if config.stop_at == "gold":
        _write_json(manifest, Path("data/reports") / f"workflow_manifest.{config.run_name}.json")
        return manifest

    if gold_records is not None:
        predictions_path = Path("data/predictions") / f"rule_baseline.{config.run_name}.jsonl"
        pred_records = _run_rule_predictions(
            Path("data/candidates") / f"candidate_spans.{config.run_name}.jsonl",
            predictions_path,
        )
        evaluation = evaluate_all(gold_records, pred_records)
        json_report = Path("data/reports") / f"evaluation_report.{config.run_name}.json"
        md_report = Path("data/reports") / f"evaluation_report.{config.run_name}.md"
        _write_json(evaluation, json_report)
        md_report.write_text(render_markdown_report(evaluation), encoding="utf-8", newline="\n")
        manifest["evaluation_report_json"] = str(json_report)
        manifest["evaluation_report_md"] = str(md_report)
    _write_json(manifest, Path("data/reports") / f"workflow_manifest.{config.run_name}.json")
    return manifest


def main() -> int:
    args = parse_args()
    manifest = run_pipeline(args)
    print(f"Documents: {manifest['document_count']}")
    print(f"Candidate spans: {manifest['candidate_span_count']}")
    print(f"Draft evidence records: {manifest['draft_evidence_count']}")
    print(f"Field grounding records: {manifest['field_grounding_count']}")
    print(f"Feedback records: {manifest['draft_feedback_count']}")
    print(
        f"Next human step: open data/audit/audit_packet.{args.run_name}.md and "
        f"data/audit/review_sheet.{args.run_name}.csv"
    )
    return 0


def _merge_if_reviewed(drafts_path: Path, review_sheet: Path, gold_path: Path) -> list[dict[str, Any]] | None:
    if not review_sheet.exists():
        print(f"Review sheet not found; skipping gold merge: {review_sheet}")
        return None
    review_rows = _load_csv(review_sheet)
    if not _has_human_decisions(review_rows):
        print(f"Review sheet has no human decisions; skipping gold merge: {review_sheet}")
        return None
    drafts = _load_jsonl(drafts_path)
    gold_records = merge_reviewed_gold(drafts, review_rows)
    _write_jsonl(gold_records, gold_path)
    return gold_records


def _run_rule_predictions(spans_path: Path, output_path: Path) -> list[dict[str, Any]]:
    predictions = [run_rule_extraction(span) for span in _load_jsonl(spans_path)]
    _write_jsonl(predictions, output_path)
    return predictions


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")))
            handle.write("\n")


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _has_human_decisions(rows: list[dict[str, str]]) -> bool:
    for row in rows:
        if row.get("human_decision", "").strip() or row.get("include_in_gold", "").strip():
            return True
    return False


def _write_json(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _status_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"converted": 0, "copied": 0, "unsupported": 0, "error": 0}
    for result in results:
        status = str(result.get("status", "error"))
        counts[status if status in counts else "error"] += 1
    return counts


if __name__ == "__main__":
    raise SystemExit(main())
