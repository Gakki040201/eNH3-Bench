from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.experiment_planner import export_experiment_routes, propose_rule_based_routes  # noqa: E402
from enh3bench.experiment_result_importer import export_experiment_result_template  # noqa: E402
from enh3bench.experiment_schema import expand_route_execution_rows  # noqa: E402
from enh3bench.lab_profile import (  # noqa: E402
    capability_available,
    default_ustc_linnr_profile,
    migrate_lab_profile,
)
from enh3bench.ledger_router import load_jsonl  # noqa: E402


SCHEMA_VERSION = "0.13"
RECOGNIZED_SCIENTIFIC_SECTIONS = {"abstract", "methods", "experimental", "results", "discussion", "results_and_discussion"}
STAGE_FIELDS = {
    "execution_stage",
    "stage_rank",
    "within_stage_score",
    "stage_gate_status",
    "prerequisite_route_ids",
    "blocked_by_route_ids",
    "execution_order_reason",
}
FEASIBILITY_FIELDS = {
    "required_controls",
    "feasible_controls",
    "infeasible_controls",
    "mandatory_measurements",
    "optional_measurements",
    "feasible_measurements",
    "infeasible_measurements",
    "measurement_feasibility_status",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the integrated v0.13 hardening release.")
    parser.add_argument("--run-name", default="pilot_v013_validation")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_path = args.report or args.data_dir / "reports" / f"v013_integrated_hardening_report.{args.run_name}.md"
    payload = check_v013_integrated_hardening(args.run_name, args.data_dir)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(args.run_name, payload), encoding="utf-8", newline="\n")
    print(f"checks_passed: {payload['checks_passed']}/{payload['checks_total']}")
    print(f"report: {report_path}")
    for check in payload["checks"]:
        print(f"{'PASS' if check['passed'] else 'FAIL'}: {check['name']} - {check['detail']}")
    return 0 if payload["checks_passed"] == payload["checks_total"] else 1


