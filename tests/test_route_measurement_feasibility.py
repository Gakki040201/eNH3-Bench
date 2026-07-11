from __future__ import annotations

import unittest

from enh3bench.experiment_planner import propose_rule_based_routes
from enh3bench.lab_profile import default_ustc_linnr_profile


class RouteMeasurementFeasibilityTests(unittest.TestCase):
    def test_hor_route_flags_unavailable_h2_and_electrode_measurements(self) -> None:
        route = _route("HOR_proton_economy", _realistic_profile())
        self.assertEqual(route["priority_label"], "defer_until_capability_available")
        self.assertEqual(route["measurement_feasibility_status"], "infeasible")
        self.assertTrue({"H2", "anode_potential", "cathode_potential"} <= set(route["infeasible_measurements"]))
        self.assertTrue(route["measurement_capability_warnings"])
        self.assertTrue(route["boundary_not_closed_due_to_unavailable_measurements"])

    def test_product_state_route_requires_gas_and_liquid_analytics(self) -> None:
        profile = _realistic_profile()
        profile["analytics"]["liquid_NH4_quantification_available"] = False
        route = _route("product_state_accounting", profile)
        self.assertEqual(route["priority_label"], "defer_until_capability_available")
        self.assertIn("liquid_NH4", route["infeasible_measurements"])
        self.assertIn("product_state_split", route["infeasible_measurements"])

    def test_missing_optional_measurement_marks_route_partial(self) -> None:
        profile = _fully_capable_profile()
        profile["analytics"]["image_recording_available"] = False
        route = _route("interphase_resistance", profile)
        self.assertEqual(route["measurement_feasibility_status"], "partial")
        self.assertTrue(any("optional measurement unavailable" in warning for warning in route["measurement_capability_warnings"]))

    def test_priority_route_never_has_infeasible_mandatory_measurement(self) -> None:
        route = _route("HOR_proton_economy", _realistic_profile())
        self.assertNotEqual(route["priority_label"], "priority_experiment")
        self.assertTrue(set(route["mandatory_measurements"]) & set(route["infeasible_measurements"]))


def _route(route_type: str, profile: dict[str, object]) -> dict[str, object]:
    routes = propose_rule_based_routes(
        [
            {
                "gap_type": route_type,
                "route_type_hint": route_type,
                "hidden_tax": "hydrogen_logistics_tax" if route_type == "HOR_proton_economy" else "",
                "source_basis_id": "CR1",
                "paper_id": "P1",
                "source_span_id": "S1",
                "primary_evidence": True,
                "reaction_family": "LiNRR",
            }
        ],
        profile,
        "run1",
        reaction_family="LiNRR",
    )
    return next(route for route in routes if route["route_type"] == route_type)


def _realistic_profile() -> dict[str, object]:
    return default_ustc_linnr_profile(profile_template="ustc-linnr-realistic")


def _fully_capable_profile() -> dict[str, object]:
    profile = _realistic_profile()
    profile["electrochemistry"]["can_record_anode_cathode_potential"] = True
    profile["analytics"].update(
        {
            "gas_phase_NOx_quantification_available": True,
            "feed_gas_impurity_testing_available": True,
            "H2_quantification_available": True,
        }
    )
    return profile


if __name__ == "__main__":
    unittest.main()
