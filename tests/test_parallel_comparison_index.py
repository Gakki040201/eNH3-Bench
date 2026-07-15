from __future__ import annotations

import unittest

from enh3bench.parallel_comparison import build_parallel_comparison_index, summarize_parallel_comparison


class ParallelComparisonIndexTests(unittest.TestCase):
    def test_structural_index_does_not_assert_scientific_comparability(self) -> None:
        records = [{"paper_id": "P1", "source_span_id": "S1", "source_locator": "P1::SEC001::PAR001::ANCHOR01", "reaction_family": "LiNRR", "section_type": "methods", "source_text": "15N isotope validation.", "document_relative_position": 0.25, "section_relative_position": 0.5, "paragraph_global_index": 2, "section_outline_label": "1", "verified_source_start_offset": 10}]
        index = build_parallel_comparison_index(records)
        self.assertEqual(index[0]["normalized_position_bin"], "0.2-0.3")
        self.assertEqual(index[0]["comparison_key"], "LiNRR|methods|validation")
        self.assertFalse(index[0]["scientific_comparability_asserted"])
        self.assertEqual(summarize_parallel_comparison(index, "fixture")["scientific_comparability_asserted_count"], 0)


if __name__ == "__main__":
    unittest.main()
