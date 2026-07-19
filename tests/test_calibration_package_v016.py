from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from typing import Callable
from unittest import mock

from tests.calibration_test_helpers import create_cleanroom_fixture
from enh3bench.calibration_package import (
    CalibrationPackageBuilder,
    normalized_file_hash,
    tree_hash,
)
from enh3bench.calibration_schema import (
    HUMAN_FIELDS_BY_TYPE,
    LABEL_FIELDS_BY_TYPE,
    read_csv,
    read_json,
    read_jsonl,
    resolve_calibration_target,
    write_json,
    write_jsonl,
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

    def build_fixture(self) -> Path:
        self.builder().build(clean=True, emit=lambda _: None)
        return self.calibration_root / "calibration_fixture"

    def validate_fixture(self, *, require_blank: bool = True) -> dict[str, object]:
        return validate_calibration_package(
            calibration_run_name="calibration_fixture", calibration_root=self.calibration_root,
            cleanroom_root=self.cleanroom_root, require_blank_human_fields=require_blank,
        )

    def rewrite_review(self, item_type: str, mutate: Callable[[list[dict[str, str]]], None]) -> None:
        path = self.calibration_root / f"calibration_fixture/review/{item_type}_review.csv"
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
        mutate(rows)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def rewrite_span_frame(self, mutate: Callable[[list[dict[str, object]]], None]) -> None:
        path = self.calibration_root / "calibration_fixture/sampling/span_sampling_frame.jsonl"
        rows = read_jsonl(path)
        mutate(rows)
        write_jsonl(path, rows)

    def add_review_column(self, item_type: str, column: str, value: str = "") -> None:
        path = self.calibration_root / f"calibration_fixture/review/{item_type}_review.csv"
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = [*(reader.fieldnames or []), column]
            rows = list(reader)
        for row in rows:
            row[column] = value
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def run_metrics_cli(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            sys.executable, "scripts/summarize_calibration_reviews.py",
            "--calibration-run-name", "calibration_fixture",
            "--cleanroom-root", str(self.cleanroom_root),
            "--calibration-root", str(self.calibration_root),
        ], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)

    def complete_reviews_for_two_reviewers(self) -> None:
        for item_type in ("span", "paper", "document", "link"):
            path = self.calibration_root / f"calibration_fixture/review/{item_type}_review.csv"
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                fieldnames = list(reader.fieldnames or [])
                source_rows = list(reader)
            completed: list[dict[str, str]] = []
            for source in source_rows:
                for reviewer in ("reviewer-1", "reviewer-2"):
                    row = dict(source)
                    row["reviewer_id"] = reviewer
                    row["review_status"] = "completed"
                    for field in LABEL_FIELDS_BY_TYPE[item_type]:
                        row[field] = "yes"
                    completed.append(row)
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(completed)

    def valid_metrics_summary(self, run: Path) -> dict[str, object]:
        manifest = read_json(run / "manifests/calibration_manifest.json")
        return {
            "schema_version": manifest["schema_version"],
            "calibration_profile": manifest["calibration_profile"],
            "calibration_run_name": manifest["calibration_run_name"],
            "source_cleanroom_run_name": manifest["source_cleanroom_run_name"],
            "source_cleanroom_manifest_sha256": manifest["source_cleanroom_manifest_sha256"],
            "record_created_by_stage": "metrics",
            "metric_schema_version": "0.16-calibration-metrics.1",
            "status": "not_available",
            "validation_errors": [],
            "row_completeness": {},
            "item_coverage": {},
            "reviewer_coverage": {},
            "correctness_metrics": {},
            "class_label_metrics": {},
            "reviewer_agreement": {},
        }

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

    def test_review_semantic_claim_type_modification_fails(self) -> None:
        self.build_fixture()
        self.rewrite_review("span", lambda rows: rows[0].__setitem__("semantic_claim_type", "tampered_claim"))
        result = self.validate_fixture()
        item_id = read_csv(self.calibration_root / "calibration_fixture/review/span_review.csv")[0]["calibration_item_id"]
        self.assertIn(f"review_automatic_field_mismatch:span:{item_id}:semantic_claim_type", result["errors"])

    def test_review_target_excerpt_modification_fails(self) -> None:
        self.build_fixture()
        self.rewrite_review("span", lambda rows: rows[0].__setitem__("target_excerpt", "tampered excerpt"))
        result = self.validate_fixture()
        item_id = read_csv(self.calibration_root / "calibration_fixture/review/span_review.csv")[0]["calibration_item_id"]
        self.assertIn(f"review_automatic_field_mismatch:span:{item_id}:target_excerpt", result["errors"])

    def test_review_source_offset_modification_fails(self) -> None:
        self.build_fixture()
        self.rewrite_review("span", lambda rows: rows[0].__setitem__(
            "source_start_offset", str(int(rows[0]["source_start_offset"]) + 1)
        ))
        result = self.validate_fixture()
        item_id = read_csv(self.calibration_root / "calibration_fixture/review/span_review.csv")[0]["calibration_item_id"]
        self.assertIn(f"review_automatic_field_mismatch:span:{item_id}:source_start_offset", result["errors"])

    def test_only_legal_human_review_fields_may_change(self) -> None:
        self.build_fixture()
        def fill_human_fields(rows: list[dict[str, str]]) -> None:
            rows[0]["reviewer_id"] = "reviewer-1"
            rows[0]["review_status"] = "completed"
            for field in HUMAN_FIELDS_BY_TYPE["span"]:
                if field.startswith("human_") and not field.endswith("notes"):
                    rows[0][field] = "yes"
        self.rewrite_review("span", fill_human_fields)
        result = self.validate_fixture(require_blank=False)
        self.assertEqual(result["result"], "PASS", result["errors"])

    def test_review_json_list_and_dict_round_trip_has_no_false_positive(self) -> None:
        self.build_fixture()
        def reformat_json_fields(rows: list[dict[str, str]]) -> None:
            rows[0]["hard_gate_failures"] = json.dumps(json.loads(rows[0]["hard_gate_failures"]), indent=2)
            rows[0]["validation_gate_decisions"] = json.dumps(
                json.loads(rows[0]["validation_gate_decisions"]), indent=2, sort_keys=False
            )
        self.rewrite_review("span", reformat_json_fields)
        result = self.validate_fixture()
        self.assertEqual(result["result"], "PASS", result["errors"])

    def test_unknown_empty_review_column_fails(self) -> None:
        self.build_fixture()
        self.add_review_column("span", "arbitrary_empty_column")
        result = self.validate_fixture()
        self.assertIn("unexpected_review_column:span:arbitrary_empty_column", result["errors"])

    def test_legitimate_optional_union_header_is_allowed(self) -> None:
        run = self.build_fixture()
        frames = read_jsonl(run / "sampling/span_sampling_frame.jsonl")
        reviews = read_csv(run / "review/span_review.csv")
        human_fields = set(HUMAN_FIELDS_BY_TYPE["span"])
        self.assertTrue(any(
            column not in frame and not review.get(column)
            for frame, review in zip(frames, reviews)
            for column in set(review) - human_fields
        ))
        result = self.validate_fixture()
        self.assertEqual(result["result"], "PASS", result["errors"])

    def test_duplicate_item_reviewer_observation_fails(self) -> None:
        self.build_fixture()
        self.rewrite_review("span", lambda rows: rows.append(dict(rows[0])))
        result = self.validate_fixture()
        item_id = read_csv(self.calibration_root / "calibration_fixture/review/span_review.csv")[0]["calibration_item_id"]
        self.assertIn(f"duplicate_review_observation:span:{item_id}:<blank>", result["errors"])

    def test_missing_and_extra_review_rows_fail(self) -> None:
        self.build_fixture()
        removed: list[str] = []
        def replace_row(rows: list[dict[str, str]]) -> None:
            removed.append(rows[0]["calibration_item_id"])
            rows.pop(0)
            extra = dict(rows[0])
            extra["calibration_item_id"] = "CC16S_EXTRA"
            rows.append(extra)
        self.rewrite_review("span", replace_row)
        result = self.validate_fixture()
        self.assertIn(f"missing_review_row:span:{removed[0]}", result["errors"])
        self.assertIn("extra_review_row:span:CC16S_EXTRA", result["errors"])

    def test_review_item_type_mismatch_fails(self) -> None:
        self.build_fixture()
        self.rewrite_review("span", lambda rows: rows[0].__setitem__("item_type", "paper"))
        result = self.validate_fixture()
        item_id = read_csv(self.calibration_root / "calibration_fixture/review/span_review.csv")[0]["calibration_item_id"]
        self.assertIn(f"review_item_type_mismatch:span:{item_id}:paper", result["errors"])

    def test_unexpected_pdf_is_rejected_as_binary(self) -> None:
        run = self.build_fixture()
        (run / "paper.pdf").write_bytes(b"%PDF-1.7\nfixture")
        result = self.validate_fixture()
        self.assertIn("unexpected_package_file:paper.pdf", result["errors"])
        self.assertIn("unsupported_binary_file:paper.pdf", result["errors"])

    def test_unexpected_markdown_attachment_fails(self) -> None:
        run = self.build_fixture()
        (run / "full_document.md").write_text("full attachment", encoding="utf-8")
        result = self.validate_fixture()
        self.assertIn("unexpected_package_file:full_document.md", result["errors"])

    def test_unexpected_json_fails(self) -> None:
        run = self.build_fixture()
        write_json(run / "arbitrary.json", {"unexpected": True})
        result = self.validate_fixture()
        self.assertIn("unexpected_package_file:arbitrary.json", result["errors"])

    def test_declared_metrics_summary_is_allowed(self) -> None:
        run = self.build_fixture()
        write_json(run / "reports/calibration_metrics_summary.json", self.valid_metrics_summary(run))
        result = self.validate_fixture()
        self.assertEqual(result["result"], "PASS", result["errors"])

    def test_metrics_summary_run_name_modification_fails(self) -> None:
        run = self.build_fixture()
        summary = self.valid_metrics_summary(run)
        summary["calibration_run_name"] = "wrong_run"
        write_json(run / "reports/calibration_metrics_summary.json", summary)
        result = self.validate_fixture()
        self.assertIn("metrics_summary_field_mismatch:calibration_run_name", result["errors"])

    def test_metrics_summary_source_sha_modification_fails(self) -> None:
        run = self.build_fixture()
        summary = self.valid_metrics_summary(run)
        summary["source_cleanroom_manifest_sha256"] = "0" * 64
        write_json(run / "reports/calibration_metrics_summary.json", summary)
        result = self.validate_fixture()
        self.assertIn("metrics_summary_field_mismatch:source_cleanroom_manifest_sha256", result["errors"])

    def test_metrics_summary_missing_metric_schema_version_fails(self) -> None:
        run = self.build_fixture()
        summary = self.valid_metrics_summary(run)
        del summary["metric_schema_version"]
        write_json(run / "reports/calibration_metrics_summary.json", summary)
        result = self.validate_fixture()
        self.assertIn("metrics_summary_field_mismatch:metric_schema_version", result["errors"])

    def test_available_metrics_summary_with_validation_errors_fails(self) -> None:
        run = self.build_fixture()
        summary = self.valid_metrics_summary(run)
        summary["status"] = "available"
        summary["validation_errors"] = ["fixture_error"]
        write_json(run / "reports/calibration_metrics_summary.json", summary)
        result = self.validate_fixture()
        self.assertIn("metrics_summary_validation_errors_nonempty", result["errors"])

    def test_metrics_cli_refuses_missing_review_row_without_output(self) -> None:
        run = self.build_fixture()
        self.rewrite_review("span", lambda rows: rows.pop(0))
        result = self.run_metrics_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("calibration_metrics: FAIL", result.stdout + result.stderr)
        self.assertIn("missing_review_row:span:", result.stdout + result.stderr)
        self.assertFalse((run / "reports/calibration_metrics_summary.json").exists())

    def test_metrics_cli_refuses_modified_automatic_field(self) -> None:
        run = self.build_fixture()
        self.rewrite_review("span", lambda rows: rows[0].__setitem__("semantic_claim_type", "tampered"))
        result = self.run_metrics_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("review_automatic_field_mismatch:span:", result.stdout + result.stderr)
        self.assertFalse((run / "reports/calibration_metrics_summary.json").exists())

    def test_metrics_cli_refuses_duplicate_observation(self) -> None:
        run = self.build_fixture()
        self.rewrite_review("span", lambda rows: rows.append(dict(rows[0])))
        result = self.run_metrics_cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate_review_observation:span:", result.stdout + result.stderr)
        self.assertFalse((run / "reports/calibration_metrics_summary.json").exists())

    def test_metrics_cli_accepts_two_completed_reviewers(self) -> None:
        run = self.build_fixture()
        self.complete_reviews_for_two_reviewers()
        before = self.validate_fixture(require_blank=False)
        self.assertEqual(before["result"], "PASS", before["errors"])
        cli = self.run_metrics_cli()
        self.assertEqual(cli.returncode, 0, cli.stdout + cli.stderr)
        summary = read_json(run / "reports/calibration_metrics_summary.json")
        self.assertEqual(summary["row_completeness"]["completion_rate"], 1.0)
        self.assertEqual(summary["item_coverage"]["coverage_rate"], 1.0)
        self.assertEqual(summary["row_completeness"]["total_review_rows"], 140)
        self.assertEqual(summary["item_coverage"]["total_unique_items"], 70)
        after = self.validate_fixture(require_blank=False)
        self.assertEqual(after["result"], "PASS", after["errors"])

    def test_missing_required_preview_fails(self) -> None:
        run = self.build_fixture()
        (run / "previews/calibration_preview.md").unlink()
        result = self.validate_fixture()
        self.assertIn("missing_package_file:previews/calibration_preview.md", result["errors"])

    def test_missing_validation_summary_fails(self) -> None:
        run = self.build_fixture()
        (run / "reports/validation_summary.json").unlink()
        result = self.validate_fixture()
        self.assertIn("missing_package_file:reports/validation_summary.json", result["errors"])

    def test_validation_summary_fail_result_is_rejected(self) -> None:
        run = self.build_fixture()
        summary = read_json(run / "reports/validation_summary.json")
        summary["result"] = "FAIL"
        write_json(run / "reports/validation_summary.json", summary)
        result = self.validate_fixture()
        self.assertIn("completed_validation_summary_not_pass:FAIL", result["errors"])

    def test_validation_summary_source_sha_modification_is_rejected(self) -> None:
        run = self.build_fixture()
        summary = read_json(run / "reports/validation_summary.json")
        summary["source_cleanroom_manifest_sha256"] = "0" * 64
        write_json(run / "reports/validation_summary.json", summary)
        result = self.validate_fixture()
        self.assertIn("validation_summary_field_mismatch:source_cleanroom_manifest_sha256", result["errors"])

    def test_completed_manifest_with_pending_summary_is_rejected(self) -> None:
        run = self.build_fixture()
        summary = read_json(run / "reports/validation_summary.json")
        summary["result"] = "PENDING"
        write_json(run / "reports/validation_summary.json", summary)
        result = self.validate_fixture()
        self.assertIn("completed_validation_summary_not_pass:PENDING", result["errors"])

    def test_nonadjacent_previous_context_fails(self) -> None:
        self.build_fixture()
        source_nodes = read_jsonl(self.cleanroom_root / "cleanroom_fixture/source_nodes/source_nodes.jsonl")
        def tamper(rows: list[dict[str, object]]) -> None:
            row = next(item for item in rows if item["previous_context_source_node_id"])
            candidates = [
                node for node in source_nodes
                if node["document_id"] == row["document_id"]
                and node["source_node_id"] not in {
                    row["source_node_id"], row["previous_context_source_node_id"], row["next_context_source_node_id"]
                }
            ]
            row["previous_context_source_node_id"] = candidates[0]["source_node_id"]
        self.rewrite_span_frame(tamper)
        result = self.validate_fixture()
        self.assertTrue(any("context_source_node_id_mismatch:previous_context_source_node_id" in error for error in result["errors"]))

    def test_linked_evidence_list_length_mismatch_fails(self) -> None:
        self.build_fixture()
        def tamper(rows: list[dict[str, object]]) -> None:
            row = next(item for item in rows if len(item["linked_evidence_ids"]) >= 2)
            row["linked_evidence_span_ids"] = row["linked_evidence_span_ids"][:-1]
        self.rewrite_span_frame(tamper)
        result = self.validate_fixture()
        self.assertTrue(any("linked_evidence_list_length_mismatch" in error for error in result["errors"]))

    def test_second_linked_evidence_endpoint_modification_fails(self) -> None:
        self.build_fixture()
        def tamper(rows: list[dict[str, object]]) -> None:
            row = next(item for item in rows if len(item["linked_evidence_ids"]) >= 2)
            row["linked_evidence_span_ids"][1] = row["linked_evidence_span_ids"][0]
        self.rewrite_span_frame(tamper)
        result = self.validate_fixture()
        self.assertTrue(any("linked_evidence_endpoint_mismatch:1" in error for error in result["errors"]))

    def test_cross_paper_linked_evidence_endpoint_fails(self) -> None:
        self.build_fixture()
        def tamper(rows: list[dict[str, object]]) -> None:
            row = next(item for item in rows if item["linked_evidence_ids"])
            cross_paper = next(item for item in rows if item["paper_id"] != row["paper_id"])
            row["linked_evidence_span_ids"][0] = cross_paper["cleanroom_span_id"]
        self.rewrite_span_frame(tamper)
        result = self.validate_fixture()
        self.assertTrue(any("cross_paper_linked_evidence" in error for error in result["errors"]))

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
