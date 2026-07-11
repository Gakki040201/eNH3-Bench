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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a human audit sheet for eNH3-BoundaryLedger.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--llm-model")
    parser.add_argument("--top-n", type=int)
    parser.add_argument("--priority-only", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "human_audit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rule_records = load_claim_rights(args.run_name)
    hidden_tax_records = load_hidden_tax(args.run_name)
    llm_records = load_llm_verified_claims(args.run_name, args.llm_model) if args.llm_model else []
    audit_records = merge_audit_sources(rule_records, hidden_tax_records, llm_records)
    outputs = export_human_audit_sheet(
        audit_records,
        args.run_name,
        output_dir=args.output_dir,
        top_n=args.top_n,
        priority_only=args.priority_only,
    )
    report_path = export_audit_report(audit_records, args.run_name)

    print(f"rule_records: {len(rule_records)}")
    print(f"hidden_tax_records: {len(hidden_tax_records)}")
    print(f"llm_records: {len(llm_records)}")
    print(f"audit_records_exported: {outputs['count']}")
    print(f"priority_records: {outputs['priority_records']}")
    print(f"rule_review_records: {outputs['rule_review_records']}")
    print(f"llm_review_records: {outputs['llm_review_records']}")
    print(f"overall_review_records: {outputs['overall_review_records']}")
    print(f"priority_band_counts: {outputs['priority_band_counts']}")
    print(f"csv: {outputs['csv']}")
    print(f"jsonl: {outputs['jsonl']}")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
