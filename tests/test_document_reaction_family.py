from __future__ import annotations

import unittest

from enh3bench.reaction_profiles import (
    assess_document_reaction_family,
    assess_effective_reaction_family,
    build_document_reaction_family_context,
)


class DocumentReactionFamilyTests(unittest.TestCase):
    def test_strong_document_title_families(self) -> None:
        cases = {
            "Electrochemical ammonia synthesis via nitrate reduction": "NO3RR",
            "Selective nitrite reduction to ammonia": "NO2RR",
            "Nitric oxide reduction to ammonia": "NORR",
            "Lithium-mediated nitrogen reduction": "LiNRR",
            "Dinitrogen reduction to ammonia": "eNRR",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                result = assess_document_reaction_family({"paper_title": title})
                self.assertEqual(result["document_reaction_family"], expected)
                self.assertEqual(result["document_reaction_family_confidence"], "high")

    def test_document_title_corrects_nonexplicit_legacy_family_and_marks_conflict(self) -> None:
        result = assess_effective_reaction_family({
            "paper_title": "Electrochemical ammonia synthesis via nitrate reduction",
            "source_text": "High activity was observed for the catalyst.",
            "reaction_family": "eNRR",
        })
        self.assertEqual(result["effective_reaction_family"], "NO3RR")
        self.assertEqual(result["effective_reaction_family_source"], "high_confidence_document")
        self.assertTrue(result["reaction_family_correction"])
        self.assertTrue(result["document_target_reaction_family_conflict"])

    def test_explicit_high_confidence_target_family_has_priority(self) -> None:
        result = assess_effective_reaction_family({
            "paper_title": "Nitrate reduction pathways in mixed systems",
            "source_text": "This target reports dinitrogen reduction to ammonia under N2.",
            "reaction_family": "eNRR",
        })
        self.assertEqual(result["effective_reaction_family"], "eNRR")
        self.assertEqual(result["effective_reaction_family_source"], "explicit_high_confidence_target_span")
        self.assertFalse(result["document_target_reaction_family_conflict"])

    def test_document_context_uses_document_id_title_fallback_once(self) -> None:
        context = build_document_reaction_family_context(
            {"document_id": "P0090_Wu_2021_Electrochemical_ammonia_synthesis_via_nitrate_reduction"},
            [],
            [],
        )
        result = assess_document_reaction_family(context)
        self.assertEqual(result["document_reaction_family"], "NO3RR")

    def test_p0090_nitrate_target_is_not_routed_to_enrr_by_comparison_text(self) -> None:
        result = assess_effective_reaction_family({
            "paper_title": "Electrochemical ammonia synthesis via nitrate reduction on Fe single atom catalyst",
            "source_text": (
                "Electrocatalytic nitrate reduction converted NO3--to-NH3 in KNO3 electrolyte. "
                "The yield exceeded reported N2-to-NH3 conversions and differed from N2 reduction studies."
            ),
            "reaction_family": "eNRR",
        })
        self.assertEqual(result["document_reaction_family"], "NO3RR")
        self.assertEqual(result["effective_reaction_family"], "NO3RR")
        self.assertNotEqual(result["effective_reaction_family"], "eNRR")


if __name__ == "__main__":
    unittest.main()
