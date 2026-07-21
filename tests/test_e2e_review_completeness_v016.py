from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from enh3bench.e2e_case_generation import E2E_REVIEW_COLUMNS
from enh3bench.e2e_eval_metrics import summarize_e2e
from enh3bench.e2e_eval_package import build_selective_eval_package
from enh3bench.e2e_eval_schema import (
    FINAL_HUMAN_LABEL_FIELDS,
    make_output_id,
    read_csv,
    read_jsonl,
    write_csv,
    write_json,
    write_jsonl,
)
from enh3bench.e2e_eval_validation import validate_selective_eval_package
from tests.selective_eval_test_helpers import (
    create_source_calibration_fixture,
    valid_api_outputs,
    valid_human_reviews,
    valid_machine_judgments,
)


class E2EReviewCompletenessV016Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source_root = self.base / "data/calibration"
        self.eval_root = self.base / "data/selective_eval"
        create_source_calibration_fixture(self.source_root)
        build_selective_eval_package(
            source_calibration_run_name="calibration_fixture",
            source_calibration_root=self.source_root,
            selective_eval_run_name="eval", selective_eval_root=self.eval_root,
            clean=True, validate_source_package=False,
        )
        self.package_dir = self.eval_root / "eval"
        self.review_path = self.package_dir / "review/e2e_human_review.csv"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def validate(self) -> dict:
        return validate_selective_eval_package(
            selective_eval_run_name="eval", selective_eval_root=self.eval_root,
            source_calibration_root=self.source_root, check_source_package=False,
        )

    def complete_row(self, row: dict[str, str]) -> None:
        row["review_status"] = "completed"
        for field in FINAL_HUMAN_LABEL_FIELDS:
            row[field] = "yes"
        row["human_overall_verdict"] = "pass"

    def write_reviews(self, rows: list[dict[str, str]]) -> None:
        write_csv(self.review_path, rows, E2E_REVIEW_COLUMNS)

    def write_outputs(self, count: int = 48) -> None:
        write_jsonl(
            self.package_dir / "cases/api_outputs.jsonl",
            valid_api_outputs(self.package_dir, count),
        )

    def test_completed_blank_review_fails(self) -> None:
        rows = read_csv(self.review_path)
        rows[0]["review_status"] = "completed"
        self.write_reviews(rows)
        result = self.validate()
        self.assertEqual(result["result"], "FAIL")
        self.assertEqual(result["counts"]["invalid_completed_human_review_count"], 1)
        self.assertTrue(any("completed_human_review_missing_label" in error for error in result["errors"]))

    def test_completed_review_without_matching_output_fails(self) -> None:
        rows = read_csv(self.review_path)
        self.complete_row(rows[0])
        self.write_reviews(rows)
        result = self.validate()
        self.assertEqual(result["result"], "FAIL")
        self.assertTrue(any("completed_human_review_missing_valid_output" in error for error in result["errors"]))

    def test_completed_review_mapped_to_wrong_output_fails(self) -> None:
        self.write_outputs()
        rows = read_csv(self.review_path)
        self.complete_row(rows[0])
        rows[0]["api_output_id"] = make_output_id(rows[2]["case_id"])
        self.write_reviews(rows)
        result = self.validate()
        self.assertEqual(result["result"], "FAIL")
        self.assertTrue(any("human_review_static_field_mismatch" in error for error in result["errors"]))

    def test_no_label_requires_notes(self) -> None:
        self.write_outputs()
        rows = valid_human_reviews(self.package_dir, 1)
        rows[0]["human_answer_correct"] = "no"
        rows[0]["human_notes"] = ""
        self.write_reviews(rows)
        result = self.validate()
        self.assertEqual(result["result"], "FAIL")
        self.assertTrue(any("human_review_notes_required" in error for error in result["errors"]))

    def test_duplicate_case_reviewer_observation_fails(self) -> None:
        rows = read_csv(self.review_path)
        rows[1]["reviewer_id"] = "R1"
        rows[1]["reviewer_slot"] = "reviewer_1"
        rows[1]["human_review_id"] = rows[0]["human_review_id"]
        self.write_reviews(rows)
        result = self.validate()
        self.assertEqual(result["result"], "FAIL")
        self.assertTrue(any("duplicate_human_review_observation" in error for error in result["errors"]))

    def test_partial_review_does_not_count_as_completed(self) -> None:
        self.write_outputs(1)
        rows = read_csv(self.review_path)
        rows[0]["review_status"] = "in_progress"
        rows[0]["human_answer_correct"] = "yes"
        self.write_reviews(rows)
        result = self.validate()
        self.assertEqual(result["result"], "PASS", result["errors"])
        self.assertEqual(result["counts"]["valid_completed_human_review_count"], 0)
        self.assertEqual(result["counts"]["package_stage"], "generated")

    def test_exact_96_valid_reviews_are_recognized(self) -> None:
        self.write_outputs()
        self.write_reviews(valid_human_reviews(self.package_dir))
        result = self.validate()
        self.assertEqual(result["result"], "PASS", result["errors"])
        counts = result["counts"]
        self.assertEqual(counts["valid_completed_human_review_count"], 96)
        self.assertEqual(counts["invalid_completed_human_review_count"], 0)
        self.assertEqual(counts["completed_reviewed_case_count"], 48)
        self.assertEqual(counts["cases_with_two_completed_reviewers"], 48)
        self.assertEqual(counts["completed_rows_per_reviewer"], {"R1": 48, "R2": 48})

    def test_one_output_and_other_case_review_is_not_ready(self) -> None:
        self.write_outputs(1)
        rows = read_csv(self.review_path)
        self.complete_row(rows[2])
        self.write_reviews(rows)
        summary = summarize_e2e(self.package_dir)
        self.assertFalse(summary["generation_complete"])
        self.assertFalse(summary["human_review_complete"])
        self.assertFalse(summary["human_metrics_ready"])

    def test_48_outputs_and_one_review_are_not_ready(self) -> None:
        self.write_outputs()
        self.write_reviews(valid_human_reviews(self.package_dir, 1))
        summary = summarize_e2e(self.package_dir)
        self.assertFalse(summary["human_review_complete"])
        self.assertFalse(summary["human_metrics_ready"])

    def test_48_outputs_and_95_reviews_are_not_ready(self) -> None:
        self.write_outputs()
        self.write_reviews(valid_human_reviews(self.package_dir, 95))
        summary = summarize_e2e(self.package_dir)
        self.assertEqual(summary["valid_completed_human_review_count"], 95)
        self.assertFalse(summary["human_review_complete"])

    def test_full_human_coverage_is_ready_but_metrics_remain_unavailable(self) -> None:
        self.write_outputs()
        self.write_reviews(valid_human_reviews(self.package_dir))
        summary = summarize_e2e(self.package_dir)
        self.assertTrue(summary["generation_complete"])
        self.assertTrue(summary["human_review_complete"])
        self.assertTrue(summary["human_metrics_ready"])
        self.assertEqual(summary["status"], "not_available")
        self.assertIsNone(summary["pass_rate"])

    def test_full_judge_and_human_coverage_have_separate_readiness(self) -> None:
        self.write_outputs()
        self.write_reviews(valid_human_reviews(self.package_dir))
        write_jsonl(
            self.package_dir / "cases/machine_judgments.jsonl",
            valid_machine_judgments(self.package_dir),
        )
        summary = summarize_e2e(self.package_dir)
        self.assertTrue(summary["judge_metrics_ready"])
        self.assertTrue(summary["judge_human_metrics_ready"])
        self.assertEqual(summary["status"], "not_available")

    def test_fabricated_metrics_fail_even_after_full_coverage(self) -> None:
        self.write_outputs()
        self.write_reviews(valid_human_reviews(self.package_dir))
        summary = summarize_e2e(self.package_dir)
        summary["pass_rate"] = 1.0
        summary["precision"] = 0.75
        write_json(self.package_dir / "reports/e2e_metrics_summary.json", summary)
        result = self.validate()
        self.assertEqual(result["result"], "FAIL")
        self.assertTrue(any("unimplemented_metric_must_be_null:pass_rate" in error for error in result["errors"]))
        self.assertTrue(any("unimplemented_metric_must_be_null:precision" in error for error in result["errors"]))

    def test_authoritative_summary_passes_exact_comparison(self) -> None:
        self.write_outputs()
        self.write_reviews(valid_human_reviews(self.package_dir))
        write_json(
            self.package_dir / "reports/e2e_metrics_summary.json",
            summarize_e2e(self.package_dir),
        )
        result = self.validate()
        self.assertEqual(result["result"], "PASS", result["errors"])


if __name__ == "__main__":
    unittest.main()
