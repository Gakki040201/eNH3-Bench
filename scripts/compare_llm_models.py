from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.llm_clients import MockLLMClient, OpenAICompatibleClient  # noqa: E402
from enh3bench.llm_verifier import (  # noqa: E402
    export_llm_verification_results,
    load_claim_rights_records,
    verify_records_with_llm,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare optional LLM verification models for BoundaryLedger.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--models", required=True)
    parser.add_argument("--max-records", type=int, default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--timeout", type=int, default=60)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_claim_rights_records(args.run_name)
    models = [model.strip() for model in args.models.split(",") if model.strip()]
    rows: list[dict[str, Any]] = []
    for model in models:
        client = MockLLMClient() if args.mock else OpenAICompatibleClient(base_url=args.base_url, model=model, timeout=args.timeout)
        client.temperature = args.temperature
        client.max_tokens = args.max_tokens
        client.timeout = args.timeout
        available, message = client.verify_available()
        if not available:
            rows.append(_unavailable_row(model, records, args.max_records, message))
            continue
        results, failures = verify_records_with_llm(records, client, model=model, max_records=args.max_records)
        export_llm_verification_results(results, failures, args.run_name, model)
        rows.append(_comparison_row(model, records, results, failures, args.max_records))

    table_path = Path("data") / "model_runs" / args.run_name / "llm_model_comparison_table.csv"
    report_path = Path("data") / "reports" / f"llm_model_comparison_report.{args.run_name}.md"
    _write_csv(rows, table_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(args.run_name, rows, args), encoding="utf-8", newline="\n")
    print(f"Models compared: {len(rows)}")
    print(f"Comparison table: {table_path}")
    print(f"Comparison report: {report_path}")
    for row in rows:
        print(
            f"{row['model']}: verified={row['records_verified']} failures={row['failures']} "
            f"needs_human_review={row['needs_human_review_count']} "
            f"parse_errors={row['parse_error_count']} schema_errors={row['schema_error_count']} "
            f"trusted_caps={row['trusted_boundary_capped_count']}"
        )
    return 0 if all(not row.get("unavailable_reason") for row in rows) else 2


def _comparison_row(
    model: str,
    records: list[dict[str, Any]],
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    max_records: int | None,
) -> dict[str, Any]:
    attempted = min(len(records), max_records) if max_records is not None else len(records)
    boundary_agreements = sum(1 for result in results if bool(result.get("boundary_agreement")))
    text_agreements = sum(1 for result in results if bool(result.get("text_class_agreement")))
    verified_count = len(results)
    return {
        "model": model,
        "records_attempted": attempted,
        "records_verified": verified_count,
        "failures": len(failures),
        "boundary_agreement_rate": _rate(boundary_agreements, verified_count),
        "text_class_agreement_rate": _rate(text_agreements, verified_count),
        "llm_more_permissive_count": sum(1 for result in results if bool(result.get("llm_more_permissive"))),
        "llm_more_conservative_count": sum(1 for result in results if bool(result.get("llm_more_conservative"))),
        "needs_human_review_count": sum(1 for result in results if bool(result.get("needs_human_review"))),
        "parse_error_count": _error_count(results, "json_parse_error:"),
        "schema_error_count": _error_count(results, "schema_invalid:"),
        "low_trust_provenance_count": sum(1 for result in results if bool(result.get("low_trust_provenance"))),
        "llm_overrode_low_trust_count": _flag_count(results, "llm_overrode_low_trust_provenance"),
        "trusted_boundary_capped_count": _flag_count(results, "trusted_boundary_capped_by_provenance"),
        "unavailable_reason": "",
    }


def _unavailable_row(model: str, records: list[dict[str, Any]], max_records: int | None, reason: str) -> dict[str, Any]:
    attempted = min(len(records), max_records) if max_records is not None else len(records)
    return {
        "model": model,
        "records_attempted": attempted,
        "records_verified": 0,
        "failures": attempted,
        "boundary_agreement_rate": 0.0,
        "text_class_agreement_rate": 0.0,
        "llm_more_permissive_count": 0,
        "llm_more_conservative_count": 0,
        "needs_human_review_count": 0,
        "parse_error_count": 0,
        "schema_error_count": 0,
        "low_trust_provenance_count": 0,
        "llm_overrode_low_trust_count": 0,
        "trusted_boundary_capped_count": 0,
        "unavailable_reason": reason,
    }


def _render_report(run_name: str, rows: list[dict[str, Any]], args: argparse.Namespace) -> str:
    lines = [
        f"# LLM Model Comparison Report: {run_name}",
        "",
        "## 1. What was compared",
        "",
        f"- Models: {', '.join(row['model'] for row in rows) or 'none'}",
        f"- Max records: {args.max_records if args.max_records is not None else 'all'}",
        f"- Mock mode: {bool(args.mock)}",
        "",
        "## 2. Why LLM verification is optional",
        "",
        "BoundaryLedger remains rule-based. LLM verification is an audit layer that can disagree with or question rule outputs, but it does not overwrite them.",
        "",
        "## 3. Model-level agreement with rule BoundaryLedger",
        "",
        _markdown_table(
            ["Model", "Verified", "Boundary agreement", "Text-class agreement"],
            [[row["model"], row["records_verified"], row["boundary_agreement_rate"], row["text_class_agreement_rate"]] for row in rows],
        ),
        "",
        "## 4. More permissive vs more conservative decisions",
        "",
        _markdown_table(
            ["Model", "More permissive", "More conservative"],
            [[row["model"], row["llm_more_permissive_count"], row["llm_more_conservative_count"]] for row in rows],
        ),
        "",
        "## 5. Records needing human review",
        "",
        _markdown_table(["Model", "Needs human review"], [[row["model"], row["needs_human_review_count"]] for row in rows]),
        "",
        "## 6. Low-trust provenance constrained LLM upgrades",
        "",
        _markdown_table(
            ["Model", "Low-trust records", "LLM overrode low-trust", "Trusted boundary capped"],
            [
                [
                    row["model"],
                    row["low_trust_provenance_count"],
                    row["llm_overrode_low_trust_count"],
                    row["trusted_boundary_capped_count"],
                ]
                for row in rows
            ],
        ),
        "",
        "## 7. Trusted LLM boundary after provenance cap",
        "",
        "When low-trust provenance attempts a more permissive boundary, the original LLM output is preserved while the trusted LLM boundary is capped to the rule/provenance-constrained boundary.",
        "",
        "## 8. Parse, schema, and API failures",
        "",
        _markdown_table(
            ["Model", "Failures", "Parse errors", "Schema errors", "Unavailable reason"],
            [[row["model"], row["failures"], row["parse_error_count"], row["schema_error_count"], row["unavailable_reason"]] for row in rows],
        ),
        "",
        "## 9. Safety statement: LLM output is not gold",
        "",
        "LLM output is only a verification and disagreement signal. Human review is required before any label can become gold evidence.",
        "",
        "## 10. Recommended next audit actions",
        "",
        "- Review more-permissive LLM decisions first, especially low-trust provenance upgrades.",
        "- Review more-conservative LLM decisions to identify missing rule checks.",
        "- Treat parse/API failures as model-run quality issues, not scientific evidence.",
        "",
    ]
    return "\n".join(lines)


def _write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "model",
        "records_attempted",
        "records_verified",
        "failures",
        "boundary_agreement_rate",
        "text_class_agreement_rate",
        "llm_more_permissive_count",
        "llm_more_conservative_count",
        "needs_human_review_count",
        "parse_error_count",
        "schema_error_count",
        "low_trust_provenance_count",
        "llm_overrode_low_trust_count",
        "trusted_boundary_capped_count",
        "unavailable_reason",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |")
    return "\n".join(lines)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)


def _error_count(results: list[dict[str, Any]], prefix: str) -> int:
    return sum(1 for result in results if str(result.get("llm_parse_error") or "").startswith(prefix))


def _flag_count(results: list[dict[str, Any]], flag: str) -> int:
    return sum(1 for result in results if flag in _list_values(result.get("llm_audit_flags")))


def _list_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                import json

                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        return [part.strip() for part in stripped.split(",") if part.strip()]
    return []


if __name__ == "__main__":
    raise SystemExit(main())
