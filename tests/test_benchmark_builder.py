from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from enh3bench.benchmark_builder import (
    build_all_benchmark_tasks,
    build_claim_rights_task,
    build_experiment_decision_task,
    build_hidden_tax_task,
    build_required_control_task,
    build_source_span_task,
    build_validation_gate_task,
    load_human_gold_records,
)


class BenchmarkBuilderTests(unittest.TestCase):
    def test_unreviewed_records_are_not_loaded_as_benchmark_gold(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            run_dir = base / "human_audit" / "run1"
            run_dir.mkdir(parents=True)
            _write_jsonl(run_dir / "reviewed_audit_records.jsonl", [_reviewed_record(), dict(_reviewed_record(), human_review_status="unreviewed")])
            records = load_human_gold_records("run1", {"gold": base / "gold", "human_audit": base / "human_audit"})
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["human_review_status"], "reviewed")

    def test_reviewed_records_build_all_six_tasks(self) -> None:
        tasks = build_all_benchmark_tasks([_reviewed_record()])
        self.assertEqual(set(tasks), {
            "source_span_classification",
            "validation_gate_extraction",
            "claim_rights_boundary_classification",
            "hidden_tax_detection",
            "required_control_prediction",
            "experiment_decision_ranking",
        })
        self.assertTrue(all(len(rows) == 1 for rows in tasks.values()))

    def test_source_span_task_gold_label_equals_human_text_class(self) -> None:
        row = build_source_span_task([_reviewed_record()])[0]
        self.assertEqual(row["gold_text_class"], "primary_performance")

    def test_validation_gate_task_exports_all_five_gate_labels(self) -> None:
        row = build_validation_gate_task([_reviewed_record()])[0]
        self.assertEqual(row["gold_isotope_15N"], "explicit")
        self.assertEqual(row["gold_blank_control"], "explicit")
        self.assertEqual(row["gold_NOx_control"], "missing")
        self.assertEqual(row["gold_contamination_control"], "unclear")
        self.assertEqual(row["gold_quantification_method"], "explicit")

    def test_claim_rights_task_gold_boundary_equals_human_boundary(self) -> None:
        row = build_claim_rights_task([_reviewed_record()])[0]
        self.assertEqual(row["gold_maximum_supported_boundary"], "cell_metric")

    def test_hidden_tax_task_handles_comma_and_json_list_labels(self) -> None:
        comma = dict(_reviewed_record(), human_hidden_tax="contamination_tax, measurement_matrix_tax")
        json_list = dict(_reviewed_record(), human_hidden_tax='["solvent_management_tax"]')
        rows = build_hidden_tax_task([comma, json_list])
        self.assertEqual(rows[0]["gold_hidden_tax"], ["contamination_tax", "measurement_matrix_tax"])
        self.assertEqual(rows[1]["gold_hidden_tax"], ["solvent_management_tax"])

    def test_required_control_task_handles_empty_lists_safely(self) -> None:
        row = build_required_control_task([dict(_reviewed_record(), human_required_controls="")])[0]
        self.assertEqual(row["gold_required_controls"], [])

    def test_experiment_decision_task_computes_priority_binary(self) -> None:
        priority = build_experiment_decision_task([dict(_reviewed_record(), human_experiment_decision="control_required")])[0]
        non_priority = build_experiment_decision_task([dict(_reviewed_record(), human_experiment_decision="protocol_reference")])[0]
        self.assertEqual(priority["gold_priority_binary"], 1)
        self.assertEqual(non_priority["gold_priority_binary"], 0)

    def test_build_script_fails_clearly_when_no_reviewed_records_exist(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/build_boundary_benchmark.py", "--run-name", "__missing_boundarybench_gold__"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No reviewed human records found", result.stdout + result.stderr)


def _reviewed_record() -> dict[str, object]:
    return {
        "audit_id": "AUD1",
        "run_name": "run1",
        "paper_id": "P1",
        "document_id": "D1",
        "doi": "10.1/example",
        "source_span_id": "S1",
        "evidence_id": "E1",
        "source_text": "N2 to NH3 gave FE with validation details.",
        "source_section": "results",
        "provenance_type": "body",
        "provenance_confidence": "high",
        "text_class": "primary_performance",
        "maximum_supported_boundary": "cell_metric",
        "admissibility_status": "metric_only_or_validation_incomplete",
        "validation_gates": {"isotope_15N": "yes", "blank_control": "yes", "nox_control": "missing", "contamination_control": "unclear", "quantification_method": "yes"},
        "detected_taxes": ["contamination_tax"],
        "required_controls": ["NOx/nitrate/nitrite screening"],
        "overclaim_risk_flags": ["n2_claim_without_15n"],
        "human_reviewer_id": "reviewer1",
        "human_review_status": "reviewed",
        "human_text_class": "primary_performance",
        "human_maximum_supported_boundary": "cell_metric",
        "human_admissibility_status": "accept_with_controls",
        "human_required_controls": "NOx/nitrate/nitrite screening",
        "human_hidden_tax": "contamination_tax",
        "human_experiment_decision": "control_required",
        "human_validation_isotope_15N": "explicit",
        "human_validation_blank_control": "explicit",
        "human_validation_NOx_control": "missing",
        "human_validation_contamination_control": "unclear",
        "human_validation_quantification_method": "explicit",
        "human_notes": "reviewed",
    }


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True))
            handle.write("\n")


if __name__ == "__main__":
    unittest.main()
