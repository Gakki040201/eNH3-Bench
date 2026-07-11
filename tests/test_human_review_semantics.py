from __future__ import annotations

import unittest

from enh3bench.human_audit import merge_audit_sources
from enh3bench.llm_clients.mock_client import MockLLMClient
from enh3bench.llm_verifier import verify_record_with_llm


class HumanReviewSemanticsTests(unittest.TestCase):
    def test_high_audit_score_requires_overall_review(self) -> None:
        record = _record(
            source_text="N2 to NH3 performance was reported.",
            validation_gates={"isotope_15N": "missing", "blank_control": "missing", "nox_control": "missing"},
        )
        merged = merge_audit_sources([record])[0]
        self.assertGreaterEqual(merged["audit_priority_score"], 8)
        self.assertTrue(merged["overall_needs_human_review"])

    def test_llm_schema_error_sets_llm_and_overall_review(self) -> None:
        verified = verify_record_with_llm(_record(), MockLLMClient(force_invalid_schema=True), model="mock")
        self.assertTrue(verified["llm_needs_human_review"])
        self.assertTrue(verified["overall_needs_human_review"])

    def test_rule_provenance_conflict_sets_rule_and_overall_review(self) -> None:
        record = _record(
            provenance_type="reference",
            text_class="primary_performance",
            text_class_provenance_conflict=True,
        )
        merged = merge_audit_sources([record])[0]
        self.assertTrue(merged["rule_needs_human_review"])
        self.assertTrue(merged["overall_needs_human_review"])
        self.assertEqual(merged["review_priority_band"], "critical")

    def test_low_priority_note_can_remain_overall_false(self) -> None:
        merged = merge_audit_sources([_record(optional_audit_note="Optional wording check.")])[0]
        self.assertEqual(merged["review_priority_band"], "low")
        self.assertFalse(merged["overall_needs_human_review"])

    def test_legacy_alias_equals_overall_requirement(self) -> None:
        merged = merge_audit_sources([_record()])[0]
        self.assertEqual(merged["needs_human_review"], merged["overall_needs_human_review"])


def _record(**updates: object) -> dict[str, object]:
    record: dict[str, object] = {
        "claim_id": "CR_E1",
        "evidence_id": "E1",
        "source_span_id": "S1",
        "source_text": "A complete primary result.",
        "provenance_type": "body",
        "text_class": "primary_performance",
        "maximum_supported_boundary": "product_admissibility",
        "validation_gates": {"isotope_15N": "yes", "blank_control": "yes", "nox_control": "yes"},
        "missing_boundary_fields": [],
        "required_controls": [],
    }
    record.update(updates)
    return record


if __name__ == "__main__":
    unittest.main()
