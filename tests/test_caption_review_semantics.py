from __future__ import annotations

import unittest

from enh3bench.claim_rights import classify_claim_rights
from enh3bench.human_audit import merge_audit_sources


class CaptionReviewSemanticsTests(unittest.TestCase):
    def test_unpaired_caption_cannot_upgrade_claim_boundary(self) -> None:
        result = classify_claim_rights(
            {
                "paper_id": "P1",
                "source_span_id": "S1",
                "text_class": "primary_performance",
                "provenance_type": "figure_caption",
                "source_text": "Fig. 1. FE 80% and NH3 yield at 2.0 V.",
            }
        )
        self.assertEqual(result["maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertEqual(result["admissibility_status"], "context_only_caption")
        self.assertEqual(result["support_hint_boundary"], "cell_metric")
        self.assertTrue(all(value == "secondary_only" for value in result["validation_gates"].values()))

    def test_caption_does_not_receive_mechanical_missing_control_reasons(self) -> None:
        record = {
            "paper_id": "P1",
            "source_span_id": "S1",
            "source_text": "Fig. 1. N2-to-NH3 FE 80%.",
            "text_class": "primary_performance",
            "provenance_type": "scheme_caption",
            "maximum_supported_boundary": "cell_metric",
            "admissibility_status": "metric_only_or_validation_incomplete",
            "validation_gates": {"isotope_15N": "missing", "blank_control": "missing", "nox_control": "missing"},
            "missing_boundary_fields": [],
            "required_controls": [],
        }
        merged = merge_audit_sources(
            [record], routing_profile="secondary_hardening_v1", reference_audit_sample_rate=0.0
        )[0]
        for reason in ("missing_15N_for_N2_to_NH3_claim", "missing_blank_control", "missing_NOx_control"):
            self.assertNotIn(reason, merged["audit_priority_reasons"])


if __name__ == "__main__":
    unittest.main()
