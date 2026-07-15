"""Build and export source-grounded Evidence Context Packets."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from enh3bench.evidence_linking import DEFAULT_LINK_LIMITS, link_supporting_evidence
from enh3bench.span_context import (
    build_document_span_index,
    get_next_spans,
    get_previous_spans,
    get_same_section_spans,
    validate_no_cross_paper_links,
)


CONTEXT_PACKET_SCHEMA_VERSION = "1.0"
PACKET_FIELDS = (
    "context_packet_schema_version",
    "context_packet_id",
    "run_name",
    "paper_id",
    "paper_title",
    "paper_abstract",
    "paper_level_reaction_family",
    "paper_level_reaction_family_confidence",
    "target_span_id",
    "target_stable_span_uid",
    "target_span_order",
    "target_text",
    "target_text_class",
    "target_provenance_type",
    "target_section_heading",
    "target_section_path",
    "target_reaction_family",
    "target_span_boundary",
    "target_admissibility_status",
    "previous_spans",
    "next_spans",
    "same_section_spans",
    "linked_performance_spans",
    "linked_validation_spans",
    "linked_quantification_spans",
    "linked_reactor_spans",
    "linked_process_spans",
    "linked_negative_or_contradicting_spans",
    "context_hint_spans",
    "context_sufficient",
    "context_missing_types",
    "context_confidence",
    "linking_signals",
    "warnings",
)

LINK_PACKET_FIELDS = {
    "performance": "linked_performance_spans",
    "validation": "linked_validation_spans",
    "quantification": "linked_quantification_spans",
    "reactor": "linked_reactor_spans",
    "process": "linked_process_spans",
    "negative_or_contradicting": "linked_negative_or_contradicting_spans",
    "context_hint": "context_hint_spans",
}

LOW_TRUST_PROVENANCE = {"reference", "bibliography", "figure_caption", "scheme_caption", "review_table"}
LOW_TRUST_TEXT_CLASSES = {"reference_list", "figure_caption", "review_table", "background_context"}
BOUNDARY_RANK = {
    "unsupported_or_secondary": 0,
    "product_admissibility": 1,
    "cell_metric": 2,
    "reactor_legibility": 3,
    "process_partial": 4,
    "plant_facing_insufficient": 5,
}


def merge_context_sources(
    evidence_bundles: list[dict[str, Any]],
    claim_rights: list[dict[str, Any]] | None = None,
    hidden_tax: list[dict[str, Any]] | None = None,
    provenance: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Merge context inputs by source_span_id without mutating any ledger."""

    claim_index = _index_by_span(claim_rights or [])
    tax_index = _index_by_span(hidden_tax or [])
    provenance_index = _index_by_span(provenance or [])
    merged: list[dict[str, Any]] = []
    for bundle in evidence_bundles:
        record = dict(bundle)
        span_id = _span_id(record)
        extracted = record.get("extracted_fields")
        if isinstance(extracted, dict):
            for key, value in extracted.items():
                record.setdefault(key, value)
        raw = record.get("raw_record")
        if isinstance(raw, dict):
            for key in ("paper_title", "title", "paper_abstract", "abstract", "section_path", "section_heading", "span_order"):
                if raw.get(key) not in (None, ""):
                    record.setdefault(key, raw[key])
        claim = claim_index.get(span_id, {})
        tax = tax_index.get(span_id, {})
        prov = provenance_index.get(span_id, {})
        for key, value in claim.items():
            if key not in {"paper_id", "source_span_id", "source_text"} or not record.get(key):
                record[key] = value
        if tax:
            record["detected_taxes"] = tax.get("detected_taxes") or []
            record["hidden_tax_missing_measurements"] = tax.get("missing_measurements") or []
            record["hidden_tax_required_controls"] = tax.get("required_controls") or []
            record["hidden_tax_severity"] = tax.get("severity") or ""
        for key in (
            "section_path",
            "section_heading",
            "section_type",
            "section_confidence",
            "provenance_type",
            "provenance_confidence",
            "is_primary_admissible",
            "is_secondary_or_context",
            "is_reject_or_low_trust",
        ):
            if prov.get(key) not in (None, "", []):
                record[key] = prov[key]
        record["source_span_id"] = span_id
        merged.append(record)
    return merged


