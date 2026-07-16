from __future__ import annotations

import unittest

from enh3bench.parallel_comparison import build_parallel_comparison_index, summarize_parallel_comparison


class ParallelComparisonIndexTests(unittest.TestCase):
    def test_structural_index_does_not_assert_scientific_comparability(self) -> None:
        records = [{"paper_id": "P1", "source_span_id": "S1", "source_locator": "P1::SEC001::PAR001::ANCHOR01", "reaction_family": "LiNRR", "section_type": "methods", "source_text": "15N isotope validation.", "document_relative_position": 0.25, "section_relative_position": 0.5, "paragraph_global_index": 2, "section_outline_label": "1", "verified_source_start_offset": 10}]
        index = build_parallel_comparison_index(records)
        self.assertEqual(index[0]["normalized_position_bin"], "0.2-0.3")
        self.assertEqual(index[0]["comparison_key"], "LiNRR|methods|validation")
        self.assertEqual(index[0]["raw_comparison_key"], "LiNRR|methods|validation")
        self.assertEqual(index[0]["section_type_source"], "direct")
        self.assertFalse(index[0]["scientific_comparability_asserted"])
        self.assertEqual(summarize_parallel_comparison(index, "fixture")["scientific_comparability_asserted_count"], 0)

    def test_effective_inherited_section_drives_comparison_key(self) -> None:
        records = [{
            "paper_id": "P1", "source_span_id": "S1", "reaction_family": "eNRR",
            "direct_section_type": "unknown", "effective_section_type": "results_and_discussion",
            "inherited_section_type": "results_and_discussion", "inherited_from_section_uid": "SEC_PARENT",
            "source_text": "Faradaic efficiency 20%.", "verified_source_start_offset": 10,
        }]
        item = build_parallel_comparison_index(records)[0]
        self.assertEqual(item["comparison_key"], "eNRR|results|performance")
        self.assertEqual(item["raw_comparison_key"], "eNRR|unknown|performance")
        self.assertEqual(item["section_type_source"], "inherited")
        summary = summarize_parallel_comparison([item], "fixture")
        self.assertEqual(summary["comparison_groups_using_inherited_section"], 1)

    def test_effective_reaction_family_drives_comparison_key(self) -> None:
        item = build_parallel_comparison_index([{
            "paper_id": "P0090", "source_span_id": "S1", "reaction_family": "eNRR",
            "effective_reaction_family": "NO3RR",
            "effective_reaction_family_source": "high_confidence_document",
            "reaction_family_correction": True,
            "section_type": "results", "source_text": "Faradaic efficiency reached 20%.",
        }])[0]
        self.assertEqual(item["legacy_reaction_family"], "eNRR")
        self.assertEqual(item["effective_reaction_family"], "NO3RR")
        self.assertEqual(item["comparison_key"], "NO3RR|results|performance")
        self.assertTrue(item["reaction_family_correction"])


if __name__ == "__main__":
    unittest.main()
