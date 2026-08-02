from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.evidence_package_v018 import validate_package_set  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail-closed validator for the M018 A1 package set.")
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument(
        "--pilot-manifest",
        type=Path,
        default=ROOT / "data" / "manifests" / "v018_a1_pilot_corpus.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = validate_package_set(args.runtime_root, args.pilot_manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
