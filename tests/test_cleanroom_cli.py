from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from enh3bench.cleanroom_pipeline import CleanroomPipeline
from scripts.run_cleanroom_pipeline import main, parse_args


class CleanroomCliTests(unittest.TestCase):
    def test_clean_and_resume_are_mutually_exclusive(self) -> None:
        with patch.object(sys, "argv", ["run_cleanroom_pipeline.py", "--run-name", "run", "--clean", "--resume"]):
            with self.assertRaises(SystemExit):
                parse_args()

    def test_input_and_markdown_dirs_are_mutually_exclusive(self) -> None:
        with patch.object(sys, "argv", [
            "run_cleanroom_pipeline.py", "--run-name", "run", "--input-dir", "raw", "--markdown-dir", "markdown"
        ]):
            with self.assertRaises(SystemExit):
                parse_args()

    def test_negative_review_sample_size_is_rejected(self) -> None:
        with patch.object(sys, "argv", ["run_cleanroom_pipeline.py", "--run-name", "run", "--review-sample-size", "-1"]):
            with self.assertRaises(SystemExit):
                parse_args()

    def test_api_rejects_invalid_candidate_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "config.json"
            config.write_text('{"max_candidate_characters": 0}', encoding="utf-8")
            with self.assertRaises(ValueError):
                CleanroomPipeline(markdown_dir=temp, run_name="run", cleanroom_root=Path(temp) / "cleanroom", config_path=config)

    def test_existing_run_lock_prevents_concurrent_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pipeline = CleanroomPipeline(markdown_dir=root, run_name="locked", cleanroom_root=root / "cleanroom")
            pipeline.cleanroom_root.mkdir(parents=True)
            pipeline.lock_path.write_text("123", encoding="ascii")
            with self.assertRaises(RuntimeError):
                pipeline.run()

    def test_dry_run_without_input_does_not_execute_pipeline(self) -> None:
        with patch.object(sys, "argv", ["run_cleanroom_pipeline.py", "--run-name", "cli_dry_run", "--dry-run"]):
            self.assertEqual(main(), 0)

    def test_reversed_stage_range_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pipeline = CleanroomPipeline(markdown_dir=temp, run_name="range", cleanroom_root=Path(temp) / "cleanroom")
            with self.assertRaises(ValueError):
                pipeline.run(from_stage="papers", to_stage="documents", resume=True)

    def test_from_stage_requires_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            pipeline = CleanroomPipeline(markdown_dir=temp, run_name="range", cleanroom_root=Path(temp) / "cleanroom")
            with self.assertRaises(ValueError):
                pipeline.run(from_stage="candidates")

    def test_invalid_profile_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                CleanroomPipeline(markdown_dir=temp, run_name="run", cleanroom_root=Path(temp) / "cleanroom", profile="legacy")


if __name__ == "__main__":
    unittest.main()
