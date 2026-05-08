from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.document_loader import load_markdown_documents, split_into_paragraphs  # noqa: E402


class DocumentLoaderTests(unittest.TestCase):
    def test_load_markdown_documents(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            (directory / "P001.md").write_text("# Title\n\nNH3 yield paragraph.", encoding="utf-8")
            (directory / "notes.txt").write_text("ignored", encoding="utf-8")
            documents = load_markdown_documents(directory)
            self.assertEqual(len(documents), 1)
            self.assertEqual(documents[0]["document_id"], "P001")
            self.assertIn("NH3 yield", documents[0]["text"])

    def test_split_into_paragraphs_ignores_empty_blocks(self) -> None:
        paragraphs = split_into_paragraphs("First paragraph.\n\n\nSecond paragraph.\n\n  ")
        self.assertEqual(paragraphs, ["First paragraph.", "Second paragraph."])


if __name__ == "__main__":
    unittest.main()
