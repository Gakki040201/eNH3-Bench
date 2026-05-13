from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.toolbench_evaluator import (  # noqa: E402
    compare_methods,
    evaluate_method,
    write_comparison_markdown,
)


class ToolBenchEvaluatorTests(unittest.TestCase):
    def test_evaluate_method(self) -> None:
        gold = [
            {
                "record_id": "E001",
                "reaction_family": "LiNRR",
                "nitrogen_source": "15N2",
                "isotope_validation": "yes",
                "blank_control": "yes",
                "contamination_control": "yes",
                "nox_screening": "yes",
                "reliability_label": "B",
                "FE_percent": 61.0,
                "EE_percent": None,
                "NH3_yield": 12.0,
                "potential": None,
                "stability": None,
            }
        ]
        pred = [
            {
                "record_id": "E001",
                "method_name": "method",
                "reaction_family": "LiNRR",
                "nitrogen_source": "15N2",
                "isotope_validation": "yes",
                "blank_control": "yes",
                "contamination_control": "unclear",
                "nox_screening": "yes",
                "reliability_label": "B",
                "FE_percent": 61.05,
                "NH3_yield": 12.1,
                "source_grounding_status": "explicit",
            }
        ]
        result = evaluate_method(gold, pred, "method")
        self.assertEqual(result["categorical"]["reaction_family"]["accuracy"], 1.0)
        self.assertEqual(result["numeric"]["FE_percent"]["accuracy"], 1.0)
        self.assertEqual(result["reliability_label_agreement"], 1.0)
        self.assertEqual(result["source_grounding_coverage"], 1.0)

    def test_unsupported_validation_yes_rate(self) -> None:
        gold = [{"record_id": "E001", "isotope_validation": "unclear", "reliability_label": "D"}]
        pred = [{"record_id": "E001", "isotope_validation": "yes", "reliability_label": "B"}]
        result = evaluate_method(gold, pred, "method")
        self.assertEqual(result["unsupported_validation_yes_rate"], 1.0)

    def test_compare_methods_and_markdown(self) -> None:
        gold = [{"record_id": "E001", "reaction_family": "NO3RR", "reliability_label": "C"}]
        runs = {"m1": [{"record_id": "E001", "reaction_family": "NO3RR", "reliability_label": "C"}]}
        results = compare_methods(gold, runs)
        markdown = write_comparison_markdown(results)
        self.assertIn("eNH3-ExtractBench Method Comparison", markdown)
        self.assertIn("m1", markdown)


if __name__ == "__main__":
    unittest.main()
