from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from enh3bench.e2e_case_generation import generate_cases, make_api_output_templates, make_machine_judgment_templates
from enh3bench.e2e_eval_metrics import summarize_e2e, validate_api_output, validate_machine_judgment
from enh3bench.e2e_eval_package import build_selective_eval_package
from enh3bench.e2e_risk_routing import build_risk_ledger
from tests.selective_eval_test_helpers import create_source_calibration_fixture, synthetic_frames


class E2EEvalMetricsV016Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frames = synthetic_frames()
        cls.ledger = build_risk_ledger(cls.frames)
        cls.cases = generate_cases(cls.frames, cls.ledger, source_manifest_sha256="a" * 64, seed=16)

    def valid_output(self) -> tuple[dict, dict]:
        case = next(row for row in self.cases if row["allowed_source_span_ids"])
        output = make_api_output_templates([case])[0]
        output.update({
            "answer_text": "A bounded answer.", "answer_status": "answered",
            "confidence_statement": "Moderate confidence.", "generation_model": "fixture-model",
            "generation_prompt_version": "fixture-prompt", "generation_status": "completed",
            "generation_parameters": {"temperature": 0}, "api_call_performed": True,
            "claims": [{
                "claim_id": "c1", "claim_text": "A bounded claim.", "claim_type": "result",
                "supporting_source_span_ids": [case["allowed_source_span_ids"][0]],
                "supporting_evidence_link_ids": [], "support_status": "supported",
            }],
        })
        return case, output

    def test_valid_future_api_output_contract(self) -> None:
        case, output = self.valid_output()
        self.assertEqual(validate_api_output(output, case), [])

    def test_successful_output_requires_complete_generation_provenance(self) -> None:
        case, output = self.valid_output()
        mutations = (
            ("api_call_performed", False, "successful_output_requires_api_call"),
            ("generation_model", "", "successful_output_missing_generation_model"),
            ("generation_prompt_version", "", "successful_output_missing_generation_prompt_version"),
            ("generation_parameters", {}, "successful_output_missing_generation_parameters"),
        )
        for field, value, expected in mutations:
            with self.subTest(field=field):
                changed = deepcopy(output)
                changed[field] = value
                self.assertIn(expected, validate_api_output(changed, case))

    def test_failed_output_requires_reason_and_contains_no_substantive_answer(self) -> None:
        case = self.cases[0]
        output = make_api_output_templates([case])[0]
        output.update({
            "answer_status": "failed", "generation_status": "failed",
            "limitations": ["provider failure"],
        })
        self.assertEqual(validate_api_output(output, case), [])
        output["limitations"] = []
        self.assertIn("failed_output_missing_failure_reason", validate_api_output(output, case))
        output["answer_text"] = "fabricated result"
        self.assertIn("failed_output_contains_substantive_answer", validate_api_output(output, case))

    def test_citation_outside_allowlist_rejected(self) -> None:
        case, output = self.valid_output()
        output["claims"] = [{
            "claim_id": "c1", "claim_text": "claim", "claim_type": "result",
            "supporting_source_span_ids": ["CR15_OUTSIDE"], "supporting_evidence_link_ids": [],
            "support_status": "supported",
        }]
        self.assertTrue(any("outside_span_allowlist" in error for error in validate_api_output(output, case)))

    def test_unknown_api_field_rejected(self) -> None:
        case, output = self.valid_output(); output["unknown"] = "x"
        self.assertTrue(any("unknown_api_output_field" in error for error in validate_api_output(output, case)))

    def test_answered_without_claim_rejected(self) -> None:
        case, output = self.valid_output(); output["claims"] = []
        self.assertIn("answered_output_missing_claims", validate_api_output(output, case))

    def test_abstained_substantive_answer_rejected(self) -> None:
        case, output = self.valid_output()
        output.update({"answer_status": "abstained", "abstention_reason": "Insufficient evidence."})
        self.assertIn("abstained_output_contains_substantive_answer", validate_api_output(output, case))

    def test_malformed_top_level_citation_rejected(self) -> None:
        case, output = self.valid_output()
        output["citations"] = [{"source_span_ids": case["allowed_source_span_ids"]}]
        self.assertIn("citation_schema_mismatch:1", validate_api_output(output, case))

    def valid_judgment(self) -> tuple[dict, dict]:
        template = make_machine_judgment_templates([self.cases[0]])[0]
        row = deepcopy(template)
        row["judge_id"] = "fixture_judge"
        row["judgment_status"] = "completed"
        row["judge_call_performed"] = True
        for name, dimension in row["dimensions"].items():
            dimension.update({
                "score": 0 if name == "unsupported_claim_count" else 0.8,
                "verdict": "pass", "confidence": 0.7, "rationale": "fixture rationale",
                "evidence": [], "judge_model": "fixture", "judge_prompt_version": "v1",
            })
        return template, row

    def test_valid_future_machine_judgment(self) -> None:
        template, row = self.valid_judgment()
        self.assertEqual(validate_machine_judgment(row, template), [])

    def test_invalid_judge_schema_rejected(self) -> None:
        template, row = self.valid_judgment(); row["dimensions"].pop("answer_correctness")
        self.assertIn("invalid_judge_dimension_set", validate_machine_judgment(row, template))

    def test_judge_evidence_outside_case_rejected(self) -> None:
        template, row = self.valid_judgment()
        case = next(case for case in self.cases if case["case_id"] == row["source_case_id"])
        row["dimensions"]["answer_correctness"]["evidence"] = [{
            "source_span_ids": ["CR15_OUTSIDE"], "evidence_link_ids": [], "claim_ids": [],
        }]
        errors = validate_machine_judgment(row, template, case)
        self.assertTrue(any("outside_span_allowlist" in error for error in errors))

    def test_empty_metrics_are_not_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); source = base / "data/calibration"; eval_root = base / "data/selective_eval"
            create_source_calibration_fixture(source)
            build_selective_eval_package(
                source_calibration_run_name="calibration_fixture", source_calibration_root=source,
                selective_eval_run_name="eval", selective_eval_root=eval_root,
                clean=True, validate_source_package=False,
            )
            result = summarize_e2e(eval_root / "eval")
            self.assertEqual(result["status"], "not_available")
            self.assertIsNone(result["precision"])
            self.assertIsNone(result["pass_rate"])
            self.assertIsNone(result["unsupported_claim_rate"])
            self.assertEqual(result["fabricated_metric_count"], 0)


if __name__ == "__main__":
    unittest.main()
