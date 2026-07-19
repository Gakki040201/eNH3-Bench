from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.source_ledger import attach_source_coordinates_to_spans, build_ordered_source_ledger


class SourceLocatorTests(unittest.TestCase):
    def test_unknown_sections_are_retained_and_span_locators_are_unique(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.joinpath("P1.md").write_text("NH3 evidence before headings.\n\n# Results\n\nLater evidence.", encoding="utf-8")
            ledger = build_ordered_source_ledger(root)
            body = ledger.documents_by_id["P1"]["full_body_text"]
            start = body.index("NH3 evidence")
            records = [
                {"paper_id": "P1", "document_id": "P1", "source_span_id": f"P1_S00{i}", "source_text": "NH3 evidence before headings.", "source_start_offset": start, "source_end_offset": start + 30}
                for i in (1, 2)
            ]
            attached = attach_source_coordinates_to_spans(records, ledger)
            self.assertTrue(all("::SECUNK" in r["source_locator"] for r in attached))
            self.assertEqual(len({r["source_locator"] for r in attached}), 2)
            self.assertTrue(all(r["source_order_key"] for r in attached))


if __name__ == "__main__":
    unittest.main()
