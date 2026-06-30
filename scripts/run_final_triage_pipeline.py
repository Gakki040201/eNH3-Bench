from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.final_workflow import render_final_output_check, run_final_triage_workflow  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the final local eNH3-TriageBench CLI workflow.")
    parser.add_argument("--input-dir", type=Path, default=Path("input_raw"))
    parser.add_argument("--markdown-dir", type=Path, default=Path("input_markdown"))
    parser.add_argument("--run-name", default="final_pilot")
    parser.add_argument("--converter", choices=["auto", "docling", "markitdown", "pymupdf", "basic"], default="auto")
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument("--max-per-paper", type=int, default=6)
    parser.add_argument("--force-reconvert", action="store_true")
    parser.add_argument("--skip-conversion", action="store_true")
    parser.add_argument("--clean-markdown", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = run_final_triage_workflow(
        input_dir=args.input_dir,
        markdown_dir=args.markdown_dir,
        run_name=args.run_name,
        converter=args.converter,
        top_n=args.top_n,
        max_per_paper=args.max_per_paper,
        force_reconvert=args.force_reconvert,
        skip_conversion=args.skip_conversion,
        clean_markdown=args.clean_markdown,
    )
    print(f"Run name: {args.run_name}")
    print(f"Candidate spans: {manifest['minimal_manifest']['candidate_span_count']}")
    print(f"Classified spans: {manifest['classified_span_count']}")
    print(f"Performance records scored: {manifest['performance_records_scored']}")
    print(f"Triage report: {manifest['triage_outputs']['triage_report_md']}")
    print(f"Triage table: {manifest['triage_outputs']['triage_table_csv']}")
    print(f"Manifest: {manifest['final_workflow_manifest']}")
    print("")
    print(render_final_output_check(manifest["output_check"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
