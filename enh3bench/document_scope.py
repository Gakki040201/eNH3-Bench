"""Document genre and span-claim scope semantics for Stage B eligibility."""

from __future__ import annotations

import re
from typing import Any, Iterable


SEMANTIC_ELIGIBILITY_SCHEMA_VERSION = "0.14-stage-b"

PRIMARY_RESEARCH_GENRE = "primary_research"
REVIEW_GENRE = "review"
PERSPECTIVE_GENRE = "perspective"
PROTOCOL_OR_GUIDELINE_GENRE = "protocol_or_guideline"
COMPUTATIONAL_STUDY_GENRE = "computational_study"
PROCESS_OR_TEA_GENRE = "process_or_tea"
DATASET_OR_METADATA_GENRE = "dataset_or_metadata"
MIXED_GENRE = "mixed"
UNCLEAR_GENRE = "unclear"
DOCUMENT_GENRES = {
    PRIMARY_RESEARCH_GENRE,
    REVIEW_GENRE,
    PERSPECTIVE_GENRE,
    PROTOCOL_OR_GUIDELINE_GENRE,
    COMPUTATIONAL_STUDY_GENRE,
    PROCESS_OR_TEA_GENRE,
    DATASET_OR_METADATA_GENRE,
    MIXED_GENRE,
    UNCLEAR_GENRE,
}

TARGET_DOCUMENT_SCOPE = "target_document"
EXTERNAL_DOCUMENT_SCOPE = "external_or_cited_work"
BACKGROUND_DOCUMENT_SCOPE = "background_or_review"
SECONDARY_DOCUMENT_SCOPE = "secondary_context"
UNCLEAR_DOCUMENT_SCOPE = "unclear"
SPAN_CLAIM_SCOPES = {
    TARGET_DOCUMENT_SCOPE,
    EXTERNAL_DOCUMENT_SCOPE,
    BACKGROUND_DOCUMENT_SCOPE,
    SECONDARY_DOCUMENT_SCOPE,
    UNCLEAR_DOCUMENT_SCOPE,
}

PRIMARY_SECTIONS = {
    "abstract",
    "methods",
    "experimental",
    "results",
    "results_and_discussion",
    "discussion",
    "conclusion",
    "conclusions",
    "supplementary",
}
LOW_TRUST_PROVENANCE = {
    "reference", "bibliography", "figure_caption", "scheme_caption", "review_table",
}
LOW_TRUST_TEXT_CLASSES = {
    "reference_list", "figure_caption", "scheme_caption", "review_table", "background_context",
}

_TARGET_CUE = re.compile(
    r"\b(?:in this (?:work|study|paper)|the present (?:work|study)|we (?:report(?:ed)?|show(?:ed)?|"
    r"demonstrat(?:e|ed)|find|found|observ(?:e|ed)|develop(?:ed)?|prepar(?:e|ed)|measur(?:e|ed)|"
    r"quantif(?:y|ied)|systematically assess(?:ed)?|recommend(?:ed)?|propos(?:e|ed)|present(?:ed)?|"
    r"discuss(?:ed)?|conclud(?:e|ed)|suggest(?:ed)?|aim(?:ed)?|offer(?:ed)?)|"
    r"our (?:work|study|results?|measurements?|"
    r"experiments?|catalyst|cell)|here(?:in)? we)\b",
    re.IGNORECASE,
)
_EXTERNAL_VERBS = (
    "synthesized", "prepared", "designed", "fabricated", "constructed", "investigated",
    "evaluated", "studied", "tested", "introduced", "reported", "demonstrated", "showed",
    "found", "developed", "achieved", "observed", "proposed",
)
_EXTERNAL_ATTRIBUTION = re.compile(
    r"(?:\b(?:according to|as reported by|reported by|previously reported by)\b|"
    r"\b(?:[A-Z][A-Za-z'\u2019.-]*(?:\s+[A-Z][A-Za-z'\u2019.-]*)?\s+"
    r"(?:and\s+(?:co[- ]?workers|colleagues)|et\s+al\.?)"
    r"(?:\s*\[[^\]]+\])?(?:,\s*in\s+\d{4},)?\s+(?:have\s+|has\s+)?|"
    r"previous\s+(?:authors?|studies|work|reports?)\s+|"
    r"other\s+(?:authors?|groups?|studies)|the\s+literature)"
    r"[,;:]?\s*(?:" + "|".join(_EXTERNAL_VERBS) + r")\b|"
    r"\breported\s+in\s+(?:ref(?:erence)?\.?|citation)\s*\[?\d+\]?|"
    r"\b(?:the\s+)?(?:catalyst|material|electrode|method|system)\s+described\s+in\s+"
    r"(?:ref(?:erence)?\.?|citation)\s*\[?\d+\]?)",
    re.IGNORECASE,
)
_BACKGROUND_CUE = re.compile(
    r"\b(?:many|several|numerous|recent|earlier|prior) (?:studies|reports|works?)\b|"
    r"\b(?:it has|have) been (?:reported|shown|demonstrated)\b|"
    r"\bresearchers (?:have )?(?:reported|developed|focused|shown)\b",
    re.IGNORECASE,
)

