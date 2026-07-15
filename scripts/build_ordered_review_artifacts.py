from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from enh3bench.ledger_router import load_jsonl  # noqa: E402


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
    parallel_path.write_text(_parallel_sample(comparison), encoding="utf-8", newline="\n")
    semantic_text = _semantic_closure_sample(packets, args.seed)
    args.semantic_output.parent.mkdir(parents=True, exist_ok=True)
    args.semantic_output.write_text(semantic_text, encoding="utf-8", newline="\n")
    review_semantic_path = args.review_semantic_output or (
        args.output_dir / "stage_b_semantic_closure_sample.md"
    )
    review_semantic_path.parent.mkdir(parents=True, exist_ok=True)
    review_semantic_path.write_text(semantic_text, encoding="utf-8", newline="\n")
    print(f"ordered_source_sample: {ordered_path}")
    print(f"parallel_comparison_sample: {parallel_path}")
    print(f"semantic_closure_sample: {args.semantic_output}")
    print(f"semantic_closure_review_sample: {review_semantic_path}")
    return 0


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
    groups = [
        ("LiNRR methods/protocol", lambda r: r.get("reaction_family") == "LiNRR" and r.get("semantic_section_type") == "methods"),
        ("LiNRR results/performance", lambda r: r.get("reaction_family") == "LiNRR" and r.get("semantic_section_type") == "results" and "performance" in (r.get("evidence_roles") or [])),
        ("eNRR validation", lambda r: r.get("reaction_family") == "eNRR" and "validation" in (r.get("evidence_roles") or [])),
        ("NO3RR quantification", lambda r: r.get("reaction_family") == "NO3RR" and (
            "quantification" in (r.get("evidence_roles") or [])
            or any(term in str(r.get("source_text_excerpt") or "").casefold() for term in (
                "ion chromatography", "colorimetric", "calibration", "ammonia quantification", "nmr",
            ))
        )),
        ("reactor/process", lambda r: bool(set(r.get("evidence_roles") or []) & {"reactor", "process"})),
    ]
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
                f"  - roles: {', '.join(record.get('evidence_roles') or [])}",
                f"  - text: {' '.join(str(record.get('source_text_excerpt') or '').split())[:500].rstrip()}",
            ])
        if not selected:
            lines.append("- No matching records in this run.")
        lines.append("")
    return "\n".join(lines)


def _semantic_closure_sample(packets: list[dict], seed: int = 13) -> str:
    quotas = (
        ("eNRR performance", 15, lambda p: _family(p) == "eNRR" and _performance(p)),
        ("eNRR validation", 15, lambda p: _family(p) == "eNRR" and _validation(p)),
        ("LiNRR performance", 15, lambda p: _family(p) == "LiNRR" and _performance(p)),
        ("LiNRR methods/protocol", 15, lambda p: _family(p) == "LiNRR" and _methods_or_protocol(p)),
        ("NO3RR performance", 15, lambda p: _family(p) == "NO3RR" and _performance(p)),
        ("NO3RR quantification", 15, lambda p: _family(p) == "NO3RR" and _quantification(p)),
        ("NO2RR/NORR", 10, lambda p: _family(p) in {"NO2RR", "NORR"}),
        ("reactor/process", 10, _reactor_or_process),
        ("reference/caption/review table", 10, _low_trust),
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
        f"- Seed: {seed}",
        f"- Samples: {len(selected)}",
        f"- Quotas: `{json.dumps(category_counts, ensure_ascii=False, sort_keys=True)}`",
        "- 结构对齐不代表科学可比性。", "",
    ]
    for number, (category, packet) in enumerate(selected, 1):
        section = packet.get("section_context") or {}
        evidence_items = packet.get("evidence_items") or []
        roles = sorted({str(role) for item in evidence_items for role in item.get("link_roles") or []})
        linked = [
            {
                "span_id": item.get("span_id"),
                "roles": item.get("link_roles") or [],
                "preview": _preview(item.get("text"), 580),
            }
            for item in evidence_items[:4]
        ]
        lines.extend([
            f"## {number}. {category}", "",
            f"- paper_id: `{packet.get('paper_id') or ''}`",
            f"- source_span_id: `{packet.get('target_span_id') or ''}`",
            f"- source_locator: `{packet.get('target_source_locator') or 'unresolved'}`",
            f"- raw_heading: {section.get('raw_heading') or packet.get('target_raw_heading') or '(unheaded)'}",
            f"- direct_section_type: `{packet.get('target_direct_section_type') or 'unknown'}`",
            f"- effective_section_type: `{packet.get('target_effective_section_type') or packet.get('target_section_type') or 'unknown'}`",
            f"- section_type_source: `{packet.get('target_section_type_source') or 'unknown'}`",
            f"- target_claim_type: `{packet.get('target_claim_type') or 'unknown'}`",
            f"- previous_paragraph_preview: {_preview((packet.get('previous_paragraph') or {}).get('text'), 580)}",
            f"- target_paragraph: {_preview((packet.get('target_paragraph') or {}).get('text') or packet.get('target_text'), 780)}",
            f"- next_paragraph_preview: {_preview((packet.get('next_paragraph') or {}).get('text'), 580)}",
            f"- evidence_roles: {', '.join(roles) or 'none'}",
            f"- linked_evidence_previews: `{json.dumps(linked, ensure_ascii=False, sort_keys=True)}`",
            f"- packet_local_context_status: `{packet.get('packet_local_context_status') or ''}`",
            f"- packet_local_missing_types: `{json.dumps(packet.get('packet_local_missing_types') or [], ensure_ascii=False)}`",
            f"- family_gate_coverage: `{json.dumps(packet.get('family_gate_coverage') or {}, ensure_ascii=False, sort_keys=True)}`",
            f"- paper_gate_coverage_missing: `{json.dumps(packet.get('paper_gate_coverage_missing') or [], ensure_ascii=False)}`",
            "- human_section_type_correct:",
            "- human_local_context_sufficient:",
            "- human_link_roles_correct:",
            "- human_notes:", "",
        ])
    return "\n".join(lines)


