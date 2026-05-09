from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.minimal_pipeline import run_minimal_review_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local Markdown to audit-packet workflow.")
    parser.add_argument(
        "--input-markdown-dir",
        type=Path,
        default=Path("input_markdown"),
        help="Input Markdown directory.",
    )
    parser.add_argument("--run-name", default="v0.2", help="Run name used in output filenames.")
    parser.add_argument(
        "--max-spans-per-document",
        type=int,
        default=6,
        help="Maximum candidate spans per Markdown document.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = run_minimal_review_pipeline(
        input_markdown_dir=args.input_markdown_dir,
        run_name=args.run_name,
        max_spans_per_document=args.max_spans_per_document,
    )
    print(f"Documents: {manifest['document_count']}")
    print(f"Candidate spans: {manifest['candidate_span_count']}")
    print(f"Draft evidence records: {manifest['draft_evidence_count']}")
    print(manifest["next_human_step"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
