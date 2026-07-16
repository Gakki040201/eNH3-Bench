from __future__ import annotations

import unittest

from enh3bench.document_scope import assess_document_genre, assess_document_scope


class DocumentScopeTests(unittest.TestCase):
    def test_document_genre_is_independent_from_span_claim_scope(self) -> None:
        genre = assess_document_genre({
            "paper_title": "A Perspective and Roadmap for Nitrogen Electroreduction",
            "article_type": "perspective",
            "document_headings": ["Introduction", "Outlook"],
            "document_body_text": "We recommend a common validation protocol.",
        })
        scope = assess_document_scope(_record("We recommend a common validation protocol.", "introduction"))
        self.assertEqual(genre["document_genre"], "perspective")
        self.assertEqual(scope["span_claim_scope"], "target_document")

    def test_review_genre_uses_title_and_article_type(self) -> None:
        result = assess_document_genre({
            "paper_title": "Oxygen vacancies in electrocatalysis: a critical review",
            "article_type": "review article",
            "document_headings": ["Overview", "Mechanisms"],
        })
        self.assertEqual(result["document_genre"], "review")
        self.assertFalse(result["document_genre_primary_applicable"])

    def test_methods_results_and_current_study_language_identify_primary_research(self) -> None:
        result = assess_document_genre({
            "paper_abstract": "Here we report a catalyst and its measured ammonia yield.",
            "document_headings": ["Methods", "Results"],
            "document_body_text": "In this work we prepared samples and measured current density.",
        })
        self.assertEqual(result["document_genre"], "primary_research")
        self.assertTrue(result["document_genre_primary_applicable"])

    def test_document_genre_article_type_categories_are_canonical(self) -> None:
        cases = {
            "experimental protocol": "protocol_or_guideline",
            "computational study": "computational_study",
            "techno economic analysis": "process_or_tea",
            "data descriptor": "dataset_or_metadata",
        }
        for article_type, expected in cases.items():
            with self.subTest(article_type=article_type):
                self.assertEqual(
                    assess_document_genre({"article_type": article_type})["document_genre"],
                    expected,
                )

    def test_cited_performance_in_introduction_is_external(self) -> None:
        result = assess_document_scope(_record("Smith et al. reported a Faradaic efficiency of 20%.", "introduction"))
        self.assertEqual(result["document_scope"], "external_or_cited_work")
        self.assertEqual(result["span_claim_scope"], "external_or_cited_work")
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
