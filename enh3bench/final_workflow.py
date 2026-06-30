"""End-to-end final CLI workflow for eNH3-TriageBench."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from enh3bench.draft_extractor import draft_evidence_from_span
from enh3bench.ledger_router import (
    classify_spans,
    load_jsonl,
    route_classified_spans,
)
from enh3bench.markdown_converter import convert_directory
from enh3bench.minimal_pipeline import run_minimal_review_pipeline
from enh3bench.triage_score import export_triage_outputs, score_performance_records


LEDGER_NAMES = [
    "performance_ledger",
    "negative_evidence_ledger",
    "validation_protocol_ledger",
    "secondary_review_ledger",
    "rejected_or_context",
]


def run_final_triage_workflow(
    input_dir: str | Path = "input_raw",
    markdown_dir: str | Path = "input_markdown",
    run_name: str = "final_pilot",
    converter: str = "auto",
    top_n: int = 30,
    max_per_paper: int = 6,
    force_reconvert: bool = False,
    skip_conversion: bool = False,
    clean_markdown: bool = False,
) -> dict[str, Any]:
    """Run local conversion, classification, ledger routing, triage, and checks."""

    conversion_results: list[dict[str, Any]] = []
    if not skip_conversion:
        conversion_results = convert_directory(
            input_dir,
            markdown_dir,
            converter=converter,
            force=force_reconvert,
            clean_output=clean_markdown,
        )

    minimal_manifest = run_minimal_review_pipeline(
        input_markdown_dir=markdown_dir,
        run_name=run_name,
        top_n=top_n,
        max_per_paper=max_per_paper,
    )

    candidates_path = Path("data") / "candidates" / f"candidate_spans.{run_name}.jsonl"
    candidates = load_jsonl(candidates_path)
    classified = classify_spans(candidates)
    enriched_classified = _attach_extractable_drafts(classified)
    ledger_manifest = route_classified_spans(enriched_classified, run_name)
    performance_records = [
        record
        for record in enriched_classified
        if str(record.get("recommended_ledger") or "") == "performance"
        and bool(record.get("allow_field_extraction"))
    ]
    triage_records = score_performance_records(performance_records)
    triage_outputs = export_triage_outputs(
        triage_records,
        run_name,
        ledger_counts=ledger_manifest.get("ledger_counts", {}),
    )
    output_check = check_final_output_status(run_name)

    manifest = {
        "run_name": run_name,
        "input_dir": str(input_dir),
        "markdown_dir": str(markdown_dir),
        "conversion": {
            "skipped": skip_conversion,
            "results": conversion_results,
            "summary": _status_counts(conversion_results),
        },
        "minimal_manifest": minimal_manifest,
        "candidate_spans": str(candidates_path),
        "classified_span_count": len(enriched_classified),
        "performance_records_scored": len(triage_records),
        "ledger_manifest": ledger_manifest,
        "triage_outputs": triage_outputs,
        "output_check": output_check,
    }
    manifest_path = Path("data") / "reports" / f"final_workflow_manifest.{run_name}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    manifest["final_workflow_manifest"] = str(manifest_path)
    return manifest


def check_final_output_status(
    run_name: str,
    require_training: bool = False,
    require_models: bool = False,
) -> list[dict[str, Any]]:
    """Return final-output checklist status for one run."""

    checks: list[dict[str, Any]] = []
    ledgers_dir = Path("data") / "ledgers" / run_name
    reports_dir = Path("data") / "reports"
    training_dir = Path("data") / "training"
    models_dir = Path("models")

    checks.extend(
        [
            _check("classified spans JSONL", ledgers_dir / "classified_spans.jsonl", True),
            _check("classified spans CSV", ledgers_dir / "classified_spans.csv", True),
        ]
    )
    for ledger in LEDGER_NAMES:
        checks.append(_check(f"{ledger} JSONL", ledgers_dir / f"{ledger}.jsonl", True))
        checks.append(_check(f"{ledger} CSV", ledgers_dir / f"{ledger}.csv", True))
    checks.extend(
        [
            _check("triage report", reports_dir / f"experiment_triage_report.{run_name}.md", True),
            _check("triage table CSV", reports_dir / f"experiment_triage_table.{run_name}.csv", True),
            _check("triage scores JSONL", reports_dir / f"experiment_triage_scores.{run_name}.jsonl", True),
            _check("source-span training CSV", training_dir / f"source_span_training.{run_name}.csv", require_training),
            _check("triage training CSV", training_dir / f"triage_training.{run_name}.csv", require_training),
            _check("source-span model", models_dir / f"source_span_classifier.{run_name}.joblib", require_models),
            _check("triage ranker model", models_dir / f"triage_ranker.{run_name}.joblib", require_models),
        ]
    )
    return checks


def render_final_output_check(checks: list[dict[str, Any]]) -> str:
    """Render a human-readable checklist for final outputs."""

    lines = ["# eNH3-TriageBench Final Output Check", ""]
    for item in checks:
        mark = "[x]" if item["exists"] else "[ ]"
        required = "required" if item["required"] else "optional"
        lines.append(f"- {mark} {item['label']} ({required}): `{item['path']}`")
    missing_required = [item for item in checks if item["required"] and not item["exists"]]
    lines.append("")
    if missing_required:
        lines.append(f"Missing required outputs: {len(missing_required)}")
    else:
        lines.append("All required outputs are present.")
    return "\n".join(lines)


def _attach_extractable_drafts(classified_spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for span in classified_spans:
        record = dict(span)
        draft = draft_evidence_from_span(span)
        record["evidence_id"] = draft.get("evidence_id")
        if bool(record.get("allow_field_extraction")):
            for key, value in draft.items():
                if key in {"text", "source_text"}:
                    continue
                record[key] = value
        enriched.append(record)
    return enriched


def _check(label: str, path: Path, required: bool) -> dict[str, Any]:
    return {
        "label": label,
        "path": str(path),
        "exists": path.exists(),
        "required": required,
    }


def _status_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"converted": 0, "copied": 0, "unsupported": 0, "error": 0}
    for result in results:
        status = str(result.get("status") or "error")
        counts[status if status in counts else "error"] += 1
    return counts
