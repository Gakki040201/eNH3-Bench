from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any

from enh3bench.e2e_case_generation import (
    make_api_output_templates,
    make_machine_judgment_templates,
)
from enh3bench.e2e_holdout import build_freeze_manifest, read_generation_parameters
from enh3bench.e2e_eval_schema import (
    FINAL_HUMAN_LABEL_FIELDS,
    JUDGE_DIMENSIONS,
    read_csv,
    read_json,
    read_jsonl,
    write_json,
    write_jsonl,
)


ITEM_TYPES = ("span", "paper", "document", "link")


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def synthetic_frames() -> dict[str, list[dict[str, Any]]]:
    papers = [f"P{i:04d}" for i in range(180)]
    genres = ["primary_research", "review", "perspective", "mixed", "unclear", "computational_study"]
    families = ["eNRR", "NO3RR", "LiNRR", "unclear", "mixed", "NORR", "NO2RR"]
    strata = [
        "primary_performance", "quantification", "validation", "external_cited_claim",
        "off_target", "trap_only", "unclear_mixed_family", "reactor_process", "review_perspective",
    ]
    claim_types = [
        "performance_result_claim", "ammonia_quantification_claim", "validation_claim",
        "mechanism_claim", "secondary_context_claim", "gas_purification_or_capture_claim",
        "untyped_claim", "reactor_claim", "performance_context_claim",
    ]
    spans: list[dict[str, Any]] = []
    for index in range(300):
        paper_index = index % len(papers)
        stratum = strata[index % len(strata)]
        claim_type = claim_types[index % len(claim_types)]
        spans.append({
            "calibration_item_id": f"CC16S_{index:020d}", "item_type": "span",
            "paper_id": papers[paper_index], "document_id": f"D{paper_index:04d}",
            "cleanroom_span_id": f"CR15_{index:020d}", "source_node_id": f"CRN15_{index:020d}",
            "sampling_hash": _hash(f"span:{index}"), "assigned_primary_stratum": stratum,
            "selection_stratum": "high_risk_reservoir" if index % 15 == 0 else stratum,
            "semantic_claim_type": claim_type, "effective_reaction_family": families[index % len(families)],
            "document_reaction_family": families[index % len(families)],
            "document_genre": genres[index % len(genres)],
            "claim_ownership": ["target_authors", "external_or_cited_authors", "unclear"][index % 3],
            "semantic_confidence": ["high", "medium", "low"][index % 3],
            "primary_semantic_eligibility": index % 4 == 0, "needs_review": index % 2 == 0,
            "all_matching_strata": [stratum],
            "validation_gate_decisions": {"isotope": index % 3 == 0},
            "hard_gate_failures": ["fixture_gate"] if index % 11 == 0 else [],
            "previous_context_excerpt": "bounded previous context" if index % 5 else "",
            "next_context_excerpt": "bounded next context", "target_excerpt": f"Bounded scientific excerpt {index}.",
            "linked_evidence_ids": [f"CRL15_{index % 100:020d}"] if index % 3 else [],
        })
    paper_rows: list[dict[str, Any]] = []
    document_rows: list[dict[str, Any]] = []
    for index in range(60):
        genre = genres[index % len(genres)]
        family = families[index % len(families)]
        common = {
            "paper_id": papers[index], "document_id": f"D{index:04d}",
            "document_genre": genre, "document_reaction_family": family,
        }
        paper_rows.append({
            **common, "calibration_item_id": f"CC16P_{index:020d}", "item_type": "paper",
            "sampling_hash": _hash(f"paper:{index}"), "paper_admissibility_status": "needs_review",
            "primary_eligible_count": 2 if index % 4 == 0 else 0,
            "limitations": ["fixture limitation"] if index % 3 == 0 else [],
            "has_validation_evidence": index % 2 == 0, "has_quantification_evidence": index % 3 == 0,
        })
        document_rows.append({
            **common, "calibration_item_id": f"CC16D_{index:020d}", "item_type": "document",
            "sampling_hash": _hash(f"document:{index}"),
            "document_conflicts": ["document_reaction_family_conflict"] if index % 10 == 0 else [],
            "front_matter_excerpt": f"Bounded front matter describing document {index} and its scientific scope. " * 3,
        })
    links: list[dict[str, Any]] = []
    for index in range(100):
        paper_index = index
        roles = ["quantification_support"]
        if index % 2 == 0:
            roles.append("validation_support")
        links.append({
            "calibration_item_id": f"CC16L_{index:020d}", "item_type": "link",
            "paper_id": papers[paper_index], "sampling_hash": _hash(f"link:{index}"),
            "evidence_link_id": f"CRL15_{index:020d}",
            "target_span_id": f"CR15_{paper_index:020d}",
            "evidence_span_id": f"CR15_{paper_index + 180:020d}",
            "target_source_node_id": f"CRN15_{paper_index:020d}",
            "evidence_source_node_id": f"CRN15_{paper_index + 180:020d}",
            "target_excerpt": f"Bounded target excerpt {index}.",
            "evidence_excerpt": f"Bounded evidence excerpt {index}.",
            "link_role": roles[0], "link_roles": roles,
            "target_primary_eligibility": index % 3 == 0,
            "source_eligibility": "primary_admissible" if index % 4 else "context_only",
            "is_context_only": index % 4 == 0, "needs_review": index % 2 == 0,
            "evidence_provenance": "figure_or_scheme_caption" if index % 5 == 0 else "primary_body",
            "source_distance_band": "far" if index % 3 == 0 else "near",
            "target_claim_type": "performance_result_claim",
            "evidence_claim_type": "ammonia_quantification_claim",
        })
    return {"span": spans, "paper": paper_rows, "document": document_rows, "link": links}


