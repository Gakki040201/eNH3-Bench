from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from enh3bench.document_context import build_document_context_index, get_local_paragraph_context, get_section_chunk


class DocumentContextTests(unittest.TestCase):
    def test_loader_called_once_front_matter_isolated_and_offsets_are_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            root.joinpath("P1.md").write_text(
                "---\nsource_file: input_raw\\paper.pdf\nconversion_method: docling\n---\n# Title\n\n## Results\n\nFirst paragraph.\n\nSecond NH3 paragraph.",
                encoding="utf-8",
            )
            from enh3bench.source_ledger import load_markdown_documents as real_loader
            with patch("enh3bench.source_ledger.load_markdown_documents", wraps=real_loader) as loader:
                index = build_document_context_index(root)
                self.assertEqual(loader.call_count, 1)
            document = index.documents_by_id["P1"]
            self.assertNotIn("source_file", document["body_text"])
            paragraph = next(p for p in document["paragraph_blocks"] if "Second" in p["text"])
            self.assertEqual(document["body_text"][paragraph["start_offset"]:paragraph["end_offset"]], paragraph["text"])
            self.assertEqual(paragraph["section_heading"], "Results")
            record = {"paper_id": "P1", "document_id": "P1", "source_start_offset": paragraph["start_offset"], "source_end_offset": paragraph["end_offset"], "source_text": paragraph["text"]}
            local = get_local_paragraph_context(record, index)
            self.assertEqual(local["target_paragraph"]["paragraph_id"], paragraph["paragraph_id"])
            chunk = get_section_chunk(record, index, maximum_characters=30)
            self.assertLessEqual(len(chunk["section_chunk"]), 30)


if __name__ == "__main__":
    unittest.main()