_REVIEW_CUE = re.compile(
    r"\b(?:review|current status|perspectives|recent advances|progress|overview|"
    r"state of the art|critical review)\b",
    re.IGNORECASE,
)
_PERSPECTIVE_CUE = re.compile(
    r"\b(?:perspective|viewpoint|commentary|roadmap|outlook)\b",
    re.IGNORECASE,
)
_PRIMARY_ABSTRACT_CUE = re.compile(
    r"\b(?:here(?:in)? we (?:report|demonstrate)|in this (?:work|study),? we|"
    r"we (?:report|demonstrate) here)\b",
    re.IGNORECASE,
)
_EXPERIMENTAL_RESULT_CUE = re.compile(
    r"\b(?:sample|specimen|catalyst|electrode|experiment(?:al)?|measured|synthesized|prepared|"
    r"faradaic efficiency|yield rate|current density|the results? (?:show|demonstrate))\b",
    re.IGNORECASE,
)


def assess_document_genre(record: dict[str, Any]) -> dict[str, Any]:
    """Classify a document-level genre from aggregated document inputs."""

    explicit = str(record.get("document_genre") or "").strip().casefold()
    if explicit in DOCUMENT_GENRES:
        return _genre_result(explicit, "high", ["explicit_document_genre"])

    article_type = _first_text(record, "article_type", "paper_article_type", "document_article_type")
    title = _first_text(record, "paper_title", "title", "document_title")
    abstract = _first_text(record, "paper_abstract", "abstract", "document_abstract")
    headings = _text_values(record.get("document_headings") or record.get("headings"))
    front_matter = " ".join(_text_values(
        record.get("front_matter_metadata_text") or record.get("front_matter")
        or record.get("front_matter_signals")
    ))
    body = _first_text(record, "document_body_text", "full_body_text", "body_text")
    article_normalized = " ".join(article_type.casefold().replace("_", " ").split())
    title_abstract = " ".join(value for value in (title, abstract, front_matter) if value)
    heading_text = " ".join(headings)
    combined = " ".join(value for value in (title_abstract, heading_text, body) if value)
    target_frequency = _integer_value(record.get("target_study_language_frequency"))
    if target_frequency is None:
        target_frequency = len(_TARGET_CUE.findall(" ".join(value for value in (abstract, body) if value)))

    article_genre = _article_type_genre(article_normalized)
    if article_genre:
        return _genre_result(article_genre, "high", [f"article_type:{article_genre}"])

    scores: dict[str, int] = {genre: 0 for genre in DOCUMENT_GENRES if genre not in {MIXED_GENRE, UNCLEAR_GENRE}}
    signals: dict[str, list[str]] = {genre: [] for genre in scores}

    if _REVIEW_CUE.search(title):
        scores[REVIEW_GENRE] += 6
        signals[REVIEW_GENRE].append("review_title_signal")
    if _PERSPECTIVE_CUE.search(title) and not re.search(r"\bperspectives\b", title, re.IGNORECASE):
        scores[PERSPECTIVE_GENRE] += 6
        signals[PERSPECTIVE_GENRE].append("perspective_title_signal")
    if _REVIEW_CUE.search(abstract):
        scores[REVIEW_GENRE] += 3
        signals[REVIEW_GENRE].append("review_abstract_signal")
    if _PERSPECTIVE_CUE.search(abstract):
        scores[PERSPECTIVE_GENRE] += 3
        signals[PERSPECTIVE_GENRE].append("perspective_abstract_signal")
    if _REVIEW_CUE.search(heading_text):
        scores[REVIEW_GENRE] += 4
        signals[REVIEW_GENRE].append("review_heading_signal")
    if _PERSPECTIVE_CUE.search(heading_text) and not re.search(r"\bperspectives\b", heading_text, re.IGNORECASE):
        scores[PERSPECTIVE_GENRE] += 4
        signals[PERSPECTIVE_GENRE].append("perspective_heading_signal")
    if _PRIMARY_ABSTRACT_CUE.search(abstract):
        scores[PRIMARY_RESEARCH_GENRE] += 6
        signals[PRIMARY_RESEARCH_GENRE].append("primary_abstract_current_study_signal")

    normalized_headings = {" ".join(value.casefold().replace("_", " ").split()) for value in headings}
    has_methods = any(value in {"methods", "materials and methods", "experimental", "methodology"}
                      for value in normalized_headings)
    has_results = any(value in {"results", "results and discussion", "discussion", "findings"}
                      for value in normalized_headings)
    if has_methods and has_results:
        scores[PRIMARY_RESEARCH_GENRE] += 5
        signals[PRIMARY_RESEARCH_GENRE].append("methods_and_results_structure")
    elif has_results and target_frequency > 0:
        scores[PRIMARY_RESEARCH_GENRE] += 3
        signals[PRIMARY_RESEARCH_GENRE].append("results_with_current_study_language")
    elif has_results:
        scores[PRIMARY_RESEARCH_GENRE] += 2
        signals[PRIMARY_RESEARCH_GENRE].append("explicit_results_structure")
    if target_frequency > 0 and _EXPERIMENTAL_RESULT_CUE.search(combined):
        scores[PRIMARY_RESEARCH_GENRE] += 3
        signals[PRIMARY_RESEARCH_GENRE].append(f"target_study_language_frequency:{target_frequency}")

    _score_special_genre(scores, signals, PROTOCOL_OR_GUIDELINE_GENRE, combined,
                         r"\b(?:protocol|guideline|standard operating procedure|best practice)\b")
    _score_special_genre(scores, signals, COMPUTATIONAL_STUDY_GENRE, combined,
                         r"\b(?:computational study|density functional theory|\bdft\b|finite element analysis|simulation study)\b")
    _score_special_genre(scores, signals, PROCESS_OR_TEA_GENRE, combined,
                         r"\b(?:techno[- ]economic|life cycle assessment|process systems?|plant[- ]level|process design)\b")
    _score_special_genre(scores, signals, DATASET_OR_METADATA_GENRE, combined,
                         r"\b(?:data descriptor|benchmark dataset|metadata record|dataset paper)\b")

    top_score = max(scores.values(), default=0)
    if top_score <= 0:
        return _genre_result(UNCLEAR_GENRE, "low", ["no_document_genre_signal"])
    winners = sorted(genre for genre, score in scores.items() if score == top_score)
    if len(winners) > 1:
        mixed_signals = [signal for genre in winners for signal in signals[genre]]
        return _genre_result(MIXED_GENRE, "medium", ["tied_document_genre_signals", *mixed_signals])
    genre = winners[0]
    confidence = "high" if top_score >= 5 else "medium" if top_score >= 3 else "low"
    return _genre_result(genre, confidence, signals[genre])


