from __future__ import annotations

import json
import tempfile
import unittest
import hashlib
from pathlib import Path

from enh3bench.cleanroom_pipeline import CleanroomPipeline
from tests.cleanroom_test_helpers import write_document


class CleanroomPipelineResumeTests(unittest.TestCase):
    def test_partial_then_resume_skips_unchanged_upstream(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            write_document(markdown)
            pipeline = CleanroomPipeline(markdown_dir=markdown, run_name="resume", cleanroom_root=root / "cleanroom")
            first = pipeline.run(to_stage="candidates")
            self.assertNotEqual(first["pipeline_status"], "completed")
            manifest_before = json.loads(pipeline.manifest_path.read_text(encoding="utf-8"))
            finished_at = manifest_before["stages"]["candidates"]["finished_at"]
            candidate_path = pipeline.run_dir / "candidates/candidate_spans.jsonl"
            candidate_hash = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
            candidate_mtime = candidate_path.stat().st_mtime_ns
            second = pipeline.run(resume=True)
            manifest_after = json.loads(pipeline.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(second["pipeline_status"], "completed")
            self.assertEqual(manifest_after["stages"]["candidates"]["finished_at"], finished_at)
            self.assertEqual(hashlib.sha256(candidate_path.read_bytes()).hexdigest(), candidate_hash)
            self.assertEqual(candidate_path.stat().st_mtime_ns, candidate_mtime)

    def test_changed_input_invalidates_downstream(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            path = write_document(markdown)
            pipeline = CleanroomPipeline(markdown_dir=markdown, run_name="changed", cleanroom_root=root / "cleanroom")
            pipeline.run(to_stage="candidates")
            path.write_text(path.read_text(encoding="utf-8") + "\nChanged input.\n", encoding="utf-8")
            manifest = pipeline._load_or_initialize_manifest()
            pipeline._invalidate_changed_stages(manifest)
            self.assertTrue(all(
                manifest["stages"][stage]["status"] == "invalidated"
                for stage in ("ingest", "documents", "source_nodes", "candidates")
            ))
            pipeline.run(resume=True)
            manifest = json.loads(pipeline.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["stages"]["validate"]["status"], "completed")


if __name__ == "__main__":
    unittest.main()
