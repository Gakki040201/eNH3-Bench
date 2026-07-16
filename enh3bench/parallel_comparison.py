"""Structural alignment index for parallel human review, not scientific equivalence."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from enh3bench.evidence_linking import classify_link_type
from enh3bench.reaction_profiles import assess_effective_reaction_family, normalize_reaction_family
from enh3bench.source_ledger import sort_spans_by_source_order


def build_parallel_comparison_index(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build deterministic structural coordinates without asserting scientific comparability."""

    comparison: list[dict[str, Any]] = []
    for record in sort_spans_by_source_order(records):
        position = _position(record.get("document_relative_position"))
        roles = _evidence_roles(record)
        direct_section = str(record.get("direct_section_type") or record.get("section_type") or "unknown").casefold()
        effective_section = str(
            record.get("effective_section_type") or record.get("section_type") or "unknown"
        ).casefold()
        semantic_section = _semantic_section_type(effective_section)
        raw_semantic_section = _semantic_section_type(direct_section)
        section_source = _section_type_source(record, direct_section, effective_section)
        family_assessment = assess_effective_reaction_family(record)
        legacy_family = normalize_reaction_family(str(record.get("reaction_family") or "unclear"))
        family = normalize_reaction_family(str(
            record.get("effective_reaction_family")
            or family_assessment.get("effective_reaction_family")
            or legacy_family
        ))
        primary_role = roles[0] if roles else "context_hint"
        comparison.append({
            "paper_id": str(record.get("paper_id") or ""),
            "source_span_id": str(record.get("source_span_id") or record.get("legacy_span_id") or ""),
            "source_locator": record.get("source_locator"),
            "reaction_family": family,
            "legacy_reaction_family": legacy_family,
            "effective_reaction_family": family,
            "effective_reaction_family_source": str(
                record.get("effective_reaction_family_source")
                or family_assessment.get("effective_reaction_family_source")
                or "existing_reaction_family"
            ),
            "reaction_family_correction": bool(
                record.get("reaction_family_correction")
                if "reaction_family_correction" in record
                else family_assessment.get("reaction_family_correction")
            ),
            "direct_section_type": direct_section,
            "effective_section_type": effective_section,
            "section_type_source": section_source,
            "semantic_section_type": semantic_section,
            "evidence_roles": roles,
            "section_outline_label": str(record.get("section_outline_label") or ""),
            "paragraph_global_index": record.get("paragraph_global_index"),
            "document_relative_position": position,
            "section_relative_position": record.get("section_relative_position"),
            "normalized_position_bin": _position_bin(position),
            "comparison_key": f"{family}|{semantic_section}|{primary_role}",
            "raw_comparison_key": f"{family}|{raw_semantic_section}|{primary_role}",
            "scientific_comparability_asserted": False,
            "source_text_excerpt": str(record.get("source_text") or record.get("text") or "")[:500],
        })
    return comparison


def summarize_parallel_comparison(records: list[dict[str, Any]], run_name: str) -> dict[str, Any]:
    keys = Counter(str(record.get("comparison_key") or "") for record in records)
    source_distribution = Counter(str(record.get("section_type_source") or "unknown") for record in records)
    keys_by_source = {
        source: {str(record.get("comparison_key") or "") for record in records if record.get("section_type_source") == source}
        for source in ("direct", "inherited", "unknown")
    }
    return {
        "run_name": run_name,
        "record_count": len(records),
        "comparison_group_count": len(keys),
        "comparison_key_distribution": dict(sorted(keys.items())),
        "comparison_groups_using_direct_section": len(keys_by_source["direct"]),
        "comparison_groups_using_inherited_section": len(keys_by_source["inherited"]),
        "comparison_groups_with_unknown_section": len(keys_by_source["unknown"]),
        "section_type_source_distribution": dict(sorted(source_distribution.items())),
        "position_bin_distribution": dict(sorted(Counter(str(record.get("normalized_position_bin") or "") for record in records).items())),
        "scientific_comparability_asserted_count": sum(bool(record.get("scientific_comparability_asserted")) for record in records),
    }


def export_parallel_comparison_index(
    records: list[dict[str, Any]], run_name: str, output_dir: str | Path = "data/source_ledgers"
) -> dict[str, Any]:
    run_dir = Path(output_dir)
    if run_dir.name != run_name:
        run_dir = run_dir / run_name
    index_path = run_dir / "parallel_comparison_index.jsonl"
    summary_path = run_dir / "parallel_comparison_summary.json"
    summary = summarize_parallel_comparison(records, run_name)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"index": str(index_path), "summary": str(summary_path), "summary_data": summary}


def _evidence_roles(record: dict[str, Any]) -> list[str]:
    existing = record.get("evidence_roles") or record.get("link_roles")
    if isinstance(existing, list) and existing:
        return list(dict.fromkeys(str(item) for item in existing if str(item)))
    return [classify_link_type(record)]


def _semantic_section_type(value: Any) -> str:
    section_type = str(value or "unknown").casefold()
    if section_type == "results_and_discussion":
        return "results"
    return section_type


def _section_type_source(record: dict[str, Any], direct: str, effective: str) -> str:
    if direct != "unknown":
        return "direct"
    if effective != "unknown" and (record.get("inherited_section_type") or record.get("inherited_from_section_uid")):
        return "inherited"
    return "unknown"


def _position(value: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 8)
    except (TypeError, ValueError):
        return 0.0


def _position_bin(position: float) -> str:
    lower_index = min(9, int(position * 10))
    lower = lower_index / 10
    upper = (lower_index + 1) / 10
    return f"{lower:.1f}-{upper:.1f}"