def check_v013_integrated_hardening(run_name: str, data_dir: Path) -> dict[str, Any]:
    provenance = load_jsonl(data_dir / "provenance" / run_name / "source_span_provenance.jsonl")
    classified = load_jsonl(data_dir / "ledgers" / run_name / "classified_spans.jsonl")
    claims = load_jsonl(data_dir / "boundary_ledger" / run_name / "claim_rights_ledger.jsonl")
    audits = load_jsonl(data_dir / "human_audit" / run_name / "human_audit_sheet.jsonl")
    routes = load_jsonl(data_dir / "experiment_routes" / run_name / "ranked_experiment_routes.jsonl")
    result_rows = load_jsonl(data_dir / "experiment_results" / run_name / "experiment_results_template.jsonl")

    recognized = [record for record in provenance if str(record.get("section_type") or "unknown") in RECOGNIZED_SCIENTIFIC_SECTIONS]
    recognized_low = [record for record in recognized if str(record.get("provenance_confidence") or "low") == "low"]
    checks: list[dict[str, Any]] = []
    _check(checks, "recognized section confidence", bool(recognized) and not recognized_low, f"recognized={len(recognized)}, low={len(recognized_low)}")

    family_fields = {
        "reaction_family",
        "reaction_family_confidence",
        "reaction_family_signals",
        "reaction_family_scope",
        "reaction_family_conflict",
    }
    missing_family = [record.get("claim_id") or record.get("evidence_id") for record in claims if not family_fields <= set(record)]
    _check(checks, "reaction-family confidence fields", bool(claims) and not missing_family, f"records={len(claims)}, missing={len(missing_family)}")

    inconsistent_review = [
        record
        for record in audits
        if bool(record.get("needs_human_review")) != bool(record.get("overall_needs_human_review"))
        or (str(record.get("review_priority_band") or "") in {"high", "critical"} and not _truthy(record.get("overall_needs_human_review")))
    ]
    _check(checks, "review semantics consistency", bool(audits) and not inconsistent_review, f"records={len(audits)}, inconsistent={len(inconsistent_review)}")

    baseline = next((route for route in routes if route.get("route_type") == "baseline_repeatability"), None)
    expanded_baseline = expand_route_execution_rows(baseline) if baseline else []
    baseline_valid = (
        len(expanded_baseline) == 3
        and all(_truthy(row.get("independent_replicate")) for row in expanded_baseline)
        and len({row.get("execution_id") for row in expanded_baseline}) == 3
    )
    _check(checks, "baseline expands to three independent executions", baseline_valid, f"rows={len(expanded_baseline)}")

    missing_stage = [route.get("route_id") for route in routes if not STAGE_FIELDS <= set(route)]
    _check(checks, "route stage fields", bool(routes) and not missing_stage, f"routes={len(routes)}, missing={len(missing_stage)}")

    executable = [route for route in routes if not route.get("is_route_group")]
    missing_feasibility = [route.get("route_id") for route in executable if not FEASIBILITY_FIELDS <= set(route)]
    _check(checks, "control and measurement feasibility fields", bool(executable) and not missing_feasibility, f"executable={len(executable)}, missing={len(missing_feasibility)}")

    hierarchy_routes = routes if any(route.get("is_route_group") for route in routes) else _synthetic_hierarchy_routes(run_name)
    hierarchy_valid, hierarchy_detail = _validate_hierarchy(hierarchy_routes)
    _check(checks, "electrolyte parent-child hierarchy", hierarchy_valid, hierarchy_detail)

    migrated_legacy, nox_warnings = migrate_lab_profile({"analytics": {"NOx_quantification_available": True}})
    nox_valid = not capability_available(migrated_legacy, "gas_phase_NOx_quantification_available") and bool(nox_warnings)
    _check(checks, "legacy NOx does not imply gas-phase NOx", nox_valid, f"warnings={len(nox_warnings)}")

    false_high_review = [
        record
        for record in audits
        if str(record.get("review_priority_band") or "") in {"high", "critical"}
        and not _truthy(record.get("overall_needs_human_review"))
    ]
    _check(checks, "high-priority audit routing", not false_high_review, f"false_rows={len(false_high_review)}")

    roundtrip_valid, roundtrip_detail = _roundtrip_schemas(run_name, routes)
    _check(checks, "route/result schema round-trip", roundtrip_valid, roundtrip_detail)

    before = {
        "body_low_confidence_count": sum(
            1
            for record in classified
            if str(record.get("provenance_type") or "body") == "body"
            and str(record.get("provenance_confidence") or "low") == "low"
        ),
        "reaction_family_unclear_count": sum(1 for record in classified if str(record.get("reaction_family") or "unclear") == "unclear"),
        "legacy_needs_human_review_count": sum(1 for record in audits if _truthy(record.get("needs_human_review"))),
        "baseline_execution_row_count": 1 if baseline else 0,
        "stage_distribution": {"unassigned": len(routes)},
        "blocked_route_count": 0,
        "actionable_route_count": 0,
        "missing_measurement_capability_count": 0,
        "NOx_capability_migration_warning_count": 0,
    }
    after = {
        "body_low_confidence_count": sum(
            1
            for record in provenance
            if str(record.get("provenance_type") or "unknown") == "body"
            and str(record.get("provenance_confidence") or "low") == "low"
        ),
        "reaction_family_unclear_count": sum(1 for record in claims if str(record.get("reaction_family") or "unclear") == "unclear"),
        "rule_review_count": sum(1 for record in audits if _truthy(record.get("rule_needs_human_review"))),
        "llm_review_count": sum(1 for record in audits if _truthy(record.get("llm_needs_human_review"))),
        "overall_review_count": sum(1 for record in audits if _truthy(record.get("overall_needs_human_review"))),
        "baseline_execution_row_count": sum(1 for row in result_rows if row.get("route_id") == (baseline or {}).get("route_id")),
        "stage_distribution": dict(sorted(Counter(str(route.get("execution_stage") or "unknown") for route in routes).items())),
        "blocked_route_count": sum(1 for route in routes if route.get("stage_gate_status") == "blocked"),
        "actionable_route_count": sum(1 for route in routes if route.get("stage_gate_status") in {"actionable", "waived", "event_triggered"}),
        "missing_measurement_capability_count": sum(len(route.get("infeasible_measurements") or []) for route in executable),
        "NOx_capability_migration_warning_count": len(nox_warnings),
    }
    return {
        "checks": checks,
        "checks_total": len(checks),
        "checks_passed": sum(1 for check in checks if check["passed"]),
        "before": before,
        "after": after,
    }


