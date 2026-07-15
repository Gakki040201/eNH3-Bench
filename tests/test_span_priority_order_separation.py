from __future__ import annotations

import unittest

from enh3bench.source_ledger import sort_spans_by_priority, sort_spans_by_source_order


class SpanPriorityOrderSeparationTests(unittest.TestCase):
    def test_priority_and_source_views_are_independent(self) -> None:
        records = [
            {"source_span_id": "S1", "source_start_offset": 10, "candidate_priority_rank": 2, "candidate_score": 1},
            {"source_span_id": "S2", "source_start_offset": 20, "candidate_priority_rank": 1, "candidate_score": 9},
        ]
        self.assertEqual([r["source_span_id"] for r in sort_spans_by_source_order(records)], ["S1", "S2"])
        self.assertEqual([r["source_span_id"] for r in sort_spans_by_priority(records)], ["S2", "S1"])


if __name__ == "__main__":
    unittest.main()
