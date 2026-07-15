from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.ledger_router import load_jsonl  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build trimmed PR1 ordered-source review artifacts.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--source-ledger-dir", type=Path, default=Path("data") / "source_ledgers")
    parser.add_argument("--output-dir", type=Path, default=Path("review_artifacts") / "pr1")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.source_ledger_dir / args.run_name
    sections = load_jsonl(run_dir / "section_ledger.jsonl")
    spans = load_jsonl(run_dir / "span_source_coordinates.jsonl")
    comparison = load_jsonl(run_dir / "parallel_comparison_index.jsonl")
    if not sections or not spans or not comparison:
        print("Source ledger and parallel comparison outputs are required.")
        return 1
    args.output_dir.mkdir(parents=True, exist_ok=True)
    ordered_path = args.output_dir / "ordered_source_sample.md"
    parallel_path = args.output_dir / "parallel_comparison_sample.md"
    ordered_path.write_text(_ordered_sample(sections, spans), encoding="utf-8", newline="\n")
    parallel_path.write_text(_parallel_sample(comparison), encoding="utf-8", newline="\n")
    print(f"ordered_source_sample: {ordered_path}")
    print(f"parallel_comparison_sample: {parallel_path}")
    return 0


def _ordered_sample(sections: list[dict], spans: list[dict]) -> str:
    sections_by_paper: dict[str, list[dict]] = defaultdict(list)
    spans_by_paper: dict[str, list[dict]] = defaultdict(list)
    for section in sections:
        sections_by_paper[str(section.get("paper_id") or "")].append(section)
    for span in spans:
        spans_by_paper[str(span.get("paper_id") or "")].append(span)
    selected_papers = sorted(spans_by_paper)[:12]
    lines = [
        "# Ordered Source Sample", "",
        "Trimmed review artifact for manual source-order and semantic inspection. It does not include full papers.", "",
    ]
    for paper_id in selected_papers:
        lines.extend([f"## {paper_id}", "", "### Document outline", ""])
        for section in sorted(sections_by_paper[paper_id], key=lambda item: int(item.get("section_start_offset") or 0)):
            label = str(section.get("outline_label") or "UNK")
            lines.append(f"- `{label}` {section.get('heading_text') or '(unheaded)'} [{section.get('section_type') or 'unknown'}]")
        paper_spans = sorted(spans_by_paper[paper_id], key=lambda item: int(item.get("verified_source_start_offset") or 10**18))
        priority = sorted(paper_spans, key=lambda item: (-float(item.get("candidate_score") or 0), int(item.get("verified_source_start_offset") or 10**18)))
        ranks = {str(item.get("source_span_id")): rank for rank, item in enumerate(priority, 1)}
        lines.extend(["", "### Selected anchors in source order", ""])
        for span in paper_spans[:8]:
            excerpt = " ".join(str(span.get("source_text") or "").split())[:500].rstrip()
            lines.extend([
                f"- `{span.get('source_locator') or 'unresolved'}`",
                f"  - section: `{span.get('section_outline_label') or 'UNK'}` {span.get('section_heading') or '(unheaded)'}",
                f"  - paragraph: global {span.get('paragraph_global_index')}, in section {span.get('paragraph_index_in_section')}",
                f"  - candidate priority rank: {ranks.get(str(span.get('source_span_id')))}",
                f"  - target: {excerpt}",
            ])
        lines.append("")
    return "\n".join(lines)


def _parallel_sample(records: list[dict]) -> str:
    groups = [
        ("LiNRR methods/protocol", lambda r: r.get("reaction_family") == "LiNRR" and r.get("semantic_section_type") == "methods"),
        ("LiNRR results/performance", lambda r: r.get("reaction_family") == "LiNRR" and r.get("semantic_section_type") == "results" and "performance" in (r.get("evidence_roles") or [])),
        ("eNRR validation", lambda r: r.get("reaction_family") == "eNRR" and "validation" in (r.get("evidence_roles") or [])),
        ("NO3RR quantification", lambda r: r.get("reaction_family") == "NO3RR" and (
            "quantification" in (r.get("evidence_roles") or [])
            or any(term in str(r.get("source_text_excerpt") or "").casefold() for term in (
                "ion chromatography", "colorimetric", "calibration", "ammonia quantification", "nmr",
            ))
        )),
        ("reactor/process", lambda r: bool(set(r.get("evidence_roles") or []) & {"reactor", "process"})),
    ]
    lines = [
        "# Parallel Comparison Sample", "",
        "For manual structural and semantic review only. These alignments do not establish scientific comparability.", "",
    ]
    for name, predicate in groups:
        selected = [record for record in records if predicate(record)][:10]
        lines.extend([f"## {name}", ""])
        for record in selected:
            lines.extend([
                f"- paper: `{record.get('paper_id')}`",
                f"  - locator: `{record.get('source_locator') or 'unresolved'}`",
                f"  - section: `{record.get('section_outline_label') or 'UNK'}` {record.get('semantic_section_type')}",
                f"  - roles: {', '.join(record.get('evidence_roles') or [])}",
                f"  - text: {' '.join(str(record.get('source_text_excerpt') or '').split())[:500].rstrip()}",
            ])
        if not selected:
            lines.append("- No matching records in this run.")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
