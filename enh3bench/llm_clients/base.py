"""Base client interface for optional LLM verification."""

from __future__ import annotations

import re
from typing import Any


class LLMClientError(Exception):
    """Raised for optional LLM client configuration or request failures."""


class BaseLLMClient:
    """Small interface shared by real and mock LLM clients."""

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0,
        max_tokens: int = 1200,
        response_format: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> str:
        raise NotImplementedError

    def verify_available(self) -> tuple[bool, str]:
        return True, "available"


def sanitize_model_name_for_path(model: str) -> str:
    """Return a filesystem-safe but readable model-name segment."""

    text = str(model or "").strip()
    sanitized = re.sub(r'[/\\:*?"<>|\s]+', "_", text)
    sanitized = re.sub(r"_+", "_", sanitized).strip("._")
    return sanitized or "model"
