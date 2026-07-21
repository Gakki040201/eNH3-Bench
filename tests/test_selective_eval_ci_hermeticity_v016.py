from __future__ import annotations

import inspect
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

from enh3bench.e2e_eval_package import build_selective_eval_package
from enh3bench.e2e_eval_schema import read_jsonl
from scripts import create_holdout_freeze_manifest, prepare_api_generation_batch
from tests.selective_eval_test_helpers import create_source_calibration_fixture


ROOT = Path(__file__).resolve().parents[1]


class _ValidationProbe(RuntimeError):
    pass


class SelectiveEvalCiHermeticityV016Tests(unittest.TestCase):
    def test_selective_cli_tests_do_not_reference_ignored_runtime(self) -> None:
        forbidden_run = "enrr_calibration_v016_round1_" + "20260719"
        forbidden_root = "ROOT / " + '"data/calibration"'
        for name in ("test_e2e_eval_cli_v016.py", "test_e2e_holdout_freeze_v016.py"):
            source = (ROOT / "tests" / name).read_text(encoding="utf-8")
            self.assertNotIn(forbidden_run, source)
            self.assertNotIn(forbidden_root, source)

    def test_synthetic_fixture_builds_in_empty_temporary_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source_root = base / "source"
            run_name = "calibration_fixture"
            create_source_calibration_fixture(source_root, run_name=run_name)
            eval_root = base / "selective"
            result = build_selective_eval_package(
                source_calibration_run_name=run_name,
                source_calibration_root=source_root,
                selective_eval_run_name="eval_fixture",
                selective_eval_root=eval_root,
                clean=True,
                validate_source_package=False,
            )
            self.assertEqual(result["result"], "PASS")
            self.assertEqual(
                len(read_jsonl(eval_root / "eval_fixture/cases/e2e_case_frame.jsonl")), 48
            )

    def test_synthetic_fixture_build_never_accesses_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source_root = base / "source"
            create_source_calibration_fixture(source_root, run_name="calibration_fixture")
            with mock.patch.object(
                socket, "create_connection", side_effect=AssertionError("network forbidden")
            ):
                result = build_selective_eval_package(
                    source_calibration_run_name="calibration_fixture",
                    source_calibration_root=source_root,
                    selective_eval_run_name="eval_fixture",
                    selective_eval_root=base / "selective",
                    clean=True,
                    validate_source_package=False,
                )
            self.assertEqual(result["result"], "PASS")

    def assert_cli_requests_full_source_validation(self, module: object, argv: list[str]) -> None:
        calls: list[dict[str, object]] = []

        def probe(**kwargs: object) -> dict:
            calls.append(kwargs)
            raise _ValidationProbe

        with mock.patch.object(module, "validate_selective_eval_package", side_effect=probe):
            with self.assertRaises(_ValidationProbe):
                module.main(argv)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0].get("check_source_package"), True)

    def test_freeze_cli_requests_full_source_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            self.assert_cli_requests_full_source_validation(
                create_holdout_freeze_manifest,
                [
                    "--selective-eval-run-name", "eval",
                    "--selective-eval-root", str(base / "selective"),
                    "--source-calibration-root", str(base / "source"),
                    "--prompt-file", str(base / "prompt.txt"),
                    "--generation-parameters-json", str(base / "parameters.json"),
                    "--generation-model-family", "fixture-model",
                    "--prompt-version", "fixture-prompt",
                    "--output", str(base / "freeze.json"),
                ],
            )

    def test_release_cli_requests_full_source_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            self.assert_cli_requests_full_source_validation(
                prepare_api_generation_batch,
                [
                    "--selective-eval-run-name", "eval",
                    "--selective-eval-root", str(base / "selective"),
                    "--source-calibration-root", str(base / "source"),
                    "--output", str(base / "development.jsonl"),
                ],
            )

    def test_production_clis_expose_no_source_validation_bypass(self) -> None:
        for module in (create_holdout_freeze_manifest, prepare_api_generation_batch):
            source = inspect.getsource(module)
            self.assertNotIn("skip-source-validation", source)
            self.assertNotIn("no-source-validation", source)
            self.assertNotIn("check_source_package=False", source)
            self.assertIn("check_source_package=True", source)


if __name__ == "__main__":
    unittest.main()
