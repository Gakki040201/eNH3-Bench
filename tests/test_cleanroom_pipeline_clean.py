from __future__ import annotations

import tempfile
import unittest
import os
import subprocess
from pathlib import Path

from enh3bench.cleanroom_pipeline import CleanroomPipeline
from enh3bench.cleanroom_schema import resolve_clean_target, validate_run_name


class CleanroomPipelineCleanTests(unittest.TestCase):
    def test_clean_valid_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pipeline = CleanroomPipeline(markdown_dir=root, run_name="valid_run", cleanroom_root=root / "cleanroom")
            pipeline.run_dir.mkdir(parents=True)
            (pipeline.run_dir / "marker").write_text("x", encoding="utf-8")
            pipeline.clean()
            self.assertFalse(pipeline.run_dir.exists())

    def test_dry_run_does_not_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pipeline = CleanroomPipeline(markdown_dir=root, run_name="valid_run", cleanroom_root=root / "cleanroom")
            pipeline.run_dir.mkdir(parents=True)
            pipeline.clean(dry_run=True, emit=lambda _message: None)
            self.assertTrue(pipeline.run_dir.exists())

    def test_refuse_authoritative_old_run(self) -> None:
        with self.assertRaises(ValueError):
            validate_run_name("enrr_round1_oa_20260712")

    def test_refuse_blank_name(self) -> None:
        with self.assertRaises(ValueError):
            validate_run_name(" ")

    def test_refuse_traversal(self) -> None:
        with self.assertRaises(ValueError):
            validate_run_name("../outside")

    def test_refuse_cleanroom_root_tokens(self) -> None:
        for value in (".", "..", "data/cleanroom/"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_run_name(value)

    def test_refuse_data_root_token(self) -> None:
        for value in ("data", "data/", "cleanroom"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_run_name(value)

    def test_target_is_exact_child_of_cleanroom_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "cleanroom"
            target = resolve_clean_target(root, "exact_run")
            self.assertEqual(target.parent, root.resolve())

    def test_clean_does_not_delete_sibling_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pipeline = CleanroomPipeline(markdown_dir=root, run_name="target", cleanroom_root=root / "cleanroom")
            sibling = pipeline.cleanroom_root / "sibling"
            sibling.mkdir(parents=True)
            pipeline.run_dir.mkdir(parents=True)
            pipeline.clean(emit=lambda _message: None)
            self.assertTrue(sibling.is_dir())

    def test_symlink_outside_cleanroom_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cleanroom = root / "cleanroom"
            outside = root / "outside"
            cleanroom.mkdir()
            outside.mkdir()
            link = cleanroom / "linked_run"
            if os.name == "nt":
                result = subprocess.run(
                    ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            else:
                link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                resolve_clean_target(cleanroom, "linked_run")

    def test_junction_to_sibling_run_is_rejected(self) -> None:
        if os.name != "nt":
            return
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cleanroom = root / "cleanroom"
            sibling = cleanroom / "sibling"
            cleanroom.mkdir()
            sibling.mkdir()
            link = cleanroom / "linked_run"
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(sibling)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            with self.assertRaises(ValueError):
                resolve_clean_target(cleanroom, "linked_run")
            self.assertTrue(sibling.is_dir())

    def test_clean_refuses_active_run_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pipeline = CleanroomPipeline(markdown_dir=root, run_name="locked", cleanroom_root=root / "cleanroom")
            pipeline.cleanroom_root.mkdir(parents=True)
            pipeline.lock_path.write_text("123", encoding="ascii")
            with self.assertRaises(RuntimeError):
                pipeline.clean(emit=lambda _message: None)


if __name__ == "__main__":
    unittest.main()
