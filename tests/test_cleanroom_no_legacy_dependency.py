from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from enh3bench.cleanroom_pipeline import CleanroomPipeline
from enh3bench.cleanroom_output_check import compare_normalized_runs
from enh3bench.cleanroom_schema import read_jsonl
from tests.cleanroom_test_helpers import write_document


class CleanroomNoLegacyDependencyTests(unittest.TestCase):
    def test_cleanroom_pipeline_runs_without_legacy_runtime_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            write_document(markdown)
            pipeline = CleanroomPipeline(markdown_dir=markdown, run_name="no_legacy", cleanroom_root=root / "cleanroom")
            final = pipeline.run()
            self.assertEqual(final["pipeline_status"], "completed")
            self.assertTrue((pipeline.run_dir / "database/final_database.jsonl").exists())
            self.assertEqual(len(read_jsonl(pipeline.run_dir / "papers/paper_records.jsonl")), 1)

    def test_cleanroom_pipeline_does_not_import_legacy_semantic_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            write_document(markdown)
            legacy = root / "data/boundary_ledger/wrong/evidence_bundles.jsonl"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(json.dumps({"semantic_claim_type": "deliberately_wrong_label"}) + "\n", encoding="utf-8")
            pipeline = CleanroomPipeline(markdown_dir=markdown, run_name="ignore_legacy", cleanroom_root=root / "cleanroom")
            pipeline.run()
            values = {item["semantic_claim_type"] for item in read_jsonl(pipeline.run_dir / "semantics/semantic_spans.jsonl")}
            self.assertNotIn("deliberately_wrong_label", values)

    def test_compare_run_is_report_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            write_document(markdown)
            legacy = root / "boundary_ledger/old_run/evidence_bundles.jsonl"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(json.dumps({"semantic_claim_type": "deliberately_wrong_label"}) + "\n", encoding="utf-8")
            normal = CleanroomPipeline(markdown_dir=markdown, run_name="normal", cleanroom_root=root / "cleanroom")
            comparison = CleanroomPipeline(
                markdown_dir=markdown,
                run_name="comparison",
                cleanroom_root=root / "cleanroom",
                compare_run="old_run",
            )
            normal.run()
            comparison.run()
            report = json.loads((comparison.run_dir / "reports/legacy_comparison.json").read_text(encoding="utf-8"))
            self.assertFalse(report["legacy_semantics_imported"])
            self.assertTrue(compare_normalized_runs(normal.run_dir, comparison.run_dir)["reproducibility_match"])


if __name__ == "__main__":
    unittest.main()
