from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.evaluator import (  # noqa: E402
    evaluate_categorical_field,
    evaluate_numeric_field,
    exact_match,
    hallucination_rate,
    missing_field_rate,
    normalized_string_match,
    numeric_within_tolerance,
)


class EvaluatorTests(unittest.TestCase):
    def test_normalized_string_and_exact_match(self) -> None:
        self.assertTrue(normalized_string_match(" LiNRR ", "linrr"))
        self.assertTrue(exact_match({"reaction_family": "NO3RR"}, {"reaction_family": "no3rr"}, "reaction_family"))
        self.assertFalse(normalized_string_match("yes", "no"))

    def test_categorical_accuracy(self) -> None:
        gold = [
            {"evidence_id": "E001", "reaction_family": "LiNRR"},
            {"evidence_id": "E002", "reaction_family": "NO3RR"},
        ]
        pred = [
            {"evidence_id": "E001", "reaction_family": "LiNRR"},
            {"evidence_id": "E002", "reaction_family": "eNRR"},
        ]
        result = evaluate_categorical_field(gold, pred, "reaction_family")
        self.assertEqual(result["correct"], 1)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["accuracy"], 0.5)

    def test_numeric_tolerance(self) -> None:
        self.assertTrue(numeric_within_tolerance(10.0, 10.05, tolerance_abs=0.1))
        self.assertTrue(numeric_within_tolerance(100.0, 101.0, tolerance_rel=0.02))
        self.assertFalse(numeric_within_tolerance(10.0, 10.5, tolerance_abs=0.1))

    def test_numeric_field_summary(self) -> None:
        gold = [
            {"evidence_id": "E001", "faradaic_efficiency_percent": 62.0},
            {"evidence_id": "E002", "faradaic_efficiency_percent": 85.0},
            {"evidence_id": "E003", "faradaic_efficiency_percent": None},
        ]
        pred = [
            {"evidence_id": "E001", "faradaic_efficiency_percent": 62.05},
            {"evidence_id": "E002", "faradaic_efficiency_percent": None},
            {"evidence_id": "E003", "faradaic_efficiency_percent": 12.0},
        ]
        result = evaluate_numeric_field(
            gold,
            pred,
            "faradaic_efficiency_percent",
            tolerance_abs=0.1,
        )
        self.assertEqual(result["total_gold_values"], 2)
        self.assertEqual(result["within_tolerance"], 1)
        self.assertEqual(result["missing_predictions"], 1)
        self.assertEqual(result["accuracy"], 0.5)

    def test_hallucination_rate(self) -> None:
        gold = [
            {"evidence_id": "E001", "nh3_yield_value": None, "reaction_family": "LiNRR"},
            {"evidence_id": "E002", "nh3_yield_value": 5.0, "reaction_family": "NO3RR"},
        ]
        pred = [
            {"evidence_id": "E001", "nh3_yield_value": 10.0, "reaction_family": "LiNRR"},
            {"evidence_id": "E002", "nh3_yield_value": 5.0, "reaction_family": "NO3RR"},
        ]
        self.assertEqual(hallucination_rate(gold, pred, ["nh3_yield_value", "reaction_family"]), 0.25)

    def test_missing_field_rate(self) -> None:
        gold = [
            {"evidence_id": "E001", "nh3_yield_value": 10.0, "reaction_family": "LiNRR"},
            {"evidence_id": "E002", "nh3_yield_value": None, "reaction_family": "NO3RR"},
        ]
        pred = [
            {"evidence_id": "E001", "nh3_yield_value": None, "reaction_family": "LiNRR"},
            {"evidence_id": "E002", "nh3_yield_value": None, "reaction_family": ""},
        ]
        self.assertAlmostEqual(
            missing_field_rate(gold, pred, ["nh3_yield_value", "reaction_family"]),
            2 / 3,
        )


if __name__ == "__main__":
    unittest.main()
