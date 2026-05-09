from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.markdown_converter import convert_directory, convert_local_document  # noqa: E402


class MarkdownConverterTests(unittest.TestCase):
    def test_md_conversion_adds_header_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source = base / "paper.md"
            output_dir = base / "out"
            source.write_text("NH3 yield paragraph.", encoding="utf-8")
            result = convert_local_document(source, output_dir)
            self.assertEqual(result["status"], "converted")
            output_text = Path(result["output_path"]).read_text(encoding="utf-8")
            self.assertIn("human_verification_required: true", output_text)
            self.assertIn("NH3 yield paragraph.", output_text)

    def test_md_with_header_is_copied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source = base / "paper.md"
            source.write_text("---\nsource_file: existing\n---\n\nBody.", encoding="utf-8")
            result = convert_local_document(source, base / "out")
            self.assertEqual(result["status"], "copied")
            self.assertIn("Body.", Path(result["output_path"]).read_text(encoding="utf-8"))

    def test_txt_conversion_works(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source = base / "paper.txt"
            source.write_text("Faradaic efficiency was 62%.", encoding="utf-8")
            result = convert_local_document(source, base / "out")
            self.assertEqual(result["status"], "converted")
            self.assertEqual(Path(result["output_path"]).suffix, ".md")
            self.assertIn("txt_to_markdown", Path(result["output_path"]).read_text(encoding="utf-8"))

    def test_pdf_returns_unsupported_without_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "paper.pdf"
            source.write_bytes(b"%PDF placeholder")
            result = convert_local_document(source, Path(temp_dir) / "out")
            self.assertEqual(result["status"], "unsupported")
            self.assertIsNone(result["output_path"])
            self.assertIn("PDF conversion is deferred", result["message"])

    def test_convert_directory_skips_hidden_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / ".hidden.md").write_text("NH3 hidden.", encoding="utf-8")
            (base / "visible.txt").write_text("NH3 visible.", encoding="utf-8")
            results = convert_directory(base, base / "out")
            self.assertEqual(len(results), 1)
            self.assertIn("visible.txt", results[0]["input_path"])


if __name__ == "__main__":
    unittest.main()
