from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.claim_rights import classify_claim_rights, export_claim_rights_ledger


class ClaimRightsTests(unittest.TestCase):
    def test_reference_list_is_rejected(self) -> None:
        result = classify_claim_rights({"text_class": "reference_list", "source_text": "1. Example citation. doi:10.1/x"})
        self.assertEqual(result["claim_type"], "unsupported_claim")
        self.assertEqual(result["maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertEqual(result["admissibility_status"], "reject")

    def test_review_table_is_secondary_only(self) -> None:
        result = classify_claim_rights({"text_class": "review_table", "source_text": "Review table of previous FE reports."})
        self.assertEqual(result["claim_type"], "secondary_summary_claim")
        self.assertEqual(result["admissibility_status"], "secondary_only")
        self.assertEqual(result["maximum_supported_boundary"], "unsupported_or_secondary")

    def test_protocol_guideline_is_protocol_only(self) -> None:
        result = classify_claim_rights(
            {
                "text_class": "protocol_guideline",
                "source_text": "Protocol requires 15N2 isotope validation, blank controls, NOx screening, and NMR quantification.",
            }
        )
        self.assertEqual(result["claim_type"], "protocol_claim")
        self.assertEqual(result["maximum_supported_boundary"], "product_admissibility")
        self.assertEqual(result["admissibility_status"], "protocol_only")

    def test_primary_performance_fe_only_is_metric_incomplete(self) -> None:
        result = classify_claim_rights(
            {
                "text_class": "primary_performance",
                "source_text": "N2 reduction reported 90% FE for ammonia.",
                "reaction_family": "eNRR",
                "nitrogen_source": "N2",
                "faradaic_efficiency_percent": 90.0,
            }
        )
        self.assertEqual(result["maximum_supported_boundary"], "cell_metric")
        self.assertEqual(result["admissibility_status"], "metric_only_or_validation_incomplete")
        self.assertIn("fe_without_complete_measurement_matrix", result["overclaim_risk_flags"])

    def test_n2_to_nh3_without_15n_cannot_exceed_cell_metric(self) -> None:
        result = classify_claim_rights(
            {
                "text_class": "primary_performance",
                "source_text": "N2-to-NH3 electrolysis gave FE, NH3 yield, current density, and voltage with blank and NOx controls.",
                "reaction_family": "eNRR",
                "nitrogen_source": "N2",
                "faradaic_efficiency_percent": 42.0,
                "nh3_yield_value": 1.2,
                "current_density_mA_cm2": 20.0,
                "potential_value": -0.2,
                "blank_control": "yes",
                "nox_screening": "yes",
                "contamination_control": "yes",
            }
        )
        self.assertEqual(result["maximum_supported_boundary"], "cell_metric")
        self.assertIn("n2_claim_without_15n", result["overclaim_risk_flags"])
        self.assertIn("15N2 isotope validation", result["required_controls"])

    def test_flow_hor_validated_record_maps_to_reactor_legibility(self) -> None:
        result = classify_claim_rights(
            {
                "text_class": "primary_performance_with_validation",
                "source_text": (
                    "15N2 flow cell with hydrogen oxidation reported gas-phase ammonia at the outlet, "
                    "no flooding, stable runtime, FE, NH3 yield, current density, and voltage."
                ),
                "reaction_family": "eNRR",
                "nitrogen_source": "15N2",
                "faradaic_efficiency_percent": 55.0,
                "nh3_yield_value": 2.1,
                "current_density_mA_cm2": 100.0,
                "potential_value": 2.2,
                "isotope_validation": "yes",
                "blank_control": "yes",
                "nox_screening": "yes",
                "contamination_control": "yes",
                "detection_method": "NMR",
                "reactor_type": "flow cell",
                "flow_rate": "10 mL min-1",
                "HOR_or_anode_reaction": "HOR",
                "runtime": "10 h",
                "outlet_product_state": "gas-phase NH3",
                "wetting_or_failure_disclosure": "no flooding",
                "hydrogen_source_boundary": "bottled H2 stated",
            }
        )
        self.assertEqual(result["maximum_supported_boundary"], "reactor_legibility")
        self.assertEqual(result["admissibility_status"], "reactor_legible")

    def test_process_partial_requires_core_process_fields(self) -> None:
        base = {
            "text_class": "primary_performance_with_validation",
            "source_text": "15N2 validated cell with blank and NOx controls reports FE, NH3 yield, voltage, and current.",
            "reaction_family": "eNRR",
            "nitrogen_source": "15N2",
            "faradaic_efficiency_percent": 61.0,
            "nh3_yield_value": 3.4,
            "current_density_mA_cm2": 120.0,
            "potential_value": 2.4,
            "isotope_validation": "yes",
            "blank_control": "yes",
            "nox_screening": "yes",
            "contamination_control": "yes",
            "detection_method": "NMR",
            "gas_liquid_product_split": "reported",
            "capture_route": "acid trap",
            "solvent_inventory": "electrolyte volume stated",
            "hydrogen_source_boundary": "H2 supply stated",
            "voltage_basis": "cell voltage",
        }
        full = classify_claim_rights(base)
        self.assertEqual(full["maximum_supported_boundary"], "process_partial")

        missing_capture = dict(base)
        missing_capture.pop("capture_route")
        result = classify_claim_rights(missing_capture)
        self.assertNotEqual(result["maximum_supported_boundary"], "process_partial")
        self.assertIn("capture_route", result["missing_boundary_fields"])

    def test_export_claim_rights_ledger_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = export_claim_rights_ledger(
                [{"text_class": "review_table", "paper_id": "P001", "source_text": "review table"}],
                "run1",
                Path(temp_dir),
            )
            self.assertTrue(Path(outputs["jsonl"]).exists())
            self.assertTrue(Path(outputs["csv"]).exists())


if __name__ == "__main__":
    unittest.main()
