"""Stage B semantic claim typing and analytical-method disambiguation."""

from __future__ import annotations

import re
from typing import Any

from enh3bench.document_scope import (
    BACKGROUND_DOCUMENT_SCOPE,
    PERSPECTIVE_GENRE,
    REVIEW_GENRE,
    SECONDARY_DOCUMENT_SCOPE,
    SEMANTIC_ELIGIBILITY_SCHEMA_VERSION,
)


_AMMONIA = r"(?:ammonia|nh\s*3|nh\s*4\s*\+?|ammonium)"
_QUANT_ACTION = (
    r"(?:quantif(?:y|ied|ication)|determin(?:e|ed|ation)|measur(?:e|ed|ement)|"
    r"assay(?:ed)?|analy[sz](?:e|ed|is)|calibrat(?:e|ed|ion)|detect(?:ed|ion)|concentration)"
)
_MASS_SPEC_METHOD = r"(?:mass spectrometr(?:y|ic)|\bgc\s*[-–]?\s*ms\b|gas chromatography\s*[-–]?\s*mass spectrometry)"
_ENZYMATIC_METHOD = r"(?:enzymatic ammonium assay|nadh(?: consumption)?(?: assay)?)"
_ANALYTICAL_METHOD = (
    r"(?:ion chromatography|\bic\b|nmr|nuclear magnetic resonance|uv\s*[-–]?\s*vis|"
    r"ultraviolet[- ]visible|indophenol|nessler|colorimetric|spectrophotometr(?:y|ic)|"
    r"fluorometr(?:y|ic)|calibration curve|standard addition|" + _MASS_SPEC_METHOD + r"|"
    + _ENZYMATIC_METHOD
    + r"|ammonia[- ]selective electrode|ammonium[- ]selective electrode|titration|conductivity assay)"
)
_MASS_SPEC = re.compile(_MASS_SPEC_METHOD, re.IGNORECASE)
_ENZYMATIC = re.compile(_ENZYMATIC_METHOD, re.IGNORECASE)
_TRAP = re.compile(
    r"\b(?:acid|base|alkaline|water|boric acid|sulfuric acid|hydrochloric acid)?\s*trap(?:ping|ped|s)?\b|"
    r"\b(?:acid|base|capture) vessel\b|"
    r"\b(?:gas )?(?:scrubber|purifier|purification train|gas purification)\b|"
    r"\b(?:passed|fed|routed) through\b.{0,100}\b(?:acid|base|scrubber|trap)\b|"
    r"\b(?:outlet|gas[- ]phase) (?:capture|captured|trapping)\b",
    re.IGNORECASE,
)
_PERFORMANCE_CONTEXT = re.compile(
    r"\b(?:faradaic efficienc(?:y|ies)|ammonia yield|high yield|yield rate|"
    r"nh\s*3 (?:yield|rate)|production rate|current density|performance|activity)\b",
    re.IGNORECASE,
)
_FARADAIC_EFFICIENCY_WORDS = re.compile(r"\bfaradaic efficienc(?:y|ies)\b", re.IGNORECASE)
_FE_ACRONYM = re.compile(
    r"\bFE(?:s)?\b(?=\s*(?:(?:=|:|of|was|were|reached|up to)\s*)?(?:~\s*)?\d)",
)
_NUMERIC_RESULT = re.compile(
    r"(?:~|≈|about|up to|over|under)?\s*\d+(?:\.\d+)?\s*(?:%|"
    r"(?:m|μ|µ|n|k)?A(?:\s*cm\s*[-−]?\s*2)?|"
    r"(?:μ|µ|m|n)?g(?:\s*(?:h|hr)\s*[-−]?\s*1)?|"
    r"(?:m|μ|µ|n)?mol(?:\s*(?:h|s)\s*[-−]?\s*1)?|"
    r"(?:mV|V)|(?:h|hr|hours?|min|minutes?|s|seconds?))\b",
    re.IGNORECASE,
)
_COMPARATIVE_RESULT = re.compile(
    r"\b(?:increased|decreased|higher|lower|maximum|maximal|achieved|reached|improved|enhanced)\b",
    re.IGNORECASE,
)
_TARGET_SAMPLE = re.compile(
    r"\b(?:our|this|the)\s+(?:catalyst|sample|electrode|material|cell|system)|"
    r"\b(?:catalyst|sample|electrode|material)\s+(?:we|prepared|synthesized|developed)\b",
    re.IGNORECASE,
)
_VALIDATION = re.compile(
    r"\b(?:15\s*n(?:2|h3|h4\s*\+?)?|nitrogen[- ]15|blank control|argon blank|ar blank|n2[- ]free|"
    r"contamination control|nox screening|impurity screening|\bblank\b|control electrode|control experiment|"
    r"chronoamperometr(?:y|ic).{0,80}(?:control|comparison)|"
    r"(?:control|comparison).{0,80}chronoamperometr(?:y|ic))\b",
    re.IGNORECASE,
)
_REACTOR = re.compile(
    r"\b(?:h[- ]?cell|flow cell|flow reactor|gas diffusion electrode|gde|mea|active area|"
    r"reactor setup|cell configuration)\b",
    re.IGNORECASE,
)
_PROCESS = re.compile(
    r"\b(?:electrolyte recycle|solvent inventory|separation train|auxiliary load|balance of plant|"
    r"process boundary|system boundary|plant boundary)\b",
    re.IGNORECASE,
)
_PROTOCOL = re.compile(
    r"\b(?:protocol|guideline|stepwise procedure|standard operating procedure|experimental procedure)\b",
    re.IGNORECASE,
)
_MECHANISM = re.compile(
    r"\b(?:mechanis(?:m|tic)|reaction pathway|rate[- ]determining step|finite element analysis|\bfea\b|"
    r"density functional theory|\bdft\b|nitrate transport|mass transport|vacanc(?:y|ies)|"
    r"adsorption energ(?:y|ies)|intermediate)\b",
    re.IGNORECASE,
)
_PERSPECTIVE_RECOMMENDATION = re.compile(
    r"\b(?:we recommend|should be considered|future work should|it is important to|we propose a roadmap|"
    r"research priorities|future directions?)\b",
    re.IGNORECASE,
)

