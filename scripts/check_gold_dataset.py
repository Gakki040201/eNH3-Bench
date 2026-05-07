from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.schema import evidence_from_dict, validate_evidence_record  # noqa: E402


DEFAULT_REPORT = ROOT / "data" / "reports" / "gold_dataset_check.md"


def load_papers_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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


def check_gold_dataset(
    papers_path: Path,
    spans_path: Path,
    gold_path: Path,
    allow_empty_source_span: bool = False,
    report_path: Path = DEFAULT_REPORT,
) -> dict[str, Any]:
    papers = load_papers_csv(papers_path)
    spans = load_jsonl(spans_path)
    gold_records = load_jsonl(gold_path)

    errors: list[str] = []
    warnings: list[str] = []
    paper_ids = {row.get("paper_id", "").strip() for row in papers if row.get("paper_id", "").strip()}

    if len(paper_ids) != len(papers):
        errors.append("papers CSV contains empty or duplicate paper_id values")

    for span in spans:
        paper_id = str(span.get("paper_id", "")).strip()
        span_id = str(span.get("span_id", "")).strip()
        if not paper_id:
            errors.append(f"span {span_id or '<missing span_id>'} has empty paper_id")
        elif paper_id not in paper_ids:
            errors.append(f"span {span_id or '<missing span_id>'} references missing paper_id {paper_id}")

    for index, gold in enumerate(gold_records, start=1):
        evidence_id = str(gold.get("evidence_id", f"<record {index}>")).strip() or f"<record {index}>"
        paper_id = str(gold.get("paper_id", "")).strip()
        if not paper_id:
            errors.append(f"gold {evidence_id} has empty paper_id")
        elif paper_id not in paper_ids:
            errors.append(f"gold {evidence_id} references missing paper_id {paper_id}")

        try:
            record = evidence_from_dict(gold)
        except TypeError as exc:
            errors.append(f"gold {evidence_id} cannot be parsed as EvidenceRecord: {exc}")
            continue

        for message in validate_evidence_record(record):
            if allow_empty_source_span and message == "error: source_span is required":
                continue
            if message.startswith("warning:"):
                warnings.append(f"{evidence_id}: {message}")
            else:
                errors.append(f"{evidence_id}: {message}")

        if not allow_empty_source_span and not str(gold.get("source_span", "")).strip():
            source_span_error = f"{evidence_id}: source_span is empty in final mode"
            if source_span_error not in errors:
                errors.append(source_span_error)

    summary = {
        "paper_count": len(papers),
        "span_count": len(spans),
        "gold_count": len(gold_records),
        "reaction_family": _count_field(gold_records, "reaction_family"),
        "reliability_label": _count_field(gold_records, "reliability_label"),
        "evidence_type": _count_field(gold_records, "evidence_type"),
    }
    result = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": summary,
    }
    write_markdown_report(result, report_path)
    return result


def write_markdown_report(result: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_report(result), encoding="utf-8", newline="\n")


def render_markdown_report(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# Gold Dataset Check",
        "",
        f"- Status: {'PASS' if result['ok'] else 'FAIL'}",
        f"- Papers: {summary['paper_count']}",
        f"- Source spans: {summary['span_count']}",
        f"- Gold records: {summary['gold_count']}",
        "",
        "## Reaction Family Counts",
        "",
        _counts_table(summary["reaction_family"], "reaction_family"),
        "",
        "## Reliability Label Counts",
        "",
        _counts_table(summary["reliability_label"], "reliability_label"),
        "",
        "## Evidence Type Counts",
        "",
        _counts_table(summary["evidence_type"], "evidence_type"),
        "",
        "## Errors",
        "",
        *_message_lines(result["errors"]),
        "",
        "## Warnings",
        "",
        *_message_lines(result["warnings"]),
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an eNH3-Bench gold dataset.")
    parser.add_argument("--papers", type=Path, required=True, help="Paper metadata CSV.")
    parser.add_argument("--spans", type=Path, required=True, help="Source span JSONL.")
    parser.add_argument("--gold", type=Path, required=True, help="Gold EvidenceRecord JSONL.")
    parser.add_argument(
        "--allow-empty-source-span",
        action="store_true",
        help="Allow empty gold source_span values for template scaffolds.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help="Markdown report output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = check_gold_dataset(
        papers_path=args.papers,
        spans_path=args.spans,
        gold_path=args.gold,
        allow_empty_source_span=args.allow_empty_source_span,
        report_path=args.report,
    )
    print(f"Wrote gold dataset check report to {args.report}")
    if result["ok"]:
        print("Gold dataset check passed")
        return 0
    print("Gold dataset check failed")
    for error in result["errors"]:
        print(f"- {error}")
    return 1


def _count_field(records: Iterable[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(str(record.get(field, "<missing>") or "<missing>") for record in records)
    return dict(sorted(counts.items()))


def _counts_table(counts: dict[str, int], field: str) -> str:
    lines = [f"| {field} | Count |", "| --- | ---: |"]
    for value, count in counts.items():
        lines.append(f"| `{value}` | {count} |")
    if not counts:
        lines.append("| `<none>` | 0 |")
    return "\n".join(lines)


def _message_lines(messages: list[str]) -> list[str]:
    if not messages:
        return ["- None"]
    return [f"- {message}" for message in messages]


if __name__ == "__main__":
    raise SystemExit(main())
