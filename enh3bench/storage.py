"""Storage profile, manifest, and copy-only archive primitives.

Storage schema ``storage-1.0`` is independent of the scientific and audit
schemas.  The module deliberately provides no delete or move operation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any, Mapping


STORAGE_SCHEMA_VERSION = "storage-1.0"
FREEZE_MANIFEST_SCHEMA_VERSION = "storage-freeze-manifest-1.0"
DEFAULT_PROFILE_ENV = "ENH3_STORAGE_PROFILE"
_ENV_REFERENCE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class StorageConfigurationError(ValueError):
    """Raised when a storage profile is absent or unsafe to interpret."""


@dataclass(frozen=True)
class StoragePolicy:
    archive_only_frozen: bool = True
    delete_after_export: bool = False
    require_manifest: bool = True
    require_sha256: bool = True


@dataclass(frozen=True)
class StorageProfile:
    work_root: Path
    archive_root: Path | None = None
    pilot_root: Path | None = None
    demo_root: Path | None = None
    policy: StoragePolicy = field(default_factory=StoragePolicy)
    schema_version: str = STORAGE_SCHEMA_VERSION

    @property
    def legacy(self) -> dict[str, Path | None]:
        return {"pilot_root": self.pilot_root, "demo_root": self.demo_root}


def _expand_environment(value: str, env: Mapping[str, str], *, field_name: str) -> str:
    unresolved: list[str] = []

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        replacement = env.get(name)
        if replacement is None or not str(replacement).strip():
            unresolved.append(name)
            return match.group(0)
        return str(replacement)

    expanded = _ENV_REFERENCE.sub(replace, value)
    if unresolved:
        names = ", ".join(sorted(set(unresolved)))
        raise StorageConfigurationError(
            f"unresolved required environment variable(s) for {field_name}: {names}"
        )
    return expanded


def _path_value(
    value: Any,
    env: Mapping[str, str],
    *,
    field_name: str,
    required: bool,
) -> Path | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise StorageConfigurationError(f"{field_name} is required")
        return None
    if not isinstance(value, str):
        raise StorageConfigurationError(f"{field_name} must be a string path")
    return Path(_expand_environment(value, env, field_name=field_name)).expanduser()


def _bool_value(values: Mapping[str, Any], name: str, default: bool) -> bool:
    value = values.get(name, default)
    if type(value) is not bool:
        raise StorageConfigurationError(f"policy.{name} must be a boolean")
    return value


def load_storage_profile(
    path: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> StorageProfile:
    """Load a strict storage-1.0 profile.

    When *path* is omitted, ``ENH3_STORAGE_PROFILE`` is used when set;
    otherwise the profile is assembled directly from the four documented
    root variables.  In direct-environment mode the work root is required,
    while an absent archive root is retained as ``None`` for explicit
    preflight reporting.
    """

    environment = os.environ if env is None else env
    selected_path = path or environment.get(DEFAULT_PROFILE_ENV)
    if selected_path is None:
        work_value = environment.get("ENH3_WORK_ROOT")
        return StorageProfile(
            work_root=_path_value(
                work_value, environment, field_name="work_root", required=True
            ),  # type: ignore[arg-type]
            archive_root=_path_value(
                environment.get("ENH3_ARCHIVE_ROOT"),
                environment,
                field_name="archive_root",
                required=False,
            ),
            pilot_root=_path_value(
                environment.get("ENH3_PILOT_ROOT"),
                environment,
                field_name="legacy.pilot_root",
                required=False,
            ),
            demo_root=_path_value(
                environment.get("ENH3_DEMO_ROOT"),
                environment,
                field_name="legacy.demo_root",
                required=False,
            ),
        )

    profile_path = Path(selected_path)
    try:
        raw = json.loads(profile_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StorageConfigurationError(f"storage profile not found: {profile_path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageConfigurationError(f"invalid storage profile {profile_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise StorageConfigurationError("storage profile must be a JSON object")
    if raw.get("schema_version") != STORAGE_SCHEMA_VERSION:
        raise StorageConfigurationError(
            f"unsupported storage schema_version: {raw.get('schema_version')!r}"
        )
    legacy = raw.get("legacy", {})
    policy_values = raw.get("policy", {})
    if not isinstance(legacy, dict):
        raise StorageConfigurationError("legacy must be a JSON object")
    if not isinstance(policy_values, dict):
        raise StorageConfigurationError("policy must be a JSON object")
    policy = StoragePolicy(
        archive_only_frozen=_bool_value(policy_values, "archive_only_frozen", True),
        delete_after_export=_bool_value(policy_values, "delete_after_export", False),
        require_manifest=_bool_value(policy_values, "require_manifest", True),
        require_sha256=_bool_value(policy_values, "require_sha256", True),
    )
    if policy.delete_after_export:
        raise StorageConfigurationError("policy.delete_after_export must be false in storage-1.0")
    return StorageProfile(
        work_root=_path_value(
            raw.get("work_root"), environment, field_name="work_root", required=True
        ),  # type: ignore[arg-type]
        archive_root=_path_value(
            raw.get("archive_root"), environment, field_name="archive_root", required=False
        ),
        pilot_root=_path_value(
            legacy.get("pilot_root"),
            environment,
            field_name="legacy.pilot_root",
            required=False,
        ),
        demo_root=_path_value(
            legacy.get("demo_root"),
            environment,
            field_name="legacy.demo_root",
            required=False,
        ),
        policy=policy,
    )


def validate_storage_roots(profile: StorageProfile) -> dict[str, Any]:
    """Return a machine-readable, non-mutating root preflight report."""

    errors: list[str] = []
    roots: dict[str, dict[str, Any]] = {}
    configured = {
        "work_root": profile.work_root,
        "archive_root": profile.archive_root,
        "legacy.pilot_root": profile.pilot_root,
        "legacy.demo_root": profile.demo_root,
    }
    for name, path in configured.items():
        required = name in {"work_root", "archive_root"}
        if path is None:
            roots[name] = {"configured": False, "exists": False, "is_directory": False}
            if required:
                errors.append(
                    f"{name} is not configured; set the corresponding ENH3_*_ROOT variable or profile value"
                )
            continue
        exists = path.exists()
        is_directory = path.is_dir()
        roots[name] = {
            "configured": True,
            "path": str(path),
            "exists": exists,
            "is_directory": is_directory,
        }
        if required and not exists:
            errors.append(f"{name} does not exist: {path}")
        elif required and not is_directory:
            errors.append(f"{name} is not a directory: {path}")
    return {
        "schema_version": STORAGE_SCHEMA_VERSION,
        "valid": not errors,
        "roots": roots,
        "errors": errors,
    }


def sha256_file(path: str | Path) -> str:
    """Return the lowercase SHA256 digest of one regular file."""

    file_path = Path(path)
    if not file_path.is_file() or file_path.is_symlink():
        raise ValueError(f"not a regular file: {file_path}")
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_freeze_manifest(
    root: str | Path,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe every regular file below *root* in deterministic path order."""

    root_path = Path(root)
    if not root_path.exists():
        raise FileNotFoundError(f"freeze root does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"freeze root is not a directory: {root_path}")
    files: list[dict[str, Any]] = []
    for path in sorted(root_path.rglob("*"), key=lambda item: item.relative_to(root_path).as_posix()):
        if path.is_symlink():
            raise ValueError(f"freeze roots may not contain symbolic links: {path}")
        if path.is_file():
            files.append(
                {
                    "relative_path": path.relative_to(root_path).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    manifest_metadata = dict(metadata or {})
    # Validate now so callers never receive a manifest that cannot be serialized.
    json.dumps(manifest_metadata, ensure_ascii=False, sort_keys=True)
    return {
        "schema_version": FREEZE_MANIFEST_SCHEMA_VERSION,
        "metadata": manifest_metadata,
        "file_count": len(files),
        "total_bytes": sum(item["size_bytes"] for item in files),
        "files": files,
    }


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def copy_freeze_to_archive(
    source: str | Path,
    destination: str | Path,
    *,
    verify: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Copy a freeze tree without removing or modifying its source.

    Existing destinations are rejected by default.  ``overwrite=True`` may
    replace colliding destination files but never deletes extra destination
    files.  Symbolic links are rejected rather than followed.
    """

    source_path = Path(source)
    destination_path = Path(destination)
    manifest = build_freeze_manifest(source_path)
    source_resolved = source_path.resolve()
    destination_resolved = destination_path.resolve()
    if source_resolved == destination_resolved or _is_relative_to(
        destination_resolved, source_resolved
    ):
        raise ValueError("archive destination must be outside the source freeze")
    if destination_path.exists() and not overwrite:
        raise FileExistsError(f"archive destination already exists: {destination_path}")
    if destination_path.exists() and not destination_path.is_dir():
        raise NotADirectoryError(f"archive destination is not a directory: {destination_path}")

    destination_path.mkdir(parents=True, exist_ok=overwrite)
    for item in manifest["files"]:
        relative = Path(item["relative_path"])
        source_file = source_path / relative
        destination_file = destination_path / relative
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        if destination_file.exists() and destination_file.is_dir():
            raise IsADirectoryError(f"destination file collides with a directory: {destination_file}")
        shutil.copy2(source_file, destination_file)

    if verify:
        for item in manifest["files"]:
            destination_file = destination_path / Path(item["relative_path"])
            if not destination_file.is_file():
                raise OSError(f"copied file is missing: {destination_file}")
            if destination_file.stat().st_size != item["size_bytes"]:
                raise OSError(f"copied file size mismatch: {destination_file}")
            if sha256_file(destination_file) != item["sha256"]:
                raise OSError(f"copied file SHA256 mismatch: {destination_file}")
    return manifest


def legacy_root_from_env(name: str, default: Path, env: Mapping[str, str] | None = None) -> Path:
    """Resolve an optional legacy root without changing its historical fallback."""

    variable = {"pilot": "ENH3_PILOT_ROOT", "demo": "ENH3_DEMO_ROOT"}.get(name)
    if variable is None:
        raise ValueError(f"unknown legacy root: {name}")
    environment = os.environ if env is None else env
    value = environment.get(variable)
    return Path(value) if value and value.strip() else default
