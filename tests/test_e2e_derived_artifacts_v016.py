from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from enh3bench.e2e_case_generation import E2E_REVIEW_COLUMNS
from enh3bench.e2e_eval_metrics import summarize_e2e
from enh3bench.e2e_eval_package import build_selective_eval_package
from enh3bench.e2e_eval_schema import (
    FINAL_HUMAN_LABEL_FIELDS,
    read_csv,
    read_jsonl,
    write_csv,
    write_json,
    write_jsonl,
)
from enh3bench.e2e_eval_validation import validate_selective_eval_package
from tests.selective_eval_test_helpers import (
    create_source_calibration_fixture,
    valid_api_outputs,
    valid_machine_judgments,
)


class DerivedArtifactValidationV016Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source_root = self.base / "data/calibration"
        self.eval_root = self.base / "data/selective_eval"
        create_source_calibration_fixture(self.source_root)
        build_selective_eval_package(
            source_calibration_run_name="calibration_fixture",
            source_calibration_root=self.source_root,
            selective_eval_run_name="eval", selective_eval_root=self.eval_root,
            clean=True, validate_source_package=False,
        )
        self.package_dir = self.eval_root / "eval"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def validate(self) -> dict:
        return validate_selective_eval_package(
            selective_eval_run_name="eval", selective_eval_root=self.eval_root,
            source_calibration_root=self.source_root, check_source_package=False,
        )

    def write_outputs(self, rows: list[dict]) -> None:
        write_jsonl(self.package_dir / "cases/api_outputs.jsonl", rows)

    def write_judgments(self, rows: list[dict]) -> None:
        write_jsonl(self.package_dir / "cases/machine_judgments.jsonl", rows)

    def assert_fails_with(self, fragment: str) -> None:
        result = self.validate()
        self.assertEqual(result["result"], "FAIL")
        self.assertTrue(any(fragment in error for error in result["errors"]), result["errors"])

    def test_imported_output_case_id_mutation_fails(self) -> None:
        rows = valid_api_outputs(self.package_dir, 1)
        rows[0]["source_case_id"] = "EC16_UNKNOWN"
        self.write_outputs(rows)
        self.assert_fails_with("unknown_imported_api_output_case")

    def test_malformed_optional_output_jsonl_fails(self) -> None:
        (self.package_dir / "cases/api_outputs.jsonl").write_text("{malformed\n", encoding="utf-8")
        self.assert_fails_with("invalid_optional_artifact")

    def test_imported_output_source_sha_mutation_fails(self) -> None:
        rows = valid_api_outputs(self.package_dir, 1)
        rows[0]["source_manifest_sha256"] = "0" * 64
        self.write_outputs(rows)
        self.assert_fails_with("api_output_source_manifest_mismatch")

    def test_imported_output_outside_allowlist_fails(self) -> None:
        rows = valid_api_outputs(self.package_dir, 1)
        rows[0].update({
            "answer_status": "answered", "generation_status": "completed", "answer_text": "claim",
            "claims": [{
                "claim_id": "c1", "claim_text": "claim", "claim_type": "result",
                "supporting_source_span_ids": ["CR15_OUTSIDE"],
                "supporting_evidence_link_ids": [], "support_status": "supported",
            }],
        })
        self.write_outputs(rows)
        self.assert_fails_with("citation_outside_span_allowlist")

    def test_duplicate_imported_output_fails(self) -> None:
        row = valid_api_outputs(self.package_dir, 1)[0]
        self.write_outputs([row, deepcopy(row)])
        self.assert_fails_with("duplicate_imported_api_output")

    def test_imported_output_unknown_field_fails(self) -> None:
        rows = valid_api_outputs(self.package_dir, 1)
        rows[0]["unknown"] = True
        self.write_outputs(rows)
        self.assert_fails_with("unknown_api_output_field")

    def test_imported_output_malformed_claim_fails(self) -> None:
        rows = valid_api_outputs(self.package_dir, 1)
        rows[0].update({
            "answer_status": "answered", "generation_status": "completed",
            "answer_text": "claim", "claims": [{"claim_id": "c1"}],
        })
        self.write_outputs(rows)
        self.assert_fails_with("claim_schema_mismatch")

    def test_valid_partial_outputs_pass(self) -> None:
        self.write_outputs(valid_api_outputs(self.package_dir, 3))
        result = self.validate()
        self.assertEqual(result["result"], "PASS", result["errors"])
        self.assertEqual(result["counts"]["imported_api_output_count"], 3)
        self.assertEqual(result["counts"]["missing_api_output_count"], 45)
        self.assertEqual(result["counts"]["package_stage"], "generated")

    def test_valid_complete_outputs_pass(self) -> None:
        self.write_outputs(valid_api_outputs(self.package_dir))
        result = self.validate()
        self.assertEqual(result["result"], "PASS", result["errors"])
        self.assertEqual(result["counts"]["api_output_completion_rate"], 1.0)

    def prepare_outputs(self) -> None:
        self.write_outputs(valid_api_outputs(self.package_dir))

    def test_judgment_source_output_mismatch_fails(self) -> None:
        self.prepare_outputs()
        rows = valid_machine_judgments(self.package_dir, case_count=1, observations_per_case=1)
        rows[0]["source_api_output_id"] = "EO16_UNKNOWN"
        self.write_judgments(rows)
        self.assert_fails_with("unknown_imported_machine_judgment_output")

    def test_judgments_without_outputs_fail(self) -> None:
        self.write_judgments(valid_machine_judgments(self.package_dir, case_count=1, observations_per_case=1))
        self.assert_fails_with("machine_judgments_require_api_outputs")

    def test_unknown_judge_slot_fails(self) -> None:
        self.prepare_outputs()
        rows = valid_machine_judgments(self.package_dir, case_count=1, observations_per_case=1)
        rows[0]["judge_slot"] = "judge_3"
        self.write_judgments(rows)
        self.assert_fails_with("judgment_source_identity_mismatch:judge_slot")

    def test_judgment_unknown_case_fails(self) -> None:
        self.prepare_outputs()
        rows = valid_machine_judgments(self.package_dir, case_count=1, observations_per_case=1)
        rows[0]["source_case_id"] = "EC16_UNKNOWN"
        self.write_judgments(rows)
        self.assert_fails_with("unknown_imported_machine_judgment_case")

    def test_duplicate_judgment_observation_fails(self) -> None:
        self.prepare_outputs()
        row = valid_machine_judgments(self.package_dir, case_count=1, observations_per_case=1)[0]
        self.write_judgments([row, deepcopy(row)])
        self.assert_fails_with("duplicate_imported_machine_judgment")

    def test_invalid_judgment_score_fails(self) -> None:
        self.prepare_outputs()
        rows = valid_machine_judgments(self.package_dir, case_count=1, observations_per_case=1)
        rows[0]["dimensions"]["answer_correctness"]["score"] = 2
        self.write_judgments(rows)
        self.assert_fails_with("invalid_judge_score")

    def test_invalid_judgment_evidence_fails(self) -> None:
        self.prepare_outputs()
        rows = valid_machine_judgments(self.package_dir, case_count=1, observations_per_case=1)
        rows[0]["dimensions"]["answer_correctness"]["evidence"] = [{
            "source_span_ids": ["CR15_OUTSIDE"], "evidence_link_ids": [], "claim_ids": [],
        }]
        self.write_judgments(rows)
        self.assert_fails_with("judge_evidence_outside_span_allowlist")

    def test_machine_judgment_human_truth_claim_fails(self) -> None:
        self.prepare_outputs()
        rows = valid_machine_judgments(self.package_dir, case_count=1, observations_per_case=1)
        rows[0]["human_truth_claimed"] = True
        self.write_judgments(rows)
        self.assert_fails_with("machine_judgment_claims_human_truth")

    def test_valid_partial_judgments_pass(self) -> None:
        self.prepare_outputs()
        self.write_judgments(valid_machine_judgments(self.package_dir, case_count=2, observations_per_case=1))
        result = self.validate()
        self.assertEqual(result["result"], "PASS", result["errors"])
        self.assertEqual(result["counts"]["imported_machine_judgment_count"], 2)
        self.assertEqual(result["counts"]["package_stage"], "judged")

    def test_valid_complete_two_judge_set_passes(self) -> None:
        self.prepare_outputs()
        self.write_judgments(valid_machine_judgments(self.package_dir))
        result = self.validate()
        self.assertEqual(result["result"], "PASS", result["errors"])
        self.assertEqual(result["counts"]["imported_machine_judgment_count"], 96)

    def write_summary(self, summary: dict) -> None:
        write_json(self.package_dir / "reports/e2e_metrics_summary.json", summary)

    def test_blank_not_available_metrics_summary_passes(self) -> None:
        self.write_summary(summarize_e2e(self.package_dir))
        result = self.validate()
        self.assertEqual(result["result"], "PASS", result["errors"])

    def test_stale_metrics_output_count_fails(self) -> None:
        summary = summarize_e2e(self.package_dir)
        summary["api_output_count"] = 1
        self.write_summary(summary)
        self.assert_fails_with("metrics_summary_stale_or_inconsistent:api_output_count")

    def test_stale_metrics_judgment_count_fails(self) -> None:
        self.prepare_outputs()
        self.write_judgments(valid_machine_judgments(self.package_dir, case_count=1, observations_per_case=1))
        summary = summarize_e2e(self.package_dir)
        summary["machine_judgment_count"] = 0
        self.write_summary(summary)
        self.assert_fails_with("metrics_summary_stale_or_inconsistent:machine_judgment_count")

    def test_metrics_source_identity_mismatch_fails(self) -> None:
        summary = summarize_e2e(self.package_dir)
        summary["source_calibration_manifest_sha256"] = "0" * 64
        self.write_summary(summary)
        self.assert_fails_with("metrics_summary_identity_mismatch")

    def test_fabricated_pass_rate_fails(self) -> None:
        summary = summarize_e2e(self.package_dir)
        summary["pass_rate"] = {"value": 1.0, "status": "available", "provenance": "fixture"}
        self.write_summary(summary)
        self.assert_fails_with("metrics_summary_fabricated_without_prerequisites:pass_rate")

    def test_completed_future_package_summary_structure_passes(self) -> None:
        self.prepare_outputs()
        self.write_judgments(valid_machine_judgments(self.package_dir))
        review_path = self.package_dir / "review/e2e_human_review.csv"
        reviews = read_csv(review_path)
        for row in reviews:
            row["review_status"] = "completed"
            for field in FINAL_HUMAN_LABEL_FIELDS:
                row[field] = "yes"
            row["human_overall_verdict"] = "pass"
        write_csv(review_path, reviews, E2E_REVIEW_COLUMNS)
        self.write_summary(summarize_e2e(self.package_dir))
        result = self.validate()
        self.assertEqual(result["result"], "PASS", result["errors"])
        self.assertEqual(result["counts"]["package_stage"], "human_reviewed")


if __name__ == "__main__":
    unittest.main()
