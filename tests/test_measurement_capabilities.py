from __future__ import annotations

import unittest

from enh3bench.lab_profile import (
    default_ustc_linnr_profile,
    feasible_measurements,
    infeasible_measurements,
    measurement_feasibility_status,
    missing_capabilities_for_measurements,
)


class MeasurementCapabilityTests(unittest.TestCase):
    def test_realistic_profile_supports_liquid_but_not_h2_or_electrode_potentials(self) -> None:
        profile = default_ustc_linnr_profile(profile_template="ustc-linnr-realistic")
        self.assertIn("nitrate", feasible_measurements(profile, ["nitrate"]))
        self.assertEqual(
            set(infeasible_measurements(profile, ["H2", "anode_potential", "cathode_potential"])),
            {"H2", "anode_potential", "cathode_potential"},
        )
        self.assertIn("H2_quantification_available", missing_capabilities_for_measurements(profile, ["H2"]))

    def test_missing_optional_measurement_is_partial(self) -> None:
        profile = default_ustc_linnr_profile(profile_template="ustc-linnr-realistic")
        self.assertEqual(measurement_feasibility_status(profile, ["liquid_NH4"], ["H2"]), "partial")

    def test_missing_mandatory_measurement_is_infeasible(self) -> None:
        profile = default_ustc_linnr_profile(profile_template="ustc-linnr-realistic")
        self.assertEqual(measurement_feasibility_status(profile, ["H2"]), "infeasible")


if __name__ == "__main__":
    unittest.main()
