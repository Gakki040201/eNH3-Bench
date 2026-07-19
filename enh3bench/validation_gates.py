"""Safe Stage B validation-gate detection with provenance and negation audit."""

from __future__ import annotations

import re
from typing import Any


STRUCTURED_POSITIVE_VALUES = {"yes", "explicit", "pass", "present"}

_EXPLICIT_15N = re.compile(
    r"(?:\b15\s*N(?:2|H3|H4\s*\+?)?\b|\bnitrogen[- ]15\b|"
    r"\b15\s*N[- ]label(?:l)?ed\s+nitrogen\b)",
    re.IGNORECASE,
)
_GENERIC_ISOTOPE = re.compile(
    r"\b(?:isotope|isotope[- ]label(?:l)?ed|isotopic experiment|carbon isotope|deuterium isotope)\b",
    re.IGNORECASE,
)
_ISOTOPE_NEGATION = re.compile(
    r"\b(?:no|without)\b.{0,80}\b(?:15\s*N|nitrogen[- ]15|isotope|isotopic)\b|"
    r"\b(?:15\s*N|nitrogen[- ]15|isotope|isotopic)\b.{0,80}\b(?:not performed|not used|absent)\b",
    re.IGNORECASE,
)
_NO_SOURCE_NEGATION = re.compile(
    r"\b(?:no gas was supplied|no feed was used|no source was identified|"
    r"no concentration was reported|without (?:an? )?(?:NO|nitric[- ]oxide) (?:feed|source)|"
    r"no (?:NO|nitric[- ]oxide) (?:gas )?(?:feed|source)(?: was)? (?:used|defined|supplied)|"
    r"(?:NO|nitric[- ]oxide)(?: gas)?(?: feed| source)? was not (?:supplied|used|defined)|"
    r"(?:NO|nitric[- ]oxide) (?:gas )?(?:feed|source) was absent)\b",
    re.IGNORECASE,
)
_NOX_BALANCE_NEGATION = re.compile(
    r"\b(?:[Nn]o mass balance(?: was reported)?|[Ww]ithout (?:a )?mass balance|"
    r"[Nn]o (?:NOx|NO|nitric[- ]oxide|nitrogen[- ]oxide) (?:mass |material )?balance(?: was reported)?|"
    r"(?:NOx|NO|nitric[- ]oxide|nitrogen[- ]oxide) (?:mass |material )?balance was not "
    r"(?:performed|reported)|[Mm]ass balance was not (?:performed|reported))\b",
)


def detect_validation_gate(
    gate: str,
    text: str,
    record: dict[str, Any] | None = None,
    *,
    text_source: str = "target_text",
) -> dict[str, Any]:
    """Return a gate decision plus its detection source and conflict state."""

    source_text = str(text or "")
    structured_value = _structured_gate_value(gate, record or {})
    structured_explicit = structured_value in STRUCTURED_POSITIVE_VALUES
    negated = _gate_negated(gate, source_text)
    signals: list[str] = []
    if structured_explicit:
        signals.append(f"structured_explicit_{gate}")
        if gate == "isotope_15N":
            signals.append("structured_explicit_15N")
        if negated:
            signals.append("structured_gate_conflicts_with_text_negation")
            return _gate_result(False, "structured_explicit", True, signals)
        return _gate_result(True, "structured_explicit", False, signals)

    detected = _text_gate_satisfied(gate, source_text)
    if detected and not negated:
        signals.append(f"{text_source}_{gate}")
        return _gate_result(True, text_source, False, signals)
    if negated:
        signals.append(f"{text_source}_{gate}_negated")
    return _gate_result(False, "", False, signals)


def has_explicit_15n(text: str) -> bool:
    return bool(_EXPLICIT_15N.search(str(text or "")) and not _ISOTOPE_NEGATION.search(str(text or "")))


def has_generic_isotope_without_15n(text: str) -> bool:
    value = str(text or "")
    return bool(_GENERIC_ISOTOPE.search(value) and not _EXPLICIT_15N.search(value))


def has_negated_no_source(text: str) -> bool:
    return bool(_NO_SOURCE_NEGATION.search(str(text or "")))


def has_negated_nox_balance(text: str) -> bool:
    return bool(_NOX_BALANCE_NEGATION.search(str(text or "")))


def _structured_gate_value(gate: str, record: dict[str, Any]) -> str:
    gates = record.get("validation_gates") if isinstance(record.get("validation_gates"), dict) else {}
    aliases = {
        "ammonia_quantification": ("ammonia_quantification", "quantification_method"),
        "isotope_15N": ("isotope_15N",),
        "NOx_control": ("NOx_control", "nox_control"),
    }
    for key in aliases.get(gate, (gate,)):
        if key in gates:
            return str(gates.get(key) or "").strip().casefold()
    return ""