def build_context_packets(
    evidence_bundles: list[dict[str, Any]],
    claim_rights: list[dict[str, Any]] | None,
    hidden_tax: list[dict[str, Any]] | None,
    provenance: list[dict[str, Any]] | None,
    *,
    run_name: str,
    adjacent_before: int = 1,
    adjacent_after: int = 1,
    same_section_maximum: int = 4,
    maximum_per_category: int = 2,
    maximum_total_links: int = 12,
) -> list[dict[str, Any]]:
    """Build one packet per target evidence bundle."""

    merged = merge_context_sources(evidence_bundles, claim_rights, hidden_tax, provenance)
    index = build_document_span_index(merged)
    limits = {
        **DEFAULT_LINK_LIMITS,
        "adjacent_before": adjacent_before,
        "adjacent_after": adjacent_after,
        "same_section_maximum": same_section_maximum,
        "maximum_per_category": maximum_per_category,
        "maximum_total_links": maximum_total_links,
    }
    packets: list[dict[str, Any]] = []
    for span_id, target in index.records_by_id.items():
        paper_records = index.paper_records[str(target["paper_id"])]
        links = link_supporting_evidence(target, paper_records, limits)
        previous = get_previous_spans(index, span_id, adjacent_before)
        following = get_next_spans(index, span_id, adjacent_after)
        same_section = get_same_section_spans(index, span_id, same_section_maximum)
        packet_links = {packet_field: links[link_type] for link_type, packet_field in LINK_PACKET_FIELDS.items()}
        missing, sufficient, confidence = _context_sufficiency(target, packet_links)
        warnings = [*target.get("span_identity_warnings", []), *links["warnings"]]
        if bool(target.get("reaction_family_conflict")):
            warnings.append("target_reaction_family_conflict")
        packet = {
            "context_packet_schema_version": CONTEXT_PACKET_SCHEMA_VERSION,
            "context_packet_id": _packet_id(run_name, target),
            "run_name": run_name,
            "paper_id": str(target.get("paper_id") or ""),
            "paper_title": _first_value(target, "paper_title", "title"),
            "paper_abstract": _first_value(target, "paper_abstract", "abstract"),
            "paper_level_reaction_family": str(target.get("paper_level_reaction_family") or "unclear"),
            "paper_level_reaction_family_confidence": str(target.get("paper_level_reaction_family_confidence") or "unclear"),
            "target_span_id": span_id,
            "target_stable_span_uid": str(target.get("stable_span_uid") or ""),
            "target_span_order": target.get("span_order"),
            "target_text": str(target.get("source_text") or ""),
            "target_text_class": str(target.get("text_class") or "unknown"),
            "target_provenance_type": str(target.get("provenance_type") or "unknown"),
            "target_section_heading": str(target.get("section_heading") or ""),
            "target_section_path": target.get("section_path") or [],
            "target_reaction_family": str(target.get("reaction_family") or "unclear"),
            "target_span_boundary": str(target.get("maximum_supported_boundary") or "unsupported_or_secondary"),
            "target_admissibility_status": str(target.get("admissibility_status") or ""),
            "previous_spans": previous,
            "next_spans": following,
            "same_section_spans": same_section,
            **packet_links,
            "context_sufficient": sufficient,
            "context_missing_types": missing,
            "context_confidence": confidence,
            "linking_signals": links["linking_signals"],
            "warnings": _dedupe(warnings),
        }
        validate_no_cross_paper_links(packet)
        packets.append(packet)
    return packets


def summarize_context_packets(packets: list[dict[str, Any]], run_name: str) -> dict[str, Any]:
    missing = Counter()
    linked = Counter()
    paper_link_counts: dict[str, int] = defaultdict(int)
    total_links = 0
    maximum_links = 0
    cross_paper = 0
    low_trust_primary = {"reference": 0, "caption": 0, "review_table": 0}
    warning_count = 0
    for packet in packets:
        missing.update(packet.get("context_missing_types") or [])
        packet_links = 0
        try:
            validate_no_cross_paper_links(packet)
        except ValueError:
            cross_paper += 1
        for link_type, field in LINK_PACKET_FIELDS.items():
            records = packet.get(field) or []
            linked[link_type] += len(records)
            packet_links += len(records)
            for record in records:
                if not record.get("primary_support"):
                    continue
                provenance = str(record.get("provenance_type") or "").casefold()
                text_class = str(record.get("text_class") or "").casefold()
                if provenance in {"reference", "bibliography"} or text_class == "reference_list":
                    low_trust_primary["reference"] += 1
                if provenance in {"figure_caption", "scheme_caption"} or text_class == "figure_caption":
                    low_trust_primary["caption"] += 1
                if provenance == "review_table" or text_class == "review_table":
                    low_trust_primary["review_table"] += 1
        total_links += packet_links
        maximum_links = max(maximum_links, packet_links)
        paper_link_counts[str(packet.get("paper_id") or "")] += packet_links
        warning_count += len(packet.get("warnings") or [])
    packet_count = len(packets)
    return {
        "run_name": run_name,
        "packet_count": packet_count,
        "paper_count": len({str(packet.get("paper_id") or "") for packet in packets}),
        "packets_with_context_sufficient": sum(bool(packet.get("context_sufficient")) for packet in packets),
        "packets_with_context_insufficient": sum(not bool(packet.get("context_sufficient")) for packet in packets),
        "missing_type_distribution": dict(sorted(missing.items())),
        "linked_span_distribution": dict(sorted(linked.items())),
        "average_links_per_packet": round(total_links / packet_count, 4) if packet_count else 0.0,
        "maximum_links_per_packet": maximum_links,
        "cross_paper_link_count": cross_paper,
        "reference_primary_support_count": low_trust_primary["reference"],
        "caption_primary_support_count": low_trust_primary["caption"],
        "review_table_primary_support_count": low_trust_primary["review_table"],
        "warnings_count": warning_count,
        "paper_link_counts": dict(sorted(paper_link_counts.items())),
    }


