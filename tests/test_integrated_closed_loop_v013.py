from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from enh3bench.closed_loop import evaluate_baseline_gate, evaluate_closed_loop
from enh3bench.experiment_schema import migrate_experiment_route
from enh3bench.ledger_router import load_jsonl


class IntegratedClosedLoopV013Tests(unittest.TestCase):
    def test_three_approved_baseline_replicates_pass_and_unlock_stage_one(self) -> None:
        routes = _routes()
        results = _baseline_results(3, approved=True)
        gate = evaluate_baseline_gate(routes, results)
        self.assertEqual(gate["baseline_gate_status"], "passed")
        self.assertEqual(gate["valid_independent_replicates"], 3)
        self.assertEqual(gate["repeatability_statistics"]["FE"]["count"], 3)

        evaluation = _evaluate_fixture(routes, results)
        self.assertEqual(evaluation["baseline_gate_status"], "passed")
        self.assertEqual(evaluation["next_actionable_route"]["stage_rank"], 1)
        water = next(route for route in evaluation["_regenerated_records"] if route["route_type"] == "water_content_window")
        self.assertEqual(water["stage_gate_status"], "blocked")

    def test_completed_stage_one_routes_unlock_stage_two(self) -> None:
        routes = _routes()
        results = [
            *_baseline_results(3, approved=True),
            _simple_result("ER_run1_LiNRR_validation_gap_closure"),
            _simple_result("ER_run1_LiNRR_contamination_control"),
        ]
        evaluation = _evaluate_fixture(routes, results)
        self.assertEqual(evaluation["next_actionable_route"]["route_type"], "water_content_window")

    def test_two_baseline_replicates_are_insufficient(self) -> None:
        gate = evaluate_baseline_gate(_routes(), _baseline_results(2, approved=True))
        self.assertEqual(gate["baseline_gate_status"], "insufficient_replicates")

    def test_three_timepoints_from_one_execution_count_as_one_replicate(self) -> None:
        rows = _baseline_results(1, approved=True)
        rows.extend(
            [
                {**rows[0], "timepoint_id": "t1"},
                {**rows[0], "timepoint_id": "t2"},
            ]
        )
        gate = evaluate_baseline_gate(_routes(), rows)
        self.assertEqual(gate["valid_independent_replicates"], 1)
        self.assertEqual(gate["baseline_gate_status"], "insufficient_replicates")

    def test_missing_control_invalidates_baseline_gate(self) -> None:
        rows = _baseline_results(3, approved=True)
        rows[1]["controls_completed"] = []
        gate = evaluate_baseline_gate(_routes(), rows)
        self.assertEqual(gate["baseline_gate_status"], "invalid_controls")

    def test_missing_mandatory_measurement_blocks_baseline(self) -> None:
        rows = _baseline_results(3, approved=True)
        rows[1]["NH3_yield"] = ""
        gate = evaluate_baseline_gate(_routes(), rows)
        self.assertEqual(gate["baseline_gate_status"], "incomplete_measurements")

    def test_no_threshold_and_no_human_approval_awaits_review(self) -> None:
        gate = evaluate_baseline_gate(_routes(), _baseline_results(3, approved=False))
        self.assertTrue(gate["baseline_data_completeness"])
        self.assertEqual(gate["baseline_gate_status"], "awaiting_human_approval")

    def test_optional_profile_cv_thresholds_can_accept_complete_numeric_data(self) -> None:
        profile = {
            "minimum_valid_baseline_replicates": 3,
            "baseline_FE_CV_threshold_optional": 0.1,
            "baseline_yield_CV_threshold_optional": 0.1,
        }
        gate = evaluate_baseline_gate(_routes(), _baseline_results(3, approved=False), profile=profile)
        self.assertEqual(gate["baseline_gate_status"], "passed")


def _routes() -> list[dict[str, object]]:
    return [
        _route("baseline_repeatability", required_controls=["Ar blank"], mandatory=["FE", "NH3_yield"]),
        _route("validation_gap_closure"),
        _route("contamination_control"),
        _route("water_content_window"),
    ]


def _route(
    route_type: str,
    required_controls: list[str] | None = None,
    mandatory: list[str] | None = None,
) -> dict[str, object]:
    route = migrate_experiment_route(
        {
            "route_id": f"ER_run1_LiNRR_{route_type}",
            "run_name": "run1",
            "reaction_family": "LiNRR",
            "route_type": route_type,
            "priority_label": "priority_experiment",
            "priority_score": 70,
            "required_controls": required_controls or [],
            "required_measurements": mandatory or [],
            "mandatory_measurements": mandatory or [],
            "minimum_valid_replicates": 3 if route_type == "baseline_repeatability" else 1,
            "minimum_valid_baseline_replicates": 3,
            "independent_assembly_required": route_type == "baseline_repeatability",
        }
    )
    route["migration_warnings"] = []
    return route


def _baseline_results(count: int, approved: bool) -> list[dict[str, object]]:
    return [
        {
            "schema_version": "0.13",
            "route_id": "ER_run1_LiNRR_baseline_repeatability",
            "execution_id": f"EXEC_BASE_{index}",
            "experiment_id": f"EXP_BASE_{index}",
            "condition_id": "baseline",
            "replicate_id": f"rep_{index:02d}",
            "independent_replicate": True,
            "assembly_id": f"A{index}",
            "cell_build_id": f"C{index}",
            "success_status": "success",
            "controls_completed": ["Ar blank"],
            "controls_failed": [],
            "FE": str(50 + index),
            "NH3_yield": str(10 + index / 10),
            "human_baseline_approval": approved,
            "human_baseline_notes": "approved fixture" if approved else "",
            "validation_errors": [],
        }
        for index in range(1, count + 1)
    ]


def _simple_result(route_id: str) -> dict[str, object]:
    return {
        "route_id": route_id,
        "execution_id": f"EXEC_{route_id}",
        "success_status": "success",
        "controls_completed": [],
        "controls_failed": [],
        "validation_errors": [],
    }


def _evaluate_fixture(routes: list[dict[str, object]], results: list[dict[str, object]]) -> dict[str, object]:
    temp_dir = tempfile.TemporaryDirectory()
    _TEMP_DIRS.append(temp_dir)
    old_cwd = os.getcwd()
    os.chdir(temp_dir.name)
    try:
        _write_jsonl(Path("data/experiment_routes/run1/ranked_experiment_routes.jsonl"), routes)
        _write_jsonl(Path("data/experiment_results/run1/experiment_results_imported.jsonl"), results)
        evaluation = evaluate_closed_loop("run1")
        evaluation["_regenerated_records"] = load_jsonl(evaluation["regenerated_routes"])
        return evaluation
    finally:
        os.chdir(old_cwd)


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True))
            handle.write("\n")


_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []


if __name__ == "__main__":
    unittest.main()
