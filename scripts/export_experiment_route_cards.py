from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.experiment_route_card import export_public_route_summary, export_route_cards, load_ranked_routes  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export experiment route cards.")
    parser.add_argument("--run-name", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    routes = load_ranked_routes(args.run_name)
    cards = export_route_cards(routes, args.run_name)
    summary = export_public_route_summary(routes, args.run_name)
    print(f"routes_loaded: {len(routes)}")
    print(f"route_cards: {cards}")
    print(f"summary: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
