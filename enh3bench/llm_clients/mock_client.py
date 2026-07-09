"""Deterministic mock LLM client for tests and offline smoke runs."""

from __future__ import annotations

import json
import re
from typing import Any

from enh3bench.llm_clients.base import BaseLLMClient


class MockLLMClient(BaseLLMClient):
    """Return strict JSON without making network calls."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0,
        max_tokens: int = 1200,
        response_format: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> str:
        user_text = _last_user_message(messages)
        source_text, provenance_type, text_class = _extract_prompt_context(user_text)
        normalized = source_text.casefold()
        provenance = provenance_type.casefold()

        if "reference" in normalized or "bibliography" in normalized or provenance in {"reference", "bibliography"}:
            boundary = "unsupported_or_secondary"
            text_class_out = "unsupported_claim"
            reasoning = "The source appears to be reference or bibliography text, not primary experimental evidence."
            field_default = "secondary_only"
            required_controls = ["primary body text"]
            overclaim = ["low_trust_provenance"]
        elif _contains_isotope(source_text) and _contains_fe(source_text):
            boundary = "reactor_legibility" if re.search(r"\b(flow|hor|hydrogen oxidation)\b", normalized) else "cell_metric"
            text_class_out = text_class or "primary_performance_with_validation"
            reasoning = "The source explicitly mentions 15N/isotope evidence and FE; reactor terms raise the boundary only when present."
            field_default = "missing"
            required_controls = []
            overclaim = []
        else:
            boundary = "unsupported_or_secondary"
            text_class_out = text_class or "unsupported_claim"
            reasoning = "The source text is insufficient for verified BoundaryLedger escalation."
            field_default = "missing"
            required_controls = ["more explicit source evidence"]
            overclaim = ["insufficient_explicit_support"]

        field_support = {
            "FE": "explicit" if _contains_fe(source_text) else field_default,
            "NH3_yield": "explicit" if _contains_any(normalized, ["nh3 yield", "ammonia yield", "yield rate", "production rate"]) else field_default,
            "EE": "explicit" if "energy efficiency" in normalized else field_default,
            "current_density": "explicit" if "current density" in normalized or "ma cm" in normalized else field_default,
            "potential_or_voltage": "explicit" if _contains_any(normalized, ["potential", "voltage", " v vs", "vvs"]) else field_default,
            "runtime": "explicit" if _contains_any(normalized, ["runtime", "stability", "hours"]) else field_default,
            "isotope_15N": "explicit" if _contains_isotope(source_text) else field_default,
            "blank_control": "explicit" if "blank" in normalized else field_default,
            "NOx_control": "explicit" if "nox" in normalized or "nitrate" in normalized or "nitrite" in normalized else field_default,
            "reactor_type": "explicit" if _contains_any(normalized, ["reactor", "cell", "flow"]) else field_default,
            "HOR": "explicit" if "hor" in normalized or "hydrogen oxidation" in normalized else field_default,
            "product_state": "explicit" if _contains_any(normalized, ["gas-phase", "aqueous", "nh4+", "outlet"]) else field_default,
            "capture_route": "explicit" if _contains_any(normalized, ["capture", "acid trap", "scrubber"]) else field_default,
            "solvent_inventory": "explicit" if _contains_any(normalized, ["solvent", "electrolyte volume"]) else field_default,
            "failure_mode": "explicit" if _contains_any(normalized, ["failure", "flooding", "wetting"]) else field_default,
        }

        response = {
            "text_class": text_class_out,
            "field_support": field_support,
            "maximum_supported_boundary": boundary,
            "missing_boundary_fields": [key for key, value in field_support.items() if value == "missing"],
            "hidden_tax": ["measurement_matrix_tax"] if field_support["FE"] == "explicit" and field_support["NH3_yield"] != "explicit" else [],
            "required_controls": required_controls,
            "overclaim_risk": overclaim,
            "recommended_experiment": "Pair the rule result with explicit primary source evidence before gold use.",
            "reasoning": reasoning,
        }
        return json.dumps(response, ensure_ascii=True, sort_keys=True)


def _last_user_message(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


def _extract_prompt_context(user_text: str) -> tuple[str, str, str]:
    match = re.search(r"Record to verify:\s*(\{.*?\})\s*Return strict JSON", user_text, flags=re.DOTALL)
    if not match:
        return user_text, "", ""
    try:
        record = json.loads(match.group(1))
    except json.JSONDecodeError:
        return user_text, "", ""
    return (
        str(record.get("source_text") or ""),
        str(record.get("provenance_type") or ""),
        str(record.get("text_class") or ""),
    )


def _contains_fe(text: str) -> bool:
    normalized = text.casefold()
    return "faradaic efficiency" in normalized or bool(re.search(r"\bfe\b", normalized))


def _contains_isotope(text: str) -> bool:
    normalized = text.casefold()
    return bool(re.search(r"\b15\s*n(?:2|h3|h4)?\b", normalized)) or "isotope" in normalized


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)
