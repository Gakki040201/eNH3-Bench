from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from enh3bench.hidden_tax import detect_hidden_taxes
from enh3bench.human_audit import export_audit_report, merge_audit_sources


class SecondaryAuditRoutingTests(unittest.TestCase):
    def test_stable_reference_is_auto_secondary_without_missing_control_reasons(self) -> None:
        merged = _secondary_merge(_reference())
        self.assertTrue(merged["auto_secondary_reference"])
        self.assertFalse(merged["rule_needs_human_review"])
        self.assertFalse(merged["overall_needs_human_review"])
        self.assertEqual(merged["review_priority_band"], "none")
        self.assertEqual(merged["maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertEqual(merged["admissibility_status"], "reject_or_low_trust_provenance")
        self.assertTrue(all(value == "secondary_only" for value in merged["validation_gates"].values()))
        for reason in ("missing_15N_for_N2_to_NH3_claim", "missing_blank_control", "missing_NOx_control"):
            self.assertNotIn(reason, merged["audit_priority_reasons"])

    def test_stable_reference_does_not_trigger_hidden_tax_cascade(self) -> None:
        result = detect_hidden_taxes(
            {
                **_reference(),
                "source_text": "1. Smith et al. Electrolyte solvent flow GDE HOR H2 outlet capture FE 80%. 2020.",
            }
        )
        self.assertEqual(result["detected_taxes"], [])
        self.assertEqual(result["required_controls"], [])
        self.assertEqual(result["severity"], "none")

    def test_conflict_reference_still_requires_review(self) -> None:
        merged = merge_audit_sources(
            [{**_reference(), "reaction_family_conflict": True}],
            routing_profile="secondary_hardening_v1",
            reference_audit_sample_rate=0.0,
        )[0]
        self.assertFalse(merged["auto_secondary_reference"])
        self.assertTrue(merged["reference_conflict_review"])
        self.assertTrue(merged["rule_needs_human_review"])
        self.assertTrue(merged["overall_needs_human_review"])
        self.assertIn("reaction_family_conflict", merged["review_trigger_flags"])

    def test_unconfirmed_reference_list_and_manual_force_require_review(self) -> None:
        for updates in ({"text_class": "unknown"}, {"force_human_review": True}):
            with self.subTest(updates=updates):
                merged = merge_audit_sources(
                    [{**_reference(), **updates}],
                    routing_profile="secondary_hardening_v1",
                    reference_audit_sample_rate=0.0,
                )[0]
                self.assertTrue(merged["overall_needs_human_review"])
                self.assertTrue(merged["reference_conflict_review"])

    def test_missing_agreement_infers_disagreement_before_reference_normalization(self) -> None:
        record = {**_reference(), "maximum_supported_boundary": "cell_metric", "llm_maximum_supported_boundary": "unsupported_or_secondary"}
        record.pop("boundary_agreement")
        merged = _secondary_merge(record)
        self.assertEqual(merged["maximum_supported_boundary"], "unsupported_or_secondary")
        self.assertFalse(merged["auto_secondary_reference"])
        self.assertTrue(merged["reference_conflict_review"])
        self.assertTrue(merged["rule_needs_human_review"])
        self.assertTrue(merged["overall_needs_human_review"])
        self.assertNotEqual(merged["review_priority_band"], "none")
        self.assertIn("reference_rule_llm_disagreement", merged["review_trigger_flags"])

    def test_missing_agreement_with_equal_boundaries_can_be_stable(self) -> None:
        record = {**_reference(), "llm_maximum_supported_boundary": "unsupported_or_secondary"}
        record.pop("boundary_agreement")
        merged = _secondary_merge(record)
        self.assertTrue(merged["auto_secondary_reference"])
        self.assertFalse(merged["overall_needs_human_review"])

    def test_explicit_false_agreement_requires_review_even_when_boundaries_match(self) -> None:
        merged = _secondary_merge(
            {**_reference(), "boundary_agreement": False, "llm_maximum_supported_boundary": "unsupported_or_secondary"}
        )
        self.assertFalse(merged["auto_secondary_reference"])
        self.assertTrue(merged["overall_needs_human_review"])

    def test_llm_parse_or_schema_error_cannot_be_stable(self) -> None:
        for updates in (
            {"llm_parse_error": "schema_invalid: missing field"},
            {"llm_audit_flags": ["llm_parse_or_schema_error"]},
        ):
            with self.subTest(updates=updates):
                merged = _secondary_merge({**_reference(), **updates})
                self.assertFalse(merged["auto_secondary_reference"])
                self.assertTrue(merged["reference_conflict_review"])
                self.assertTrue(merged["overall_needs_human_review"])

    def test_no_llm_result_can_be_stable(self) -> None:
        record = _reference()
        record.pop("boundary_agreement")
        merged = _secondary_merge(record)
        self.assertTrue(merged["auto_secondary_reference"])
        self.assertFalse(merged["overall_needs_human_review"])

    def test_human_audit_report_includes_secondary_routing_counts_and_explanation(self) -> None:
        records = merge_audit_sources(
            [_reference()], routing_profile="secondary_hardening_v1", reference_audit_sample_rate=0.0
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = export_audit_report(
                records, "fixture", output_dir=Path(temp_dir), routing_profile="secondary_hardening_v1"
            )
            report = Path(report_path).read_text(encoding="utf-8")
        for name in (
            "stable_reference_auto_secondary_count",
            "reference_sampled_for_audit_count",
            "reference_conflict_review_count",
            "caption_context_only_count",
            "review_table_secondary_count",
            "secondary_validation_gate_count",
        ):
            self.assertIn(name, report)
        self.assertIn("routing_profile: secondary_hardening_v1", report)
        self.assertIn("remain in the dataset", report)
        self.assertIn("conflict cases still enter human review", report)

    def test_v013_primary_input_remains_processable(self) -> None:
        legacy = {
            "schema_version": "0.13",
            "paper_id": "P1",
            "source_span_id": "S-body",
            "evidence_id": "E-body",
            "source_text": "Primary results report FE 30% with blank and NOx controls.",
            "provenance_type": "body",
            "text_class": "primary_performance",
            "maximum_supported_boundary": "cell_metric",
            "admissibility_status": "metric_only_or_validation_incomplete",
            "validation_gates": {"isotope_15N": "yes", "blank_control": "yes", "nox_control": "yes"},
            "missing_boundary_fields": [],
            "required_controls": [],
        }
        merged = merge_audit_sources([legacy], reference_audit_sample_rate=0.0)[0]
        self.assertEqual(merged["schema_version"], "0.13")
        self.assertEqual(merged["maximum_supported_boundary"], "cell_metric")
        self.assertNotIn("auto_secondary_reference", merged)


def _reference() -> dict[str, object]:
    return {
        "schema_version": "0.13",
        "paper_id": "P1",
        "source_span_id": "S-ref",
        "evidence_id": "E-ref",
        "source_text": "1. Smith et al. A catalyst study. Journal 10, 1-2 (2020).",
        "provenance_type": "reference",
        "text_class": "reference_list",
        "maximum_supported_boundary": "unsupported_or_secondary",
        "admissibility_status": "reject_or_low_trust_provenance",
        "validation_gates": {
            "isotope_15N": "missing",
            "blank_control": "missing",
            "nox_control": "missing",
            "contamination_control": "missing",
            "quantification_method": "missing",
        },
        "missing_boundary_fields": ["isotope_15N", "blank_control", "nox_control"],
        "required_controls": ["15N2 isotope validation", "Ar/N2-free blank", "NOx/nitrate/nitrite screening"],
        "reaction_family_conflict": False,
        "text_class_provenance_conflict": False,
        "boundary_agreement": True,
    }


def _secondary_merge(record: dict[str, object]) -> dict[str, object]:
    return merge_audit_sources(
        [record], routing_profile="secondary_hardening_v1", reference_audit_sample_rate=0.0
    )[0]


if __name__ == "__main__":
    unittest.main()
