from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.source_ledger import build_ordered_source_ledger
from enh3bench.span_finder import ORDERED_SELECTION_PROFILE, find_candidate_spans


class SpanSelectionSourceOrderTests(unittest.TestCase):
    def test_top_k_is_selected_by_score_then_exported_in_source_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.joinpath("P1.md").write_text("# Paper\n\nNH3 mention.\n\n15N isotope blank control NOx.\n\nFaradaic efficiency and ammonia yield.", encoding="utf-8")
            ledger = build_ordered_source_ledger(root)
            selected = find_candidate_spans({"document_id": "P1"}, max_spans_per_document=2, selection_profile=ORDERED_SELECTION_PROFILE, source_ledger=ledger)
            self.assertEqual(len(selected), 2)
            self.assertEqual(selected, sorted(selected, key=lambda item: item["source_start_offset"]))
            self.assertTrue(all(item["selected_by_priority"] for item in selected))
            self.assertTrue(all(item["source_locator"] for item in selected))


if __name__ == "__main__":
    unittest.main()
