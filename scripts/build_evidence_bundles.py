from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.evidence_bundle import (  # noqa: E402
    build_evidence_bundles,
    export_evidence_bundles,
    load_records_from_ledgers,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build eNH3-BoundaryLedger evidence bundles.")
    parser.add_argument("--run-name", default="final_pilot")
    parser.add_argument("--ledger-dir", type=Path, default=Path("data") / "ledgers")
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "boundary_ledger")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_records_from_ledgers(args.run_name, args.ledger_dir)
    bundles = build_evidence_bundles(records)
    outputs = export_evidence_bundles(bundles, args.run_name, args.output_dir)
    print(f"Loaded records: {len(records)}")
    print(f"Evidence bundles: {outputs['count']}")
    print(f"JSONL: {outputs['jsonl']}")
    print(f"CSV: {outputs['csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
