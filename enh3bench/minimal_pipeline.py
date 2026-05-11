"""Lowest-level pipeline from local Markdown documents to human audit packet."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from enh3bench.audit_packet import (
    REVIEW_SHEET_COLUMNS,
    build_audit_packet,
    build_review_sheet_rows,
)
from enh3bench.document_loader import load_markdown_documents
from enh3bench.draft_extractor import draft_evidence_from_span
from enh3bench.draft_feedback import generate_feedback, summarize_feedback
from enh3bench.field_grounding import ground_record, summarize_grounding
from enh3bench.span_finder import find_candidate_spans


def run_minimal_review_pipeline(
    input_markdown_dir: str | Path = "input_markdown",
    run_name: str = "v0.2",
    max_spans_per_document: int = 6,
    top_n: int | None = None,
    max_per_paper: int | None = None,
) -> dict[str, Any]:
    """Run local Markdown -> candidates -> drafts -> audit packet."""

    paths = _output_paths(run_name)
    documents = load_markdown_documents(input_markdown_dir)
    candidates: list[dict[str, Any]] = []
    for document in documents:
        candidates.extend(
            find_candidate_spans(
                document,
                max_spans_per_document=max_per_paper or max_spans_per_document,
            )
        )
    candidates.sort(key=lambda item: (-int(item.get("candidate_score", 0)), str(item.get("span_id", ""))))
    if top_n is not None:
        candidates = candidates[:top_n]
    drafts = [draft_evidence_from_span(span) for span in candidates]
    grounding_records = [_grounding_record(draft) for draft in drafts]
    grounding_by_id = {str(item.get("evidence_id")): item for item in grounding_records}
    feedback_records = [
        _feedback_record(draft, grounding_by_id.get(str(draft.get("evidence_id"))))
        for draft in drafts
    ]

    _write_jsonl(candidates, paths["candidates"])
    _write_jsonl(drafts, paths["drafts"])
    _write_jsonl(grounding_records, paths["grounding"])
    _write_jsonl(feedback_records, paths["feedback"])
    paths["audit_packet"].parent.mkdir(parents=True, exist_ok=True)
    paths["audit_packet"].write_text(
        build_audit_packet(candidates, drafts, grounding_records, feedback_records),
        encoding="utf-8",
        newline="\n",
    )
    _write_review_sheet(build_review_sheet_rows(candidates, drafts), paths["review_sheet"])
    paths["human_instructions"].write_text(
        _human_instructions(run_name),
        encoding="utf-8",
        newline="\n",
    )

    next_step = (
        f"Open data/audit/audit_packet.{run_name}.md and "
        f"data/audit/review_sheet.{run_name}.csv for minimal verification."
    )
    manifest = {
        "run_name": run_name,
        "input_markdown_dir": str(input_markdown_dir),
        "document_count": len(documents),
        "candidate_span_count": len(candidates),
        "draft_evidence_count": len(drafts),
        "field_grounding_count": len(grounding_records),
        "draft_feedback_count": len(feedback_records),
        "outputs": {name: str(path) for name, path in paths.items()},
        "next_human_step": next_step,
    }
    paths["manifest"].parent.mkdir(parents=True, exist_ok=True)
    paths["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _output_paths(run_name: str) -> dict[str, Path]:
    return {
        "candidates": Path("data") / "candidates" / f"candidate_spans.{run_name}.jsonl",
        "drafts": Path("data") / "drafts" / f"draft_evidence.{run_name}.jsonl",
        "grounding": Path("data") / "drafts" / f"field_grounding.{run_name}.jsonl",
        "feedback": Path("data") / "drafts" / f"draft_feedback.{run_name}.jsonl",
        "audit_packet": Path("data") / "audit" / f"audit_packet.{run_name}.md",
        "review_sheet": Path("data") / "audit" / f"review_sheet.{run_name}.csv",
        "human_instructions": Path("data") / "audit" / "HUMAN_VERIFICATION_INSTRUCTIONS.md",
        "manifest": Path("data") / "reports" / f"workflow_manifest.{run_name}.json",
    }


def _write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")))
            handle.write("\n")


def _write_review_sheet(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_SHEET_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _human_instructions(run_name: str) -> str:
    return "\n".join(
        [
            "# Human Verification Instructions",
            "",
            "This pipeline stops before reviewed gold creation.",
            "",
            f"1. Open `data/audit/audit_packet.{run_name}.md`.",
            f"2. Open `data/audit/review_sheet.{run_name}.csv`.",
            "3. For each candidate, verify source grounding against the original paper text.",
            "4. Fill `human_decision`, `include_in_gold`, `reliability_override`, and `correction_notes`.",
            "5. Run `scripts/merge_reviewed_gold.py` after review is complete.",
            "",
            "Draft evidence is not gold until human review accepts it.",
            "",
        ]
    )


def _grounding_record(draft: dict[str, Any]) -> dict[str, Any]:
    grounding = ground_record(draft)
    return {
        "evidence_id": draft.get("evidence_id"),
        "paper_id": draft.get("paper_id"),
        "grounding": grounding,
        "summary": summarize_grounding(grounding),
    }


def _feedback_record(
    draft: dict[str, Any],
    grounding_result: dict[str, Any] | None,
) -> dict[str, Any]:
    feedback = generate_feedback(draft, grounding_result)
    return {
        "evidence_id": draft.get("evidence_id"),
        "paper_id": draft.get("paper_id"),
        "feedback": feedback,
        "summary": summarize_feedback(feedback),
    }
