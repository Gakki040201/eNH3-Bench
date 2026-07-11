from __future__ import annotations

import unittest

from enh3bench.experiment_planner import propose_rule_based_routes
from enh3bench.experiment_schema import expand_routes_to_result_rows
from enh3bench.lab_profile import default_ustc_linnr_profile


class RouteHierarchyTests(unittest.TestCase):
    def test_electrolyte_parent_has_three_expected_children(self) -> None:
        routes = _electrolyte_routes()
        parent = next(route for route in routes if route["route_type"] == "electrolyte_window")
        children = [next(route for route in routes if route["route_id"] == child_id) for child_id in parent["child_route_ids"]]
        self.assertTrue(parent["is_route_group"])
        self.assertEqual(parent["stage_gate_status"], "non_executable")
        self.assertEqual(
            [child["route_type"] for child in children],
            ["water_content_window", "proton_donor_window", "salt_solvent_window"],
        )
        self.assertTrue(all(child["parent_route_id"] == parent["route_id"] for child in children))

    def test_shared_evidence_bonus_is_pooled_across_children(self) -> None:
        routes = _electrolyte_routes()
        children = [route for route in routes if route.get("parent_route_id")]
        self.assertEqual(len({route["shared_evidence_group"] for route in children}), 1)
        self.assertLessEqual(
            sum(float(route["within_stage_score"]) for route in children),
            max(int(route["priority_score"]) for route in children),
        )

    def test_non_executable_parent_has_no_result_execution_rows(self) -> None:
        routes = _electrolyte_routes()
        rows = expand_routes_to_result_rows(routes)
        parent_ids = {route["route_id"] for route in routes if route["is_route_group"]}
        self.assertFalse(parent_ids & {row["route_id"] for row in rows})


def _electrolyte_routes() -> list[dict[str, object]]:
    return propose_rule_based_routes(
        [
            {
                "gap_type": "solvent_management_tax",
                "route_type_hint": "electrolyte_window",
                "hidden_tax": "solvent_management_tax",
                "source_basis_id": "CR1",
                "paper_id": "P1",
                "source_span_id": "S1",
                "primary_evidence": True,
                "reaction_family": "LiNRR",
            }
        ],
        default_ustc_linnr_profile(profile_template="ustc-linnr-realistic"),
        "run1",
        reaction_family="LiNRR",
        require_baseline_first=True,
    )


if __name__ == "__main__":
    unittest.main()
