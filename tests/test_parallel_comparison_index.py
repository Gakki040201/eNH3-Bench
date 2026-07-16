from __future__ import annotations

import unittest

from enh3bench.parallel_comparison import build_parallel_comparison_index, summarize_parallel_comparison
from scripts.build_parallel_comparison_index import (
    _attach_context_semantics,
    _parallel_context_consistency,
)


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

    def test_context_semantics_are_authoritative_without_family_reinference(self) -> None:
        item = build_parallel_comparison_index([{
            "paper_id": "P0021", "source_span_id": "S1",
            "paper_title": "Generic electrochemical N2 reduction",
            "source_text": "The HOR activity of Pt/C decreased after cycling.",
            "reaction_family": "eNRR", "effective_reaction_family": "LiNRR",
            "effective_reaction_family_source": "high_confidence_document",
            "document_reaction_family": "LiNRR", "reaction_family_correction": True,
            "primary_semantic_eligibility": False,
            "semantic_claim_type": "performance_context_claim",
            "performance_result_evidence": False,
            "performance_evidence_strength": "context_only",
            "section_type": "results",
        }])[0]
        self.assertEqual(item["effective_reaction_family"], "LiNRR")
        self.assertEqual(item["document_reaction_family"], "LiNRR")
        self.assertEqual(item["semantic_claim_type"], "performance_context_claim")
        self.assertFalse(item["performance_result_evidence"])
        self.assertFalse(item["primary_semantic_eligibility"])

    def test_span_coordinates_receive_authoritative_packet_semantics(self) -> None:
        spans = [{
            "paper_id": "P1", "source_span_id": "S1", "reaction_family": "eNRR",
            "section_type": "results", "source_text": "HOR activity declined.",
        }]
        packets = [{
            "target_span_id": "S1", "effective_reaction_family": "LiNRR",
            "effective_reaction_family_source": "high_confidence_document",
            "document_reaction_family": "LiNRR", "reaction_family_correction": True,
            "semantic_claim_type": "performance_context_claim",
            "performance_result_evidence": False, "performance_evidence_strength": "context_only",
            "primary_semantic_eligibility": False,
            "local_reaction_family_conflict_primary_admissible": False,
            "target_ammonia_reaction_outcome_anchor": False,
        }]
        routed, missing = _attach_context_semantics(spans, packets)
        self.assertEqual(missing, [])
        comparison = build_parallel_comparison_index(routed)
        self.assertEqual(comparison[0]["effective_reaction_family"], "LiNRR")
        self.assertTrue(all(
            value == 0 for value in _parallel_context_consistency(comparison, packets).values()
        ))


if __name__ == "__main__":
    unittest.main()
