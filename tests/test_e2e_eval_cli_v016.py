from __future__ import annotations

import json
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from enh3bench.e2e_case_generation import make_api_output_templates
from enh3bench.e2e_eval_schema import JUDGE_DIMENSIONS
from enh3bench.e2e_eval_package import build_selective_eval_package
from enh3bench.e2e_eval_schema import read_jsonl, write_json, write_jsonl
from scripts import prepare_api_generation_batch
from tests.selective_eval_test_helpers import (
    create_source_calibration_fixture,
    valid_freeze_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


class E2EEvalCliV016Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source_root = self.base / "data/calibration"
        self.source_run_name = "calibration_fixture"
        create_source_calibration_fixture(self.source_root, run_name=self.source_run_name)
        self.eval_root = self.base / "data/selective_eval"
        build_selective_eval_package(
            source_calibration_run_name=self.source_run_name, source_calibration_root=self.source_root,
            selective_eval_run_name="eval", selective_eval_root=self.eval_root,
            clean=True, validate_source_package=False,
        )
        self.package_dir = self.eval_root / "eval"
        imported = make_api_output_templates([
            case for case in read_jsonl(self.package_dir / "cases/e2e_case_frame.jsonl")
            if case["split"] == "development"
        ])
        for row in imported:
            row.update({
                "answer_status": "abstained", "generation_status": "completed",
                "api_call_performed": True, "generation_model": "fixture-model-family",
                "generation_prompt_version": "fixture-prompt-v1",
                "generation_parameters": {"temperature": 0, "max_tokens": 512},
                "abstention_reason": "fixture bounded evidence insufficient",
            })
        write_jsonl(self.package_dir / "cases/api_outputs.jsonl", imported)
        self.prompt_file = self.base / "prompt.txt"
        self.prompt_file.write_text("fixture generation prompt\n", encoding="utf-8")
        self.parameters_file = self.base / "generation_parameters.json"
        write_json(self.parameters_file, {"temperature": 0, "max_tokens": 512})

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_source_validated_main(
        self, module: object, args: tuple[str, ...], script: str,
    ) -> subprocess.CompletedProcess[str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        real_validate = module.validate_selective_eval_package

        def validate_with_synthetic_source(**kwargs: object) -> dict:
            self.assertIs(kwargs.get("check_source_package"), True)
            with mock.patch(
                "enh3bench.e2e_eval_validation.validate_calibration_package",
                return_value={"result": "PASS", "errors": []},
            ):
                return real_validate(**kwargs)

        with mock.patch.object(
            module, "validate_selective_eval_package", side_effect=validate_with_synthetic_source,
        ):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                returncode = module.main(list(args))
        return subprocess.CompletedProcess(
            [script, *args], returncode, stdout.getvalue(), stderr.getvalue()
        )

    def run_cli(self, script: str, *args: str) -> subprocess.CompletedProcess[str]:
        if script == "prepare_api_generation_batch.py":
            return self.run_source_validated_main(
                prepare_api_generation_batch, args, script,
            )
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script), *args], cwd=ROOT,
            text=True, capture_output=True, check=False,
        )

    def test_build_dry_run_writes_nothing(self) -> None:
        target = "dry_run_target"
        result = self.run_cli(
            "build_selective_eval_package.py", "--source-calibration-run-name", self.source_run_name,
            "--source-calibration-root", str(self.source_root), "--selective-eval-run-name", target,
            "--selective-eval-root", str(self.eval_root), "--dry-run",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.eval_root / target).exists())

    def test_prepare_batch_exports_without_api(self) -> None:
        output = self.base / "exported_batch.jsonl"
        result = self.run_cli(
            "prepare_api_generation_batch.py", "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root),
            "--source-calibration-root", str(self.source_root), "--output", str(output),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("network_calls: 0", result.stdout)
        rows = read_jsonl(output)
        self.assertEqual(len(rows), 36)
        case_split = {
            row["case_id"]: row["split"]
            for row in read_jsonl(self.package_dir / "cases/e2e_case_frame.jsonl")
        }
        self.assertTrue(all(case_split[row["case_id"]] == "development" for row in rows))
        self.assertTrue(all("answerability_status" not in row for row in rows))

    def test_holdout_export_requires_freeze_manifest(self) -> None:
        output = self.base / "holdout_without_freeze.jsonl"
        result = self.run_cli(
            "prepare_api_generation_batch.py", "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root), "--split", "holdout",
            "--source-calibration-root", str(self.source_root),
            "--output", str(output),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires --freeze-manifest", result.stderr)
        self.assertFalse(output.exists())

    def test_invalid_holdout_freeze_manifest_fails(self) -> None:
        freeze = valid_freeze_manifest(self.package_dir, self.prompt_file, self.parameters_file)
        freeze["prompt_frozen"] = False
        freeze["routing_rules_frozen"] = False
        path = self.base / "invalid_freeze.json"; write_json(path, freeze)
        output = self.base / "invalid_holdout.jsonl"
        result = self.run_cli(
            "prepare_api_generation_batch.py", "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root), "--split", "holdout",
            "--source-calibration-root", str(self.source_root),
            "--freeze-manifest", str(path), "--prompt-file", str(self.prompt_file),
            "--generation-parameters-json", str(self.parameters_file), "--output", str(output),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("prompt_frozen", result.stderr)
        self.assertIn("routing_rules_frozen", result.stderr)
        self.assertFalse(output.exists())

    def test_holdout_source_identity_mismatch_fails(self) -> None:
        freeze = valid_freeze_manifest(self.package_dir, self.prompt_file, self.parameters_file)
        freeze["source_calibration_manifest_sha256"] = "0" * 64
        path = self.base / "wrong_source_freeze.json"; write_json(path, freeze)
        result = self.run_cli(
            "prepare_api_generation_batch.py", "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root), "--split", "holdout",
            "--source-calibration-root", str(self.source_root),
            "--freeze-manifest", str(path), "--prompt-file", str(self.prompt_file),
            "--generation-parameters-json", str(self.parameters_file),
            "--output", str(self.base / "wrong_source/wrong_source.jsonl"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source_calibration_manifest_sha256", result.stderr)

    def test_valid_holdout_export_is_sealed_and_label_free(self) -> None:
        freeze_path = self.base / "valid_freeze.json"
        write_json(freeze_path, valid_freeze_manifest(
            self.package_dir, self.prompt_file, self.parameters_file,
        ))
        output = self.base / "valid_release/holdout.jsonl"
        result = self.run_cli(
            "prepare_api_generation_batch.py", "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root), "--split", "holdout",
            "--source-calibration-root", str(self.source_root),
            "--freeze-manifest", str(freeze_path), "--prompt-file", str(self.prompt_file),
            "--generation-parameters-json", str(self.parameters_file), "--output", str(output),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = read_jsonl(output)
        self.assertEqual(len(rows), 12)
        forbidden = {
            "split", "answerability_status", "answerability_reasons", "abstention_expected",
            "automatic_case_risk_tier", "automatic_case_risk_reasons", "human_route", "machine_route",
        }
        self.assertTrue(all(not (set(row) & forbidden) for row in rows))

    def test_generation_export_refuses_overwrite(self) -> None:
        output = self.base / "existing_batch.jsonl"
        output.write_text("existing", encoding="utf-8")
        result = self.run_cli(
            "prepare_api_generation_batch.py", "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root),
            "--source-calibration-root", str(self.source_root), "--output", str(output),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_text(encoding="utf-8"), "existing")

    def test_unknown_case_import_rejected(self) -> None:
        case = read_jsonl(self.package_dir / "cases/e2e_case_frame.jsonl")[0]
        output = make_api_output_templates([case])[0]
        output["source_case_id"] = "EC16_UNKNOWN"
        source = self.base / "unknown.jsonl"; write_jsonl(source, [output])
        result = self.run_cli(
            "import_api_outputs.py", "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root), "--input-jsonl", str(source),
            "--output-jsonl", str(self.base / "unknown_out.jsonl"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown_case", result.stderr)
        self.assertFalse((self.base / "unknown_out.jsonl").exists())

    def test_duplicate_api_output_rejected(self) -> None:
        case = read_jsonl(self.package_dir / "cases/e2e_case_frame.jsonl")[0]
        output = make_api_output_templates([case])[0]
        output.update({
            "answer_status": "failed", "generation_status": "failed",
            "limitations": ["fixture generation failure"],
        })
        source = self.base / "duplicate.jsonl"; write_jsonl(source, [output, output])
        result = self.run_cli(
            "import_api_outputs.py", "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root), "--input-jsonl", str(source),
            "--output-jsonl", str(self.base / "duplicate_out.jsonl"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate_api_output", result.stderr)
        self.assertFalse((self.base / "duplicate_out.jsonl").exists())

    def test_judge_import_failure_is_atomic(self) -> None:
        template = read_jsonl(self.package_dir / "cases/machine_judgment_template.jsonl")[0]
        row = deepcopy(template)
        row.update({"judge_id": "fixture-judge", "judgment_status": "completed", "judge_call_performed": True})
        for name in JUDGE_DIMENSIONS:
            row["dimensions"][name].update({
                "score": 0 if name == "unsupported_claim_count" else 0.8,
                "verdict": "pass", "confidence": 0.8, "rationale": "fixture",
                "evidence": [], "judge_model": "fixture", "judge_prompt_version": "v1",
            })
        row["dimensions"]["answer_correctness"]["evidence"] = [{
            "source_span_ids": ["CR15_OUTSIDE"], "evidence_link_ids": [], "claim_ids": [],
        }]
        source = self.base / "invalid_judge.jsonl"; write_jsonl(source, [row])
        output = self.base / "invalid_judge_out.jsonl"
        result = self.run_cli(
            "import_machine_judgments.py", "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root), "--input-jsonl", str(source),
            "--source-calibration-root", str(self.source_root),
            "--output-jsonl", str(output),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside_span_allowlist", result.stderr)
        self.assertFalse(output.exists())

    def test_empty_summary_cli(self) -> None:
        result = self.run_cli(
            "summarize_e2e_evaluation.py", "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not_available", result.stdout)

    def test_build_contains_no_real_network_call(self) -> None:
        with mock.patch("socket.create_connection", side_effect=AssertionError("network forbidden")):
            result = build_selective_eval_package(
                source_calibration_run_name=self.source_run_name, source_calibration_root=self.source_root,
                selective_eval_run_name="no_network", selective_eval_root=self.eval_root,
                clean=True, validate_source_package=False,
            )
        self.assertEqual(result["result"], "PASS")


if __name__ == "__main__":
    unittest.main()
