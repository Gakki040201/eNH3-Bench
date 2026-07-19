from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.human_audit import (  # noqa: E402
    export_audit_report,
    export_human_audit_sheet,
    load_claim_rights,
    load_hidden_tax,
    load_llm_verified_claims,
    merge_audit_sources,
)
from enh3bench.audit_routing import (  # noqa: E402
    LEGACY_ROUTING_PROFILE,
    MAX_REFERENCE_SPANS_PER_PAPER_FOR_AUDIT,
    REFERENCE_AUDIT_HASH_NAMESPACE,
    REFERENCE_AUDIT_SAMPLE_RATE,
    ROUTING_PROFILES,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a human audit sheet for eNH3-BoundaryLedger.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--llm-model")
    parser.add_argument("--top-n", type=int)
    parser.add_argument("--priority-only", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "human_audit")
    parser.add_argument("--report-output-dir", type=Path, default=Path("data") / "reports")
    parser.add_argument("--routing-profile", choices=ROUTING_PROFILES, default=LEGACY_ROUTING_PROFILE)
    parser.add_argument("--reference-audit-sample-rate", type=float, default=REFERENCE_AUDIT_SAMPLE_RATE)
    parser.add_argument(
        "--max-reference-spans-per-paper-for-audit",
        type=int,
        default=MAX_REFERENCE_SPANS_PER_PAPER_FOR_AUDIT,
    )
    parser.add_argument("--reference-audit-seed", default=REFERENCE_AUDIT_HASH_NAMESPACE)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rule_records = load_claim_rights(args.run_name)
    hidden_tax_records = load_hidden_tax(args.run_name)
    llm_records = load_llm_verified_claims(args.run_name, args.llm_model) if args.llm_model else []
    audit_records = merge_audit_sources(
        rule_records,
        hidden_tax_records,
        llm_records,
        routing_profile=args.routing_profile,
        reference_audit_sample_rate=args.reference_audit_sample_rate,
        max_reference_spans_per_paper_for_audit=args.max_reference_spans_per_paper_for_audit,
        reference_audit_seed=args.reference_audit_seed,
    )
    outputs = export_human_audit_sheet(
        audit_records,
        args.run_name,
        output_dir=args.output_dir,
        top_n=args.top_n,
        priority_only=args.priority_only,
        routing_profile=args.routing_profile,
    )
    report_path = export_audit_report(
        audit_records,
        args.run_name,
        output_dir=args.report_output_dir,
        routing_profile=args.routing_profile,
    )

    print(f"rule_records: {len(rule_records)}")
    print(f"hidden_tax_records: {len(hidden_tax_records)}")
    print(f"llm_records: {len(llm_records)}")
    print(f"routing_profile: {args.routing_profile}")
    print(f"audit_records_exported: {outputs['count']}")
    print(f"priority_records: {outputs['priority_records']}")
    print(f"rule_review_records: {outputs['rule_review_records']}")
    print(f"llm_review_records: {outputs['llm_review_records']}")
    print(f"overall_review_records: {outputs['overall_review_records']}")
    print(f"priority_band_counts: {outputs['priority_band_counts']}")
    if args.routing_profile != LEGACY_ROUTING_PROFILE:
        print(f"stable_reference_auto_secondary_count: {outputs['stable_reference_auto_secondary_count']}")
        print(f"reference_sampled_for_audit_count: {outputs['reference_sampled_for_audit_count']}")
        print(f"reference_conflict_review_count: {outputs['reference_conflict_review_count']}")
        print(f"caption_context_only_count: {outputs['caption_context_only_count']}")
        print(f"review_table_secondary_count: {outputs['review_table_secondary_count']}")
        print(f"secondary_validation_gate_count: {outputs['secondary_validation_gate_count']}")
    print(f"csv: {outputs['csv']}")
    print(f"jsonl: {outputs['jsonl']}")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
