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
            "The current density reached 100 mA cm-2.",
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
            "source_text": "Our catalyst achieved higher activity than the reference sample.",
            "claim_ownership": "target_authors",
        })
        self.assertEqual(result["semantic_claim_type"], "performance_result_claim")
        self.assertEqual(result["performance_evidence_strength"], "comparative_result")

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
