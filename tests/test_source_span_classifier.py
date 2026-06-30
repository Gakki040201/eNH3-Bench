from __future__ import annotations

import unittest

from enh3bench.source_span_classifier import classify_source_span


class SourceSpanClassifierTests(unittest.TestCase):
    def test_primary_performance_with_validation(self) -> None:
        result = classify_source_span(
            "Li-mediated N2 reduction produced NH3 at 10.5 nmol s-1 cm-2 with "
            "62% FE at 20 mA cm-2 and 15N2 isotope labeling plus blank control."
        )
        self.assertEqual(result["text_class"], "primary_performance_with_validation")
        self.assertEqual(result["recommended_ledger"], "performance")
        self.assertTrue(result["allow_field_extraction"])
        self.assertTrue(result["allow_gold"])

    def test_reference_list_is_rejected(self) -> None:
        result = classify_source_span(
            "[1] Smith, J. Journal 2020, 1, 1. doi:10.1000/a\n"
            "[2] Lee, K. Journal 2021, 2, 2. doi:10.1000/b"
        )
        self.assertEqual(result["text_class"], "reference_list")
        self.assertEqual(result["recommended_ledger"], "reject")
        self.assertFalse(result["allow_field_extraction"])
        self.assertFalse(result["allow_gold"])

    def test_review_table_routes_secondary(self) -> None:
        result = classify_source_span("Table S1 review table of previous reports and literature values.")
        self.assertEqual(result["text_class"], "review_table")
        self.assertEqual(result["recommended_ledger"], "secondary")
        self.assertFalse(result["allow_field_extraction"])

    def test_protocol_routes_protocol_ledger(self) -> None:
        result = classify_source_span(
            "The recommended protocol requires 15N isotope labeling, blank control, "
            "NOx screening, and calibration curve checks."
        )
        self.assertEqual(result["text_class"], "protocol_guideline")
        self.assertEqual(result["recommended_ledger"], "protocol")

    def test_contamination_routes_negative(self) -> None:
        result = classify_source_span(
            "Nitrate contamination and background ammonia were detected during the NOx screening."
        )
        self.assertEqual(result["text_class"], "contamination_detection_evidence")
        self.assertEqual(result["recommended_ledger"], "negative")
        self.assertFalse(result["allow_field_extraction"])

    def test_figure_caption_is_context(self) -> None:
        result = classify_source_span("Figure 2. Faradaic efficiency and NH3 yield for the catalyst.")
        self.assertEqual(result["text_class"], "figure_caption")
        self.assertEqual(result["recommended_ledger"], "context")
        self.assertFalse(result["allow_field_extraction"])


if __name__ == "__main__":
    unittest.main()
