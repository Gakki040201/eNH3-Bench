from __future__ import annotations

import unittest

from enh3bench.experiment_schema import (
    empty_experiment_result_template,
    normalize_control_list,
    normalize_measurement_list,
    normalize_route_label,
    validate_experiment_route,
    utc_now,
)


class ExperimentSchemaTests(unittest.TestCase):
    def test_normalizers(self) -> None:
        self.assertEqual(normalize_route_label("HOR"), "HOR_proton_economy")
        self.assertEqual(normalize_measurement_list("FE, NH3_yield, bad"), ["FE", "NH3_yield"])
        self.assertEqual(normalize_control_list('["Ar blank","bad"]'), ["Ar blank"])

    def test_route_validation_and_result_template(self) -> None:
        route = _route()
        valid, errors = validate_experiment_route(route)
        self.assertTrue(valid, errors)
        template = empty_experiment_result_template(route)
        self.assertEqual(template["route_id"], "ER1")
        self.assertIn("Ar blank", template["required_controls"])


def _route() -> dict[str, object]:
    return {
        "route_id": "ER1",
        "run_name": "run1",
        "source_basis_ids": [],
        "linked_paper_ids": [],
        "linked_source_span_ids": [],
        "reaction_family": "LiNRR",
        "reaction_profile": {"reaction_family": "LiNRR"},
        "lab_demonstration_allowed": True,
        "route_type": "validation_gap_closure",
        "priority_label": "priority_experiment",
        "priority_score": 60,
        "hypothesis": "test",
        "literature_rationale": "because",
        "boundary_gap_targeted": [],
        "hidden_tax_targeted": [],
        "variable_type": "control_experiment",
        "experimental_matrix": [],
        "fixed_conditions": {},
        "required_controls": ["Ar blank"],
        "feasible_controls": ["Ar blank"],
        "infeasible_controls": [],
        "required_measurements": ["FE", "NH3_yield"],
        "success_criteria": [],
        "failure_criteria": [],
        "stopping_rules": [],
        "expected_outcomes": [],
        "failure_diagnosis_tree": [],
        "SOP_anchor_points": [],
        "minimum_report_fields": [],
        "boundary_upgrade_if_successful": [],
        "boundary_not_closed_even_if_successful": [],
        "required_raw_records_to_save": [],
        "lab_capability_warnings": [],
        "safety_notes": [],
        "estimated_difficulty": "low",
        "estimated_cost_level": "low",
        "estimated_time_level": "short",
        "human_review_required": False,
        "llm_used": False,
        "llm_model": "",
        "llm_rationale": "",
        "created_at_utc": utc_now(),
    }


if __name__ == "__main__":
    unittest.main()
