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