_LOW_TRUST_PROVENANCE = {"reference", "bibliography", "figure_caption", "scheme_caption", "review_table"}
_LOW_TRUST_TEXT_CLASSES = {
    "reference_list", "figure_caption", "scheme_caption", "review_table", "background_context",
}
_LEGACY_TYPES = {
    "performance_claim", "validation_claim", "ammonia_quantification_claim", "reactor_claim",
    "process_claim", "protocol_claim", "mechanism_claim", "gas_purification_or_capture_claim",
    "secondary_context_claim", "performance_result_claim", "performance_context_claim",
}


def has_ammonia_quantification_signal(value: str | dict[str, Any]) -> bool:
    """Return true only for NH3/NH4 analytical measurement semantics.

    Trapping, scrubbing, purification, and capture remain insufficient without
    an ammonia analyte connected to an analytical method or measurement action.
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
    return bool(
        analyte_method
        and analyte_action
        and re.search(_ANALYTICAL_METHOD, normalized, re.IGNORECASE)
    )


def has_mass_spectrometry_quantification_signal(value: str | dict[str, Any]) -> bool:
    text = _record_text(value) if isinstance(value, dict) else str(value or "")
    return bool(has_ammonia_quantification_signal(value) and _MASS_SPEC.search(text))


def has_enzymatic_quantification_signal(value: str | dict[str, Any]) -> bool:
    text = _record_text(value) if isinstance(value, dict) else str(value or "")
    return bool(has_ammonia_quantification_signal(value) and _ENZYMATIC.search(text))


def has_gas_purification_trap_signal(value: str | dict[str, Any]) -> bool:
    """Return true for gas purification, scrubbing, or trap/capture semantics."""

    text = _record_text(value) if isinstance(value, dict) else str(value or "")
    return bool(_TRAP.search(" ".join(text.split())))


def assess_performance_evidence(record: dict[str, Any]) -> dict[str, Any]:
    """Distinguish an actual result from qualitative performance context."""

    text = _record_text(record)
    signals: list[str] = []
    structured = _structured_performance_field(record)
    if structured:
        signals.append("structured_performance_result_field")
    faradaic = bool(_FARADAIC_EFFICIENCY_WORDS.search(text) or _FE_ACRONYM.search(text))
    if faradaic:
        signals.append("faradaic_efficiency_result")
    numeric = bool(_NUMERIC_RESULT.search(text))
    if numeric:
        signals.append("numeric_value_with_unit")
    comparative = bool(
        _COMPARATIVE_RESULT.search(text)
        and _TARGET_SAMPLE.search(text)
        and str(record.get("claim_ownership") or "target_authors") == "target_authors"
    )
    if comparative:
        signals.append("current_study_comparative_result")
    context = bool(_PERFORMANCE_CONTEXT.search(text) or faradaic)
    result = bool(structured or (context and numeric) or (faradaic and re.search(r"\d|%", text)) or comparative)
    if result:
        strength = "quantitative_result" if structured or numeric or faradaic else "comparative_result"
    elif context:
        strength = "context_only"
        signals.append("qualitative_performance_context")
    else:
        strength = "none"
    return {
        "performance_evidence_strength": strength,
        "performance_evidence_signals": list(dict.fromkeys(signals)),
        "performance_result_evidence": result,
        "quantitative_performance_evidence": strength == "quantitative_result",
    }


def is_fe_material_only_false_performance(record: dict[str, Any]) -> bool:
    """Return true only if an Fe-material token would be the sole result cue."""

    text = _record_text(record)
    material = bool(re.search(r"\b(?:FeS|FeSe|Fe\s+single atom|Fe\s+SAC|Fe[- ]based)\b", text))
    evidence = assess_performance_evidence(record)
    return bool(material and not evidence["performance_result_evidence"])


def classify_claim_type(record: dict[str, Any]) -> dict[str, Any]:
    """Infer a corrective semantic type without rewriting the v0.13 label."""

    text = _record_text(record)
    quantification = has_ammonia_quantification_signal(record)
    gas_trap = has_gas_purification_trap_signal(record)
    performance = assess_performance_evidence(record)
    provenance = str(record.get("provenance_type") or "unknown").casefold()
    text_class = str(record.get("text_class") or "unknown").casefold()
    span_scope = str(record.get("span_claim_scope") or record.get("document_scope") or "").casefold()
    document_genre = str(record.get("document_genre") or "").casefold()
    legacy = str(record.get("claim_type") or "").strip().casefold()
    signals: list[str] = []

    low_trust = (
        provenance in _LOW_TRUST_PROVENANCE
        or text_class in _LOW_TRUST_TEXT_CLASSES
        or bool(record.get("is_secondary_or_context"))
        or bool(record.get("is_reject_or_low_trust"))
        or span_scope in {BACKGROUND_DOCUMENT_SCOPE, SECONDARY_DOCUMENT_SCOPE}
    )
    perspective_recommendation = (
        document_genre in {REVIEW_GENRE, PERSPECTIVE_GENRE}
        and bool(_PERSPECTIVE_RECOMMENDATION.search(text))
    )

    # Priority is deliberate: semantic evidence corrects rather than inherits
    # the legacy type whenever a stronger signal is present.
    if low_trust or perspective_recommendation:
        semantic_type = "secondary_context_claim"
        confidence = "high"
        signals.append("secondary_context_source" if low_trust else "review_or_perspective_recommendation")
    elif quantification:
        semantic_type = "ammonia_quantification_claim"
        confidence = "high"
        signals.append("ammonia_analytical_measurement")
        if _MASS_SPEC.search(text):
            signals.append("mass_spectrometry_quantification")
        if _ENZYMATIC.search(text):
            signals.append("enzymatic_quantification")
    elif gas_trap:
        semantic_type = "gas_purification_or_capture_claim"
        confidence = "high"
        signals.append("gas_purification_or_trap_without_quantification")
    elif _VALIDATION.search(text):
        semantic_type = "validation_claim"
        confidence = "high"
        signals.append("explicit_validation_signal")
    elif _REACTOR.search(text):
        semantic_type = "reactor_claim"
        confidence = "high"
        signals.append("explicit_reactor_signal")
    elif _PROCESS.search(text):
        semantic_type = "process_claim"
        confidence = "high"
        signals.append("explicit_process_boundary_signal")
    elif _PROTOCOL.search(text) or text_class == "protocol_guideline":
        semantic_type = "protocol_claim"
        confidence = "medium"
        signals.append("protocol_signal")
    elif _MECHANISM.search(text):
        semantic_type = "mechanism_claim"
        confidence = "medium"
        signals.append("mechanism_signal")
    elif performance["performance_result_evidence"]:
        semantic_type = "performance_result_claim"
        confidence = "high"
        signals.append("performance_result_signal")
    elif performance["performance_evidence_strength"] == "context_only" or legacy == "performance_claim":
        semantic_type = "performance_context_claim"
        confidence = "medium" if performance["performance_evidence_strength"] == "context_only" else "low"
        signals.append("performance_context_signal")
    elif legacy in _LEGACY_TYPES:
        semantic_type = legacy
        confidence = "low"
        signals.append("legacy_claim_type_fallback")
    else:
        semantic_type = "untyped_claim"
        confidence = "low"
        signals.append("no_semantic_claim_signal")

    conflict = bool(legacy and legacy != semantic_type)
    if conflict:
        signals.append(f"legacy_semantic_conflict:{legacy}_vs_{semantic_type}")
    return {
        "semantic_eligibility_schema_version": SEMANTIC_ELIGIBILITY_SCHEMA_VERSION,
        "semantic_claim_type": semantic_type,
        "semantic_claim_type_confidence": confidence,
        "semantic_claim_type_conflict": conflict,
        "legacy_claim_type": legacy,
        "semantic_claim_type_signals": signals,
        **performance,
        "ammonia_quantification_signal": quantification,
        "gas_purification_trap_signal": gas_trap,
        "mass_spectrometry_quantification_signal": has_mass_spectrometry_quantification_signal(record),
        "enzymatic_quantification_signal": has_enzymatic_quantification_signal(record),
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


def _structured_performance_field(record: dict[str, Any]) -> bool:
    for key in (
        "faradaic_efficiency", "faradaic_efficiency_percent", "FE", "nh3_yield", "ammonia_yield",
        "yield_rate", "current_density", "runtime", "stability_runtime",
    ):
        value = record.get(key)
        if value is not None and str(value).strip():
            return True
    return False
