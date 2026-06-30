from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from enh3bench.trainers import (
    dependencies_available,
    missing_dependency_message,
    train_source_span_classifier,
    train_triage_ranker,
)


class TrainerTests(unittest.TestCase):
    def test_missing_dependency_message_contains_install_command(self) -> None:
        self.assertIn("scikit-learn joblib", missing_dependency_message())
        self.assertIn(r"C:\Python314\python.exe", missing_dependency_message())

    @unittest.skipUnless(dependencies_available(), "scikit-learn/joblib not installed")
    def test_train_source_span_classifier_smoke_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            training_csv = base / "source.csv"
            _write_csv(
                training_csv,
                [
                    {
                        "source_text": "N2 reduction produced NH3 with 15N2 validation.",
                        "human_text_class": "primary_performance_with_validation",
                        "machine_text_class": "primary_performance_with_validation",
                    },
                    {
                        "source_text": "References [1] doi 10.1000/test",
                        "human_text_class": "reference_list",
                        "machine_text_class": "reference_list",
                    },
                    {
                        "source_text": "Review table of literature values.",
                        "human_text_class": "review_table",
                        "machine_text_class": "review_table",
                    },
                    {
                        "source_text": "Blank control protocol with isotope validation.",
                        "human_text_class": "protocol_guideline",
                        "machine_text_class": "protocol_guideline",
                    },
                ],
                ["source_text", "human_text_class", "machine_text_class"],
            )
            result = train_source_span_classifier(training_csv, base / "source.joblib", base / "source.md")
            self.assertTrue((base / "source.joblib").exists())
            self.assertTrue(result["smoke_warning"])

    @unittest.skipUnless(dependencies_available(), "scikit-learn/joblib not installed")
    def test_train_triage_ranker_smoke_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            training_csv = base / "triage.csv"
            _write_csv(
                training_csv,
                [
                    _triage_row("priority_follow_up", "yes", "yes", "yes", "yes"),
                    _triage_row("conditional_follow_up", "yes", "yes", "unclear", "unclear"),
                    _triage_row("insufficient_evidence", "unclear", "unclear", "unclear", "unclear"),
                    _triage_row("deprioritize", "no", "no", "no", "no"),
                ],
                [
                    "reaction_family",
                    "FE_percent",
                    "EE_percent",
                    "NH3_yield",
                    "isotope_validation",
                    "blank_control",
                    "contamination_control",
                    "nox_screening",
                    "reactor_type",
                    "engineering_flags",
                    "human_recommendation",
                    "machine_recommendation",
                ],
            )
            result = train_triage_ranker(training_csv, base / "triage.joblib", base / "triage.md")
            self.assertTrue((base / "triage.joblib").exists())
            self.assertTrue(result["smoke_warning"])


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _triage_row(label: str, isotope: str, blank: str, contamination: str, nox: str) -> dict[str, str]:
    return {
        "reaction_family": "eNRR",
        "FE_percent": "50",
        "EE_percent": "",
        "NH3_yield": "5",
        "isotope_validation": isotope,
        "blank_control": blank,
        "contamination_control": contamination,
        "nox_screening": nox,
        "reactor_type": "flow cell",
        "engineering_flags": "flow_or_GDE_reactor",
        "human_recommendation": label,
        "machine_recommendation": label,
    }


if __name__ == "__main__":
    unittest.main()
