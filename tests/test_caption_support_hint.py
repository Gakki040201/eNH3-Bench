from __future__ import annotations

import copy
import unittest
from typing import Any

from enh3bench.benchmark_builder import build_claim_rights_task
from enh3bench.claim_rights import classify_claim_rights
from enh3bench.hidden_tax import detect_hidden_taxes
from enh3bench.llm_verifier import compare_rule_and_llm


class CaptionSupportHintTests(unittest.TestCase):
    def test_figure_caption_metric_terms_are_support_hint_not_boundary(self) -> None:
        result = classify_claim_rights(_caption_record("Fig. 1. FE and NH3 yield at different voltages."))
        self.assertEqual(result["maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertEqual(result["admissibility_status"], "context_only_caption")
        self.assertEqual(result["support_hint_boundary"], "cell_metric")

    def test_figure_caption_validation_terms_hint_product_admissibility(self) -> None:
        result = classify_claim_rights(_caption_record("Fig. 2. 15N isotope validation and blank controls."))
        self.assertEqual(result["maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertEqual(result["support_hint_boundary"], "product_admissibility")

    def test_figure_caption_reactor_terms_hint_reactor_legibility(self) -> None:
        result = classify_claim_rights(_caption_record("Fig. 3. Flow GDE reactor with HOR outlet runtime stability."))
        self.assertEqual(result["maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertEqual(result["support_hint_boundary"], "reactor_legibility")

    def test_scheme_caption_process_terms_hint_process_partial(self) -> None:
        result = classify_claim_rights(
            _caption_record("Scheme 1. Capture route, solvent inventory, recycle, H2 source, auxiliary load and TEA.", provenance_type="scheme_caption")
        )
        self.assertEqual(result["maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertEqual(result["support_hint_boundary"], "process_partial")

    def test_caption_requires_primary_body_text_pairing(self) -> None:
        result = classify_claim_rights(_caption_record("Fig. 4. FE and NH3 yield."))
        self.assertIn("primary body text pairing", result["required_controls"])
        self.assertTrue(result["paired_body_required"])
        self.assertTrue(result["caption_context_only"])

    def test_caption_overclaim_flags_include_not_primary_evidence(self) -> None:
        result = classify_claim_rights(_caption_record("Fig. 5. FE and NH3 yield."))
        self.assertIn("caption_not_primary_evidence", result["overclaim_risk_flags"])
        self.assertIn("pair_with_primary_body_text_required", result["overclaim_risk_flags"])

    def test_llm_upgrading_unpaired_caption_is_capped(self) -> None:
        comparison = compare_rule_and_llm(
            {
                "text_class": "primary_performance",
                "provenance_type": "figure_caption",
                "maximum_supported_boundary": "unsupported_or_secondary",
                "missing_boundary_fields": [],
                "required_controls": ["primary body text pairing"],
                "source_text": "Fig. 6. FE and NH3 yield.",
            },
            _llm_response("cell_metric"),
        )
        self.assertTrue(comparison["needs_human_review"])
        self.assertIn("llm_upgraded_unpaired_caption", comparison["llm_audit_flags"])
        self.assertEqual(comparison["trusted_llm_maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertEqual(comparison["trusted_llm_boundary_reason"], "Unpaired caption cannot establish primary boundary.")

    def test_primary_body_performance_record_is_unaffected(self) -> None:
        result = classify_claim_rights(
            {
                "text_class": "primary_performance",
                "provenance_type": "body",
                "source_text": "Results report 30% FE and NH3 yield at 2.5 V.",
                "faradaic_efficiency_percent": 30.0,
                "nh3_yield_value": 1.2,
                "potential_value": 2.5,
            }
        )
        self.assertEqual(result["maximum_supported_boundary"], "cell_metric")
        self.assertFalse(result["caption_context_only"])

    def test_benchmark_common_fields_preserve_caption_support_hint(self) -> None:
        row = build_claim_rights_task(
            [
                {
                    **_reviewed_record(),
                    "provenance_type": "figure_caption",
                    "maximum_supported_boundary": "unsupported_or_secondary",
                    "support_hint_boundary": "cell_metric",
                    "paired_body_required": True,
                    "caption_context_only": True,
                }
            ]
        )[0]
        self.assertEqual(row["support_hint_boundary"], "cell_metric")
        self.assertTrue(row["paired_body_required"])
        self.assertTrue(row["caption_context_only"])

    def test_caption_hidden_tax_does_not_trigger_domain_cascade(self) -> None:
        result = detect_hidden_taxes(
            _caption_record("Fig. 7. Flow GDE HOR electrolyte solvent capture outlet FE 70%.")
        )
        self.assertIn("measurement_matrix_tax", result["detected_taxes"])
        self.assertNotIn("solvent_management_tax", result["detected_taxes"])
        self.assertNotIn("wetting_outlet_capture_tax", result["detected_taxes"])
        self.assertNotIn("hydrogen_logistics_tax", result["detected_taxes"])
        self.assertIn("caption_requires_primary_body_pairing", result["hidden_assumptions"])


def _caption_record(text: str, provenance_type: str = "figure_caption") -> dict[str, Any]:
    return {
        "paper_id": "P1",
        "source_span_id": "S1",
        "evidence_id": "E1",
        "text_class": "primary_performance",
        "provenance_type": provenance_type,
        "source_text": text,
    }


def _reviewed_record() -> dict[str, Any]:
    return {
        "audit_id": "AUD1",
        "run_name": "run1",
        "paper_id": "P1",
        "source_span_id": "S1",
        "evidence_id": "E1",
        "source_text": "Fig. 1. FE and NH3 yield.",
        "source_section": "figure_caption",
        "provenance_confidence": "high",
        "text_class": "figure_caption",
        "admissibility_status": "context_only_caption",
        "human_reviewer_id": "reviewer1",
        "human_review_status": "reviewed",
        "human_text_class": "figure_caption",
        "human_maximum_supported_boundary": "unsupported_or_secondary",
        "human_admissibility_status": "context_only_caption",
        "human_required_controls": "primary body text pairing",
        "human_hidden_tax": "",
        "human_experiment_decision": "insufficient_evidence",
        "human_validation_isotope_15N": "unclear",
        "human_validation_blank_control": "unclear",
        "human_validation_NOx_control": "unclear",
        "human_validation_contamination_control": "unclear",
        "human_validation_quantification_method": "unclear",
        "human_notes": "reviewed",
    }


def _llm_response(boundary: str) -> dict[str, Any]:
    response = {
        "text_class": "primary_performance",
        "field_support": {
            "FE": "explicit",
            "NH3_yield": "explicit",
            "EE": "missing",
            "current_density": "missing",
            "potential_or_voltage": "missing",
            "runtime": "missing",
            "isotope_15N": "missing",
            "blank_control": "missing",
            "NOx_control": "missing",
            "reactor_type": "missing",
            "HOR": "missing",
            "product_state": "missing",
            "capture_route": "missing",
            "solvent_inventory": "missing",
            "failure_mode": "missing",
        },
        "maximum_supported_boundary": boundary,
        "missing_boundary_fields": [],
        "hidden_tax": [],
        "required_controls": [],
        "overclaim_risk": [],
        "recommended_experiment": "Pair caption with body text.",
        "reasoning": "The caption contains metric terms.",
    }
    return copy.deepcopy(response)


if __name__ == "__main__":
    unittest.main()
