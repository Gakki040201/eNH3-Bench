from __future__ import annotations

import unittest

from enh3bench.claim_rights import classify_claim_rights


class ClaimRightsProvenanceTests(unittest.TestCase):
    def test_reference_provenance_dominates_primary_text_class(self) -> None:
        result = classify_claim_rights(
            {
                "text_class": "primary_performance",
                "provenance_type": "reference",
                "source_text": "Smith et al. reported FE and NH3 yield. doi:10.1000/test",
                "faradaic_efficiency_percent": 80.0,
            }
        )
        self.assertEqual(result["maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertEqual(result["admissibility_status"], "reject_or_low_trust_provenance")
        self.assertIn("low_trust_provenance", result["overclaim_risk_flags"])
        self.assertIn("text_class_provenance_conflict", result["overclaim_risk_flags"])
        self.assertTrue(result["text_class_provenance_conflict"])

    def test_reference_text_inference_rejects_claim_rights(self) -> None:
        result = classify_claim_rights(
            {
                "text_class": "primary_performance",
                "source_section": "References",
                "source_text": (
                    "[1] Smith et al. Journal 12, 44-50 (2020). doi:10.1000/test\n"
                    "[2] Chen et al. Catalysis 9, 12-18 (2021). doi:10.1000/test2"
                ),
            }
        )
        self.assertEqual(result["maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertEqual(result["admissibility_status"], "reject_or_low_trust_provenance")

    def test_review_table_provenance_is_secondary_only(self) -> None:
        result = classify_claim_rights(
            {
                "text_class": "primary_performance_with_validation",
                "provenance_type": "review_table",
                "source_text": "| Reference | Catalyst | Electrolyte | FE (%) | 15N |\n|---|---|---|---|---|\n| Smith et al. (2020) | Fe | KOH | 10 | no |",
            }
        )
        self.assertEqual(result["claim_type"], "secondary_summary_claim")
        self.assertEqual(result["admissibility_status"], "secondary_only")
        self.assertEqual(result["maximum_supported_boundary"], "unsupported_or_secondary")

    def test_figure_caption_is_context_only(self) -> None:
        result = classify_claim_rights(
            {
                "text_class": "primary_performance",
                "source_text": "Fig. 2. FE and NH3 yield under N2 at different voltages.",
            }
        )
        self.assertEqual(result["provenance_type"], "figure_caption")
        self.assertEqual(result["admissibility_status"], "context_only_caption")
        self.assertIn("pair_with_primary_body_text", result["required_controls"])

    def test_body_performance_keeps_phase_a_rules(self) -> None:
        result = classify_claim_rights(
            {
                "text_class": "primary_performance",
                "source_section": "Results",
                "source_text": "N2 reduction reported 90% FE for ammonia.",
                "reaction_family": "eNRR",
                "nitrogen_source": "N2",
                "faradaic_efficiency_percent": 90.0,
            }
        )
        self.assertEqual(result["provenance_type"], "results")
        self.assertEqual(result["maximum_supported_boundary"], "cell_metric")
        self.assertEqual(result["admissibility_status"], "metric_only_or_validation_incomplete")

    def test_primary_result_table_cannot_exceed_cell_metric(self) -> None:
        result = classify_claim_rights(
            {
                "text_class": "primary_performance_with_validation",
                "source_text": "| Sample | FE (%) | NH3 yield | Voltage |\n|---|---|---|---|\n| this work | 60 | 2.1 | 2.4 |",
                "faradaic_efficiency_percent": 60.0,
                "nh3_yield_value": 2.1,
                "potential_value": 2.4,
            }
        )
        self.assertEqual(result["provenance_type"], "table")
        self.assertEqual(result["maximum_supported_boundary"], "cell_metric")
        self.assertEqual(result["admissibility_status"], "table_metric_only_requires_body_pairing")

    def test_supplementary_adds_crosscheck_flag(self) -> None:
        result = classify_claim_rights(
            {
                "text_class": "primary_performance",
                "provenance_type": "supplementary",
                "source_text": "Supplementary Table S1 reports 20% FE for NH3.",
                "faradaic_efficiency_percent": 20.0,
            }
        )
        self.assertIn("supplementary_requires_crosscheck", result["overclaim_risk_flags"])


if __name__ == "__main__":
    unittest.main()
