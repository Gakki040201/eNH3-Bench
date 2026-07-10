from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from enh3bench.closed_loop import NO_RESULTS_MESSAGE, evaluate_closed_loop


class ClosedLoopTests(unittest.TestCase):
    def test_closed_loop_fails_clearly_without_imported_results(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                _write_jsonl(Path("data/experiment_routes/run1/ranked_experiment_routes.jsonl"), [_route()])
                with self.assertRaisesRegex(ValueError, NO_RESULTS_MESSAGE):
                    evaluate_closed_loop("run1")
            finally:
                os.chdir(old_cwd)

    def test_closed_loop_counts_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            old_cwd = os.getcwd()
            os.chdir(temp_dir)
            try:
                _write_jsonl(Path("data/experiment_routes/run1/ranked_experiment_routes.jsonl"), [_route()])
                _write_jsonl(
                    Path("data/experiment_results/run1/experiment_results_imported.jsonl"),
                    [
                        {"route_id": "ER1", "success_status": "success", "controls_failed": ""},
                        {"route_id": "ER1", "success_status": "partial", "controls_failed": ""},
                        {"route_id": "ER1", "success_status": "failed", "controls_failed": ""},
                        {"route_id": "ER1", "success_status": "invalid", "controls_failed": "Ar blank"},
                    ],
                )
                evaluation = evaluate_closed_loop("run1")
            finally:
                os.chdir(old_cwd)
        self.assertEqual(evaluation["success_count"], 1)
        self.assertEqual(evaluation["partial_count"], 1)
        self.assertEqual(evaluation["failed_count"], 1)
        self.assertEqual(evaluation["invalid_count"], 1)
        self.assertEqual(evaluation["invalid_due_to_controls_count"], 1)


def _route() -> dict[str, object]:
    return {
        "route_id": "ER1",
        "route_type": "validation_gap_closure",
        "priority_label": "priority_experiment",
        "hidden_tax_targeted": ["measurement_matrix_tax"],
    }


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True))
            handle.write("\n")


if __name__ == "__main__":
    unittest.main()
