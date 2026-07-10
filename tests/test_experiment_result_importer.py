from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from enh3bench.experiment_result_importer import (
    export_experiment_result_template,
    import_experiment_results,
    validate_experiment_result,
)


class ExperimentResultImporterTests(unittest.TestCase):
    def test_result_template_includes_all_route_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs = export_experiment_result_template([_route("ER1"), _route("ER2")], "run1", output_dir=Path(temp_dir))
            text = Path(outputs["csv"]).read_text(encoding="utf-8")
        self.assertIn("ER1", text)
        self.assertIn("ER2", text)

    def test_failed_mandatory_controls_cannot_be_success(self) -> None:
        valid, errors = validate_experiment_result(
            {
                **_result(),
                "success_status": "success",
                "controls_failed": "Ar blank",
            }
        )
        self.assertFalse(valid)
        self.assertIn("failed mandatory controls cannot be marked success", errors)

    def test_import_writes_errors_for_invalid_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "results.csv"
            _write_csv(path, [{**_result(), "success_status": "success", "controls_failed": "Ar blank"}])
            outputs = import_experiment_results(path, "run1", output_dir=Path(temp_dir) / "out")
            self.assertEqual(outputs["invalid_results"], 1)
            self.assertTrue(Path(outputs["errors_csv"]).exists())


def _route(route_id: str) -> dict[str, object]:
    return {"route_id": route_id, "run_name": "run1", "required_controls": ["Ar blank"], "required_measurements": ["FE"]}


def _result() -> dict[str, str]:
    return {
        "experiment_id": "EXP1",
        "route_id": "ER1",
        "run_name": "run1",
        "success_status": "partial",
        "controls_completed": "Ar blank",
        "controls_failed": "",
        "required_controls": '["Ar blank"]',
        "required_measurements": '["FE"]',
        "FE": "10%",
        "invalid_reason": "",
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