def _synthetic_hierarchy_routes(run_name: str) -> list[dict[str, Any]]:
    return propose_rule_based_routes(
        [
            {
                "gap_type": "solvent_management_tax",
                "route_type_hint": "electrolyte_window",
                "hidden_tax": "solvent_management_tax",
                "source_basis_id": "SMOKE_CR1",
                "paper_id": "SMOKE_P1",
                "source_span_id": "SMOKE_S1",
                "primary_evidence": True,
                "reaction_family": "LiNRR",
            }
        ],
        default_ustc_linnr_profile(profile_template="ustc-linnr-realistic"),
        run_name,
        reaction_family="LiNRR",
        require_baseline_first=True,
    )


def _validate_hierarchy(routes: list[dict[str, Any]]) -> tuple[bool, str]:
    parents = [route for route in routes if route.get("is_route_group") and route.get("route_type") == "electrolyte_window"]
    if not parents:
        return False, "no electrolyte parent"
    parent = parents[0]
    children = [route for route in routes if route.get("parent_route_id") == parent.get("route_id")]
    child_types = {route.get("route_type") for route in children}
    expected = {"water_content_window", "proton_donor_window", "salt_solvent_window"}
    valid = child_types == expected and parent.get("stage_gate_status") == "non_executable"
    return valid, f"children={sorted(str(value) for value in child_types)}"


def _roundtrip_schemas(run_name: str, routes: list[dict[str, Any]]) -> tuple[bool, str]:
    if not routes:
        return False, "no routes available"
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        route_outputs = export_experiment_routes(routes, run_name, output_dir=root / "routes")
        route_roundtrip = load_jsonl(route_outputs["jsonl"])
        result_outputs = export_experiment_result_template(routes, run_name, output_dir=root / "results")
        result_roundtrip = load_jsonl(result_outputs["jsonl"])
    valid = (
        bool(route_roundtrip)
        and bool(result_roundtrip)
        and all(record.get("schema_version") == SCHEMA_VERSION for record in route_roundtrip)
        and all(record.get("schema_version") == SCHEMA_VERSION for record in result_roundtrip)
        and all(record.get("execution_id") and record.get("replicate_id") for record in result_roundtrip)
    )
    return valid, f"routes={len(route_roundtrip)}, results={len(result_roundtrip)}"


def _check(checks: list[dict[str, Any]], name: str, passed: bool, detail: str) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"true", "1", "yes", "y", "passed", "approved"}


def _render_report(run_name: str, payload: dict[str, Any]) -> str:
    lines = [
        f"# v0.13 Integrated Hardening Report: {run_name}",
        "",
        f"- Checks passed: {payload['checks_passed']}/{payload['checks_total']}",
        "- Real LLM API calls: none",
        "",
        "## Release checks",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for check in payload["checks"]:
        lines.append(
            f"| {check['name']} | {'PASS' if check['passed'] else 'FAIL'} | {str(check['detail']).replace('|', '/')} |"
        )
    lines.extend(
        [
            "",
            "## Before metrics",
            "",
            "```json",
            json.dumps(payload["before"], ensure_ascii=True, indent=2, sort_keys=True),
            "```",
            "",
            "## After metrics",
            "",
            "```json",
            json.dumps(payload["after"], ensure_ascii=True, indent=2, sort_keys=True),
            "```",
            "",
            "## Limitations",
            "",
            "- Before metrics use legacy one-row and unassigned-stage assumptions when those fields did not previously exist.",
            "- This smoke check validates local deterministic rules and mock-free execution; it does not validate a real LLM provider.",
            "- Repeatability thresholds remain profile-specific or require human baseline approval.",
            "",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
