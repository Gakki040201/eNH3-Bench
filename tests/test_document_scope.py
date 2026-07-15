from __future__ import annotations

import unittest

from enh3bench.document_scope import assess_document_scope


class DocumentScopeTests(unittest.TestCase):
    def test_cited_performance_in_introduction_is_external(self) -> None:
        result = assess_document_scope(_record("Smith et al. reported a Faradaic efficiency of 20%.", "introduction"))
        self.assertEqual(result["document_scope"], "external_or_cited_work")
        self.assertFalse(result["document_scope_primary_applicable"])

    def test_current_work_cue_establishes_target_document_scope(self) -> None:
        result = assess_document_scope(_record("In this work, we report a Faradaic efficiency of 20%.", "introduction"))
        self.assertEqual(result["document_scope"], "target_document")
        self.assertTrue(result["document_scope_primary_applicable"])

    def test_we_reported_is_not_misread_as_an_external_author_name(self) -> None:
        result = assess_document_scope(_record("We reported a Faradaic efficiency of 20%.", "introduction"))
        self.assertEqual(result["document_scope"], "target_document")

    def test_passive_results_statement_defaults_to_target_document(self) -> None:
        result = assess_document_scope(_record("Ammonia was quantified by NMR.", "results"))
        self.assertEqual(result["document_scope"], "target_document")

    def test_unowned_introduction_statement_is_not_primary(self) -> None:
        result = assess_document_scope(_record("Faradaic efficiency is an important metric.", "introduction"))
        self.assertEqual(result["document_scope"], "unclear")
        self.assertFalse(result["document_scope_primary_applicable"])

    def test_reference_is_secondary_context(self) -> None:
        record = _record("1. Example citation.", "references")
        record.update({"provenance_type": "reference", "text_class": "reference_list"})
        self.assertEqual(assess_document_scope(record)["document_scope"], "secondary_context")


def _record(text: str, section: str) -> dict[str, object]:
    return {
        "source_text": text,
        "effective_section_type": section,
        "provenance_type": "body",
        "text_class": "primary_performance",
    }


if __name__ == "__main__":
    unittest.main()
