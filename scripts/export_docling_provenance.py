from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.document_provenance import (  # noqa: E402
    export_provenance_records,
    extract_provenance_from_docling_json,
    infer_provenance_for_record,
    load_docling_json,
    summarize_provenance,
)
from enh3bench.evidence_bundle import load_records_from_ledgers  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Docling-style provenance for eNH3-BoundaryLedger.")
    parser.add_argument("--run-name", default="final_pilot")
    parser.add_argument("--docling-json-dir", type=Path, default=Path("input_docling_json"))
    parser.add_argument("--ledger-dir", type=Path, default=Path("data") / "ledgers")
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "provenance")
    parser.add_argument("--report-dir", type=Path, default=Path("data") / "reports")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records, sources = _load_docling_or_fallback(args.run_name, args.docling_json_dir, args.ledger_dir)
    for record in records:
        record.setdefault("run_name", args.run_name)
    outputs = export_provenance_records(records, args.run_name, args.output_dir)
    run_dir = args.output_dir / args.run_name
    _write_summary_csv(records, run_dir / "provenance_summary.csv")
    _write_category_files(records, run_dir)
    report_path = args.report_dir / f"provenance_report.{args.run_name}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(args.run_name, records, sources), encoding="utf-8", newline="\n")

    summary = summarize_provenance(records)
    print(f"Provenance records: {outputs['count']}")
    print(f"Source files used: {len(sources)}")
    print(f"Source span provenance: {outputs['jsonl']}")
    print(f"Summary CSV: {run_dir / 'provenance_summary.csv'}")
    print(f"Report: {report_path}")
    print("Distribution: " + ", ".join(f"{key}={value}" for key, value in summary["provenance_type_counts"].items()))
    print(
        "Recognized section coverage: "
        f"{summary['recognized_section_count']}/{summary['total']} "
        f"({summary['recognized_section_coverage']:.1%})"
    )
    return 0


def _load_docling_or_fallback(
    run_name: str,
    docling_json_dir: Path,
    ledger_dir: Path,
) -> tuple[list[dict[str, Any]], list[str]]:
    records: list[dict[str, Any]] = []
    sources: list[str] = []
    if docling_json_dir.exists():
        for path in sorted(docling_json_dir.glob("*.json")):
            data = load_docling_json(path)
            if not data:
                continue
            paper_id = path.stem
            extracted = extract_provenance_from_docling_json(data, paper_id=paper_id)
            if extracted:
                records.extend(extracted)
                sources.append(str(path))
    if records:
        return records, sources

    fallback = load_records_from_ledgers(run_name, ledger_dir)
    records = [infer_provenance_for_record(record) for record in fallback]
    return records, [str(ledger_dir / run_name)]


