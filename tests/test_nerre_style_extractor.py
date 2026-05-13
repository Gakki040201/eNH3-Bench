from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.nerre_style_extractor import (  # noqa: E402
    build_nerre_json_prompt,
    parse_model_json_output,
    run_rule_nerre_style,
    validate_nerre_json_record,
)


class NerreStyleExtractorTests(unittest.TestCase):
    def test_build_prompt(self) -> None:
        prompt = build_nerre_json_prompt("Nitrate reduction gave FE 80%.")
        self.assertIn("Return JSON only", prompt)
        self.assertIn("Nitrate reduction", prompt)

    def test_parse_model_json_output_object(self) -> None:
        text = """
        ```json
        {"record_id":"E001","paper_id":"P001","source_span":"span","method_name":"m",
        "reaction_family":"NO3RR","nitrogen_source":"NO3-","catalyst":null,
        "electrolyte":null,"reactor_type":null,"potential":null,"FE_percent":80.0,
        "EE_percent":null,"NH3_yield":null,"NH3_yield_unit":null,"stability":null,
        "isotope_validation":"not_applicable","blank_control":"unclear",
        "contamination_control":"unclear","nox_screening":"unclear",
        "detection_method":null,"reliability_label":"C","extraction_confidence":"medium",
        "source_grounding_status":"explicit","notes":null}
        ```
        """
        records = parse_model_json_output(text)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["reaction_family"], "NO3RR")
        self.assertEqual(validate_nerre_json_record(records[0]), [])

    def test_rule_nerre_style_sets_method(self) -> None:
        record = run_rule_nerre_style(
            {"span_id": "S002", "paper_id": "P002", "text": "Nitrate reduction to ammonia gave FE of 80%."}
        )
        self.assertEqual(record["method_name"], "enh3_nerre_rule")
        self.assertEqual(record["reaction_family"], "NO3RR")


if __name__ == "__main__":
    unittest.main()
