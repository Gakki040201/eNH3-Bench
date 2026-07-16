from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.ledger_router import load_jsonl  # noqa: E402
from enh3bench.claim_ownership import assess_claim_ownership  # noqa: E402
from enh3bench.claim_typing import (  # noqa: E402
    classify_claim_type,
    has_ammonia_quantification_signal,
    has_gas_purification_trap_signal,
)
from enh3bench.document_scope import assess_document_genre, assess_document_scope  # noqa: E402
from enh3bench.validation_gates import detect_validation_gate  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build trimmed PR1 ordered-source review artifacts.")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--source-ledger-dir", type=Path, default=Path("data") / "source_ledgers")
    parser.add_argument("--output-dir", type=Path, default=Path("review_artifacts") / "pr1")
    parser.add_argument("--context-packets", type=Path)
    parser.add_argument(
        "--semantic-output", type=Path,
        default=Path("data") / "reports" / "stage_b_semantic_closure_sample.md",
    )
    parser.add_argument("--review-semantic-output", type=Path)
    parser.add_argument(
        "--sentinel-output",
        type=Path,
        default=Path("review_artifacts") / "pr1" / "stage_b_semantic_sentinel_sample.md",
    )
    parser.add_argument("--seed", type=int, default=13)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.source_ledger_dir / args.run_name
    sections = load_jsonl(run_dir / "section_ledger.jsonl")
    spans = load_jsonl(run_dir / "span_source_coordinates.jsonl")
    comparison = load_jsonl(run_dir / "parallel_comparison_index.jsonl")
    packet_path = args.context_packets or (
        Path("data") / "context_packets" / args.run_name / "ordered_source_v1" / "context_packets.jsonl"
    )
    packets = load_jsonl(packet_path)
    if not sections or not spans or not comparison or not packets:
        print("Source ledger, ordered context packets, and parallel comparison outputs are required.")
        return 1
    args.output_dir.mkdir(parents=True, exist_ok=True)
    ordered_path = args.output_dir / "ordered_source_sample.md"
    parallel_path = args.output_dir / "parallel_comparison_sample.md"
    ordered_path.write_text(_ordered_sample(sections, spans), encoding="utf-8", newline="\n")
    packets_by_span = {str(packet.get("target_span_id") or ""): packet for packet in packets}
    enriched_comparison = [
        _enrich_comparison_record(
            record,
            packets_by_span.get(str(record.get("source_span_id") or ""), {}),
        )
        for record in comparison
    ]
    parallel_text = _parallel_sample(enriched_comparison)
    parallel_path.write_text(parallel_text, encoding="utf-8", newline="\n")
    semantic_text = _semantic_closure_sample(packets, args.seed)
    args.semantic_output.parent.mkdir(parents=True, exist_ok=True)
    args.semantic_output.write_text(semantic_text, encoding="utf-8", newline="\n")
    review_semantic_path = args.review_semantic_output or (
        args.output_dir / "stage_b_semantic_closure_sample.md"
    )
    review_semantic_path.parent.mkdir(parents=True, exist_ok=True)
    review_semantic_path.write_text(semantic_text, encoding="utf-8", newline="\n")
    sentinel_text, sentinel_passed = _semantic_sentinel_sample(packets)
    args.sentinel_output.parent.mkdir(parents=True, exist_ok=True)
    args.sentinel_output.write_text(sentinel_text, encoding="utf-8", newline="\n")
    diagnostics = _artifact_diagnostics(semantic_text, sentinel_text, enriched_comparison)
    print(f"ordered_source_sample: {ordered_path}")
    print(f"parallel_comparison_sample: {parallel_path}")
    print(f"semantic_closure_sample: {args.semantic_output}")
    print(f"semantic_closure_review_sample: {review_semantic_path}")
    print(f"semantic_sentinel_sample: {args.sentinel_output}")
    print(f"semantic_sentinel_passed: {sentinel_passed}")
    for key, value in diagnostics.items():
        print(f"{key}: {value}")
    diagnostics_passed = (
        diagnostics["sample_count"] == 130
        and diagnostics["sentinel_count"] == 12
        and diagnostics["sentinel_pass_count"] == 12
        and diagnostics["sentinel_fail_count"] == 0
        and all(
            diagnostics[key] == 0
            for key in diagnostics
            if key.endswith("_count")
            and key not in {"sample_count", "sentinel_count", "sentinel_pass_count"}
        )
    )
    print(f"artifact_diagnostics_passed: {diagnostics_passed}")
    return 0 if sentinel_passed and diagnostics_passed else 1


