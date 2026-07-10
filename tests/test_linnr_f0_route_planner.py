from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from enh3bench.experiment_schema import empty_experiment_result_template
from enh3bench.experiment_planner import identify_actionable_gaps, propose_rule_based_routes
from enh3bench.experiment_result_importer import export_experiment_result_template
from enh3bench.experiment_route_card import route_to_markdown_card
from enh3bench.lab_profile import default_ustc_linnr_profile


class LiNRRF0RoutePlannerTests(unittest.TestCase):
    def test_baseline_repeatability_route_generated_for_linnr(self) -> None:
        routes = propose_rule_based_routes(
            [],
            _profile(),
            "run1",
            reaction_family="LiNRR",
            lab_demo_only=True,
            require_baseline_first=True,
        )
        self.assertEqual(routes[0]["route_type"], "baseline_repeatability")
        self.assertEqual(routes[0]["reaction_family"], "LiNRR")

    def test_baseline_route_includes_water_photos_and_resistance(self) -> None:
        route = _route("baseline_repeatability")
        self.assertIn("three water-content measurements", route["required_controls"])
        self.assertIn("water_content_before", route["required_measurements"])
        self.assertIn("water_content_mid", route["required_measurements"])
        self.assertIn("water_content_after", route["required_measurements"])
        self.assertIn("SSC/PtAuSSC before-after photos", route["required_controls"])
        self.assertIn("electrolyte_resistance_before", route["required_measurements"])
        self.assertIn("electrolyte_resistance_after", route["required_measurements"])

    def test_flow_wetting_route_includes_line_and_pump_status(self) -> None:
        route = _route("flow_wetting")
        self.assertIn("leak_status", route["required_measurements"])
        self.assertIn("back_suction_status", route["required_measurements"])
        self.assertIn("pump_status", route["required_measurements"])
        self.assertIn("gas-line blank", route["required_controls"])
        self.assertIn("liquid-line blank", route["required_controls"])

    def test_hor_route_requires_h2_and_hor_off_controls(self) -> None:
        route = _route("HOR_proton_economy")
        self.assertIn("H2-off control", route["required_controls"])
        self.assertIn("HOR-off control", route["required_controls"])
        self.assertIn("H2_observation", route["required_measurements"])

    def test_non_linnr_family_does_not_generate_default_wet_lab_route(self) -> None:
        gaps = identify_actionable_gaps([_claim("NO3RR", "Nitrate reduction reports FE 60%.")])
        routes = propose_rule_based_routes(
            gaps,
            _profile(),
            "run1",
            reaction_family="LiNRR",
            lab_demo_only=True,
            require_baseline_first=True,
        )
        self.assertEqual(routes, [])

    def test_route_card_contains_sop_and_minimum_report_sections(self) -> None:
        card = route_to_markdown_card(_route("baseline_repeatability"), 1)
        self.assertIn("SOP Anchor Points", card)
        self.assertIn("Minimum Report Fields", card)
        self.assertIn("Boundary Upgrade If Successful", card)
        self.assertIn("Required Raw Records To Save", card)

    def test_result_template_includes_new_sop_fields(self) -> None:
        route = _route("baseline_repeatability")
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = export_experiment_result_template([route], "run1", output_dir=Path(temp_dir))
            self.assertEqual(outputs["count"], 1)
        template = empty_experiment_result_template(route)
        for field in ("OCV", "pump_speed", "SSC_photo_before", "PtAuSSC_photo_after", "IC_NH4", "SOP_deviation", "operator_failure_note"):
            self.assertIn(field, template)


def _route(route_type: str) -> dict[str, object]:
    routes = propose_rule_based_routes(
        [_gap(route_type)],
        _profile(),
        "run1",
        reaction_family="LiNRR",
        lab_demo_only=True,
        require_baseline_first=False,
    )
    for route in routes:
        if route["route_type"] == route_type:
            return route
    raise AssertionError(f"missing route: {route_type}")


def _gap(route_type: str) -> dict[str, object]:
    return {
        "gap_type": route_type,
        "route_type_hint": route_type,
        "source_basis_id": "CR1",
        "paper_id": "P1",
        "source_span_id": "S1",
        "primary_evidence": True,
        "reaction_family": "LiNRR",
    }


def _claim(family: str, source_text: str) -> dict[str, object]:
    return {
        "claim_id": f"CR_{family}",
        "paper_id": "P1",
        "source_span_id": f"S_{family}",
        "evidence_id": f"E_{family}",
        "text_class": "primary_performance",
        "provenance_type": "body",
        "is_primary_admissible": True,
        "reaction_family": family,
        "source_text": source_text,
        "validation_gates": {"blank_control": "missing", "contamination_control": "missing", "nox_control": "missing", "isotope_15N": "missing"},
        "missing_boundary_fields": [],
        "detected_taxes": ["measurement_matrix_tax"],
    }


def _profile() -> dict[str, object]:
    return default_ustc_linnr_profile(profile_template="ustc-linnr-realistic")


if __name__ == "__main__":
    unittest.main()
