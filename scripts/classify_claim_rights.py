from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.claim_rights import export_claim_rights_ledger  # noqa: E402
from enh3bench.evidence_bundle import load_records_from_ledgers  # noqa: E402
from enh3bench.ledger_router import load_jsonl  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify eNH3-BoundaryLedger claim rights.")
    parser.add_argument("--run-name", default="final_pilot")
    parser.add_argument("--ledger-dir", type=Path, default=Path("data") / "ledgers")
    parser.add_argument("--boundary-dir", type=Path, default=Path("data") / "boundary_ledger")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence_path = args.boundary_dir / args.run_name / "evidence_bundles.jsonl"
    records = load_jsonl(evidence_path)
    source = evidence_path
    if not records:
        records = load_records_from_ledgers(args.run_name, args.ledger_dir)
        source = args.ledger_dir / args.run_name
    outputs = export_claim_rights_ledger(records, args.run_name, args.boundary_dir)
    print(f"Loaded records: {len(records)}")
    print(f"Source: {source}")
    print(f"Claim-rights records: {outputs['count']}")
    print(f"JSONL: {outputs['jsonl']}")
    print(f"CSV: {outputs['csv']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
