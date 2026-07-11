from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from enh3bench.experiment_result_importer import import_experiment_results


class ExperimentResultIdentityTests(unittest.TestCase):
    def test_duplicate_execution_id_is_rejected(self) -> None:
        rows = [_result("EXEC1", "rep_01"), _result("EXEC1", "rep_02")]
        outputs = _import(rows)
        self.assertEqual(outputs["invalid_results"], 1)
        self.assertIn("duplicate execution_id", Path(outputs["errors_csv"]).read_text(encoding="utf-8"))

    def test_duplicate_condition_replicate_identity_is_rejected(self) -> None:
        rows = [_result("EXEC1", "rep_01"), _result("EXEC2", "rep_01")]
        outputs = _import(rows)
        self.assertEqual(outputs["invalid_results"], 1)
        self.assertIn("duplicate route/condition/replicate identity", Path(outputs["errors_csv"]).read_text(encoding="utf-8"))

    def test_timepoints_do_not_create_independent_replicates(self) -> None:
        rows = [
            {**_result("EXEC1", "rep_01"), "timepoint_id": "t0"},
            {**_result("EXEC2", "rep_01"), "timepoint_id": "t1"},
        ]
        outputs = _import(rows)
        self.assertEqual(outputs["invalid_results"], 1)

    def test_old_one_row_template_imports_with_migration_warnings(self) -> None:
        old = {
            "experiment_id": "EXP_OLD",
            "route_id": "ER1",
            "run_name": "run1",
            "success_status": "partial",
            "required_measurements": "[]",
        }
        outputs = _import([old])
        self.assertEqual(outputs["valid_results"], 1)
        self.assertEqual(outputs["warning_results"], 1)
        warning_text = Path(outputs["warnings_csv"]).read_text(encoding="utf-8")
        self.assertIn("legacy template missing execution_id", warning_text)
        self.assertIn("did not establish an independent replicate", warning_text)

    def test_reused_baseline_assembly_is_rejected(self) -> None:
        rows = [
            {
                **_result("EXEC1", "rep_01"),
                "independent_assembly_required": "true",
                "assembly_id": "A1",
                "cell_build_id": "C1",
            },
            {
                **_result("EXEC2", "rep_02"),
                "independent_assembly_required": "true",
                "assembly_id": "A1",
                "cell_build_id": "C2",
            },
        ]
        outputs = _import(rows)
        self.assertEqual(outputs["invalid_results"], 1)
        self.assertIn("reuse assembly_id", Path(outputs["errors_csv"]).read_text(encoding="utf-8"))


def _result(execution_id: str, replicate_id: str) -> dict[str, str]:
    return {
        "schema_version": "1.1",
        "execution_unit": "route_condition_replicate",
        "execution_id": execution_id,
        "experiment_id": f"EXP_{execution_id}",
        "route_id": "ER1",
        "run_name": "run1",
        "condition_id": "baseline",
        "replicate_id": replicate_id,
        "replicate_index": replicate_id[-2:],
        "independent_replicate": "true",
        "independent_assembly_required": "false",
        "success_status": "partial",
        "required_measurements": "[]",
    }


def _import(rows: list[dict[str, str]]) -> dict[str, object]:
    temp_dir = tempfile.TemporaryDirectory()
    _TEMP_DIRS.append(temp_dir)
    root = Path(temp_dir.name)
    path = root / "results.csv"
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return import_experiment_results(path, "run1", output_dir=root / "out")


_TEMP_DIRS: list[tempfile.TemporaryDirectory[str]] = []


if __name__ == "__main__":
    unittest.main()
