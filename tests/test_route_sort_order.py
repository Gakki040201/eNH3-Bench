from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from enh3bench.experiment_planner import rank_routes
from enh3bench.experiment_route_card import export_route_cards


class RouteSortOrderTests(unittest.TestCase):
    def test_baseline_precedes_later_stage_despite_lower_raw_score(self) -> None:
        routes = rank_routes(
            [
                _route("water_content_window", 2, 99),
                _route("baseline_repeatability", 0, 5),
            ]
        )
        self.assertEqual(routes[0]["route_type"], "baseline_repeatability")

    def test_contamination_precedes_screening_with_equal_gate_status(self) -> None:
        routes = rank_routes(
            [
                _route("salt_solvent_window", 2, 99, status="blocked"),
                _route("contamination_control", 1, 5, status="blocked"),
                _route("proton_donor_window", 2, 98, status="blocked"),
                _route("water_content_window", 2, 97, status="blocked"),
            ]
        )
        self.assertEqual(routes[0]["route_type"], "contamination_control")

    def test_exported_cards_are_grouped_by_stage(self) -> None:
        routes = [
            _route("water_content_window", 2, 99, status="blocked"),
            _route("baseline_repeatability", 0, 5),
            _route("contamination_control", 1, 20, status="blocked"),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            path = export_route_cards(routes, "run1", output_dir=Path(temp_dir))
            text = Path(path).read_text(encoding="utf-8")
        self.assertLess(text.index("Stage 0:"), text.index("Stage 1:"))
        self.assertLess(text.index("Stage 1:"), text.index("Stage 2:"))


def _route(route_type: str, stage_rank: int, score: int, status: str = "actionable") -> dict[str, object]:
    return {
        "route_id": f"ER_{route_type}",
        "route_type": route_type,
        "stage_rank": stage_rank,
        "stage_gate_status": status,
        "priority_label": "priority_experiment",
        "priority_score": score,
        "within_stage_score": score,
        "is_route_group": False,
    }


if __name__ == "__main__":
    unittest.main()
