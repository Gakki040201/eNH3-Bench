from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.human_audit import import_human_audit_sheet  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a reviewed BoundaryLedger human audit CSV.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--accept-as-gold", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "human_audit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = import_human_audit_sheet(
        args.input,
        args.run_name,
        output_dir=args.output_dir,
        accept_as_gold=args.accept_as_gold,
    )
    print(f"rows_read: {outputs['rows_read']}")
    print(f"reviewed_valid: {outputs['reviewed_valid']}")
    print(f"reviewed_invalid: {outputs['reviewed_invalid']}")
    print(f"unreviewed: {outputs['unreviewed']}")
    print(f"gold_written: {outputs['gold_written']}")
    print(f"reviewed_jsonl: {outputs['reviewed_jsonl']}")
    print(f"reviewed_csv: {outputs['reviewed_csv']}")
    print(f"errors_csv: {outputs['errors_csv']}")
    if outputs.get("gold_jsonl"):
        print(f"gold_jsonl: {outputs['gold_jsonl']}")
        print(f"gold_csv: {outputs['gold_csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