def _sample_hash(seed: int, category: str, packet: dict) -> str:
    value = f"{seed}\0{category}\0{packet.get('context_packet_id') or packet.get('target_span_id') or ''}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _family(packet: dict) -> str:
    return str(packet.get("target_reaction_family") or "unclear")


def _performance(packet: dict) -> bool:
    if not bool(packet.get("packet_local_context_applicable")):
        return False
    claim_type = str(packet.get("target_claim_type") or "")
    if claim_type:
        return claim_type == "performance_claim"
    return str(packet.get("target_text_class") or "") in {
        "primary_performance", "primary_performance_with_validation"
    }


def _validation(packet: dict) -> bool:
    return (
        str(packet.get("target_claim_type") or "") == "validation_claim"
        or bool((packet.get("evidence_role_index") or {}).get("validation"))
        or "validation" in str(packet.get("target_text_class") or "")
    )


def _methods_or_protocol(packet: dict) -> bool:
    if _low_trust(packet):
        return False
    if str(packet.get("target_effective_section_type") or packet.get("target_section_type") or "") == "methods":
        return True
    if str(packet.get("target_text_class") or "") == "protocol_guideline":
        return True
    if str(packet.get("target_provenance_type") or "") in {"methods", "protocol"}:
        return True
    text = _packet_review_text(packet)
    return any(term in text for term in (
        "experimental method", "experimental section", "was prepared", "were prepared",
        "was measured", "were measured", "protocol", "electrolyte preparation", "materials and methods",
    ))


def _quantification(packet: dict) -> bool:
    gate = (packet.get("family_gate_coverage") or {}).get("ammonia_quantification") or {}
    if gate.get("status") in {
        "observed_in_target", "observed_in_local_context", "observed_in_linked_evidence"
    }:
        return True
    return any(term in _packet_review_text(packet) for term in (
        "ion chromatography", "colorimetric", "calibration", "ammonia quantification", "nmr", "uv-vis",
    ))


def _reactor_or_process(packet: dict) -> bool:
    return bool(packet.get("packet_local_context_applicable")) and (
        str(packet.get("target_claim_type") or "") in {"reactor_claim", "process_claim"}
        or bool(set(role for item in packet.get("evidence_items") or [] for role in item.get("link_roles") or []) & {"reactor", "process"})
    )


def _low_trust(packet: dict) -> bool:
    return (
        str(packet.get("target_provenance_type") or "").casefold()
        in {"reference", "bibliography", "figure_caption", "scheme_caption", "review_table"}
        or str(packet.get("target_text_class") or "").casefold()
        in {"reference_list", "figure_caption", "scheme_caption", "review_table"}
    )


def _packet_review_text(packet: dict) -> str:
    values = [packet.get("target_text") or ""]
    for key in ("previous_paragraph", "target_paragraph", "next_paragraph"):
        values.append((packet.get(key) or {}).get("text") or "")
    values.extend(item.get("text") or "" for item in packet.get("evidence_items") or [])
    return " ".join(str(value) for value in values).casefold()


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
