from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.ledger_router import load_jsonl  # noqa: E402
from enh3bench.parallel_comparison import (  # noqa: E402
    build_parallel_comparison_index,
    export_parallel_comparison_index,
)


SEMANTIC_FIELDS = (
    "effective_reaction_family", "effective_reaction_family_source",
    "reaction_family_correction", "document_reaction_family",
    "document_target_reaction_family_conflict", "local_reaction_family_conflict_primary_admissible",
    "primary_semantic_eligibility", "semantic_claim_type", "performance_result_evidence",
    "performance_evidence_strength", "target_ammonia_reaction_outcome_anchor",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build structural parallel-comparison coordinates.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--span-coordinates", type=Path)
    parser.add_argument("--context-packets", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "source_ledgers")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    span_path = args.span_coordinates or args.output_dir / args.run_name / "span_source_coordinates.jsonl"
    context_path = args.context_packets or (
        Path("data") / "context_packets" / args.run_name / "ordered_source_v1" / "context_packets.jsonl"
    )
    spans = load_jsonl(span_path)
    packets = load_jsonl(context_path)
    if not spans:
        print(f"No span source coordinates found: {span_path}")
        return 1
    if not packets:
        print(f"No ordered context packets found: {context_path}")
        return 1
    routed_spans, missing_semantics = _attach_context_semantics(spans, packets)
    comparison = build_parallel_comparison_index(routed_spans)
    outputs = export_parallel_comparison_index(comparison, args.run_name, args.output_dir)
    summary = outputs["summary_data"]
    consistency = _parallel_context_consistency(comparison, packets)
    print(f"record_count: {summary['record_count']}")
    print(f"comparison_group_count: {summary['comparison_group_count']}")
    print(f"comparison_groups_using_direct_section: {summary['comparison_groups_using_direct_section']}")
    print(f"comparison_groups_using_inherited_section: {summary['comparison_groups_using_inherited_section']}")
    print(f"comparison_groups_with_unknown_section: {summary['comparison_groups_with_unknown_section']}")
    print(f"scientific_comparability_asserted_count: {summary['scientific_comparability_asserted_count']}")
    print(f"missing_context_semantic_span_count: {len(missing_semantics)}")
    for key, value in consistency.items():
        print(f"{key}: {value}")
    print(f"index: {outputs['index']}")
    print(f"summary: {outputs['summary']}")
    return 0 if (
        summary["scientific_comparability_asserted_count"] == 0
        and not missing_semantics
        and len(comparison) == len(packets) == len(spans)
        and all(value == 0 for value in consistency.values())
    ) else 1


def _attach_context_semantics(
    spans: list[dict], packets: list[dict]
) -> tuple[list[dict], list[str]]:
    packets_by_span = {str(packet.get("target_span_id") or ""): packet for packet in packets}
    routed_spans: list[dict] = []
    missing_semantics: list[str] = []
    for span in spans:
        span_id = str(span.get("source_span_id") or span.get("legacy_span_id") or "")
        packet = packets_by_span.get(span_id)
        if packet is None:
            missing_semantics.append(span_id)
            continue
        routed_spans.append({
            **span,
            **{field: packet.get(field) for field in SEMANTIC_FIELDS},
        })
    return routed_spans, missing_semantics


def _parallel_context_consistency(
    comparison: list[dict], packets: list[dict]
) -> dict[str, int]:
    comparison_by_span = {str(row.get("source_span_id") or ""): row for row in comparison}
    mismatch_fields = {
        "parallel_context_effective_family_mismatch_count": "effective_reaction_family",
        "parallel_context_semantic_claim_type_mismatch_count": "semantic_claim_type",
        "parallel_context_performance_result_mismatch_count": "performance_result_evidence",
        "parallel_context_primary_eligibility_mismatch_count": "primary_semantic_eligibility",
    }
    return {
        key: sum(
            comparison_by_span.get(str(packet.get("target_span_id") or ""), {}).get(field)
            != packet.get(field)
            for packet in packets
        )
        for key, field in mismatch_fields.items()
    }


if __name__ == "__main__":
    raise SystemExit(main())
