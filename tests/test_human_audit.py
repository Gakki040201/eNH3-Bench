from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from enh3bench.human_audit import import_human_audit_sheet, merge_audit_sources, score_audit_priority
from enh3bench.ledger_router import load_jsonl


class HumanAuditTests(unittest.TestCase):
    def test_priority_increases_for_llm_more_permissive(self) -> None:
        base = _base_record()
        flagged = dict(base, llm_more_permissive=True)
        self.assertGreater(score_audit_priority(flagged)["audit_priority_score"], score_audit_priority(base)["audit_priority_score"])

    def test_priority_increases_for_low_trust_provenance(self) -> None:
        base = _base_record()
        flagged = dict(base, is_reject_or_low_trust=True)
        self.assertGreater(score_audit_priority(flagged)["audit_priority_score"], score_audit_priority(base)["audit_priority_score"])

    def test_priority_increases_for_missing_15n(self) -> None:
        base = _base_record()
        flagged = dict(
            base,
            source_text="N2 to NH3 was reported with ammonia production.",
            validation_gates={"isotope_15N": "missing", "blank_control": "yes", "nox_control": "yes"},
        )
        self.assertGreater(score_audit_priority(flagged)["audit_priority_score"], score_audit_priority(base)["audit_priority_score"])

    def test_merge_preserves_rule_fields_and_separates_llm_fields(self) -> None:
        rule = {
            "claim_id": "CR_E1",
            "paper_id": "P1",
            "source_span_id": "S1",
            "evidence_id": "E1",
            "text_class": "primary_performance",
            "maximum_supported_boundary": "unsupported_or_secondary",
            "source_text": "Primary source text.",
        }
        llm = {
            "evidence_id": "E1",
            "llm_model": "deepseek-v4-pro",
            "llm_verification": {"maximum_supported_boundary": "cell_metric", "text_class": "primary_performance"},
            "boundary_agreement": False,
            "llm_more_permissive": True,
        }
        merged = merge_audit_sources([rule], llm_records=[llm])
        self.assertEqual(merged[0]["maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertEqual(merged[0]["llm_maximum_supported_boundary"], "cell_metric")
        self.assertTrue(merged[0]["llm_more_permissive"])

    def test_import_writes_errors_for_invalid_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "reviewed.csv"
            _write_rows(
                input_path,
                [
                    dict(_valid_reviewed_row(), human_maximum_supported_boundary="bad_boundary"),
                ],
            )
            outputs = import_human_audit_sheet(input_path, "run1", output_dir=Path(temp_dir) / "human_audit")
            self.assertEqual(outputs["reviewed_invalid"], 1)
            self.assertTrue(Path(outputs["errors_csv"]).exists())
            self.assertIn("invalid human_maximum_supported_boundary", Path(outputs["errors_csv"]).read_text(encoding="utf-8-sig"))

    def test_accept_as_gold_false_does_not_write_gold_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "reviewed.csv"
            _write_rows(input_path, [_valid_reviewed_row()])
            outputs = import_human_audit_sheet(input_path, "run1", output_dir=Path(temp_dir) / "human_audit")
            self.assertEqual(outputs["gold_written"], 0)
            self.assertFalse((Path(temp_dir) / "gold" / "run1").exists())

    def test_accept_as_gold_true_writes_only_valid_reviewed_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "reviewed.csv"
            unreviewed = dict(_valid_reviewed_row(), audit_id="AUD2", human_review_status="unreviewed")
            _write_rows(input_path, [_valid_reviewed_row(), unreviewed])
            outputs = import_human_audit_sheet(
                input_path,
                "run1",
                output_dir=Path(temp_dir) / "human_audit",
                accept_as_gold=True,
            )
            self.assertEqual(outputs["gold_written"], 1)
            gold_records = load_jsonl(outputs["gold_jsonl"])
            self.assertEqual(len(gold_records), 1)
            self.assertEqual(gold_records[0]["audit_id"], "AUD1")


def _base_record() -> dict[str, object]:
    return {
        "source_text": "Control source text with explicit validation.",
        "provenance_type": "body",
        "validation_gates": {"isotope_15N": "yes", "blank_control": "yes", "nox_control": "yes"},
        "maximum_supported_boundary": "cell_metric",
    }


def _valid_reviewed_row() -> dict[str, str]:
    return {
        "audit_id": "AUD1",
        "paper_id": "P1",
        "source_span_id": "S1",
        "evidence_id": "E1",
        "source_text": "Primary source text.",
        "text_class": "primary_performance",
        "maximum_supported_boundary": "cell_metric",
        "human_reviewer_id": "reviewer1",
        "human_review_status": "reviewed",
        "human_text_class": "primary_performance",
        "human_maximum_supported_boundary": "cell_metric",
        "human_admissibility_status": "accept",
        "human_required_controls": "",
        "human_hidden_tax": "",
        "human_experiment_decision": "priority_experiment",
        "human_validation_isotope_15N": "explicit",
        "human_validation_blank_control": "explicit",
        "human_validation_NOx_control": "explicit",
        "human_validation_contamination_control": "not_applicable",
        "human_validation_quantification_method": "explicit",
        "human_notes": "",
    }


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
