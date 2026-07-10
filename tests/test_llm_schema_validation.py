from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from enh3bench.llm_clients import MockLLMClient
from enh3bench.llm_verifier import (
    export_llm_verification_results,
    parse_llm_json_response,
    validate_llm_verification_schema,
    verify_record_with_llm,
    verify_records_with_llm,
)
from scripts.compare_llm_models import _comparison_row


class LLMVerificationSchemaTests(unittest.TestCase):
    def test_valid_strict_json_passes_validation(self) -> None:
        valid, messages = validate_llm_verification_schema(_valid_llm_response())
        self.assertTrue(valid)
        self.assertEqual(messages, [])

    def test_text_only_json_fails_schema_validation(self) -> None:
        valid, messages = validate_llm_verification_schema({"text": "We are given a record to verify..."})
        self.assertFalse(valid)
        self.assertTrue(any(message.startswith("missing_top_level_key:") for message in messages))

    def test_missing_field_support_fails(self) -> None:
        response = _valid_llm_response()
        del response["field_support"]
        valid, messages = validate_llm_verification_schema(response)
        self.assertFalse(valid)
        self.assertIn("missing_top_level_key:field_support", messages)

    def test_missing_required_field_support_key_fails(self) -> None:
        response = _valid_llm_response()
        del response["field_support"]["FE"]
        valid, messages = validate_llm_verification_schema(response)
        self.assertFalse(valid)
        self.assertIn("missing_field_support_key:FE", messages)

    def test_invalid_maximum_supported_boundary_fails(self) -> None:
        response = _valid_llm_response()
        response["maximum_supported_boundary"] = "paper_level_truth"
        valid, messages = validate_llm_verification_schema(response)
        self.assertFalse(valid)
        self.assertIn("invalid_maximum_supported_boundary:paper_level_truth", messages)

    def test_invalid_field_support_value_fails(self) -> None:
        response = _valid_llm_response()
        response["field_support"]["FE"] = "supported"
        valid, messages = validate_llm_verification_schema(response)
        self.assertFalse(valid)
        self.assertIn("invalid_field_support_value:FE=supported", messages)

    def test_markdown_fenced_valid_json_passes(self) -> None:
        parsed, error = parse_llm_json_response(f"```json\n{json.dumps(_valid_llm_response())}\n```")
        self.assertIsNone(error)
        self.assertEqual(parsed["maximum_supported_boundary"], "cell_metric")

    def test_markdown_fenced_invalid_schema_fails(self) -> None:
        parsed, error = parse_llm_json_response('```json\n{"text":"invalid schema"}\n```')
        self.assertIsNone(parsed)
        self.assertTrue(str(error).startswith("schema_invalid:"))

    def test_verify_record_with_llm_marks_schema_failure_for_human_review(self) -> None:
        verified = verify_record_with_llm(_record(), MockLLMClient(force_invalid_schema=True), model="mock")
        self.assertIsNone(verified["llm_verification"])
        self.assertTrue(str(verified["llm_parse_error"]).startswith("schema_invalid:"))
        self.assertFalse(verified["boundary_agreement"])
        self.assertFalse(verified["text_class_agreement"])
        self.assertFalse(verified["llm_more_permissive"])
        self.assertFalse(verified["llm_more_conservative"])
        self.assertTrue(verified["needs_human_review"])
        self.assertEqual(verified["llm_audit_flags"], ["llm_parse_or_schema_error"])

    def test_schema_failure_is_exported_to_failures(self) -> None:
        results, failures = verify_records_with_llm([_record()], MockLLMClient(force_invalid_schema=True), model="mock")
        self.assertEqual(len(results), 1)
        self.assertEqual(len(failures), 1)
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = export_llm_verification_results(results, failures, "schema_test", "mock", output_dir=Path(temp_dir))
            failure_rows = [json.loads(line) for line in Path(outputs["failures_jsonl"]).read_text(encoding="utf-8").splitlines()]
            csv_text = Path(outputs["csv"]).read_text(encoding="utf-8")

        self.assertEqual(failure_rows[0]["evidence_id"], "E1")
        self.assertEqual(failure_rows[0]["source_span_id"], "S1")
        self.assertEqual(failure_rows[0]["error_type"], "schema_invalid")
        self.assertTrue(failure_rows[0]["error_message"].startswith("schema_invalid:"))
        self.assertIn("invalid schema", failure_rows[0]["llm_raw_response"])
        self.assertIn("llm_parse_error", csv_text.splitlines()[0])

    def test_compare_model_metrics_count_parse_and_schema_errors(self) -> None:
        row = _comparison_row(
            "mock",
            [_record(), _record()],
            [
                {"llm_parse_error": "json_parse_error: bad json"},
                {"llm_parse_error": "schema_invalid: missing_top_level_key:text_class"},
            ],
            [],
            max_records=2,
        )
        self.assertEqual(row["parse_error_count"], 1)
        self.assertEqual(row["schema_error_count"], 1)


def _valid_llm_response() -> dict[str, object]:
    response: dict[str, object] = {
        "text_class": "primary_performance",
        "field_support": {
            "FE": "explicit",
            "NH3_yield": "missing",
            "EE": "missing",
            "current_density": "missing",
            "potential_or_voltage": "missing",
            "runtime": "missing",
            "isotope_15N": "explicit",
            "blank_control": "missing",
            "NOx_control": "missing",
            "reactor_type": "explicit",
            "HOR": "missing",
            "product_state": "missing",
            "capture_route": "missing",
            "solvent_inventory": "missing",
            "failure_mode": "missing",
        },
        "maximum_supported_boundary": "cell_metric",
        "missing_boundary_fields": [],
        "hidden_tax": [],
        "required_controls": [],
        "overclaim_risk": [],
        "recommended_experiment": "Run source-grounded follow-up checks.",
        "reasoning": "The source explicitly supports FE and isotope evidence.",
    }
    return copy.deepcopy(response)


def _record() -> dict[str, object]:
    return {
        "claim_id": "CR1",
        "paper_id": "P1",
        "source_span_id": "S1",
        "evidence_id": "E1",
        "text_class": "primary_performance",
        "provenance_type": "body",
        "maximum_supported_boundary": "cell_metric",
        "missing_boundary_fields": [],
        "required_controls": [],
        "source_text": "15N2 isotope evidence reports FE in a reactor cell.",
    }


if __name__ == "__main__":
    unittest.main()