def create_source_calibration_fixture(root: Path, run_name: str = "calibration_fixture") -> Path:
    run = root / run_name
    frames = synthetic_frames()
    write_json(run / "manifests/calibration_manifest.json", {
        "schema_version": "0.16-calibration.1", "calibration_run_name": run_name,
        "source_cleanroom_run_name": "cleanroom_fixture", "status": "completed",
    })
    for item_type, rows in frames.items():
        write_jsonl(run / "sampling" / f"{item_type}_sampling_frame.jsonl", rows)
        review = run / "review" / f"{item_type}_review.csv"
        review.parent.mkdir(parents=True, exist_ok=True)
        with review.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["calibration_item_id", "reviewer_id", "review_status"])
            writer.writerows((row["calibration_item_id"], "", "") for row in rows)
    (run / "previews").mkdir(parents=True, exist_ok=True)
    (run / "previews/calibration_preview.md").write_text("# Blank fixture preview\n", encoding="utf-8")
    return run


def valid_api_outputs(package_dir: Path, count: int = 48) -> list[dict[str, Any]]:
    cases = read_jsonl(package_dir / "cases/e2e_case_frame.jsonl")[:count]
    rows = make_api_output_templates(cases)
    for row in rows:
        row.update({
            "answer_status": "abstained", "generation_status": "completed",
            "api_call_performed": True, "generation_model": "fixture-model-family",
            "generation_prompt_version": "fixture-prompt-v1",
            "generation_parameters": {"temperature": 0, "max_tokens": 512},
            "abstention_reason": "fixture bounded evidence insufficient",
        })
    return rows


def valid_machine_judgments(
    package_dir: Path, *, case_count: int = 48, observations_per_case: int = 2,
) -> list[dict[str, Any]]:
    cases = read_jsonl(package_dir / "cases/e2e_case_frame.jsonl")[:case_count]
    rows = make_machine_judgment_templates(cases)
    if observations_per_case == 1:
        rows = [row for row in rows if row["judge_slot"] == "judge_1"]
    for row in rows:
        row.update({
            "judge_id": f"fixture_{row['judge_slot']}", "judgment_status": "completed",
            "judge_call_performed": True,
        })
        for name in JUDGE_DIMENSIONS:
            row["dimensions"][name].update({
                "score": 0 if name == "unsupported_claim_count" else 0.8,
                "verdict": "pass", "confidence": 0.8, "rationale": "fixture rationale",
                "evidence": [], "judge_model": "fixture", "judge_prompt_version": "v1",
            })
    return rows


def valid_human_reviews(package_dir: Path, count: int = 96) -> list[dict[str, str]]:
    rows = read_csv(package_dir / "review/e2e_human_review.csv")
    for row in rows[:count]:
        row["review_status"] = "completed"
        for field in FINAL_HUMAN_LABEL_FIELDS:
            row[field] = "yes"
        row["human_overall_verdict"] = "pass"
    return rows


def valid_freeze_manifest(
    package_dir: Path, prompt_file: Path, generation_parameters_json: Path,
) -> dict[str, Any]:
    manifest = read_json(package_dir / "manifests/selective_eval_manifest.json")
    cases = read_jsonl(package_dir / "cases/e2e_case_frame.jsonl")
    return build_freeze_manifest(
        manifest, cases, run_dir=package_dir, prompt_file=prompt_file,
        generation_parameters=read_generation_parameters(generation_parameters_json),
        prompt_version="fixture-prompt-v1", generation_model_family="fixture-model-family",
        created_at_utc="2026-07-21T00:00:00Z",
    )
