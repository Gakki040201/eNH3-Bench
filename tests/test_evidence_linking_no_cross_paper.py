from __future__ import annotations

import unittest

from enh3bench.evidence_linking import link_supporting_evidence, score_link


class EvidenceLinkingNoCrossPaperTests(unittest.TestCase):
    def test_cross_paper_candidate_is_rejected(self) -> None:
        target = {"paper_id": "P1", "source_span_id": "P1_S001", "source_text": "FE 10%"}
        other = {"paper_id": "P2", "source_span_id": "P2_S001", "source_text": "15N isotope"}
        self.assertEqual(score_link(target, other), float("-inf"))
        result = link_supporting_evidence(target, [target, other])
        self.assertEqual(result["total_links"], 0)
        self.assertIn("cross_paper_candidate_rejected:P2_S001", result["warnings"])


if __name__ == "__main__":
    unittest.main()
