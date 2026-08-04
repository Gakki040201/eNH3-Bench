from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.design_compiler_v018 import validate_design_problem  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a fail-closed M018 A2A design problem.")
    parser.add_argument("--problem", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        value = json.loads(args.problem.read_text(encoding="utf-8"))
        result = validate_design_problem(value)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        result = {"schema_version": "0.18-design-problem.1", "artifact_id": "", "result": "FAIL", "error_count": 1, "errors": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
