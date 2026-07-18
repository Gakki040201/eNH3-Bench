from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import enh3bench.cleanroom_pipeline as cleanroom_pipeline_module

from enh3bench.cleanroom_output_check import validate_cleanroom_run
from enh3bench.cleanroom_pipeline import CleanroomPipeline
from enh3bench.cleanroom_schema import read_jsonl
from tests.cleanroom_test_helpers import write_fixture_corpus


class CleanroomPipelineTests(unittest.TestCase):
    def test_fixture_corpus_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            write_fixture_corpus(markdown)
            pipeline = CleanroomPipeline(markdown_dir=markdown, run_name="fixture", cleanroom_root=root / "cleanroom")
            final = pipeline.run()
            self.assertEqual(final["pipeline_status"], "completed")
            documents = read_jsonl(pipeline.run_dir / "documents/document_ledger.jsonl")
            papers = read_jsonl(pipeline.run_dir / "papers/paper_records.jsonl")
            semantics = read_jsonl(pipeline.run_dir / "semantics/semantic_spans.jsonl")
            self.assertEqual(len(documents), 10)
            self.assertEqual(len(papers), 10)
            self.assertFalse(any(item["primary_semantic_eligibility"] for item in semantics if item["document_genre"] == "review"))
            self.assertFalse(any(item["primary_semantic_eligibility"] for item in semantics if item["document_id"] == "off_target"))
            self.assertFalse(any(
                item["ammonia_quantification_signal"]
                for item in semantics
                if item["document_id"] == "trap_only" and item["gas_purification_trap_signal"]
            ))
            self.assertFalse(any(
                item["claim_ownership"] == "target_authors"
                for item in semantics
                if item["document_id"] == "external_cited" and "Smith et al." in item["source_text"]
            ))
            self.assertIn("unclear", {item["document_reaction_family"] for item in documents})
            document_index = {item["document_id"]: item for item in documents}
            self.assertTrue(all(
                item["document_genre"] == document_index[item["document_id"]]["document_genre"]
                and item["document_reaction_family"] == document_index[item["document_id"]]["document_reaction_family"]
                and item["document_reaction_family_signals"] == document_index[item["document_id"]]["document_reaction_family_signals"]
                for item in semantics
            ))
            self.assertFalse(any(
                item["primary_semantic_eligibility"]
                for item in semantics
                if item["effective_reaction_family"] in {"unclear", "mixed"}
            ))
            diagnostics = validate_cleanroom_run(pipeline.run_dir)["counts"]
            self.assertEqual(diagnostics["cross_paper_link_count"], 0)

    def test_document_assessment_runs_once_per_document(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            write_fixture_corpus(markdown)
            original = cleanroom_pipeline_module.assess_document_reaction_family
            with patch.object(cleanroom_pipeline_module, "assess_document_reaction_family", wraps=original) as assessment:
                pipeline = CleanroomPipeline(markdown_dir=markdown, run_name="assessment_cache", cleanroom_root=root / "cleanroom")
                pipeline.run()
            self.assertEqual(assessment.call_count, 10)

    def test_evidence_link_ids_are_present_and_unique(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            write_fixture_corpus(markdown)
            pipeline = CleanroomPipeline(markdown_dir=markdown, run_name="link_ids", cleanroom_root=root / "cleanroom")
            pipeline.run()
            links = read_jsonl(pipeline.run_dir / "links/evidence_links.jsonl")
            identifiers = [item["evidence_link_id"] for item in links]
            self.assertTrue(identifiers)
            self.assertTrue(all(value.startswith("CRL15_") for value in identifiers))
            self.assertEqual(len(identifiers), len(set(identifiers)))

    def test_all_output_schemas_validate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            write_fixture_corpus(markdown)
            pipeline = CleanroomPipeline(markdown_dir=markdown, run_name="schema", cleanroom_root=root / "cleanroom")
            pipeline.run()
            self.assertEqual(validate_cleanroom_run(pipeline.run_dir)["result"], "PASS")

    def test_no_candidate_document_still_has_paper_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            markdown.mkdir()
            (markdown / "neutral.md").write_text("# Neutral\n\n## Results\n\nA plain sentence.", encoding="utf-8")
            pipeline = CleanroomPipeline(markdown_dir=markdown, run_name="neutral", cleanroom_root=root / "cleanroom")
            pipeline.run()
            paper = read_jsonl(pipeline.run_dir / "papers/paper_records.jsonl")[0]
            self.assertEqual(paper["candidate_span_count"], 0)
            self.assertIn(paper["paper_admissibility_status"], {"insufficient_evidence", "needs_review"})


if __name__ == "__main__":
    unittest.main()
