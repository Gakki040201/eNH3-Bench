"""Rule-based field-level grounding checks for draft evidence records."""

from __future__ import annotations

import re
from typing import Any


GROUNDING_FIELDS = [
    "reaction_family",
    "nitrogen_source",
    "faradaic_efficiency_percent",
    "energy_efficiency_percent",
    "nh3_yield_value",
    "nh3_yield_unit",
    "potential_value",
    "current_density_mA_cm2",
    "stability_hours",
    "isotope_validation",
    "blank_control",
    "contamination_control",
    "nox_screening",
    "detection_method",
]

_NUMBER = r"[-+]?\d+(?:\.\d+)?"


def ground_field(record: dict[str, Any], field: str) -> dict[str, Any]:
    """Return source-grounding status for one field in a draft record."""

    value = record.get(field)
    text = str(record.get("source_span", ""))
    if _is_missing(value):
        return _grounding(field, value, "missing", None, None)

    checker = _FIELD_CHECKERS.get(field, _explicit_value_in_text)
    explicit = checker(value, text)
    if explicit:
        return _grounding(field, value, "explicit", _snippet(text, explicit), None)

    status = "inferred" if value not in {"unclear", "unknown", "no", "not_applicable"} else "unclear"
    risk = _risk_for_ungrounded(field, value, status)
    return _grounding(field, value, status, None, risk)


