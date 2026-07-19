from __future__ import annotations

import unittest

from enh3bench.claim_rights import classify_claim_rights
from enh3bench.human_audit import merge_audit_sources


class ReviewTableSemanticsTests(unittest.TestCase):
    def test_review_table_cannot_be_primary_evidence(self) -> None:
        result = classify_claim_rights(
            {
                "paper_id": "P1",
                "source_span_id": "S1",
                "text_class": "review_table",
                "provenance_type": "review_table",
                "source_text": "Review table reports FE 90%, NH3 yield, and 15N validation.",
            }
        )
        self.assertEqual(result["maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertEqual(result["admissibility_status"], "secondary_only")
        self.assertTrue(all(value == "secondary_only" for value in result["validation_gates"].values()))

    def test_text_class_alone_enforces_review_table_secondary_semantics(self) -> None:
        record = {
            "paper_id": "P1",
            "source_span_id": "S1",
            "source_text": "A literature summary table reports N2-to-NH3 FE 90%.",
            "text_class": "review_table",
            "provenance_type": "body",
            "maximum_supported_boundary": "cell_metric",
            "admissibility_status": "metric_only_or_validation_incomplete",
            "validation_gates": {"isotope_15N": "missing", "blank_control": "missing", "nox_control": "missing"},
            "missing_boundary_fields": [],
            "required_controls": [],
        }
        merged = merge_audit_sources(
            [record], routing_profile="secondary_hardening_v1", reference_audit_sample_rate=0.0
        )[0]
        self.assertEqual(merged["maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertEqual(merged["admissibility_status"], "secondary_only")
        self.assertNotIn("missing_blank_control", merged["audit_priority_reasons"])
        self.assertNotIn("missing_NOx_control", merged["audit_priority_reasons"])


if __name__ == "__main__":
    unittest.main()
