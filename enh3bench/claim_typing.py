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
_PERCENT_VALUE = re.compile(r"\d+(?:\.\d+)?\s*%")
_RATE_VALUE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:[numk\u00b5\u03bc]?g|渭g|碌g|[numk\u00b5\u03bc]?mol)\s*"
    r"(?:g\s*(?:cat(?:alyst)?)?\s*)?(?:[-/]?\s*(?:h|hr|s)\s*(?:[-\u2212\u2013^]?\s*1)?)"
    r"(?:\s*(?:cm|m)\s*(?:[-\u2212\u2013^]?\s*2))?",
    re.IGNORECASE,
)
_CURRENT_DENSITY_VALUE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:[mun\u00b5\u03bc]?A)\s*(?:cm|m)\s*(?:[-\u2212\u2013^]?\s*2)",
    re.IGNORECASE,
)
_YIELD_OR_RATE_METRIC = re.compile(
    rf"(?:{_AMMONIA}.{{0,45}}(?:yield|production rate)|(?:yield|production rate).{{0,45}}{_AMMONIA})",
    re.IGNORECASE,
)
_AMMONIA_CURRENT_METRIC = re.compile(
    rf"(?:{_AMMONIA}.{{0,35}}(?:partial )?current density|"
    rf"(?:partial )?current density.{{0,35}}{_AMMONIA})",
    re.IGNORECASE,
)
_AMMONIA_OUTCOME = re.compile(_AMMONIA, re.IGNORECASE)
_NON_AMMONIA_REACTION_ACTIVITY = re.compile(
    r"\b(?:HOR|HER|OER|ORR|CO2RR|hydrogen oxidation|hydrogen evolution|"
    r"oxygen evolution|oxygen reduction|carbon dioxide reduction)\b.{0,80}"
    r"\b(?:activity|performance|current density|deactivation|poisoning|stability)\b|"
    r"\b(?:activity|performance|current density|deactivation|poisoning|stability)\b.{0,80}"
    r"\b(?:HOR|HER|OER|ORR|CO2RR|hydrogen oxidation|hydrogen evolution|"
    r"oxygen evolution|oxygen reduction|carbon dioxide reduction)\b|"
    r"\b(?:Pt/C|anode|auxiliary electrode)\b.{0,60}\b(?:activity|deactivation|poisoning|stability)\b",
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
        # Validation-gate text detection calls back with a plain string, so
        # this local import has no recursive record-level decision.
        from enh3bench.validation_gates import detect_validation_gate

        return bool(detect_validation_gate(
            "ammonia_quantification", _record_text(value), value
        )["satisfied"])
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
        signals.append("faradaic_efficiency_context")
    fe_numeric = _metric_value_near(
        text, _FARADAIC_EFFICIENCY_WORDS, _PERCENT_VALUE, 60
    ) or _metric_value_near(text, _FE_ACRONYM, _PERCENT_VALUE, 60)
    yield_numeric = _metric_value_near(text, _YIELD_OR_RATE_METRIC, _RATE_VALUE, 85)
    current_numeric = _metric_value_near(
        text, _AMMONIA_CURRENT_METRIC, _CURRENT_DENSITY_VALUE, 70
    )
    if fe_numeric:
        signals.append("faradaic_efficiency_value_proximity")
    if yield_numeric:
        signals.append("ammonia_yield_rate_value_proximity")
    if current_numeric:
        signals.append("ammonia_current_density_value_proximity")
    numeric = bool(fe_numeric or yield_numeric or current_numeric)
    if numeric:
        signals.append("metric_specific_numeric_result")
    target_anchor = has_target_ammonia_reaction_outcome_anchor(record, text=text)
    if target_anchor:
        signals.append("target_ammonia_reaction_outcome_anchor")
    non_ammonia_activity_signal = bool(_NON_AMMONIA_REACTION_ACTIVITY.search(text))
    comparative = bool(
        _COMPARATIVE_RESULT.search(text)
        and target_anchor
        and (
            _AMMONIA_CURRENT_METRIC.search(text)
            or _YIELD_OR_RATE_METRIC.search(text)
            or faradaic
            or (_AMMONIA_OUTCOME.search(text) and _TARGET_SAMPLE.search(text))
        )
        and str(record.get("claim_ownership") or "target_authors") == "target_authors"
    )
    if comparative:
        signals.append("current_study_comparative_result")
    non_ammonia_activity = bool(
        non_ammonia_activity_signal and not (numeric or comparative)
    )
    if non_ammonia_activity:
        signals.append("non_ammonia_reaction_activity")
    context = bool(_PERFORMANCE_CONTEXT.search(text) or faradaic)
    result = bool(
        target_anchor
        and not (non_ammonia_activity and not _AMMONIA_OUTCOME.search(text))
        and (structured or numeric or comparative)
    )
    if result:
        strength = "quantitative_result" if structured or numeric else "comparative_result"
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
        "target_ammonia_reaction_outcome_anchor": target_anchor,
        "non_ammonia_reaction_activity": non_ammonia_activity,
    }


