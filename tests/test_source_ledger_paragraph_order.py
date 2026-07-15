from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.source_ledger import build_ordered_source_ledger


class SourceLedgerParagraphOrderTests(unittest.TestCase):
    def test_paragraph_order_links_offsets_and_relative_positions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.joinpath("P1.md").write_text("Preface without heading.\n\n# Results\n\nFirst.\n\nSecond.", encoding="utf-8")
            ledger = build_ordered_source_ledger(root)
            paragraphs = ledger.paragraphs_by_document["P1"]
            self.assertEqual([p["paragraph_global_index"] for p in paragraphs], list(range(1, len(paragraphs) + 1)))
            self.assertEqual(paragraphs[1]["previous_paragraph_uid"], paragraphs[0]["paragraph_uid"])
            self.assertEqual(paragraphs[1]["next_paragraph_uid"], paragraphs[2]["paragraph_uid"])
            self.assertTrue(all(0 <= p["document_relative_position"] <= 1 for p in paragraphs))
            self.assertTrue(all(0 <= p["section_relative_position"] <= 1 for p in paragraphs))
            self.assertEqual(paragraphs[0]["document_region"], "unknown")


if __name__ == "__main__":
    unittest.main()
