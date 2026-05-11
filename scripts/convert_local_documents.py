from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.markdown_converter import convert_directory  # noqa: E402


DEFAULT_INPUT_DIR = Path("input_raw")
DEFAULT_OUTPUT_DIR = Path("input_markdown")
DEFAULT_MANIFEST = Path("data") / "reports" / "document_conversion_manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert local documents to Markdown.")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR, help="Input raw document directory.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output Markdown directory.")
    parser.add_argument(
        "--converter",
        choices=["auto", "docling", "markitdown", "pymupdf", "basic"],
        default="auto",
        help="Document converter strategy.",
    )
    parser.add_argument("--force", action="store_true", help="Reconvert even when output Markdown already exists.")
    parser.add_argument("--clean-output", action="store_true", help="Remove existing Markdown outputs before conversion.")
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Output conversion manifest JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = convert_directory(
        args.input_dir,
        args.output_dir,
        converter=args.converter,
        force=args.force,
        clean_output=args.clean_output,
    )
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    counts = _status_counts(results)
    converter_counts = _converter_counts(results)
    print(f"Converter requested: {args.converter}")
    print(f"Processed {len(results)} files")
    print(f"- converted: {counts['converted']}")
    print(f"- copied: {counts['copied']}")
    print(f"- unsupported: {counts['unsupported']}")
    print(f"- error: {counts['error']}")
    print(f"Converter used counts: {converter_counts}")
    print(f"Wrote conversion manifest to {args.manifest_output}")
    print("Next command:")
    print("python scripts/run_minimal_review_pipeline.py --input-markdown-dir input_markdown --run-name v0.2")
    return 0


def _status_counts(results: list[dict]) -> dict[str, int]:
    counts = {"converted": 0, "copied": 0, "unsupported": 0, "error": 0}
    for result in results:
        status = result.get("status", "error")
        if status not in counts:
            status = "error"
        counts[status] += 1
    return counts


def _converter_counts(results: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        converter_used = result.get("converter_used") or "none"
        counts[converter_used] = counts.get(converter_used, 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    raise SystemExit(main())
