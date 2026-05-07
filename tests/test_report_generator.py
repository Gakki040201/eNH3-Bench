from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.report_generator import (  # noqa: E402
    generate_error_taxonomy_table,
    generate_field_performance_table,
    generate_method_comparison_table,
    generate_reliability_label_summary,
)


def example_evaluation() -> dict:
    return {
        "categorical": {
            "reaction_family": {
                "accuracy": 1.0,
                "correct": 2,
                "total": 2,
                "missing_predictions": 0,
            },
            "reliability_label": {
                "accuracy": 0.5,
                "correct": 1,
                "total": 2,
                "missing_predictions": 0,
            },
        },
        "numeric": {
            "faradaic_efficiency_percent": {
                "accuracy": 1.0,
                "within_tolerance": 1,
                "total_gold_values": 1,
                "missing_predictions": 0,
                "mean_absolute_error": 0.0,
                "max_absolute_error": 0.0,
            }
        },
        "hallucination_rate": 0.25,
        "missing_field_rate": 0.125,
    }


class ReportGeneratorTests(unittest.TestCase):
    def test_method_comparison_headers(self) -> None:
        markdown = generate_method_comparison_table(example_evaluation())
        self.assertIn("| Method | Mean categorical accuracy |", markdown)
        self.assertIn("Hallucination rate", markdown)

    def test_field_performance_headers(self) -> None:
        markdown = generate_field_performance_table(example_evaluation())
        self.assertIn("| Field | Type | Accuracy | Support |", markdown)
        self.assertIn("`reaction_family`", markdown)

    def test_error_taxonomy_headers(self) -> None:
        markdown = generate_error_taxonomy_table(example_evaluation())
        self.assertIn("| Error category | Signal | Interpretation |", markdown)
        self.assertIn("Categorical disagreement", markdown)

    def test_reliability_summary_headers(self) -> None:
        markdown = generate_reliability_label_summary(example_evaluation())
        self.assertIn("| Reliability-label metric | Value |", markdown)
        self.assertIn("Correct labels", markdown)


if __name__ == "__main__":
    unittest.main()