def _ordered_sample(sections: list[dict], spans: list[dict]) -> str:
    sections_by_paper: dict[str, list[dict]] = defaultdict(list)
    spans_by_paper: dict[str, list[dict]] = defaultdict(list)
    for section in sections:
        sections_by_paper[str(section.get("paper_id") or "")].append(section)
    for span in spans:
        spans_by_paper[str(span.get("paper_id") or "")].append(span)
    selected_papers = sorted(spans_by_paper)[:12]
    lines = [
        "# Ordered Source Sample", "",
        "Trimmed review artifact for manual source-order and semantic inspection. It does not include full papers.",
        "结构对齐不代表科学可比性 (structural alignment does not establish scientific comparability).", "",
    ]
    for paper_id in selected_papers:
        lines.extend([f"## {paper_id}", "", "### Document outline", ""])
        for section in sorted(sections_by_paper[paper_id], key=lambda item: int(item.get("section_start_offset") or 0)):
            label = str(section.get("outline_label") or "UNK")
            direct = section.get("direct_section_type") or "unknown"
            effective = section.get("effective_section_type") or section.get("section_type") or "unknown"
            source = _section_type_source(section)
            lines.append(
                f"- `{label}` {section.get('heading_text') or '(unheaded)'} "
                f"[direct={direct}; effective={effective}; source={source}]"
            )
        paper_spans = sorted(spans_by_paper[paper_id], key=lambda item: int(item.get("verified_source_start_offset") or 10**18))
        priority = sorted(paper_spans, key=lambda item: (-float(item.get("candidate_score") or 0), int(item.get("verified_source_start_offset") or 10**18)))
        ranks = {str(item.get("source_span_id")): rank for rank, item in enumerate(priority, 1)}
        lines.extend(["", "### Selected anchors in source order", ""])
        for span in paper_spans[:8]:
            excerpt = " ".join(str(span.get("source_text") or "").split())[:500].rstrip()
            lines.extend([
                f"- `{span.get('source_locator') or 'unresolved'}`",
                f"  - section: `{span.get('section_outline_label') or 'UNK'}` {span.get('section_heading') or '(unheaded)'}",
                f"  - section semantics: direct=`{span.get('direct_section_type') or 'unknown'}`; "
                f"effective=`{span.get('effective_section_type') or span.get('section_type') or 'unknown'}`; "
                f"source=`{_section_type_source(span)}`",
                f"  - paragraph: global {span.get('paragraph_global_index')}, in section {span.get('paragraph_index_in_section')}",
                f"  - candidate priority rank: {ranks.get(str(span.get('source_span_id')))}",
                f"  - target: {excerpt}",
            ])
        lines.append("")
    return "\n".join(lines)


def _parallel_sample(records: list[dict]) -> str:
    groups = _parallel_groups()
    lines = [
        "# Parallel Comparison Sample", "",
        "For manual structural and semantic review only. These alignments do not establish scientific comparability.",
        "结构对齐不代表科学可比性。", "",
    ]
    for name, predicate in groups:
        selected = [record for record in records if predicate(record)][:10]
        lines.extend([f"## {name}", ""])
        for record in selected:
            lines.extend([
                f"- paper: `{record.get('paper_id')}`",
                f"  - locator: `{record.get('source_locator') or 'unresolved'}`",
                f"  - section: `{record.get('section_outline_label') or 'UNK'}` "
                f"direct=`{record.get('direct_section_type') or 'unknown'}`; "
                f"effective=`{record.get('effective_section_type') or 'unknown'}`; "
                f"source=`{record.get('section_type_source') or 'unknown'}`",
                f"  - comparison keys: raw=`{record.get('raw_comparison_key') or ''}`; "
                f"effective=`{record.get('comparison_key') or ''}`",
                f"  - reaction family: legacy=`{record.get('legacy_reaction_family') or record.get('reaction_family') or 'unclear'}`; "
                f"document=`{record.get('document_reaction_family') or 'unclear'}`; "
                f"effective=`{_family(record)}`; source=`{record.get('effective_reaction_family_source') or 'legacy'}`; "
                f"corrected=`{bool(record.get('reaction_family_correction'))}`",
                f"  - semantic claim type: `{record.get('semantic_claim_type') or 'unknown'}`; "
                f"performance result=`{bool(record.get('performance_result_evidence'))}`; "
                f"strength=`{record.get('performance_evidence_strength') or 'none'}`",
                f"  - roles: {', '.join(record.get('evidence_roles') or [])}",
                f"  - text: {' '.join(str(record.get('source_text_excerpt') or '').split())[:500].rstrip()}",
            ])
        if not selected:
            lines.append("- No matching records in this run.")
        lines.append("")
    return "\n".join(lines)


def _parallel_groups() -> list[tuple[str, object]]:
    return [
        ("LiNRR methods/protocol", lambda r: _family(r) == "LiNRR" and r.get("semantic_section_type") == "methods"),
        ("LiNRR results/performance", lambda r: _family(r) == "LiNRR" and r.get("semantic_section_type") == "results" and "performance" in (r.get("evidence_roles") or []) and _parallel_performance_result(r)),
        ("eNRR validation", lambda r: _family(r) == "eNRR" and "validation" in (r.get("evidence_roles") or [])),
        ("NO3RR quantification", lambda r: _family(r) == "NO3RR" and (
            "quantification" in (r.get("evidence_roles") or [])
            or any(term in str(r.get("source_text_excerpt") or "").casefold() for term in (
                "ion chromatography", "colorimetric", "calibration", "ammonia quantification", "nmr",
            ))
        )),
        ("reactor/process", lambda r: bool(set(r.get("evidence_roles") or []) & {"reactor", "process"})),
    ]


