from __future__ import annotations

import unittest

from enh3bench.experiment_planner import propose_rule_based_routes
from enh3bench.experiment_schema import expand_route_execution_rows
from enh3bench.lab_profile import default_ustc_linnr_profile


class BaselineReplicateTests(unittest.TestCase):
    def test_baseline_expands_to_three_independent_rows_without_stress(self) -> None:
        routes = propose_rule_based_routes(
            [],
            default_ustc_linnr_profile(),
            "run1",
            reaction_family="LiNRR",
            lab_demo_only=True,
            require_baseline_first=True,
        )
        route = routes[0]
        rows = expand_route_execution_rows(route)
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["condition_id"] for row in rows}, {"baseline"})
        self.assertEqual([row["replicate_id"] for row in rows], ["rep_01", "rep_02", "rep_03"])
        self.assertTrue(all(row["independent_replicate"] for row in rows))
        self.assertEqual(route["minimum_valid_replicates"], 3)
        self.assertTrue(route["independent_assembly_required"])
        self.assertNotIn("stress_or_control", {item["condition_id"] for item in route["experimental_matrix"]})


if __name__ == "__main__":
    unittest.main()
