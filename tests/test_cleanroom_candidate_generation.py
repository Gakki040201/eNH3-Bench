from __future__ import annotations

import unittest

from enh3bench.cleanroom_candidates import generate_candidate_spans, summarize_candidates


class CleanroomCandidateGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        text = "We measured ammonia yield rate of 10 ug h-1 using NMR."
        self.node = {
            "source_node_id": "node", "paper_id": "paper", "document_id": "paper",
            "source_start_offset": 100, "source_end_offset": 100 + len(text),
            "source_locator": "P1", "source_order_key": "1", "source_text": text,
            "provenance_type": "primary_body", "maximum_support_role": "primary_support",
            "raw_heading": "Results", "direct_section_type": "results", "effective_section_type": "results",
            "document_region": "main_body", "paragraph_uid": "paragraph", "section_uid": "section",
        }
        self.document = {
            "document_body_sha256": "a" * 64, "document_genre": "primary_research",
            "document_reaction_family": "eNRR", "document_reaction_family_signals": [],
        }

    def test_generates_exact_single_node_candidate(self) -> None:
        records = generate_candidate_spans([self.node], {"paper": self.document}, run_name="run", profile="document_first_cleanroom_v1")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source_start_offset"], 100)
        self.assertEqual(records[0]["source_end_offset"], 100 + len(self.node["source_text"]))

    def test_candidate_kind_is_separate_from_semantic_type(self) -> None:
        record = generate_candidate_spans([self.node], {"paper": self.document}, run_name="run", profile="document_first_cleanroom_v1")[0]
        self.assertIn("candidate_kind", record)
        self.assertNotIn("semantic_claim_type", record)

    def test_no_signal_produces_no_candidate(self) -> None:
        self.node["source_text"] = "A neutral paragraph."
        self.node["source_end_offset"] = 120
        records = generate_candidate_spans([self.node], {"paper": self.document}, run_name="run", profile="document_first_cleanroom_v1")
        self.assertEqual(records, [])

    def test_diagnostics_have_zero_mapping_violations(self) -> None:
        records = generate_candidate_spans([self.node], {"paper": self.document}, run_name="run", profile="document_first_cleanroom_v1")
        summary = summarize_candidates(records, [self.node], 1)
        self.assertEqual(summary["cross_paragraph_candidate_count"], 0)
        self.assertEqual(summary["candidate_id_collision_count"], 0)


if __name__ == "__main__":
    unittest.main()
