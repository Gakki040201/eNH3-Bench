from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from enh3bench.hidden_tax import detect_hidden_taxes
from enh3bench.human_audit import score_audit_priority
from enh3bench.llm_clients import MockLLMClient
from enh3bench.llm_clients.base import BaseLLMClient
from enh3bench.llm_verifier import compare_rule_and_llm, export_llm_verification_results, verify_record_with_llm


class LowTrustConstraintTests(unittest.TestCase):
    def test_low_trust_reference_llm_upgrade_is_capped_to_rule_boundary(self) -> None:
        comparison = compare_rule_and_llm(_record("reference"), _llm_response("cell_metric"))
        self.assertEqual(comparison["trusted_llm_maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertIn("trusted_boundary_capped_by_provenance", comparison["llm_audit_flags"])
        self.assertTrue(comparison["needs_human_review"])

    def test_low_trust_copyright_llm_upgrade_adds_override_flag(self) -> None:
        comparison = compare_rule_and_llm(_record("copyright_note"), _llm_response("cell_metric"))
        self.assertIn("llm_overrode_low_trust_provenance", comparison["llm_audit_flags"])
        self.assertTrue(comparison["low_trust_provenance"])

    def test_low_trust_invalid_llm_schema_still_needs_human_review(self) -> None:
        verified = verify_record_with_llm(_record("reference"), MockLLMClient(force_invalid_schema=True), model="mock")
        self.assertTrue(verified["needs_human_review"])
        self.assertTrue(verified["low_trust_provenance"])
        self.assertTrue(str(verified["llm_parse_error"]).startswith("schema_invalid:"))
        self.assertEqual(verified["trusted_llm_maximum_supported_boundary"], "unsupported_or_secondary")

    def test_body_provenance_llm_boundary_is_not_capped(self) -> None:
        comparison = compare_rule_and_llm(_record("body"), _llm_response("cell_metric"))
        self.assertEqual(comparison["trusted_llm_maximum_supported_boundary"], "cell_metric")
        self.assertNotIn("trusted_boundary_capped_by_provenance", comparison["llm_audit_flags"])
        self.assertFalse(comparison["low_trust_provenance"])

    def test_reference_hidden_tax_keywords_do_not_trigger_domain_tax_cascade(self) -> None:
        result = detect_hidden_taxes(
            {
                **_record("reference"),
                "source_text": "Reference title: electrolyte solvent flow GDE HOR H2 outlet capture FE 80%.",
            }
        )
        self.assertIn("measurement_matrix_tax", result["detected_taxes"])
        self.assertNotIn("solvent_management_tax", result["detected_taxes"])
        self.assertNotIn("resistance_or_renewal_tax", result["detected_taxes"])
        self.assertNotIn("wetting_outlet_capture_tax", result["detected_taxes"])
        self.assertNotIn("hydrogen_logistics_tax", result["detected_taxes"])
        self.assertIn("secondary_or_low_trust_text_cannot_establish_primary_boundary", result["hidden_assumptions"])
        self.assertIn("primary_body_text_required", result["missing_measurements"])

    def test_low_trust_contamination_text_can_trigger_contamination_tax(self) -> None:
        result = detect_hidden_taxes(
            {
                **_record("copyright_note"),
                "source_text": "Copyright note includes background ammonia contamination, nitrate and nitrite impurity terms.",
            }
        )
        self.assertIn("contamination_tax", result["detected_taxes"])
        self.assertNotIn("solvent_management_tax", result["detected_taxes"])

    def test_primary_body_flow_hor_still_triggers_wetting_and_hydrogen_taxes(self) -> None:
        result = detect_hidden_taxes(
            {
                **_record("body"),
                "text_class": "primary_performance",
                "is_primary_admissible": True,
                "source_text": "Primary results report a flow GDE cell with outlet capture, HOR, H2 feed, and FE 30%.",
            }
        )
        self.assertIn("wetting_outlet_capture_tax", result["detected_taxes"])
        self.assertIn("hydrogen_logistics_tax", result["detected_taxes"])

    def test_audit_priority_increases_for_low_trust_llm_override(self) -> None:
        base = _audit_record()
        flagged = dict(
            base,
            provenance_type="reference",
            low_trust_provenance=True,
            llm_maximum_supported_boundary="cell_metric",
            llm_audit_flags=["llm_overrode_low_trust_provenance", "trusted_boundary_capped_by_provenance"],
        )
        self.assertGreater(score_audit_priority(flagged)["audit_priority_score"], score_audit_priority(base)["audit_priority_score"])

    def test_trusted_llm_boundary_appears_in_verification_csv(self) -> None:
        verified = verify_record_with_llm(_record("reference"), _FixedLLMClient(_llm_response("cell_metric")), model="fixed")
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = export_llm_verification_results([verified], [], "low_trust_csv", "fixed", output_dir=Path(temp_dir))
            csv_text = Path(outputs["csv"]).read_text(encoding="utf-8")
        header = csv_text.splitlines()[0]
        self.assertIn("trusted_llm_maximum_supported_boundary", header)
        self.assertIn("unsupported_or_secondary", csv_text)


class _FixedLLMClient(BaseLLMClient):
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0,
        max_tokens: int = 1200,
        response_format: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> str:
        return json.dumps(self.response, ensure_ascii=True, sort_keys=True)


def _record(provenance_type: str) -> dict[str, Any]:
    return {
        "claim_id": "CR1",
        "paper_id": "P1",
        "source_span_id": "S1",
        "evidence_id": "E1",
        "text_class": "primary_performance",
        "provenance_type": provenance_type,
        "maximum_supported_boundary": "unsupported_or_secondary",
        "missing_boundary_fields": [],
        "required_controls": [],
        "source_text": "Source text reports FE for NH3 without enough admissible primary support.",
    }


def _audit_record() -> dict[str, Any]:
    return {
        **_record("body"),
        "maximum_supported_boundary": "unsupported_or_secondary",
        "admissibility_status": "reject",
        "llm_maximum_supported_boundary": "unsupported_or_secondary",
        "llm_audit_flags": [],
    }


def _llm_response(boundary: str) -> dict[str, Any]:
    response = {
        "text_class": "primary_performance",
        "field_support": {
            "FE": "explicit",
            "NH3_yield": "missing",
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
        "recommended_experiment": "Verify in primary body text before use.",
        "reasoning": "The LLM claims support, but provenance constraints are audited separately.",
    }
    return copy.deepcopy(response)


if __name__ == "__main__":
    unittest.main()