def ground_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Return grounding checks for all important fields."""

    return [ground_field(record, field) for field in GROUNDING_FIELDS]


def summarize_grounding(groundings: list[dict[str, Any]]) -> dict[str, int]:
    """Summarize grounding statuses and risk flags."""

    summary = {"explicit": 0, "missing": 0, "inferred": 0, "unclear": 0, "risk_flags": 0}
    for item in groundings:
        status = str(item.get("grounding_status", "unclear"))
        if status in summary:
            summary[status] += 1
        if item.get("risk_flag"):
            summary["risk_flags"] += 1
    return summary


def _grounding(
    field: str,
    value: Any,
    status: str,
    evidence_snippet: str | None,
    risk_flag: str | None,
) -> dict[str, Any]:
    return {
        "field": field,
        "value": value,
        "grounding_status": status,
        "evidence_snippet": evidence_snippet,
        "risk_flag": risk_flag,
    }


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _explicit_value_in_text(value: Any, text: str) -> re.Match[str] | None:
    if _is_missing(value):
        return None
    return re.search(re.escape(str(value)), text, flags=re.IGNORECASE)


def _check_reaction_family(value: Any, text: str) -> re.Match[str] | None:
    patterns = {
        "eNRR": r"\b(?:N2 reduction|nitrogen reduction|NRR)\b",
        "LiNRR": r"\b(?:Li-mediated|lithium-mediated|Li\+|THF|Li salt)\b",
        "NO3RR": r"\b(?:NO3-|nitrate|nitrate reduction)\b",
        "NO2RR": r"\b(?:NO2-|nitrite|nitrite reduction)\b",
        "NORR": r"\b(?:nitric oxide|NO reduction|NORR)\b",
    }
    return _search(patterns.get(str(value), re.escape(str(value))), text)


def _check_nitrogen_source(value: Any, text: str) -> re.Match[str] | None:
    patterns = {
        "N2": r"\bN2\b|nitrogen gas",
        "15N2": r"15\s*N2|15N2|15\s*N",
        "NO3-": r"NO3-|nitrate",
        "NO2-": r"NO2-|nitrite",
        "NO": r"\bnitric oxide\b|\bNO\b",
        "NOx": r"\bNOx\b",
        "catalyst_impurity": r"catalyst impurity|nitrogen impurity",
    }
    return _search(patterns.get(str(value), re.escape(str(value))), text)


def _check_fe(value: Any, text: str) -> re.Match[str] | None:
    if _numeric_near(value, text, r"(?:FE|Faradaic efficiency|%)"):
        return _numeric_match(value, text)
    return None


def _check_ee(value: Any, text: str) -> re.Match[str] | None:
    if _numeric_near(value, text, r"(?:EE|energy efficiency)"):
        return _numeric_match(value, text)
    return None


def _check_nh3_yield_value(value: Any, text: str) -> re.Match[str] | None:
    if _numeric_near(value, text, r"(?:NH3|ammonia).{0,80}(?:yield|rate|productivity)|(?:yield|rate|productivity).{0,80}(?:NH3|ammonia)"):
        return _numeric_match(value, text)
    return None


def _check_nh3_yield_unit(value: Any, text: str) -> re.Match[str] | None:
    if _check_nh3_yield_value("0", text) or re.search(r"NH3|ammonia", text, flags=re.IGNORECASE):
        return _explicit_value_in_text(value, text)
    return None


def _check_potential(value: Any, text: str) -> re.Match[str] | None:
    if _numeric_near(value, text, r"(?:V|RHE|potential)"):
        return _numeric_match(value, text)
    return None


def _check_current_density(value: Any, text: str) -> re.Match[str] | None:
    if _numeric_near(value, text, r"mA\s*(?:cm|/cm|cm-2|cm\^-2)"):
        return _numeric_match(value, text)
    return None


def _check_stability(value: Any, text: str) -> re.Match[str] | None:
    if _numeric_near(value, text, r"(?:h|hour|hours|stability|stable|sustained)"):
        return _numeric_match(value, text)
    return None


def _check_isotope(value: Any, text: str) -> re.Match[str] | None:
    if str(value) != "yes":
        return _explicit_value_in_text(value, text)
    return _search(r"15\s*N|15N2|15NH4|isotope|isotopic", text)


def _check_blank(value: Any, text: str) -> re.Match[str] | None:
    if str(value) != "yes":
        return _explicit_value_in_text(value, text)
    return _search(r"\bblank\b|Ar blank|argon blank|N2-free|control", text)


def _check_contamination(value: Any, text: str) -> re.Match[str] | None:
    if str(value) != "yes":
        return _explicit_value_in_text(value, text)
    return _search(r"contamination|impurity|background ammonia|nitrate|nitrite|NOx", text)


def _check_nox(value: Any, text: str) -> re.Match[str] | None:
    if str(value) != "yes":
        return _explicit_value_in_text(value, text)
    return _search(r"NOx|NO2|NO3|nitrate|nitrite|screening|screened", text)


def _check_detection(value: Any, text: str) -> re.Match[str] | None:
    return _search(r"indophenol|Nessler|NMR|ion chromatography|\bIC\b", text)


def _numeric_near(value: Any, text: str, context_pattern: str) -> bool:
    if _numeric_match(value, text) is None:
        return False
    return _search(context_pattern, text) is not None


def _numeric_match(value: Any, text: str) -> re.Match[str] | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    candidates = {f"{number:g}", str(value)}
    if number.is_integer():
        candidates.add(str(int(number)))
    for candidate in candidates:
        match = _search(rf"(?<![\d.]){re.escape(candidate)}(?![\d.])", text)
        if match:
            return match
    return None


def _search(pattern: str | None, text: str) -> re.Match[str] | None:
    if not pattern:
        return None
    return re.search(pattern, text, flags=re.IGNORECASE)


def _snippet(text: str, match: re.Match[str]) -> str:
    start = max(0, match.start() - 50)
    end = min(len(text), match.end() + 50)
    return text[start:end].strip()


def _risk_for_ungrounded(field: str, value: Any, status: str) -> str | None:
    if status == "inferred":
        return f"{field} has value {value!r} but is not explicit in source_span"
    if field in {"isotope_validation", "blank_control", "contamination_control", "nox_screening"} and value == "yes":
        return f"{field}=yes requires explicit source evidence"
    return None


_FIELD_CHECKERS = {
    "reaction_family": _check_reaction_family,
    "nitrogen_source": _check_nitrogen_source,
    "faradaic_efficiency_percent": _check_fe,
    "energy_efficiency_percent": _check_ee,
    "nh3_yield_value": _check_nh3_yield_value,
    "nh3_yield_unit": _check_nh3_yield_unit,
    "potential_value": _check_potential,
    "current_density_mA_cm2": _check_current_density,
    "stability_hours": _check_stability,
    "isotope_validation": _check_isotope,
    "blank_control": _check_blank,
    "contamination_control": _check_contamination,
    "nox_screening": _check_nox,
    "detection_method": _check_detection,
}