def _write_summary_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    summary = summarize_provenance(records)
    rows = []
    for provenance_type, count in sorted(summary["provenance_type_counts"].items()):
        rows.append(
            {
                "provenance_type": provenance_type,
                "count": count,
                "section_type_distribution": json.dumps(summary["section_type_counts"], sort_keys=True),
                "body_confidence_distribution": json.dumps(summary["body_confidence_counts"], sort_keys=True),
                "recognized_section_count": summary["recognized_section_count"],
                "recognized_section_coverage": f"{summary['recognized_section_coverage']:.6f}",
                "unsectioned_body_count": summary["unsectioned_body_count"],
                "is_primary_admissible": provenance_type in {"body", "abstract", "methods", "results", "discussion"},
                "is_secondary_or_context": provenance_type in {"table", "review_table", "figure_caption", "scheme_caption", "supplementary"},
                "is_reject_or_low_trust": provenance_type in {"reference", "bibliography", "front_matter", "metadata", "copyright_note"},
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "provenance_type",
            "count",
            "section_type_distribution",
            "body_confidence_distribution",
            "recognized_section_count",
            "recognized_section_coverage",
            "unsectioned_body_count",
            "is_primary_admissible",
            "is_secondary_or_context",
            "is_reject_or_low_trust",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_category_files(records: list[dict[str, Any]], run_dir: Path) -> None:
    categories = {
        "table_spans.jsonl": {"table", "review_table"},
        "caption_spans.jsonl": {"figure_caption", "scheme_caption"},
        "reference_spans.jsonl": {"reference", "bibliography"},
        "front_matter_spans.jsonl": {"front_matter", "metadata", "copyright_note"},
    }
    for filename, provenance_types in categories.items():
        selected = [record for record in records if str(record.get("provenance_type") or "") in provenance_types]
        _write_jsonl(selected, run_dir / filename)


def _render_report(run_name: str, records: list[dict[str, Any]], sources: list[str]) -> str:
    summary = summarize_provenance(records)
    counter = Counter(str(record.get("provenance_type") or "unknown") for record in records)
    lines = [
        f"# Provenance Hardening Report: {run_name}",
        "",
        "## 1. What provenance hardening adds",
        "",
        (
            "This pass marks whether each span came from primary body text, tables, captions, "
            "references, front matter, metadata, or supplementary context before claim-rights adjudication."
        ),
        "",
        "## 2. Source files used",
        "",
        _list_or_none(sources),
        "",
        "## 3. Provenance type distribution",
        "",
        _counter_table(counter, "Provenance type"),
        "",
        "## 4. Primary-admissible span count",
        "",
        f"- {summary['primary_admissible_count']}",
        "",
        "## 5. Section type distribution",
        "",
        _counter_table(Counter({key: int(value) for key, value in summary["section_type_counts"].items()}), "Section type"),
        "",
        "## 6. Body confidence distribution",
        "",
        _counter_table(Counter({key: int(value) for key, value in summary["body_confidence_counts"].items()}), "Confidence"),
        "",
        "## 7. Recognized-section coverage",
        "",
        f"- Recognized section records: {summary['recognized_section_count']} / {summary['total']} ({summary['recognized_section_coverage']:.1%})",
        f"- Unsectioned body records: {summary['unsectioned_body_count']}",
        "",
        "## 8. Secondary/context span count",
        "",
        f"- {summary['secondary_or_context_count']}",
        "",
        "## 9. Reject/low-trust span count",
        "",
        f"- {summary['reject_or_low_trust_count']}",
        "",
        "## 10. Table/review-table examples",
        "",
        _examples(records, {"table", "review_table"}),
        "",
        "## 11. Figure caption examples",
        "",
        _examples(records, {"figure_caption", "scheme_caption"}),
        "",
        "## 12. Reference/front-matter examples",
        "",
        _examples(records, {"reference", "bibliography", "front_matter", "metadata", "copyright_note"}),
        "",
        "## 13. Consequences for claim-rights adjudication",
        "",
        (
            "Reference, bibliography, metadata, copyright, and front-matter spans are low trust for "
            "primary performance boundaries. Review tables remain secondary. Captions and ordinary "
            "tables require paired primary body text before stronger claim rights are allowed."
        ),
        "",
    ]
    return "\n".join(lines)


def _examples(records: list[dict[str, Any]], provenance_types: set[str], limit: int = 5) -> str:
    rows = []
    for record in records:
        if str(record.get("provenance_type") or "") not in provenance_types:
            continue
        rows.append(
            [
                record.get("source_span_id") or "",
                record.get("paper_id") or "",
                record.get("provenance_type") or "",
                record.get("provenance_confidence") or "",
                _preview(record.get("source_text") or ""),
            ]
        )
        if len(rows) >= limit:
            break
    if not rows:
        return "No examples in this run."
    return _markdown_table(["Span", "Paper", "Type", "Confidence", "Preview"], rows)


def _list_or_none(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- `{item}`" for item in items)


def _counter_table(counter: Counter[str], label: str) -> str:
    if not counter:
        return "No records."
    rows = [[key, count] for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))]
    return _markdown_table([label, "Records"], rows)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_escape_cell(value) for value in row) + " |")
    return "\n".join(lines)


def _escape_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _preview(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, default=str, separators=(",", ":")))
            handle.write("\n")


if __name__ == "__main__":
    raise SystemExit(main())
