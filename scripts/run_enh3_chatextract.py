"""Run offline eNH3-ChatExtract-style extraction on candidate spans."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.chatextract_chain import run_rule_chatextract  # noqa: E402
from enh3bench.extraction_runs import write_method_records  # noqa: E402


DEFAULT_SPANS = Path("data/candidates/candidate_spans.v0.2.jsonl")
DEFAULT_METHOD = "enh3_chatextract_rule"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline eNH3-ChatExtract-style extraction.")
    parser.add_argument("--spans", type=Path, default=DEFAULT_SPANS, help="Candidate spans JSONL or audit packet Markdown.")
    parser.add_argument("--run-name", default="v0.4_pilot", help="Extraction run name.")
    parser.add_argument("--method-name", default=DEFAULT_METHOD, help="Method output file stem.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spans = _load_spans(args.spans)
    records = [run_rule_chatextract(span) for span in spans]
    for record in records:
        record["method_name"] = args.method_name
    output = write_method_records(records, args.run_name, args.method_name)
    print(f"Wrote {len(records)} eNH3-ChatExtract rule records to {output}")
    print("Prompt templates for future optional API use:")
    print("- prompts/enh3_chatextract_relevance.md")
    print("- prompts/enh3_chatextract_extraction.md")
    print("- prompts/enh3_chatextract_verification.md")
    print("- prompts/enh3_chatextract_reliability.md")
    return 0


def _load_spans(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".md":
        return _load_audit_packet_spans(path)
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _load_audit_packet_spans(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    spans: list[dict[str, Any]] = []
    current_id = "S_AUDIT"
    paper_id = "UNKNOWN"
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("- evidence_id:"):
            current_id = line.split("`")[1] if "`" in line else current_id
        if line.startswith("- paper_id:"):
            paper_id = line.split("`")[1] if "`" in line else paper_id
        if line.strip() == "### Source Span":
            block: list[str] = []
            for block_line in lines[index + 1 :]:
                if block_line.startswith("### "):
                    break
                if block_line.startswith(">"):
                    block.append(block_line.lstrip("> ").rstrip())
            source = "\n".join(block).strip()
            if source:
                spans.append(
                    {
                        "span_id": current_id,
                        "paper_id": paper_id,
                        "source_section": "unknown",
                        "text": source,
                    }
                )
    return spans


if __name__ == "__main__":
    raise SystemExit(main())
