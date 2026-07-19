from __future__ import annotations

import unittest

from enh3bench.claim_typing import assess_performance_evidence, classify_claim_type


class PerformanceEvidenceTests(unittest.TestCase):
    def test_quantitative_performance_is_result_claim(self) -> None:
        for text in (
            "The catalyst achieved FE = 20%.",
            "FEs of 20% and 30% were obtained.",
            "The Faradaic efficiency reached 42%.",
            "The NH3 yield rate was 15 μg h-1.",
            "The NH3 partial current density reached 100 mA cm-2.",
        ):
            with self.subTest(text=text):
                result = classify_claim_type({"source_text": text})
                self.assertEqual(result["semantic_claim_type"], "performance_result_claim")
                self.assertTrue(result["performance_result_evidence"])

    def test_qualitative_performance_is_context_only(self) -> None:
        for text in ("The catalyst showed high yield rate.", "Current density is important for performance."):
            with self.subTest(text=text):
                result = classify_claim_type({"source_text": text, "claim_type": "performance_claim"})
                self.assertEqual(result["semantic_claim_type"], "performance_context_claim")
                self.assertEqual(result["performance_evidence_strength"], "context_only")

    def test_current_study_comparative_result_is_result_claim(self) -> None:
        result = classify_claim_type({
            "source_text": "Our catalyst achieved a higher NH3 yield than the reference sample.",
            "claim_ownership": "target_authors",
        })
        self.assertEqual(result["semantic_claim_type"], "performance_result_claim")
        self.assertEqual(result["performance_evidence_strength"], "comparative_result")

    def test_non_ammonia_reaction_activity_is_not_ammonia_performance(self) -> None:
        for text in (
            "The HOR activity of Pt/C decreased after cycling.",
            "The Pt catalyst maintained higher HOR activity.",
            "HER activity increased after cycling.",
            "The OER activity reached a maximum.",
            "CO2RR activity was enhanced.",
        ):
            with self.subTest(text=text):
                result = classify_claim_type({"source_text": text, "claim_type": "performance_claim"})
                self.assertFalse(result["performance_result_evidence"])
                self.assertNotEqual(result["semantic_claim_type"], "performance_result_claim")

    def test_ammonia_metric_results_require_metric_specific_value_proximity(self) -> None:
        positive = (
            "The catalyst achieved an NH3 yield rate of 230 nmol s-1 cm-2.",
            "The Faradaic efficiency toward ammonia reached 86%.",
            "Faradaic efficiency reached 25%.",
            "The NH3 yield was 20 µg h-1 cm-2 at -0.5 V.",
            "The NH3 partial current density reached 50 mA cm-2.",
            "The NH3 partial current density increased compared with the control.",
        )
        for text in positive:
            with self.subTest(text=text):
                result = classify_claim_type({"source_text": text})
                self.assertTrue(result["performance_result_evidence"])
                self.assertTrue(result["target_ammonia_reaction_outcome_anchor"])
                self.assertEqual(result["semantic_claim_type"], "performance_result_claim")

    def test_unrelated_numeric_tokens_do_not_create_performance_results(self) -> None:
        negative = (
            "Faradaic efficiency was calculated according to Eq. 2.",
            "Faradaic efficiency is presented in Fig. 3.",
            "The catalyst showed high NH3 yield at -0.5 V.",
            "The current density was measured for 6 h.",
            "The activity was discussed in Ref. 12.",
            "The current density increased at -0.5 V.",
        )
        for text in negative:
            with self.subTest(text=text):
                result = classify_claim_type({"source_text": text, "claim_type": "performance_claim"})
                self.assertFalse(result["performance_result_evidence"])
                self.assertNotEqual(result["semantic_claim_type"], "performance_result_claim")

    def test_fe_material_names_do_not_match_fe_acronym(self) -> None:
        for text in (
            "FeS catalyst was synthesized.",
            "FeSe nanosheets were prepared.",
            "The Fe single atom catalyst was characterized.",
            "Fe SAC and Fe-based materials were compared.",
        ):
            with self.subTest(text=text):
                evidence = assess_performance_evidence({"source_text": text})
                self.assertFalse(evidence["performance_result_evidence"])
                self.assertNotEqual(
                    classify_claim_type({"source_text": text, "claim_type": "performance_claim"})[
                        "semantic_claim_type"
                    ],
                    "performance_result_claim",
                )


if __name__ == "__main__":
    unittest.main()
