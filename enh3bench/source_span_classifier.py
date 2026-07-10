"""Rule-based source span classification for eNH3-TriageBench."""

from __future__ import annotations

import re
from typing import Any

from enh3bench.reaction_profiles import infer_reaction_family_detailed


TEXT_CLASSES = {
    "primary_performance",
    "primary_performance_with_validation",
    "protocol_guideline",
    "review_table",
    "figure_caption",
    "reference_list",
    "contamination_detection_evidence",
    "contamination_reassignment_evidence",
    "computational_screening",
    "background_context",
    "unknown",
}

LEDGERS = {"performance", "negative", "protocol", "secondary", "context", "reject"}


def classify_source_span(text: str) -> dict[str, Any]:
    """Classify one source span and return ledger-routing permissions."""

    source_text = str(text or "").strip()
    normalized = _normalize(source_text)
    reasons: list[str] = []

    if not source_text:
        return _result("unknown", "low", ["empty source span"], "context", False, False)

    if _looks_like_reference_list(source_text, normalized):
        return _result(
            "reference_list",
            "high",
            ["reference-list formatting or DOI-heavy citation text"],
            "reject",
            False,
            False,
        )

    if _looks_like_review_table(source_text, normalized):
        return _result(
            "review_table",
            "high",
            ["review or literature-summary table signal"],
            "secondary",
            False,
            False,
        )

    if _looks_like_protocol_guideline(normalized):
        reasons = _protocol_reasons(normalized)
        return _result(
            "protocol_guideline",
            _confidence(reasons, high_at=2),
            reasons or ["validation protocol or control guideline signal"],
            "protocol",
            False,
            True,
        )

    reassignment_reasons = _contamination_reassignment_reasons(normalized)
    if reassignment_reasons:
        return _result(
            "contamination_reassignment_evidence",
            _confidence(reassignment_reasons, high_at=1),
            reassignment_reasons,
            "negative",
            False,
            True,
        )

    contamination_reasons = _contamination_detection_reasons(normalized)
    if contamination_reasons:
        return _result(
            "contamination_detection_evidence",
            _confidence(contamination_reasons, high_at=2),
            contamination_reasons,
            "negative",
            False,
            True,
        )

    figure_caption = _looks_like_figure_caption(source_text, normalized)
    performance_reasons = _performance_reasons(normalized)
    validation_reasons = _validation_reasons(normalized)
    clear_primary_caption = figure_caption and _contains_any(
        normalized,
        ["we measured", "we report", "this work reports", "this study reports", "we produced"],
    )

    if figure_caption and not clear_primary_caption:
        return _result(
            "figure_caption",
            "high",
            ["figure-caption formatting without clear paired primary prose"],
            "context",
            False,
            False,
        )

    if _looks_like_computational_screening(normalized):
        return _result(
            "computational_screening",
            "high",
            ["computational or screening-only evidence signal"],
            "context",
            False,
            False,
        )

    if performance_reasons and validation_reasons:
        return _result(
            "primary_performance_with_validation",
            _confidence([*performance_reasons, *validation_reasons], high_at=3),
            [*performance_reasons, *validation_reasons],
            "performance",
            True,
            True,
        )

    if performance_reasons:
        return _result(
            "primary_performance",
            _confidence(performance_reasons, high_at=2),
            performance_reasons,
            "performance",
            True,
            True,
        )

    background_reasons = _background_reasons(normalized)
    if background_reasons:
        return _result(
            "background_context",
            _confidence(background_reasons, high_at=3),
            background_reasons,
            "context",
            False,
            False,
        )

    return _result("unknown", "low", ["no triage-specific evidence signal"], "context", False, False)


def classify_span_record(span: dict[str, Any]) -> dict[str, Any]:
    """Return a span record with source classification fields attached."""

    record = dict(span)
    text = str(record.get("text") or record.get("source_text") or record.get("source_span") or "")
    classification = classify_source_span(text)
    record.update(classification)
    if "source_text" not in record:
        record["source_text"] = text
    reaction = infer_reaction_family_detailed(
        text=text,
        section_type=str(record.get("section_type") or record.get("source_section") or ""),
        title=str(record.get("title") or record.get("paper_title") or ""),
        abstract=str(record.get("abstract") or record.get("paper_abstract") or ""),
        record=record,
    )
    record.update(reaction)
    record.setdefault("paper_level_reaction_family", "unclear")
    return record


