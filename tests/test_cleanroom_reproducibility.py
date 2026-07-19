from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from enh3bench.cleanroom_output_check import _normalize, compare_normalized_runs
from enh3bench.cleanroom_pipeline import CleanroomPipeline
from tests.cleanroom_test_helpers import write_document


class CleanroomReproducibilityTests(unittest.TestCase):
    def test_normalization_does_not_hide_source_text_paths(self) -> None:
        left = _normalize({"source_text": r"reported at C:\\alpha"})
        right = _normalize({"source_text": r"reported at C:\\beta"})
        self.assertNotEqual(left, right)

    def test_two_run_names_have_matching_normalized_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            write_document(markdown)
            left = CleanroomPipeline(markdown_dir=markdown, run_name="repro_a", cleanroom_root=root / "cleanroom")
            right = CleanroomPipeline(markdown_dir=markdown, run_name="repro_b", cleanroom_root=root / "cleanroom")
            left.run()
            right.run()
            self.assertTrue(compare_normalized_runs(left.run_dir, right.run_dir)["reproducibility_match"])

    def test_difference_report_names_first_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            markdown = root / "markdown"
            path = write_document(markdown)
            left = CleanroomPipeline(markdown_dir=markdown, run_name="different_a", cleanroom_root=root / "cleanroom")
            left.run()
            path.write_text(path.read_text(encoding="utf-8") + "\nAmmonia measurement changed.\n", encoding="utf-8")
            right = CleanroomPipeline(markdown_dir=markdown, run_name="different_b", cleanroom_root=root / "cleanroom")
            right.run()
            result = compare_normalized_runs(left.run_dir, right.run_dir)
            self.assertFalse(result["reproducibility_match"])
            self.assertIn("field", result["first_difference"])


if __name__ == "__main__":
    unittest.main()
