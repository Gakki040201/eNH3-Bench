from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.evidence_package_v018 import (  # noqa: E402
    FROZEN_PILOT_ORDER,
    assemble_evidence_package,
    load_real_pilot_assets,
    publish_single_package,
    stage_and_publish_packages,
    validate_package_set,
)
from scripts.audit_v018_evidence_assets import ensure_runtime_outside_repository  # noqa: E402
from scripts.check_v018_evidence_package import validate_evidence_package_file  # noqa: E402


DEFAULT_RUNTIME_ROOT = Path(r"F:\eNH3_Bench_API\v018")
DEFAULT_PILOT_MANIFEST = Path("data/manifests/v018_a1_pilot_corpus.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deterministically assemble M018 A1 packages from existing accepted assets only."
    )
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--pilot-manifest", type=Path, default=DEFAULT_PILOT_MANIFEST)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME_ROOT)
    parser.add_argument("--audit-inventory", type=Path)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--paper-id")
    parser.add_argument("--check-only", action="store_true")
    return parser.parse_args()


def git_commit(repository_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def main() -> int:
    args = parse_args()
    repository = args.repository_root.resolve()
    runtime = ensure_runtime_outside_repository(args.runtime_root, repository)
    manifest_path = args.pilot_manifest
    if not manifest_path.is_absolute():
        manifest_path = repository / manifest_path
    inventory_path = args.audit_inventory or runtime / "audits" / "v018_asset_inventory.jsonl"
    if args.paper_id and args.paper_id not in FROZEN_PILOT_ORDER:
        print(json.dumps({"result": "FAIL", "error": "paper is outside the frozen pilot"}, indent=2))
        return 1
    if args.check_only:
        if args.paper_id:
            result = validate_evidence_package_file(
                runtime / "packages" / args.paper_id / "evidence_package.json"
            )
        else:
            result = validate_package_set(runtime, manifest_path)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["result"] == "PASS" else 1

    manifest, assets = load_real_pilot_assets(repository, manifest_path, inventory_path)
    code_commit = git_commit(repository)
    if args.paper_id:
        build = assemble_evidence_package(assets[args.paper_id], code_commit)
        publish_single_package(runtime, args.paper_id, build, clean=args.clean)
        result = {
            "result": "PASS",
            "paper_id": args.paper_id,
            "package_id": build.package["package_id"],
            "content_sha256": build.package["package_hashes"]["content_sha256"],
        }
    else:
        builds = {
            record["paper_id"]: assemble_evidence_package(assets[record["paper_id"]], code_commit)
            for record in manifest
        }
        result = stage_and_publish_packages(
            runtime,
            manifest,
            builds,
            clean=args.clean,
            pilot_manifest_path=manifest_path,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
