from __future__ import annotations

import unittest

from enh3bench.evidence_linking import HIERARCHICAL_LINKING_PROFILE, link_supporting_evidence


class EvidenceLinkingDeduplicationTests(unittest.TestCase):
    def test_multi_role_candidate_is_one_unique_link(self) -> None:
        target = _record("P1_S001", "Faradaic efficiency 20%.")
        support = _record("P1_S002", "15N isotope validation and ammonia quantification by ion chromatography.")
        result = link_supporting_evidence(target, [target, support], profile=HIERARCHICAL_LINKING_PROFILE)
        self.assertEqual(result["validation"][0]["span_id"], "P1_S002")
        self.assertEqual(result["quantification"][0]["span_id"], "P1_S002")
        self.assertEqual(result["total_links"], 1)
        self.assertEqual(result["diagnostics"]["self_link_count"], 0)
        self.assertEqual(result["diagnostics"]["self_candidate_rejected_count"], 1)


def _record(span_id: str, text: str) -> dict[str, object]:
    return {"paper_id": "P1", "source_span_id": span_id, "source_text": text, "section_path": ["Results"], "provenance_type": "body", "text_class": "primary_performance", "is_primary_admissible": True, "reaction_family": "eNRR"}


if __name__ == "__main__":
    unittest.main()