def export_context_packets(
    packets: list[dict[str, Any]],
    run_name: str,
    *,
    output_dir: str | Path = "data/context_packets",
    report_dir: str | Path = "data/reports",
) -> dict[str, Any]:
    run_dir = Path(output_dir) / run_name
    jsonl_path = run_dir / "context_packets.jsonl"
    csv_path = run_dir / "context_packets.csv"
    summary_path = run_dir / "context_packet_summary.json"
    report_path = Path(report_dir) / f"context_packet_report.{run_name}.md"
    summary = summarize_context_packets(packets, run_name)
    _write_jsonl(packets, jsonl_path)
    _write_csv(packets, csv_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_render_report(packets, summary), encoding="utf-8", newline="\n")
    return {
        "run_name": run_name,
        "count": len(packets),
        "jsonl": str(jsonl_path),
        "csv": str(csv_path),
        "summary": str(summary_path),
        "report": str(report_path),
        "summary_data": summary,
    }


def _context_sufficiency(
    target: dict[str, Any], packet_links: dict[str, list[dict[str, Any]]]
) -> tuple[list[str], bool, str]:
    missing: list[str] = []
    text = str(target.get("source_text") or "").casefold()
    provenance = str(target.get("provenance_type") or "unknown").casefold()
    text_class = str(target.get("text_class") or "unknown").casefold()
    context_only = provenance in LOW_TRUST_PROVENANCE or text_class in LOW_TRUST_TEXT_CLASSES
    if context_only:
        sufficient = bool(text and provenance != "unknown" and text_class != "unknown")
        return ([] if sufficient else ["primary_body_text"], sufficient, "high" if sufficient else "low")

    family = str(target.get("reaction_family") or "unclear")
    if family in {"", "unclear"} or bool(target.get("reaction_family_conflict")):
        missing.append("reaction_family")
    is_primary_performance = text_class in {"primary_performance", "primary_performance_with_validation"} or str(
        target.get("claim_type") or ""
    ) in {"performance_claim", "validation_claim", "reactor_claim", "process_claim"}
    if not is_primary_performance:
        sufficient = bool(text)
        return (_dedupe(missing), sufficient and not missing, "medium" if sufficient else "low")
    if not _contains_performance_metric(text, target):
        missing.append("performance_metric")
    if provenance in LOW_TRUST_PROVENANCE:
        missing.append("primary_body_text")

    boundary = str(target.get("maximum_supported_boundary") or "unsupported_or_secondary")
    rank = BOUNDARY_RANK.get(boundary, 0)
    linked_validation_text = _linked_text(packet_links.get("linked_validation_spans", []))
    linked_quant_text = _linked_text(packet_links.get("linked_quantification_spans", []))
    gates = target.get("validation_gates") if isinstance(target.get("validation_gates"), dict) else {}
    if rank >= BOUNDARY_RANK["cell_metric"]:
        if family in {"eNRR", "LiNRR"} and not _gate_or_text(gates, "isotope_15N", text + linked_validation_text, ("15n", "isotope")):
            missing.append("isotope_validation")
        if not _gate_or_text(gates, "blank_control", text + linked_validation_text, ("blank", "n2-free", "argon")):
            missing.append("blank_control")
        if not _gate_or_text(gates, "nox_control", text + linked_validation_text, ("nox", "nitrate", "nitrite")):
            missing.append("NOx_control")
        if not _gate_or_text(gates, "contamination_control", text + linked_validation_text, ("contamination control", "impurity screen")):
            missing.append("contamination_control")
        if not _gate_or_text(gates, "quantification_method", text + linked_quant_text, ("chromatography", "nmr", "colorimetric", "uv-vis", "calibration")):
            missing.append("quantification_method")
    if rank >= BOUNDARY_RANK["reactor_legibility"] and not packet_links.get("linked_reactor_spans"):
        if not any(term in text for term in ("flow cell", "gde", "active area", "flow rate", "outlet")):
            missing.append("reactor_details")
    if rank >= BOUNDARY_RANK["process_partial"] and not packet_links.get("linked_process_spans"):
        if not any(term in text for term in ("capture", "separation", "recycle", "hydrogen source", "auxiliary")):
            missing.append("process_boundary")
    if any(term in text for term in ("false positive", "contamination", "background ammonia")) and not packet_links.get(
        "linked_negative_or_contradicting_spans"
    ):
        missing.append("negative_evidence_resolution")
    missing = _dedupe(missing)
    sufficient = not missing
    confidence = "high" if sufficient else ("medium" if len(missing) <= 2 else "low")
    return missing, sufficient, confidence


