from __future__ import annotations

import unittest

from enh3bench.benchmark_builder import build_all_benchmark_tasks
from enh3bench.benchmark_metrics import (
    boundary_overclaim_underclaim,
    evaluate_all_tasks,
    macro_f1,
    multilabel_jaccard_mean,
)


class BenchmarkMetricsTests(unittest.TestCase):
    def test_macro_f1_handles_missing_labels_safely(self) -> None:
        score = macro_f1(["a"], ["b"], labels=["a", "b", "c"])
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_boundary_overclaim_detects_prediction_rank_greater_than_human(self) -> None:
        result = boundary_overclaim_underclaim("process_partial", "cell_metric")
        self.assertTrue(result["overclaim"])
        self.assertFalse(result["underclaim"])

    def test_boundary_underclaim_detects_prediction_rank_lower_than_human(self) -> None:
        result = boundary_overclaim_underclaim("product_admissibility", "reactor_legibility")
        self.assertFalse(result["overclaim"])
        self.assertTrue(result["underclaim"])

    def test_multilabel_jaccard_handles_empty_empty_as_one(self) -> None:
        self.assertEqual(multilabel_jaccard_mean([[]], [[]]), 1.0)

    def test_evaluation_works_when_llm_fields_are_absent(self) -> None:
        tasks = build_all_benchmark_tasks([_reviewed_record()])
        results = evaluate_all_tasks(tasks)
        self.assertIn("claim_rights_boundary_classification", results)
        self.assertEqual(results["claim_rights_boundary_classification"]["llm"]["records_evaluated"], 0)
        self.assertEqual(results["source_span_classification"]["rule"]["records_evaluated"], 1)


def _reviewed_record() -> dict[str, object]:
    return {
        "audit_id": "AUD1",
        "run_name": "run1",
        "paper_id": "P1",
        "source_span_id": "S1",
        "evidence_id": "E1",
        "source_text": "N2 to NH3 gave FE with validation details.",
        "provenance_type": "body",
        "text_class": "primary_performance",
        "maximum_supported_boundary": "cell_metric",
        "admissibility_status": "metric_only_or_validation_incomplete",
        "validation_gates": {"isotope_15N": "yes", "blank_control": "yes", "nox_control": "missing", "contamination_control": "unclear", "quantification_method": "yes"},
        "detected_taxes": ["contamination_tax"],
        "required_controls": ["NOx/nitrate/nitrite screening"],
        "human_reviewer_id": "reviewer1",
        "human_review_status": "reviewed",
        "human_text_class": "primary_performance",
        "human_maximum_supported_boundary": "cell_metric",
        "human_admissibility_status": "accept_with_controls",
        "human_required_controls": "NOx/nitrate/nitrite screening",
        "human_hidden_tax": "contamination_tax",
        "human_experiment_decision": "control_required",
        "human_validation_isotope_15N": "explicit",
        "human_validation_blank_control": "explicit",
        "human_validation_NOx_control": "missing",
        "human_validation_contamination_control": "unclear",
        "human_validation_quantification_method": "explicit",
    }


if __name__ == "__main__":
    unittest.main()