def _parallel_performance_result(record: dict) -> bool:
    return bool(
        str(record.get("semantic_claim_type") or "") == "performance_result_claim"
        and record.get("performance_result_evidence")
    )


def _semantic_closure_sample(packets: list[dict], seed: int = 13) -> str:
    requested_gas_trap_quota = 10
    sample_capacity_gas_trap_quota = 7
    available_gas_trap_ids = {
        str(packet.get("context_packet_id") or packet.get("target_span_id") or "")
        for packet in packets
        if _gas_purification_trap(packet)
    }
    available_gas_trap_count = len(available_gas_trap_ids)
    gas_trap_quota = min(
        requested_gas_trap_quota,
        sample_capacity_gas_trap_quota,
        available_gas_trap_count,
    )
    quotas = (
        ("eNRR performance", 15, lambda p: _family(p) == "eNRR" and _performance(p)),
        ("eNRR validation", 15, lambda p: _family(p) == "eNRR" and _validation(p)),
        ("LiNRR performance", 15, lambda p: _family(p) == "LiNRR" and _performance(p)),
        ("NO3RR performance", 15, lambda p: _family(p) == "NO3RR" and _performance(p)),
        ("NO3RR quantification", 15, lambda p: _family(p) == "NO3RR" and _quantification(p)),
        ("NO2RR/NORR primary", 10, lambda p: _family(p) in {"NO2RR", "NORR"} and _primary(p)),
        ("reactor/process", 10, _reactor_or_process),
        ("gas-purification trap (target-only, not quantification)", gas_trap_quota, _gas_purification_trap),
        ("review_or_perspective", 6, _review_or_perspective),
        ("external_cited_claim", 6, _external_cited_claim),
        ("background", 4, _background),
        ("legacy_claim_type_conflict", 4, _legacy_claim_type_conflict),
        ("off_target_reaction_conflict", 4, _off_target_reaction_conflict),
        ("quantification_false_negative_candidates", 4, _quantification_false_negative_candidate),
    )
    selected: list[tuple[str, dict]] = []
    used: set[str] = set()
    category_counts: dict[str, int] = {}
    for category, quota, predicate in quotas:
        candidates = [
            packet for packet in packets
            if predicate(packet) and str(packet.get("context_packet_id") or "") not in used
        ]
        candidates.sort(key=lambda packet: _sample_hash(seed, category, packet))
        if len(candidates) < quota:
            raise ValueError(
                f"semantic sample quota unavailable for {category}: required {quota}, found {len(candidates)}"
            )
        for packet in candidates[:quota]:
            selected.append((category, packet))
            used.add(str(packet.get("context_packet_id") or ""))
        category_counts[category] = quota

    lines = [
        "# Stage B Semantic Closure Review Sample", "",
        "This file is a stratified review artifact generated with seed 13.",
        "It is intended for structural and semantic review only.", "",
        "It does not establish:",
        "- global model precision;",
        "- paper-level validation;",
        "- scientific comparability;",
        "- paper admissibility.", "",
        "Primary applicability requires primary-research document genre, target-document span scope,",
        "target-author ownership, admissible provenance, an eligible result-bearing semantic type,",
        "a safe effective reaction family, and no local off-target conflict.",
        "Gate coverage is shown separately for any source and primary-admissible evidence.",
        "Gas purification or trapping is not ammonia quantification without analytical measurement semantics.", "",
        f"- Seed: {seed}",
        f"- Samples: {len(selected)}",
        f"- Quotas: `{json.dumps(category_counts, ensure_ascii=False, sort_keys=True)}`",
        f"- Requested gas-trap quota: {requested_gas_trap_quota}",
        f"- 130-sample capacity for gas-trap stratum: {sample_capacity_gas_trap_quota}",
        f"- Unique target-level gas-trap records available: {available_gas_trap_count}",
        f"- Gas-trap records sampled: {gas_trap_quota}",
        "- No duplicate or synthetic gas-trap samples were added.",
        "- 结构对齐不代表科学可比性。", "",
    ]
    for number, (category, packet) in enumerate(selected, 1):
        stratum_type = "primary" if category in {
            "eNRR performance", "eNRR validation", "LiNRR performance", "NO3RR performance",
            "NO3RR quantification", "NO2RR/NORR primary", "reactor/process",
        } else "secondary"
        section = packet.get("section_context") or {}
        evidence_items = packet.get("evidence_items") or []
        roles = sorted({str(role) for item in evidence_items for role in item.get("link_roles") or []})
        linked = [
            {
                "span_id": item.get("span_id"),
                "roles": item.get("link_roles") or [],
                "primary_admissible_gate_source": bool(item.get("primary_admissible_gate_source")),
                "document_genre": item.get("document_genre") or "unknown",
                "span_claim_scope": item.get("span_claim_scope") or item.get("document_scope") or "unknown",
                "document_scope": item.get("document_scope") or "unknown",
                "claim_ownership": item.get("claim_ownership") or "unknown",
                "preview": _preview(item.get("text"), 580),
            }
            for item in evidence_items[:4]
        ]
        lines.extend([
            f"## {number}. {category}", "",
            f"- context_packet_id: `{packet.get('context_packet_id') or ''}`",
            f"- sample_stratum_type: `{stratum_type}`",
            f"- secondary_stratum_reason: `{category if stratum_type == 'secondary' else 'not_applicable'}`",
            f"- paper_id: `{packet.get('paper_id') or ''}`",
            f"- source_span_id: `{packet.get('target_span_id') or ''}`",
            f"- source_locator: `{packet.get('target_source_locator') or 'unresolved'}`",
            f"- raw_heading: {section.get('raw_heading') or packet.get('target_raw_heading') or '(unheaded)'}",
            f"- direct_section_type: `{packet.get('target_direct_section_type') or 'unknown'}`",
            f"- effective_section_type: `{packet.get('target_effective_section_type') or packet.get('target_section_type') or 'unknown'}`",
            f"- section_type_source: `{packet.get('target_section_type_source') or 'unknown'}`",
            f"- target_claim_type: `{packet.get('target_claim_type') or 'unknown'}`",
            f"- legacy_claim_type: `{packet.get('legacy_claim_type') or packet.get('target_claim_type') or 'unknown'}`",
            f"- semantic_claim_type: `{packet.get('semantic_claim_type') or 'unknown'}`",
            f"- semantic_claim_type_confidence: `{packet.get('semantic_claim_type_confidence') or 'unknown'}`",
            f"- semantic_claim_type_conflict: `{bool(packet.get('semantic_claim_type_conflict'))}`",
            f"- performance_evidence_strength: `{packet.get('performance_evidence_strength') or 'none'}`",
            f"- performance_evidence_signals: `{json.dumps(packet.get('performance_evidence_signals') or [], ensure_ascii=False)}`",
            f"- performance_result_evidence: `{bool(packet.get('performance_result_evidence'))}`",
            f"- quantitative_performance_evidence: `{bool(packet.get('quantitative_performance_evidence'))}`",
            f"- document_genre: `{packet.get('document_genre') or 'unknown'}`",
            f"- legacy_reaction_family: `{packet.get('legacy_reaction_family') or packet.get('target_reaction_family') or 'unclear'}`",
            f"- document_reaction_family: `{packet.get('document_reaction_family') or 'unclear'}`",
            f"- document_reaction_family_confidence: `{packet.get('document_reaction_family_confidence') or 'unclear'}`",
            f"- effective_reaction_family: `{_family(packet)}`",
            f"- effective_reaction_family_source: `{packet.get('effective_reaction_family_source') or 'legacy'}`",
            f"- reaction_family_correction: `{bool(packet.get('reaction_family_correction'))}`",
            f"- document_target_reaction_family_conflict: `{bool(packet.get('document_target_reaction_family_conflict'))}`",
            f"- span_claim_scope: `{packet.get('span_claim_scope') or packet.get('document_scope') or 'unknown'}`",
            f"- document_scope: `{packet.get('document_scope') or 'unknown'}`",
            f"- claim_ownership: `{packet.get('claim_ownership') or 'unknown'}`",
            f"- primary_semantic_eligibility: `{bool(packet.get('primary_semantic_eligibility'))}`",
            f"- hard_gate_failures: `{json.dumps(packet.get('primary_applicability_hard_gate_failures') or [], ensure_ascii=False)}`",
            f"- primary_applicability_hard_gate_failures: `{json.dumps(packet.get('primary_applicability_hard_gate_failures') or [], ensure_ascii=False)}`",
            f"- ammonia_quantification_signal: `{bool(packet.get('ammonia_quantification_signal'))}`",
            f"- gas_purification_trap_signal: `{bool(packet.get('gas_purification_trap_signal'))}`",
            f"- mass_spectrometry_quantification_signal: `{bool(packet.get('mass_spectrometry_quantification_signal'))}`",
            f"- enzymatic_quantification_signal: `{bool(packet.get('enzymatic_quantification_signal'))}`",
            f"- previous_paragraph_preview: {_preview((packet.get('previous_paragraph') or {}).get('text'), 580)}",
            f"- target_paragraph: {_preview((packet.get('target_paragraph') or {}).get('text') or packet.get('target_text'), 780)}",
            f"- next_paragraph_preview: {_preview((packet.get('next_paragraph') or {}).get('text'), 580)}",
            f"- evidence_roles: {', '.join(roles) or 'none'}",
            f"- linked_evidence_previews: `{json.dumps(linked, ensure_ascii=False, sort_keys=True)}`",
            f"- packet_local_context_status: `{packet.get('packet_local_context_status') or ''}`",
            f"- packet_local_missing_types: `{json.dumps(packet.get('packet_local_missing_types') or [], ensure_ascii=False)}`",
            f"- family_gate_coverage: `{json.dumps(packet.get('family_gate_coverage') or {}, ensure_ascii=False, sort_keys=True)}`",
            f"- family_gate_coverage_any_source: `{json.dumps(packet.get('family_gate_coverage_any_source') or packet.get('family_gate_coverage') or {}, ensure_ascii=False, sort_keys=True)}`",
            f"- family_gate_coverage_primary_admissible: `{json.dumps(packet.get('family_gate_coverage_primary_admissible') or {}, ensure_ascii=False, sort_keys=True)}`",
            f"- paper_gate_coverage_missing: `{json.dumps(packet.get('paper_gate_coverage_missing') or [], ensure_ascii=False)}`",
            f"- paper_gate_coverage_primary_admissible_missing: `{json.dumps(packet.get('paper_gate_coverage_primary_admissible_missing') or [], ensure_ascii=False)}`",
            f"- local_reaction_family_conflict_any_source: `{bool(packet.get('local_reaction_family_conflict_any_source'))}`",
            f"- local_reaction_family_conflict_primary_admissible: `{bool(packet.get('local_reaction_family_conflict_primary_admissible'))}`",
            f"- local_off_target_reaction_conflict: `{bool(packet.get('local_off_target_reaction_conflict'))}`",
            f"- off_target_reaction_conflict: `{bool(packet.get('local_off_target_reaction_conflict'))}`",
            "- human_section_type_correct:",
            "- human_document_genre_correct:",
            "- human_span_claim_scope_correct:",
            "- human_document_scope_correct:",
            "- human_claim_ownership_correct:",
            "- human_claim_type_correct:",
            "- human_effective_reaction_family_correct:",
            "- human_performance_result_evidence_correct:",
            "- human_local_context_sufficient:",
            "- human_link_roles_correct:",
            "- human_gate_source_eligibility_correct:",
            "- human_quantification_vs_trap_correct:",
            "- human_notes:", "",
        ])
    return "\n".join(lines)


