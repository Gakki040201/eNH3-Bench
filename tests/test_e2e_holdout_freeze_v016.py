from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from enh3bench.e2e_case_generation import make_api_output_templates
from enh3bench.e2e_eval_package import build_selective_eval_package
from enh3bench.e2e_eval_schema import (
    canonical_json,
    read_json,
    read_jsonl,
    sha256_bytes,
    sha256_file,
    write_json,
    write_jsonl,
)
from enh3bench.e2e_holdout import write_holdout_release
from tests.selective_eval_test_helpers import create_source_calibration_fixture


ROOT = Path(__file__).resolve().parents[1]


class E2EHoldoutFreezeV016Tests(unittest.TestCase):
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
        self.prompt = self.base / "prompt.txt"
        self.prompt.write_text("frozen prompt v1\n", encoding="utf-8")
        self.parameters = self.base / "parameters.json"
        write_json(self.parameters, {"temperature": 0, "max_tokens": 512})
        self.freeze = self.base / "freeze.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, script: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script), *args], cwd=ROOT,
            text=True, capture_output=True, check=False,
        )

    def write_development_outputs(self, count: int = 36) -> None:
        cases = [
            case for case in read_jsonl(self.package_dir / "cases/e2e_case_frame.jsonl")
            if case["split"] == "development"
        ][:count]
        rows = make_api_output_templates(cases)
        for row in rows:
            row.update({"answer_status": "failed", "generation_status": "failed"})
        write_jsonl(self.package_dir / "cases/api_outputs.jsonl", rows)

    def freeze_args(self, output: Path | None = None) -> list[str]:
        return [
            "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root),
            "--source-calibration-root", str(self.source_root),
            "--prompt-file", str(self.prompt),
            "--generation-parameters-json", str(self.parameters),
            "--generation-model-family", "fixture-family",
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
        self.assertIn("exactly 36", result.stderr)
        self.assertFalse(self.freeze.exists())

    def test_freeze_hashes_are_computed_from_actual_files(self) -> None:
        self.prepare_valid_freeze()
        freeze = read_json(self.freeze)
        self.assertEqual(freeze["development_api_output_count"], 36)
        self.assertEqual(freeze["prompt_sha256"], sha256_file(self.prompt))
        parameters = read_json(self.parameters)
        self.assertEqual(
            freeze["generation_parameters_sha256"],
            sha256_bytes(canonical_json(parameters).encode("utf-8")),
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
