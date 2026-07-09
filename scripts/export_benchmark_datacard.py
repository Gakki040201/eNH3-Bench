from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.benchmark_schema import (  # noqa: E402
    BENCHMARK_TASKS,
    BOUNDARY_LABELS,
    EXPERIMENT_DECISION_LABELS,
    HIDDEN_TAX_LABELS,
    REQUIRED_CONTROL_LABELS,
    SOURCE_SPAN_LABELS,
    VALIDATION_GATE_LABELS,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export an eNH3-BoundaryBench datacard.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "benchmarks")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = _render(args.run_name)
    run_dir = args.output_dir / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    datacard_path = run_dir / "DATACARD.md"
    report_path = Path("data") / "reports" / f"boundary_benchmark_datacard.{args.run_name}.md"
    datacard_path.write_text(text, encoding="utf-8", newline="\n")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8", newline="\n")
    print(f"datacard: {datacard_path}")
    print(f"report: {report_path}")
    return 0


def _render(run_name: str) -> str:
    return "\n".join(
        [
            "# Dataset Card: eNH3-BoundaryBench",
            "",
            f"- Version/run name: {run_name}",
            "- Dataset name: eNH3-BoundaryBench",
            "",
            "## Intended use",
            "",
            "Evaluate eNH3-specific source classification, validation gates, claim-rights boundaries, hidden taxes, required controls, and experiment-decision ranking from reviewed source spans.",
            "",
            "## Not intended use",
            "",
            "Do not use this benchmark as proof of real-world catalyst performance, as a replacement for paper reading, or as a source of full copyrighted documents.",
            "",
            "## Data sources",
            "",
            "Rows are derived from BoundaryLedger source spans and Phase D human-reviewed audit records. Gold records are loaded from explicit human gold exports when present, otherwise from validated reviewed audit records.",
            "",
            "## Human review protocol",
            "",
            "A row is gold only after `human_review_status=reviewed` and required human fields validate. Unreviewed rows are excluded.",
            "",
            "## Task definitions",
            "",
            _bullet_list(BENCHMARK_TASKS),
            "",
            "## Label schema",
            "",
            "Source-span labels:",
            _bullet_list(SOURCE_SPAN_LABELS),
            "",
            "Boundary labels:",
            _bullet_list(BOUNDARY_LABELS),
            "",
            "Validation gate labels:",
            _bullet_list(VALIDATION_GATE_LABELS),
            "",
            "Hidden-tax labels:",
            _bullet_list(HIDDEN_TAX_LABELS),
            "",
            "Required-control labels:",
            _bullet_list(REQUIRED_CONTROL_LABELS),
            "",
            "Experiment-decision labels:",
            _bullet_list(EXPERIMENT_DECISION_LABELS),
            "",
            "## Provenance handling",
            "",
            "Provenance type and confidence are retained as inputs. Splits should use paper-level grouping to reduce leakage across records from the same paper.",
            "",
            "## LLM verification handling",
            "",
            "LLM fields are optional baseline predictions or disagreement signals. They are never treated as gold labels.",
            "",
            "## Leakage prevention",
            "",
            "Use `split_boundary_benchmark.py` to split by `paper_id` by default. If `paper_id` is missing, grouping falls back to document or span identifiers.",
            "",
            "## Limitations",
            "",
            "Coverage depends on manually reviewed audit rows. Small runs may have empty dev/test splits. Labels are source-span-level judgments, not whole-paper conclusions.",
            "",
            "## Ethics and copyright note",
            "",
            "Use source spans, not full copyrighted texts, when exporting or sharing benchmark artifacts.",
            "",
            "## Reproducibility commands",
            "",
            "```powershell",
            f"C:\\Python314\\python.exe scripts\\build_boundary_benchmark.py --run-name {run_name}",
            f"C:\\Python314\\python.exe scripts\\split_boundary_benchmark.py --run-name {run_name} --seed 13",
            f"C:\\Python314\\python.exe scripts\\evaluate_boundary_benchmark.py --run-name {run_name}",
            f"C:\\Python314\\python.exe scripts\\export_benchmark_datacard.py --run-name {run_name}",
            "```",
            "",
        ]
    )


def _bullet_list(values: tuple[str, ...]) -> str:
    return "\n".join(f"- `{value}`" for value in values)


if __name__ == "__main__":
    raise SystemExit(main())