def has_target_ammonia_reaction_outcome_anchor(
    record: dict[str, Any], *, text: str | None = None
) -> bool:
    """Require an ammonia outcome, while retaining canonical FE shorthand."""

    source = text if text is not None else _record_text(record)
    if _AMMONIA_OUTCOME.search(source):
        return True
    if (
        (_FARADAIC_EFFICIENCY_WORDS.search(source) or _FE_ACRONYM.search(source))
        and not _NON_AMMONIA_REACTION_ACTIVITY.search(source)
    ):
        return True
    return any(
        record.get(key) is not None and str(record.get(key)).strip()
        for key in ("nh3_yield", "ammonia_yield", "yield_rate")
    )


def _metric_value_near(
    text: str, metric: re.Pattern[str], value: re.Pattern[str], window: int
) -> bool:
    metric_matches = list(metric.finditer(text))
    value_matches = list(value.finditer(text))
    return any(
        max(metric_match.start(), value_match.start())
        - min(metric_match.end(), value_match.end())
        <= window
        for metric_match in metric_matches
        for value_match in value_matches
    )


def is_fe_material_only_false_performance(record: dict[str, Any]) -> bool:
    """Return true only if an Fe-material token would be the sole result cue."""

    text = _record_text(record)
    material = bool(re.search(r"\b(?:FeS|FeSe|Fe\s+single atom|Fe\s+SAC|Fe[- ]based)\b", text))
    evidence = assess_performance_evidence(record)
    return bool(material and not evidence["performance_result_evidence"])


def classify_claim_type(record: dict[str, Any]) -> dict[str, Any]:
    """Infer a corrective semantic type without rewriting the v0.13 label."""

    text = _record_text(record)
    from enh3bench.validation_gates import detect_validation_gate

    quantification_gate = detect_validation_gate(
        "ammonia_quantification", text, record, text_source="target_text"
    )
    quantification = bool(quantification_gate["satisfied"])
    structured_quantification = _structured_quantification_present(record)
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
    elif quantification_gate["gate_conflict"]:
        semantic_type = "untyped_claim"
        confidence = "high"
        signals.append("structured_quantification_conflicts_with_target_text")
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
        "structured_quantification_present": structured_quantification,
        "structured_gate_text_conflict": bool(quantification_gate["gate_conflict"]),
        "ammonia_quantification_gate": quantification_gate,
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
        "yield_rate", "current_density",
    ):
        value = record.get(key)
        if value is not None and str(value).strip():
            return True
    return False


def _structured_quantification_present(record: dict[str, Any]) -> bool:
    gates = record.get("validation_gates") if isinstance(record.get("validation_gates"), dict) else {}
    stored = gates.get("ammonia_quantification", gates.get("quantification_method"))
    return str(stored or "").strip().casefold() in {"yes", "explicit", "pass", "present"}
