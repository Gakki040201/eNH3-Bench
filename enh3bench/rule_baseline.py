"""No-API rule-based extraction baseline for eNH3-Bench."""

from __future__ import annotations

import re
from typing import Any

from enh3bench.reaction_profiles import infer_reaction_family_detailed


_NUMBER = r"[-+]?\d+(?:\.\d+)?"


def classify_reaction_family(text: str) -> str:
    """Classify a source span into a benchmark reaction family."""

    return infer_reaction_family_detailed(text=text)["reaction_family"]


def detect_nitrogen_source(text: str) -> str:
    """Detect the nitrogen source explicitly named in a span."""

    normalized = _normalize(text)
    if _contains_any(normalized, ["15n2", "15 n2"]):
        return "15N2"
    if _contains_any(normalized, ["no3-", "nitrate"]):
        return "NO3-"
    if _contains_any(normalized, ["no2-", "nitrite"]):
        return "NO2-"
    if "nox" in normalized:
        return "NOx"
    if _contains_any(normalized, ["nitric oxide", " no "]):
        return "NO"
    if _contains_any(normalized, ["n2", "nitrogen gas"]):
        return "N2"
    if _contains_any(normalized, ["catalyst impurity", "nitrogen impurity"]):
        return "catalyst_impurity"
    return "unknown"


def extract_fe_percent(text: str) -> float | None:
    """Extract Faradaic efficiency percentage from a source span."""

    patterns = [
        rf"({_NUMBER})\s*%\s*(?:faradaic\s+efficiency|fe)\b",
        rf"(?:faradaic\s+efficiency|fe)\s*(?:for\s+\w+\s*)?(?:of|=|was|is|reached|at)?\s*({_NUMBER})\s*%",
    ]
    return _first_float_match(text, patterns)


