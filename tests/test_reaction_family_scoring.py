from __future__ import annotations

import unittest

from enh3bench.reaction_profiles import infer_reaction_family_detailed, score_reaction_families


class ReactionFamilyScoringTests(unittest.TestCase):
    def test_nitrate_impurity_screening_in_n2_enrr_stays_enrr(self) -> None:
        result = infer_reaction_family_detailed(
            text="N2-to-NH3 electrochemical nitrogen reduction included nitrate screening and background NOx checks."
        )
        self.assertEqual(result["reaction_family"], "eNRR")
        self.assertNotEqual(result["reaction_family"], "NO3RR")
        self.assertIn("span:nitrate_context_not_feed", result["reaction_family_signals"])

    def test_nitrate_feed_to_ammonia_is_no3rr(self) -> None:
        result = infer_reaction_family_detailed(text="Nitrate was used as the nitrogen source for nitrate-to-ammonia electroreduction.")
        self.assertEqual(result["reaction_family"], "NO3RR")
        self.assertEqual(result["reaction_family_confidence"], "high")

    def test_n2_literature_comparison_does_not_override_nitrate_target(self) -> None:
        result = infer_reaction_family_detailed(text=(
            "Electrochemical nitrate reduction used KNO3 and converted NO3 to NH3. "
            "The yield exceeded reported N2-to-NH3 conversions and was different from N2 reduction studies."
        ))
        self.assertEqual(result["reaction_family"], "NO3RR")
        self.assertIn(
            "span:external_n2_comparison_not_target_family",
            result["reaction_family_signals"],
        )

    def test_nitrite_feed_to_ammonia_is_no2rr(self) -> None:
        result = infer_reaction_family_detailed(text="Nitrite feed was converted to ammonia in the NO2RR cell.")
        self.assertEqual(result["reaction_family"], "NO2RR")
        self.assertEqual(result["reaction_family_confidence"], "high")

    def test_explicit_lithium_mediated_n2_reduction_is_linnr(self) -> None:
        result = infer_reaction_family_detailed(text="Lithium-mediated N2 reduction in THF used Li salt and formed an SEI.")
        self.assertEqual(result["reaction_family"], "LiNRR")
        self.assertEqual(result["reaction_family_confidence"], "high")
        self.assertFalse(result["reaction_family_conflict"])

    def test_thf_only_is_unclear(self) -> None:
        result = infer_reaction_family_detailed(text="The THF solvent was dried before electrolysis.")
        self.assertEqual(result["reaction_family"], "unclear")
        self.assertEqual(result["reaction_family_confidence"], "unclear")
        scores = score_reaction_families("The THF solvent was dried before electrolysis.")
        self.assertLess(scores["LiNRR"], 4)


if __name__ == "__main__":
    unittest.main()
