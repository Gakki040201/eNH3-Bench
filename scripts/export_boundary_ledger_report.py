from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.ledger_router import load_jsonl  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export an eNH3-BoundaryLedger Markdown report.")
    parser.add_argument("--run-name", default="final_pilot")
    parser.add_argument("--boundary-dir", type=Path, default=Path("data") / "boundary_ledger")
    parser.add_argument("--report-dir", type=Path, default=Path("data") / "reports")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.boundary_dir / args.run_name
    bundles = load_jsonl(run_dir / "evidence_bundles.jsonl")
    claims = load_jsonl(run_dir / "claim_rights_ledger.jsonl")
    taxes = load_jsonl(run_dir / "hidden_tax_ledger.jsonl")
    report = render_report(args.run_name, bundles, claims, taxes)
    output_path = args.report_dir / f"boundary_ledger_report.{args.run_name}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8", newline="\n")
    print(f"BoundaryLedger report: {output_path}")
    print(f"Evidence bundles: {len(bundles)}")
    print(f"Claim-rights records: {len(claims)}")
    print(f"Hidden-tax records: {len(taxes)}")
    return 0


def render_report(
    run_name: str,
    bundles: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    taxes: list[dict[str, Any]],
) -> str:
    lines = [
        f"# eNH3-BoundaryLedger Report: {run_name}",
        "",
        "## 1. What eNH3-BoundaryLedger adds",
        "",
        (
            "eNH3-BoundaryLedger adds a source-grounded claim-rights layer above "
            "eNH3-TriageBench span classification. It asks what a claim is allowed "
            "to support: product admissibility, cell metrics, reactor legibility, "
            "partial process boundaries, or only secondary/contextual use."
        ),
        "",
        "## 2. Evidence bundle count",
        "",
        f"- Evidence bundles: {len(bundles)}",
        f"- Claim-rights records: {len(claims)}",
        f"- Hidden-tax records: {len(taxes)}",
        "",
        "## 3. Claim type distribution",
        "",
        _counter_table(_counter(claims, "claim_type"), "Claim type"),
        "",
        "## 4. Maximum supported boundary distribution",
        "",
        _counter_table(_counter(claims, "maximum_supported_boundary"), "Boundary"),
        "",
        "## 5. Admissibility status distribution",
        "",
        _counter_table(_counter(claims, "admissibility_status"), "Status"),
        "",
        "## 6. Missing boundary fields",
        "",
        _counter_table(_list_counter(claims, "missing_boundary_fields"), "Missing field"),
        "",
        "## 7. Required controls",
        "",
        _counter_table(_list_counter(claims, "required_controls"), "Required control"),
        "",
        "## 8. Hidden tax distribution",
        "",
        _counter_table(_list_counter(taxes, "detected_taxes"), "Hidden tax"),
        "",
        "## 9. Provenance distribution",
        "",
        _counter_table(_counter(_records_with_provenance(bundles, claims), "provenance_type"), "Provenance type"),
        "",
        "## 10. Caption support hints",
        "",
        _caption_support_hint_section(claims),
        "",
        "## 11. Claim-rights decisions changed by provenance",
        "",
        _provenance_constrained_examples(claims),
        "",
        "## 12. Text-class/provenance conflicts",
        "",
        _conflict_examples(claims),
        "",
        "## 13. Low-trust provenance warnings",
        "",
        _low_trust_examples(claims),
        "",
        "## 14. High-risk overclaim examples",
        "",
        _high_risk_examples(claims, taxes),
        "",
        "## 15. Hidden-tax records constrained by low-trust provenance",
        "",
        _low_trust_hidden_tax_examples(taxes),
        "",
        "## 16. Why this is not generic literature extraction",
        "",
        (
            "Generic extraction asks what values are present in text. BoundaryLedger "
            "asks what those values are allowed to support after eNH3-specific "
            "validation gates, reactor descriptors, process-boundary fields, and "
            "hidden taxes are considered. The output is therefore an admissibility "
            "ledger, not just a table of extracted material-property records."
        ),
        "",
    ]
    return "\n".join(lines)


def _counter(records: list[dict[str, Any]], key: str) -> Counter[str]:
    return Counter(str(record.get(key) or "missing") for record in records)


def _list_counter(records: list[dict[str, Any]], key: str) -> Counter[str]:
    counter: Counter[str] = Counter()
    for record in records:
        value = record.get(key)
        if isinstance(value, list):
            if value:
                counter.update(str(item) for item in value)
            continue
        if isinstance(value, str) and value:
            counter.update([value])
    return counter


def _records_with_provenance(
    bundles: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if any(record.get("provenance_type") for record in bundles):
        return bundles
    return claims


def _counter_table(counter: Counter[str], label: str) -> str:
    if not counter:
        return "No records."
    rows = [[key, count] for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))]
    return _markdown_table([label, "Records"], rows)


