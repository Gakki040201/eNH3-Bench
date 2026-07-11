from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from enh3bench.document_provenance import migrate_provenance_record
from enh3bench.experiment_result_importer import import_experiment_results
from enh3bench.experiment_schema import migrate_experiment_route
from enh3bench.human_audit import migrate_audit_record
from enh3bench.ledger_router import load_jsonl


class SchemaMigrationV013Tests(unittest.TestCase):
    def test_provenance_audit_and_route_migrations_are_explicit(self) -> None:
        provenance = migrate_provenance_record({"source_span_id": "S1"})
        audit = migrate_audit_record({"audit_id": "A1"})
        route = migrate_experiment_route({"route_id": "R1", "route_type": "baseline_repeatability"})
        for record in (provenance, audit, route):
            self.assertEqual(record["schema_version"], "0.13")
            self.assertTrue(record["migration_warnings"])

    def test_old_one_row_template_remains_non_independent_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "old.csv"
            with input_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["experiment_id", "route_id", "run_name", "success_status", "required_measurements"],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "experiment_id": "EXP_OLD",
                        "route_id": "ER_OLD",
                        "run_name": "run1",
                        "success_status": "partial",
                        "required_measurements": "[]",
                    }
                )
            outputs = import_experiment_results(input_path, "run1", output_dir=root / "out")
            imported = load_jsonl(outputs["imported_jsonl"])[0]
        self.assertEqual(imported["schema_version"], "0.13")
        self.assertEqual(imported["independent_replicate"], "false")
        self.assertTrue(imported["migration_warnings"])
        self.assertIn("result schema migrated", " ".join(imported["migration_warnings"]))

    def test_v013_result_fields_survive_csv_and_jsonl_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "new.csv"
            fields = [
                "schema_version",
                "execution_id",
                "experiment_id",
                "route_id",
                "run_name",
                "condition_id",
                "replicate_id",
                "independent_replicate",
                "success_status",
                "required_controls",
                "mandatory_measurements",
                "human_baseline_approval",
                "human_baseline_notes",
                "baseline_gate_status",
            ]
            with input_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerow(
                    {
                        "schema_version": "0.13",
                        "execution_id": "EXEC1",
                        "experiment_id": "EXP1",
                        "route_id": "ER1",
                        "run_name": "run1",
                        "condition_id": "baseline",
                        "replicate_id": "rep_01",
                        "independent_replicate": "true",
                        "success_status": "partial",
                        "required_controls": "[]",
                        "mandatory_measurements": "[]",
                        "human_baseline_approval": "true",
                        "human_baseline_notes": "reviewed",
                        "baseline_gate_status": "passed",
                    }
                )
            first = import_experiment_results(input_path, "run1", output_dir=root / "first")
            second = import_experiment_results(first["imported_csv"], "run1", output_dir=root / "second")
            record = load_jsonl(second["imported_jsonl"])[0]
        self.assertEqual(record["schema_version"], "0.13")
        self.assertEqual(record["human_baseline_approval"], "true")
        self.assertEqual(record["human_baseline_notes"], "reviewed")
        self.assertEqual(record["baseline_gate_status"], "passed")


if __name__ == "__main__":
    unittest.main()
