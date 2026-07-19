from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.document_context import build_document_context_index, resolve_span_mapping


class SpanDocumentMappingTests(unittest.TestCase):
    def test_explicit_exact_multiple_and_cross_paper_safe_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = "# Paper\n\n## Results\n\nUnique evidence.\n\nRepeated sentence.\n\n## References\n\nRepeated sentence."
            root.joinpath("P1.md").write_text(body, encoding="utf-8")
            root.joinpath("P2.md").write_text("# Other\n\nUnique evidence.", encoding="utf-8")
            index = build_document_context_index(root)
            start = index.documents_by_id["P1"]["body_text"].index("Unique evidence.")
            explicit = resolve_span_mapping({"paper_id": "P1", "document_id": "P1", "source_text": "Unique evidence.", "source_start_offset": start, "source_end_offset": start + 16}, index)
            self.assertEqual((explicit["method"], explicit["confidence"]), ("explicit_offset", "high"))
            exact = resolve_span_mapping({"paper_id": "P1", "source_text": "Unique evidence."}, index)
            self.assertEqual(exact["method"], "document_exact")
            repeated = resolve_span_mapping({"paper_id": "P1", "source_text": "Repeated sentence."}, index)
            self.assertEqual(repeated["method"], "unresolved")
            self.assertIn("multiple_exact_matches", repeated["warnings"])
            self.assertEqual(len(repeated["candidate_offsets"]), 2)
            cross = resolve_span_mapping({"paper_id": "P2", "document_id": "P1", "source_text": "Unique evidence."}, index)
            self.assertEqual(cross["method"], "unresolved")
            missing = resolve_span_mapping({"paper_id": "P1", "source_text": "Not in document"}, index)
            self.assertEqual(missing["confidence"], "unresolved")


if __name__ == "__main__":
    unittest.main()
