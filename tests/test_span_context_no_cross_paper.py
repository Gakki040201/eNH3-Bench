from __future__ import annotations

import unittest

from enh3bench.span_context import build_document_span_index, get_next_spans, validate_no_cross_paper_links


class SpanContextNoCrossPaperTests(unittest.TestCase):
    def test_adjacent_query_stops_at_paper_boundary(self) -> None:
        index = build_document_span_index([
            {"paper_id": "P1", "source_span_id": "P1_S001", "source_text": "one"},
            {"paper_id": "P2", "source_span_id": "P2_S002", "source_text": "two"},
        ])
        self.assertEqual(get_next_spans(index, "P1_S001"), [])

    def test_validator_rejects_cross_paper_nested_link(self) -> None:
        with self.assertRaises(ValueError):
            validate_no_cross_paper_links({"paper_id": "P1", "linked": [{"span_id": "S2", "paper_id": "P2"}]})


if __name__ == "__main__":
    unittest.main()
