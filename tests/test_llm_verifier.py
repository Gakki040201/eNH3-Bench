from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.llm_clients import MockLLMClient
from enh3bench.llm_verifier import (
    compare_rule_and_llm,
    export_llm_verification_results,
    parse_llm_json_response,
    verify_record_with_llm,
)


class LLMVerifierTests(unittest.TestCase):
    def test_markdown_fenced_json_parsing(self) -> None:
        parsed, error = parse_llm_json_response('```json\n{"maximum_supported_boundary":"cell_metric"}\n```')
        self.assertIsNone(error)
        self.assertEqual(parsed["maximum_supported_boundary"], "cell_metric")

    def test_invalid_json_parsing_failure(self) -> None:
        parsed, error = parse_llm_json_response("not json")
        self.assertIsNone(parsed)
        self.assertIn("invalid JSON", str(error))

    def test_verification_output_includes_needs_human_review(self) -> None:
        record = {
            "claim_id": "CR1",
            "text_class": "primary_performance",
            "provenance_type": "body",
            "maximum_supported_boundary": "cell_metric",
            "missing_boundary_fields": [],
            "required_controls": [],
            "source_text": "The source is too vague for a verified boundary.",
        }
        verified = verify_record_with_llm(record, MockLLMClient(), model="mock")
        self.assertIn("needs_human_review", verified)
        self.assertTrue(verified["llm_more_conservative"])
        self.assertTrue(verified["needs_human_review"])

    def test_llm_more_permissive_than_rule_is_flagged(self) -> None:
        comparison = compare_rule_and_llm(
            {
                "text_class": "primary_performance",
                "maximum_supported_boundary": "unsupported_or_secondary",
                "missing_boundary_fields": [],
                "required_controls": [],
                "source_text": "15N2 isotope FE evidence.",
            },
            {
                "text_class": "primary_performance",
                "maximum_supported_boundary": "cell_metric",
                "missing_boundary_fields": [],
                "required_controls": [],
                "field_support": {"isotope_15N": "explicit"},
            },
        )
        self.assertTrue(comparison["llm_more_permissive"])
        self.assertTrue(comparison["needs_human_review"])
        self.assertIn("llm_more_permissive_than_rule", comparison["llm_audit_flags"])

    def test_low_trust_provenance_cannot_be_silently_upgraded(self) -> None:
        comparison = compare_rule_and_llm(
            {
                "text_class": "primary_performance",
                "provenance_type": "reference",
                "is_reject_or_low_trust": True,
                "maximum_supported_boundary": "unsupported_or_secondary",
                "missing_boundary_fields": [],
                "required_controls": [],
                "source_text": "Reference list text.",
            },
            {
                "text_class": "primary_performance",
                "maximum_supported_boundary": "cell_metric",
                "missing_boundary_fields": [],
                "required_controls": [],
                "field_support": {},
            },
        )
        self.assertTrue(comparison["needs_human_review"])
        self.assertIn("llm_overrode_low_trust_provenance", comparison["llm_audit_flags"])

    def test_possible_unsupported_isotope_claim_flag(self) -> None:
        comparison = compare_rule_and_llm(
            {
                "text_class": "primary_performance",
                "maximum_supported_boundary": "cell_metric",
                "missing_boundary_fields": [],
                "required_controls": [],
                "source_text": "The text reports FE but no labeling evidence.",
            },
            {
                "text_class": "primary_performance",
                "maximum_supported_boundary": "cell_metric",
                "missing_boundary_fields": [],
                "required_controls": [],
                "field_support": {"isotope_15N": "explicit"},
            },
        )
        self.assertTrue(comparison["needs_human_review"])
        self.assertIn("possible_unsupported_isotope_claim", comparison["llm_audit_flags"])

    def test_missing_field_and_required_control_disagreements(self) -> None:
        comparison = compare_rule_and_llm(
            {
                "text_class": "primary_performance",
                "maximum_supported_boundary": "cell_metric",
                "missing_boundary_fields": ["nh3_yield"],
                "required_controls": ["15N2 isotope validation"],
                "source_text": "FE only.",
            },
            {
                "text_class": "primary_performance",
                "maximum_supported_boundary": "cell_metric",
                "missing_boundary_fields": ["runtime"],
                "required_controls": ["Ar/N2-free blank"],
                "field_support": {},
            },
        )
        self.assertIn("nh3_yield", comparison["missing_field_disagreement"])
        self.assertIn("Ar/N2-free blank", comparison["required_control_disagreement"])
        self.assertTrue(comparison["needs_human_review"])

    def test_export_path_sanitizes_model_name(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = export_llm_verification_results(
                [{"claim_id": "CR1", "llm_model": "model/a", "source_text": "x"}],
                [],
                "run1",
                "ustc/model:alpha beta?",
                output_dir=Path(temp_dir),
            )
            self.assertIn("ustc_model_alpha_beta", outputs["jsonl"])
            self.assertTrue(Path(outputs["jsonl"]).exists())
            self.assertTrue(Path(outputs["csv"]).exists())
            self.assertTrue(Path(outputs["failures_jsonl"]).exists())


if __name__ == "__main__":
    unittest.main()
