from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.rule_baseline import (  # noqa: E402
    classify_reaction_family,
    detect_blank_control,
    detect_contamination_control,
    detect_detection_method,
    detect_isotope_validation,
    detect_nitrogen_source,
    extract_fe_percent,
    extract_nh3_yield,
    run_rule_extraction,
)
from scripts.run_rule_baseline import run_baseline  # noqa: E402


class RuleBaselineTests(unittest.TestCase):
    def test_family_classification(self) -> None:
        self.assertEqual(classify_reaction_family("Li-mediated N2 reduction in THF"), "LiNRR")
        self.assertEqual(classify_reaction_family("nitrate reduction to ammonia"), "NO3RR")
        self.assertEqual(classify_reaction_family("NO2- reduction to ammonia"), "NO2RR")
        self.assertEqual(classify_reaction_family("nitric oxide reduction to ammonia"), "NORR")
        self.assertEqual(classify_reaction_family("N2 reduction to NH3"), "eNRR")

    def test_nitrogen_source_detection(self) -> None:
        self.assertEqual(detect_nitrogen_source("15N2 labeling confirmed NH3"), "15N2")
        self.assertEqual(detect_nitrogen_source("10 mM NO3- electrolyte"), "NO3-")
        self.assertEqual(detect_nitrogen_source("nitrite feed"), "NO2-")

    def test_fe_extraction(self) -> None:
        self.assertEqual(extract_fe_percent("The NH3 FE reached 62%."), 62.0)
        self.assertEqual(extract_fe_percent("85% faradaic efficiency for NH3"), 85.0)
        self.assertIsNone(extract_fe_percent("No efficiency value was reported."))

    def test_nh3_yield_extraction(self) -> None:
        value, unit = extract_nh3_yield("NH3 at 10.5 nmol s-1 cm-2 with 62% FE")
        self.assertEqual(value, 10.5)
        self.assertEqual(unit, "nmol s-1 cm-2")

    def test_validation_detection(self) -> None:
        text = (
            "15N2 isotope labeling, Ar blank control, NOx screening, "
            "background ammonia checks, and ion chromatography were reported."
        )
        self.assertEqual(detect_isotope_validation(text), "yes")
        self.assertEqual(detect_blank_control(text), "yes")
        self.assertEqual(detect_contamination_control(text), "yes")
        self.assertEqual(detect_detection_method(text), "ion chromatography")

    def test_run_rule_extraction_shape(self) -> None:
        prediction = run_rule_extraction(
            {
                "span_id": "S002",
                "paper_id": "P002",
                "source_section": "results",
                "text": "Li-mediated N2 reduction produced NH3 at 10.5 nmol s-1 cm-2 with 62% FE.",
            }
        )
        self.assertEqual(prediction["evidence_id"], "E002")
        self.assertEqual(prediction["reaction_family"], "LiNRR")
        self.assertEqual(prediction["faradaic_efficiency_percent"], 62.0)
        self.assertEqual(prediction["nh3_yield_value"], 10.5)

    def test_output_jsonl_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "spans.jsonl"
            output_path = temp_path / "predictions.jsonl"
            input_path.write_text(
                json.dumps(
                    {
                        "span_id": "S001",
                        "paper_id": "P001",
                        "source_section": "results",
                        "text": "N2 reduction to NH3 with 15N2 isotope labeling and blank control.",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            count = run_baseline(input_path, output_path)
            self.assertEqual(count, 1)
            rows = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows[0]["reaction_family"], "eNRR")
            self.assertEqual(rows[0]["isotope_validation"], "yes")


if __name__ == "__main__":
    unittest.main()
