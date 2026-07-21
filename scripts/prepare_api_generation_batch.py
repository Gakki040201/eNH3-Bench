from __future__ import annotations

import argparse
import shutil
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.e2e_eval_schema import read_jsonl, resolve_run_target  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export an API generation batch without making an API call.")
    parser.add_argument("--selective-eval-run-name", required=True)
    parser.add_argument("--selective-eval-root", type=Path, default=Path("data/selective_eval"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    run_dir = resolve_run_target(args.selective_eval_root, args.selective_eval_run_name)
    source = run_dir / "cases/api_generation_batch.jsonl"
    rows = read_jsonl(source)
    if any(row.get("generation_status") != "pending" or row.get("network_call_performed") is not False for row in rows):
        print("api_generation_batch_export: FAIL\n- batch is not blank/pending", file=sys.stderr)
        return 1
    output = None
    if args.output:
        output = args.output.resolve()
        if output.exists():
            print(f"api_generation_batch_export: FAIL\n- refusing to overwrite: {output}", file=sys.stderr)
            return 1
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
    print(f"api_generation_batch_export: PASS\ncases: {len(rows)}\nnetwork_calls: 0\noutput: {output or '<not written>'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
