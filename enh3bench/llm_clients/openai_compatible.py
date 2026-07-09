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
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMClientError("chat completions response did not contain choices[0].message.content") from exc
        if not isinstance(content, str):
            raise LLMClientError("chat completions response content was not a string")
        return content


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