def _high_risk_examples(claims: list[dict[str, Any]], taxes: list[dict[str, Any]], limit: int = 10) -> str:
    tax_by_evidence = {str(tax.get("evidence_id") or ""): tax for tax in taxes}
    rows: list[list[Any]] = []
    for claim in claims:
        flags = claim.get("overclaim_risk_flags") or []
        status = str(claim.get("admissibility_status") or "")
        boundary = str(claim.get("maximum_supported_boundary") or "")
        risky = bool(flags) or status in {"reject", "secondary_only", "metric_only_or_validation_incomplete", "plant_facing_incomplete"}
        if not risky:
            continue
        evidence_id = str(claim.get("evidence_id") or "")
        tax = tax_by_evidence.get(evidence_id, {})
        rows.append(
            [
                claim.get("claim_id") or "",
                claim.get("paper_id") or "",
                boundary,
                status,
                "; ".join(str(flag) for flag in flags[:3]),
                "; ".join(str(item) for item in (tax.get("detected_taxes") or [])[:3]),
                _preview(claim.get("source_text") or ""),
            ]
        )
        if len(rows) >= limit:
            break
    if not rows:
        return "No high-risk overclaim examples were found."
    return _markdown_table(["Claim", "Paper", "Boundary", "Status", "Risk flags", "Hidden taxes", "Source preview"], rows)


def _provenance_constrained_examples(claims: list[dict[str, Any]], limit: int = 12) -> str:
    selected = [claim for claim in claims if bool(claim.get("provenance_constrained"))]
    if not selected:
        return "No claim-rights decisions were provenance-constrained in this run."
    rows = [
        [
            claim.get("claim_id") or "",
            claim.get("paper_id") or "",
            claim.get("text_class") or "",
            claim.get("provenance_type") or "",
            claim.get("maximum_supported_boundary") or "",
            claim.get("admissibility_status") or "",
        ]
        for claim in selected[:limit]
    ]
    return _markdown_table(["Claim", "Paper", "Text class", "Provenance", "Boundary", "Status"], rows)


def _conflict_examples(claims: list[dict[str, Any]], limit: int = 12) -> str:
    selected = [claim for claim in claims if bool(claim.get("text_class_provenance_conflict"))]
    if not selected:
        return "No text-class/provenance conflicts were found."
    rows = [
        [
            claim.get("claim_id") or "",
            claim.get("paper_id") or "",
            claim.get("text_class") or "",
            claim.get("provenance_type") or "",
            "; ".join(str(flag) for flag in (claim.get("overclaim_risk_flags") or [])[:4]),
            _preview(claim.get("source_text") or ""),
        ]
        for claim in selected[:limit]
    ]
    return _markdown_table(["Claim", "Paper", "Text class", "Provenance", "Flags", "Source preview"], rows)


def _low_trust_examples(claims: list[dict[str, Any]], limit: int = 12) -> str:
    selected = [
        claim
        for claim in claims
        if bool(claim.get("is_reject_or_low_trust")) or claim.get("admissibility_status") == "reject_or_low_trust_provenance"
    ]
    if not selected:
        return "No low-trust provenance warnings were found."
    rows = [
        [
            claim.get("claim_id") or "",
            claim.get("paper_id") or "",
            claim.get("provenance_type") or "",
            claim.get("admissibility_status") or "",
            _preview(claim.get("source_text") or ""),
        ]
        for claim in selected[:limit]
    ]
    return _markdown_table(["Claim", "Paper", "Provenance", "Status", "Source preview"], rows)


def _caption_support_hint_section(claims: list[dict[str, Any]]) -> str:
    captions = [
        claim
        for claim in claims
        if str(claim.get("provenance_type") or "") in {"figure_caption", "scheme_caption"}
        or str(claim.get("admissibility_status") or "") == "context_only_caption"
    ]
    lines = [
        f"- Caption/context records: {len(captions)}",
        "",
        "Caption support hints are not primary claim boundaries.",
        "",
        _counter_table(_counter(captions, "support_hint_boundary"), "Support hint boundary"),
    ]
    return "\n".join(lines)


def _low_trust_hidden_tax_examples(taxes: list[dict[str, Any]], limit: int = 12) -> str:
    selected = [
        tax
        for tax in taxes
        if "Low-trust provenance constrained domain-tax detection." in _list_values(tax.get("reasoning"))
    ]
    if not selected:
        return "No hidden-tax records were constrained by low-trust provenance in this run."
    rows = [
        [
            tax.get("tax_record_id") or "",
            tax.get("paper_id") or "",
            tax.get("provenance_type") or "",
            "; ".join(str(item) for item in (tax.get("detected_taxes") or [])[:4]),
            tax.get("severity") or "",
            _preview(tax.get("source_text") or ""),
        ]
        for tax in selected[:limit]
    ]
    return _markdown_table(["Tax record", "Paper", "Provenance", "Detected taxes", "Severity", "Source preview"], rows)


def _preview(value: Any, limit: int = 160) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _list_values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(_escape_cell(value) for value in row) + " |")
    return "\n".join(lines)


def _escape_cell(value: Any) -> str:
    if isinstance(value, (list, dict)):
        value = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return str(value).replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
