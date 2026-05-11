from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.draft_feedback import generate_feedback, summarize_feedback  # noqa: E402


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")))
            handle.write("\n")


def run_draft_feedback(drafts_path: Path, grounding_path: Path, output_path: Path) -> list[dict[str, Any]]:
    groundings = {str(item.get("evidence_id")): item for item in load_jsonl(grounding_path)}
    outputs: list[dict[str, Any]] = []
    for draft in load_jsonl(drafts_path):
        feedback = generate_feedback(draft, groundings.get(str(draft.get("evidence_id"))))
        outputs.append(
            {
                "evidence_id": draft.get("evidence_id"),
                "paper_id": draft.get("paper_id"),
                "feedback": feedback,
                "summary": summarize_feedback(feedback),
            }
        )
    write_jsonl(outputs, output_path)
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run rule-based draft feedback.")
    parser.add_argument("--drafts", type=Path, default=Path("data/drafts/draft_evidence.v0.2.jsonl"))
    parser.add_argument("--grounding", type=Path, default=Path("data/drafts/field_grounding.v0.2.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/drafts/draft_feedback.v0.2.jsonl"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = run_draft_feedback(args.drafts, args.grounding, args.output)
    print(f"Wrote feedback for {len(outputs)} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
