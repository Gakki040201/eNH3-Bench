from __future__ import annotations

import unittest

from enh3bench.experiment_schema import expand_route_execution_rows, expand_routes_to_result_rows


class ExperimentMatrixExpansionTests(unittest.TestCase):
    def test_two_conditions_with_two_replicates_expand_to_four_rows(self) -> None:
        route = _route(
            "validation_gap_closure",
            [
                {"condition_id": "baseline", "planned_value": "base"},
                {"condition_id": "perturbed", "planned_value": "changed"},
            ],
            replicates=2,
        )
        rows = expand_route_execution_rows(route)
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            {(row["condition_id"], row["replicate_id"]) for row in rows},
            {("baseline", "rep_01"), ("baseline", "rep_02"), ("perturbed", "rep_01"), ("perturbed", "rep_02")},
        )
        self.assertEqual(len({row["execution_id"] for row in rows}), 4)

    def test_default_replicate_override_expands_each_condition(self) -> None:
        route = _route("validation_gap_closure", [{"condition_id": "baseline"}], replicates=1)
        rows = expand_route_execution_rows(route, default_replicates=2)
        self.assertEqual([row["replicate_id"] for row in rows], ["rep_01", "rep_02"])

    def test_no_expand_matrix_uses_only_first_condition(self) -> None:
        route = _route(
            "validation_gap_closure",
            [{"condition_id": "baseline"}, {"condition_id": "perturbed"}],
            replicates=2,
        )
        rows = expand_route_execution_rows(route, expand_matrix=False)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["condition_id"] for row in rows}, {"baseline"})

    def test_baseline_rows_are_ordered_before_other_routes(self) -> None:
        other = _route("validation_gap_closure", [{"condition_id": "baseline"}])
        baseline = _route(
            "baseline_repeatability",
            [{"condition_id": "baseline"}, {"condition_id": "stress_or_control"}],
        )
        rows = expand_routes_to_result_rows([other, baseline])
        self.assertEqual([row["route_id"] for row in rows[:3]], [baseline["route_id"]] * 3)


def _route(route_type: str, matrix: list[dict[str, str]], replicates: int = 1) -> dict[str, object]:
    return {
        "route_id": f"ER_{route_type}",
        "run_name": "run1",
        "route_type": route_type,
        "variable_type": "control_experiment",
        "experimental_matrix": matrix,
        "default_replicate_count": replicates,
        "replicate_type": "independent",
        "independent_assembly_required": route_type == "baseline_repeatability",
        "required_controls": [],
        "required_measurements": [],
    }


if __name__ == "__main__":
    unittest.main()
