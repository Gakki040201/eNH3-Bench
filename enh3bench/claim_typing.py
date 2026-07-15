"""Stage B semantic claim typing and analytical-method disambiguation."""

from __future__ import annotations

import re
from typing import Any

from enh3bench.document_scope import SEMANTIC_ELIGIBILITY_SCHEMA_VERSION


_AMMONIA = r"(?:ammonia|nh\s*3|nh\s*4\s*\+?|ammonium)"
_QUANT_ACTION = r"(?:quantif(?:y|ied|ication)|determin(?:e|ed|ation)|measur(?:e|ed|ement)|assay(?:ed)?|analy[sz](?:e|ed|is)|calibrat(?:e|ed|ion)|detect(?:ed|ion)|concentration)"
_ANALYTICAL_METHOD = (
    r"(?:ion chromatography|\bic\b|nmr|nuclear magnetic resonance|uv\s*[-–]?\s*vis|"
    r"ultraviolet[- ]visible|indophenol|nessler|colorimetric|spectrophotometr(?:y|ic)|"
    r"fluorometr(?:y|ic)|calibration curve|standard addition)"
)
_TRAP = re.compile(
    r"\b(?:acid|base|alkaline|water|boric acid|sulfuric acid|hydrochloric acid)?\s*trap(?:ping|ped|s)?\b|"
    r"\b(?:gas )?(?:scrubber|purifier|purification train)\b|"
    r"\b(?:passed|fed|routed) through\b.{0,100}\b(?:acid|base|scrubber|trap)\b|"
    r"\b(?:outlet|gas[- ]phase) (?:capture|captured|trapping)\b",
    re.IGNORECASE,
)
_PERFORMANCE = re.compile(
    r"\b(?:faradaic efficiency|fe\s*(?:=|of|was|:)?\s*\d|ammonia yield|nh\s*3 yield|"
    r"production rate|current density)\b",
    re.IGNORECASE,
)
_VALIDATION = re.compile(
    r"\b(?:15\s*n(?:2)?|isotope|blank control|argon blank|ar blank|n2[- ]free|"
    r"contamination control|nox screening|impurity screening)\b",
    re.IGNORECASE,
)
_REACTOR = re.compile(r"\b(?:flow cell|flow reactor|gas diffusion electrode|gde|mea|active area)\b", re.IGNORECASE)
_PROCESS = re.compile(r"\b(?:electrolyte recycle|solvent inventory|separation train|auxiliary load|balance of plant|process boundary)\b", re.IGNORECASE)


def has_ammonia_quantification_signal(value: str | dict[str, Any]) -> bool:
    """Return true only for NH3/NH4 analytical measurement semantics.

    Trapping, scrubbing, or removing ammonia is not quantification unless an
    analytical action or method is also attached to the ammonia analyte.
    """

    if isinstance(value, dict):
        gates = value.get("validation_gates") if isinstance(value.get("validation_gates"), dict) else {}
        stored = gates.get("ammonia_quantification", gates.get("quantification_method"))
        if str(stored or "").strip().casefold() in {"yes", "explicit", "pass", "present"}:
            return True
        text = _record_text(value)
    else:
        text = str(value or "")
    normalized = " ".join(text.casefold().split())
    if not re.search(_AMMONIA, normalized, re.IGNORECASE):
        return False
    analyte_action = re.search(
        rf"{_AMMONIA}.{{0,100}}{_QUANT_ACTION}|{_QUANT_ACTION}.{{0,100}}{_AMMONIA}",
        normalized,
        re.IGNORECASE,
    )
    analyte_method = re.search(
        rf"{_AMMONIA}.{{0,120}}{_ANALYTICAL_METHOD}|{_ANALYTICAL_METHOD}.{{0,120}}{_AMMONIA}",
        normalized,
        re.IGNORECASE,
    )
    return bool(analyte_method or (analyte_action and re.search(_ANALYTICAL_METHOD, normalized, re.IGNORECASE)))


def has_gas_purification_trap_signal(value: str | dict[str, Any]) -> bool:
    """Return true for gas purification, scrubbing, or trap/capture semantics."""

    text = _record_text(value) if isinstance(value, dict) else str(value or "")
    return bool(_TRAP.search(" ".join(text.split())))


def classify_claim_type(record: dict[str, Any]) -> dict[str, Any]:
    """Return an additive semantic claim type without rewriting v0.13 claim_type."""

    text = _record_text(record)
    quantification = has_ammonia_quantification_signal(record)
    gas_trap = has_gas_purification_trap_signal(record)
    provenance = str(record.get("provenance_type") or "unknown").casefold()
    text_class = str(record.get("text_class") or "unknown").casefold()
    existing = str(record.get("claim_type") or "").strip().casefold()
    signals: list[str] = []

    if provenance in {"reference", "bibliography", "figure_caption", "scheme_caption", "review_table"} or text_class in {
        "reference_list", "figure_caption", "scheme_caption", "review_table", "background_context",
    }:
        semantic_type = "secondary_context_claim"
        signals.append("secondary_context_source")
    elif quantification:
        semantic_type = "ammonia_quantification_claim"
        signals.append("ammonia_analytical_measurement")
    elif gas_trap:
        semantic_type = "gas_purification_or_capture_claim"
        signals.append("gas_purification_or_trap_without_quantification")
    elif existing in {"performance_claim", "validation_claim", "reactor_claim", "process_claim", "protocol_claim"}:
        semantic_type = existing
        signals.append("existing_claim_type")
    elif _PROCESS.search(text):
        semantic_type = "process_claim"
        signals.append("process_signal")
    elif _REACTOR.search(text):
        semantic_type = "reactor_claim"
        signals.append("reactor_signal")
    elif _VALIDATION.search(text):
        semantic_type = "validation_claim"
        signals.append("validation_signal")
    elif _PERFORMANCE.search(text):
        semantic_type = "performance_claim"
        signals.append("performance_signal")
    elif text_class == "protocol_guideline":
        semantic_type = "protocol_claim"
        signals.append("protocol_text_class")
    else:
        semantic_type = "untyped_claim"
        signals.append("no_semantic_claim_signal")

    return {
        "semantic_eligibility_schema_version": SEMANTIC_ELIGIBILITY_SCHEMA_VERSION,
        "semantic_claim_type": semantic_type,
        "semantic_claim_type_signals": signals,
        "ammonia_quantification_signal": quantification,
        "gas_purification_trap_signal": gas_trap,
    }


def classify_claim_typing(record: dict[str, Any]) -> dict[str, Any]:
    """Alias exposing the module's additive Stage B semantic typing result."""

    return classify_claim_type(record)


def _record_text(record: dict[str, Any]) -> str:
    for key in ("source_text", "target_text", "text", "source_span"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return ""
