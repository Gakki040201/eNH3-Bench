from __future__ import annotations

import unittest

from enh3bench.calibration_metrics import classification_metrics, summarize_reviews
from enh3bench.calibration_schema import blank_human_fields


def completed_span(item_id: str, reviewer: str, claim_label: str) -> dict[str, str]:
    row = {"calibration_item_id": item_id, "assigned_primary_stratum": "validation", **blank_human_fields("span")}
    row["reviewer_id"] = reviewer
    row["review_status"] = "completed"
    for field in tuple(row):
        if field.startswith("human_") and field.endswith("correct") or field == "human_context_sufficient":
            row[field] = "yes"
    row["human_claim_type_correct"] = claim_label
    if claim_label in {"no", "uncertain"}:
        row["human_notes"] = "Reviewer rationale."
    return row


def incomplete_span(item_id: str, reviewer: str) -> dict[str, str]:
    return {
        "calibration_item_id": item_id,
        "assigned_primary_stratum": "validation",
        **blank_human_fields("span"),
        "reviewer_id": reviewer,
    }


class CalibrationMetricsV016Tests(unittest.TestCase):
    def test_blank_labels_make_metrics_unavailable(self) -> None:
        row = {"calibration_item_id": "CC16S_X", **blank_human_fields("span")}
        result = summarize_reviews({"span": [row], "paper": [], "document": [], "link": []})
        self.assertEqual(result["status"], "not_available")
        self.assertIsNone(result["correctness_metrics"]["precision"])
        self.assertEqual(result["missing_reviewed_records"], 1)

    def test_fixture_correctness_metrics(self) -> None:
        rows = [completed_span("A", "r1", "yes"), completed_span("B", "r1", "no")]
        result = summarize_reviews({"span": rows, "paper": [], "document": [], "link": []})
        self.assertEqual(result["status"], "available")
        self.assertGreater(result["correctness_metrics"]["evaluated_assertions"], 0)
        self.assertLess(result["per_stratum_error_rate"]["validation"], 1.0)

    def test_reviewer_agreement_and_kappa(self) -> None:
        rows = [
            completed_span("A", "r1", "yes"), completed_span("A", "r2", "yes"),
            completed_span("B", "r1", "yes"), completed_span("B", "r2", "no"),
        ]
        result = summarize_reviews({"span": rows, "paper": [], "document": [], "link": []})
        self.assertEqual(result["reviewer_agreement"]["status"], "available")
        self.assertIsNotNone(result["reviewer_agreement"]["cohen_kappa"])

    def test_more_than_two_reviewers_is_invalid(self) -> None:
        rows = [completed_span("A", reviewer, "yes") for reviewer in ("r1", "r2", "r3")]
        result = summarize_reviews({"span": rows, "paper": [], "document": [], "link": []})
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["reviewer_agreement"]["status"], "invalid")
        self.assertTrue(any(
            error.startswith("reviewer_count_exceeds_phase_a_limit:span:A:")
            for error in result["validation_errors"]
        ))

    def test_two_completed_reviewers_have_full_row_and_item_coverage(self) -> None:
        rows = [
            completed_span(item, reviewer, "yes")
            for item in ("A", "B") for reviewer in ("r1", "r2")
        ]
        result = summarize_reviews({"span": rows, "paper": [], "document": [], "link": []})
        self.assertEqual(result["row_completeness"]["completion_rate"], 1.0)
        self.assertEqual(result["item_coverage"]["coverage_rate"], 1.0)
        self.assertEqual(result["reviewer_coverage"]["rows_per_reviewer"], {"r1": 2, "r2": 2})
        self.assertEqual(result["reviewer_coverage"]["completed_rows_per_reviewer"], {"r1": 2, "r2": 2})

    def test_one_completed_and_one_incomplete_reviewer_separates_rates(self) -> None:
        rows = [completed_span("A", "r1", "yes"), incomplete_span("A", "r2")]
        result = summarize_reviews({"span": rows, "paper": [], "document": [], "link": []})
        self.assertEqual(result["row_completeness"]["completion_rate"], 0.5)
        self.assertEqual(result["row_completeness"]["incomplete_review_rows"], 1)
        self.assertEqual(result["item_coverage"]["coverage_rate"], 1.0)

    def test_item_without_completed_reviewer_reduces_coverage(self) -> None:
        rows = [completed_span("A", "r1", "yes"), incomplete_span("B", "r1")]
        result = summarize_reviews({"span": rows, "paper": [], "document": [], "link": []})
        self.assertEqual(result["row_completeness"]["completion_rate"], 0.5)
        self.assertEqual(result["item_coverage"], {
            "total_unique_items": 2, "reviewed_unique_items": 1,
            "missing_unique_items": 1, "coverage_rate": 0.5,
        })

    def test_classification_precision_recall_macro_f1(self) -> None:
        result = classification_metrics([("a", "a"), ("a", "b"), ("b", "b")])
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["per_class"]["a"]["precision"], 0.5)
        self.assertEqual(result["per_class"]["b"]["recall"], 0.5)
        self.assertIsNotNone(result["macro_f1"])

    def test_correctness_is_not_misread_as_class_label(self) -> None:
        result = summarize_reviews({"span": [completed_span("A", "r1", "yes")], "paper": [], "document": [], "link": []})
        self.assertEqual(result["class_label_metrics"]["status"], "not_available")
        self.assertIn("not class labels", result["class_label_metrics"]["reason"])


if __name__ == "__main__":
    unittest.main()
