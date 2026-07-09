from __future__ import annotations

import subprocess
import sys
import unittest

from enh3bench.calibration import boundary_overclaim_underclaim, compute_hidden_tax_metrics


class CalibrationTests(unittest.TestCase):
    def test_boundary_overclaim_underclaim_detects_rule_overclaim(self) -> None:
        result = boundary_overclaim_underclaim("process_partial", "cell_metric")
        self.assertTrue(result["overclaim"])
        self.assertFalse(result["underclaim"])

    def test_boundary_overclaim_underclaim_detects_rule_underclaim(self) -> None:
        result = boundary_overclaim_underclaim("product_admissibility", "reactor_legibility")
        self.assertFalse(result["overclaim"])
        self.assertTrue(result["underclaim"])

    def test_hidden_tax_jaccard_handles_empty_lists_safely(self) -> None:
        metrics = compute_hidden_tax_metrics(
            [
                {
                    "human_review_status": "reviewed",
                    "human_text_class": "primary_performance",
                    "human_maximum_supported_boundary": "cell_metric",
                    "human_admissibility_status": "accept",
                    "human_experiment_decision": "priority_experiment",
                    "detected_taxes": [],
                    "human_hidden_tax": [],
                }
            ]
        )
        self.assertEqual(metrics["hidden_tax_exact_match_rate"], 1.0)
        self.assertEqual(metrics["hidden_tax_jaccard_mean"], 1.0)

    def test_calibration_cli_fails_clearly_without_reviewed_records(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/calibrate_boundary_ledger.py",
                "--run-name",
                "__missing_phase_d_reviewed_records__",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No reviewed audit records found", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
