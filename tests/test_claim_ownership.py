from __future__ import annotations

import unittest

from enh3bench.claim_ownership import assess_claim_ownership
from enh3bench.document_scope import assess_document_scope


class ClaimOwnershipTests(unittest.TestCase):
    def test_external_attribution_blocks_target_author_ownership(self) -> None:
        record = _record("Jones and co-workers demonstrated an ammonia yield of 10 mmol h-1.", "introduction")
        scope = assess_document_scope(record)
        result = assess_claim_ownership(record, scope)
        self.assertEqual(result["claim_ownership"], "external_or_cited_authors")
        self.assertFalse(result["claim_ownership_primary_applicable"])

    def test_current_work_cue_assigns_target_authors(self) -> None:
        record = _record("Here we demonstrate an ammonia yield of 10 mmol h-1.", "introduction")
        result = assess_claim_ownership(record, assess_document_scope(record))
        self.assertEqual(result["claim_ownership"], "target_authors")
        self.assertTrue(result["claim_ownership_primary_applicable"])

    def test_first_person_reported_claim_remains_target_owned(self) -> None:
        record = _record("We reported an ammonia yield of 10 mmol h-1.", "introduction")
        result = assess_claim_ownership(record, assess_document_scope(record))
        self.assertEqual(result["claim_ownership"], "target_authors")

    def test_results_scope_supports_passive_target_author_statement(self) -> None:
        record = _record("The Faradaic efficiency was 20%.", "results")
        result = assess_claim_ownership(record, assess_document_scope(record))
        self.assertEqual(result["claim_ownership"], "target_authors")

    def test_secondary_document_scope_dominates_first_person_words(self) -> None:
        record = _record("Our study of ammonia electrosynthesis. Journal citation.", "references")
        record.update({"provenance_type": "reference", "text_class": "reference_list"})
        result = assess_claim_ownership(record, assess_document_scope(record))
        self.assertEqual(result["claim_ownership"], "secondary_context")
        self.assertFalse(result["claim_ownership_primary_applicable"])


def _record(text: str, section: str) -> dict[str, object]:
    return {
        "source_text": text,
        "effective_section_type": section,
        "provenance_type": "body",
        "text_class": "primary_performance",
    }


if __name__ == "__main__":
    unittest.main()
