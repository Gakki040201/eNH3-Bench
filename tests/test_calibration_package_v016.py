from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from tests.calibration_test_helpers import create_cleanroom_fixture
from enh3bench.calibration_package import (
    CalibrationPackageBuilder,
    normalized_file_hash,
    tree_hash,
)
from enh3bench.calibration_schema import (
    HUMAN_FIELDS_BY_TYPE,
    read_csv,
    read_json,
    read_jsonl,
    resolve_calibration_target,
)
from enh3bench.calibration_validation import validate_calibration_package


class CalibrationPackageV016Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.cleanroom_root = self.base / "cleanroom"
        self.calibration_root = self.base / "calibration"
        create_cleanroom_fixture(self.cleanroom_root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def builder(self, run_name: str = "calibration_fixture") -> CalibrationPackageBuilder:
        return CalibrationPackageBuilder(
            cleanroom_run_name="cleanroom_fixture", calibration_run_name=run_name,
            cleanroom_root=self.cleanroom_root, calibration_root=self.calibration_root,
            span_sample_size=30, paper_sample_size=10, link_sample_size=20, seed=16,
        )

    def test_package_has_exact_counts_and_passes_validation(self) -> None:
        manifest = self.builder().build(clean=True, emit=lambda _: None)
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["selected_sample_counts"], {"span": 30, "paper": 10, "document": 10, "link": 20})
        result = validate_calibration_package(
            calibration_run_name="calibration_fixture", calibration_root=self.calibration_root,
            cleanroom_root=self.cleanroom_root, require_blank_human_fields=True,
        )
        self.assertEqual(result["result"], "PASS", result["errors"])

    def test_paper_document_alignment(self) -> None:
        self.builder().build(clean=True, emit=lambda _: None)
        run = self.calibration_root / "calibration_fixture"
        papers = read_jsonl(run / "sampling/paper_sampling_frame.jsonl")
        documents = read_jsonl(run / "sampling/document_sampling_frame.jsonl")
        self.assertEqual(
            {(row["paper_id"], row["document_id"]) for row in papers},
            {(row["paper_id"], row["document_id"]) for row in documents},
        )

    def test_bounded_excerpt_limits_and_no_cross_paper_context(self) -> None:
        self.builder().build(clean=True, emit=lambda _: None)
        spans = read_jsonl(self.calibration_root / "calibration_fixture/sampling/span_sampling_frame.jsonl")
        for row in spans:
            self.assertLessEqual(len(row["target_excerpt"]), 700)
            self.assertLessEqual(len(row["previous_context_excerpt"]), 500)
            self.assertLessEqual(len(row["next_context_excerpt"]), 500)

    def test_generated_human_fields_are_blank(self) -> None:
        self.builder().build(clean=True, emit=lambda _: None)
        run = self.calibration_root / "calibration_fixture"
        for item_type, fields in HUMAN_FIELDS_BY_TYPE.items():
            rows = read_csv(run / f"review/{item_type}_review.csv")
            self.assertTrue(all(not row[field] for row in rows for field in fields))

    def test_source_and_gold_are_not_mutated(self) -> None:
        cleanroom_before = tree_hash(self.cleanroom_root / "cleanroom_fixture")
        gold_before = tree_hash(Path("data/gold"))
        self.builder().build(clean=True, emit=lambda _: None)
        self.assertEqual(cleanroom_before, tree_hash(self.cleanroom_root / "cleanroom_fixture"))
        self.assertEqual(gold_before, tree_hash(Path("data/gold")))

    def test_existing_package_overwrite_is_refused(self) -> None:
        self.builder().build(clean=True, emit=lambda _: None)
        with self.assertRaises(FileExistsError):
            self.builder().build(emit=lambda _: None)

    def test_clean_removes_only_exact_target_and_protects_sibling(self) -> None:
        self.builder().build(clean=True, emit=lambda _: None)
        sibling = self.calibration_root / "sibling"
        sibling.mkdir()
        (sibling / "keep.txt").write_text("keep", encoding="utf-8")
        self.builder().clean(emit=lambda _: None)
        self.assertFalse((self.calibration_root / "calibration_fixture").exists())
        self.assertEqual((sibling / "keep.txt").read_text(encoding="utf-8"), "keep")

    def test_clean_target_rejects_traversal_and_current_directory(self) -> None:
        with self.assertRaises(ValueError):
            resolve_calibration_target(self.calibration_root, "../escape")
        with self.assertRaises(ValueError):
            resolve_calibration_target(".", "safe_run")

    def test_calibration_root_cannot_overlap_cleanroom(self) -> None:
        with self.assertRaisesRegex(ValueError, "protected data root"):
            CalibrationPackageBuilder(
                cleanroom_run_name="cleanroom_fixture", calibration_run_name="unsafe",
                cleanroom_root=self.cleanroom_root, calibration_root=self.cleanroom_root,
                span_sample_size=2, paper_sample_size=1, link_sample_size=1,
            )

    def test_symlink_or_junction_target_is_refused(self) -> None:
        with mock.patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(ValueError, "symlink or junction"):
                resolve_calibration_target(self.calibration_root, "safe_run")

    def test_failed_build_writes_failed_manifest(self) -> None:
        builder = CalibrationPackageBuilder(
            cleanroom_run_name="missing_source", calibration_run_name="failed_fixture",
            cleanroom_root=self.cleanroom_root, calibration_root=self.calibration_root,
            span_sample_size=2, paper_sample_size=1, link_sample_size=1,
        )
        with self.assertRaises(FileNotFoundError):
            builder.build(clean=True, emit=lambda _: None)
        manifest = read_json(self.calibration_root / "failed_fixture/manifests/calibration_manifest.json")
        self.assertEqual(manifest["status"], "failed")

    def test_reproducibility_normalized_hashes(self) -> None:
        self.builder("repro_a").build(clean=True, emit=lambda _: None)
        self.builder("repro_b").build(clean=True, emit=lambda _: None)
        paths = [
            "sampling/span_sampling_frame.jsonl", "sampling/paper_sampling_frame.jsonl",
            "sampling/document_sampling_frame.jsonl", "sampling/link_sampling_frame.jsonl",
            "review/span_review.csv", "review/paper_review.csv",
            "review/document_review.csv", "review/link_review.csv",
        ]
        for relative in paths:
            self.assertEqual(
                normalized_file_hash(self.calibration_root / "repro_a" / relative),
                normalized_file_hash(self.calibration_root / "repro_b" / relative),
                relative,
            )

    def test_cli_build_and_check(self) -> None:
        build = subprocess.run([
            sys.executable, "scripts/build_calibration_package.py",
            "--cleanroom-run-name", "cleanroom_fixture", "--calibration-run-name", "cli_fixture",
            "--cleanroom-root", str(self.cleanroom_root), "--calibration-root", str(self.calibration_root),
            "--span-sample-size", "20", "--paper-sample-size", "8", "--link-sample-size", "10",
            "--seed", "16", "--clean",
        ], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(build.returncode, 0, build.stderr)
        check = subprocess.run([
            sys.executable, "scripts/check_calibration_package.py",
            "--calibration-run-name", "cli_fixture", "--cleanroom-root", str(self.cleanroom_root),
            "--calibration-root", str(self.calibration_root), "--require-blank-human-fields",
        ], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)


if __name__ == "__main__":
    unittest.main()
