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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build structural parallel-comparison coordinates.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--span-coordinates", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "source_ledgers")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    span_path = args.span_coordinates or args.output_dir / args.run_name / "span_source_coordinates.jsonl"
    spans = load_jsonl(span_path)
    if not spans:
        print(f"No span source coordinates found: {span_path}")
        return 1
    comparison = build_parallel_comparison_index(spans)
    outputs = export_parallel_comparison_index(comparison, args.run_name, args.output_dir)
    summary = outputs["summary_data"]
    print(f"record_count: {summary['record_count']}")
    print(f"comparison_group_count: {summary['comparison_group_count']}")
    print(f"comparison_groups_using_direct_section: {summary['comparison_groups_using_direct_section']}")
    print(f"comparison_groups_using_inherited_section: {summary['comparison_groups_using_inherited_section']}")
    print(f"comparison_groups_with_unknown_section: {summary['comparison_groups_with_unknown_section']}")
    print(f"scientific_comparability_asserted_count: {summary['scientific_comparability_asserted_count']}")
    print(f"index: {outputs['index']}")
    print(f"summary: {outputs['summary']}")
    return 0 if summary["scientific_comparability_asserted_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