def build_document_genre_context(
    document: dict[str, Any],
    records: Iterable[dict[str, Any]],
    sections: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Aggregate the required genre inputs once for one document."""

    records_list = list(records)
    sections_list = list(sections)
    body = str(document.get("full_body_text") or document.get("body_text") or "")
    document_id = str(document.get("document_id") or "")
    title = _first_record_text(records_list, "paper_title", "title")
    if not title:
        title = next((
            str(section.get("heading_text") or "").strip()
            for section in sections_list
            if str(section.get("section_type") or "") == "title"
            and str(section.get("heading_text") or "").strip()
        ), "")
    if not title:
        title = document_id.replace("_", " ")
    abstract = _first_record_text(records_list, "paper_abstract", "abstract")
    if not abstract:
        abstract_section = next((
            section for section in sections_list
            if str(section.get("section_type") or "") == "abstract"
        ), None)
        if abstract_section:
            start = int(abstract_section.get("section_start_offset") or 0)
            end = int(abstract_section.get("section_end_offset") or len(body))
            abstract = body[start:end]
    return {
        "document_id": document_id,
        "document_genre": _first_record_text(records_list, "document_genre"),
        "paper_title": title,
        "paper_abstract": abstract,
        "article_type": _first_record_text(records_list, "article_type", "paper_article_type"),
        "front_matter_signals": list(document.get("front_matter_signals") or []),
        "document_headings": [str(section.get("heading_text") or "") for section in sections_list],
        "target_study_language_frequency": len(_TARGET_CUE.findall(body)),
        "document_body_text": body,
    }


def assess_span_claim_scope(record: dict[str, Any]) -> dict[str, Any]:
    """Classify whether one exact span belongs to the target or an external claim."""

    explicit = str(record.get("span_claim_scope") or record.get("document_scope") or "").strip()
    if explicit in SPAN_CLAIM_SCOPES:
        return _scope_result(explicit, "high", ["explicit_span_claim_scope"])

    text = _record_text(record)
    provenance = str(record.get("provenance_type") or "unknown").strip().casefold()
    text_class = str(record.get("text_class") or "unknown").strip().casefold()
    section = _section_type(record)

    if provenance in LOW_TRUST_PROVENANCE or text_class in LOW_TRUST_TEXT_CLASSES:
        return _scope_result(SECONDARY_DOCUMENT_SCOPE, "high", ["secondary_context_provenance"])
    if has_external_attribution(text):
        return _scope_result(EXTERNAL_DOCUMENT_SCOPE, "high", ["explicit_external_attribution"])
    if _BACKGROUND_CUE.search(text):
        return _scope_result(BACKGROUND_DOCUMENT_SCOPE, "high", ["background_or_literature_synthesis"])
    if _TARGET_CUE.search(text):
        return _scope_result(TARGET_DOCUMENT_SCOPE, "high", ["explicit_current_work_cue"])
    if section in PRIMARY_SECTIONS or provenance in PRIMARY_SECTIONS:
        return _scope_result(
            TARGET_DOCUMENT_SCOPE,
            "medium",
            [f"current_paper_section:{section if section != 'unknown' else provenance}"],
        )
    if section in {"introduction", "background", "related_work", "literature_review"}:
        return _scope_result(UNCLEAR_DOCUMENT_SCOPE, "low", [f"unowned_background_section:{section}"])
    if provenance == "body" and section in {"unknown", "title"}:
        return _scope_result(TARGET_DOCUMENT_SCOPE, "medium", [f"current_paper_{section}_body"])
    return _scope_result(UNCLEAR_DOCUMENT_SCOPE, "low", ["no_span_claim_scope_signal"])


def assess_document_scope(record: dict[str, Any]) -> dict[str, Any]:
    """Backward-compatible alias for the independent span-claim scope assessment."""

    result = assess_span_claim_scope(record)
    return {
        **result,
        "document_scope": result["span_claim_scope"],
        "document_scope_confidence": result["span_claim_scope_confidence"],
        "document_scope_signals": result["span_claim_scope_signals"],
        "document_scope_primary_applicable": result["span_claim_scope_primary_applicable"],
    }


def document_scope_allows_primary(record_or_assessment: dict[str, Any]) -> bool:
    """Return whether the span scope (not document genre) permits primary use."""

    if "span_claim_scope_primary_applicable" in record_or_assessment:
        return bool(record_or_assessment.get("span_claim_scope_primary_applicable"))
    if "document_scope_primary_applicable" in record_or_assessment:
        return bool(record_or_assessment.get("document_scope_primary_applicable"))
    return assess_span_claim_scope(record_or_assessment)["span_claim_scope_primary_applicable"]


def classify_document_scope(record: dict[str, Any]) -> dict[str, Any]:
    """Compatibility-friendly classifier name retained for v0.13 callers."""

    return assess_document_scope(record)


def has_external_attribution(text: str) -> bool:
    """Return true for explicit cited-author action constructions."""

    return bool(_EXTERNAL_ATTRIBUTION.search(str(text or "")))


def _genre_result(genre: str, confidence: str, signals: list[str]) -> dict[str, Any]:
    return {
        "semantic_eligibility_schema_version": SEMANTIC_ELIGIBILITY_SCHEMA_VERSION,
        "document_genre": genre,
        "document_genre_confidence": confidence,
        "document_genre_signals": signals,
        "document_genre_primary_applicable": genre == PRIMARY_RESEARCH_GENRE,
    }


def _scope_result(scope: str, confidence: str, signals: list[str]) -> dict[str, Any]:
    return {
        "semantic_eligibility_schema_version": SEMANTIC_ELIGIBILITY_SCHEMA_VERSION,
        "span_claim_scope": scope,
        "span_claim_scope_confidence": confidence,
        "span_claim_scope_signals": signals,
        "span_claim_scope_primary_applicable": scope == TARGET_DOCUMENT_SCOPE,
    }


def _article_type_genre(article_type: str) -> str:
    if not article_type:
        return ""
    if re.search(r"\b(?:review|systematic review|meta analysis)\b", article_type):
        return REVIEW_GENRE
    if re.search(r"\b(?:perspective|viewpoint|commentary|roadmap|outlook)\b", article_type):
        return PERSPECTIVE_GENRE
    if re.search(r"\b(?:protocol|guideline|standard)\b", article_type):
        return PROTOCOL_OR_GUIDELINE_GENRE
    if re.search(r"\b(?:computational|theoretical|simulation|modelling|modeling)\b", article_type):
        return COMPUTATIONAL_STUDY_GENRE
    if re.search(r"\b(?:techno economic|process|life cycle|tea)\b", article_type):
        return PROCESS_OR_TEA_GENRE
    if re.search(r"\b(?:dataset|data descriptor|metadata)\b", article_type):
        return DATASET_OR_METADATA_GENRE
    if re.search(r"\b(?:primary research|original research article|original article)\b", article_type):
        return PRIMARY_RESEARCH_GENRE
    return ""


def _score_special_genre(
    scores: dict[str, int], signals: dict[str, list[str]], genre: str, text: str, pattern: str
) -> None:
    if re.search(pattern, text, re.IGNORECASE):
        scores[genre] += 2
        signals[genre].append(f"{genre}_content_signal")


def _section_type(record: dict[str, Any]) -> str:
    for key in (
        "effective_section_type", "target_effective_section_type", "section_type",
        "target_section_type", "direct_section_type", "target_direct_section_type",
    ):
        value = str(record.get(key) or "").strip().casefold().replace(" ", "_")
        if value and value != "unknown":
            return value
    return "unknown"


def _record_text(record: dict[str, Any]) -> str:
    return _first_text(record, "source_text", "target_text", "text", "source_span")


def _first_text(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(record.get(key) or "").strip()
        if value:
            return value
    return ""


def _first_record_text(records: list[dict[str, Any]], *keys: str) -> str:
    for record in records:
        value = _first_text(record, *keys)
        if value:
            return value
    return ""


def _text_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _integer_value(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
