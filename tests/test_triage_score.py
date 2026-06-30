from __future__ import annotations

import unittest

from enh3bench.triage_score import (
    is_performance_triage_eligible,
    score_performance_record,
)


class TriageScoreTests(unittest.TestCase):
    def test_complete_validated_record_can_be_priority(self) -> None:
        record = {
            "evidence_id": "E001",
            "paper_id": "P001",
            "text_class": "primary_performance_with_validation",
            "confidence": "high",
            "allow_field_extraction": True,
            "reaction_family": "LiNRR",
            "nitrogen_source": "15N2",
            "faradaic_efficiency_percent": 62.0,
            "nh3_yield_value": 10.5,
            "potential_value": -0.2,
            "current_density_mA_cm2": 20.0,
            "energy_efficiency_percent": 12.0,
            "stability_hours": 24.0,
            "isotope_validation": "yes",
            "blank_control": "yes",
            "contamination_control": "yes",
            "nox_screening": "yes",
            "detection_method": "NMR",
            "reactor_type": "flow cell",
            "source_span": "Flow cell Li-mediated N2 reduction used 15N2 and produced gas-phase ammonia.",
        }
        scored = score_performance_record(record)
        self.assertEqual(scored["recommendation"], "priority_follow_up")

    def test_high_fe_alone_is_not_priority(self) -> None:
        record = {
            "text_class": "primary_performance",
            "confidence": "high",
            "allow_field_extraction": True,
            "reaction_family": "eNRR",
            "nitrogen_source": "N2",
            "faradaic_efficiency_percent": 90.0,
            "isotope_validation": "yes",
            "blank_control": "yes",
            "contamination_control": "yes",
            "nox_screening": "yes",
            "source_span": "N2 reduction reported 90% FE.",
        }
        scored = score_performance_record(record)
        self.assertNotEqual(scored["recommendation"], "priority_follow_up")
        self.assertIn(scored["recommendation"], {"conditional_follow_up", "insufficient_evidence"})

    def test_n2_without_isotope_is_not_priority(self) -> None:
        record = {
            "text_class": "primary_performance",
            "confidence": "high",
            "allow_field_extraction": True,
            "reaction_family": "eNRR",
            "nitrogen_source": "N2",
            "faradaic_efficiency_percent": 60.0,
            "nh3_yield_value": 8.0,
            "potential_value": -0.3,
            "current_density_mA_cm2": 10.0,
            "blank_control": "yes",
            "contamination_control": "yes",
            "nox_screening": "yes",
            "source_span": "N2 reduction produced NH3 with controls but no isotope text.",
        }
        scored = score_performance_record(record)
        self.assertNotEqual(scored["recommendation"], "priority_follow_up")

    def test_review_table_is_ineligible(self) -> None:
        record = {"text_class": "review_table", "faradaic_efficiency_percent": 80.0}
        self.assertFalse(is_performance_triage_eligible(record))
        with self.assertRaises(ValueError):
            score_performance_record(record)


if __name__ == "__main__":
    unittest.main()
