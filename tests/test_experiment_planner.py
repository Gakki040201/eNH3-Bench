from __future__ import annotations

import unittest

from enh3bench.experiment_planner import identify_actionable_gaps, propose_rule_based_routes
from enh3bench.lab_profile import default_ustc_linnr_profile


class ExperimentPlannerTests(unittest.TestCase):
    def test_validation_gap_records_generate_validation_route(self) -> None:
        gaps = identify_actionable_gaps([_record(validation_gates={"isotope_15N": "missing", "blank_control": "missing"})])
        routes = propose_rule_based_routes(gaps, _capable_profile(), "run1")
        self.assertIn("validation_gap_closure", {route["route_type"] for route in routes})

    def test_solvent_management_tax_generates_electrolyte_window(self) -> None:
        routes = propose_rule_based_routes([_gap("solvent_management_tax", "electrolyte_window", hidden_tax="solvent_management_tax")], _capable_profile(), "run1")
        parent = next(route for route in routes if route["route_type"] == "electrolyte_window")
        self.assertTrue(parent["is_route_group"])

    def test_wetting_tax_generates_flow_route(self) -> None:
        routes = propose_rule_based_routes([_gap("wetting_outlet_capture_tax", "flow_wetting", hidden_tax="wetting_outlet_capture_tax")], _capable_profile(), "run1")
        self.assertEqual(routes[0]["route_type"], "flow_wetting")

    def test_hydrogen_tax_generates_hor_route(self) -> None:
        routes = propose_rule_based_routes([_gap("hydrogen_logistics_tax", "HOR_proton_economy", hidden_tax="hydrogen_logistics_tax")], _capable_profile(), "run1")
        self.assertEqual(routes[0]["route_type"], "HOR_proton_economy")

    def test_priority_decreases_when_critical_capability_unavailable(self) -> None:
        capable = propose_rule_based_routes([_gap("missing isotope_15N", "validation_gap_closure")], _capable_profile(), "run1")[0]
        limited = propose_rule_based_routes([_gap("missing isotope_15N", "validation_gap_closure")], default_ustc_linnr_profile(), "run1")[0]
        self.assertLess(limited["priority_score"], capable["priority_score"])
        self.assertEqual(limited["priority_label"], "defer_until_capability_available")

    def test_hidden_tax_frequency_increases_priority(self) -> None:
        one = propose_rule_based_routes([_gap("solvent_management_tax", "electrolyte_window", hidden_tax="solvent_management_tax")], _capable_profile(), "run1")[0]
        many = propose_rule_based_routes(
            [_gap(f"solvent_management_tax_{i}", "electrolyte_window", hidden_tax="solvent_management_tax") for i in range(4)],
            _capable_profile(),
            "run1",
        )[0]
        self.assertGreater(many["priority_score"], one["priority_score"])

    def test_llm_disagreement_increases_review_priority(self) -> None:
        route = propose_rule_based_routes([dict(_gap("LLM more permissive", "validation_gap_closure"), llm_disagreement=True)], _capable_profile(), "run1")[0]
        self.assertEqual(route["priority_label"], "needs_human_review")
        self.assertTrue(route["human_review_required"])


def _record(**overrides: object) -> dict[str, object]:
    record = {
        "claim_id": "CR1",
        "paper_id": "P1",
        "source_span_id": "S1",
        "evidence_id": "E1",
        "is_primary_admissible": True,
        "provenance_type": "body",
        "validation_gates": {"isotope_15N": "yes", "blank_control": "yes", "nox_control": "yes", "contamination_control": "yes"},
        "missing_boundary_fields": [],
        "detected_taxes": [],
    }
    record.update(overrides)
    return record


def _gap(name: str, route_type: str, hidden_tax: str = "") -> dict[str, object]:
    return {
        "gap_type": name,
        "route_type_hint": route_type,
        "hidden_tax": hidden_tax,
        "source_basis_id": "CR1",
        "paper_id": "P1",
        "source_span_id": "S1",
        "primary_evidence": True,
    }


def _capable_profile() -> dict[str, object]:
    profile = default_ustc_linnr_profile()
    profile["reactor_capabilities"].update({"can_do_flow_cell": True, "can_do_HOR_coupling": True})
    profile["electrochemistry"].update({"potentiostat_available": True, "can_record_full_cell_voltage": True, "can_record_anode_cathode_potential": True, "EIS_available": True})
    profile["gases"].update({"Ar_available": True, "H2_available": True, "isotopic_15N2_available": True})
    profile["analytics"].update(
        {
            "liquid_nitrate_nitrite_IC_available": True,
            "gas_phase_NOx_quantification_available": True,
            "feed_gas_impurity_testing_available": True,
            "gas_phase_NH3_capture_available": True,
            "liquid_NH4_quantification_available": True,
            "H2_quantification_available": True,
            "water_content_quantification_available": True,
            "image_recording_available": True,
            "electrical_resistance_measurement_available": True,
            "product_state_accounting_available": True,
        }
    )
    profile["controls"].update({"can_do_Ar_blank": True, "can_do_N2_free_blank": True, "can_do_15N_control": True, "can_do_NOx_screening": True, "can_do_background_NH3_control": True, "can_do_H2_off_control": True, "can_do_HOR_off_control": True, "can_do_electrolyte_blank": True})
    profile["electrolyte_chemistry"].update({"can_measure_water_content": True, "Karl_Fischer_available": True})
    profile["sop_capabilities"].update({"Karl_Fischer_SOP": True})
    return profile


if __name__ == "__main__":
    unittest.main()
