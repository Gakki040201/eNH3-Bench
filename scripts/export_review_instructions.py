from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.audit_schema import (  # noqa: E402
    HUMAN_ADMISSIBILITY_STATUSES,
    HUMAN_BOUNDARIES,
    HUMAN_EXPERIMENT_DECISIONS,
    HUMAN_HIDDEN_TAX_TYPES,
    HUMAN_TEXT_CLASSES,
    NEEDS_HUMAN_REVIEW_ALIAS_NOTE,
    VALIDATION_GATE_LABELS,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export BoundaryLedger human-review instructions.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "human_audit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.output_dir / args.run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_dir / "REVIEW_INSTRUCTIONS.md"
    output_path.write_text(_render(args.run_name), encoding="utf-8", newline="\n")
    print(f"review_instructions: {output_path}")
    return 0


def _render(run_name: str) -> str:
    return "\n".join(
        [
            f"# Human Review Instructions: {run_name}",
            "",
            "## Review protocol",
            "",
            "Edit only the human_* columns in human_audit_sheet.csv.",
            "Set human_review_status to reviewed only when the core labels are complete.",
            "Use needs_second_reviewer for records that cannot be decided from the provided source text.",
            "Do not promote LLM output to gold. LLM fields are disagreement cues only.",
            "Do not overwrite rule columns. Save a copy such as human_audit_sheet.reviewed.csv before import.",
            "rule_needs_human_review, llm_needs_human_review, and overall_needs_human_review show separate routing decisions.",
            NEEDS_HUMAN_REVIEW_ALIAS_NOTE,
            "",
            "## Required reviewed fields",
            "",
            "- human_reviewer_id",
            "- human_review_status = reviewed",
            "- human_text_class",
            "- human_maximum_supported_boundary",
            "- human_admissibility_status",
            "- human_experiment_decision",
            "",
            "## Allowed human_text_class labels",
            "",
            _bullet_list(HUMAN_TEXT_CLASSES),
            "",
            "## Allowed human_maximum_supported_boundary labels",
            "",
            _bullet_list(HUMAN_BOUNDARIES),
            "",
            "## Allowed human_admissibility_status labels",
            "",
            _bullet_list(HUMAN_ADMISSIBILITY_STATUSES),
            "",
            "## Allowed human_experiment_decision labels",
            "",
            _bullet_list(HUMAN_EXPERIMENT_DECISIONS),
            "",
            "## Allowed human_hidden_tax labels",
            "",
            _bullet_list(HUMAN_HIDDEN_TAX_TYPES),
            "",
            "## Validation gate labels",
            "",
            _bullet_list(VALIDATION_GATE_LABELS),
            "",
            "## Examples",
            "",
            "- Reference list: label as reference_list, unsupported_or_secondary, reject or reject_or_low_trust_provenance.",
            "- Review table: label as review_table, unsupported_or_secondary, secondary_only.",
            "- Figure caption: label as figure_caption unless paired body evidence supports a stronger class.",
            "- Primary Li-NRR performance without 15N: keep performance class, but use cell_metric or lower with controls required.",
            "- Flow or HOR claim without product state: do not move beyond reactor_legibility and require product accounting.",
            "- Process claim without capture or solvent inventory: mark process_partial or plant_facing_insufficient, not full plant support.",
            "",
            "## What not to do",
            "",
            "- Do not use outside knowledge to fill missing controls.",
            "- Do not mark a row reviewed when the source text is insufficient.",
            "- Do not change claim_rights_ledger or llm_verified_claims.",
            "- Do not create gold labels unless the reviewed CSV is imported with --accept-as-gold.",
            "",
            "## Import command",
            "",
            "```powershell",
            (
                "python scripts/import_human_audit_sheet.py "
                f"--run-name {run_name} --input data\\human_audit\\{run_name}\\human_audit_sheet.reviewed.csv"
            ),
            "```",
            "",
        ]
    )


def _bullet_list(values: tuple[str, ...]) -> str:
    return "\n".join(f"- {value}" for value in values)


if __name__ == "__main__":
    raise SystemExit(main())
