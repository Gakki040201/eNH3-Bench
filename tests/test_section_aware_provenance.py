from __future__ import annotations

import unittest

from enh3bench.document_provenance import attach_provenance_to_records, extract_provenance_from_docling_json
from enh3bench.span_finder import find_candidate_spans


class SectionAwareProvenanceTests(unittest.TestCase):
    def test_results_heading_candidate_gets_section_confidence(self) -> None:
        document = {
            "document_id": "P1",
            "text": "## Results\n\nThe catalyst produced NH3 with FE and yield.",
        }
        span = find_candidate_spans(document)[0]
        self.assertEqual(span["section_type"], "results")
        self.assertIn(span["section_confidence"], {"medium", "high"})
        attached = attach_provenance_to_records([span])[0]
        self.assertEqual(attached["provenance_type"], "results")
        self.assertIn(attached["provenance_confidence"], {"medium", "high"})

    def test_methods_heading_candidate_gets_methods_context(self) -> None:
        document = {
            "document_id": "P1",
            "text": "## Materials and Methods\n\nThe electrolyte and flow cell control were prepared.",
        }
        span = find_candidate_spans(document)[0]
        attached = attach_provenance_to_records([span])[0]
        self.assertEqual(attached["section_type"], "methods")
        self.assertEqual(attached["provenance_type"], "methods")
        self.assertIn(attached["provenance_confidence"], {"medium", "high"})

    def test_abstract_heading_is_high_confidence(self) -> None:
        records = [
            {
                "span_id": "S1",
                "source_text": "The abstract reports NH3 yield and Faradaic efficiency.",
                "section_heading": "Abstract",
            }
        ]
        attached = attach_provenance_to_records(records)[0]
        self.assertEqual(attached["provenance_type"], "abstract")
        self.assertEqual(attached["provenance_confidence"], "high")

    def test_introduction_context_remains_body_medium(self) -> None:
        records = [
            {
                "span_id": "S1",
                "source_text": "The introduction reviews prior NH3 FE reports.",
                "section_heading": "Introduction",
            }
        ]
        attached = attach_provenance_to_records(records)[0]
        self.assertEqual(attached["section_type"], "introduction")
        self.assertEqual(attached["provenance_type"], "body")
        self.assertEqual(attached["provenance_confidence"], "medium")

    def test_reference_under_references_remains_reference_high(self) -> None:
        records = [
            {
                "span_id": "S1",
                "source_text": "[1] Smith et al. Journal 12, 44-50 (2020). doi:10.1000/a\n"
                "[2] Wang et al. Journal 13, 50-60 (2021). doi:10.1000/b",
                "section_heading": "References",
            }
        ]
        attached = attach_provenance_to_records(records)[0]
        self.assertEqual(attached["provenance_type"], "reference")
        self.assertEqual(attached["provenance_confidence"], "high")
        self.assertTrue(attached["is_reject_or_low_trust"])

    def test_figure_caption_under_results_remains_caption(self) -> None:
        records = [
            {
                "span_id": "S1",
                "source_text": "Fig. 2. NH3 yield and FE at different potentials.",
                "section_heading": "Results",
            }
        ]
        attached = attach_provenance_to_records(records)[0]
        self.assertEqual(attached["section_type"], "results")
        self.assertEqual(attached["provenance_type"], "figure_caption")
        self.assertTrue(attached["is_secondary_or_context"])

    def test_no_heading_remains_body_low(self) -> None:
        records = [{"span_id": "S1", "source_text": "The catalyst produced NH3 with FE."}]
        attached = attach_provenance_to_records(records)[0]
        self.assertEqual(attached["provenance_type"], "body")
        self.assertEqual(attached["provenance_confidence"], "low")

    def test_docling_section_hierarchy_beats_heuristic_markdown(self) -> None:
        data = {
            "document_id": "D1",
            "texts": [
                {
                    "id": "b1",
                    "label": "text",
                    "text": "The cell used electrolyte and controls.",
                    "section": "Experimental",
                    "hierarchy": ["Experimental"],
                }
            ],
        }
        record = extract_provenance_from_docling_json(data, paper_id="P1")[0]
        self.assertEqual(record["section_type"], "methods")
        self.assertEqual(record["provenance_type"], "methods")
        self.assertEqual(record["provenance_confidence"], "high")


if __name__ == "__main__":
    unittest.main()
