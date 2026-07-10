from __future__ import annotations

import unittest

from enh3bench.lab_profile import capability_available, default_ustc_linnr_profile, validate_lab_profile


class USTCLiNRRProfileTests(unittest.TestCase):
    def test_ustc_linnr_realistic_profile_validates(self) -> None:
        profile = default_ustc_linnr_profile(profile_template="ustc-linnr-realistic")
        valid, errors = validate_lab_profile(profile)
        self.assertTrue(valid, errors)

    def test_realistic_profile_has_sop_and_flow_capabilities(self) -> None:
        profile = default_ustc_linnr_profile(profile_template="ustc-linnr-realistic")
        for key in (
            "glovebox_available",
            "Karl_Fischer_available",
            "ion_chromatography_available",
            "can_do_flow_cell",
            "can_do_SSC",
            "has_Li_NRR_SOP",
            "Karl_Fischer_SOP",
            "IC_sampling_SOP",
        ):
            with self.subTest(key=key):
                self.assertTrue(capability_available(profile, key))

    def test_15n2_remains_false_by_default(self) -> None:
        profile = default_ustc_linnr_profile(profile_template="ustc-linnr-realistic")
        self.assertFalse(capability_available(profile, "isotopic_15N2_available"))
        self.assertFalse(capability_available(profile, "can_do_15N_control"))


if __name__ == "__main__":
    unittest.main()
