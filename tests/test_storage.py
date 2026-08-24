from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from enh3bench.demo_v017 import DEFAULT_DEMO_ROOT, DEFAULT_PILOT_ROOT
from enh3bench.storage import (
    StorageConfigurationError,
    StorageProfile,
    build_freeze_manifest,
    copy_freeze_to_archive,
    load_storage_profile,
    sha256_file,
    validate_storage_roots,
)
from scripts.run_demo_v017 import parse_args as parse_demo_args


class StorageProfileTests(unittest.TestCase):
    def test_unresolved_environment_variable_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile_path = Path(temp_dir) / "profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": "storage-1.0",
                        "work_root": "${ENH3_WORK_ROOT}",
                        "archive_root": "${ENH3_ARCHIVE_ROOT}",
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(StorageConfigurationError, "ENH3_ARCHIVE_ROOT"):
                load_storage_profile(profile_path, env={"ENH3_WORK_ROOT": temp_dir})

    def test_profile_loads_with_explicit_temporary_roots(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            work = base / "work"
            archive = base / "archive"
            work.mkdir()
            archive.mkdir()
            profile_path = base / "profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": "storage-1.0",
                        "work_root": "${WORK}",
                        "archive_root": "${ARCHIVE}",
                        "legacy": {"pilot_root": str(base / "pilot"), "demo_root": str(base / "demo")},
                        "policy": {"require_sha256": True},
                    }
                ),
                encoding="utf-8",
            )
            profile = load_storage_profile(
                profile_path, env={"WORK": str(work), "ARCHIVE": str(archive)}
            )
            self.assertEqual(profile.work_root, work)
            self.assertEqual(profile.archive_root, archive)
            self.assertTrue(validate_storage_roots(profile)["valid"])

    def test_missing_archive_root_preflight_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            profile = StorageProfile(work_root=Path(temp_dir), archive_root=None)
            report = validate_storage_roots(profile)
            self.assertFalse(report["valid"])
            self.assertFalse(report["roots"]["archive_root"]["configured"])
            self.assertTrue(any("archive_root is not configured" in error for error in report["errors"]))


class FreezeOperationsTests(unittest.TestCase):
    def _source(self, base: Path) -> Path:
        source = base / "freeze"
        (source / "nested").mkdir(parents=True)
        (source / "b.txt").write_bytes(b"beta\n")
        (source / "nested" / "a.bin").write_bytes(b"\x00alpha\xff")
        return source

    def test_manifest_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = self._source(Path(temp_dir))
            first = build_freeze_manifest(source, metadata={"release": "R001"})
            second = build_freeze_manifest(source, metadata={"release": "R001"})
            self.assertEqual(first, second)
            self.assertEqual(
                [item["relative_path"] for item in first["files"]],
                ["b.txt", "nested/a.bin"],
            )

    def test_sha256_is_correct(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "value.bin"
            payload = b"eNH3-Bench\x00storage"
            path.write_bytes(payload)
            self.assertEqual(sha256_file(path), hashlib.sha256(payload).hexdigest())

    def test_copy_preserves_files_hashes_and_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source = self._source(base)
            destination = base / "archive" / "freeze"
            manifest = copy_freeze_to_archive(source, destination)
            for item in manifest["files"]:
                relative = Path(item["relative_path"])
                self.assertTrue((source / relative).exists())
                self.assertEqual(sha256_file(source / relative), sha256_file(destination / relative))
            self.assertTrue(source.exists())

    def test_copy_refuses_overwrite_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            source = self._source(base)
            destination = base / "archive"
            destination.mkdir()
            with self.assertRaises(FileExistsError):
                copy_freeze_to_archive(source, destination)
            self.assertTrue(source.exists())


class M017StorageCompatibilityTests(unittest.TestCase):
    def test_legacy_defaults_are_unchanged_without_environment_overrides(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            args = parse_demo_args([])
        self.assertEqual(args.pilot_root, DEFAULT_PILOT_ROOT)
        self.assertEqual(args.demo_root, DEFAULT_DEMO_ROOT)

    def test_explicit_cli_roots_win_over_environment(self) -> None:
        with patch.dict(
            "os.environ", {"ENH3_PILOT_ROOT": "env-pilot", "ENH3_DEMO_ROOT": "env-demo"}, clear=True
        ):
            args = parse_demo_args(["--pilot-root", "cli-pilot", "--demo-root", "cli-demo"])
        self.assertEqual(args.pilot_root, Path("cli-pilot"))
        self.assertEqual(args.demo_root, Path("cli-demo"))

    def test_environment_can_supply_optional_legacy_roots(self) -> None:
        with patch.dict(
            "os.environ", {"ENH3_PILOT_ROOT": "env-pilot", "ENH3_DEMO_ROOT": "env-demo"}, clear=True
        ):
            args = parse_demo_args([])
        self.assertEqual(args.pilot_root, Path("env-pilot"))
        self.assertEqual(args.demo_root, Path("env-demo"))


if __name__ == "__main__":
    unittest.main()
