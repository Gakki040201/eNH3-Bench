from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.cleanroom_output_check import validate_cleanroom_run
from enh3bench.cleanroom_pipeline import CleanroomPipeline
from tests.cleanroom_test_helpers import write_document


class CleanroomOutputCheckTests(unittest.TestCase):
    def test_valid_run_has_zero_safety_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            write_document(markdown)
            pipeline = CleanroomPipeline(markdown_dir=markdown, run_name="checked", cleanroom_root=root / "cleanroom")
            pipeline.run()
            result = validate_cleanroom_run(pipeline.run_dir)
            self.assertEqual(result["result"], "PASS")
            self.assertEqual(result["counts"]["cross_paper_link_count"], 0)
            self.assertEqual(result["counts"]["invalid_source_offset_count"], 0)
            self.assertEqual(result["counts"]["duplicate_review_cleanroom_span_id_count"], 0)
            self.assertEqual(result["counts"]["review_human_fields_filled_count"], 0)
            self.assertEqual(result["counts"]["review_full_document_embedding_count"], 0)

    def test_missing_outputs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = validate_cleanroom_run(Path(temp))
            self.assertEqual(result["result"], "FAIL")
            self.assertGreater(result["error_count"], 0)


if __name__ == "__main__":
    unittest.main()