def _sample_hash(seed: int, category: str, packet: dict) -> str:
    value = f"{seed}\0{category}\0{packet.get('context_packet_id') or packet.get('target_span_id') or ''}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _family(packet: dict) -> str:
    return str(
        packet.get("effective_reaction_family")
        or packet.get("reaction_family")
        or packet.get("target_reaction_family")
        or "unclear"
    )


def _performance(packet: dict) -> bool:
    return bool(
        _primary(packet)
        and str(packet.get("semantic_claim_type") or "") == "performance_result_claim"
        and bool(packet.get("performance_result_evidence"))
    )


def _validation(packet: dict) -> bool:
    return _primary(packet) and str(packet.get("semantic_claim_type") or "") == "validation_claim"


def _quantification(packet: dict) -> bool:
    return bool(
        _primary(packet)
        and packet.get("ammonia_quantification_signal")
        and str(packet.get("semantic_claim_type") or "") == "ammonia_quantification_claim"
    )


def _gas_purification_trap(packet: dict) -> bool:
    target_text = str(packet.get("target_text") or "")
    return bool(
        packet.get("gas_purification_trap_signal")
        and not packet.get("ammonia_quantification_signal")
        and re.search(r"\b(?:ammonia|ammonium|nh\s*3|nh\s*4)\b", target_text, re.IGNORECASE)
        and str(packet.get("semantic_claim_type") or "") == "gas_purification_or_capture_claim"
        and str(packet.get("document_genre") or "") == "primary_research"
        and str(packet.get("span_claim_scope") or packet.get("document_scope") or "") == "target_document"
        and str(packet.get("claim_ownership") or "") == "target_authors"
        and _family(packet) in {"eNRR", "LiNRR", "NO2RR", "NO3RR", "NORR", "mixed"}
        and not re.search(
            r"\b(?:did\s+not|does\s+not|do\s+not|without|no)\b.{0,100}"
            r"\b(?:acid\s+|base\s+|downstream\s+)?trap\b",
            target_text,
            re.IGNORECASE,
        )
    )


