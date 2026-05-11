from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.field_grounding import ground_field, ground_record, summarize_grounding  # noqa: E402


class FieldGroundingTests(unittest.TestCase):
    def test_isotope_yes_without_15n_is_inferred(self) -> None:
        record = {"source_span": "NH3 was reported after electrolysis.", "isotope_validation": "yes"}
        result = ground_field(record, "isotope_validation")
        self.assertEqual(result["grounding_status"], "inferred")
        self.assertIn("isotope_validation", result["risk_flag"])

    def test_isotope_yes_with_15n_is_explicit(self) -> None:
        record = {"source_span": "15N2 isotope labeling confirmed NH3.", "isotope_validation": "yes"}
        self.assertEqual(ground_field(record, "isotope_validation")["grounding_status"], "explicit")

    def test_fe_numeric_with_fe_phrase_is_explicit(self) -> None:
        record = {"source_span": "The NH3 FE reached 62%.", "faradaic_efficiency_percent": 62.0}
        self.assertEqual(ground_field(record, "faradaic_efficiency_percent")["grounding_status"], "explicit")

    def test_blank_control_terms_recognized(self) -> None:
        record = {"source_span": "An Ar blank control was reported.", "blank_control": "yes"}
        self.assertEqual(ground_field(record, "blank_control")["grounding_status"], "explicit")

    def test_contamination_and_nox_terms_recognized(self) -> None:
        record = {
            "source_span": "NOx screening checked nitrate contamination and background ammonia.",
            "contamination_control": "yes",
            "nox_screening": "yes",
        }
        self.assertEqual(ground_field(record, "contamination_control")["grounding_status"], "explicit")
        self.assertEqual(ground_field(record, "nox_screening")["grounding_status"], "explicit")

    def test_summary_counts_risks(self) -> None:
        record = {"source_span": "NH3 was reported.", "isotope_validation": "yes"}
        grounding = ground_record(record)
        summary = summarize_grounding(grounding)
        self.assertGreater(summary["risk_flags"], 0)


if __name__ == "__main__":
    unittest.main()
