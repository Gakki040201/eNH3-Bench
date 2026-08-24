from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.storage import (  # noqa: E402
    StorageConfigurationError,
    build_freeze_manifest,
    copy_freeze_to_archive,
    load_storage_profile,
    validate_storage_roots,
)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage storage-1.0 roots and frozen exports.")
    commands = parser.add_subparsers(dest="command", required=True)

    preflight = commands.add_parser("preflight", help="Validate configured roots without changing them.")
    preflight.add_argument("--profile", type=Path)

    manifest = commands.add_parser("manifest", help="Print a deterministic freeze manifest.")
    manifest.add_argument("--root", type=Path, required=True)
    manifest.add_argument("--metadata", type=Path, help="Optional JSON object with manifest metadata.")
    manifest.add_argument("--output", type=Path, help="Write the manifest outside the freeze root.")

    copy = commands.add_parser("copy-freeze", help="Copy a freeze to an archive; never delete the source.")
    copy.add_argument("--source", type=Path, required=True)
    copy.add_argument("--destination", type=Path, required=True)
    copy.add_argument("--profile", type=Path)
    copy.add_argument("--overwrite", action="store_true")
    copy.add_argument("--no-verify", action="store_true")
    copy.add_argument("--manifest-output", type=Path)
    return parser.parse_args(argv)


def _within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _manifest_command(args: argparse.Namespace) -> int:
    metadata = None
    if args.metadata:
        metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("manifest metadata must be a JSON object")
    manifest = build_freeze_manifest(args.root, metadata=metadata)
    rendered = _json(manifest)
    if args.output:
        if _within(args.output, args.root):
            raise ValueError("manifest output must be outside the source freeze")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
        print(args.output)
    else:
        print(rendered, end="")
    return 0


def _copy_command(args: argparse.Namespace) -> int:
    profile = load_storage_profile(args.profile) if args.profile else None
    verify = not args.no_verify
    if profile:
        report = validate_storage_roots(profile)
        if not report["valid"]:
            raise StorageConfigurationError("; ".join(report["errors"]))
        if profile.policy.require_sha256 and not verify:
            raise StorageConfigurationError("policy.require_sha256 forbids --no-verify")
        if profile.policy.archive_only_frozen:
            freeze_root = profile.work_root / "07_dataset_freezes"
            if not _within(args.source, freeze_root):
                raise StorageConfigurationError(
                    f"source must be below the configured freeze root: {freeze_root}"
                )
        if profile.archive_root is not None and not _within(args.destination, profile.archive_root):
            raise StorageConfigurationError(
                f"destination must be below the configured archive root: {profile.archive_root}"
            )
    manifest_output = args.manifest_output
    require_manifest = profile.policy.require_manifest if profile else True
    if require_manifest and manifest_output is None:
        manifest_output = args.destination.parent / f"{args.destination.name}.manifest.json"
    if manifest_output and _within(manifest_output, args.source):
        raise ValueError("archive manifest output must be outside the source freeze")
    if manifest_output and manifest_output.exists() and not args.overwrite:
        raise FileExistsError(f"archive manifest already exists: {manifest_output}")
    manifest = copy_freeze_to_archive(
        args.source, args.destination, verify=verify, overwrite=args.overwrite
    )
    if manifest_output:
        manifest_output.parent.mkdir(parents=True, exist_ok=True)
        manifest_output.write_text(_json(manifest), encoding="utf-8", newline="\n")
    print(
        _json(
            {
                "copied": True,
                "source_preserved": args.source.exists(),
                "verified": verify,
                "file_count": manifest["file_count"],
                "manifest": str(manifest_output) if manifest_output else None,
            }
        ),
        end="",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "preflight":
            report = validate_storage_roots(load_storage_profile(args.profile))
            print(_json(report), end="")
            return 0 if report["valid"] else 2
        if args.command == "manifest":
            return _manifest_command(args)
        return _copy_command(args)
    except (StorageConfigurationError, FileNotFoundError, FileExistsError, OSError, ValueError) as exc:
        print(f"storage-v1: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