def _result(
    text_class: str,
    confidence: str,
    reasons: list[str],
    recommended_ledger: str,
    allow_field_extraction: bool,
    allow_gold: bool,
) -> dict[str, Any]:
    if text_class not in TEXT_CLASSES:
        raise ValueError(f"Unknown text_class: {text_class}")
    if recommended_ledger not in LEDGERS:
        raise ValueError(f"Unknown recommended_ledger: {recommended_ledger}")
    return {
        "text_class": text_class,
        "confidence": confidence,
        "reasons": reasons,
        "recommended_ledger": recommended_ledger,
        "allow_field_extraction": allow_field_extraction,
        "allow_gold": allow_gold,
    }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _looks_like_reference_list(text: str, normalized: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if normalized in {"references", "reference"} or normalized.startswith(("references ", "# references")):
        return True
    numbered = sum(1 for line in lines if re.match(r"^(?:\[\d+\]|\d+[\).])\s+", line))
    doi_hits = len(re.findall(r"\bdoi\b|10\.\d{4,9}/", normalized))
    citation_year_hits = len(re.findall(r"\b(?:19|20)\d{2}\b", normalized))
    if len(lines) >= 2 and numbered >= max(2, len(lines) // 2):
        return True
    return doi_hits >= 2 and citation_year_hits >= 2 and not _performance_reasons(normalized)


def _looks_like_review_table(text: str, normalized: str) -> bool:
    if _contains_any(normalized, ["review table", "literature summary", "summarized in table", "surveyed reports"]):
        return True
    if "table" in normalized and _contains_any(
        normalized,
        ["reported in previous studies", "previous reports", "literature values", "recent reviews"],
    ):
        return True
    return bool(re.search(r"\btable\s+s?\d+", normalized)) and "review" in normalized


def _contamination_reassignment_reasons(normalized: str) -> list[str]:
    reasons: list[str] = []
    if _contains_any(
        normalized,
        [
            "reassigned",
            "re-attributed",
            "reattributed",
            "false positive",
            "not from n2",
            "originated from contamination",
            "derived from nitrate contamination",
            "derived from nitrite contamination",
        ],
    ):
        reasons.append("claim reassigned away from electrochemical N2-to-NH3")
    if _contains_any(normalized, ["background ammonia accounted for the signal", "ammonia was from impurity"]):
        reasons.append("ammonia signal attributed to background or impurity")
    return reasons


def _contamination_detection_reasons(normalized: str) -> list[str]:
    reasons: list[str] = []
    if _contains_any(
        normalized,
        [
            "nitrate contamination",
            "nitrite contamination",
            "nox contamination",
            "background ammonia",
            "nitrogen impurity",
            "catalyst impurity",
            "adventitious ammonia",
        ],
    ):
        reasons.append("explicit contamination or impurity evidence")
    if _contains_any(normalized, ["impurity analysis"]) or (
        _contains_any(normalized, ["contamination check", "contamination control", "nox screening"])
        and _contains_any(normalized, ["detected", "found", "observed", "present", "positive"])
    ):
        reasons.append("contamination or NOx screening detected a risk")
    if _contains_any(normalized, ["detected nitrate", "detected nitrite", "detected nox"]):
        reasons.append("NOx contaminant detected")
    return reasons


def _looks_like_protocol_guideline(normalized: str) -> bool:
    protocol_words = [
        "protocol",
        "guideline",
        "recommended",
        "should be performed",
        "must be performed",
        "control experiment",
        "blank experiment",
        "calibration curve",
        "standard addition",
    ]
    validation_words = ["15n", "isotope", "blank", "nox", "contamination", "indophenol", "nessler", "nmr"]
    return _contains_any(normalized, protocol_words) and _contains_any(normalized, validation_words)


def _protocol_reasons(normalized: str) -> list[str]:
    reasons: list[str] = []
    if _contains_any(normalized, ["protocol", "guideline", "recommended", "should be performed", "must be performed"]):
        reasons.append("protocol or guideline language")
    if _contains_any(normalized, ["15n", "isotope", "blank", "nox", "contamination"]):
        reasons.append("validation-control requirement language")
    if _contains_any(normalized, ["calibration curve", "standard addition", "indophenol", "nessler", "nmr"]):
        reasons.append("analytical quantification procedure language")
    return reasons


def _looks_like_figure_caption(text: str, normalized: str) -> bool:
    stripped = text.strip()
    return bool(re.match(r"^(?:fig\.?|figure)\s+[a-z0-9.\-:)]", stripped, flags=re.IGNORECASE)) or normalized.startswith(
        ("fig. ", "figure ")
    )


def _looks_like_computational_screening(normalized: str) -> bool:
    return _contains_any(
        normalized,
        [
            "dft",
            "density functional theory",
            "computational screening",
            "free energy diagram",
            "adsorption energy",
            "limiting potential",
            "descriptor",
        ],
    ) and not _contains_any(normalized, ["measured", "experimentally", "faradaic efficiency", "nh3 yield"])


def _performance_reasons(normalized: str) -> list[str]:
    reasons: list[str] = []
    if _contains_any(normalized, ["faradaic efficiency", " fe ", "fe reached", "% fe", "nh3 fe"]):
        reasons.append("reported Faradaic efficiency")
    if _contains_any(normalized, ["nh3 yield", "ammonia yield", "yield rate", "production rate", "produced nh3"]):
        reasons.append("reported ammonia yield or production")
    if _contains_any(normalized, [" ma cm", "current density", " v vs", "potential"]):
        reasons.append("reported electrochemical operating condition")
    if _contains_any(normalized, ["flow cell", "h-cell", "divided cell", "reactor", "gde", "gas diffusion electrode"]):
        reasons.append("reported reactor or electrode configuration")
    if re.search(r"\b\d+(?:\.\d+)?\s*%", normalized) and _contains_any(normalized, ["nh3", "ammonia"]):
        reasons.append("numeric ammonia performance percentage")
    return reasons


def _validation_reasons(normalized: str) -> list[str]:
    reasons: list[str] = []
    if _contains_any(normalized, ["15n", "15n2", "15nh4", "isotope labeling", "isotopic"]):
        reasons.append("explicit isotope validation")
    if _contains_any(normalized, ["blank control", "ar blank", "n2-free", "control experiment"]):
        reasons.append("explicit blank/control experiment")
    if _contains_any(normalized, ["nox screening", "contamination control", "background ammonia", "nitrate contamination"]):
        reasons.append("explicit contamination or NOx control")
    return reasons


def _background_reasons(normalized: str) -> list[str]:
    reasons: list[str] = []
    if _contains_any(normalized, ["nitrogen reduction reaction", "ammonia synthesis", "electrocatalytic"]):
        reasons.append("general electrochemical ammonia context")
    if _contains_any(normalized, ["has attracted", "important", "promising", "challenge", "review"]):
        reasons.append("background or motivation language")
    return reasons


def _confidence(reasons: list[str], high_at: int = 2) -> str:
    if len(reasons) >= high_at:
        return "high"
    if reasons:
        return "medium"
    return "low"
