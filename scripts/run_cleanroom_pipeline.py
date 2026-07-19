from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.cleanroom_pipeline import CleanroomPipeline, prepare_markdown_input  # noqa: E402
from enh3bench.cleanroom_schema import CLEANROOM_PROFILE, CLEANROOM_STAGES  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the v0.15 document-first clean-room pipeline.")
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--input-dir", type=Path)
    inputs.add_argument("--markdown-dir", type=Path)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--converter")
    parser.add_argument("--skip-conversion", action="store_true")
    lifecycle = parser.add_mutually_exclusive_group()
    lifecycle.add_argument("--clean", action="store_true")
    lifecycle.add_argument("--resume", action="store_true")
    parser.add_argument("--from-stage", choices=CLEANROOM_STAGES)
    parser.add_argument("--to-stage", choices=CLEANROOM_STAGES)
    parser.add_argument("--profile", default=CLEANROOM_PROFILE)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--review-sample-size", type=_non_negative_int, default=130)
    parser.add_argument("--review-seed", type=int, default=13)
    parser.add_argument("--compare-run")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def main() -> int:
    args = parse_args()
    if args.dry_run:
        markdown_dir = args.markdown_dir or args.input_dir or ROOT / "input_markdown"
    else:
        markdown_dir = prepare_markdown_input(
            markdown_dir=args.markdown_dir,
            input_dir=args.input_dir or (ROOT / "input_markdown" if args.clean else None),
            converter=args.converter,
            skip_conversion=args.skip_conversion or (args.clean and args.input_dir is None),
        )
    pipeline = CleanroomPipeline(
        markdown_dir=markdown_dir,
        run_name=args.run_name,
        cleanroom_root=ROOT / "data" / "cleanroom",
        profile=args.profile,
        config_path=args.config,
        review_sample_size=args.review_sample_size,
        review_seed=args.review_seed,
        compare_run=args.compare_run,
    )
    if args.clean:
        pipeline.clean(dry_run=args.dry_run)
        if args.dry_run:
            return 0
    elif args.dry_run:
        print(f"dry run: would execute {args.from_stage or CLEANROOM_STAGES[0]} through {args.to_stage or CLEANROOM_STAGES[-1]}")
        print(f"run directory: {pipeline.run_dir}")
        return 0
    manifest = pipeline.run(resume=args.resume, from_stage=args.from_stage, to_stage=args.to_stage)
    print(f"pipeline_status: {manifest['pipeline_status']}")
    print(f"run_name: {args.run_name}")
    print(f"run_directory: {pipeline.run_dir}")
    return 0 if manifest["pipeline_status"] in {"completed", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
