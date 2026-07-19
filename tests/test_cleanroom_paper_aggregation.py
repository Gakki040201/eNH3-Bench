from __future__ import annotations

import unittest

from enh3bench.paper_aggregation import aggregate_paper_records


def document() -> dict:
    return {
        "paper_id": "p", "document_id": "p", "document_ref": "input_markdown/p.md",
        "document_genre": "primary_research", "document_reaction_family": "eNRR",
        "document_warnings": [], "document_reaction_family_conflict": False,
    }


class CleanroomPaperAggregationTests(unittest.TestCase):
    def test_document_without_candidates_is_preserved(self) -> None:
        records = aggregate_paper_records([document()], [], [], [], run_name="run", profile="document_first_cleanroom_v1")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["paper_admissibility_status"], "insufficient_evidence")

    def test_primary_result_without_controls_is_partial(self) -> None:
        semantic = {
            "paper_id": "p", "cleanroom_span_id": "s", "primary_semantic_eligibility": True,
            "performance_result_evidence": True, "validation_gate_decisions": {},
            "semantic_claim_type": "performance_result_claim", "source_start_offset": 1,
            "semantic_claim_type_score": 3, "needs_review": False,
        }
        record = aggregate_paper_records([document()], [], [semantic], [], run_name="run", profile="document_first_cleanroom_v1")[0]
        self.assertEqual(record["paper_admissibility_status"], "partially_supported")

    def test_paper_record_does_not_copy_full_document(self) -> None:
        record = aggregate_paper_records([document()], [], [], [], run_name="run", profile="document_first_cleanroom_v1")[0]
        self.assertNotIn("full_body_text", record)
        self.assertNotIn("source_text", record)


if __name__ == "__main__":
    unittest.main()
