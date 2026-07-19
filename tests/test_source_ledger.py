from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.source_ledger import build_ordered_source_ledger


class SourceLedgerTests(unittest.TestCase):
    def test_document_loaded_with_front_matter_isolated_and_body_kept_in_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.joinpath("P1.md").write_text(
                "---\nsource_file: input_raw\\paper.pdf\nconversion_method: docling\n---\n# Title\n\n## Results\n\nNH3 evidence.", encoding="utf-8"
            )
            ledger = build_ordered_source_ledger(root)
            document = ledger.documents_by_id["P1"]
            self.assertNotIn("source_file", document["full_body_text"])
            self.assertEqual(document["document_character_count"], len(document["full_body_text"]))
            self.assertEqual(document["section_count"], len(ledger.sections_by_document["P1"]))
            self.assertEqual(document["paragraph_count"], len(ledger.paragraphs_by_document["P1"]))
            self.assertEqual(ledger.sections_by_document["P1"][0]["document_region"], "title")


if __name__ == "__main__":
    unittest.main()
