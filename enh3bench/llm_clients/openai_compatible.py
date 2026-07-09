"""OpenAI-compatible chat-completions client using only the Python standard library."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from enh3bench.llm_clients.base import BaseLLMClient, LLMClientError


class OpenAICompatibleClient(BaseLLMClient):
    """Minimal OpenAI-compatible chat completions client."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int = 60,
    ) -> None:
        self.api_key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("USTC_API_KEY")
        self.base_url = base_url or os.environ.get("LLM_BASE_URL") or os.environ.get("USTC_BASE_URL")
        self.model = model or os.environ.get("LLM_MODEL") or os.environ.get("USTC_MODEL")
        self.timeout = int(timeout)
        self.endpoint = normalize_chat_completions_endpoint(self.base_url) if self.base_url else None

    def verify_available(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "missing API key; set LLM_API_KEY or USTC_API_KEY"
        if not self.base_url:
            return False, "missing base URL; set LLM_BASE_URL or USTC_BASE_URL"
        if not self.model:
            return False, "missing model; set LLM_MODEL or USTC_MODEL or pass --model"
        return True, "available"

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0,
        max_tokens: int = 1200,
        response_format: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> str:
        available, message = self.verify_available()
        if not available:
            raise LLMClientError(message)
        endpoint = self.endpoint
        if not endpoint:
            raise LLMClientError("missing chat-completions endpoint")

        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = _safe_error_body(exc)
            raise LLMClientError(f"HTTP {exc.code} from chat completions endpoint: {body}") from exc
        except urllib.error.URLError as exc:
            raise LLMClientError(f"chat completions request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMClientError("chat completions request timed out") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMClientError(f"chat completions response was not valid JSON: {raw[:500]}") from exc
        return extract_chat_completion_content(data)


def extract_chat_completion_content(response_json: dict[str, Any]) -> str:
    """Extract text from common OpenAI-compatible chat-completions response shapes."""

    if not isinstance(response_json, dict):
        raise LLMClientError(
            "chat completions response did not contain usable text content: "
            f"{_sanitized_response_preview(response_json)}"
        )

    choices = response_json.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0]
        if isinstance(choice, dict):
            message = choice.get("message")
            if isinstance(message, dict):
                if "content" in message:
                    content_text = _content_to_text(message.get("content"))
                    if content_text:
                        return content_text
                for key in ("reasoning_content", "response_content", "output_text", "text", "refusal"):
                    fallback_text = _content_to_text(message.get(key))
                    if fallback_text:
                        return fallback_text

            choice_text = _content_to_text(choice.get("text"))
            if choice_text:
                return choice_text

    output_text = _content_to_text(response_json.get("output_text"))
    if output_text:
        return output_text

    raise LLMClientError(
        "chat completions response did not contain usable text content: "
        f"{_sanitized_response_preview(response_json)}"
    )


def normalize_chat_completions_endpoint(base_url: str) -> str:
    """Normalize a base URL to the OpenAI-compatible chat-completions endpoint."""

    url = str(base_url or "").strip().rstrip("/")
    if url.endswith("/v1/chat/completions"):
        return url
    if url.endswith("/v1"):
        return f"{url}/chat/completions"
    return f"{url}/v1/chat/completions"


def _safe_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    if not body:
        return "no response body"
    return body[:500]


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    if isinstance(content, list):
        parts = [_content_to_text(part) for part in content]
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        for key in ("text", "content", "value"):
            value = content.get(key)
            if isinstance(value, str):
                return value
        return json.dumps(content, ensure_ascii=False, default=str)
    return ""


def _sanitized_response_preview(value: Any) -> str:
    sanitized = _sanitize_for_preview(value)
    try:
        preview = json.dumps(sanitized, ensure_ascii=False, default=str)
    except TypeError:
        preview = str(sanitized)
    return preview[:500]


def _sanitize_for_preview(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).casefold()
            if lowered in {"authorization", "api_key", "apikey", "key", "token", "headers"}:
                safe[key] = "[redacted]"
            else:
                safe[key] = _sanitize_for_preview(item)
        return safe
    if isinstance(value, list):
        return [_sanitize_for_preview(item) for item in value]
    return value