def _gate_negated(gate: str, text: str) -> bool:
    if gate == "isotope_15N":
        return bool(_ISOTOPE_NEGATION.search(text))
    if gate == "NO_source_defined":
        return has_negated_no_source(text)
    if gate == "NOx_balance":
        return has_negated_nox_balance(text)
    if gate == "ammonia_quantification":
        return bool(re.search(
            r"\b(?:[Nn]o|[Ww]ithout)\b.{0,80}(?i:\b(?:ammonia|ammonium|nh\s*3|nh\s*4)\b.{0,80}"
            r"\b(?:quantification|measurement|analysis|assay)\b)|"
            r"(?i:\b(?:ammonia|ammonium|nh\s*3|nh\s*4)\b.{0,80}\bnot (?:measured|quantified|analyzed)\b)",
            text,
        ))
    return False


def _text_gate_satisfied(gate: str, text: str) -> bool:
    if gate == "isotope_15N":
        return has_explicit_15n(text)
    if gate == "blank_control":
        return bool(re.search(r"\b(?:ar|argon|n2[- ]?free|electrolyte)\s+blank\b|\bblank control\b", text, re.IGNORECASE))
    if gate == "NOx_control":
        return bool(re.search(
            r"\bnox\s+(?:screening|control|impurit(?:y|ies)|analysis)\b|\bnitrate/nitrite impurity\b",
            text,
            re.IGNORECASE,
        ))
    if gate == "contamination_control":
        return bool(re.search(
            r"\b(?:ammonia )?contamination control\b|\bbackground (?:nh3|ammonia) control\b|\bimpurity screening\b",
            text,
            re.IGNORECASE,
        ))
    if gate == "ammonia_quantification":
        from enh3bench.claim_typing import has_ammonia_quantification_signal

        return has_ammonia_quantification_signal(text)
    if gate == "operating_field_disclosure":
        return bool(re.search(r"\b(?:current density|cell voltage|applied potential|runtime|flow rate)\b", text, re.IGNORECASE))
    if gate == "nitrate_source_defined":
        return bool(re.search(
            r"\bnitrate\s+(?:feed|source|reactant|concentration|electrolyte)\b|\b(?:feed|source|reactant)\s+nitrate\b",
            text,
            re.IGNORECASE,
        ))
    if gate == "nitrite_source_defined":
        return bool(re.search(
            r"\bnitrite\s+(?:feed|source|reactant|concentration|electrolyte)\b|\b(?:feed|source|reactant)\s+nitrite\b",
            text,
            re.IGNORECASE,
        ))
    if gate == "NO_source_defined":
        return _no_source_positive(text)
    if gate == "nitrogen_balance":
        return bool(re.search(r"\bnitrogen (?:mass )?balance\b|\bn balance\b", text, re.IGNORECASE))
    if gate == "NOx_balance":
        return _nox_balance_positive(text)
    if gate == "competing_product_tracking":
        return bool(re.search(
            r"\b(?:competing|by[- ]?product|nitrite|nitrate|n2)\b.{0,60}\b(?:tracking|quantif|balance|analysis)\b",
            text,
            re.IGNORECASE,
        ))
    if gate == "nitrogen_source_disambiguation":
        return bool(re.search(
            r"\bnitrogen source\b.{0,40}\b(?:defined|identified|n2|nitrate|nitrite|NO)\b",
            text,
            re.IGNORECASE,
        ))
    return False


def _no_source_positive(text: str) -> bool:
    if has_negated_no_source(text):
        return False
    patterns = (
        r"\b\d+(?:\.\d+)?\s*%\s+NO\s+in\s+(?:Ar|argon|N2|nitrogen)\b",
        r"\b(?:NO|nitric[- ]oxide) (?:gas )?(?:feed|stream)\b",
        r"\b(?:NO|nitric[- ]oxide)(?: gas)? was (?:supplied|introduced)\b",
        r"\b(?:NO|nitric[- ]oxide)(?: gas)? was used as (?:the |a )?(?:reactant|nitrogen source)\b",
        r"\b(?:NO|nitric[- ]oxide) concentration (?:of|was) \d+(?:\.\d+)?\s*%",
        r"\b(?:feed|feed gas|gas feed) (?:contained|containing) \d+(?:\.\d+)?\s*%\s+NO\b",
        r"\b(?:feed|feed gas|gas feed) containing (?:NO|nitric[- ]oxide)\b",
    )
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _nox_balance_positive(text: str) -> bool:
    if has_negated_nox_balance(text):
        return False
    return bool(
        re.search(r"\bNOx\s+(?:mass |material )?balance\b", text)
        or re.search(r"\bNO\s+mass balance\b", text)
        or re.search(r"\bnitric[- ]oxide\s+mass balance\b", text, re.IGNORECASE)
        or re.search(r"\bnitrogen[- ]oxide\s+material balance\b", text, re.IGNORECASE)
    )


def _gate_result(satisfied: bool, source: str, conflict: bool, signals: list[str]) -> dict[str, Any]:
    return {
        "satisfied": bool(satisfied),
        "gate_detection_source": source,
        "gate_conflict": bool(conflict),
        "gate_detection_signals": list(dict.fromkeys(signals)),
    }
