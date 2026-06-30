from __future__ import annotations

import csv
import json
import os
import tempfile
import unittest
from pathlib import Path

from enh3bench.training_dataset import build_training_datasets


class TrainingDatasetTests(unittest.TestCase):
    def test_builds_weak_label_training_csvs(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            try:
                os.chdir(base)
                ledgers = base / "data" / "ledgers" / "test"
                reports = base / "data" / "reports"
                ledgers.mkdir(parents=True)
                reports.mkdir(parents=True)
                (ledgers / "classified_spans.jsonl").write_text(
                    json.dumps(
                        {
                            "span_id": "S001",
                            "evidence_id": "E001",
                            "paper_id": "P001",
                            "source_text": "N2 reduction produced NH3 with 15N2 validation.",
                            "text_class": "primary_performance_with_validation",
                            "allow_field_extraction": True,
                            "allow_gold": True,
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                (reports / "experiment_triage_scores.test.jsonl").write_text(
                    json.dumps(
                        {
                            "evidence_id": "E001",
                            "paper_id": "P001",
                            "reaction_family": "eNRR",
                            "faradaic_efficiency_percent": 55.0,
                            "nh3_yield_value": 5.0,
                            "isotope_validation": "yes",
                            "blank_control": "yes",
                            "contamination_control": "yes",
                            "nox_screening": "yes",
                            "reactor_type": "flow cell",
                            "engineering_flags": ["flow_or_GDE_reactor"],
                            "recommendation": "conditional_follow_up",
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )

                result = build_training_datasets("test")
            finally:
                os.chdir(original_cwd)

            self.assertEqual(result["source_span_rows"], 1)
            self.assertEqual(result["triage_rows"], 1)

            source_path = base / "data" / "training" / "source_span_training.test.csv"
            triage_path = base / "data" / "training" / "triage_training.test.csv"
            with source_path.open("r", encoding="utf-8", newline="") as handle:
                source_rows = list(csv.DictReader(handle))
            with triage_path.open("r", encoding="utf-8", newline="") as handle:
                triage_rows = list(csv.DictReader(handle))
            self.assertEqual(source_rows[0]["label_source"], "weak_rule_label")
            self.assertEqual(triage_rows[0]["human_recommendation"], "conditional_follow_up")
            self.assertEqual(triage_rows[0]["label_source"], "weak_rule_label")


if __name__ == "__main__":
    unittest.main()
