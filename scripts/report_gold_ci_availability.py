from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def report_gold_ci_availability(
    run_name: str, *, gold_root: str | Path = ROOT / "data" / "gold"
) -> dict[str, Any]:
    """Describe local authoritative Gold availability without creating or fetching data."""

    run_dir = Path(gold_root) / run_name
    jsonl_path = run_dir / "human_gold_claim_rights.jsonl"
    csv_path = run_dir / "human_gold_claim_rights.csv"
    jsonl_available = jsonl_path.is_file()
    csv_available = csv_path.is_file()
    return {
        "run_name": run_name,
        "status": "available" if jsonl_available and csv_available else "local_authoritative_gold_not_committed",
        "jsonl_available": jsonl_available,
        "csv_available": csv_available,
        "exact_integrity_check_available": jsonl_available and csv_available,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Report whether local authoritative Gold is available to CI."
    )
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--gold-root", type=Path, default=ROOT / "data" / "gold")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = report_gold_ci_availability(args.run_name, gold_root=args.gold_root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
