from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from enh3bench.cleanroom_pipeline import CleanroomPipeline
from enh3bench.cleanroom_schema import CLEANROOM_STAGES
from tests.cleanroom_test_helpers import write_document


class CleanroomManifestTests(unittest.TestCase):
    def test_completed_manifest_requires_all_stages(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            write_document(markdown)
            pipeline = CleanroomPipeline(markdown_dir=markdown, run_name="manifest", cleanroom_root=root / "cleanroom")
            final = pipeline.run()
            stages = json.loads(pipeline.manifest_path.read_text(encoding="utf-8"))["stages"]
            self.assertEqual(final["pipeline_status"], "completed")
            self.assertTrue(all(stages[name]["status"] == "completed" for name in CLEANROOM_STAGES))

    def test_partial_manifest_is_not_completed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            write_document(markdown)
            pipeline = CleanroomPipeline(markdown_dir=markdown, run_name="partial", cleanroom_root=root / "cleanroom")
            final = pipeline.run(to_stage="source_nodes")
            self.assertEqual(final["pipeline_status"], "partial")

    def test_failed_stage_cannot_leave_completed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            write_document(markdown)
            pipeline = CleanroomPipeline(markdown_dir=markdown, run_name="failed", cleanroom_root=root / "cleanroom")

            def fail_documents():
                raise RuntimeError("deliberate stage failure")

            pipeline._stage_documents = fail_documents
            with self.assertRaises(RuntimeError):
                pipeline.run()
            final = json.loads(pipeline.final_manifest_path.read_text(encoding="utf-8"))
            stages = json.loads(pipeline.manifest_path.read_text(encoding="utf-8"))["stages"]
            self.assertEqual(final["pipeline_status"], "failed")
            self.assertEqual(stages["documents"]["status"], "failed")
            self.assertIn("deliberate stage failure", stages["documents"]["errors"][0])


if __name__ == "__main__":
    unittest.main()
