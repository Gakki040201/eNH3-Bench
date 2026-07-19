from __future__ import annotations

import unittest

from enh3bench.calibration_schema import (
    ALLOWED_HUMAN_LABELS,
    CALIBRATION_PROFILE,
    CALIBRATION_SCHEMA_VERSION,
    blank_human_fields,
    make_document_item_id,
    make_link_item_id,
    make_paper_item_id,
    make_span_item_id,
    validate_review_row,
)


class CalibrationSchemaV016Tests(unittest.TestCase):
    def test_schema_and_profile_are_versioned(self) -> None:
        self.assertEqual(CALIBRATION_SCHEMA_VERSION, "0.16-calibration.1")
        self.assertEqual(CALIBRATION_PROFILE, "human_semantic_calibration_round1_v1")

    def test_stable_ids_have_required_prefixes(self) -> None:
        self.assertTrue(make_span_item_id("CR15_X").startswith("CC16S_"))
        self.assertTrue(make_paper_item_id("P1").startswith("CC16P_"))
        self.assertTrue(make_document_item_id("D1").startswith("CC16D_"))
        self.assertTrue(make_link_item_id("CRL15_X").startswith("CC16L_"))

    def test_stable_ids_are_repeatable_and_run_name_independent(self) -> None:
        self.assertEqual(make_span_item_id("CR15_X"), make_span_item_id("CR15_X"))
        self.assertNotEqual(make_span_item_id("CR15_X"), make_span_item_id("CR15_Y"))

    def test_blank_human_fields_are_all_empty(self) -> None:
        for item_type in ("span", "paper", "document", "link"):
            self.assertTrue(blank_human_fields(item_type))
            self.assertEqual({""}, set(blank_human_fields(item_type).values()))

    def test_allowed_labels_are_exact(self) -> None:
        self.assertEqual(ALLOWED_HUMAN_LABELS, {"yes", "no", "uncertain", "not_applicable"})

    def test_invalid_human_label_is_rejected(self) -> None:
        row = blank_human_fields("span")
        row["human_claim_type_correct"] = "pass"
        self.assertTrue(any("invalid_human_label" in error for error in validate_review_row("span", row)))

    def test_no_or_uncertain_requires_notes(self) -> None:
        row = blank_human_fields("span")
        row["human_claim_type_correct"] = "no"
        self.assertIn("no_or_uncertain_requires_notes:human_notes", validate_review_row("span", row))
        row["human_notes"] = "Correction required."
        self.assertNotIn("no_or_uncertain_requires_notes:human_notes", validate_review_row("span", row))


if __name__ == "__main__":
    unittest.main()
