from __future__ import annotations

import unittest

from enh3bench.reaction_profiles import (
    experimental_demonstration_allowed,
    get_reaction_profile,
    infer_reaction_family_from_text,
    normalize_reaction_family,
    profile_hidden_taxes,
    profile_route_types,
)


class ReactionProfileTests(unittest.TestCase):
    def test_infer_linnr_from_lithium_mediated_terms(self) -> None:
        text = "Lithium-mediated N2 reduction used Li salt in THF with SEI formation."
        self.assertEqual(infer_reaction_family_from_text(text), "LiNRR")

    def test_infer_no3rr_from_nitrate_text(self) -> None:
        self.assertEqual(infer_reaction_family_from_text("Nitrate reduction to ammonia was measured."), "NO3RR")

    def test_infer_no2rr_from_nitrite_text(self) -> None:
        self.assertEqual(infer_reaction_family_from_text("Nitrite electroreduction produced NH3."), "NO2RR")

    def test_infer_norr_from_no_reduction_text(self) -> None:
        self.assertEqual(infer_reaction_family_from_text("NO reduction to NH3 used gas handling blanks."), "NORR")

    def test_normalize_aliases(self) -> None:
        self.assertEqual(normalize_reaction_family("li-nrr"), "LiNRR")
        self.assertEqual(normalize_reaction_family("nitrate_reduction"), "NO3RR")
        self.assertEqual(normalize_reaction_family("unknown"), "unclear")

    def test_linnr_profile_contains_full_hidden_tax_and_route_set(self) -> None:
        taxes = profile_hidden_taxes("LiNRR")
        routes = profile_route_types("LiNRR")
        self.assertIn("solvent_management_tax", taxes)
        self.assertIn("resistance_or_renewal_tax", taxes)
        self.assertIn("wetting_outlet_capture_tax", taxes)
        self.assertIn("hydrogen_logistics_tax", taxes)
        self.assertIn("electrolyte_window", routes)
        self.assertTrue(experimental_demonstration_allowed("LiNRR"))

    def test_non_linnr_profiles_are_not_wet_lab_demo_by_default(self) -> None:
        self.assertFalse(experimental_demonstration_allowed("eNRR"))
        self.assertFalse(experimental_demonstration_allowed("NO3RR"))
        self.assertFalse(get_reaction_profile("mixed")["experimental_demonstration_allowed"])


if __name__ == "__main__":
    unittest.main()
