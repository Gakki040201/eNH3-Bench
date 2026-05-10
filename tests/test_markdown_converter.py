from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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
            self.assertEqual(result["format"], ".md")
            self.assertIsNone(result["pages"])
            self.assertIsInstance(result["characters"], int)
            output_text = Path(result["output_path"]).read_text(encoding="utf-8")
            self.assertIn("human_verification_required: true", output_text)
            self.assertIn("source_format: .md", output_text)
            self.assertIn("copyright_note:", output_text)
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
            source.write_text(
                "Faradaic efficiency was 62%.\n\nNH3 yield was reported.",
                encoding="utf-8",
            )
            result = convert_local_document(source, base / "out")
            self.assertEqual(result["status"], "converted")
            self.assertEqual(Path(result["output_path"]).suffix, ".md")
            output_text = Path(result["output_path"]).read_text(encoding="utf-8")
            self.assertIn("txt_to_markdown", output_text)
            self.assertIn("Faradaic efficiency was 62%.\n\nNH3 yield was reported.", output_text)

    def test_pdf_returns_unsupported_without_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "paper.pdf"
            source.write_bytes(b"%PDF placeholder")
            with mock.patch("enh3bench.markdown_converter.has_pymupdf", return_value=False):
                result = convert_local_document(source, Path(temp_dir) / "out")
            self.assertEqual(result["status"], "unsupported")
            self.assertIsNone(result["output_path"])
            self.assertIn("Install pymupdf", result["message"])

    def test_docx_returns_unsupported_without_python_docx(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "paper.docx"
            source.write_bytes(b"docx placeholder")
            with mock.patch("enh3bench.markdown_converter.has_python_docx", return_value=False):
                result = convert_local_document(source, Path(temp_dir) / "out")
            self.assertEqual(result["status"], "unsupported")
            self.assertIsNone(result["output_path"])
            self.assertEqual(result["message"], "Install python-docx to convert DOCX files.")

    def test_convert_directory_skips_hidden_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / ".hidden.md").write_text("NH3 hidden.", encoding="utf-8")
            (base / "visible.txt").write_text("NH3 visible.", encoding="utf-8")
            results = convert_directory(base, base / "out")
            self.assertEqual(len(results), 1)
            self.assertIn("visible.txt", results[0]["input_path"])

    def test_convert_directory_continues_when_one_file_is_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / "visible.txt").write_text("NH3 visible.", encoding="utf-8")
            (base / "paper.pdf").write_bytes(b"%PDF placeholder")
            with mock.patch("enh3bench.markdown_converter.has_pymupdf", return_value=False):
                results = convert_directory(base, base / "out")
            statuses = sorted(result["status"] for result in results)
            self.assertEqual(statuses, ["converted", "unsupported"])

    def test_mocked_pymupdf_text_pdf_conversion(self) -> None:
        class FakePage:
            def __init__(self, text: str) -> None:
                self._text = text

            def get_text(self, mode: str) -> str:
                if mode != "text":
                    raise AssertionError(mode)
                return self._text

        class FakeDocument:
            def __iter__(self):
                return iter([FakePage("NH3 yield on page one."), FakePage("15N isotope page two.")])

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback) -> None:
                return None

        class FakeFitz:
            @staticmethod
            def open(path: str) -> FakeDocument:
                return FakeDocument()

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source = base / "paper.pdf"
            source.write_bytes(b"%PDF placeholder")
            with (
                mock.patch("enh3bench.markdown_converter.has_pymupdf", return_value=True),
                mock.patch.dict(sys.modules, {"fitz": FakeFitz}),
            ):
                result = convert_local_document(source, base / "out")
            self.assertEqual(result["status"], "converted")
            self.assertEqual(result["pages"], 2)
            output_text = Path(result["output_path"]).read_text(encoding="utf-8")
            self.assertIn("## Page 1", output_text)
            self.assertIn("## Page 2", output_text)
            self.assertIn("NH3 yield on page one.", output_text)


if __name__ == "__main__":
    unittest.main()
