from __future__ import annotations

import unittest

from enh3bench.evidence_linking import classify_link_type, link_supporting_evidence


class EvidenceLinkingLowTrustTests(unittest.TestCase):
    def test_reference_caption_and_review_table_are_context_only(self) -> None:
        target = _record("P1_S001", "body", "primary_performance")
        candidates = [
            _record("P1_S002", "reference", "reference_list"),
            _record("P1_S003", "figure_caption", "figure_caption"),
            _record("P1_S004", "review_table", "review_table"),
        ]
        for candidate in candidates:
            self.assertEqual(classify_link_type(candidate), "context_hint")
        result = link_supporting_evidence(target, [target, *candidates])
        self.assertTrue(result["context_hint"])
        self.assertTrue(all(item["context_only"] and not item["primary_support"] for item in result["context_hint"]))


def _record(span_id: str, provenance: str, text_class: str) -> dict[str, object]:
    return {"paper_id": "P1", "source_span_id": span_id, "source_text": "FE 50% and 15N", "provenance_type": provenance, "text_class": text_class, "is_primary_admissible": provenance == "body"}


if __name__ == "__main__":
    unittest.main()
