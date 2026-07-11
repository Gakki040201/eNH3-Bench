from __future__ import annotations

import unittest

from enh3bench.experiment_planner import apply_stage_gates, next_actionable_route, propose_rule_based_routes
from enh3bench.lab_profile import default_ustc_linnr_profile


class RouteStageGateTests(unittest.TestCase):
    def test_blocked_stage_two_cannot_be_next_actionable(self) -> None:
        routes = _gated_routes()
        baseline = next(route for route in routes if route["route_type"] == "baseline_repeatability")
        refreshed = apply_stage_gates(routes, {"completed_route_ids": [baseline["route_id"]]})
        next_route = next_actionable_route(refreshed)
        self.assertIsNotNone(next_route)
        self.assertEqual(next_route["route_type"], "contamination_control")
        water = next(route for route in refreshed if route["route_type"] == "water_content_window")
        self.assertEqual(water["stage_gate_status"], "blocked")

    def test_failure_triggered_postmortem_can_bypass_normal_ordering(self) -> None:
        routes = propose_rule_based_routes(
            [_gap("postmortem_failure_analysis")],
            _profile(),
            "run1",
            reaction_family="LiNRR",
        )
        refreshed = apply_stage_gates(routes, {"documented_failure": True})
        postmortem = next(route for route in refreshed if route["route_type"] == "postmortem_failure_analysis")
        self.assertEqual(postmortem["stage_gate_status"], "event_triggered")
        self.assertEqual(next_actionable_route(refreshed)["route_id"], postmortem["route_id"])

    def test_stage_one_can_be_human_waived(self) -> None:
        routes = _gated_routes()
        refreshed = apply_stage_gates(routes, {"human_stage_gate_waiver": True})
        contamination = next(route for route in refreshed if route["route_type"] == "contamination_control")
        self.assertEqual(contamination["stage_gate_status"], "waived")


def _gated_routes() -> list[dict[str, object]]:
    return propose_rule_based_routes(
        [
            _gap("contamination_control"),
            {
                **_gap("electrolyte_window"),
                "gap_type": "solvent_management_tax",
                "hidden_tax": "solvent_management_tax",
            },
        ],
        _profile(),
        "run1",
        reaction_family="LiNRR",
        require_baseline_first=True,
    )


def _gap(route_type: str) -> dict[str, object]:
    return {
        "gap_type": route_type,
        "route_type_hint": route_type,
        "source_basis_id": f"CR_{route_type}",
        "paper_id": "P1",
        "source_span_id": f"S_{route_type}",
        "primary_evidence": True,
        "reaction_family": "LiNRR",
    }


def _profile() -> dict[str, object]:
    profile = default_ustc_linnr_profile(profile_template="ustc-linnr-realistic")
    profile["analytics"]["gas_phase_NOx_quantification_available"] = True
    profile["analytics"]["feed_gas_impurity_testing_available"] = True
    return profile


if __name__ == "__main__":
    unittest.main()
