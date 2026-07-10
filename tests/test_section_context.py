from __future__ import annotations

import unittest

from enh3bench.section_context import (
    attach_section_context_to_records,
    classify_section_heading,
    extract_markdown_section_blocks,
    infer_section_confidence,
    normalize_heading,
)


class SectionContextTests(unittest.TestCase):
    def test_normalize_spaced_abstract_heading(self) -> None:
        self.assertEqual(normalize_heading("A B S T R A C T"), "abstract")
        self.assertEqual(classify_section_heading("A B S T R A C T"), "abstract")

    def test_extract_results_heading_block(self) -> None:
        blocks = extract_markdown_section_blocks("# Title\n\n## Results\n\nNH3 FE was reported.")
        results = [block for block in blocks if block["section_type"] == "results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["section_heading"], "Results")
        self.assertEqual(results[0]["section_confidence"], "high")
        self.assertIn("Title", results[0]["section_path"])

    def test_plain_methods_heading_block(self) -> None:
        blocks = extract_markdown_section_blocks("Materials and Methods\n\nThe electrolyte was prepared.")
        self.assertEqual(blocks[0]["section_type"], "methods")
        self.assertIn(blocks[0]["section_confidence"], {"medium", "high"})

    def test_attach_markdown_context_to_record(self) -> None:
        markdown = "## Introduction\n\nNH3 background paragraph.\n\n## Results\n\nNH3 FE was 10%."
        records = [{"document_id": "D1", "source_text": "NH3 FE was 10%."}]
        attached = attach_section_context_to_records(records, {"D1": markdown})
        self.assertEqual(attached[0]["section_type"], "results")
        self.assertEqual(attached[0]["section_heading"], "Results")

    def test_docling_hierarchy_precedes_markdown_context(self) -> None:
        markdown = "## Results\n\nNH3 FE was 10%."
        records = [
            {
                "document_id": "D1",
                "source_text": "NH3 FE was 10%.",
                "hierarchy": ["Experimental"],
            }
        ]
        attached = attach_section_context_to_records(records, {"D1": markdown})
        self.assertEqual(attached[0]["section_type"], "methods")
        self.assertIn("docling_hierarchy", attached[0]["section_signals"])

    def test_infer_section_confidence_no_heading_is_low(self) -> None:
        confidence, rationale = infer_section_confidence({"section_type": "unknown"})
        self.assertEqual(confidence, "low")
        self.assertIn("body_without_section_context", rationale)


if __name__ == "__main__":
    unittest.main()
