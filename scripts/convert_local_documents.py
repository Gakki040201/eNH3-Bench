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
        "--manifest-output",
        type=Path,
        default=DEFAULT_MANIFEST,
        help="Output conversion manifest JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = convert_directory(args.input_dir, args.output_dir)
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    converted = sum(1 for result in results if result["status"] in {"converted", "copied"})
    print(f"Processed {len(results)} files; {converted} converted or copied")
    print(f"Wrote conversion manifest to {args.manifest_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
