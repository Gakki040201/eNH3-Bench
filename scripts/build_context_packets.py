from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.context_packet import (  # noqa: E402
    build_context_packets,
    export_context_packets,
    export_semantic_sample,
    summarize_context_packets,
)
from enh3bench.document_context import build_document_context_index  # noqa: E402
from enh3bench.evidence_linking import (  # noqa: E402
    HIERARCHICAL_LINKING_PROFILE,
    KEYWORD_LINKING_PROFILE,
    ORDERED_SOURCE_PROFILE,
)
from enh3bench.source_ledger import build_ordered_source_ledger  # noqa: E402
from enh3bench.ledger_router import load_jsonl  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build paper-scoped Evidence Context Packets.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--evidence-bundles", type=Path)
    parser.add_argument("--claim-rights", type=Path)
    parser.add_argument("--hidden-tax", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "context_packets")
    parser.add_argument("--report-dir", type=Path, default=Path("data") / "reports")
    parser.add_argument("--markdown-dir", type=Path, default=Path("input_markdown"))
    parser.add_argument(
        "--context-profile",
        choices=(KEYWORD_LINKING_PROFILE, HIERARCHICAL_LINKING_PROFILE, ORDERED_SOURCE_PROFILE),
        default=HIERARCHICAL_LINKING_PROFILE,
    )
    parser.add_argument("--minimum-link-score", type=float, default=0.60)
    parser.add_argument("--local-paragraphs-before", type=int, default=1)
    parser.add_argument("--local-paragraphs-after", type=int, default=1)
    parser.add_argument("--section-chunk-max-characters", type=int, default=12000)
    parser.add_argument("--adjacent-before", type=int, default=1)
    parser.add_argument("--adjacent-after", type=int, default=1)
    parser.add_argument("--same-section-maximum", type=int, default=4)
    parser.add_argument("--maximum-per-category", type=int, default=2)
    parser.add_argument("--maximum-total-links", type=int, default=12)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    boundary_dir = Path("data") / "boundary_ledger" / args.run_name
    provenance_dir = Path("data") / "provenance" / args.run_name
    evidence_path = args.evidence_bundles or boundary_dir / "evidence_bundles.jsonl"
    claim_path = args.claim_rights or boundary_dir / "claim_rights_ledger.jsonl"
    hidden_path = args.hidden_tax or boundary_dir / "hidden_tax_ledger.jsonl"
    provenance_path = args.provenance or provenance_dir / "source_span_provenance.jsonl"
    evidence = load_jsonl(evidence_path)
    if not evidence:
        print(f"No evidence bundles found: {evidence_path}")
        return 1
    claims = load_jsonl(claim_path)
    hidden = load_jsonl(hidden_path)
    provenance = load_jsonl(provenance_path)
    source_ledger = (
        build_ordered_source_ledger(args.markdown_dir)
        if args.context_profile == ORDERED_SOURCE_PROFILE
        else None
    )
    document_index = (
        build_document_context_index(args.markdown_dir)
        if args.context_profile == HIERARCHICAL_LINKING_PROFILE
        else None
    )
    packets = build_context_packets(
        evidence, claims, hidden, provenance,
        run_name=args.run_name,
        context_profile=args.context_profile,
        document_context_index=document_index,
        source_ledger=source_ledger,
        minimum_link_score=args.minimum_link_score,
        adjacent_before=args.adjacent_before,
        adjacent_after=args.adjacent_after,
        same_section_maximum=args.same_section_maximum,
        maximum_per_category=args.maximum_per_category,
        maximum_total_links=args.maximum_total_links,
        local_paragraphs_before=args.local_paragraphs_before,
        local_paragraphs_after=args.local_paragraphs_after,
        section_chunk_max_characters=args.section_chunk_max_characters,
    )
    legacy_comparison = None
    if args.context_profile in {HIERARCHICAL_LINKING_PROFILE, ORDERED_SOURCE_PROFILE}:
        legacy_packets = build_context_packets(
            evidence, claims, hidden, provenance,
            run_name=args.run_name,
            context_profile=KEYWORD_LINKING_PROFILE,
            adjacent_before=args.adjacent_before,
            adjacent_after=args.adjacent_after,
            same_section_maximum=args.same_section_maximum,
            maximum_per_category=args.maximum_per_category,
            maximum_total_links=args.maximum_total_links,
        )
        legacy_comparison = summarize_context_packets(legacy_packets, args.run_name)
    outputs = export_context_packets(
        packets, args.run_name, output_dir=args.output_dir, report_dir=args.report_dir,
        context_profile=args.context_profile,
        legacy_keyword_linking_comparison=legacy_comparison,
    )
    summary = outputs["summary_data"]
    print(f"context_packets: {summary['packet_count']}")
    print(f"papers: {summary['paper_count']}")
    if args.context_profile in {HIERARCHICAL_LINKING_PROFILE, ORDERED_SOURCE_PROFILE}:
        print(f"classification_context_sufficient: {summary['classification_context_sufficient_count']}")
        print(f"claim_support_context_sufficient: {summary['claim_support_context_sufficient_count']}")
        print(f"unique_evidence_total: {summary['unique_evidence_total']}")
        print(f"links_below_threshold: {summary['links_below_threshold']}")
        print(f"self_link_count: {summary['self_link_count']}")
        print(f"duplicate_serialized_span_count: {summary['duplicate_serialized_span_count']}")
        print(f"context_hint_positive_overlap_count: {summary['context_hint_positive_overlap_count']}")
        if args.context_profile == ORDERED_SOURCE_PROFILE:
            print(f"claim_support_applicable_count: {summary['claim_support_applicable_count']}")
            print(f"claim_support_sufficient_among_applicable: {summary['claim_support_sufficient_among_applicable']}")
    else:
        print(f"context_sufficient: {summary['packets_with_context_sufficient']}")
        print(f"context_insufficient: {summary['packets_with_context_insufficient']}")
    print(f"cross_paper_link_count: {summary['cross_paper_link_count']}")
    print(f"reference_primary_support_count: {summary['reference_primary_support_count']}")
    print(f"caption_primary_support_count: {summary['caption_primary_support_count']}")
    print(f"review_table_primary_support_count: {summary['review_table_primary_support_count']}")
    print(f"jsonl: {outputs['jsonl']}")
    print(f"csv: {outputs['csv']}")
    print(f"summary: {outputs['summary']}")
    print(f"report: {outputs['report']}")
    if args.context_profile == HIERARCHICAL_LINKING_PROFILE:
        sample = export_semantic_sample(packets, args.run_name, report_dir=args.report_dir, seed=13)
        print(f"semantic_sample: {sample}")
    return 0 if (
        summary["cross_paper_link_count"] == 0
        and summary.get("self_link_count", 0) == 0
        and summary.get("duplicate_serialized_span_count", 0) == 0
        and summary.get("context_hint_positive_overlap_count", 0) == 0
        and summary["reference_primary_support_count"] == 0
        and summary["caption_primary_support_count"] == 0
        and summary["review_table_primary_support_count"] == 0
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
