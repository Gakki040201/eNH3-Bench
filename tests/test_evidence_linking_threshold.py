from __future__ import annotations

import unittest

from enh3bench.evidence_linking import HIERARCHICAL_LINKING_PROFILE, link_supporting_evidence, score_link


class EvidenceLinkingThresholdTests(unittest.TestCase):
    def test_threshold_accepts_strong_adjacent_and_rejects_generic_without_filling_quota(self) -> None:
        target = _record("P1_S001", "Faradaic efficiency was 20%.")
        strong = _record("P1_S002", "15N isotope validation and Ar blank were performed.")
        generic = _record("P1_S003", "Ammonia nitrogen electrochemical potential stability background.")
        result = link_supporting_evidence(target, [target, strong, generic], {"maximum_total_links": 12}, profile=HIERARCHICAL_LINKING_PROFILE, minimum_link_score=0.60)
        self.assertGreaterEqual(score_link(target, strong), 0.60)
        self.assertEqual([item["span_id"] for item in result["validation"]], ["P1_S002"])
        self.assertEqual(result["total_links"], 1)
        self.assertEqual(result["context_hint"], [])

    def test_high_threshold_rejects_candidate(self) -> None:
        target = _record("P1_S001", "Faradaic efficiency was 20%.")
        candidate = _record("P1_S002", "15N isotope validation was performed.")
        result = link_supporting_evidence(target, [target, candidate], profile=HIERARCHICAL_LINKING_PROFILE, minimum_link_score=0.99)
        self.assertEqual(result["total_links"], 0)
        self.assertGreater(result["diagnostics"]["links_below_threshold"], 0)


def _record(span_id: str, text: str) -> dict[str, object]:
    return {"paper_id": "P1", "document_id": "P1", "source_span_id": span_id, "source_text": text, "section_path": ["Results"], "provenance_type": "body", "text_class": "primary_performance", "is_primary_admissible": True, "reaction_family": "eNRR"}


if __name__ == "__main__":
    unittest.main()
