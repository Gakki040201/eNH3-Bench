"""Build a high-level eNH3-ExtractBench comparison report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.toolbench_evaluator import write_comparison_markdown  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an eNH3 extraction comparison report.")
    parser.add_argument(
        "--comparison-json",
        type=Path,
        default=Path("data/extraction_runs/v0.4_pilot/comparison_report.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/extraction_runs/v0.4_pilot/comparison_report_high_level.md"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = json.loads(args.comparison_json.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_high_level_report(results), encoding="utf-8", newline="\n")
    print(f"Wrote high-level extraction comparison report to {args.output}")
    return 0


def build_high_level_report(results: dict[str, Any]) -> str:
    """Build a report with method list, field tables, validation risks, and next action."""

    methods = results.get("methods", {})
    lines = [
        "# eNH3-ExtractBench Comparison Report",
        "",
        "## Methods Run",
        "",
    ]
    if not methods:
        lines.append("No method outputs were found.")
    for method_name, result in methods.items():
        lines.append(f"- `{method_name}`: {result.get('pred_records', 0)} prediction records")

    lines.extend(["", "## Field Performance", "", write_comparison_markdown(results).strip(), ""])
    lines.extend(
        [
            "## Validation Hallucination Table",
            "",
            "| method | unsupported validation yes rate | source grounding coverage |",
            "| --- | ---: | ---: |",
        ]
    )
    for method_name, result in methods.items():
        lines.append(
            f"| {method_name} | {result.get('unsupported_validation_yes_rate', 0.0):.3f} | "
            f"{result.get('source_grounding_coverage', 0.0):.3f} |"
        )

    lines.extend(
        [
            "",
            "## Method Limitations",
            "",
            "- Offline rule fallbacks are deterministic but brittle.",
            "- Prompt-chain outputs are scaffolds until a user explicitly enables a local or API model.",
            "- Validation controls must remain source-grounded and human-verified.",
            "",
            "## Next Human Action",
            "",
            "Review audit packets and accepted gold records before treating any method output as benchmark evidence.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
