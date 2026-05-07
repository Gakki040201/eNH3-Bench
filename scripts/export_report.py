from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.report_generator import (  # noqa: E402
    generate_error_taxonomy_markdown,
    generate_main_results_markdown,
)


DEFAULT_INPUT = ROOT / "data" / "reports" / "evaluation_report.example.json"
DEFAULT_MAIN_RESULTS = ROOT / "paper" / "tables" / "main_results.md"
DEFAULT_ERROR_TAXONOMY = ROOT / "paper" / "tables" / "error_taxonomy.md"


def load_evaluation(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def export_report(
    input_path: Path = DEFAULT_INPUT,
    main_results_path: Path = DEFAULT_MAIN_RESULTS,
    error_taxonomy_path: Path = DEFAULT_ERROR_TAXONOMY,
) -> None:
    evaluation = load_evaluation(input_path)
    main_results_path.parent.mkdir(parents=True, exist_ok=True)
    error_taxonomy_path.parent.mkdir(parents=True, exist_ok=True)
    main_results_path.write_text(
        generate_main_results_markdown(evaluation),
        encoding="utf-8",
        newline="\n",
    )
    error_taxonomy_path.write_text(
        generate_error_taxonomy_markdown(evaluation),
        encoding="utf-8",
        newline="\n",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export evaluation JSON to paper tables.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Evaluation JSON file.")
    parser.add_argument(
        "--main-results",
        type=Path,
        default=DEFAULT_MAIN_RESULTS,
        help="Output Markdown file for main result tables.",
    )
    parser.add_argument(
        "--error-taxonomy",
        type=Path,
        default=DEFAULT_ERROR_TAXONOMY,
        help="Output Markdown file for error taxonomy table.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    export_report(args.input, args.main_results, args.error_taxonomy)
    print(f"Wrote main results to {args.main_results}")
    print(f"Wrote error taxonomy to {args.error_taxonomy}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
