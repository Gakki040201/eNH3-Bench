from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.lab_profile import default_ustc_linnr_profile, save_lab_profile  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize an editable lab capability profile.")
    parser.add_argument("--output", type=Path, default=Path("data") / "lab_profiles" / "ustc_linnr_profile.yaml")
    parser.add_argument("--profile-template", choices=["conservative", "ustc-linnr-realistic"], default="conservative")
    parser.add_argument("--format", choices=["yaml", "json"], default="yaml")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output
    if args.format == "json" and output.suffix.lower() not in {".json"}:
        output = output.with_suffix(".json")
    if args.format == "yaml" and output.suffix.lower() not in {".yaml", ".yml"}:
        output = output.with_suffix(".yaml")
    if output.exists() and not args.overwrite:
        print(f"Lab profile already exists: {output}")
        print("Use --overwrite to replace it.")
        return 0
    save_lab_profile(default_ustc_linnr_profile(profile_template=args.profile_template), output)
    print(f"Lab profile written: {output}")
    print("Edit this profile before generating routes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
