"""Recall-oriented candidate generation from new clean-room source nodes."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any, Iterable

from enh3bench.cleanroom_schema import common_fields, make_cleanroom_span_id


_TRIGGERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("quantification_signal", re.compile(
        r"\b(?:quantif(?:y|ied|ication)|measur(?:e|ed|ement)|assay|indophenol|nessler|"
        r"ion chromatograph|nmr|nuclear magnetic resonance|mass spectrom|colorimetric)\b",
        re.IGNORECASE,
    )),
    ("validation_signal", re.compile(
        r"\b(?:15\s*N|nitrogen[- ]15|isotop|blank control|contamination|impurit|NOx|"
        r"mass balance|nitrogen balance|feed source|nitrogen source)\b",
        re.IGNORECASE,
    )),
    ("performance_signal", re.compile(
        r"\b(?:faradaic efficiency|\bFE\b|yield rate|ammonia yield|NH\s*3\s+yield|"
        r"current density|selectivity|conversion|production rate)\b",
        re.IGNORECASE,
    )),
    ("reactor_signal", re.compile(
        r"\b(?:reactor|electroly[sz]er|flow cell|membrane electrode assembly|\bMEA\b|"
        r"gas diffusion electrode|zero[- ]gap|cell configuration)\b",
        re.IGNORECASE,
    )),
    ("process_signal", re.compile(
        r"\b(?:process|plant[- ]level|scale[- ]up|techno[- ]economic|life cycle|separation|"
        r"downstream|continuous operation|single[- ]pass)\b",
        re.IGNORECASE,
    )),
    ("energy_boundary_signal", re.compile(
        r"\b(?:energy efficiency|energy consumption|electricity|cell voltage|overpotential|"
        r"energy intensity|kwh)\b",
        re.IGNORECASE,
    )),
    ("product_state_signal", re.compile(
        r"\b(?:aqueous ammonia|ammonium|NH\s*4|product concentration|product state|"
        r"ammonia solution|anhydrous ammonia)\b",
        re.IGNORECASE,
    )),
    ("control_signal", re.compile(
        r"\b(?:control experiment|control test|argon blank|Ar blank|N2[- ]free|"
        r"background ammonia|background NH\s*3)\b",
        re.IGNORECASE,
    )),
    ("general_ammonia_context", re.compile(r"\b(?:ammonia|NH\s*3|nitrogen reduction|NRR)\b", re.IGNORECASE)),
)

_KIND_PRIORITY = {kind: index for index, (kind, _pattern) in enumerate(_TRIGGERS)}


def generate_candidate_spans(
    source_nodes: Iterable[dict[str, Any]],
    documents_by_id: dict[str, dict[str, Any]],
    *,
    run_name: str,
    profile: str,
    max_candidate_characters: int = 3000,
) -> list[dict[str, Any]]:
    """Generate deterministic exact anchors without consulting any legacy runtime output."""

    if max_candidate_characters <= 0:
        raise ValueError("max_candidate_characters must be positive")
    candidates: list[dict[str, Any]] = []
    seen_ranges: set[tuple[str, int, int]] = set()
    for node in sorted(source_nodes, key=_node_sort_key):
        text = str(node.get("source_text") or "")
        if not text.strip():
            continue
        document_id = str(node["document_id"])
        document = documents_by_id[document_id]
        for local_start, local_end, candidate_text, method in _candidate_windows(text, max_candidate_characters):
            trigger_signals = [kind for kind, pattern in _TRIGGERS if pattern.search(candidate_text)]
            if not trigger_signals:
                continue
            start = int(node["source_start_offset"]) + local_start
            end = int(node["source_start_offset"]) + local_end
            exact_key = (document_id, start, end)
            if exact_key in seen_ranges:
                continue
            seen_ranges.add(exact_key)
            kind = min(trigger_signals, key=lambda value: _KIND_PRIORITY[value])
            score = round(min(1.0, 0.35 + 0.1 * len(trigger_signals)), 3)
            span_id = make_cleanroom_span_id(
                str(document["document_body_sha256"]), start, end, kind
            )
            record = {
                **common_fields(run_name, "candidates", profile),
                "cleanroom_span_id": span_id,
                "legacy_source_span_id": "",
                "source_node_id": node["source_node_id"],
                "paper_id": node["paper_id"],
                "document_id": document_id,
                "candidate_kind": kind,
                "source_start_offset": start,
                "source_end_offset": end,
                "source_locator": f"{node['source_locator']}::CRANCHOR:{start}-{end}",
                "source_order_key": f"{node['source_order_key']}::{start:012d}-{end:012d}",
                "source_text": candidate_text,
                "source_text_sha256": hashlib.sha256(candidate_text.encode("utf-8")).hexdigest(),
                "trigger_signals": trigger_signals,
                "candidate_score": score,
                "candidate_priority": _KIND_PRIORITY[kind] + 1,
                "generation_method": method,
                "document_genre": document["document_genre"],
                "document_reaction_family": document["document_reaction_family"],
                "document_reaction_family_signals": document["document_reaction_family_signals"],
                "provenance_type": node["provenance_type"],
                "maximum_support_role": node["maximum_support_role"],
                "raw_heading": node["raw_heading"],
                "direct_section_type": node["direct_section_type"],
                "effective_section_type": node["effective_section_type"],
                "document_region": node["document_region"],
                "paragraph_uid": node["paragraph_uid"],
                "section_uid": node["section_uid"],
            }
            candidates.append(record)
    return sorted(candidates, key=lambda item: (str(item["paper_id"]), int(item["source_start_offset"]), int(item["source_end_offset"])))


def summarize_candidates(
    candidates: list[dict[str, Any]],
    source_nodes: list[dict[str, Any]],
    document_count: int,
) -> dict[str, Any]:
    node_index = {str(node["source_node_id"]): node for node in source_nodes}
    ids = [str(record["cleanroom_span_id"]) for record in candidates]
    ranges = [(str(record["document_id"]), int(record["source_start_offset"]), int(record["source_end_offset"])) for record in candidates]
    per_document = Counter(str(record["document_id"]) for record in candidates)
    cross_paragraph = 0
    unresolved = 0
    for record in candidates:
        node = node_index.get(str(record["source_node_id"]))
        if node is None:
            unresolved += 1
            continue
        if not (
            int(node["source_start_offset"]) <= int(record["source_start_offset"])
            and int(record["source_end_offset"]) <= int(node["source_end_offset"])
        ):
            cross_paragraph += 1
    distribution = Counter(per_document.get(document_id, 0) for document_id in {
        str(node["document_id"]) for node in source_nodes
    })
    return {
        "document_count": document_count,
        "source_node_count": len(source_nodes),
        "candidate_span_count": len(candidates),
        "candidates_per_document_distribution": {str(key): value for key, value in sorted(distribution.items())},
        "duplicate_offset_count": len(ranges) - len(set(ranges)),
        "cross_paragraph_candidate_count": cross_paragraph,
        "candidate_id_collision_count": len(ids) - len(set(ids)),
        "unresolved_source_mapping_count": unresolved,
    }


def _candidate_windows(text: str, maximum: int) -> list[tuple[int, int, str, str]]:
    if len(text) <= maximum:
        return [(0, len(text), text, "whole_source_node")]
    spans = [match.span() for match in re.finditer(r"[^.!?\n]+(?:[.!?]+|\Z)", text)]
    if not spans:
        return [(offset, min(len(text), offset + maximum), text[offset:offset + maximum], "bounded_character_window")
                for offset in range(0, len(text), maximum)]
    windows: list[tuple[int, int, str, str]] = []
    start = spans[0][0]
    end = spans[0][1]
    for sentence_start, sentence_end in spans[1:]:
        if sentence_end - start > maximum and end > start:
            windows.append((start, end, text[start:end], "bounded_sentence_window"))
            start = sentence_start
        end = sentence_end
    windows.append((start, end, text[start:end], "bounded_sentence_window"))
    return windows


def _node_sort_key(node: dict[str, Any]) -> tuple[str, int, int]:
    return (
        str(node.get("paper_id") or ""),
        int(node.get("source_start_offset") or 0),
        int(node.get("source_end_offset") or 0),
    )