def _reactor_or_process(packet: dict) -> bool:
    return _primary(packet) and str(packet.get("semantic_claim_type") or "") in {
        "reactor_claim", "process_claim",
    }


def _primary(packet: dict) -> bool:
    return bool(packet.get("primary_semantic_eligibility"))


def _review_or_perspective(packet: dict) -> bool:
    return str(packet.get("document_genre") or "") in {"review", "perspective"}


def _external_cited_claim(packet: dict) -> bool:
    return (
        str(packet.get("span_claim_scope") or packet.get("document_scope") or "") == "external_or_cited_work"
        or str(packet.get("claim_ownership") or "") == "external_or_cited_authors"
    )


def _background(packet: dict) -> bool:
    return str(packet.get("span_claim_scope") or packet.get("document_scope") or "") == "background_or_review"


def _legacy_claim_type_conflict(packet: dict) -> bool:
    return bool(packet.get("semantic_claim_type_conflict"))


def _off_target_reaction_conflict(packet: dict) -> bool:
    return bool(packet.get("local_off_target_reaction_conflict"))


def _quantification_false_negative_candidate(packet: dict) -> bool:
    if bool(packet.get("ammonia_quantification_signal")):
        return False
    text = str(packet.get("target_text") or "").casefold()
    analyte = any(term in text for term in ("ammonia", "nh3", "nh 3", "nh4", "nh 4", "ammonium"))
    possible_method = any(term in text for term in (
        "mass spectrometry", "gc-ms", "gas chromatography-mass spectrometry", "enzymatic",
        "nadh", "selective electrode", "titration", "conductivity", "calibration", "assay",
        "measured", "quantified", "determined",
    ))
    return analyte and possible_method


