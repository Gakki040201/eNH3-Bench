from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.span_finder import find_candidate_spans  # noqa: E402


class SpanFinderTests(unittest.TestCase):
    def test_candidate_span_scoring_and_sorting(self) -> None:
        document = {
            "document_id": "P007",
            "path": "P007.md",
            "text": (
                "General background without benchmark keywords.\n\n"
                "Li-mediated N2 reduction in THF reported NH3 yield and Faradaic efficiency.\n\n"
                "A brief control paragraph mentions blank experiments."
            ),
        }
        spans = find_candidate_spans(document, max_spans_per_document=2)
        self.assertEqual(len(spans), 2)
        self.assertGreaterEqual(spans[0]["candidate_score"], spans[1]["candidate_score"])
        self.assertEqual(spans[0]["paper_id"], "P007")
        self.assertIn("Li-mediated", spans[0]["matched_keywords"])
        self.assertEqual(spans[0]["annotation_status"], "machine_drafted")

    def test_paper_id_override(self) -> None:
        document = {"document_id": "local_doc", "path": "doc.md", "text": "NH3 yield was reported."}
        spans = find_candidate_spans(document, paper_id="P009")
        self.assertEqual(spans[0]["paper_id"], "P009")


if __name__ == "__main__":
    unittest.main()
