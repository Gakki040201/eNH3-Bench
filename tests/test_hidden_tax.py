from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.hidden_tax import detect_hidden_taxes, export_hidden_tax_ledger


class HiddenTaxTests(unittest.TestCase):
    def test_high_fe_without_measurement_matrix_triggers_tax(self) -> None:
        result = detect_hidden_taxes(
            {
                "paper_id": "P001",
                "source_text": "The catalyst reached 90% FE for NH3.",
                "faradaic_efficiency_percent": 90.0,
            }
        )
        self.assertIn("measurement_matrix_tax", result["detected_taxes"])
        self.assertIn("NH3 yield", result["missing_measurements"])
        self.assertEqual(result["severity"], "high")

    def test_hor_text_triggers_hydrogen_logistics_tax(self) -> None:
        result = detect_hidden_taxes(
            {
                "paper_id": "P001",
                "source_text": "The reactor used hydrogen oxidation at the anode with H2 feed for proton economy.",
            }
        )
        self.assertIn("hydrogen_logistics_tax", result["detected_taxes"])

    def test_contamination_text_triggers_contamination_tax(self) -> None:
        result = detect_hidden_taxes(
            {
                "paper_id": "P001",
                "source_text": "NOx contamination, nitrate, nitrite, and background ammonia created a false positive risk.",
            }
        )
        self.assertIn("contamination_tax", result["detected_taxes"])
        self.assertIn("NOx/nitrate/nitrite screen", result["missing_measurements"])

    def test_export_hidden_tax_ledger_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = export_hidden_tax_ledger(
                [{"paper_id": "P001", "source_text": "90% FE for NH3.", "faradaic_efficiency_percent": 90.0}],
                "run1",
                Path(temp_dir),
            )
            self.assertTrue(Path(outputs["jsonl"]).exists())
            self.assertTrue(Path(outputs["csv"]).exists())


if __name__ == "__main__":
    unittest.main()
