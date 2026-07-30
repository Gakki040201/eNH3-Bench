"""Local M017 single-case web demonstration.

This module is intentionally separate from the M016 benchmark execution path.  Importing it,
browsing cases, running fixtures, and serving health/configuration routes never read a
credential or contact a provider.  A credential is read only inside an explicitly requested
live preflight or live run.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import math
import os
from pathlib import Path
import re
import threading
import time
from typing import Any, Callable, Protocol
from urllib.parse import parse_qs, unquote, urlparse
import uuid

import requests

from enh3bench.e2e_eval_schema import canonical_json
from enh3bench.provider_execution import (
    USTC_LLM_DEEPSEEK_V4_PRO_PROFILE,
    USTC_LLM_GATEWAY_ENDPOINT,
    _load_development_contract,
)


LOGGER = logging.getLogger(__name__)

DEMO_VERSION = "M017-D0-D1-D2"
DEMO_RUN_SCHEMA_VERSION = "0.17-demo-run.1"
DEMO_FIXTURE_SCHEMA_VERSION = "0.17-demo-fixtures.1"
DEMO_BATCH_SCHEMA_VERSION = "0.17-demo-batch.1"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_PILOT_ROOT = Path(r"F:\eNH3_Bench_API\v016_b1b0")
DEFAULT_GENERATION_RUN_NAME = "enrr_generation_pilot_v016_b1b0_20260722"
DEFAULT_DEMO_ROOT = Path(r"F:\eNH3_Bench_API\v017_demo_runtime")
DEFAULT_MODEL_ID = "deepseek-v4-pro"
DEFAULT_TIMEOUT_SECONDS = 900.0
DEFAULT_MAX_OUTPUT_TOKENS = 4096
USTC_MODELS_ENDPOINT = "https://api.llm.ustc.edu.cn/v1/models"
API_KEY_ENVIRONMENT_VARIABLE = "ENH3BENCH_API_KEY"
REQUEST_BODY_SIZE_LIMIT = 16 * 1024
FIXTURE_WARNING = "DEMO_FIXTURE_NOT_MODEL_OUTPUT"
FIXTURE_MESSAGE = (
    "Fixture 已验证案例加载、异步执行、结果持久化、浏览器轮询和界面渲染的完整链路。"
    "此内容不是模型生成的科学结论。"
)

EXPECTED_CASE_IDS = (
    "EC16_CEEE6E048F7B34D28600",
    "EC16_019B2E986566533635D0",
    "EC16_F1CE2281BF67967C6F5F",
    "EC16_EB62B436C9FD7F8D1242",
    "EC16_47CBB413B6F7B9E4FE62",
    "EC16_7263EBEC21D9DF523A7D",
    "EC16_83242FA9E17F52D12567",
)

RUN_STATES = frozenset({
    "queued", "running", "succeeded_structured", "succeeded_unstructured", "failed",
})
TERMINAL_RUN_STATES = frozenset({"succeeded_structured", "succeeded_unstructured", "failed"})
BATCH_STATES = frozenset({"queued", "running", "completed", "completed_with_failures", "failed"})
TERMINAL_BATCH_STATES = frozenset({"completed", "completed_with_failures", "failed"})
PARSER_LEVELS = frozenset({"strict_json", "fenced_json", "extracted_json", "unstructured_text"})
DEMO_RUN_FIELDS = frozenset({
    "schema_version", "run_id", "case_id", "paper_id", "task_type", "mode", "status",
    "provider", "requested_model", "reported_model", "created_at_utc", "started_at_utc",
    "completed_at_utc", "latency_seconds", "timeout_seconds", "max_output_tokens",
    "request_sha256", "http_status", "provider_response_id", "finish_reason", "usage",
    "parse_level", "structured_output", "answer_text", "citations", "warnings",
    "safe_error_code", "safe_error_message",
})
_RUN_ID = re.compile(r"^DR17_[A-F0-9]{20}$")
_BATCH_ID = re.compile(r"^DB17_[A-F0-9]{20}$")
_AUTHORIZATION_TEXT = re.compile(r"(?i)authorization\s*:\s*bearer\s+\S+")
_BEARER_TEXT = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{8,}")
_WINDOWS_USER_PATH = re.compile(r"(?i)[A-Z]:[\\/]Users[\\/][^\\/\s]+")
_FENCED_JSON = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.IGNORECASE | re.DOTALL)
_DISCARDED_KEYS = frozenset({
    "authorization", "authorization_header", "headers", "request_headers", "api_key",
    "credential", "credential_hash", "reasoning_content", "hidden_reasoning", "chain_of_thought",
})
DEMO_BATCH_FIELDS = frozenset({
    "schema_version", "batch_id", "mode", "status", "case_ids", "created_at_utc",
    "started_at_utc", "completed_at_utc", "latency_seconds", "current_case_index",
    "current_case_id", "completed_case_count", "succeeded_case_count", "failed_case_count",
    "run_ids", "items", "aggregate_usage", "aggregate_child_latency_seconds", "warnings",
    "safe_error_code", "safe_error_message", "report_filename",
})
BATCH_ITEM_FIELDS = frozenset({
    "case_number", "case_id", "paper_id", "task_type", "run_id", "status", "parse_level",
    "latency_seconds", "prompt_tokens", "completion_tokens", "total_tokens", "safe_error_code",
})


class DemoConfigurationError(ValueError):
    """Raised when the local demo cannot start safely."""


class DemoSafeError(RuntimeError):
    """A provider or demo failure with browser-safe metadata."""

    def __init__(self, code: str, message: str, *, http_status: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.safe_message = message
        self.http_status = http_status


class HTTPClient(Protocol):
    def get(self, url: str, **kwargs: Any) -> Any: ...
    def post(self, url: str, **kwargs: Any) -> Any: ...


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _replace_atomic_with_sharing_retry(source: Path, target: Path) -> None:
    """Preserve atomic replace while tolerating brief Windows file-sharing locks."""

    for attempt in range(10):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.02)


def _validated_endpoint(endpoint: str) -> str:
    try:
        parsed = urlparse(endpoint)
    except ValueError as exc:
        raise DemoConfigurationError("demo_endpoint_invalid") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise DemoConfigurationError("demo_endpoint_requires_https")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise DemoConfigurationError("demo_endpoint_contains_unsafe_components")
    if parsed.path.rstrip("/") != "/v1/chat/completions":
        raise DemoConfigurationError("demo_endpoint_path_invalid")
    return endpoint.rstrip("/")


def safe_endpoint_label(endpoint: str) -> str:
    parsed = urlparse(_validated_endpoint(endpoint))
    port = f":{parsed.port}" if parsed.port and parsed.port != 443 else ""
    return f"https://{parsed.hostname}{port}{parsed.path}"


@dataclass(frozen=True)
class DemoConfig:
    pilot_root: Path = DEFAULT_PILOT_ROOT
    generation_run_name: str = DEFAULT_GENERATION_RUN_NAME
    demo_root: Path = DEFAULT_DEMO_ROOT
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    endpoint: str = USTC_LLM_GATEWAY_ENDPOINT
    model_id: str = DEFAULT_MODEL_ID
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    live_enabled: bool = False
    repository_root: Path | None = None

    def validate(self) -> None:
        if not isinstance(self.host, str) or not self.host.strip():
            raise DemoConfigurationError("demo_host_invalid")
        if type(self.port) is not int or not 0 <= self.port <= 65535:
            raise DemoConfigurationError("demo_port_invalid")
        _validated_endpoint(self.endpoint)
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise DemoConfigurationError("demo_model_id_invalid")
        if (
            type(self.timeout_seconds) not in {int, float}
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise DemoConfigurationError("demo_timeout_invalid")
        if type(self.max_output_tokens) is not int or self.max_output_tokens <= 0:
            raise DemoConfigurationError("demo_max_output_tokens_invalid")
        if not isinstance(self.generation_run_name, str) or not self.generation_run_name.strip():
            raise DemoConfigurationError("demo_generation_run_name_invalid")
        repo = (self.repository_root or _repository_root()).resolve()
        demo = self.demo_root.resolve()
        if demo == repo or _is_within(demo, repo):
            raise DemoConfigurationError("demo_root_must_be_outside_repository")


def _read_live_credential(variable: str) -> str | None:
    """Read the live credential.  This function is called only from explicit live operations."""

    return os.environ.get(variable)


def _sanitize_text(value: str, *, secret: str | None = None, repository_root: Path | None = None) -> str:
    text = value
    if secret:
        text = text.replace(secret, "[REDACTED]")
    text = _AUTHORIZATION_TEXT.sub("Authorization: [REDACTED]", text)
    text = _BEARER_TEXT.sub("Bearer [REDACTED]", text)
    text = _WINDOWS_USER_PATH.sub(lambda _: r"C:\Users\[REDACTED_USER]", text)
    if repository_root:
        for rendered in {str(repository_root), repository_root.as_posix()}:
            if rendered:
                text = text.replace(rendered, "[REPOSITORY_PATH_REDACTED]")
    return text


def sanitize_for_record(
    value: Any, *, secret: str | None = None, repository_root: Path | None = None,
) -> Any:
    if isinstance(value, dict):
        return {
            str(key): sanitize_for_record(item, secret=secret, repository_root=repository_root)
            for key, item in value.items()
            if str(key).lower() not in _DISCARDED_KEYS
        }
    if isinstance(value, list):
        return [sanitize_for_record(item, secret=secret, repository_root=repository_root) for item in value]
    if isinstance(value, tuple):
        return [sanitize_for_record(item, secret=secret, repository_root=repository_root) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value, secret=secret, repository_root=repository_root)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _sanitize_text(str(value), secret=secret, repository_root=repository_root)


def _first_balanced_json_object(text: str) -> dict[str, Any] | None:
    for start, character in enumerate(text):
        if character != "{":
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            current = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[start:index + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(parsed, dict):
                        return parsed
                    break
    return None


def _answer_and_citations(structured: dict[str, Any]) -> tuple[str, list[Any]]:
    answer = structured.get("answer_text")
    if not isinstance(answer, str) or not answer.strip():
        answer = structured.get("summary")
    if not isinstance(answer, str) or not answer.strip():
        answer = json.dumps(structured, ensure_ascii=False, indent=2, sort_keys=True)
    citations = structured.get("citations")
    return answer, citations if isinstance(citations, list) else []


def parse_demo_content(content: str) -> dict[str, Any]:
    """Parse provider content progressively while preserving readable fallback text."""

    if not isinstance(content, str) or not content.strip():
        raise DemoSafeError("provider_empty_content", "Provider response content was empty.")
    stripped = content.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        structured = sanitize_for_record(parsed)
        answer, citations = _answer_and_citations(structured)
        return {
            "parse_level": "strict_json", "structured_output": structured,
            "answer_text": answer, "citations": citations, "warnings": [],
        }

    fenced = _FENCED_JSON.match(stripped)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            structured = sanitize_for_record(parsed)
            answer, citations = _answer_and_citations(structured)
            return {
                "parse_level": "fenced_json", "structured_output": structured,
                "answer_text": answer, "citations": citations,
                "warnings": ["DEMO_TOLERANT_PARSE_FENCED_JSON"],
            }

    extracted = _first_balanced_json_object(stripped)
    if extracted is not None:
        structured = sanitize_for_record(extracted)
        answer, citations = _answer_and_citations(structured)
        return {
            "parse_level": "extracted_json", "structured_output": structured,
            "answer_text": answer, "citations": citations,
            "warnings": ["DEMO_TOLERANT_PARSE_EXTRACTED_JSON"],
        }
    return {
        "parse_level": "unstructured_text", "structured_output": None,
        "answer_text": sanitize_for_record(stripped), "citations": [],
        "warnings": ["DEMO_UNSTRUCTURED_TEXT_NOT_BENCHMARK_SCHEMA"],
    }


class CaseRepository:
    """Read-only view over the exact frozen B1B0 development package."""

    def __init__(
        self,
        pilot_root: str | Path,
        generation_run_name: str,
        *,
        contract_loader: Callable[[Path, str], tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]] = _load_development_contract,
    ) -> None:
        self.pilot_root = Path(pilot_root)
        self.generation_run_name = generation_run_name
        if not self.pilot_root.is_dir():
            raise DemoConfigurationError("pilot_root_missing")
        run_dir = self.pilot_root / generation_run_name
        if not run_dir.is_dir():
            raise DemoConfigurationError("generation_run_missing")
        try:
            manifest, selection, prompts, envelopes = contract_loader(run_dir, generation_run_name)
        except FileNotFoundError as exc:
            raise DemoConfigurationError("required_case_artifact_missing") from exc
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise DemoConfigurationError(f"frozen_case_package_invalid:{exc}") from exc
        selected = selection.get("selected_cases")
        if not isinstance(selected, list):
            raise DemoConfigurationError("frozen_case_selection_missing")
        selected_ids = [row.get("case_id") for row in selected]
        if selected_ids != list(EXPECTED_CASE_IDS):
            raise DemoConfigurationError("frozen_case_order_mismatch")
        if [row.get("case_id") for row in prompts] != list(EXPECTED_CASE_IDS):
            raise DemoConfigurationError("compiled_prompt_case_order_mismatch")
        if [row.get("case_id") for row in envelopes] != list(EXPECTED_CASE_IDS):
            raise DemoConfigurationError("request_envelope_case_order_mismatch")
        self._manifest = deepcopy(manifest)
        self._selected = deepcopy(selected)
        self._prompts = {row["case_id"]: deepcopy(row) for row in prompts}
        self._envelopes = {row["case_id"]: deepcopy(row) for row in envelopes}
        self._details: dict[str, dict[str, Any]] = {}
        for position, selected_case in enumerate(self._selected, start=1):
            case_id = selected_case["case_id"]
            prompt = self._prompts[case_id]
            envelope = self._envelopes[case_id]
            if (
                prompt.get("paper_id") != selected_case.get("paper_id")
                or prompt.get("case_type") != selected_case.get("case_type")
                or envelope.get("paper_id") != prompt.get("paper_id")
                or envelope.get("prompt_instance_id") != prompt.get("prompt_instance_id")
                or envelope.get("compiled_prompt_sha256") != prompt.get("compiled_prompt_sha256")
            ):
                raise DemoConfigurationError(f"case_prompt_request_binding_failed:{case_id}")
            evidence = []
            for block_index, block in enumerate(prompt.get("bounded_source_context") or [], start=1):
                locator = (
                    block.get("source_span_id")
                    or block.get("evidence_link_id")
                    or block.get("source_node_id")
                    or f"evidence-{block_index}"
                )
                evidence.append({
                    "index": block_index,
                    "context_role": block.get("context_role"),
                    "excerpt": block.get("excerpt"),
                    "source_span_id": block.get("source_span_id"),
                    "evidence_link_id": block.get("evidence_link_id"),
                    "source_node_id": block.get("source_node_id"),
                    "source_locator": locator,
                })
            self._details[case_id] = {
                "case_number": position,
                "case_id": case_id,
                "paper_id": prompt["paper_id"],
                "task_type": prompt["case_type"],
                "question": prompt["question"],
                "expected_answerability": selected_case.get("answerability_status"),
                "bounded_evidence": evidence,
                "prompt_metadata": {
                    "prompt_instance_id": prompt.get("prompt_instance_id"),
                    "prompt_version": prompt.get("prompt_version"),
                    "compiled_prompt_sha256": prompt.get("compiled_prompt_sha256"),
                    "request_envelope_id": envelope.get("request_envelope_id"),
                    "request_sha256": envelope.get("request_sha256"),
                    "required_answer_sections": deepcopy(prompt.get("required_answer_sections") or []),
                    "allowed_source_span_ids": deepcopy(prompt.get("allowed_source_span_ids") or []),
                    "allowed_evidence_link_ids": deepcopy(prompt.get("allowed_evidence_link_ids") or []),
                },
            }

    def summaries(self) -> list[dict[str, Any]]:
        return [{key: detail[key] for key in (
            "case_number", "case_id", "paper_id", "task_type", "expected_answerability",
        )} for detail in self._details.values()]

    def detail(self, case_id: str) -> dict[str, Any]:
        if case_id not in self._details:
            raise DemoSafeError("unknown_case_id", "The selected case is not in the frozen package.")
        return deepcopy(self._details[case_id])

    def prompt(self, case_id: str) -> dict[str, Any]:
        self.detail(case_id)
        return deepcopy(self._prompts[case_id])

    def envelope(self, case_id: str) -> dict[str, Any]:
        self.detail(case_id)
        return deepcopy(self._envelopes[case_id])


class FixtureRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DemoConfigurationError("demo_fixture_file_invalid") from exc
        if value.get("schema_version") != DEMO_FIXTURE_SCHEMA_VERSION:
            raise DemoConfigurationError("demo_fixture_schema_mismatch")
        outputs = value.get("outputs")
        if not isinstance(outputs, list) or [row.get("case_id") for row in outputs] != list(EXPECTED_CASE_IDS):
            raise DemoConfigurationError("demo_fixture_case_order_mismatch")
        if any(FIXTURE_WARNING not in (row.get("warnings") or []) for row in outputs):
            raise DemoConfigurationError("demo_fixture_warning_missing")
        self._outputs = {row["case_id"]: deepcopy(row) for row in outputs}

    def result(self, case_id: str) -> dict[str, Any]:
        if case_id not in self._outputs:
            raise DemoSafeError("unknown_case_id", "No fixture exists for the selected case.")
        return deepcopy(self._outputs[case_id])


class RunStore:
    def __init__(self, demo_root: str | Path, *, repository_root: str | Path | None = None) -> None:
        self.demo_root = Path(demo_root).resolve()
        self.repository_root = Path(repository_root or _repository_root()).resolve()
        if self.demo_root == self.repository_root or _is_within(self.demo_root, self.repository_root):
            raise DemoConfigurationError("demo_root_must_be_outside_repository")
        self.runs_dir = self.demo_root / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, run_id: str) -> Path:
        if not _RUN_ID.fullmatch(run_id):
            raise DemoSafeError("run_id_invalid", "The demo run ID is invalid.")
        return self.runs_dir / f"{run_id}.json"

    def write(self, record: dict[str, Any], *, secret: str | None = None) -> None:
        if set(record) != DEMO_RUN_FIELDS or record.get("schema_version") != DEMO_RUN_SCHEMA_VERSION:
            raise DemoConfigurationError("demo_run_record_contract_mismatch")
        if record.get("status") not in RUN_STATES:
            raise DemoConfigurationError("demo_run_status_invalid")
        safe = sanitize_for_record(record, secret=secret, repository_root=self.repository_root)
        path = self._path(str(safe["run_id"]))
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        serialized = json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with self._lock:
            try:
                temporary.write_text(serialized, encoding="utf-8")
                os.replace(temporary, path)
            finally:
                if temporary.exists():
                    temporary.unlink()

    def read(self, run_id: str) -> dict[str, Any]:
        path = self._path(run_id)
        if not path.is_file():
            raise DemoSafeError("run_not_found", "The requested demo run was not found.")
        with self._lock:
            return json.loads(path.read_text(encoding="utf-8"))

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        if type(limit) is not int or limit < 1 or limit > 100:
            raise DemoSafeError("history_limit_invalid", "History limit must be between 1 and 100.")
        records: list[dict[str, Any]] = []
        with self._lock:
            for path in self.runs_dir.glob("DR17_*.json"):
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if set(value) == DEMO_RUN_FIELDS:
                    records.append(value)
        records.sort(key=lambda row: (str(row.get("created_at_utc") or ""), str(row.get("run_id") or "")), reverse=True)
        return [{key: row.get(key) for key in (
            "run_id", "created_at_utc", "completed_at_utc", "case_id", "mode", "status",
            "latency_seconds", "parse_level", "safe_error_code",
        )} for row in records[:limit]]


class BatchStore:
    """Atomic external storage for sanitized batch records and portable reports."""

    def __init__(self, demo_root: str | Path, *, repository_root: str | Path | None = None) -> None:
        self.demo_root = Path(demo_root).resolve()
        self.repository_root = Path(repository_root or _repository_root()).resolve()
        if self.demo_root == self.repository_root or _is_within(self.demo_root, self.repository_root):
            raise DemoConfigurationError("demo_root_must_be_outside_repository")
        self.batches_dir = self.demo_root / "batches"
        self.reports_dir = self.demo_root / "reports"
        self.batches_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, batch_id: str) -> Path:
        if not _BATCH_ID.fullmatch(batch_id):
            raise DemoSafeError("batch_id_invalid", "The demo batch ID is invalid.")
        return self.batches_dir / f"{batch_id}.json"

    def _report_path(self, batch_id: str) -> Path:
        if not _BATCH_ID.fullmatch(batch_id):
            raise DemoSafeError("batch_id_invalid", "The demo batch ID is invalid.")
        return self.reports_dir / f"{batch_id}.html"

    def write(self, record: dict[str, Any]) -> None:
        if set(record) != DEMO_BATCH_FIELDS or record.get("schema_version") != DEMO_BATCH_SCHEMA_VERSION:
            raise DemoConfigurationError("demo_batch_record_contract_mismatch")
        if record.get("status") not in BATCH_STATES:
            raise DemoConfigurationError("demo_batch_status_invalid")
        if record.get("case_ids") != list(EXPECTED_CASE_IDS):
            raise DemoConfigurationError("demo_batch_case_order_mismatch")
        items = record.get("items")
        if (
            not isinstance(items, list)
            or len(items) != len(EXPECTED_CASE_IDS)
            or any(set(item) != BATCH_ITEM_FIELDS for item in items if isinstance(item, dict))
            or any(not isinstance(item, dict) for item in items)
            or [item.get("case_id") for item in items] != list(EXPECTED_CASE_IDS)
        ):
            raise DemoConfigurationError("demo_batch_items_contract_mismatch")
        safe = sanitize_for_record(record, repository_root=self.repository_root)
        path = self._path(str(safe["batch_id"]))
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        serialized = json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with self._lock:
            try:
                temporary.write_text(serialized, encoding="utf-8")
                _replace_atomic_with_sharing_retry(temporary, path)
            finally:
                if temporary.exists():
                    temporary.unlink()

    def read(self, batch_id: str) -> dict[str, Any]:
        path = self._path(batch_id)
        if not path.is_file():
            raise DemoSafeError("batch_not_found", "The requested demo batch was not found.")
        with self._lock:
            return json.loads(path.read_text(encoding="utf-8"))

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        if type(limit) is not int or limit < 1 or limit > 100:
            raise DemoSafeError("history_limit_invalid", "History limit must be between 1 and 100.")
        records: list[dict[str, Any]] = []
        with self._lock:
            for path in self.batches_dir.glob("DB17_*.json"):
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if set(value) == DEMO_BATCH_FIELDS:
                    records.append(value)
        records.sort(
            key=lambda row: (str(row.get("created_at_utc") or ""), str(row.get("batch_id") or "")),
            reverse=True,
        )
        return [{
            "batch_id": row.get("batch_id"),
            "created_at_utc": row.get("created_at_utc"),
            "completed_at_utc": row.get("completed_at_utc"),
            "mode": row.get("mode"),
            "status": row.get("status"),
            "completed_case_count": row.get("completed_case_count"),
            "succeeded_case_count": row.get("succeeded_case_count"),
            "failed_case_count": row.get("failed_case_count"),
            "latency_seconds": row.get("latency_seconds"),
            "total_tokens": (row.get("aggregate_usage") or {}).get("total_tokens", 0),
        } for row in records[:limit]]

    def write_report(self, batch_id: str, html_text: str) -> str:
        path = self._report_path(batch_id)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        with self._lock:
            try:
                temporary.write_text(html_text, encoding="utf-8", newline="\n")
                _replace_atomic_with_sharing_retry(temporary, path)
            finally:
                if temporary.exists():
                    temporary.unlink()
        return f"reports/{batch_id}.html"

    def read_report(self, batch_id: str) -> bytes:
        record = self.read(batch_id)
        expected = f"reports/{batch_id}.html"
        if record.get("status") not in TERMINAL_BATCH_STATES or record.get("report_filename") != expected:
            raise DemoSafeError("batch_report_not_ready", "The demo batch report is not ready.")
        path = self._report_path(batch_id)
        if not path.is_file():
            raise DemoSafeError("batch_report_not_ready", "The demo batch report is not ready.")
        with self._lock:
            return path.read_bytes()


def build_live_payload(prompt: dict[str, Any], *, model_id: str, max_output_tokens: int) -> dict[str, Any]:
    user_contract = {
        "case_id": prompt["case_id"],
        "paper_id": prompt["paper_id"],
        "question": prompt["question"],
        "required_answer_sections": prompt["required_answer_sections"],
        "expected_answer_contract": prompt["expected_answer_contract"],
        "allowed_source_span_ids": prompt["allowed_source_span_ids"],
        "allowed_evidence_link_ids": prompt["allowed_evidence_link_ids"],
        "bounded_source_context": prompt["bounded_source_context"],
        "response_json_schema": prompt["response_json_schema"],
    }
    return {
        "model": model_id,
        "messages": [
            {"role": "system", "content": prompt["prompt_contract_text"]},
            {"role": "user", "content": canonical_json(user_contract)},
        ],
        "max_tokens": max_output_tokens,
    }


def _safe_usage(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    safe: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        item = value.get(key)
        if type(item) is int and item >= 0:
            safe[key] = item
    return safe or None


def _http_error(status: int) -> str:
    return {
        401: "provider_unauthorized",
        403: "provider_forbidden",
        404: "provider_not_found",
        429: "provider_rate_limited",
    }.get(status, "provider_http_error")


class DemoService:
    """Case browsing, one-worker execution, safe persistence, and explicit preflight."""

    def __init__(
        self,
        config: DemoConfig,
        cases: CaseRepository,
        fixtures: FixtureRepository,
        *,
        http_client: HTTPClient = requests,
        credential_reader: Callable[[str], str | None] = _read_live_credential,
    ) -> None:
        config.validate()
        self.config = config
        self.cases = cases
        self.fixtures = fixtures
        self.http_client = http_client
        self.credential_reader = credential_reader
        self.store = RunStore(config.demo_root, repository_root=config.repository_root)
        self.batch_store = BatchStore(config.demo_root, repository_root=config.repository_root)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="enh3-demo-v017")
        self._futures: set[Future[Any]] = set()
        self._futures_lock = threading.Lock()

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=False)

    def config_view(self) -> dict[str, Any]:
        return {
            "version": DEMO_VERSION,
            "provider": USTC_LLM_DEEPSEEK_V4_PRO_PROFILE,
            "endpoint_label": safe_endpoint_label(self.config.endpoint),
            "model": self.config.model_id,
            "timeout_seconds": float(self.config.timeout_seconds),
            "max_output_tokens": self.config.max_output_tokens,
            "live_enabled": self.config.live_enabled,
            "case_count": len(EXPECTED_CASE_IDS),
        }

    def _validate_mode(self, mode: str) -> None:
        if mode not in {"fixture", "live"}:
            raise DemoSafeError("demo_mode_invalid", "Mode must be fixture or live.")
        if mode == "live" and not self.config.live_enabled:
            raise DemoSafeError("live_api_disabled", "Live API mode was not enabled at server startup.")

    def _create_run_record(self, *, case_id: str, mode: str) -> str:
        self._validate_mode(mode)
        case = self.cases.detail(case_id)
        envelope = self.cases.envelope(case_id)
        run_id = "DR17_" + uuid.uuid4().hex[:20].upper()
        record = {
            "schema_version": DEMO_RUN_SCHEMA_VERSION,
            "run_id": run_id,
            "case_id": case_id,
            "paper_id": case["paper_id"],
            "task_type": case["task_type"],
            "mode": mode,
            "status": "queued",
            "provider": "fixture" if mode == "fixture" else USTC_LLM_DEEPSEEK_V4_PRO_PROFILE,
            "requested_model": self.config.model_id,
            "reported_model": None,
            "created_at_utc": utc_now(),
            "started_at_utc": None,
            "completed_at_utc": None,
            "latency_seconds": None,
            "timeout_seconds": float(self.config.timeout_seconds),
            "max_output_tokens": self.config.max_output_tokens,
            "request_sha256": envelope.get("request_sha256"),
            "http_status": None,
            "provider_response_id": None,
            "finish_reason": None,
            "usage": None,
            "parse_level": None,
            "structured_output": None,
            "answer_text": "",
            "citations": [],
            "warnings": [FIXTURE_WARNING] if mode == "fixture" else [],
            "safe_error_code": None,
            "safe_error_message": None,
        }
        self.store.write(record)
        return run_id

    def _track_future(self, future: Future[Any]) -> None:
        with self._futures_lock:
            self._futures.add(future)
        future.add_done_callback(self._forget_future)

    def submit_run(self, *, case_id: str, mode: str) -> dict[str, Any]:
        run_id = self._create_run_record(case_id=case_id, mode=mode)
        self._track_future(self._executor.submit(self._execute_run, run_id))
        return {"run_id": run_id, "status": "queued", "poll_url": f"/api/runs/{run_id}"}

    def _create_batch_record(self, mode: str) -> dict[str, Any]:
        self._validate_mode(mode)
        batch_id = "DB17_" + uuid.uuid4().hex[:20].upper()
        items = []
        for case_number, case_id in enumerate(EXPECTED_CASE_IDS, start=1):
            case = self.cases.detail(case_id)
            items.append({
                "case_number": case_number,
                "case_id": case_id,
                "paper_id": case["paper_id"],
                "task_type": case["task_type"],
                "run_id": None,
                "status": "pending",
                "parse_level": None,
                "latency_seconds": None,
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "safe_error_code": None,
            })
        record = {
            "schema_version": DEMO_BATCH_SCHEMA_VERSION,
            "batch_id": batch_id,
            "mode": mode,
            "status": "queued",
            "case_ids": list(EXPECTED_CASE_IDS),
            "created_at_utc": utc_now(),
            "started_at_utc": None,
            "completed_at_utc": None,
            "latency_seconds": None,
            "current_case_index": None,
            "current_case_id": None,
            "completed_case_count": 0,
            "succeeded_case_count": 0,
            "failed_case_count": 0,
            "run_ids": [],
            "items": items,
            "aggregate_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "aggregate_child_latency_seconds": 0.0,
            "warnings": [FIXTURE_WARNING] if mode == "fixture" else [],
            "safe_error_code": None,
            "safe_error_message": None,
            "report_filename": None,
        }
        self.batch_store.write(record)
        return record

    def submit_batch(self, *, mode: str) -> dict[str, Any]:
        record = self._create_batch_record(mode)
        batch_id = record["batch_id"]
        self._track_future(self._executor.submit(self._execute_batch, batch_id))
        return {"batch_id": batch_id, "status": "queued", "poll_url": f"/api/batches/{batch_id}"}

    def _forget_future(self, future: Future[Any]) -> None:
        with self._futures_lock:
            self._futures.discard(future)

    def _execute_run(self, run_id: str) -> dict[str, Any]:
        record = self.store.read(run_id)
        started_monotonic = time.monotonic()
        record.update({"status": "running", "started_at_utc": utc_now()})
        self.store.write(record)
        secret: str | None = None
        try:
            if record["mode"] == "fixture":
                fixture = self.fixtures.result(record["case_id"])
                structured = sanitize_for_record(fixture.get("structured_output") or {})
                answer, citations = _answer_and_citations(structured)
                warnings = list(dict.fromkeys([FIXTURE_WARNING, *(fixture.get("warnings") or [])]))
                record.update({
                    "status": "succeeded_structured",
                    "reported_model": "deterministic-fixture",
                    "parse_level": "strict_json",
                    "structured_output": structured,
                    "answer_text": answer,
                    "citations": citations,
                    "warnings": warnings,
                })
            else:
                secret = self.credential_reader(API_KEY_ENVIRONMENT_VARIABLE)
                if not secret:
                    raise DemoSafeError("credential_missing", "Live API credential is unavailable.")
                result = self._perform_live_request(record["case_id"], secret)
                record.update(result)
        except DemoSafeError as exc:
            record.update({
                "status": "failed", "http_status": exc.http_status,
                "safe_error_code": exc.code, "safe_error_message": exc.safe_message,
            })
        except Exception:
            # Do not interpolate exception text: a third-party exception could echo request data.
            LOGGER.error("Unexpected internal failure for demo run %s", run_id)
            record.update({
                "status": "failed", "safe_error_code": "demo_internal_error",
                "safe_error_message": "The local demo encountered an internal error.",
            })
        record["latency_seconds"] = round(time.monotonic() - started_monotonic, 6)
        record["completed_at_utc"] = utc_now()
        self.store.write(record, secret=secret)
        return self.store.read(run_id)

    def _update_batch_from_child(
        self, batch: dict[str, Any], *, item_index: int, child: dict[str, Any],
    ) -> None:
        usage = child.get("usage") if isinstance(child.get("usage"), dict) else {}
        item = batch["items"][item_index]
        item.update({
            "run_id": child["run_id"],
            "status": child["status"],
            "parse_level": child.get("parse_level"),
            "latency_seconds": child.get("latency_seconds"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "safe_error_code": child.get("safe_error_code"),
        })
        terminal_items = [row for row in batch["items"] if row["status"] in TERMINAL_RUN_STATES]
        batch["completed_case_count"] = len(terminal_items)
        batch["succeeded_case_count"] = sum(row["status"].startswith("succeeded_") for row in terminal_items)
        batch["failed_case_count"] = sum(row["status"] == "failed" for row in terminal_items)
        batch["aggregate_child_latency_seconds"] = round(sum(
            float(row["latency_seconds"] or 0.0) for row in terminal_items
        ), 6)
        batch["aggregate_usage"] = {
            key: sum(int(row[key] or 0) for row in terminal_items)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }

    def _execute_batch(self, batch_id: str) -> None:
        batch = self.batch_store.read(batch_id)
        started_monotonic = time.monotonic()
        batch.update({"status": "running", "started_at_utc": utc_now()})
        self.batch_store.write(batch)
        try:
            for item_index, case_id in enumerate(EXPECTED_CASE_IDS):
                batch["current_case_index"] = item_index + 1
                batch["current_case_id"] = case_id
                run_id = self._create_run_record(case_id=case_id, mode=batch["mode"])
                batch["run_ids"].append(run_id)
                batch["items"][item_index].update({"run_id": run_id, "status": "queued"})
                self.batch_store.write(batch)
                batch["items"][item_index]["status"] = "running"
                self.batch_store.write(batch)
                child = self._execute_run(run_id)
                self._update_batch_from_child(batch, item_index=item_index, child=child)
                batch["latency_seconds"] = round(time.monotonic() - started_monotonic, 6)
                self.batch_store.write(batch)
            batch["status"] = "completed" if batch["failed_case_count"] == 0 else "completed_with_failures"
        except Exception as exc:
            # Never include exception text because a transport may echo request content.
            trace = exc.__traceback__
            while trace is not None and trace.tb_next is not None:
                trace = trace.tb_next
            LOGGER.error(
                "Unexpected internal failure for demo batch %s (%s in %s:%s)",
                batch_id, type(exc).__name__, trace.tb_frame.f_code.co_name if trace else "unknown",
                trace.tb_lineno if trace else 0,
            )
            batch.update({
                "status": "failed",
                "safe_error_code": "demo_internal_error",
                "safe_error_message": "The local demo batch coordinator encountered an internal error.",
            })
        batch["latency_seconds"] = round(time.monotonic() - started_monotonic, 6)
        batch["completed_at_utc"] = utc_now()
        try:
            report = self._build_batch_report(batch)
            batch["report_filename"] = self.batch_store.write_report(batch_id, report)
        except Exception as exc:
            LOGGER.error(
                "Unexpected report generation failure for demo batch %s (%s)",
                batch_id, type(exc).__name__,
            )
            batch["warnings"] = list(dict.fromkeys([*batch["warnings"], "DEMO_BATCH_REPORT_FAILED"]))
        self.batch_store.write(batch)

    def _build_batch_report(self, batch: dict[str, Any]) -> str:
        batch_id = str(batch["batch_id"])

        def h(value: Any) -> str:
            return escape("—" if value is None else str(value), quote=True)

        def json_text(value: Any) -> str:
            return h(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))

        item_rows: list[str] = []
        details: list[str] = []
        for item in batch["items"]:
            item_rows.append(
                "<tr>"
                f"<td>{h(item['case_number'])}</td><td><code>{h(item['case_id'])}</code></td>"
                f"<td>{h(item['task_type'])}</td><td>{h(item['status'])}</td>"
                f"<td>{h(item['parse_level'])}</td><td>{h(item['latency_seconds'])}</td>"
                f"<td>{h(item['prompt_tokens'])}</td><td>{h(item['completion_tokens'])}</td>"
                f"<td>{h(item['total_tokens'])}</td><td>{h(item['safe_error_code'])}</td></tr>"
            )
            run_id = item.get("run_id")
            if not run_id:
                continue
            child = self.store.read(run_id)
            case = self.cases.detail(item["case_id"])
            structured = child.get("structured_output") if isinstance(child.get("structured_output"), dict) else {}
            provider_metadata = {
                "provider": child.get("provider"),
                "requested_model": child.get("requested_model"),
                "reported_model": child.get("reported_model"),
                "provider_response_id": child.get("provider_response_id"),
                "http_status": child.get("http_status"),
                "finish_reason": child.get("finish_reason"),
                "usage": child.get("usage"),
            }
            details.append(
                "<section class=\"case\">"
                f"<h2>{h(item['case_number'])}. <code>{h(item['case_id'])}</code></h2>"
                f"<p><strong>Question:</strong> {h(case['question'])}</p>"
                f"<p><strong>Status:</strong> {h(child['status'])} · <strong>Parse level:</strong> {h(child.get('parse_level'))}</p>"
                f"<h3>Answer</h3><pre>{h(child.get('answer_text') or '')}</pre>"
                f"<h3>Warnings</h3><pre>{json_text(child.get('warnings') or [])}</pre>"
                f"<h3>Safe provider metadata</h3><pre>{json_text(provider_metadata)}</pre>"
                f"<h3>Claims</h3><pre>{json_text(structured.get('claims') or [])}</pre>"
                f"<h3>Citations</h3><pre>{json_text(child.get('citations') or [])}</pre>"
                "</section>"
            )
        usage = batch.get("aggregate_usage") or {}
        fixture_notice = (
            "<p class=\"notice fixture\"><strong>Fixture — not model-generated scientific output</strong><br>"
            "No provider request occurred.</p>" if batch["mode"] == "fixture" else ""
        )
        return "".join([
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
            f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{h(batch_id)} batch report</title>",
            "<style>body{max-width:1200px;margin:0 auto;padding:32px;font:15px/1.55 system-ui,sans-serif;color:#14211d}"
            "table{width:100%;border-collapse:collapse}th,td{padding:8px;border:1px solid #dce4de;text-align:left}"
            "th{background:#edf5f0}code,pre{font-family:ui-monospace,monospace}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8f6;padding:12px}"
            ".notice{padding:14px;background:#fff1d8;border-left:4px solid #a45b08}.case{margin-top:30px;padding-top:18px;border-top:2px solid #dce4de}</style></head><body>",
            "<p class=\"notice\"><strong>Demo output — not automatically accepted into the benchmark</strong></p>",
            fixture_notice,
            f"<h1>Seven-case batch report</h1><p><strong>Batch ID:</strong> <code>{h(batch_id)}</code><br>"
            f"<strong>Mode:</strong> {h(batch['mode'])}<br><strong>Status:</strong> {h(batch['status'])}<br>"
            f"<strong>Created:</strong> {h(batch['created_at_utc'])}<br><strong>Started:</strong> {h(batch['started_at_utc'])}<br>"
            f"<strong>Completed:</strong> {h(batch['completed_at_utc'])}</p>",
            f"<p><strong>Completed cases:</strong> {h(batch['completed_case_count'])}/7 · "
            f"<strong>Successful:</strong> {h(batch['succeeded_case_count'])} · <strong>Failed:</strong> {h(batch['failed_case_count'])}<br>"
            f"<strong>Batch wall-clock latency:</strong> {h(batch['latency_seconds'])} s · "
            f"<strong>Summed child latency:</strong> {h(batch['aggregate_child_latency_seconds'])} s<br>"
            f"<strong>Aggregate tokens:</strong> prompt {h(usage.get('prompt_tokens', 0))}, completion {h(usage.get('completion_tokens', 0))}, total {h(usage.get('total_tokens', 0))}</p>",
            "<table><thead><tr><th>#</th><th>Case ID</th><th>Task type</th><th>Status</th><th>Parse level</th>"
            "<th>Latency</th><th>Prompt</th><th>Completion</th><th>Total</th><th>Error</th></tr></thead><tbody>",
            "".join(item_rows), "</tbody></table>", "".join(details), "</body></html>",
        ])

    def _perform_live_request(self, case_id: str, secret: str) -> dict[str, Any]:
        prompt = self.cases.prompt(case_id)
        payload = build_live_payload(
            prompt, model_id=self.config.model_id, max_output_tokens=self.config.max_output_tokens,
        )
        try:
            response = self.http_client.post(
                self.config.endpoint,
                headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
                json=payload,
                timeout=float(self.config.timeout_seconds),
            )
        except requests.Timeout as exc:
            raise DemoSafeError("provider_timeout", "The provider request reached the client timeout.") from exc
        except requests.ConnectionError as exc:
            raise DemoSafeError("provider_connection_error", "The provider connection failed.") from exc
        except requests.RequestException as exc:
            raise DemoSafeError("provider_connection_error", "The provider request could not be completed.") from exc
        status = int(getattr(response, "status_code", 0) or 0)
        if status != HTTPStatus.OK:
            raise DemoSafeError(
                _http_error(status), f"Provider returned HTTP {status}.", http_status=status or None,
            )
        try:
            body = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise DemoSafeError(
                "provider_malformed_response", "Provider response was not valid JSON.", http_status=status,
            ) from exc
        if not isinstance(body, dict):
            raise DemoSafeError(
                "provider_malformed_response", "Provider response shape was invalid.", http_status=status,
            )
        choices = body.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise DemoSafeError(
                "provider_malformed_response", "Provider response choices were invalid.", http_status=status,
            )
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict):
            raise DemoSafeError(
                "provider_malformed_response", "Provider response message was invalid.", http_status=status,
            )
        content = message.get("content")
        parsed = parse_demo_content(content)
        parsed = sanitize_for_record(parsed, secret=secret, repository_root=self.store.repository_root)
        return {
            "status": (
                "succeeded_unstructured"
                if parsed["parse_level"] == "unstructured_text"
                else "succeeded_structured"
            ),
            "http_status": status,
            "provider_response_id": sanitize_for_record(body.get("id"), secret=secret),
            "reported_model": sanitize_for_record(body.get("model"), secret=secret),
            "finish_reason": sanitize_for_record(choice.get("finish_reason"), secret=secret),
            "usage": _safe_usage(body.get("usage")),
            **parsed,
        }

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self.store.read(run_id)

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.store.history(limit)

    def get_batch(self, batch_id: str) -> dict[str, Any]:
        return self.batch_store.read(batch_id)

    def batch_history(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.batch_store.history(limit)

    def get_batch_report(self, batch_id: str) -> bytes:
        return self.batch_store.read_report(batch_id)

    def preflight_models(self) -> dict[str, Any]:
        if not self.config.live_enabled:
            raise DemoSafeError("live_api_disabled", "Live API mode was not enabled at server startup.")
        checked_at = utc_now()
        started = time.monotonic()
        secret = self.credential_reader(API_KEY_ENVIRONMENT_VARIABLE)
        if not secret:
            return {
                "status": "failed", "http_status": None, "model_count": 0,
                "target_model": self.config.model_id, "target_model_visible": False,
                "latency_seconds": round(time.monotonic() - started, 6),
                "checked_at_utc": checked_at, "safe_error_code": "credential_missing",
            }
        try:
            response = self.http_client.get(
                USTC_MODELS_ENDPOINT,
                headers={"Authorization": f"Bearer {secret}"},
                timeout=float(self.config.timeout_seconds),
            )
        except requests.Timeout:
            code, status, models = "provider_timeout", None, []
        except requests.ConnectionError:
            code, status, models = "provider_connection_error", None, []
        except requests.RequestException:
            code, status, models = "provider_connection_error", None, []
        else:
            status = int(getattr(response, "status_code", 0) or 0)
            if status != HTTPStatus.OK:
                code, models = _http_error(status), []
            else:
                try:
                    body = response.json()
                except (ValueError, json.JSONDecodeError):
                    code, models = "provider_malformed_response", []
                else:
                    data = body.get("data") if isinstance(body, dict) else None
                    if not isinstance(data, list):
                        code, models = "provider_malformed_response", []
                    else:
                        models = [row.get("id") for row in data if isinstance(row, dict) and isinstance(row.get("id"), str)]
                        code = None
        return {
            "status": "succeeded" if code is None else "failed",
            "http_status": status,
            "model_count": len(models),
            "target_model": self.config.model_id,
            "target_model_visible": self.config.model_id in models,
            "latency_seconds": round(time.monotonic() - started, 6),
            "checked_at_utc": checked_at,
            "safe_error_code": code,
        }


class DemoHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], service: DemoService, static_root: Path) -> None:
        self.demo_service = service
        self.static_root = static_root.resolve()
        super().__init__(address, DemoRequestHandler)


class DemoRequestHandler(BaseHTTPRequestHandler):
    server: DemoHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("demo_http " + format, *args)

    def _send_json(self, status: int, value: Any) -> None:
        body = json.dumps(sanitize_for_record(value), ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _api_error(self, status: int, code: str, message: str) -> None:
        self._send_json(status, {"status": "error", "safe_error_code": code, "message": message})

    def _send_html(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _path(self) -> tuple[str, dict[str, list[str]]]:
        parsed = urlparse(self.path)
        return unquote(parsed.path), parse_qs(parsed.query)

    def _unsafe_path(self, path: str) -> bool:
        return "\\" in path or any(segment == ".." for segment in path.split("/"))

    def _read_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "0")
        except ValueError as exc:
            raise DemoSafeError("request_length_invalid", "Request Content-Length is invalid.") from exc
        if length < 0 or length > REQUEST_BODY_SIZE_LIMIT:
            self.close_connection = True
            raise DemoSafeError("request_body_too_large", "Request body exceeds the demo limit.")
        body = self.rfile.read(length)
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DemoSafeError("request_json_invalid", "Request body must be a JSON object.") from exc
        if not isinstance(value, dict):
            raise DemoSafeError("request_json_invalid", "Request body must be a JSON object.")
        return value

    def do_GET(self) -> None:  # noqa: N802
        path, query = self._path()
        if path.startswith("/api/") and self._unsafe_path(path):
            self._api_error(400, "api_path_invalid", "API path is invalid.")
            return
        if path == "/health":
            self._send_json(200, {
                "status": "ok", "version": DEMO_VERSION,
                "live_enabled": self.server.demo_service.config.live_enabled,
            })
            return
        if path == "/api/config":
            self._send_json(200, self.server.demo_service.config_view())
            return
        if path == "/api/cases":
            self._send_json(200, {"cases": self.server.demo_service.cases.summaries()})
            return
        if path.startswith("/api/cases/"):
            case_id = path.removeprefix("/api/cases/")
            try:
                detail = self.server.demo_service.cases.detail(case_id)
            except DemoSafeError as exc:
                self._api_error(404, exc.code, exc.safe_message)
            else:
                self._send_json(200, detail)
            return
        if path == "/api/batches":
            try:
                limit = int(query.get("limit", ["20"])[0])
                history = self.server.demo_service.batch_history(limit)
            except (ValueError, DemoSafeError) as exc:
                code = exc.code if isinstance(exc, DemoSafeError) else "history_limit_invalid"
                message = exc.safe_message if isinstance(exc, DemoSafeError) else "History limit is invalid."
                self._api_error(400, code, message)
            else:
                self._send_json(200, {"batches": history})
            return
        if path.startswith("/api/batches/"):
            suffix = path.removeprefix("/api/batches/")
            is_report = suffix.endswith("/report")
            batch_id = suffix.removesuffix("/report") if is_report else suffix
            try:
                if is_report:
                    report = self.server.demo_service.get_batch_report(batch_id)
                else:
                    record = self.server.demo_service.get_batch(batch_id)
            except DemoSafeError as exc:
                if exc.code == "batch_report_not_ready":
                    self._api_error(409, exc.code, exc.safe_message)
                else:
                    status = 404 if exc.code == "batch_not_found" else 400
                    self._api_error(status, exc.code, exc.safe_message)
            else:
                if is_report:
                    self._send_html(200, report)
                else:
                    self._send_json(200, record)
            return
        if path == "/api/runs":
            try:
                limit = int(query.get("limit", ["20"])[0])
                history = self.server.demo_service.history(limit)
            except (ValueError, DemoSafeError) as exc:
                code = exc.code if isinstance(exc, DemoSafeError) else "history_limit_invalid"
                message = exc.safe_message if isinstance(exc, DemoSafeError) else "History limit is invalid."
                self._api_error(400, code, message)
            else:
                self._send_json(200, {"runs": history})
            return
        if path.startswith("/api/runs/"):
            run_id = path.removeprefix("/api/runs/")
            try:
                record = self.server.demo_service.get_run(run_id)
            except DemoSafeError as exc:
                status = 404 if exc.code == "run_not_found" else 400
                self._api_error(status, exc.code, exc.safe_message)
            else:
                self._send_json(200, record)
            return
        if path.startswith("/api/"):
            self._api_error(404, "api_route_not_found", "API route not found.")
            return
        if path == "/":
            self._serve_static("index.html", "text/html; charset=utf-8")
            return
        if path == "/static/app.js":
            self._serve_static("app.js", "text/javascript; charset=utf-8")
            return
        if path == "/static/styles.css":
            self._serve_static("styles.css", "text/css; charset=utf-8")
            return
        self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        path, _ = self._path()
        if path.startswith("/api/") and self._unsafe_path(path):
            self._api_error(400, "api_path_invalid", "API path is invalid.")
            return
        if path == "/api/preflight/models":
            try:
                if not self.server.demo_service.config.live_enabled:
                    raise DemoSafeError(
                        "live_api_disabled", "Live API mode was not enabled at server startup.",
                    )
                body = self._read_body()
                if body:
                    raise DemoSafeError("preflight_request_invalid", "Preflight request must be empty.")
                result = self.server.demo_service.preflight_models()
            except DemoSafeError as exc:
                status = 413 if exc.code == "request_body_too_large" else 403 if exc.code == "live_api_disabled" else 400
                self._api_error(status, exc.code, exc.safe_message)
            else:
                self._send_json(200, result)
            return
        if path == "/api/runs":
            try:
                body = self._read_body()
                if set(body) != {"case_id", "mode"}:
                    raise DemoSafeError("run_request_invalid", "Run request fields are invalid.")
                result = self.server.demo_service.submit_run(
                    case_id=body.get("case_id"), mode=body.get("mode"),
                )
            except DemoSafeError as exc:
                if exc.code == "request_body_too_large":
                    status = 413
                elif exc.code == "live_api_disabled":
                    status = 403
                elif exc.code == "unknown_case_id":
                    status = 404
                else:
                    status = 400
                self._api_error(status, exc.code, exc.safe_message)
            else:
                self._send_json(202, result)
            return
        if path == "/api/batches":
            try:
                body = self._read_body()
                if set(body) != {"mode"}:
                    raise DemoSafeError("batch_request_invalid", "Batch request fields are invalid.")
                result = self.server.demo_service.submit_batch(mode=body.get("mode"))
            except DemoSafeError as exc:
                if exc.code == "request_body_too_large":
                    status = 413
                elif exc.code == "live_api_disabled":
                    status = 403
                else:
                    status = 400
                self._api_error(status, exc.code, exc.safe_message)
            else:
                self._send_json(202, result)
            return
        if path.startswith("/api/"):
            self._api_error(404, "api_route_not_found", "API route not found.")
            return
        self.send_error(404)

    def _serve_static(self, name: str, content_type: str) -> None:
        path = self.server.static_root / name
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def create_demo_server(
    config: DemoConfig,
    *,
    static_root: str | Path | None = None,
    fixture_path: str | Path | None = None,
    contract_loader: Callable[[Path, str], tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]] = _load_development_contract,
    http_client: HTTPClient = requests,
    credential_reader: Callable[[str], str | None] = _read_live_credential,
) -> DemoHTTPServer:
    config.validate()
    repo = config.repository_root or _repository_root()
    static = Path(static_root or repo / "demo_v017/static")
    fixtures = Path(fixture_path or repo / "demo_v017/fixtures/fixture_outputs.json")
    cases = CaseRepository(
        config.pilot_root, config.generation_run_name, contract_loader=contract_loader,
    )
    service = DemoService(
        config, cases, FixtureRepository(fixtures),
        http_client=http_client, credential_reader=credential_reader,
    )
    return DemoHTTPServer((config.host, config.port), service, static)


def serve_demo(config: DemoConfig) -> None:
    server = create_demo_server(config)
    host, port = server.server_address[:2]
    print(f"eNH3-Bench M017 Demo: http://{host}:{port}", flush=True)
    print("Live API is enabled." if config.live_enabled else "Fixture-only mode; live API is disabled.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping M017 demo.", flush=True)
    finally:
        server.shutdown()
        server.server_close()
        server.demo_service.shutdown(wait=True)
