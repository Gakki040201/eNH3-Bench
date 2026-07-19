from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.source_ledger import build_ordered_source_ledger


class SourceLedgerSectionOrderTests(unittest.TestCase):
    def test_nested_and_repeated_headings_have_ordered_unique_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.joinpath("P1.md").write_text(
                "# Title\n\n## Abstract\n\nSummary.\n\n## Experimental\n\nMethods.\n\n### Preparation\n\nStep.\n\n## Results\n\n### Repeated\n\nOne.\n\n### Repeated\n\nTwo.", encoding="utf-8"
            )
            sections = build_ordered_source_ledger(root).sections_by_document["P1"]
            self.assertEqual([s["source_section_index"] for s in sections], list(range(1, len(sections) + 1)))
            experimental = next(s for s in sections if s["heading_text"] == "Experimental")
            preparation = next(s for s in sections if s["heading_text"] == "Preparation")
            self.assertEqual(experimental["outline_index_path"], [1])
            self.assertEqual(preparation["outline_index_path"], [1, 1])
            repeated = [s for s in sections if s["heading_text"] == "Repeated"]
            self.assertEqual([s["outline_index_path"] for s in repeated], [[2, 1], [2, 2]])
            self.assertNotEqual(repeated[0]["section_uid"], repeated[1]["section_uid"])
            self.assertEqual(preparation["parent_section_uid"], experimental["section_uid"])
            self.assertEqual(preparation["section_path"], ["Title", "Experimental", "Preparation"])


if __name__ == "__main__":
    unittest.main()
