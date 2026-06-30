from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.ledger_router import classify_and_route_spans, load_jsonl  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify source spans and route eNH3-TriageBench ledgers.")
    parser.add_argument("--run-name", default="final_pilot")
    parser.add_argument("--spans", type=Path, default=None, help="Candidate-span JSONL input.")
    parser.add_argument("--ledger-dir", type=Path, default=Path("data") / "ledgers")
    parser.add_argument("--manifest", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spans_path = args.spans or Path("data") / "candidates" / f"candidate_spans.{args.run_name}.jsonl"
    spans = load_jsonl(spans_path)
    classified, manifest = classify_and_route_spans(spans, args.run_name, args.ledger_dir)
    manifest_path = args.manifest or Path("data") / "reports" / f"ledger_routing_manifest.{args.run_name}.json"
    _write_json(manifest, manifest_path)
    print(f"Classified {len(classified)} spans from {spans_path}")
    for ledger_name, count in manifest["ledger_counts"].items():
        print(f"{ledger_name}: {count}")
    print(f"Manifest: {manifest_path}")
    return 0


def _write_json(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
