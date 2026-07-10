from __future__ import annotations

import unittest

from enh3bench.claim_rights import classify_claim_rights
from enh3bench.evidence_bundle import build_evidence_bundle
from enh3bench.experiment_planner import identify_actionable_gaps, propose_rule_based_routes
from enh3bench.hidden_tax import detect_hidden_taxes
from enh3bench.lab_profile import default_ustc_linnr_profile


class ReactionProfileIntegrationTests(unittest.TestCase):
    def test_evidence_bundle_normalizes_or_infers_reaction_family(self) -> None:
        bundle = build_evidence_bundle(
            {
                "paper_id": "P1",
                "span_id": "S1",
                "source_text": "Lithium-mediated N2 reduction in THF used a Li salt.",
            }
        )
        self.assertEqual(bundle["reaction_family"], "LiNRR")
        self.assertEqual(bundle["extracted_fields"]["reaction_family"], "LiNRR")

    def test_enrr_n2_claim_requires_15n2_validation(self) -> None:
        result = classify_claim_rights(
            {
                "text_class": "primary_performance",
                "provenance_type": "body",
                "reaction_family": "eNRR",
                "nitrogen_source": "N2",
                "source_text": "N2-to-NH3 electrolysis reported FE, NH3 yield, current density, and voltage.",
                "faradaic_efficiency_percent": 30.0,
                "nh3_yield_value": 1.0,
                "current_density_mA_cm2": 20.0,
                "potential_value": -0.2,
            }
        )
        self.assertIn("15N2 isotope validation", result["required_controls"])
        self.assertIn("n2_claim_without_15n", result["overclaim_risk_flags"])

    def test_no3rr_requires_source_accounting_not_15n2_by_default(self) -> None:
        result = classify_claim_rights(
            {
                "text_class": "primary_performance",
                "provenance_type": "body",
                "reaction_family": "NO3RR",
                "nitrogen_source": "nitrate",
                "source_text": "Nitrate reduction to ammonia reported FE, NH3 yield, current density, and voltage.",
                "faradaic_efficiency_percent": 30.0,
                "nh3_yield_value": 1.0,
                "current_density_mA_cm2": 20.0,
                "potential_value": -0.2,
            }
        )
        self.assertNotIn("15N2 isotope validation", result["required_controls"])
        self.assertIn("nitrate/nitrite source accounting", result["required_controls"])
        self.assertIn("nitrogen mass balance", result["required_controls"])
        self.assertIn("nitrogen_balance", result["missing_boundary_fields"])

    def test_linnr_hidden_tax_profile_allows_li_specific_taxes(self) -> None:
        result = detect_hidden_taxes(
            {
                "text_class": "primary_performance",
                "provenance_type": "body",
                "reaction_family": "LiNRR",
                "source_text": "Li salt in THF electrolyte formed SEI resistance in a flow GDE with HOR H2 feed and FE 60%.",
                "faradaic_efficiency_percent": 60.0,
            }
        )
        self.assertIn("solvent_management_tax", result["detected_taxes"])
        self.assertIn("resistance_or_renewal_tax", result["detected_taxes"])
        self.assertIn("wetting_outlet_capture_tax", result["detected_taxes"])
        self.assertIn("hydrogen_logistics_tax", result["detected_taxes"])

    def test_no3rr_hidden_tax_profile_blocks_li_specific_taxes(self) -> None:
        result = detect_hidden_taxes(
            {
                "text_class": "primary_performance",
                "provenance_type": "body",
                "reaction_family": "NO3RR",
                "source_text": "Nitrate reduction used electrolyte solvent, SEI resistance, GDE flow, HOR H2 feed, and FE 60%.",
                "faradaic_efficiency_percent": 60.0,
            }
        )
        self.assertIn("measurement_matrix_tax", result["detected_taxes"])
        self.assertNotIn("solvent_management_tax", result["detected_taxes"])
        self.assertNotIn("resistance_or_renewal_tax", result["detected_taxes"])
        self.assertNotIn("wetting_outlet_capture_tax", result["detected_taxes"])
        self.assertNotIn("hydrogen_logistics_tax", result["detected_taxes"])

    def test_experiment_planner_defaults_to_linnr_lab_demo_routes(self) -> None:
        records = [_claim("LiNRR", "N2-to-NH3 Li salt THF electrolyte reports FE 60%."), _claim("NO3RR", "Nitrate reduction reports FE 60%.")]
        gaps = identify_actionable_gaps(records)
        routes = propose_rule_based_routes(gaps, default_ustc_linnr_profile(), "run1", reaction_family="LiNRR", lab_demo_only=True)
        self.assertTrue(routes)
        self.assertEqual({route["reaction_family"] for route in routes}, {"LiNRR"})
        self.assertTrue(all(route["lab_demonstration_allowed"] for route in routes))

    def test_non_linnr_record_is_not_default_wet_lab_route(self) -> None:
        gaps = identify_actionable_gaps([_claim("NO3RR", "Nitrate reduction reports FE 60%.")])
        default_routes = propose_rule_based_routes(gaps, default_ustc_linnr_profile(), "run1", reaction_family="LiNRR", lab_demo_only=True)
        self.assertEqual(default_routes, [])
        audit_routes = propose_rule_based_routes(
            gaps,
            default_ustc_linnr_profile(),
            "run1",
            include_families=["NO3RR"],
            lab_demo_only=False,
        )
        self.assertTrue(audit_routes)
        self.assertFalse(audit_routes[0]["lab_demonstration_allowed"])


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


if __name__ == "__main__":
    unittest.main()
