from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from enh3bench.e2e_case_generation import (
    E2E_REVIEW_COLUMNS,
    make_api_output_templates,
    make_machine_judgment_templates,
)
from enh3bench.e2e_eval_package import build_selective_eval_package
from enh3bench.e2e_eval_schema import (
    canonical_json,
    read_json,
    read_csv,
    read_jsonl,
    sha256_bytes,
    sha256_file,
    write_json,
    write_csv,
    write_jsonl,
)
from enh3bench.e2e_holdout import validate_development_freeze_outputs, write_holdout_release
from scripts import create_holdout_freeze_manifest, prepare_api_generation_batch
from tests.selective_eval_test_helpers import create_source_calibration_fixture

class E2EHoldoutFreezeV016Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source_root = self.base / "data/calibration"
        self.source_run_name = "calibration_fixture"
        create_source_calibration_fixture(self.source_root, run_name=self.source_run_name)
        self.eval_root = self.base / "data/selective_eval"
        build_selective_eval_package(
            source_calibration_run_name=self.source_run_name,
            source_calibration_root=self.source_root,
            selective_eval_run_name="eval", selective_eval_root=self.eval_root,
            clean=True, validate_source_package=False,
        )
        self.package_dir = self.eval_root / "eval"
        self.prompt = self.base / "prompt.txt"
        self.prompt.write_text("frozen prompt v1\n", encoding="utf-8")
        self.parameters = self.base / "parameters.json"
        write_json(self.parameters, {"temperature": 0, "max_tokens": 512})
        self.freeze = self.base / "freeze.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, script: str, *args: str) -> subprocess.CompletedProcess[str]:
        modules = {
            "create_holdout_freeze_manifest.py": create_holdout_freeze_manifest,
            "prepare_api_generation_batch.py": prepare_api_generation_batch,
        }
        module = modules[script]
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

    def write_development_outputs(self, count: int = 36) -> None:
        cases = [
            case for case in read_jsonl(self.package_dir / "cases/e2e_case_frame.jsonl")
            if case["split"] == "development"
        ][:count]
        rows = make_api_output_templates(cases)
        for row in rows:
            row.update({
                "answer_status": "abstained", "generation_status": "completed",
                "api_call_performed": True, "generation_model": "fixture-model-family",
                "generation_prompt_version": "fixture-prompt-v1",
                "generation_parameters": {"temperature": 0, "max_tokens": 512},
                "abstention_reason": "fixture bounded evidence insufficient",
            })
        write_jsonl(self.package_dir / "cases/api_outputs.jsonl", rows)

    def cases(self) -> list[dict]:
        return read_jsonl(self.package_dir / "cases/e2e_case_frame.jsonl")

    def output_gate_errors(self, rows: list[dict] | None = None) -> list[str]:
        if rows is None:
            rows = read_jsonl(self.package_dir / "cases/api_outputs.jsonl")
        errors, _ = validate_development_freeze_outputs(
            rows, self.cases(), generation_model_family="fixture-model-family",
            prompt_version="fixture-prompt-v1",
            generation_parameters={"temperature": 0, "max_tokens": 512},
        )
        return errors

    def freeze_args(self, output: Path | None = None) -> list[str]:
        return [
            "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root),
            "--source-calibration-root", str(self.source_root),
            "--prompt-file", str(self.prompt),
            "--generation-parameters-json", str(self.parameters),
            "--generation-model-family", "fixture-model-family",
            "--prompt-version", "fixture-prompt-v1",
            "--output", str(output or self.freeze),
        ]

    def create_freeze(self, output: Path | None = None) -> subprocess.CompletedProcess[str]:
        return self.run_cli("create_holdout_freeze_manifest.py", *self.freeze_args(output))

    def export_args(self, output: Path, freeze: Path | None = None) -> list[str]:
        return [
            "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root),
            "--source-calibration-root", str(self.source_root),
            "--split", "holdout", "--freeze-manifest", str(freeze or self.freeze),
            "--prompt-file", str(self.prompt),
            "--generation-parameters-json", str(self.parameters),
            "--output", str(output),
        ]

    def prepare_valid_freeze(self) -> None:
        self.write_development_outputs()
        result = self.create_freeze()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_freeze_creation_requires_36_development_outputs(self) -> None:
        result = self.create_freeze()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("api_outputs.jsonl", result.stderr)

    def test_freeze_creation_rejects_35_development_outputs(self) -> None:
        self.write_development_outputs(35)
        result = self.create_freeze()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("freeze_requires_development_only_outputs", result.stderr)
        self.assertFalse(self.freeze.exists())

    def test_development_plus_holdout_output_is_rejected(self) -> None:
        self.write_development_outputs()
        rows = read_jsonl(self.package_dir / "cases/api_outputs.jsonl")
        holdout = next(case for case in self.cases() if case["split"] == "holdout")
        extra = make_api_output_templates([holdout])[0]
        extra.update({
            "answer_status": "abstained", "generation_status": "completed",
            "api_call_performed": True, "generation_model": "fixture-model-family",
            "generation_prompt_version": "fixture-prompt-v1",
            "generation_parameters": {"temperature": 0, "max_tokens": 512},
            "abstention_reason": "fixture bounded evidence insufficient",
        })
        errors = self.output_gate_errors([*rows, extra])
        self.assertTrue(any("freeze_holdout_output_already_exists" in error for error in errors))
        self.assertTrue(any("freeze_requires_development_only_outputs" in error for error in errors))

    def test_all_48_outputs_are_rejected(self) -> None:
        cases = self.cases()
        rows = make_api_output_templates(cases)
        for row in rows:
            row.update({
                "answer_status": "abstained", "generation_status": "completed",
                "api_call_performed": True, "generation_model": "fixture-model-family",
                "generation_prompt_version": "fixture-prompt-v1",
                "generation_parameters": {"temperature": 0, "max_tokens": 512},
                "abstention_reason": "fixture bounded evidence insufficient",
            })
        errors = self.output_gate_errors(rows)
        self.assertTrue(any("freeze_holdout_output_already_exists" in error for error in errors))

    def test_failed_development_outputs_do_not_unlock_holdout(self) -> None:
        self.write_development_outputs()
        rows = read_jsonl(self.package_dir / "cases/api_outputs.jsonl")
        for row in rows:
            row.update({
                "answer_status": "failed", "generation_status": "failed",
                "api_call_performed": False, "answer_text": "", "claims": [], "citations": [],
                "limitations": ["fixture generation failure"],
            })
        errors = self.output_gate_errors(rows)
        self.assertTrue(any("freeze_failed_development_output:36" in error for error in errors))

    def test_one_failed_development_output_is_rejected(self) -> None:
        self.write_development_outputs()
        rows = read_jsonl(self.package_dir / "cases/api_outputs.jsonl")
        rows[0].update({
            "answer_status": "failed", "generation_status": "failed",
            "api_call_performed": False, "abstention_reason": "fixture failure",
        })
        errors = self.output_gate_errors(rows)
        self.assertTrue(any("freeze_failed_development_output:1" in error for error in errors))

    def test_incomplete_generation_provenance_is_rejected(self) -> None:
        mutations = (
            ("api_call_performed", False),
            ("generation_model", ""),
            ("generation_prompt_version", ""),
            ("generation_parameters", {}),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                self.write_development_outputs()
                rows = read_jsonl(self.package_dir / "cases/api_outputs.jsonl")
                rows[0][field] = value
                errors = self.output_gate_errors(rows)
                self.assertIn("freeze_incomplete_generation_provenance", errors)

    def test_declared_and_heterogeneous_provenance_mismatches_are_rejected(self) -> None:
        self.write_development_outputs()
        rows = read_jsonl(self.package_dir / "cases/api_outputs.jsonl")
        rows[0]["generation_model"] = "different-model"
        rows[1]["generation_prompt_version"] = "different-prompt"
        rows[2]["generation_parameters"] = {"temperature": 0.5, "max_tokens": 512}
        errors = self.output_gate_errors(rows)
        self.assertTrue(any("freeze_development_model_mismatch" in error for error in errors))
        self.assertTrue(any("freeze_development_prompt_mismatch" in error for error in errors))
        self.assertTrue(any("freeze_development_parameters_mismatch" in error for error in errors))
        self.assertIn("freeze_heterogeneous_development_provenance", errors)

    def test_cli_declarations_must_match_development_outputs(self) -> None:
        self.write_development_outputs()
        rows = read_jsonl(self.package_dir / "cases/api_outputs.jsonl")
        scenarios = (
            ("wrong-model", "fixture-prompt-v1", {"temperature": 0, "max_tokens": 512}, "model_mismatch"),
            ("fixture-model-family", "wrong-prompt", {"temperature": 0, "max_tokens": 512}, "prompt_mismatch"),
            ("fixture-model-family", "fixture-prompt-v1", {"temperature": 1}, "parameters_mismatch"),
        )
        for model, prompt, parameters, fragment in scenarios:
            with self.subTest(fragment=fragment):
                errors, _ = validate_development_freeze_outputs(
                    rows, self.cases(), generation_model_family=model,
                    prompt_version=prompt, generation_parameters=parameters,
                )
                self.assertTrue(any(fragment in error for error in errors), errors)

    def test_freeze_hashes_are_computed_from_actual_files(self) -> None:
        self.prepare_valid_freeze()
        freeze = read_json(self.freeze)
        self.assertEqual(freeze["development_api_output_count"], 36)
        self.assertEqual(freeze["development_generation_model_family"], "fixture-model-family")
        self.assertEqual(freeze["development_prompt_version"], "fixture-prompt-v1")
        self.assertTrue(freeze["development_generation_provenance_consistent"])
        self.assertEqual(freeze["prompt_sha256"], sha256_file(self.prompt))
        parameters = read_json(self.parameters)
        self.assertEqual(
            freeze["generation_parameters_sha256"],
            sha256_bytes(canonical_json(parameters).encode("utf-8")),
        )
        self.assertEqual(
            freeze["development_generation_parameters_sha256"],
            freeze["generation_parameters_sha256"],
        )
        self.assertEqual(
            freeze["package_manifest_sha256"],
            sha256_file(self.package_dir / "manifests/selective_eval_manifest.json"),
        )

    def assert_freeze_invalidated(self) -> None:
        output = self.base / "release/holdout.jsonl"
        result = self.run_cli("prepare_api_generation_batch.py", *self.export_args(output))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        self.assertFalse((output.parent / "holdout_release_manifest.json").exists())

    def test_prompt_change_invalidates_freeze(self) -> None:
        self.prepare_valid_freeze()
        self.prompt.write_text("changed prompt\n", encoding="utf-8")
        self.assert_freeze_invalidated()

    def test_parameters_change_invalidates_freeze(self) -> None:
        self.prepare_valid_freeze()
        write_json(self.parameters, {"temperature": 0.1, "max_tokens": 512})
        self.assert_freeze_invalidated()

    def test_development_output_change_invalidates_freeze(self) -> None:
        self.prepare_valid_freeze()
        path = self.package_dir / "cases/api_outputs.jsonl"
        rows = read_jsonl(path)
        rows[0]["generation_model"] = "changed-after-freeze"
        write_jsonl(path, rows)
        self.assert_freeze_invalidated()

    def test_case_frame_change_invalidates_freeze(self) -> None:
        self.prepare_valid_freeze()
        path = self.package_dir / "cases/e2e_case_frame.jsonl"
        rows = read_jsonl(path)
        rows[0]["question"] += " changed"
        write_jsonl(path, rows)
        self.assert_freeze_invalidated()

    def test_generation_batch_change_invalidates_freeze(self) -> None:
        self.prepare_valid_freeze()
        path = self.package_dir / "cases/api_generation_batch.jsonl"
        rows = read_jsonl(path)
        rows[0]["question"] += " changed"
        write_jsonl(path, rows)
        self.assert_freeze_invalidated()

    def test_package_validation_failure_prevents_any_export(self) -> None:
        path = self.package_dir / "cases/api_generation_batch.jsonl"
        rows = read_jsonl(path)
        rows[0]["answerability_status"] = "answerable"
        write_jsonl(path, rows)
        output = self.base / "development.jsonl"
        result = self.run_cli(
            "prepare_api_generation_batch.py", "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root),
            "--source-calibration-root", str(self.source_root), "--output", str(output),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("package validation failed", result.stderr)
        self.assertFalse(output.exists())

    def test_valid_freeze_releases_exactly_12_label_free_rows(self) -> None:
        self.prepare_valid_freeze()
        output = self.base / "release/holdout.jsonl"
        result = self.run_cli("prepare_api_generation_batch.py", *self.export_args(output))
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = read_jsonl(output)
        self.assertEqual(len(rows), 12)
        forbidden = {
            "split", "answerability_status", "answerability_reasons", "abstention_expected",
            "automatic_case_risk_score", "automatic_case_risk_tier",
            "automatic_case_risk_reasons", "human_route", "machine_route",
        }
        self.assertTrue(all(not (set(row) & forbidden) for row in rows))
        release = read_json(output.parent / "holdout_release_manifest.json")
        self.assertEqual(release["freeze_manifest_sha256"], sha256_file(self.freeze))
        self.assertEqual(release["exported_holdout_batch_sha256"], sha256_file(output))
        self.assertEqual(release["network_calls_performed"], 0)

    def test_holdout_output_added_after_freeze_blocks_release(self) -> None:
        self.prepare_valid_freeze()
        path = self.package_dir / "cases/api_outputs.jsonl"
        rows = read_jsonl(path)
        holdout = next(case for case in self.cases() if case["split"] == "holdout")
        extra = make_api_output_templates([holdout])[0]
        extra.update({
            "answer_status": "abstained", "generation_status": "completed",
            "api_call_performed": True, "generation_model": "fixture-model-family",
            "generation_prompt_version": "fixture-prompt-v1",
            "generation_parameters": {"temperature": 0, "max_tokens": 512},
            "abstention_reason": "fixture bounded evidence insufficient",
        })
        write_jsonl(path, [*rows, extra])
        output = self.base / "exposed_output/holdout.jsonl"
        result = self.run_cli("prepare_api_generation_batch.py", *self.export_args(output))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("freeze_holdout_output_already_exists", result.stderr)
        self.assertFalse(output.exists())

    def test_holdout_judgment_before_release_is_rejected(self) -> None:
        self.prepare_valid_freeze()
        holdout = next(case for case in self.cases() if case["split"] == "holdout")
        judgment = make_machine_judgment_templates([holdout])[0]
        write_jsonl(self.package_dir / "cases/machine_judgments.jsonl", [judgment])
        output = self.base / "exposed_judgment/holdout.jsonl"
        result = self.run_cli("prepare_api_generation_batch.py", *self.export_args(output))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("holdout_machine_judgment_already_exists", result.stderr)
        self.assertFalse(output.exists())

    def test_holdout_completed_review_before_release_is_rejected(self) -> None:
        self.prepare_valid_freeze()
        path = self.package_dir / "review/e2e_human_review.csv"
        rows = read_csv(path)
        row = next(row for row in rows if row["split"] == "holdout")
        row["review_status"] = "completed"
        write_csv(path, rows, E2E_REVIEW_COLUMNS)
        output = self.base / "exposed_review/holdout.jsonl"
        result = self.run_cli("prepare_api_generation_batch.py", *self.export_args(output))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("holdout_completed_review_already_exists", result.stderr)
        self.assertFalse(output.exists())

    def test_complete_source_validation_failure_prevents_freeze_and_release(self) -> None:
        self.write_development_outputs()
        missing_source = self.base / "missing_calibration"
        freeze_args = self.freeze_args(self.base / "source_failure_freeze.json")
        freeze_args[freeze_args.index("--source-calibration-root") + 1] = str(missing_source)
        freeze_result = self.run_cli("create_holdout_freeze_manifest.py", *freeze_args)
        self.assertNotEqual(freeze_result.returncode, 0)
        self.assertIn("package validation failed", freeze_result.stderr)

        self.prepare_valid_freeze()
        output = self.base / "source_failure_release/holdout.jsonl"
        release_args = self.export_args(output)
        release_args[release_args.index("--source-calibration-root") + 1] = str(missing_source)
        release_result = self.run_cli("prepare_api_generation_batch.py", *release_args)
        self.assertNotEqual(release_result.returncode, 0)
        self.assertIn("package validation failed", release_result.stderr)
        self.assertFalse(output.exists())

    def test_freeze_and_release_outputs_inside_runtime_are_rejected(self) -> None:
        self.write_development_outputs()
        inside_freeze = self.package_dir / "freeze.json"
        freeze_result = self.create_freeze(inside_freeze)
        self.assertNotEqual(freeze_result.returncode, 0)
        self.assertIn("freeze_manifest_output_inside_runtime", freeze_result.stderr)
        self.assertFalse(inside_freeze.exists())

        self.prepare_valid_freeze()
        inside_release = self.package_dir / "holdout.jsonl"
        release_result = self.run_cli(
            "prepare_api_generation_batch.py", *self.export_args(inside_release)
        )
        self.assertNotEqual(release_result.returncode, 0)
        self.assertIn("release_output_inside_runtime", release_result.stderr)
        self.assertFalse(inside_release.exists())

    def test_second_nonidentical_holdout_release_fails(self) -> None:
        self.prepare_valid_freeze()
        output = self.base / "release/holdout.jsonl"
        first = self.run_cli("prepare_api_generation_batch.py", *self.export_args(output))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.prompt.write_text("frozen prompt v2\n", encoding="utf-8")
        freeze_two = self.base / "freeze_two.json"
        second_freeze = self.create_freeze(freeze_two)
        self.assertEqual(second_freeze.returncode, 0, second_freeze.stderr)
        second = self.run_cli(
            "prepare_api_generation_batch.py", *self.export_args(output, freeze_two)
        )
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("differs", second.stderr)

    def test_identical_second_release_is_idempotent(self) -> None:
        self.prepare_valid_freeze()
        output = self.base / "release/holdout.jsonl"
        first = self.run_cli("prepare_api_generation_batch.py", *self.export_args(output))
        second = self.run_cli("prepare_api_generation_batch.py", *self.export_args(output))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("already_released", second.stdout)

    def test_failed_release_removes_both_partial_files(self) -> None:
        freeze = self.base / "fixture_freeze.json"
        write_json(freeze, {"fixture": True})
        output = self.base / "atomic/holdout.jsonl"
        rows = [{"case_id": "fixture"}]
        with mock.patch("enh3bench.e2e_holdout.write_json", side_effect=OSError("fixture failure")):
            with self.assertRaises(OSError):
                write_holdout_release(
                    output, rows, freeze_manifest=freeze, selective_eval_run_name="eval",
                )
        self.assertFalse(output.exists())
        self.assertFalse((output.parent / "holdout_release_manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
