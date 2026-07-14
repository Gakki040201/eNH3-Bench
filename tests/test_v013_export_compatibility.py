from __future__ import annotations

import copy
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from enh3bench.human_audit import export_audit_report, export_human_audit_sheet, merge_audit_sources
from scripts.export_human_audit_sheet import parse_args


FIXTURE_COLUMNS = Path(__file__).parent / "fixtures" / "v013_human_audit_columns.txt"


class V013ExportCompatibilityTests(unittest.TestCase):
    def test_cli_default_profile_is_legacy_v013(self) -> None:
        with patch.object(sys, "argv", ["export_human_audit_sheet.py", "--run-name", "fixture"]):
            args = parse_args()
        self.assertEqual(args.routing_profile, "legacy_v013")

    def test_legacy_empty_export_columns_match_fixed_v013_fixture(self) -> None:
        expected = FIXTURE_COLUMNS.read_text(encoding="utf-8").splitlines()
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = export_human_audit_sheet([], "fixture", output_dir=Path(temp_dir))
            with Path(outputs["csv"]).open("r", encoding="utf-8-sig", newline="") as handle:
                actual = next(csv.reader(handle))
        self.assertEqual(actual, expected)
        self.assertEqual(
            set(outputs),
            {
                "run_name",
                "count",
                "priority_records",
                "rule_review_records",
                "llm_review_records",
                "overall_review_records",
                "priority_band_counts",
                "jsonl",
                "csv",
            },
        )

    def test_legacy_default_does_not_sample_or_export_routing_fields(self) -> None:
        record = _reference("S1")
        merged = merge_audit_sources([record], reference_audit_sample_rate=1.0)
        self.assertNotIn("reference_sampled_for_audit", merged[0])
        self.assertNotIn("auto_secondary_reference", merged[0])
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = export_human_audit_sheet(merged, "fixture", output_dir=Path(temp_dir))
            with Path(outputs["csv"]).open("r", encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle))
            jsonl_record = json.loads(Path(outputs["jsonl"]).read_text(encoding="utf-8").splitlines()[0])
        self.assertFalse(set(header) & {"routing_profile", "auto_secondary_reference", "reference_sampled_for_audit"})
        self.assertNotIn("routing_profile", jsonl_record)

    def test_legacy_report_identifies_profile_without_secondary_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = export_audit_report([], "fixture", output_dir=Path(temp_dir))
            report = Path(report_path).read_text(encoding="utf-8")
        self.assertIn("routing_profile: legacy_v013", report)
        self.assertNotIn("stable_reference_auto_secondary_count", report)

    def test_opt_in_profile_enables_secondary_routing_and_sampling(self) -> None:
        merged = merge_audit_sources(
            [_reference("S1"), _reference("S2")],
            routing_profile="secondary_hardening_v1",
            reference_audit_sample_rate=1.0,
            max_reference_spans_per_paper_for_audit=1,
            reference_audit_seed="fixed",
        )
        self.assertTrue(all(record["auto_secondary_reference"] for record in merged))
        self.assertEqual(sum(bool(record["reference_sampled_for_audit"]) for record in merged), 1)
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = export_human_audit_sheet(
                merged,
                "fixture",
                output_dir=Path(temp_dir),
                routing_profile="secondary_hardening_v1",
            )
            with Path(outputs["csv"]).open("r", encoding="utf-8-sig", newline="") as handle:
                header = next(csv.reader(handle))
        self.assertIn("routing_profile", header)
        self.assertIn("auto_secondary_reference", header)
        self.assertIn("reference_sampled_for_audit", header)

    def test_both_profiles_read_v013_input_without_mutating_it(self) -> None:
        for profile in ("legacy_v013", "secondary_hardening_v1"):
            with self.subTest(profile=profile):
                original = _reference("S1")
                before = copy.deepcopy(original)
                merged = merge_audit_sources(
                    [original],
                    routing_profile=profile,
                    reference_audit_sample_rate=0.0,
                )
                self.assertEqual(original, before)
                self.assertEqual(merged[0]["schema_version"], "0.13")

    def test_caption_and_review_table_do_not_upgrade_in_either_profile(self) -> None:
        for profile in ("legacy_v013", "secondary_hardening_v1"):
            for record in (_caption(), _review_table()):
                with self.subTest(profile=profile, provenance=record["provenance_type"]):
                    merged = merge_audit_sources(
                        [record],
                        routing_profile=profile,
                        reference_audit_sample_rate=0.0,
                    )[0]
                    self.assertEqual(merged["maximum_supported_boundary"], "unsupported_or_secondary")


def _reference(source_span_id: str) -> dict[str, object]:
    return {
        "schema_version": "0.13",
        "paper_id": "P1",
        "source_span_id": source_span_id,
        "evidence_id": f"E-{source_span_id}",
        "source_text": "1. Smith et al. A citation. Journal (2020).",
        "provenance_type": "reference",
        "text_class": "reference_list",
        "maximum_supported_boundary": "unsupported_or_secondary",
        "admissibility_status": "reject_or_low_trust_provenance",
        "validation_gates": {},
        "missing_boundary_fields": [],
        "required_controls": [],
        "reaction_family_conflict": False,
        "text_class_provenance_conflict": False,
    }


def _caption() -> dict[str, object]:
    return {
        "schema_version": "0.13",
        "paper_id": "P1",
        "source_span_id": "caption",
        "source_text": "Fig. 1. FE 80%.",
        "provenance_type": "figure_caption",
        "text_class": "figure_caption",
        "maximum_supported_boundary": "unsupported_or_secondary",
        "admissibility_status": "context_only_caption",
        "validation_gates": {},
        "missing_boundary_fields": [],
        "required_controls": [],
    }


def _review_table() -> dict[str, object]:
    return {
        "schema_version": "0.13",
        "paper_id": "P1",
        "source_span_id": "review-table",
        "source_text": "Review table row reports FE 80%.",
        "provenance_type": "review_table",
        "text_class": "review_table",
        "maximum_supported_boundary": "unsupported_or_secondary",
        "admissibility_status": "secondary_only",
        "validation_gates": {},
        "missing_boundary_fields": [],
        "required_controls": [],
    }


if __name__ == "__main__":
    unittest.main()
