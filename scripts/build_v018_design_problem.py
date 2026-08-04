from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.design_compiler_v018 import write_runtime_outputs  # noqa: E402


DEFAULT_A1_RUNTIME = Path(r"F:\eNH3_Bench_API\v018")
DEFAULT_RUNTIME = DEFAULT_A1_RUNTIME / "design_compiler"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the deterministic M018 A2A LiNRR design-problem baseline.")
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--a1-runtime-root", type=Path, default=DEFAULT_A1_RUNTIME)
    parser.add_argument("--runtime-root", type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument("--clean", action="store_true")
    return parser.parse_args()


def git_commit(repository_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository_root, check=True, capture_output=True, text=True,
    )
    return completed.stdout.strip()


def main() -> int:
    args = parse_args()
    result = write_runtime_outputs(
        args.runtime_root,
        args.repository_root,
        args.a1_runtime_root,
        git_commit(args.repository_root),
        clean=args.clean,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
