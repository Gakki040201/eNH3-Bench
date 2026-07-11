from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.experiment_route_card import export_public_route_summary, export_route_cards, route_to_markdown_card


class ExperimentRouteCardTests(unittest.TestCase):
    def test_route_card_contains_required_sections(self) -> None:
        text = route_to_markdown_card(_route(), 1)
        self.assertIn("Hypothesis", text)
        self.assertIn("Required Controls", text)
        self.assertIn("Required Measurements", text)
        self.assertIn("Success Criteria", text)
        self.assertIn("Failure Criteria", text)
        self.assertIn("Measurement feasibility: feasible", text)
        self.assertIn("Alternative measurement plan", text)

    def test_export_route_cards_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cards = export_route_cards([_route()], "run1", output_dir=Path(temp_dir) / "routes")
            summary = export_public_route_summary([_route()], "run1", output_dir=Path(temp_dir) / "reports")
            self.assertTrue(Path(cards).exists())
            self.assertTrue(Path(summary).exists())
            self.assertIn("Feasible measurements", Path(summary).read_text(encoding="utf-8"))


def _route() -> dict[str, object]:
    return {
        "route_id": "ER1",
        "route_type": "validation_gap_closure",
        "priority_label": "priority_experiment",
        "priority_score": 70,
        "hypothesis": "close validation gap",
        "literature_rationale": "BoundaryLedger found missing controls.",
        "boundary_gap_targeted": ["missing isotope_15N"],
        "hidden_tax_targeted": ["measurement_matrix_tax"],
        "feasible_controls": ["Ar blank"],
        "infeasible_controls": [],
        "lab_capability_warnings": [],
        "experimental_matrix": [{"condition_id": "baseline"}],
        "required_controls": ["Ar blank"],
        "required_measurements": ["FE", "NH3_yield"],
        "mandatory_measurements": ["FE", "NH3_yield"],
        "optional_measurements": [],
        "feasible_measurements": ["FE", "NH3_yield"],
        "infeasible_measurements": [],
        "measurement_capability_warnings": [],
        "measurement_feasibility_status": "feasible",
        "alternative_measurement_plan": [],
        "boundary_not_closed_due_to_unavailable_measurements": [],
        "success_criteria": ["controls pass"],
        "failure_criteria": ["controls fail"],
        "failure_diagnosis_tree": ["check blanks"],
        "human_review_required": False,
        "llm_used": False,
    }


if __name__ == "__main__":
    unittest.main()
