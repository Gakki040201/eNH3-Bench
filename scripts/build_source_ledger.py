from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.context_packet import merge_context_sources  # noqa: E402
from enh3bench.ledger_router import load_jsonl  # noqa: E402
from enh3bench.source_ledger import (  # noqa: E402
    attach_source_coordinates_to_spans,
    build_ordered_source_ledger,
    export_source_ledger,
    sort_spans_by_source_order,
)
from enh3bench.span_identity import attach_span_identity  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the ordered Markdown Source Ledger.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--markdown-dir", type=Path, default=Path("input_markdown"))
    parser.add_argument("--evidence-bundles", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "source_ledgers")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence_path = args.evidence_bundles or Path("data") / "boundary_ledger" / args.run_name / "evidence_bundles.jsonl"
    provenance_path = args.provenance or Path("data") / "provenance" / args.run_name / "source_span_provenance.jsonl"
    evidence = load_jsonl(evidence_path)
    if not evidence:
        print(f"No evidence bundles found: {evidence_path}")
        return 1
    provenance = load_jsonl(provenance_path)
    source_ids = [str(record.get("source_span_id") or "") for record in evidence]
    merged = merge_context_sources(evidence, [], [], provenance)
    ledger = build_ordered_source_ledger(args.markdown_dir)
    attached = attach_span_identity(attach_source_coordinates_to_spans(merged, ledger))
    attached = sort_spans_by_source_order(attached)
    outputs = export_source_ledger(
        ledger, attached, args.run_name, args.output_dir, original_span_ids=source_ids
    )
    summary = outputs["summary_data"]
    for key in (
        "document_count", "section_count", "paragraph_count", "span_count",
        "verified_span_mapping_count", "unresolved_span_mapping_count", "multiple_exact_match_count",
        "source_locator_coverage", "duplicate_source_locator_count", "source_order_violation_count",
        "offset_overlap_violation_count", "source_span_id_changed_count",
    ):
        print(f"{key}: {summary[key]}")
    print(f"summary: {outputs['summary']}")
    return 0 if (
        summary["source_span_id_changed_count"] == 0
        and summary["duplicate_source_locator_count"] == 0
        and summary["source_order_violation_count"] == 0
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
