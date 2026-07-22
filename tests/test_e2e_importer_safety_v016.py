from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from enh3bench.calibration_package import tree_hash
from enh3bench.e2e_eval_metrics import summarize_e2e
from enh3bench.e2e_eval_package import build_selective_eval_package
from enh3bench.e2e_eval_schema import write_json, write_jsonl
from enh3bench.e2e_eval_validation import validate_selective_eval_package
from tests.selective_eval_test_helpers import (
    create_source_calibration_fixture,
    valid_api_outputs,
    valid_machine_judgments,
)


ROOT = Path(__file__).resolve().parents[1]


class ImporterSafetyV016Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source_root = self.base / "data/calibration"
        self.eval_root = self.base / "data/selective_eval"
        create_source_calibration_fixture(self.source_root)
        build_selective_eval_package(
            source_calibration_run_name="calibration_fixture", source_calibration_root=self.source_root,
            selective_eval_run_name="eval", selective_eval_root=self.eval_root,
            clean=True, validate_source_package=False,
        )
        self.package_dir = self.eval_root / "eval"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, script: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script), *args], cwd=ROOT,
            text=True, capture_output=True, check=False,
        )

    def api_args(self, input_path: Path) -> list[str]:
        return [
            "--selective-eval-run-name", "eval", "--selective-eval-root", str(self.eval_root),
            "--source-calibration-root", str(self.source_root), "--input-jsonl", str(input_path),
        ]

    def test_api_package_import_post_validation_passes(self) -> None:
        source = self.base / "outputs.jsonl"
        write_jsonl(source, valid_api_outputs(self.package_dir, 2))
        result = self.run_cli("import_api_outputs.py", *self.api_args(source))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("import_mode: package", result.stdout)
        validation = validate_selective_eval_package(
            selective_eval_run_name="eval", selective_eval_root=self.eval_root,
            source_calibration_root=self.source_root, check_source_package=False,
        )
        self.assertEqual(validation["result"], "PASS", validation["errors"])

    def test_api_import_post_validation_failure_rolls_back(self) -> None:
        stale = summarize_e2e(self.package_dir)
        stale["case_count"] = 47
        write_json(self.package_dir / "reports/e2e_metrics_summary.json", stale)
        before = tree_hash(self.package_dir)
        source = self.base / "outputs.jsonl"
        write_jsonl(source, valid_api_outputs(self.package_dir, 1))
        result = self.run_cli("import_api_outputs.py", *self.api_args(source))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("post-write package validation failed", result.stderr)
        self.assertFalse((self.package_dir / "cases/api_outputs.jsonl").exists())
        self.assertEqual(tree_hash(self.package_dir), before)

    def test_api_export_only_does_not_modify_package(self) -> None:
        source = self.base / "outputs.jsonl"; write_jsonl(source, valid_api_outputs(self.package_dir, 1))
        output = self.base / "validated_export.jsonl"
        before = tree_hash(self.package_dir)
        result = self.run_cli(
            "import_api_outputs.py", *self.api_args(source), "--export-only", "--output-jsonl", str(output),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("import_mode: export_only", result.stdout)
        self.assertTrue(output.is_file())
        self.assertFalse((self.package_dir / "cases/api_outputs.jsonl").exists())
        self.assertEqual(tree_hash(self.package_dir), before)

    def test_api_arbitrary_output_without_export_only_fails(self) -> None:
        source = self.base / "outputs.jsonl"; write_jsonl(source, valid_api_outputs(self.package_dir, 1))
        output = self.base / "arbitrary.jsonl"
        result = self.run_cli(
            "import_api_outputs.py", *self.api_args(source), "--output-jsonl", str(output),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("use --export-only", result.stderr)
        self.assertFalse(output.exists())

    def test_api_existing_target_is_not_overwritten(self) -> None:
        target = self.package_dir / "cases/api_outputs.jsonl"
        target.write_text("existing\n", encoding="utf-8")
        source = self.base / "outputs.jsonl"; write_jsonl(source, valid_api_outputs(self.package_dir, 1))
        result = self.run_cli("import_api_outputs.py", *self.api_args(source))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(encoding="utf-8"), "existing\n")

    def test_failed_api_input_does_not_change_package_tree(self) -> None:
        rows = valid_api_outputs(self.package_dir, 1); rows[0]["source_case_id"] = "EC16_UNKNOWN"
        source = self.base / "invalid.jsonl"; write_jsonl(source, rows)
        before = tree_hash(self.package_dir)
        result = self.run_cli("import_api_outputs.py", *self.api_args(source))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(tree_hash(self.package_dir), before)

    def prepare_api_package(self) -> None:
        write_jsonl(self.package_dir / "cases/api_outputs.jsonl", valid_api_outputs(self.package_dir))

    def judgment_args(self, input_path: Path) -> list[str]:
        return [
            "--selective-eval-run-name", "eval", "--selective-eval-root", str(self.eval_root),
            "--source-calibration-root", str(self.source_root), "--input-jsonl", str(input_path),
        ]

    def test_judgment_package_import_post_validation_passes(self) -> None:
        self.prepare_api_package()
        source = self.base / "judgments.jsonl"
        write_jsonl(source, valid_machine_judgments(self.package_dir, case_count=1, observations_per_case=1))
        result = self.run_cli("import_machine_judgments.py", *self.judgment_args(source))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("import_mode: package", result.stdout)

    def test_judgment_post_validation_failure_rolls_back(self) -> None:
        self.prepare_api_package()
        write_json(self.package_dir / "reports/e2e_metrics_summary.json", summarize_e2e(self.package_dir))
        before = tree_hash(self.package_dir)
        source = self.base / "judgments.jsonl"
        write_jsonl(source, valid_machine_judgments(self.package_dir, case_count=1, observations_per_case=1))
        result = self.run_cli("import_machine_judgments.py", *self.judgment_args(source))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("post-write package validation failed", result.stderr)
        self.assertFalse((self.package_dir / "cases/machine_judgments.jsonl").exists())
        self.assertEqual(tree_hash(self.package_dir), before)


if __name__ == "__main__":
    unittest.main()
