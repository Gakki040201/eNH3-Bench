from __future__ import annotations

import unittest

from enh3bench.hidden_tax import detect_hidden_taxes, is_secondary_context_provenance


class ReviewTableHiddenTaxConstraintTests(unittest.TestCase):
    def test_review_table_process_keywords_do_not_trigger_domain_tax_cascade(self) -> None:
        result = detect_hidden_taxes(
            _record(
                "review_table",
                "Review table summarizes electrolyte solvent, HOR, H2 feed, GDE outlet capture, and SEI resistance.",
            )
        )
        self.assertNotIn("solvent_management_tax", result["detected_taxes"])
        self.assertNotIn("resistance_or_renewal_tax", result["detected_taxes"])
        self.assertNotIn("wetting_outlet_capture_tax", result["detected_taxes"])
        self.assertNotIn("hydrogen_logistics_tax", result["detected_taxes"])
        self.assertIn("secondary_summary_cannot_establish_primary_hidden_tax", result["hidden_assumptions"])
        self.assertIn("primary_body_text_pairing_required_for_domain_tax", result["hidden_assumptions"])

    def test_review_table_fe_triggers_only_measurement_matrix_tax(self) -> None:
        result = detect_hidden_taxes(_record("review_table", "Review table row reports FE 70% for NH3."))
        self.assertEqual(result["detected_taxes"], ["measurement_matrix_tax"])
        self.assertEqual(result["severity"], "medium")

    def test_review_table_contamination_terms_trigger_contamination_tax(self) -> None:
        result = detect_hidden_taxes(_record("review_table", "Review table note flags NOx contamination, nitrate, and nitrite."))
        self.assertIn("contamination_tax", result["detected_taxes"])
        self.assertNotIn("solvent_management_tax", result["detected_taxes"])
        self.assertEqual(result["severity"], "high")

    def test_primary_body_same_keywords_still_trigger_domain_taxes(self) -> None:
        result = detect_hidden_taxes(
            _record(
                "body",
                "Primary results report electrolyte solvent, HOR, H2 feed, flow GDE outlet capture, and SEI resistance.",
            )
        )
        self.assertIn("solvent_management_tax", result["detected_taxes"])
        self.assertIn("resistance_or_renewal_tax", result["detected_taxes"])
        self.assertIn("wetting_outlet_capture_tax", result["detected_taxes"])
        self.assertIn("hydrogen_logistics_tax", result["detected_taxes"])

    def test_table_and_review_table_require_primary_body_pairing(self) -> None:
        for provenance_type in ("table", "review_table"):
            with self.subTest(provenance_type=provenance_type):
                result = detect_hidden_taxes(_record(provenance_type, "Table context reports FE 60%."))
                self.assertIn("primary_body_text_pairing_required", result["missing_measurements"])
                self.assertIn("pair context/table/caption evidence with primary body text", result["required_controls"])

    def test_secondary_context_helper_includes_captions_and_secondary_review(self) -> None:
        for provenance_type in ("review_table", "table", "secondary_review", "figure_caption", "scheme_caption"):
            with self.subTest(provenance_type=provenance_type):
                self.assertTrue(is_secondary_context_provenance(provenance_type))


def _record(provenance_type: str, source_text: str) -> dict[str, object]:
    return {
        "paper_id": "P1",
        "source_span_id": "S1",
        "evidence_id": "E1",
        "text_class": "primary_performance",
        "provenance_type": provenance_type,
        "source_text": source_text,
    }


if __name__ == "__main__":
    unittest.main()