def extract_nh3_yield(text: str) -> tuple[float | None, str | None]:
    """Extract a reported NH3 yield value and original unit."""

    unit = r"(?:n?mol|u?mol|mmol|µmol|μmol|ug|µg|μg|mg)\s*[A-Za-z0-9µμ%/\-^ ]{0,40}"
    patterns = [
        rf"(?:nh3|ammonia)[^.:\n;]{{0,90}}?\b(?:at|of|rate\s+of|yield\s+of|produced|production\s+rate\s+of)\s*({_NUMBER})\s*({unit})",
        rf"(?:yield|rate|production\s+rate)[^.:\n;]{{0,70}}?(?:of|was|reached|=)?\s*({_NUMBER})\s*({unit})",
        rf"({_NUMBER})\s*({unit})[^.:\n;]{{0,40}}?(?:nh3|ammonia)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = float(match.group(1))
            raw_unit = _clean_unit(match.group(2))
            if raw_unit:
                return value, raw_unit
    return None, None


def detect_isotope_validation(text: str) -> str:
    """Detect whether isotope validation is explicitly reported."""

    normalized = _normalize(text)
    if _contains_any(normalized, ["15n", "15n2", "isotope labeling", "15nh4", "isotopic"]):
        return "yes"
    return "unclear"


def detect_blank_control(text: str) -> str:
    """Detect whether blank controls are explicitly reported."""

    normalized = _normalize(text)
    if _contains_any(normalized, ["ar blank", "blank control", "control experiment", "n2-free"]):
        return "yes"
    return "unclear"


def detect_contamination_control(text: str) -> str:
    """Detect whether contamination controls are explicitly reported."""

    normalized = _normalize(text)
    if _contains_any(
        normalized,
        [
            "nox",
            "nitrate contamination",
            "nitrite contamination",
            "impurity",
            "background ammonia",
            "contamination check",
            "contamination checks",
        ],
    ):
        return "yes"
    return "unclear"


def detect_detection_method(text: str) -> str | None:
    """Detect common ammonia quantification methods."""

    normalized = _normalize(text)
    methods = [
        ("indophenol", "indophenol"),
        ("nessler", "Nessler"),
        ("ion chromatography", "ion chromatography"),
        ("nmr", "NMR"),
    ]
    found = [label for needle, label in methods if needle in normalized]
    if not found:
        return None
    return " and ".join(found)


def run_rule_extraction(span_record: dict[str, Any]) -> dict[str, Any]:
    """Run the local rule baseline for one span record."""

    text = str(span_record.get("text", "")).strip()
    source_section = str(span_record.get("source_section", "unknown")).strip() or "unknown"
    fe_percent = extract_fe_percent(text)
    nh3_yield_value, nh3_yield_unit = extract_nh3_yield(text)
    reaction = infer_reaction_family_detailed(
        text=text,
        section_type=str(span_record.get("section_type") or source_section),
        record=span_record,
    )
    return {
        "evidence_id": _evidence_id(span_record),
        "paper_id": str(span_record.get("paper_id", "")).strip(),
        "source_span": text,
        "source_section": source_section,
        "reaction_family": reaction["reaction_family"],
        "reaction_family_confidence": reaction["reaction_family_confidence"],
        "reaction_family_scores": reaction["reaction_family_scores"],
        "reaction_family_signals": reaction["reaction_family_signals"],
        "reaction_family_scope": reaction["reaction_family_scope"],
        "paper_level_reaction_family": str(span_record.get("paper_level_reaction_family") or "unclear"),
        "reaction_family_conflict": reaction["reaction_family_conflict"],
        "nitrogen_source": detect_nitrogen_source(text),
        "catalyst": _detect_catalyst(text),
        "catalyst_class": None,
        "electrolyte": _detect_electrolyte(text),
        "reactor_type": _detect_reactor_type(text),
        "membrane": None,
        "potential_value": _extract_potential_value(text),
        "potential_unit": _extract_potential_unit(text),
        "potential_reference": _extract_potential_reference(text),
        "current_density_mA_cm2": _extract_current_density(text),
        "faradaic_efficiency_percent": fe_percent,
        "nh3_yield_value": nh3_yield_value,
        "nh3_yield_unit": nh3_yield_unit,
        "nh3_yield_normalized_value": None,
        "nh3_yield_normalized_unit": None,
        "energy_efficiency_percent": None,
        "stability_hours": _extract_stability_hours(text),
        "detection_method": detect_detection_method(text),
        "isotope_validation": detect_isotope_validation(text),
        "blank_control": detect_blank_control(text),
        "contamination_control": detect_contamination_control(text),
        "nox_screening": _detect_nox_screening(text),
        "reliability_label": _baseline_reliability_label(text),
        "evidence_type": "primary_claim",
        "gold_notes": None,
    }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _first_float_match(text: str, patterns: list[str]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _clean_unit(unit: str) -> str:
    unit = re.sub(r"\s+", " ", unit).strip(" .,;")
    unit = re.sub(r"\s+(?:with|and|at|for|from|in|by)\b.*$", "", unit, flags=re.IGNORECASE)
    return unit.strip(" .,;")


def _evidence_id(span_record: dict[str, Any]) -> str:
    span_id = str(span_record.get("span_id", "")).strip()
    if span_id.startswith("S") and len(span_id) > 1:
        return f"E{span_id[1:]}"
    if span_id:
        return f"E_{span_id}"
    return "E_TODO"


def _detect_catalyst(text: str) -> str | None:
    match = re.search(r"\b(?:the\s+)?([A-Z][A-Za-z0-9/\-]{0,20})\s+catalyst\b", text)
    if match:
        return match.group(1)
    return None


def _detect_electrolyte(text: str) -> str | None:
    match = re.search(
        r"\b(\d+(?:\.\d+)?\s*M\s+[A-Za-z0-9+\-]*"
        r"(?:KOH|NaOH|HCl|H2SO4)"
        r"(?:\s+with\s+\d+(?:\.\d+)?\s*mM\s+[A-Za-z0-9+\-]+)?)\b",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(r"\b([A-Za-z0-9+\-]*(?:KOH|NaOH|HCl|H2SO4))\b", text)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    return None


def _detect_reactor_type(text: str) -> str | None:
    normalized = _normalize(text)
    if "divided cell" in normalized:
        return "divided cell"
    if "h-cell" in normalized or "h cell" in normalized:
        return "H-cell"
    if "flow cell" in normalized:
        return "flow cell"
    return None


def _extract_potential_value(text: str) -> float | None:
    patterns = [
        rf"({_NUMBER})\s*V\s+vs\.?\s*[A-Za-z]+",
        rf"at\s+({_NUMBER})\s*V\b",
    ]
    return _first_float_match(text, patterns)


def _extract_potential_unit(text: str) -> str | None:
    return "V" if _extract_potential_value(text) is not None else None


def _extract_potential_reference(text: str) -> str | None:
    match = re.search(r"\bvs\.?\s*([A-Za-z]+)\b", text)
    if match and _extract_potential_value(text) is not None:
        return f"vs {match.group(1).upper()}"
    return None


def _extract_current_density(text: str) -> float | None:
    patterns = [
        rf"({_NUMBER})\s*mA\s*cm(?:\^-?2|-2|−2)?",
        rf"({_NUMBER})\s*mA\s*/\s*cm(?:\^?2)?",
    ]
    return _first_float_match(text, patterns)


def _extract_stability_hours(text: str) -> float | None:
    match = re.search(rf"({_NUMBER})\s*h(?:ours?)?\b", text, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _detect_nox_screening(text: str) -> str:
    normalized = _normalize(text)
    if _contains_any(normalized, ["nox screening", "screening for nox", "nox"]):
        return "yes"
    return "unclear"


def _baseline_reliability_label(text: str) -> str:
    if detect_isotope_validation(text) == "yes" and detect_blank_control(text) == "yes":
        return "B"
    if extract_fe_percent(text) is not None or extract_nh3_yield(text)[0] is not None:
        return "C"
    return "D"
