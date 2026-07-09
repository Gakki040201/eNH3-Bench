from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.calibration import (  # noqa: E402
    export_calibration_outputs,
    export_calibration_report,
    load_reviewed_audit_records,
)


NO_REVIEWED_MESSAGE = (
    "No reviewed audit records found. Run export_human_audit_sheet, manually fill human fields, "
    "then import_human_audit_sheet."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate BoundaryLedger against reviewed human labels.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data") / "calibration")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_reviewed_audit_records(args.run_name)
    if not records:
        print(NO_REVIEWED_MESSAGE)
        return 1

    outputs = export_calibration_outputs(records, args.run_name, output_dir=args.output_dir)
    report_path = export_calibration_report(outputs["metrics"], args.run_name)
    rule = outputs["metrics"]["rule_human"]
    llm = outputs["metrics"]["llm_human"]

    print(f"reviewed_records: {outputs['reviewed_records']}")
    print(f"rule_boundary_accuracy: {rule['rule_boundary_accuracy']}")
    print(f"rule_boundary_overclaim_rate: {rule['rule_boundary_overclaim_rate']}")
    print(f"rule_boundary_underclaim_rate: {rule['rule_boundary_underclaim_rate']}")
    print(f"llm_records_available: {llm['llm_records_available']}")
    print(f"llm_boundary_accuracy: {llm['llm_boundary_accuracy']}")
    for label, path in outputs["paths"].items():
        print(f"{label}: {path}")
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