def _enrich_comparison_record(record: dict, packet: dict) -> dict:
    """Apply packet-level effective family semantics to a review-only comparison row."""

    enriched = {
        **record,
        **_comparison_packet_fields(packet),
    }
    family = _family(enriched)
    roles = enriched.get("evidence_roles") or []
    primary_role = str(roles[0]) if roles else "context_hint"
    semantic_section = str(enriched.get("semantic_section_type") or "unknown")
    enriched["reaction_family"] = family
    enriched["effective_reaction_family"] = family
    enriched["comparison_key"] = f"{family}|{semantic_section}|{primary_role}"
    return enriched


def _comparison_packet_fields(packet: dict) -> dict:
    if not packet:
        return {}
    return {
        "legacy_reaction_family": packet.get("legacy_reaction_family") or packet.get("target_reaction_family"),
        "document_reaction_family": packet.get("document_reaction_family") or "unclear",
        "effective_reaction_family": packet.get("effective_reaction_family") or packet.get("target_reaction_family"),
        "effective_reaction_family_source": packet.get("effective_reaction_family_source") or "legacy",
        "reaction_family_correction": bool(packet.get("reaction_family_correction")),
        "document_target_reaction_family_conflict": bool(
            packet.get("document_target_reaction_family_conflict")
        ),
        "semantic_claim_type": packet.get("semantic_claim_type") or "unknown",
        "performance_result_evidence": bool(packet.get("performance_result_evidence")),
        "performance_evidence_strength": packet.get("performance_evidence_strength") or "none",
    }


def _artifact_diagnostics(
    semantic_text: str,
    sentinel_text: str,
    comparison_records: list[dict],
) -> dict[str, int]:
    """Validate the generated review artifacts, not just their source predicates."""

    sample_sections = _numbered_markdown_sections(semantic_text)
    expected_families = {
        "eNRR performance": {"eNRR"},
        "eNRR validation": {"eNRR"},
        "LiNRR performance": {"LiNRR"},
        "NO3RR performance": {"NO3RR"},
        "NO3RR quantification": {"NO3RR"},
        "NO2RR/NORR primary": {"NO2RR", "NORR"},
    }
    family_sections = [
        (category, block, expected_families[category])
        for category, block in sample_sections
        if category in expected_families
    ]
    performance_sections = [
        block for category, block in sample_sections
        if category in {"eNRR performance", "LiNRR performance", "NO3RR performance"}
    ]
    packet_ids = [_markdown_field(block, "context_packet_id") for _, block in sample_sections]

    group_expectations = {
        "LiNRR methods/protocol": {"LiNRR"},
        "LiNRR results/performance": {"LiNRR"},
        "eNRR validation": {"eNRR"},
        "NO3RR quantification": {"NO3RR"},
    }
    selected_groups = {
        name: [record for record in comparison_records if predicate(record)][:10]
        for name, predicate in _parallel_groups()
    }
    family_comparison = [
        (name, record, group_expectations[name])
        for name, records in selected_groups.items()
        if name in group_expectations
        for record in records
    ]
    parallel_unclear = sum(1 for _, record, _ in family_comparison if _family(record) == "unclear")
    parallel_mismatch = sum(
        1 for _, record, expected in family_comparison if _family(record) not in expected
    )
    result_group = selected_groups.get("LiNRR results/performance", [])
    sentinel_sections = _numbered_markdown_sections(sentinel_text)
    sentinel_passes = sum(
        1 for _, block in sentinel_sections if _markdown_field(block, "pass") == "True"
    )

    return {
        "sample_count": len(sample_sections),
        "duplicate_packet_id_count": len(packet_ids) - len(set(packet_ids)),
        "filled_human_review_field_count": len(re.findall(
            r"(?m)^- human_[^:\n]+:[ \t]*\S+", semantic_text
        )),
        "absolute_local_path_count": len(re.findall(
            r"(?:[A-Za-z]:[\\/](?![\\/])|(?i:file://)|/(?:home|Users|tmp)/)", semantic_text
        )),
        "full_document_embedding_count": len(re.findall(
            r"(?im)^- (?:full_document_text|full_body_text|document_body_text):", semantic_text
        )),
        "family_specific_primary_with_unclear_effective_family_count": sum(
            1 for _, block, _ in family_sections
            if _markdown_field(block, "effective_reaction_family") == "unclear"
        ),
        "family_specific_primary_with_mismatched_effective_family_count": sum(
            1 for _, block, expected in family_sections
            if _markdown_field(block, "effective_reaction_family") not in expected
        ),
        "family_specific_parallel_comparison_with_unclear_family_count": parallel_unclear,
        "performance_context_primary_performance_strata_count": sum(
            1 for block in performance_sections
            if _markdown_field(block, "semantic_claim_type") == "performance_context_claim"
        ),
        "primary_performance_without_result_evidence_count": sum(
            1 for block in performance_sections
            if _markdown_field(block, "semantic_claim_type") != "performance_result_claim"
            or _markdown_field(block, "performance_result_evidence") != "True"
        ),
        "P0090_eNRR_sample_count": sum(
            1 for category, block in sample_sections
            if category.startswith("eNRR") and _markdown_field(block, "paper_id").startswith("P0090")
        ),
        "sentinel_count": len(sentinel_sections),
        "sentinel_pass_count": sentinel_passes,
        "sentinel_fail_count": len(sentinel_sections) - sentinel_passes,
        "sentinel_missing_case_id_count": sum(
            1 for _, block in sentinel_sections if not _markdown_field(block, "case_id")
        ),
        "parallel_family_mismatch_count": parallel_mismatch,
        "parallel_unclear_in_family_specific_group_count": parallel_unclear,
        "parallel_performance_context_in_result_group_count": sum(
            1 for record in result_group if not _parallel_performance_result(record)
        ),
        "P0090_eNRR_parallel_comparison_count": sum(
            1 for name, records in selected_groups.items()
            if name.startswith("eNRR")
            for record in records
            if str(record.get("paper_id") or "").startswith("P0090")
        ),
    }


