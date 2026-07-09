from __future__ import annotations

import unittest

from enh3bench.benchmark_schema import (
    benchmark_record_id,
    normalize_multi_label,
    task_output_fields,
    validate_task_record,
)


class BenchmarkSchemaTests(unittest.TestCase):
    def test_normalize_multi_label_handles_json_and_commas(self) -> None:
        self.assertEqual(normalize_multi_label('["contamination_tax","measurement_matrix_tax"]'), ["contamination_tax", "measurement_matrix_tax"])
        self.assertEqual(normalize_multi_label("a, b; c|d"), ["a", "b", "c", "d"])

    def test_validate_source_span_task_record(self) -> None:
        record = {
            "benchmark_id": "BB1",
            "task_name": "source_span_classification",
            "gold_text_class": "primary_performance",
        }
        valid, errors = validate_task_record("source_span_classification", record)
        self.assertTrue(valid)
        self.assertEqual(errors, [])

    def test_task_output_fields_include_gold(self) -> None:
        fields = task_output_fields("claim_rights_boundary_classification")
        self.assertIn("gold_maximum_supported_boundary", fields)
        self.assertIn("source_text", fields)

    def test_benchmark_record_id_is_task_specific(self) -> None:
        record_id = benchmark_record_id({"audit_id": "AUD 1"}, "hidden_tax_detection")
        self.assertTrue(record_id.startswith("BB_hidden_tax_detection_"))


if __name__ == "__main__":
    unittest.main()
