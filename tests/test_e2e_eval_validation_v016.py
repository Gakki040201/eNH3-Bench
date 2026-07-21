from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from enh3bench.calibration_package import tree_hash
from enh3bench.e2e_eval_package import build_selective_eval_package
from enh3bench.e2e_eval_schema import normalized_hash, read_json, read_jsonl, write_jsonl
from enh3bench.e2e_eval_validation import REQUIRED_FILES, validate_selective_eval_package
from tests.selective_eval_test_helpers import create_source_calibration_fixture


class E2EEvalValidationV016Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.source_root = cls.base / "data/calibration"
        cls.eval_root = cls.base / "data/selective_eval"
        create_source_calibration_fixture(cls.source_root)
        build_selective_eval_package(
            source_calibration_run_name="calibration_fixture", source_calibration_root=cls.source_root,
            selective_eval_run_name="eval_fixture", selective_eval_root=cls.eval_root,
            clean=True, validate_source_package=False,
        )
        cls.package_dir = cls.eval_root / "eval_fixture"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def validate(self) -> dict[str, object]:
        return validate_selective_eval_package(
            selective_eval_run_name="eval_fixture", selective_eval_root=self.eval_root,
            source_calibration_root=self.source_root, check_source_package=False,
        )

    def test_package_passes_and_inventory_is_exact(self) -> None:
        result = self.validate()
        self.assertEqual(result["result"], "PASS", result["errors"])
        actual = {path.relative_to(self.package_dir).as_posix() for path in self.package_dir.rglob("*") if path.is_file()}
        self.assertEqual(actual, set(REQUIRED_FILES))

    def test_required_counts_and_blank_safety(self) -> None:
        counts = self.validate()["counts"]
        self.assertEqual(counts["risk_ledger_items"], 520)
        self.assertEqual(counts["anchors"], 24)
        self.assertEqual(counts["e2e_cases"], 48)
        self.assertEqual(counts["human_labels_filled"], 0)
        self.assertEqual(counts["api_outputs_filled"], 0)
        self.assertEqual(counts["machine_judgments_filled"], 0)

    def test_third_reviewer_is_rejected(self) -> None:
        path = self.package_dir / "review/e2e_human_review.csv"
        original = path.read_bytes()
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle); header = list(reader.fieldnames or []); rows = list(reader)
            rows[0]["reviewer_id"] = "R3"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
            result = self.validate()
            self.assertEqual(result["result"], "FAIL")
            self.assertTrue(any("third_reviewer" in error for error in result["errors"]))
        finally:
            path.write_bytes(original)

    def test_nonblank_api_output_template_is_rejected(self) -> None:
        path = self.package_dir / "cases/api_output_template.jsonl"
        original = path.read_bytes()
        try:
            rows = read_jsonl(path); rows[0]["answer_text"] = "fabricated"; write_jsonl(path, rows)
            result = self.validate()
            self.assertEqual(result["counts"]["api_outputs_filled"], 1)
            self.assertEqual(result["result"], "FAIL")
        finally:
            path.write_bytes(original)

    def test_risk_recomputation_detects_change(self) -> None:
        path = self.package_dir / "risk/full_item_risk_ledger.jsonl"
        original = path.read_bytes()
        try:
            rows = read_jsonl(path); rows[0]["risk_score"] = 0; write_jsonl(path, rows)
            result = self.validate()
            self.assertTrue(any("risk_recomputation_mismatch" in error for error in result["errors"]))
        finally:
            path.write_bytes(original)

    def test_unexpected_inventory_file_is_rejected(self) -> None:
        path = self.package_dir / "unexpected.txt"
        try:
            path.write_text("unexpected", encoding="utf-8")
            result = self.validate()
            self.assertIn("unexpected_file:unexpected.txt", result["errors"])
        finally:
            path.unlink(missing_ok=True)

    def test_failed_manifest_behavior(self) -> None:
        with self.assertRaises(ValueError):
            build_selective_eval_package(
                source_calibration_run_name="calibration_fixture", source_calibration_root=self.source_root,
                selective_eval_run_name="failed_fixture", selective_eval_root=self.eval_root,
                anchor_count=23, clean=True, validate_source_package=False,
            )
        manifest = read_json(self.eval_root / "failed_fixture/manifests/selective_eval_manifest.json")
        self.assertEqual(manifest["status"], "failed")
        self.assertTrue(manifest["errors"])

    def test_reproducibility_and_source_mutation_guards(self) -> None:
        before = tree_hash(self.source_root / "calibration_fixture")
        results = []
        for name in ("repro_a", "repro_b"):
            results.append(build_selective_eval_package(
                source_calibration_run_name="calibration_fixture", source_calibration_root=self.source_root,
                selective_eval_run_name=name, selective_eval_root=self.eval_root,
                clean=True, validate_source_package=False,
            ))
        self.assertEqual(results[0]["normalized_hashes"], results[1]["normalized_hashes"])
        self.assertEqual(tree_hash(self.source_root / "calibration_fixture"), before)
        self.assertEqual(tree_hash(self.base / "data/cleanroom"), hashlib_empty_tree())
        self.assertEqual(tree_hash(self.base / "data/gold"), hashlib_empty_tree())


def hashlib_empty_tree() -> str:
    import hashlib
    return hashlib.sha256(b"").hexdigest()


if __name__ == "__main__":
    unittest.main()