def _numbered_markdown_sections(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^## \d+\. ([^\n]+)$", text))
    return [
        (
            match.group(1),
            text[match.start(): matches[index + 1].start()]
            if index + 1 < len(matches)
            else text[match.start():],
        )
        for index, match in enumerate(matches)
    ]


def _markdown_field(block: str, field: str) -> str:
    match = re.search(rf"(?m)^- {re.escape(field)}:\s*`?([^`\n]*)`?\s*$", block)
    return match.group(1).strip() if match else ""


def _semantic_sentinel_sample(packets: list[dict]) -> tuple[str, bool]:
    """Build deterministic, human-readable semantic safety sentinels."""

    p0090_packets = [
        packet for packet in packets
        if str(packet.get("paper_id") or "").startswith("P0090")
    ]
    p0090_primary = [packet for packet in p0090_packets if bool(packet.get("primary_semantic_eligibility"))]
    p0090_document_families = sorted({
        str(packet.get("document_reaction_family") or "unclear") for packet in p0090_packets
    })
    p0090_enrr_primary_ids = [
        str(packet.get("target_span_id") or "")
        for packet in p0090_primary
        if str(packet.get("effective_reaction_family") or "unclear") == "eNRR"
    ]
    p0090_actual = {
        "packet_count": len(p0090_packets),
        "primary_eligible_count": len(p0090_primary),
        "document_families": p0090_document_families,
        "primary_effective_eNRR_span_ids": p0090_enrr_primary_ids,
    }
    fe_material = classify_claim_type({"source_text": "FeS catalyst was synthesized.", "claim_type": "performance_claim"})
    high_yield = classify_claim_type({
        "source_text": "The catalyst showed high ammonia yield.",
        "claim_type": "performance_claim",
    })
    explicit_15n = detect_validation_gate("isotope_15N", "15N2 isotope validation was performed.")
    generic_isotope = detect_validation_gate("isotope_15N", "An isotope-labelled material was analyzed.")
    no_gas = detect_validation_gate("NO_source_defined", "no gas was supplied")
    ten_percent_no = detect_validation_gate("NO_source_defined", "10% NO in Ar was supplied")
    no_balance = detect_validation_gate("NOx_balance", "no mass balance was reported")
    nadh_text = "NH4+ concentration was measured by an NADH consumption assay."
    trap_text = "The N2 feed passed through an acid trap to remove adventitious NH3."
    genre = assess_document_genre({
        "paper_title": "A critical review of electrochemical ammonia synthesis",
        "article_type": "Article",
    })
    cited_record = {
        "source_text": "Yang et al. [12] synthesized the catalyst.",
        "effective_section_type": "results",
        "provenance_type": "body",
        "text_class": "primary_performance",
    }
    cited_scope = assess_document_scope(cited_record)
    cited_owner = assess_claim_ownership(cited_record, cited_scope)

    cases = [
        _sentinel_case(
            "P0090 nitrate family correction",
            {"paper_id": "P0090"},
            {"document_families": ["NO3RR"], "primary_effective_eNRR_span_ids": []},
            p0090_actual,
            bool(
                p0090_packets
                and p0090_document_families == ["NO3RR"]
                and not p0090_enrr_primary_ids
            ),
        ),
        _sentinel_case(
            "FeS is not FE performance",
            "FeS catalyst was synthesized.",
            {"semantic_claim_type_not": "performance_result_claim"},
            {"semantic_claim_type": fe_material["semantic_claim_type"]},
            fe_material["semantic_claim_type"] != "performance_result_claim",
        ),
        _sentinel_case(
            "Qualitative high yield is context",
            "The catalyst showed high ammonia yield.",
            {"semantic_claim_type": "performance_context_claim"},
            {"semantic_claim_type": high_yield["semantic_claim_type"]},
            high_yield["semantic_claim_type"] == "performance_context_claim",
        ),
        _sentinel_case("Explicit 15N is positive", "15N2 validation", {"satisfied": True}, explicit_15n, explicit_15n["satisfied"]),
        _sentinel_case("Generic isotope is not 15N", "isotope-labelled material", {"satisfied": False}, generic_isotope, not generic_isotope["satisfied"]),
        _sentinel_case("English no gas is not NO feed", "no gas was supplied", {"satisfied": False}, no_gas, not no_gas["satisfied"]),
        _sentinel_case("Uppercase NO concentration is a source", "10% NO in Ar", {"satisfied": True}, ten_percent_no, ten_percent_no["satisfied"]),
        _sentinel_case("Negated mass balance is not coverage", "no mass balance was reported", {"satisfied": False}, no_balance, not no_balance["satisfied"]),
        _sentinel_case(
            "NADH NH4 assay is quantification",
            nadh_text,
            {"ammonia_quantification": True},
            {"ammonia_quantification": has_ammonia_quantification_signal(nadh_text)},
            has_ammonia_quantification_signal(nadh_text),
        ),
        _sentinel_case(
            "Gas purification trap is not quantification",
            trap_text,
            {"trap": True, "ammonia_quantification": False},
            {
                "trap": has_gas_purification_trap_signal(trap_text),
                "ammonia_quantification": has_ammonia_quantification_signal(trap_text),
            },
            has_gas_purification_trap_signal(trap_text) and not has_ammonia_quantification_signal(trap_text),
        ),
        _sentinel_case(
            "Review title overrides generic Article type",
            {"title": "A critical review...", "article_type": "Article"},
            {"document_genre": "review"},
            {"document_genre": genre["document_genre"]},
            genre["document_genre"] == "review",
        ),
        _sentinel_case(
            "Bracketed cited-author action is external",
            cited_record["source_text"],
            {"span_claim_scope": "external_or_cited_work", "claim_ownership": "external_or_cited_authors"},
            {
                "span_claim_scope": cited_scope["span_claim_scope"],
                "claim_ownership": cited_owner["claim_ownership"],
            },
            cited_scope["span_claim_scope"] == "external_or_cited_work"
            and cited_owner["claim_ownership"] == "external_or_cited_authors",
        ),
    ]
    passed = all(case["passed"] for case in cases)
    lines = [
        "# Stage B Semantic Sentinel Sample",
        "",
        "Deterministic safety sentinels for document reaction family, result-bearing performance,",
        "validation-gate regex safety, document genre, and cited-claim ownership.",
        "",
        f"- Cases: {len(cases)}",
        f"- Passed: {sum(case['passed'] for case in cases)}",
        f"- Overall pass: `{passed}`",
        "",
    ]
    for index, case in enumerate(cases, 1):
        lines.extend([
            f"## {index}. {case['name']}",
            "",
            f"- case_id: `SB_SENTINEL_{index:02d}`",
            f"- input: `{json.dumps(case['input'], ensure_ascii=False, sort_keys=True)}`",
            f"- expected: `{json.dumps(case['expected'], ensure_ascii=False, sort_keys=True)}`",
            f"- actual: `{json.dumps(case['actual'], ensure_ascii=False, sort_keys=True)}`",
            f"- pass: `{case['passed']}`",
            "",
        ])
    return "\n".join(lines), passed


def _sentinel_case(name: str, input_value: object, expected: object, actual: object, passed: bool) -> dict:
    return {
        "name": name,
        "input": input_value,
        "expected": expected,
        "actual": actual,
        "passed": bool(passed),
    }


def _section_type_source(record: dict) -> str:
    direct = str(record.get("direct_section_type") or "unknown")
    effective = str(record.get("effective_section_type") or record.get("section_type") or "unknown")
    if direct != "unknown":
        return "direct"
    if effective != "unknown" and (record.get("inherited_section_type") or record.get("inherited_from_section_uid")):
        return "inherited"
    return "unknown"


def _preview(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return "(none)"
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


if __name__ == "__main__":
    raise SystemExit(main())
