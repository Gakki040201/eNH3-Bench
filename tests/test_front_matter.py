from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.document_loader import load_markdown_documents
from enh3bench.front_matter import (
    is_repository_cover_page_text,
    make_front_matter_records,
    split_yaml_front_matter,
    strip_conversion_front_matter,
)
from enh3bench.provenance_rules import contains_mixed_front_matter_and_body, infer_provenance_from_text
from enh3bench.span_finder import find_candidate_spans


class FrontMatterTests(unittest.TestCase):
    def test_yaml_front_matter_and_title_abstract_is_split(self) -> None:
        text = (
            "---\n"
            "source_file: input_raw\\paper.pdf\n"
            "source_format: .pdf\n"
            "conversion_method: docling\n"
            "---\n"
            "Title\n\nAbstract\nNH3 yield was reported."
        )
        metadata, body = split_yaml_front_matter(text)
        self.assertIsNotNone(metadata)
        self.assertIn("source_file", str(metadata))
        self.assertTrue(body.startswith("Title"))
        result = strip_conversion_front_matter(text)
        self.assertTrue(result["metadata_removed"])
        self.assertIn("Abstract", result["body_text"])

    def test_yaml_without_known_metadata_keys_is_not_stripped(self) -> None:
        text = "---\ntitle: not conversion metadata\n---\nAbstract\nNH3 yield."
        metadata, body = split_yaml_front_matter(text)
        self.assertIsNone(metadata)
        self.assertEqual(body, text)

    def test_repository_cover_page_detected_with_multiple_signals(self) -> None:
        text = "Research Online\nUniversity of Wollongong\nRecommended Citation\nGeneral rights"
        self.assertTrue(is_repository_cover_page_text(text))

    def test_repository_cover_page_with_abstract_splits(self) -> None:
        text = (
            "Research Online\n"
            "University of Wollongong\n"
            "Recommended Citation\n"
            "General rights\n\n"
            "Abstract\nThis paper reports ammonia synthesis."
        )
        result = strip_conversion_front_matter(text)
        self.assertTrue(result["repository_cover_removed"])
        self.assertIn("Recommended Citation", str(result["repository_cover_text"]))
        self.assertTrue(str(result["body_text"]).startswith("Abstract"))

    def test_plain_scientific_abstract_remains_unchanged(self) -> None:
        text = "Abstract\nThe catalyst produced NH3 with Faradaic efficiency."
        result = strip_conversion_front_matter(text)
        self.assertFalse(result["metadata_removed"])
        self.assertFalse(result["repository_cover_removed"])
        self.assertEqual(result["body_text"], text)

    def test_make_front_matter_records_creates_low_trust_records(self) -> None:
        result = {
            "metadata_text": "source_file: input_raw\\paper.pdf",
            "repository_cover_text": "Research Online\nGeneral rights",
        }
        records = make_front_matter_records("D1", "P1", result)
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record["is_reject_or_low_trust"] for record in records))
        self.assertEqual(records[0]["provenance_type"], "metadata")
        self.assertEqual(records[1]["provenance_type"], "front_matter")

    def test_span_finder_does_not_emit_candidates_from_yaml_metadata_text(self) -> None:
        document = {
            "document_id": "P1",
            "text": (
                "---\n"
                "source_file: input_raw\\NH3_FE_control.pdf\n"
                "conversion_method: docling\n"
                "---\n"
                "Title only\n\nNo benchmark terms here."
            ),
        }
        spans = find_candidate_spans(document)
        self.assertEqual(spans, [])

    def test_provenance_rules_detect_mixed_front_matter_body(self) -> None:
        text = (
            "---\n"
            "source_file: input_raw\\paper.pdf\n"
            "conversion_method: docling\n"
            "---\n"
            "Abstract\nThe catalyst produced NH3 with Faradaic efficiency."
        )
        self.assertTrue(contains_mixed_front_matter_and_body(text))
        result = infer_provenance_from_text(text)
        self.assertIn("mixed_front_matter_body_detected", result["signals"])
        self.assertNotIn(result["provenance_type"], {"metadata", "copyright_note"})

    def test_old_documents_without_front_matter_still_load_normally(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            (directory / "P1.md").write_text("Abstract\nNH3 yield was reported.", encoding="utf-8")
            documents = load_markdown_documents(directory)
            self.assertEqual(len(documents), 1)
            self.assertIn("NH3 yield", documents[0]["text"])
            self.assertFalse(documents[0]["metadata_removed"])


if __name__ == "__main__":
    unittest.main()
