from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from enh3bench.e2e_case_generation import make_api_output_templates
from enh3bench.e2e_eval_schema import JUDGE_DIMENSIONS
from enh3bench.e2e_eval_package import build_selective_eval_package
from enh3bench.e2e_eval_schema import read_jsonl, write_jsonl
from tests.selective_eval_test_helpers import create_source_calibration_fixture


ROOT = Path(__file__).resolve().parents[1]


class E2EEvalCliV016Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.source_root = cls.base / "data/calibration"
        cls.eval_root = cls.base / "data/selective_eval"
        create_source_calibration_fixture(cls.source_root)
        build_selective_eval_package(
            source_calibration_run_name="calibration_fixture", source_calibration_root=cls.source_root,
            selective_eval_run_name="eval", selective_eval_root=cls.eval_root,
            clean=True, validate_source_package=False,
        )
        cls.package_dir = cls.eval_root / "eval"
        imported = make_api_output_templates(read_jsonl(cls.package_dir / "cases/e2e_case_frame.jsonl"))
        for row in imported:
            row.update({"answer_status": "failed", "generation_status": "failed"})
        write_jsonl(cls.package_dir / "cases/api_outputs.jsonl", imported)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def run_cli(self, script: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script), *args], cwd=ROOT,
            text=True, capture_output=True, check=False,
        )

    def test_build_dry_run_writes_nothing(self) -> None:
        target = "dry_run_target"
        result = self.run_cli(
            "build_selective_eval_package.py", "--source-calibration-run-name", "calibration_fixture",
            "--source-calibration-root", str(self.source_root), "--selective-eval-run-name", target,
            "--selective-eval-root", str(self.eval_root), "--dry-run",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.eval_root / target).exists())

    def test_prepare_batch_exports_without_api(self) -> None:
        output = self.base / "exported_batch.jsonl"
        result = self.run_cli(
            "prepare_api_generation_batch.py", "--selective-eval-run-name", "eval",
            "--selective-eval-root", str(self.eval_root), "--output", str(output),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("network_calls: 0", result.stdout)
        self.assertEqual(len(read_jsonl(output)), 48)

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
        output.update({"answer_status": "failed", "generation_status": "failed"})
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
                source_calibration_run_name="calibration_fixture", source_calibration_root=self.source_root,
                selective_eval_run_name="no_network", selective_eval_root=self.eval_root,
                clean=True, validate_source_package=False,
            )
        self.assertEqual(result["result"], "PASS")


if __name__ == "__main__":
    unittest.main()