def _render_report(packets: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    missing = sorted(summary["missing_type_distribution"].items(), key=lambda item: (-item[1], item[0]))[:10]
    high_papers = sorted(summary["paper_link_counts"].items(), key=lambda item: (-item[1], item[0]))[:10]
    order_warnings = [packet["target_span_id"] for packet in packets if any("span_order" in warning for warning in packet["warnings"])][:10]
    family_conflicts = [packet["target_span_id"] for packet in packets if "target_reaction_family_conflict" in packet["warnings"]][:10]
    negative_examples = [packet["target_span_id"] for packet in packets if packet["linked_negative_or_contradicting_spans"]][:5]
    hint_examples = [packet["target_span_id"] for packet in packets if packet["context_hint_spans"]][:5]
    lines = [
        f"# Evidence Context Packet Report: {summary['run_name']}", "",
        f"- Packets: {summary['packet_count']}", f"- Papers: {summary['paper_count']}",
        f"- Context sufficient: {summary['packets_with_context_sufficient']}",
        f"- Context insufficient: {summary['packets_with_context_insufficient']}",
        f"- Cross-paper links: {summary['cross_paper_link_count']}",
        f"- Reference primary support: {summary['reference_primary_support_count']}",
        f"- Caption primary support: {summary['caption_primary_support_count']}",
        f"- Review-table primary support: {summary['review_table_primary_support_count']}", "",
        "## Most common missing context", "", *_bullet_pairs(missing), "",
        "## Papers with unusually high link counts", "", *_bullet_pairs(high_papers), "",
        "## Unparseable span order examples", "", *_bullets(order_warnings), "",
        "## Target/paper family conflict examples", "", *_bullets(family_conflicts), "",
        "## Negative evidence linked examples", "", *_bullets(negative_examples), "",
        "## Reference/caption context-hint examples", "", *_bullets(hint_examples), "",
    ]
    return "\n".join(lines)


def _index_by_span(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        span_id = _span_id(record)
        if span_id and span_id not in result:
            result[span_id] = record
    return result


def _span_id(record: dict[str, Any]) -> str:
    return str(record.get("source_span_id") or record.get("span_id") or record.get("legacy_span_id") or "").strip()


def _packet_id(run_name: str, target: dict[str, Any]) -> str:
    payload = f"{run_name}\0{target.get('paper_id')}\0{target.get('stable_span_uid')}".encode("utf-8")
    return "CP_" + hashlib.sha256(payload).hexdigest()[:32]


def _contains_performance_metric(text: str, target: dict[str, Any]) -> bool:
    if any(target.get(key) not in (None, "", [], {}) for key in ("faradaic_efficiency_percent", "FE_percent", "nh3_yield_value", "current_density", "potential_value", "voltage", "runtime", "stability_hours")):
        return True
    return any(term in text for term in ("faradaic efficiency", " nh3 yield", "ammonia yield", "current density", "potential", "voltage", "runtime", "stability")) or " fe " in f" {text} "


def _gate_or_text(gates: dict[str, Any], key: str, text: str, signals: tuple[str, ...]) -> bool:
    if str(gates.get(key) or "").casefold() in {"yes", "explicit"}:
        return True
    return any(signal in text for signal in signals)


def _linked_text(records: list[dict[str, Any]]) -> str:
    return " ".join(str(record.get("source_text") or "").casefold() for record in records)


def _first_value(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if str(record.get(key) or "").strip():
            return str(record[key]).strip()
    return ""


def _write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n")


def _write_csv(records: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(PACKET_FIELDS))
        writer.writeheader()
        for record in records:
            writer.writerow({field: _csv_value(record.get(field)) for field in PACKET_FIELDS})


def _csv_value(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def _bullet_pairs(values: list[tuple[str, int]]) -> list[str]:
    return [f"- {name}: {count}" for name, count in values] or ["- None"]


def _bullets(values: list[str]) -> list[str]:
    return [f"- {value}" for value in values] or ["- None"]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))
