"""Controlled v0.16 B1B1 provider execution infrastructure.

Preparing and validating execution artifacts is always offline.  The only network-capable
entry point is :func:`run_real_execution`, which reads a credential only after every
authorization, development-only, configuration, and budget gate has passed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Any, Callable, Protocol, runtime_checkable
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from enh3bench.e2e_eval_schema import (
    canonical_json,
    read_json,
    read_jsonl,
    sha256_bytes,
    write_json,
    write_jsonl,
)
from enh3bench.generation_pilot import (
    COMPILED_PROMPT_FIELDS,
    PILOT_CASE_COUNT,
    REQUEST_ENVELOPE_FIELDS,
    RESPONSE_JSON_SCHEMA,
    resolve_external_run_target,
    validate_response_object,
)


REAL_EXECUTION_PLAN_SCHEMA_VERSION = "0.16-real-execution-plan.3"
REAL_EXECUTION_RECEIPT_SCHEMA_VERSION = "0.16-real-execution-receipt.1"
CANDIDATE_OUTPUT_SCHEMA_VERSION = "0.16-candidate-api-output.1"
PROVIDER_RAW_RESPONSE_SCHEMA_VERSION = "0.16-provider-raw-response.1"
REAL_EXECUTION_JOURNAL_SCHEMA_VERSION = "0.16-real-execution-journal.1"
PROVIDER_EXECUTION_INTERFACE_VERSION = "provider-execution-v3"
OPENAI_COMPATIBLE_BACKEND_NAME = "openai-compatible-http"
OPENAI_COMPATIBLE_BACKEND_VERSION = "openai-compatible-chat-completions-v3"
GENERIC_OPENAI_COMPATIBLE_PROFILE = "generic-openai-compatible-v1"
DEEPSEEK_V4_PRO_THINKING_JSON_PROFILE = "deepseek-v4-pro-thinking-json-v1"
DEEPSEEK_V4_PRO_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_V4_PRO_MODEL_ID = "deepseek-v4-pro"
DEEPSEEK_V4_PRO_MAX_OUTPUT_TOKENS = 4096
REAL_API_AUTHORIZATION_SCOPE = "REAL_API_DEVELOPMENT_V016_B1B1"
API_KEY_ENVIRONMENT_VARIABLE = "ENH3BENCH_API_KEY"
REAL_EXECUTION_PLAN_ID_PREFIX = "RE16"
REAL_EXECUTION_RECEIPT_ID_PREFIX = "RR16"
CANDIDATE_OUTPUT_ID_PREFIX = "CO16"
TRANSIENT_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
MAX_REAL_REQUESTS = 7
MAX_ALLOWED_RETRIES = 2
INPUT_TOKEN_RESERVATION_METHOD = "utf8_payload_byte_upper_bound_v1"

REAL_EXECUTION_PLAN_RELATIVE_PATH = Path("execution/real_execution_plan.json")
REAL_EXECUTION_JOURNAL_RELATIVE_PATH = Path("execution/real_execution_journal.json")
REAL_EXECUTION_LOCK_RELATIVE_PATH = Path("execution/real_execution.lock")
REAL_EXECUTION_RECEIPTS_RELATIVE_PATH = Path("execution/real_execution_receipts.jsonl")
PROVIDER_RAW_RESPONSES_RELATIVE_PATH = Path("provider_raw/provider_raw_responses.jsonl")
CANDIDATE_OUTPUTS_RELATIVE_PATH = Path("candidate_outputs/candidate_api_outputs.jsonl")

_WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)(?:^|[\s\"'])(?:[a-z]:[\\/]|\\\\)")
_POSIX_ABSOLUTE_PATH = re.compile(r"(?:^|[\s\"'])/(?:home|Users|var|tmp|opt|mnt|srv)/")
_SECRET_TEXT = re.compile(
    r"(?i)(?:authorization\s*[:=]\s*bearer(?:\s+\S+)?|bearer\s+sk-\S*|begin\s+private\s+key|"
    r"api[_-]?key\s*[:=]\s*[\"'][^\"']+|password\s*[:=]\s*[\"'][^\"']+)"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stable_id(prefix: str, value: dict[str, Any]) -> str:
    digest = sha256_bytes(canonical_json(value).encode("utf-8"))[:20].upper()
    return f"{prefix}_{digest}"


def _require_nonblank(value: str, error_code: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(error_code)
    return normalized


@dataclass(frozen=True)
class ExecutionBudget:
    """Hard limits checked before and during provider execution."""

    max_requests: int
    max_network_attempts: int
    max_input_tokens: int
    max_output_tokens: int
    max_total_tokens: int
    timeout_seconds: float
    max_retries: int
    max_estimated_cost: float | None = None
    currency: str | None = None

    def validate(self, *, request_count: int | None = None) -> None:
        if not isinstance(self.max_requests, int) or not 1 <= self.max_requests <= MAX_REAL_REQUESTS:
            raise ValueError("invalid_max_requests")
        if request_count is not None and request_count > self.max_requests:
            raise ValueError("request_budget_exceeded")
        for field_name in ("max_input_tokens", "max_output_tokens", "max_total_tokens"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or value <= 0:
                raise ValueError(f"invalid_{field_name}")
        if self.max_total_tokens < self.max_input_tokens or self.max_total_tokens < self.max_output_tokens:
            raise ValueError("invalid_total_token_budget")
        if not isinstance(self.timeout_seconds, (int, float)) or not math.isfinite(self.timeout_seconds):
            raise ValueError("invalid_timeout_seconds")
        if self.timeout_seconds <= 0:
            raise ValueError("invalid_timeout_seconds")
        if not isinstance(self.max_retries, int) or not 0 <= self.max_retries <= MAX_ALLOWED_RETRIES:
            raise ValueError("invalid_max_retries")
        if not isinstance(self.max_network_attempts, int):
            raise ValueError("invalid_max_network_attempts")
        if self.max_network_attempts < self.max_requests:
            raise ValueError("network_attempt_budget_below_logical_requests")
        if self.max_network_attempts > self.max_requests * (1 + self.max_retries):
            raise ValueError("network_attempt_budget_exceeds_retry_contract")
        if self.max_estimated_cost is not None:
            if not isinstance(self.max_estimated_cost, (int, float)):
                raise ValueError("invalid_max_estimated_cost")
            if not math.isfinite(self.max_estimated_cost) or self.max_estimated_cost < 0:
                raise ValueError("invalid_max_estimated_cost")
            if not str(self.currency or "").strip():
                raise ValueError("cost_budget_requires_currency")
            raise ValueError("cost_budget_requires_explicit_pricing")
        elif self.currency not in (None, ""):
            raise ValueError("currency_without_cost_budget")


@dataclass(frozen=True)
class ProviderConfiguration:
    """All provider-visible parameters that can affect generation identity."""

    endpoint: str
    model_id: str
    temperature: float | None
    top_p: float | None
    max_output_tokens: int
    seed: int | None
    response_format: str
    reasoning_effort: str | None = None
    provider_profile: str = GENERIC_OPENAI_COMPATIBLE_PROFILE
    thinking_mode: str | None = None

    def validate(self) -> None:
        endpoint_identity = safe_endpoint_identity(self.endpoint)
        _require_nonblank(self.model_id, "model_configuration_missing")
        if not isinstance(self.max_output_tokens, int) or self.max_output_tokens <= 0:
            raise ValueError("invalid_generation_max_output_tokens")
        if self.provider_profile == GENERIC_OPENAI_COMPATIBLE_PROFILE:
            if not isinstance(self.temperature, (int, float)) or not math.isfinite(self.temperature):
                raise ValueError("invalid_temperature")
            if not 0 <= self.temperature <= 2:
                raise ValueError("invalid_temperature")
            if not isinstance(self.top_p, (int, float)) or not math.isfinite(self.top_p):
                raise ValueError("invalid_top_p")
            if not 0 < self.top_p <= 1:
                raise ValueError("invalid_top_p")
            if self.seed is not None and not isinstance(self.seed, int):
                raise ValueError("invalid_seed")
            if self.response_format not in {"json_object", "json_schema"}:
                raise ValueError("invalid_response_format")
            if self.reasoning_effort not in {None, "low", "medium", "high"}:
                raise ValueError("invalid_reasoning_effort")
            if self.thinking_mode is not None:
                raise ValueError("invalid_thinking_mode")
            return
        if self.provider_profile != DEEPSEEK_V4_PRO_THINKING_JSON_PROFILE:
            raise ValueError("invalid_provider_profile")
        if endpoint_identity != DEEPSEEK_V4_PRO_ENDPOINT:
            raise ValueError("deepseek_endpoint_contract_mismatch")
        if self.model_id != DEEPSEEK_V4_PRO_MODEL_ID:
            raise ValueError("deepseek_model_contract_mismatch")
        if self.thinking_mode != "enabled":
            raise ValueError("deepseek_thinking_mode_required")
        if self.reasoning_effort != "high":
            raise ValueError("deepseek_reasoning_effort_not_canonical")
        if self.response_format != "json_object":
            raise ValueError("deepseek_json_object_required")
        if self.temperature is not None or self.top_p is not None:
            raise ValueError("deepseek_inactive_sampling_parameter_present")
        if self.seed is not None:
            raise ValueError("deepseek_seed_not_supported_for_profile")
        if self.max_output_tokens != DEEPSEEK_V4_PRO_MAX_OUTPUT_TOKENS:
            raise ValueError("deepseek_max_output_tokens_contract_mismatch")


@dataclass(frozen=True)
class TransportResponse:
    status_code: int
    body: bytes


class ProviderTransportError(RuntimeError):
    """Safe transport exception whose message never includes request material."""

    def __init__(self, safe_error_code: str, *, transient: bool) -> None:
        super().__init__(safe_error_code)
        self.safe_error_code = safe_error_code
        self.transient = transient


@runtime_checkable
class ProviderExecutionBackend(Protocol):
    backend_name: str
    backend_version: str

    def prepare_request(
        self, prompt_instance: dict[str, Any], request_envelope: dict[str, Any],
        configuration: ProviderConfiguration,
    ) -> dict[str, Any]: ...

    def execute_once(
        self, prepared_request: dict[str, Any], *, api_key: str, timeout_seconds: float,
    ) -> TransportResponse: ...

    def normalize_provider_response(
        self, response: TransportResponse, *, expected_model_id: str,
    ) -> dict[str, Any]: ...


def safe_endpoint_identity(endpoint: str) -> str:
    """Return a credential-free endpoint identity; the raw endpoint is never serialized."""

    value = _require_nonblank(endpoint, "provider_configuration_missing")
    parsed = urllib_parse.urlsplit(value)
    if parsed.scheme.casefold() != "https":
        raise ValueError("provider_endpoint_requires_https")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("unsafe_provider_endpoint")
    if parsed.query or parsed.fragment:
        raise ValueError("unsafe_provider_endpoint")
    if parsed.path.rstrip("/") != "/v1/chat/completions":
        raise ValueError("unsupported_provider_endpoint")
    hostname = parsed.hostname.casefold()
    port = f":{parsed.port}" if parsed.port and parsed.port != 443 else ""
    return f"https://{hostname}{port}/v1/chat/completions"


def endpoint_origin_hash(endpoint: str) -> str:
    return sha256_bytes(safe_endpoint_identity(endpoint).encode("utf-8"))


def _generation_parameters(configuration: ProviderConfiguration) -> dict[str, Any]:
    return {
        "temperature": (
            float(configuration.temperature) if configuration.temperature is not None else None
        ),
        "top_p": float(configuration.top_p) if configuration.top_p is not None else None,
        "max_output_tokens": configuration.max_output_tokens,
        "seed": configuration.seed,
        "response_format": configuration.response_format,
        "reasoning_effort": configuration.reasoning_effort,
        "thinking_mode": configuration.thinking_mode,
    }


def _provider_payload(prompt: dict[str, Any], configuration: ProviderConfiguration) -> dict[str, Any]:
    configuration.validate()
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
    payload: dict[str, Any] = {
        "model": configuration.model_id,
        "messages": [
            {"role": "system", "content": prompt["prompt_contract_text"]},
            {"role": "user", "content": canonical_json(user_contract)},
        ],
        "max_tokens": configuration.max_output_tokens,
    }
    if configuration.provider_profile == DEEPSEEK_V4_PRO_THINKING_JSON_PROFILE:
        payload.update({
            "response_format": {"type": "json_object"},
            "thinking": {"type": "enabled"},
            "reasoning_effort": "high",
        })
        return payload
    payload["temperature"] = float(configuration.temperature)  # type: ignore[arg-type]
    payload["top_p"] = float(configuration.top_p)  # type: ignore[arg-type]
    if configuration.seed is not None:
        payload["seed"] = configuration.seed
    if configuration.reasoning_effort is not None:
        payload["reasoning_effort"] = configuration.reasoning_effort
    if configuration.response_format == "json_schema":
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "enh3bench_v016_generation_response",
                "strict": True,
                "schema": RESPONSE_JSON_SCHEMA,
            },
        }
    else:
        payload["response_format"] = {"type": "json_object"}
    return payload


def estimate_request_input_tokens(prompt: dict[str, Any], configuration: ProviderConfiguration) -> int:
    payload_bytes = canonical_json(_provider_payload(prompt, configuration)).encode("utf-8")
    return max(1, math.ceil(len(payload_bytes) / 4))


def reserve_request_input_tokens(prompt: dict[str, Any], configuration: ProviderConfiguration) -> int:
    """Conservative provider-independent bound: at most one token per UTF-8 payload byte."""

    return len(canonical_json(_provider_payload(prompt, configuration)).encode("utf-8"))


class OpenAICompatibleHTTPBackend:
    """Minimal standard-library transport for one compatible chat-completions endpoint."""

    backend_name = OPENAI_COMPATIBLE_BACKEND_NAME
    backend_version = OPENAI_COMPATIBLE_BACKEND_VERSION

    def __init__(
        self,
        *,
        endpoint: str,
        transport: Callable[[str, bytes, dict[str, str], float], TransportResponse] | None = None,
    ) -> None:
        safe_endpoint_identity(endpoint)
        self._endpoint = endpoint
        self._transport = transport or self._stdlib_transport

    @staticmethod
    def _stdlib_transport(
        endpoint: str, body: bytes, headers: dict[str, str], timeout: float,
    ) -> TransportResponse:
        request = urllib_request.Request(endpoint, data=body, headers=headers, method="POST")
        try:
            with urllib_request.urlopen(request, timeout=timeout) as response:
                return TransportResponse(int(response.status), response.read())
        except urllib_error.HTTPError as exc:
            return TransportResponse(int(exc.code), exc.read())
        except TimeoutError as exc:
            raise ProviderTransportError("provider_timeout", transient=True) from exc
        except urllib_error.URLError as exc:
            reason = getattr(exc, "reason", None)
            transient = isinstance(reason, (TimeoutError, ConnectionResetError))
            raise ProviderTransportError(
                "provider_connection_failure" if transient else "provider_transport_failure",
                transient=transient,
            ) from exc
        except ConnectionResetError as exc:
            raise ProviderTransportError("provider_connection_reset", transient=True) from exc

    def prepare_request(
        self, prompt_instance: dict[str, Any], request_envelope: dict[str, Any],
        configuration: ProviderConfiguration,
    ) -> dict[str, Any]:
        payload = _provider_payload(prompt_instance, configuration)
        return {
            "request_envelope_id": request_envelope["request_envelope_id"],
            "request_sha256": request_envelope["request_sha256"],
            "prompt_instance_id": prompt_instance["prompt_instance_id"],
            "compiled_prompt_sha256": prompt_instance["compiled_prompt_sha256"],
            "case_id": prompt_instance["case_id"],
            "paper_id": prompt_instance["paper_id"],
            "provider_payload": payload,
            "provider_request_sha256": sha256_bytes(canonical_json(payload).encode("utf-8")),
        }

    def execute_once(
        self, prepared_request: dict[str, Any], *, api_key: str, timeout_seconds: float,
    ) -> TransportResponse:
        if not str(api_key or ""):
            raise ValueError("provider_credential_missing")
        body = canonical_json(prepared_request["provider_payload"]).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }
        return self._transport(self._endpoint, body, headers, timeout_seconds)

    def normalize_provider_response(
        self, response: TransportResponse, *, expected_model_id: str,
    ) -> dict[str, Any]:
        if response.status_code < 200 or response.status_code >= 300:
            raise ValueError(f"provider_http_status_{response.status_code}")
        try:
            value = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("provider_response_not_json") from exc
        if not isinstance(value, dict):
            raise ValueError("provider_response_not_object")
        model = value.get("model")
        if model != expected_model_id:
            raise ValueError("provider_model_mismatch")
        choices = value.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise ValueError("provider_choice_contract_mismatch")
        message = choices[0].get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise ValueError("provider_message_contract_mismatch")
        usage = value.get("usage")
        if not isinstance(usage, dict):
            raise ValueError("provider_usage_missing")
        token_values: dict[str, int] = {}
        for output_name, provider_name in (
            ("input_token_count", "prompt_tokens"),
            ("output_token_count", "completion_tokens"),
            ("total_token_count", "total_tokens"),
        ):
            token_value = usage.get(provider_name)
            if not isinstance(token_value, int) or token_value < 0:
                raise ValueError("provider_usage_invalid")
            token_values[output_name] = token_value
        if token_values["total_token_count"] != (
            token_values["input_token_count"] + token_values["output_token_count"]
        ):
            raise ValueError("provider_usage_total_mismatch")
        provider_response_id = value.get("id")
        if not isinstance(provider_response_id, str) or not provider_response_id.strip():
            raise ValueError("provider_response_id_missing")
        finish_reason = choices[0].get("finish_reason")
        if finish_reason != "stop":
            raise ValueError("provider_finish_reason_not_complete")
        return {
            "provider_response_id": provider_response_id,
            "model_id": model,
            "finish_reason": finish_reason,
            "response_content": message["content"],
            **token_values,
        }


def is_retryable_http_status(status_code: int) -> bool:
    return status_code in TRANSIENT_HTTP_STATUSES


def _validate_b1b0_request_binding(
    prompt: dict[str, Any], envelope: dict[str, Any], generation_run_name: str,
) -> None:
    if set(prompt) != COMPILED_PROMPT_FIELDS:
        raise ValueError("compiled_prompt_contract_mismatch")
    if set(envelope) != REQUEST_ENVELOPE_FIELDS:
        raise ValueError("request_envelope_contract_mismatch")
    prompt_stable = {key: value for key, value in prompt.items() if key != "compiled_prompt_sha256"}
    if prompt.get("compiled_prompt_sha256") != sha256_bytes(
        canonical_json(prompt_stable).encode("utf-8")
    ):
        raise ValueError("compiled_prompt_sha_binding_mismatch")
    if prompt.get("response_json_schema") != RESPONSE_JSON_SCHEMA:
        raise ValueError("response_schema_contract_mismatch")
    for field in ("prompt_instance_id", "case_id", "paper_id", "compiled_prompt_sha256"):
        if envelope.get(field) != prompt.get(field):
            raise ValueError(f"{field}_binding_mismatch")
    stable = {
        "schema_version": envelope["schema_version"],
        "backend_interface_version": envelope["backend_interface_version"],
        "prompt_instance_id": envelope["prompt_instance_id"],
        "case_id": envelope["case_id"],
        "paper_id": envelope["paper_id"],
        "backend_name": envelope["backend_name"],
        "backend_version": envelope["backend_version"],
        "prompt_version": envelope["prompt_version"],
        "compiled_prompt_sha256": envelope["compiled_prompt_sha256"],
        "execution_mode": envelope["execution_mode"],
    }
    expected_request_sha = sha256_bytes(canonical_json(stable).encode("utf-8"))
    if envelope.get("request_sha256") != expected_request_sha:
        raise ValueError("request_sha_binding_mismatch")
    expected_request_id = _stable_id("RQ16", stable)
    if envelope.get("request_envelope_id") != expected_request_id:
        raise ValueError("request_identity_binding_mismatch")
    if envelope.get("generation_run_name") != generation_run_name:
        raise ValueError("generation_run_name_binding_mismatch")


def _load_development_contract(
    run_dir: Path, generation_run_name: str,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    manifest = read_json(run_dir / "manifests/generation_run_manifest.json")
    selection = read_json(run_dir / "pilot/pilot_selection_manifest.json")
    prompts = read_jsonl(run_dir / "prompts/compiled_prompt_instances.jsonl")
    envelopes = read_jsonl(run_dir / "execution/request_envelopes.jsonl")
    if manifest.get("generation_run_name") != generation_run_name:
        raise ValueError("generation_run_name_binding_mismatch")
    if manifest.get("pilot_selection_id") != selection.get("pilot_selection_id"):
        raise ValueError("pilot_selection_identity_binding_mismatch")
    if selection.get("selected_case_count") != PILOT_CASE_COUNT:
        raise ValueError("development_selection_requires_seven_cases")
    if selection.get("development_case_count") != PILOT_CASE_COUNT:
        raise ValueError("development_only_gate_failed")
    if selection.get("holdout_case_count") != 0:
        raise ValueError("holdout_execution_forbidden")
    selected_cases = selection.get("selected_cases")
    if not isinstance(selected_cases, list) or len(selected_cases) != PILOT_CASE_COUNT:
        raise ValueError("development_selection_contract_mismatch")
    if any("development_split_only" not in (row.get("selection_reasons") or []) for row in selected_cases):
        raise ValueError("development_only_gate_failed")
    selected_ids = [row.get("case_id") for row in selected_cases]
    if len(set(selected_ids)) != PILOT_CASE_COUNT or any(not str(value or "") for value in selected_ids):
        raise ValueError("development_case_identity_invalid")
    if len(prompts) != PILOT_CASE_COUNT or len(envelopes) != PILOT_CASE_COUNT:
        raise ValueError("real_execution_requires_seven_requests")
    prompt_ids = [row.get("case_id") for row in prompts]
    envelope_ids = [row.get("case_id") for row in envelopes]
    if prompt_ids != selected_ids or envelope_ids != selected_ids:
        raise ValueError("unknown_or_unapproved_case")
    for prompt, envelope in zip(prompts, envelopes):
        _validate_b1b0_request_binding(prompt, envelope, generation_run_name)
    return manifest, selection, prompts, envelopes


def _plan_identity_payload(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": plan["schema_version"],
        "generation_run_id": plan["generation_run_id"],
        "pilot_selection_id": plan["pilot_selection_id"],
        "provider_backend_name": plan["provider_backend_name"],
        "provider_backend_version": plan["provider_backend_version"],
        "provider_profile": plan["provider_profile"],
        "model_id": plan["model_id"],
        "endpoint_origin_hash": plan["endpoint_origin_hash"],
        "request_count": plan["request_count"],
        "development_case_count": plan["development_case_count"],
        "holdout_case_count": plan["holdout_case_count"],
        "max_requests": plan["max_requests"],
        "max_network_attempts": plan["max_network_attempts"],
        "max_input_tokens": plan["max_input_tokens"],
        "max_output_tokens": plan["max_output_tokens"],
        "max_total_tokens": plan["max_total_tokens"],
        "max_estimated_cost": plan["max_estimated_cost"],
        "currency": plan["currency"],
        "timeout_seconds": plan["timeout_seconds"],
        "max_retries": plan["max_retries"],
        "input_token_reservation_method": plan["input_token_reservation_method"],
        "reserved_input_tokens_per_request": plan["reserved_input_tokens_per_request"],
        "reserved_input_tokens_total": plan["reserved_input_tokens_total"],
        "reserved_output_tokens_total": plan["reserved_output_tokens_total"],
        "reserved_total_tokens": plan["reserved_total_tokens"],
        "authorization_scope": plan["authorization_scope"],
        "generation_parameters": plan["generation_parameters"],
        "approved_case_ids": plan["approved_case_ids"],
    }


def prepare_real_execution(
    *,
    generation_run_name: str,
    generation_root: str | Path,
    configuration: ProviderConfiguration,
    budget: ExecutionBudget,
    resume: bool = False,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Prepare the stable execution plan without reading credentials or using a network."""

    configuration.validate()
    budget.validate(request_count=PILOT_CASE_COUNT)
    run_dir = resolve_external_run_target(generation_root, generation_run_name)
    manifest, selection, prompts, _ = _load_development_contract(run_dir, generation_run_name)
    estimated_input_tokens = sum(estimate_request_input_tokens(row, configuration) for row in prompts)
    estimated_total_tokens = estimated_input_tokens + configuration.max_output_tokens * PILOT_CASE_COUNT
    per_request_reservations = [reserve_request_input_tokens(row, configuration) for row in prompts]
    retry_slots = budget.max_network_attempts - PILOT_CASE_COUNT
    reserved_input_total = sum(per_request_reservations) + retry_slots * max(per_request_reservations)
    reserved_output_total = configuration.max_output_tokens * budget.max_network_attempts
    reserved_total = reserved_input_total + reserved_output_total
    if reserved_input_total > budget.max_input_tokens:
        raise ValueError("reserved_input_token_budget_preflight_failed")
    if reserved_output_total > budget.max_output_tokens:
        raise ValueError("reserved_output_token_budget_preflight_failed")
    if reserved_total > budget.max_total_tokens:
        raise ValueError("reserved_total_token_budget_preflight_failed")
    plan = {
        "schema_version": REAL_EXECUTION_PLAN_SCHEMA_VERSION,
        "provider_interface_version": PROVIDER_EXECUTION_INTERFACE_VERSION,
        "generation_run_id": manifest["generation_run_id"],
        "pilot_selection_id": selection["pilot_selection_id"],
        "provider_backend_name": OPENAI_COMPATIBLE_BACKEND_NAME,
        "provider_backend_version": OPENAI_COMPATIBLE_BACKEND_VERSION,
        "provider_profile": configuration.provider_profile,
        "model_id": configuration.model_id,
        "endpoint_origin_hash": endpoint_origin_hash(configuration.endpoint),
        "request_count": PILOT_CASE_COUNT,
        "development_case_count": PILOT_CASE_COUNT,
        "holdout_case_count": 0,
        "approved_case_ids": [row["case_id"] for row in selection["selected_cases"]],
        "estimated_input_tokens": estimated_input_tokens,
        "estimated_max_output_tokens": configuration.max_output_tokens * PILOT_CASE_COUNT,
        "estimated_max_total_tokens": estimated_total_tokens,
        "input_token_reservation_method": INPUT_TOKEN_RESERVATION_METHOD,
        "reserved_input_tokens_per_request": per_request_reservations,
        "reserved_input_tokens_total": reserved_input_total,
        "reserved_output_tokens_total": reserved_output_total,
        "reserved_total_tokens": reserved_total,
        "max_requests": budget.max_requests,
        "max_network_attempts": budget.max_network_attempts,
        "max_input_tokens": budget.max_input_tokens,
        "max_output_tokens": budget.max_output_tokens,
        "max_total_tokens": budget.max_total_tokens,
        "max_estimated_cost": budget.max_estimated_cost,
        "currency": budget.currency,
        "timeout_seconds": float(budget.timeout_seconds),
        "max_retries": budget.max_retries,
        "authorization_scope": REAL_API_AUTHORIZATION_SCOPE,
        "generation_parameters": _generation_parameters(configuration),
        "created_at_utc": created_at_utc or _utc_now(),
    }
    plan["execution_plan_id"] = _stable_id(REAL_EXECUTION_PLAN_ID_PREFIX, _plan_identity_payload(plan))
    plan_path = run_dir / REAL_EXECUTION_PLAN_RELATIVE_PATH
    journal_path = run_dir / REAL_EXECUTION_JOURNAL_RELATIVE_PATH
    if plan_path.exists():
        existing = read_json(plan_path)
        if not resume:
            raise FileExistsError("real_execution_plan_already_exists")
        if existing.get("execution_plan_id") != plan["execution_plan_id"]:
            raise ValueError("resume_execution_plan_mismatch")
        if not journal_path.is_file():
            raise ValueError("resume_execution_journal_missing")
        return existing
    write_json(plan_path, plan)
    write_json(journal_path, {
        "schema_version": REAL_EXECUTION_JOURNAL_SCHEMA_VERSION,
        "execution_plan_id": plan["execution_plan_id"],
        "state": "prepared",
        "logical_request_count": 0,
        "network_attempt_count": 0,
        "reserved_input_tokens_consumed": 0,
        "reserved_output_tokens_consumed": 0,
        "reserved_total_tokens_consumed": 0,
        "attempts": [],
        "updated_at_utc": created_at_utc or _utc_now(),
    })
    return plan


def validate_execution_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version", "provider_interface_version", "execution_plan_id",
        "generation_run_id", "pilot_selection_id", "provider_backend_name",
        "provider_backend_version", "provider_profile", "model_id", "endpoint_origin_hash", "request_count",
        "development_case_count", "holdout_case_count", "approved_case_ids",
        "estimated_input_tokens", "estimated_max_output_tokens", "estimated_max_total_tokens",
        "input_token_reservation_method", "reserved_input_tokens_per_request",
        "reserved_input_tokens_total", "reserved_output_tokens_total", "reserved_total_tokens",
        "max_requests", "max_network_attempts", "max_input_tokens", "max_output_tokens", "max_total_tokens",
        "max_estimated_cost", "currency", "timeout_seconds", "max_retries",
        "authorization_scope", "generation_parameters", "created_at_utc",
    }
    if not isinstance(plan, dict):
        return ["execution_plan_not_object"]
    for field in sorted(required - set(plan)):
        errors.append(f"execution_plan_missing:{field}")
    for field in sorted(set(plan) - required):
        errors.append(f"execution_plan_unknown:{field}")
    if errors:
        return errors
    if plan["schema_version"] != REAL_EXECUTION_PLAN_SCHEMA_VERSION:
        errors.append("execution_plan_schema_mismatch")
    if plan["provider_interface_version"] != PROVIDER_EXECUTION_INTERFACE_VERSION:
        errors.append("provider_interface_version_mismatch")
    if plan["provider_backend_name"] != OPENAI_COMPATIBLE_BACKEND_NAME:
        errors.append("provider_backend_name_mismatch")
    if plan["provider_backend_version"] != OPENAI_COMPATIBLE_BACKEND_VERSION:
        errors.append("provider_backend_version_mismatch")
    if plan["authorization_scope"] != REAL_API_AUTHORIZATION_SCOPE:
        errors.append("authorization_scope_mismatch")
    if plan["request_count"] != PILOT_CASE_COUNT or plan["development_case_count"] != PILOT_CASE_COUNT:
        errors.append("development_request_count_mismatch")
    if plan["holdout_case_count"] != 0:
        errors.append("holdout_execution_forbidden")
    if not isinstance(plan["approved_case_ids"], list) or len(set(plan["approved_case_ids"])) != PILOT_CASE_COUNT:
        errors.append("approved_case_identity_mismatch")
    if plan["input_token_reservation_method"] != INPUT_TOKEN_RESERVATION_METHOD:
        errors.append("input_token_reservation_method_mismatch")
    try:
        parameters = plan["generation_parameters"]
        expected_parameter_fields = {
            "thinking_mode", "reasoning_effort", "response_format", "max_output_tokens",
            "temperature", "top_p", "seed",
        }
        if not isinstance(parameters, dict) or set(parameters) != expected_parameter_fields:
            errors.append("generation_parameters_contract_mismatch")
        else:
            validation_endpoint = (
                DEEPSEEK_V4_PRO_ENDPOINT
                if plan["provider_profile"] == DEEPSEEK_V4_PRO_THINKING_JSON_PROFILE
                else "https://offline-validation.invalid/v1/chat/completions"
            )
            ProviderConfiguration(
                endpoint=validation_endpoint,
                model_id=plan["model_id"],
                temperature=parameters["temperature"],
                top_p=parameters["top_p"],
                max_output_tokens=parameters["max_output_tokens"],
                seed=parameters["seed"],
                response_format=parameters["response_format"],
                reasoning_effort=parameters["reasoning_effort"],
                provider_profile=plan["provider_profile"],
                thinking_mode=parameters["thinking_mode"],
            ).validate()
            if (
                plan["provider_profile"] == DEEPSEEK_V4_PRO_THINKING_JSON_PROFILE
                and plan["endpoint_origin_hash"] != endpoint_origin_hash(DEEPSEEK_V4_PRO_ENDPOINT)
            ):
                errors.append("deepseek_endpoint_identity_mismatch")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    try:
        reservations = plan["reserved_input_tokens_per_request"]
        if (
            not isinstance(reservations, list) or len(reservations) != PILOT_CASE_COUNT
            or any(not isinstance(value, int) or value <= 0 for value in reservations)
        ):
            errors.append("reserved_input_tokens_per_request_invalid")
        else:
            retry_slots = plan["max_network_attempts"] - plan["max_requests"]
            expected_input = sum(reservations) + retry_slots * max(reservations)
            if plan["reserved_input_tokens_total"] != expected_input:
                errors.append("reserved_input_tokens_total_mismatch")
            expected_output = plan["generation_parameters"]["max_output_tokens"] * plan["max_network_attempts"]
            if plan["reserved_output_tokens_total"] != expected_output:
                errors.append("reserved_output_tokens_total_mismatch")
            if plan["reserved_total_tokens"] != expected_input + expected_output:
                errors.append("reserved_total_tokens_mismatch")
            if plan["reserved_input_tokens_total"] > plan["max_input_tokens"]:
                errors.append("reserved_input_token_budget_exceeded")
            if plan["reserved_output_tokens_total"] > plan["max_output_tokens"]:
                errors.append("reserved_output_token_budget_exceeded")
            if plan["reserved_total_tokens"] > plan["max_total_tokens"]:
                errors.append("reserved_total_token_budget_exceeded")
    except (KeyError, TypeError, ValueError):
        errors.append("token_reservation_contract_invalid")
    try:
        ExecutionBudget(
            max_requests=plan["max_requests"], max_network_attempts=plan["max_network_attempts"],
            max_input_tokens=plan["max_input_tokens"],
            max_output_tokens=plan["max_output_tokens"], max_total_tokens=plan["max_total_tokens"],
            timeout_seconds=plan["timeout_seconds"], max_retries=plan["max_retries"],
            max_estimated_cost=plan["max_estimated_cost"], currency=plan["currency"],
        ).validate(request_count=plan["request_count"])
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    try:
        expected = _stable_id(REAL_EXECUTION_PLAN_ID_PREFIX, _plan_identity_payload(plan))
        if plan["execution_plan_id"] != expected:
            errors.append("execution_plan_identity_mismatch")
    except (KeyError, TypeError):
        errors.append("execution_plan_identity_unavailable")
    serialized = canonical_json(plan)
    if _SECRET_TEXT.search(serialized):
        errors.append("secret_in_execution_plan")
    if _WINDOWS_ABSOLUTE_PATH.search(serialized) or _POSIX_ABSOLUTE_PATH.search(serialized):
        errors.append("absolute_path_in_execution_plan")
    return errors


def _configuration_from_plan(endpoint: str, plan: dict[str, Any]) -> ProviderConfiguration:
    parameters = plan["generation_parameters"]
    configuration = ProviderConfiguration(
        endpoint=endpoint,
        model_id=plan["model_id"],
        temperature=parameters["temperature"],
        top_p=parameters["top_p"],
        max_output_tokens=parameters["max_output_tokens"],
        seed=parameters["seed"],
        response_format=parameters["response_format"],
        reasoning_effort=parameters["reasoning_effort"],
        provider_profile=plan["provider_profile"],
        thinking_mode=parameters["thinking_mode"],
    )
    configuration.validate()
    if endpoint_origin_hash(endpoint) != plan["endpoint_origin_hash"]:
        raise ValueError("provider_endpoint_identity_mismatch")
    return configuration


def authorize_real_execution(
    *, execute_real_api: bool, authorization: str | None,
) -> None:
    if not execute_real_api or authorization != REAL_API_AUTHORIZATION_SCOPE:
        raise ValueError("real_api_execution_not_authorized")


def _parse_candidate_response(content: str, prompt: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    if content.strip().startswith("```") or content.strip().endswith("```"):
        raise ValueError("markdown_fence_forbidden")
    try:
        value = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("model_output_malformed_json") from exc
    errors = validate_response_object(value)
    if errors:
        raise ValueError("model_output_schema_invalid:" + ";".join(errors))
    allowed_spans = set(prompt["allowed_source_span_ids"])
    allowed_links = set(prompt["allowed_evidence_link_ids"])
    claim_ids = {claim["claim_id"] for claim in value["claims"]}
    citation_ids = {citation["citation_id"] for citation in value["citations"]}
    allowlist_errors: list[str] = []
    if len(claim_ids) != len(value["claims"]):
        allowlist_errors.append("duplicate_claim_id")
    if len(citation_ids) != len(value["citations"]):
        allowlist_errors.append("duplicate_citation_id")
    for claim in value["claims"]:
        if not set(claim["supporting_source_span_ids"]).issubset(allowed_spans):
            allowlist_errors.append("claim_source_span_not_allowed")
        if not set(claim["supporting_evidence_link_ids"]).issubset(allowed_links):
            allowlist_errors.append("claim_evidence_link_not_allowed")
    for citation in value["citations"]:
        if not set(citation["claim_ids"]).issubset(claim_ids):
            allowlist_errors.append("citation_claim_not_found")
        if not set(citation["source_span_ids"]).issubset(allowed_spans):
            allowlist_errors.append("citation_source_span_not_allowed")
        if not set(citation["evidence_link_ids"]).issubset(allowed_links):
            allowlist_errors.append("citation_evidence_link_not_allowed")
    if allowlist_errors:
        raise ValueError("citation_allowlist_invalid:" + ";".join(sorted(set(allowlist_errors))))
    return value, []


def _safe_raw_response(
    *, plan: dict[str, Any], prepared: dict[str, Any], normalized: dict[str, Any],
    http_status: int, attempt_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": PROVIDER_RAW_RESPONSE_SCHEMA_VERSION,
        "execution_plan_id": plan["execution_plan_id"],
        "request_envelope_id": prepared["request_envelope_id"],
        "prompt_instance_id": prepared["prompt_instance_id"],
        "case_id": prepared["case_id"],
        "provider_response_id": normalized["provider_response_id"],
        "model_id": normalized["model_id"],
        "finish_reason": normalized["finish_reason"],
        "http_status": http_status,
        "attempt_count": attempt_count,
        "input_token_count": normalized["input_token_count"],
        "output_token_count": normalized["output_token_count"],
        "total_token_count": normalized["total_token_count"],
        "response_content": _redact_secret_text(normalized["response_content"]),
    }


def _redact_secret_text(value: str) -> str:
    return _SECRET_TEXT.sub("[REDACTED_SENSITIVE_TEXT]", str(value))


def _safe_error_code(exc: BaseException) -> str:
    value = str(exc).split(":", 1)[0].strip()
    return value if re.fullmatch(r"[a-z0-9_\-]+", value) else "provider_execution_failure"


def _receipt(
    *, plan: dict[str, Any], prepared: dict[str, Any], attempt_count: int,
    http_status: int | None, normalized: dict[str, Any] | None,
    parse_success: bool, schema_success: bool, allowlist_success: bool,
    started_at_utc: str, completed_at_utc: str, safe_error_code: str | None,
) -> dict[str, Any]:
    stable = {
        "schema_version": REAL_EXECUTION_RECEIPT_SCHEMA_VERSION,
        "execution_plan_id": plan["execution_plan_id"],
        "request_envelope_id": prepared["request_envelope_id"],
        "prompt_instance_id": prepared["prompt_instance_id"],
        "case_id": prepared["case_id"],
        "backend_name": plan["provider_backend_name"],
        "backend_version": plan["provider_backend_version"],
        "model_id": plan["model_id"],
        "attempt_count": attempt_count,
        "execution_status": "candidate_created" if allowlist_success else "failed",
        "transport_status": "success" if normalized is not None else "failed",
        "http_status": http_status,
        "network_call_performed": attempt_count > 0,
        "provider_response_received": normalized is not None,
        "model_output_generated": normalized is not None,
        "parse_success": parse_success,
        "schema_success": schema_success,
        "allowlist_success": allowlist_success,
        "input_token_count": normalized["input_token_count"] if normalized else 0,
        "output_token_count": normalized["output_token_count"] if normalized else 0,
        "total_token_count": normalized["total_token_count"] if normalized else 0,
        "safe_error_code": safe_error_code,
        "request_sha256": prepared["request_sha256"],
        "compiled_prompt_sha256": prepared["compiled_prompt_sha256"],
        "provider_request_sha256": prepared["provider_request_sha256"],
    }
    return {
        **stable,
        "real_execution_receipt_id": _stable_id(REAL_EXECUTION_RECEIPT_ID_PREFIX, stable),
        "started_at_utc": started_at_utc,
        "completed_at_utc": completed_at_utc,
    }


def _candidate_output(
    *, plan: dict[str, Any], receipt: dict[str, Any], prepared: dict[str, Any],
    response_object: dict[str, Any], created_at_utc: str,
) -> dict[str, Any]:
    stable = {
        "schema_version": CANDIDATE_OUTPUT_SCHEMA_VERSION,
        "execution_plan_id": plan["execution_plan_id"],
        "real_execution_receipt_id": receipt["real_execution_receipt_id"],
        "request_envelope_id": prepared["request_envelope_id"],
        "prompt_instance_id": prepared["prompt_instance_id"],
        "case_id": prepared["case_id"],
        "paper_id": prepared["paper_id"],
        "model_id": plan["model_id"],
        "response_sha256": sha256_bytes(canonical_json(response_object).encode("utf-8")),
        "import_status": "not_imported",
    }
    return {
        **stable,
        "candidate_output_id": _stable_id(CANDIDATE_OUTPUT_ID_PREFIX, stable),
        "response_object": response_object,
        "created_at_utc": created_at_utc,
    }


def _failed_receipt(
    *, plan: dict[str, Any], prepared: dict[str, Any], attempt_count: int,
    response: TransportResponse | None, normalized: dict[str, Any] | None,
    started_at_utc: str, completed_at_utc: str, safe_error_code: str,
) -> dict[str, Any]:
    stable = {
        "schema_version": REAL_EXECUTION_RECEIPT_SCHEMA_VERSION,
        "execution_plan_id": plan["execution_plan_id"],
        "request_envelope_id": prepared["request_envelope_id"],
        "prompt_instance_id": prepared["prompt_instance_id"],
        "case_id": prepared["case_id"],
        "backend_name": plan["provider_backend_name"],
        "backend_version": plan["provider_backend_version"],
        "model_id": plan["model_id"],
        "attempt_count": attempt_count,
        "execution_status": "failed",
        "transport_status": (
            "transport_error" if response is None else
            "http_error" if not 200 <= response.status_code < 300 else
            "response_invalid"
        ),
        "http_status": response.status_code if response is not None else None,
        "network_call_performed": attempt_count > 0,
        "provider_response_received": response is not None,
        "model_output_generated": normalized is not None,
        "parse_success": False,
        "schema_success": False,
        "allowlist_success": False,
        "input_token_count": normalized["input_token_count"] if normalized else 0,
        "output_token_count": normalized["output_token_count"] if normalized else 0,
        "total_token_count": normalized["total_token_count"] if normalized else 0,
        "safe_error_code": safe_error_code,
        "request_sha256": prepared["request_sha256"],
        "compiled_prompt_sha256": prepared["compiled_prompt_sha256"],
        "provider_request_sha256": prepared["provider_request_sha256"],
    }
    return {
        **stable,
        "real_execution_receipt_id": _stable_id(REAL_EXECUTION_RECEIPT_ID_PREFIX, stable),
        "started_at_utc": started_at_utc,
        "completed_at_utc": completed_at_utc,
    }


def _safe_failure_raw_response(
    *, plan: dict[str, Any], prepared: dict[str, Any], attempt_count: int,
    response: TransportResponse | None, normalized: dict[str, Any] | None,
    safe_error_code: str,
) -> dict[str, Any]:
    return {
        "schema_version": PROVIDER_RAW_RESPONSE_SCHEMA_VERSION,
        "execution_plan_id": plan["execution_plan_id"],
        "request_envelope_id": prepared["request_envelope_id"],
        "prompt_instance_id": prepared["prompt_instance_id"],
        "case_id": prepared["case_id"],
        "provider_response_id": normalized["provider_response_id"] if normalized else "",
        "model_id": normalized["model_id"] if normalized else plan["model_id"],
        "finish_reason": normalized["finish_reason"] if normalized else "",
        "http_status": response.status_code if response is not None else None,
        "attempt_count": attempt_count,
        "input_token_count": normalized["input_token_count"] if normalized else 0,
        "output_token_count": normalized["output_token_count"] if normalized else 0,
        "total_token_count": normalized["total_token_count"] if normalized else 0,
        "response_content": _redact_secret_text(normalized["response_content"]) if normalized else "",
        "safe_error_code": safe_error_code,
    }


def _serialize_safe(rows: list[dict[str, Any]]) -> None:
    serialized = "\n".join(canonical_json(row) for row in rows)
    if _SECRET_TEXT.search(serialized):
        raise ValueError("secret_in_serialized_artifact")
    if _WINDOWS_ABSOLUTE_PATH.search(serialized) or _POSIX_ABSOLUTE_PATH.search(serialized):
        raise ValueError("absolute_path_in_serialized_artifact")


_JOURNAL_FIELDS = frozenset({
    "schema_version", "execution_plan_id", "state", "logical_request_count",
    "network_attempt_count", "reserved_input_tokens_consumed",
    "reserved_output_tokens_consumed", "reserved_total_tokens_consumed",
    "attempts", "updated_at_utc",
})
_ATTEMPT_FIELDS = frozenset({
    "execution_plan_id", "request_envelope_id", "prompt_instance_id", "case_id",
    "paper_id", "request_sha256", "compiled_prompt_sha256", "provider_request_sha256",
    "attempt_number", "global_network_attempt_number", "reserved_input_tokens",
    "reserved_output_tokens", "reserved_total_tokens", "state", "started_at_utc",
    "completed_at_utc", "http_status", "transient", "safe_error_code",
    "terminal_artifacts",
})
_RECEIPT_FIELDS = frozenset({
    "schema_version", "execution_plan_id", "request_envelope_id", "prompt_instance_id",
    "case_id", "backend_name", "backend_version", "model_id", "attempt_count",
    "execution_status", "transport_status", "http_status", "network_call_performed",
    "provider_response_received", "model_output_generated", "parse_success",
    "schema_success", "allowlist_success", "input_token_count", "output_token_count",
    "total_token_count", "safe_error_code", "request_sha256", "compiled_prompt_sha256",
    "provider_request_sha256", "real_execution_receipt_id", "started_at_utc",
    "completed_at_utc",
})
_CANDIDATE_FIELDS = frozenset({
    "schema_version", "execution_plan_id", "real_execution_receipt_id",
    "request_envelope_id", "prompt_instance_id", "case_id", "paper_id", "model_id",
    "response_sha256", "import_status", "candidate_output_id", "response_object",
    "created_at_utc",
})
_RAW_SUCCESS_FIELDS = frozenset({
    "schema_version", "execution_plan_id", "request_envelope_id", "prompt_instance_id",
    "case_id", "provider_response_id", "model_id", "finish_reason", "http_status",
    "attempt_count", "input_token_count", "output_token_count", "total_token_count",
    "response_content",
})
_RAW_FAILURE_FIELDS = _RAW_SUCCESS_FIELDS | {"safe_error_code"}


def _configuration_parameters_from_plan(plan: dict[str, Any]) -> ProviderConfiguration:
    parameters = plan["generation_parameters"]
    return ProviderConfiguration(
        endpoint=(
            DEEPSEEK_V4_PRO_ENDPOINT
            if plan["provider_profile"] == DEEPSEEK_V4_PRO_THINKING_JSON_PROFILE
            else "https://offline-validation.invalid/v1/chat/completions"
        ),
        model_id=plan["model_id"], temperature=parameters["temperature"],
        top_p=parameters["top_p"], max_output_tokens=parameters["max_output_tokens"],
        seed=parameters["seed"], response_format=parameters["response_format"],
        reasoning_effort=parameters["reasoning_effort"],
        provider_profile=plan["provider_profile"], thinking_mode=parameters["thinking_mode"],
    )


def _expected_provider_request_sha(
    prompt: dict[str, Any], configuration: ProviderConfiguration,
) -> str:
    return sha256_bytes(canonical_json(_provider_payload(prompt, configuration)).encode("utf-8"))


def _validate_plan_reservations_for_prompts(
    plan: dict[str, Any], prompts: list[dict[str, Any]], configuration: ProviderConfiguration,
) -> None:
    expected = [reserve_request_input_tokens(row, configuration) for row in prompts]
    if plan.get("reserved_input_tokens_per_request") != expected:
        raise ValueError("execution_plan_input_reservation_binding_mismatch")
    retry_slots = plan["max_network_attempts"] - plan["max_requests"]
    expected_input_total = sum(expected) + retry_slots * max(expected)
    expected_output_total = configuration.max_output_tokens * plan["max_network_attempts"]
    if plan.get("reserved_input_tokens_total") != expected_input_total:
        raise ValueError("execution_plan_reserved_input_total_mismatch")
    if plan.get("reserved_output_tokens_total") != expected_output_total:
        raise ValueError("execution_plan_reserved_output_total_mismatch")
    if plan.get("reserved_total_tokens") != expected_input_total + expected_output_total:
        raise ValueError("execution_plan_reserved_total_mismatch")


def _receipt_stable(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row[key] for key in _RECEIPT_FIELDS
        if key not in {"real_execution_receipt_id", "started_at_utc", "completed_at_utc"}
    }


def _candidate_stable(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row[key] for key in _CANDIDATE_FIELDS
        if key not in {"candidate_output_id", "response_object", "created_at_utc"}
    }


def _write_journal(path: Path, journal: dict[str, Any]) -> None:
    journal["updated_at_utc"] = _utc_now()
    _serialize_safe([journal])
    write_json(path, journal)


def _start_attempt(
    *, journal_path: Path, journal: dict[str, Any], plan: dict[str, Any],
    prepared: dict[str, Any], attempt_number: int, reserved_input_tokens: int,
    reserved_output_tokens: int,
) -> None:
    if journal["network_attempt_count"] >= plan["max_network_attempts"]:
        raise ValueError("network_attempt_budget_exhausted")
    next_input = journal["reserved_input_tokens_consumed"] + reserved_input_tokens
    next_output = journal["reserved_output_tokens_consumed"] + reserved_output_tokens
    next_total = journal["reserved_total_tokens_consumed"] + reserved_input_tokens + reserved_output_tokens
    if next_input > plan["max_input_tokens"]:
        raise ValueError("remaining_input_token_reservation_insufficient")
    if next_output > plan["max_output_tokens"]:
        raise ValueError("remaining_output_token_reservation_insufficient")
    if next_total > plan["max_total_tokens"]:
        raise ValueError("remaining_total_token_reservation_insufficient")
    global_attempt = journal["network_attempt_count"] + 1
    record = {
        "execution_plan_id": plan["execution_plan_id"],
        "request_envelope_id": prepared["request_envelope_id"],
        "prompt_instance_id": prepared["prompt_instance_id"],
        "case_id": prepared["case_id"],
        "paper_id": prepared["paper_id"],
        "request_sha256": prepared["request_sha256"],
        "compiled_prompt_sha256": prepared["compiled_prompt_sha256"],
        "provider_request_sha256": prepared["provider_request_sha256"],
        "attempt_number": attempt_number,
        "global_network_attempt_number": global_attempt,
        "reserved_input_tokens": reserved_input_tokens,
        "reserved_output_tokens": reserved_output_tokens,
        "reserved_total_tokens": reserved_input_tokens + reserved_output_tokens,
        "state": "attempt_started",
        "started_at_utc": _utc_now(),
        "completed_at_utc": None,
        "http_status": None,
        "transient": None,
        "safe_error_code": None,
        "terminal_artifacts": None,
    }
    journal["attempts"].append(record)
    journal["state"] = "attempt_started"
    journal["network_attempt_count"] = global_attempt
    journal["reserved_input_tokens_consumed"] = next_input
    journal["reserved_output_tokens_consumed"] = next_output
    journal["reserved_total_tokens_consumed"] = next_total
    _write_journal(journal_path, journal)


def _finish_attempt(
    *, journal_path: Path, journal: dict[str, Any], state: str,
    http_status: int | None, transient: bool, safe_error_code: str | None,
    terminal_artifacts: dict[str, Any] | None,
) -> None:
    if state not in {"terminal_success", "terminal_failure"}:
        raise ValueError("invalid_attempt_terminal_state")
    record = journal["attempts"][-1]
    if record.get("state") != "attempt_started":
        raise ValueError("attempt_terminal_transition_invalid")
    record.update({
        "state": state,
        "completed_at_utc": _utc_now(),
        "http_status": http_status,
        "transient": transient,
        "safe_error_code": safe_error_code,
        "terminal_artifacts": terminal_artifacts,
    })
    journal["state"] = state
    if state == "terminal_success":
        journal["logical_request_count"] += 1
    _write_journal(journal_path, journal)


def _materialized_rows(journal: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    receipts: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for attempt in journal["attempts"]:
        artifacts = attempt.get("terminal_artifacts")
        if not isinstance(artifacts, dict):
            continue
        if artifacts.get("receipt") is not None:
            receipts.append(artifacts["receipt"])
        if artifacts.get("raw_response") is not None:
            raw.append(artifacts["raw_response"])
        if artifacts.get("candidate_output") is not None:
            candidates.append(artifacts["candidate_output"])
    return receipts, raw, candidates


def _materialize_journal(run_dir: Path, journal: dict[str, Any]) -> None:
    receipts, raw, candidates = _materialized_rows(journal)
    _serialize_safe(receipts + raw + candidates)
    write_jsonl(run_dir / REAL_EXECUTION_RECEIPTS_RELATIVE_PATH, receipts)
    write_jsonl(run_dir / PROVIDER_RAW_RESPONSES_RELATIVE_PATH, raw)
    write_jsonl(run_dir / CANDIDATE_OUTPUTS_RELATIVE_PATH, candidates)


def _journal_stage(journal: dict[str, Any]) -> str:
    state = journal.get("state")
    if state == "prepared" and not journal.get("attempts"):
        return "PREPARED"
    if state == "completed":
        return "COMPLETED"
    if state == "attempt_started":
        return "INDETERMINATE"
    if state == "terminal_failure":
        return "FAILED"
    if state == "terminal_success":
        return "PARTIAL"
    return "CORRUPT"


def _acquire_real_execution_lock(run_dir: Path) -> tuple[Path, int]:
    """Atomically create and retain the external-runtime execution lock."""

    lock_path = run_dir / REAL_EXECUTION_LOCK_RELATIVE_PATH
    try:
        descriptor = os.open(
            lock_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
        )
    except FileExistsError as exc:
        raise ValueError("real_execution_lock_held") from exc
    try:
        os.write(descriptor, b"orphaned_lock_requires_manual_review\n")
        os.fsync(descriptor)
    except BaseException:
        os.close(descriptor)
        lock_path.unlink()
        raise
    return lock_path, descriptor


def _release_real_execution_lock(lock_path: Path, descriptor: int) -> None:
    os.close(descriptor)
    lock_path.unlink()


def run_real_execution(
    *,
    generation_run_name: str,
    generation_root: str | Path,
    endpoint: str,
    execute_real_api: bool = False,
    authorization: str | None = None,
    credential_reader: Callable[[str], str | None] | None = None,
    backend: ProviderExecutionBackend | None = None,
    resume: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute an approved plan; this is the sole credential-reading entry point."""

    run_dir = resolve_external_run_target(generation_root, generation_run_name)
    if not (run_dir / REAL_EXECUTION_PLAN_RELATIVE_PATH).parent.is_dir():
        authorize_real_execution(
            execute_real_api=execute_real_api,
            authorization=authorization,
        )
        raise FileNotFoundError("real_execution_runtime_missing")
    lock_path, lock_descriptor = _acquire_real_execution_lock(run_dir)
    try:
        return _run_real_execution_under_lock(
            generation_run_name=generation_run_name,
            generation_root=generation_root,
            endpoint=endpoint,
            execute_real_api=execute_real_api,
            authorization=authorization,
            credential_reader=credential_reader,
            backend=backend,
            resume=resume,
            sleep=sleep,
        )
    finally:
        _release_real_execution_lock(lock_path, lock_descriptor)


def _run_real_execution_under_lock(
    *,
    generation_run_name: str,
    generation_root: str | Path,
    endpoint: str,
    execute_real_api: bool = False,
    authorization: str | None = None,
    credential_reader: Callable[[str], str | None] | None = None,
    backend: ProviderExecutionBackend | None = None,
    resume: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Run every safety gate and mutation while the caller retains the lock."""

    authorize_real_execution(execute_real_api=execute_real_api, authorization=authorization)
    run_dir = resolve_external_run_target(generation_root, generation_run_name)
    plan = read_json(run_dir / REAL_EXECUTION_PLAN_RELATIVE_PATH)
    plan_errors = validate_execution_plan(plan)
    if plan_errors:
        raise ValueError("invalid_real_execution_plan:" + ";".join(plan_errors))
    configuration = _configuration_from_plan(endpoint, plan)
    manifest, selection, prompts, envelopes = _load_development_contract(run_dir, generation_run_name)
    if plan["generation_run_id"] != manifest["generation_run_id"]:
        raise ValueError("execution_plan_generation_identity_mismatch")
    if plan["pilot_selection_id"] != selection["pilot_selection_id"]:
        raise ValueError("execution_plan_selection_identity_mismatch")
    if plan["approved_case_ids"] != [row["case_id"] for row in selection["selected_cases"]]:
        raise ValueError("execution_plan_approved_cases_mismatch")
    _validate_plan_reservations_for_prompts(plan, prompts, configuration)
    selected_backend = backend or OpenAICompatibleHTTPBackend(endpoint=endpoint)
    if (
        selected_backend.backend_name != plan["provider_backend_name"]
        or selected_backend.backend_version != plan["provider_backend_version"]
    ):
        raise ValueError("provider_backend_contract_mismatch")
    audit = check_real_execution(
        generation_run_name=generation_run_name, generation_root=generation_root,
        require_completed=False,
    )
    stage = audit["stage"]
    if stage == "COMPLETED":
        if resume:
            return check_real_execution(
                generation_run_name=generation_run_name, generation_root=generation_root,
                require_completed=True,
            )
        raise FileExistsError("real_execution_artifacts_already_exist")
    if stage == "FAILED":
        raise ValueError("failed_execution_requires_manual_review")
    if stage == "INDETERMINATE":
        raise ValueError("indeterminate_provider_attempt_requires_manual_review")
    if stage in {"PARTIAL", "CORRUPT"} or audit["result"] != "PASS":
        raise ValueError("corrupt_or_partial_execution_requires_manual_review")
    if stage != "PREPARED":
        raise ValueError("real_execution_state_invalid")
    # This is intentionally the first and only credential access, after every safety gate.
    api_key = (credential_reader or os.environ.get)(API_KEY_ENVIRONMENT_VARIABLE)
    if not api_key:
        raise ValueError("provider_credential_missing")
    journal_path = run_dir / REAL_EXECUTION_JOURNAL_RELATIVE_PATH
    journal = read_json(journal_path)
    for request_index, (prompt, envelope) in enumerate(zip(prompts, envelopes)):
        if journal["logical_request_count"] >= plan["max_requests"]:
            raise ValueError("remaining_logical_request_budget_exhausted")
        prepared = selected_backend.prepare_request(prompt, envelope, configuration)
        reserved_input = plan["reserved_input_tokens_per_request"][request_index]
        reserved_output = configuration.max_output_tokens
        for attempt_number in range(1, plan["max_retries"] + 2):
            _start_attempt(
                journal_path=journal_path, journal=journal, plan=plan, prepared=prepared,
                attempt_number=attempt_number, reserved_input_tokens=reserved_input,
                reserved_output_tokens=reserved_output,
            )
            started = journal["attempts"][-1]["started_at_utc"]
            response: TransportResponse | None = None
            normalized: dict[str, Any] | None = None
            try:
                response = selected_backend.execute_once(
                    prepared, api_key=api_key, timeout_seconds=plan["timeout_seconds"],
                )
                if is_retryable_http_status(response.status_code) and attempt_number <= plan["max_retries"]:
                    _finish_attempt(
                        journal_path=journal_path, journal=journal, state="terminal_failure",
                        http_status=response.status_code, transient=True,
                        safe_error_code=f"transient_http_{response.status_code}_retry_scheduled",
                        terminal_artifacts=None,
                    )
                    sleep(min(2 ** (attempt_number - 1), 4))
                    continue
                normalized = selected_backend.normalize_provider_response(
                    response, expected_model_id=plan["model_id"],
                )
                if normalized["input_token_count"] > reserved_input:
                    raise ValueError("provider_input_usage_exceeded_reservation")
                if normalized["output_token_count"] > reserved_output:
                    raise ValueError("provider_output_usage_exceeded_reservation")
                if _SECRET_TEXT.search(normalized["response_content"]):
                    raise ValueError("secret_in_model_output")
                response_object, _ = _parse_candidate_response(normalized["response_content"], prompt)
            except Exception as exc:
                transient = isinstance(exc, ProviderTransportError) and exc.transient
                if transient and attempt_number <= plan["max_retries"]:
                    _finish_attempt(
                        journal_path=journal_path, journal=journal, state="terminal_failure",
                        http_status=None, transient=True,
                        safe_error_code=f"{_safe_error_code(exc)}_retry_scheduled",
                        terminal_artifacts=None,
                    )
                    sleep(min(2 ** (attempt_number - 1), 4))
                    continue
                completed = _utc_now()
                error_code = _safe_error_code(exc)
                receipt = _failed_receipt(
                    plan=plan, prepared=prepared, attempt_count=attempt_number,
                    response=response, normalized=normalized, started_at_utc=started,
                    completed_at_utc=completed, safe_error_code=error_code,
                )
                raw = _safe_failure_raw_response(
                    plan=plan, prepared=prepared, attempt_count=attempt_number,
                    response=response, normalized=normalized, safe_error_code=error_code,
                )
                artifacts = {"receipt": receipt, "raw_response": raw, "candidate_output": None}
                _finish_attempt(
                    journal_path=journal_path, journal=journal, state="terminal_failure",
                    http_status=response.status_code if response else None, transient=transient,
                    safe_error_code=error_code, terminal_artifacts=artifacts,
                )
                _materialize_journal(run_dir, journal)
                raise
            completed = _utc_now()
            receipt = _receipt(
                plan=plan, prepared=prepared, attempt_count=attempt_number,
                http_status=response.status_code, normalized=normalized,
                parse_success=True, schema_success=True, allowlist_success=True,
                started_at_utc=started, completed_at_utc=completed, safe_error_code=None,
            )
            raw = _safe_raw_response(
                plan=plan, prepared=prepared, normalized=normalized,
                http_status=response.status_code, attempt_count=attempt_number,
            )
            candidate = _candidate_output(
                plan=plan, receipt=receipt, prepared=prepared,
                response_object=response_object, created_at_utc=completed,
            )
            artifacts = {"receipt": receipt, "raw_response": raw, "candidate_output": candidate}
            _finish_attempt(
                journal_path=journal_path, journal=journal, state="terminal_success",
                http_status=response.status_code, transient=False, safe_error_code=None,
                terminal_artifacts=artifacts,
            )
            _materialize_journal(run_dir, journal)
            break
    journal["state"] = "completed"
    _write_journal(journal_path, journal)
    try:
        completed_audit = check_real_execution(
            generation_run_name=generation_run_name,
            generation_root=generation_root,
            require_completed=True,
        )
    except Exception as exc:
        raise ValueError("completed_execution_self_validation_failed") from exc
    if completed_audit.get("result") != "PASS" or completed_audit.get("stage") != "COMPLETED":
        raise ValueError("completed_execution_self_validation_failed")
    return completed_audit


def _validate_receipt_row(
    row: dict[str, Any], *, plan: dict[str, Any], prompt: dict[str, Any],
    envelope: dict[str, Any], errors: list[str], label: str,
) -> None:
    if set(row) != _RECEIPT_FIELDS:
        errors.append(f"{label}:field_set_mismatch")
        return
    expected_bindings = {
        "schema_version": REAL_EXECUTION_RECEIPT_SCHEMA_VERSION,
        "execution_plan_id": plan["execution_plan_id"],
        "request_envelope_id": envelope["request_envelope_id"],
        "prompt_instance_id": prompt["prompt_instance_id"],
        "case_id": prompt["case_id"],
        "backend_name": plan["provider_backend_name"],
        "backend_version": plan["provider_backend_version"],
        "model_id": plan["model_id"],
        "request_sha256": envelope["request_sha256"],
        "compiled_prompt_sha256": prompt["compiled_prompt_sha256"],
    }
    configuration = _configuration_parameters_from_plan(plan)
    expected_bindings["provider_request_sha256"] = _expected_provider_request_sha(prompt, configuration)
    for field, expected in expected_bindings.items():
        if row.get(field) != expected:
            errors.append(f"{label}:{field}_mismatch")
    attempt_count = row.get("attempt_count")
    if not isinstance(attempt_count, int) or not 1 <= attempt_count <= plan["max_retries"] + 1:
        errors.append(f"{label}:attempt_count_invalid")
    token_values = [row.get(field) for field in (
        "input_token_count", "output_token_count", "total_token_count",
    )]
    if any(not isinstance(value, int) or value < 0 for value in token_values):
        errors.append(f"{label}:token_count_invalid")
    elif token_values[0] + token_values[1] != token_values[2]:
        errors.append(f"{label}:token_arithmetic_mismatch")
    success = row.get("execution_status") == "candidate_created"
    if success:
        if (
            row.get("transport_status") != "success"
            or not isinstance(row.get("http_status"), int) or not 200 <= row["http_status"] < 300
            or row.get("network_call_performed") is not True
            or row.get("provider_response_received") is not True
            or row.get("model_output_generated") is not True
            or row.get("parse_success") is not True
            or row.get("schema_success") is not True
            or row.get("allowlist_success") is not True
            or row.get("safe_error_code") is not None
        ):
            errors.append(f"{label}:success_semantics_invalid")
    elif row.get("execution_status") == "failed":
        if (
            row.get("allowlist_success") is not False
            or not isinstance(row.get("safe_error_code"), str)
            or not row["safe_error_code"]
        ):
            errors.append(f"{label}:failure_semantics_invalid")
    else:
        errors.append(f"{label}:execution_status_invalid")
    expected_id = _stable_id(REAL_EXECUTION_RECEIPT_ID_PREFIX, _receipt_stable(row))
    if row.get("real_execution_receipt_id") != expected_id:
        errors.append(f"{label}:receipt_identity_mismatch")


def _validate_candidate_row(
    row: dict[str, Any], *, plan: dict[str, Any], prompt: dict[str, Any],
    envelope: dict[str, Any], receipt: dict[str, Any] | None,
    errors: list[str], label: str,
) -> None:
    if set(row) != _CANDIDATE_FIELDS:
        errors.append(f"{label}:field_set_mismatch")
        return
    expected = {
        "schema_version": CANDIDATE_OUTPUT_SCHEMA_VERSION,
        "execution_plan_id": plan["execution_plan_id"],
        "request_envelope_id": envelope["request_envelope_id"],
        "prompt_instance_id": prompt["prompt_instance_id"],
        "case_id": prompt["case_id"],
        "paper_id": prompt["paper_id"],
        "model_id": plan["model_id"],
        "import_status": "not_imported",
    }
    for field, value in expected.items():
        if row.get(field) != value:
            errors.append(f"{label}:{field}_mismatch")
    if receipt is None or row.get("real_execution_receipt_id") != receipt.get("real_execution_receipt_id"):
        errors.append(f"{label}:receipt_binding_mismatch")
    response_object = row.get("response_object")
    if not isinstance(response_object, dict):
        errors.append(f"{label}:response_object_invalid")
    else:
        response_sha = sha256_bytes(canonical_json(response_object).encode("utf-8"))
        if row.get("response_sha256") != response_sha:
            errors.append(f"{label}:response_sha_mismatch")
        try:
            _parse_candidate_response(canonical_json(response_object), prompt)
        except ValueError as exc:
            errors.append(f"{label}:{exc}")
    expected_id = _stable_id(CANDIDATE_OUTPUT_ID_PREFIX, _candidate_stable(row))
    if row.get("candidate_output_id") != expected_id:
        errors.append(f"{label}:candidate_identity_mismatch")


def _validate_raw_row(
    row: dict[str, Any], *, plan: dict[str, Any], prompt: dict[str, Any],
    envelope: dict[str, Any], receipt: dict[str, Any] | None,
    candidate: dict[str, Any] | None, errors: list[str], label: str,
) -> None:
    success = receipt is not None and receipt.get("execution_status") == "candidate_created"
    expected_fields = _RAW_SUCCESS_FIELDS if success else _RAW_FAILURE_FIELDS
    if set(row) != expected_fields:
        errors.append(f"{label}:field_set_mismatch")
        return
    for field, expected in {
        "schema_version": PROVIDER_RAW_RESPONSE_SCHEMA_VERSION,
        "execution_plan_id": plan["execution_plan_id"],
        "request_envelope_id": envelope["request_envelope_id"],
        "prompt_instance_id": prompt["prompt_instance_id"],
        "case_id": prompt["case_id"],
        "model_id": plan["model_id"],
    }.items():
        if row.get(field) != expected:
            errors.append(f"{label}:{field}_mismatch")
    token_values = [row.get(field) for field in (
        "input_token_count", "output_token_count", "total_token_count",
    )]
    if any(not isinstance(value, int) or value < 0 for value in token_values):
        errors.append(f"{label}:token_count_invalid")
    elif token_values[0] + token_values[1] != token_values[2]:
        errors.append(f"{label}:token_arithmetic_mismatch")
    if receipt is None or row.get("attempt_count") != receipt.get("attempt_count"):
        errors.append(f"{label}:receipt_attempt_binding_mismatch")
    elif token_values != [receipt.get(field) for field in (
        "input_token_count", "output_token_count", "total_token_count",
    )]:
        errors.append(f"{label}:receipt_usage_binding_mismatch")
    if success:
        if not isinstance(row.get("http_status"), int) or not 200 <= row["http_status"] < 300:
            errors.append(f"{label}:http_status_invalid")
        if (
            not isinstance(row.get("provider_response_id"), str)
            or not row["provider_response_id"].strip()
        ):
            errors.append(f"{label}:provider_response_id_invalid")
        if row.get("finish_reason") != "stop":
            errors.append(f"{label}:finish_reason_not_complete")
        try:
            response_object, _ = _parse_candidate_response(row.get("response_content", ""), prompt)
            if candidate is None or response_object != candidate.get("response_object"):
                errors.append(f"{label}:candidate_response_binding_mismatch")
        except ValueError as exc:
            errors.append(f"{label}:{exc}")
    elif not isinstance(row.get("safe_error_code"), str) or not row["safe_error_code"]:
        errors.append(f"{label}:safe_error_code_invalid")


def _validate_journal(
    journal: dict[str, Any], *, plan: dict[str, Any], prompts: list[dict[str, Any]],
    envelopes: list[dict[str, Any]], errors: list[str],
) -> None:
    if set(journal) != _JOURNAL_FIELDS:
        errors.append("journal_field_set_mismatch")
        return
    if journal.get("schema_version") != REAL_EXECUTION_JOURNAL_SCHEMA_VERSION:
        errors.append("journal_schema_mismatch")
    if journal.get("execution_plan_id") != plan["execution_plan_id"]:
        errors.append("journal_execution_plan_binding_mismatch")
    attempts = journal.get("attempts")
    if not isinstance(attempts, list):
        errors.append("journal_attempts_not_array")
        return
    prompt_by_request = {
        envelope["request_envelope_id"]: (index, prompt, envelope)
        for index, (prompt, envelope) in enumerate(zip(prompts, envelopes))
    }
    per_request_attempts: dict[str, int] = {}
    success_cases: list[str] = []
    reserved_input = reserved_output = reserved_total = 0
    for index, attempt in enumerate(attempts):
        label = f"journal_attempt[{index}]"
        if not isinstance(attempt, dict) or set(attempt) != _ATTEMPT_FIELDS:
            errors.append(f"{label}:field_set_mismatch")
            continue
        if attempt.get("execution_plan_id") != plan["execution_plan_id"]:
            errors.append(f"{label}:execution_plan_binding_mismatch")
        if attempt.get("global_network_attempt_number") != index + 1:
            errors.append(f"{label}:global_attempt_number_mismatch")
        request_id = attempt.get("request_envelope_id")
        contract = prompt_by_request.get(request_id)
        if contract is None:
            errors.append(f"{label}:unknown_request")
            continue
        request_index, prompt, envelope = contract
        per_request_attempts[request_id] = per_request_attempts.get(request_id, 0) + 1
        if attempt.get("attempt_number") != per_request_attempts[request_id]:
            errors.append(f"{label}:attempt_number_mismatch")
        for field, expected in {
            "prompt_instance_id": prompt["prompt_instance_id"],
            "case_id": prompt["case_id"], "paper_id": prompt["paper_id"],
            "request_sha256": envelope["request_sha256"],
            "compiled_prompt_sha256": prompt["compiled_prompt_sha256"],
            "provider_request_sha256": _expected_provider_request_sha(
                prompt, _configuration_parameters_from_plan(plan),
            ),
            "reserved_input_tokens": plan["reserved_input_tokens_per_request"][request_index],
            "reserved_output_tokens": plan["generation_parameters"]["max_output_tokens"],
        }.items():
            if attempt.get(field) != expected:
                errors.append(f"{label}:{field}_mismatch")
        if attempt.get("reserved_total_tokens") != (
            attempt.get("reserved_input_tokens", 0) + attempt.get("reserved_output_tokens", 0)
        ):
            errors.append(f"{label}:reserved_total_mismatch")
        if isinstance(attempt.get("reserved_input_tokens"), int):
            reserved_input += attempt["reserved_input_tokens"]
        if isinstance(attempt.get("reserved_output_tokens"), int):
            reserved_output += attempt["reserved_output_tokens"]
        if isinstance(attempt.get("reserved_total_tokens"), int):
            reserved_total += attempt["reserved_total_tokens"]
        state = attempt.get("state")
        artifacts = attempt.get("terminal_artifacts")
        if state == "attempt_started":
            if any(attempt.get(field) is not None for field in (
                "completed_at_utc", "http_status", "transient", "safe_error_code", "terminal_artifacts",
            )):
                errors.append(f"{label}:attempt_started_semantics_invalid")
        elif state == "terminal_success":
            if not isinstance(artifacts, dict) or set(artifacts) != {
                "receipt", "raw_response", "candidate_output",
            } or any(artifacts.get(field) is None for field in artifacts):
                errors.append(f"{label}:terminal_success_artifacts_invalid")
            success_cases.append(prompt["case_id"])
        elif state == "terminal_failure":
            if artifacts is not None and (
                not isinstance(artifacts, dict)
                or set(artifacts) != {"receipt", "raw_response", "candidate_output"}
                or artifacts.get("receipt") is None or artifacts.get("raw_response") is None
                or artifacts.get("candidate_output") is not None
            ):
                errors.append(f"{label}:terminal_failure_artifacts_invalid")
        else:
            errors.append(f"{label}:state_invalid")
    if journal.get("network_attempt_count") != len(attempts):
        errors.append("journal_network_attempt_count_mismatch")
    if len(attempts) > plan["max_network_attempts"]:
        errors.append("journal_network_attempt_budget_exceeded")
    if journal.get("logical_request_count") != len(success_cases):
        errors.append("journal_logical_request_count_mismatch")
    if success_cases != plan["approved_case_ids"][:len(success_cases)]:
        errors.append("journal_completed_case_order_mismatch")
    for field, expected in {
        "reserved_input_tokens_consumed": reserved_input,
        "reserved_output_tokens_consumed": reserved_output,
        "reserved_total_tokens_consumed": reserved_total,
    }.items():
        if journal.get(field) != expected:
            errors.append(f"journal_{field}_mismatch")
    if reserved_input > plan["max_input_tokens"] or reserved_output > plan["max_output_tokens"] or reserved_total > plan["max_total_tokens"]:
        errors.append("journal_token_reservation_budget_exceeded")
    if attempts:
        expected_state = "completed" if journal.get("state") == "completed" else attempts[-1].get("state")
        if journal.get("state") != expected_state:
            errors.append("journal_top_state_mismatch")
    elif journal.get("state") != "prepared":
        errors.append("journal_empty_state_mismatch")


def check_real_execution(
    *, generation_run_name: str, generation_root: str | Path,
    require_completed: bool = False,
) -> dict[str, Any]:
    """Strict offline validator; credentials and network are never consulted."""

    run_dir = resolve_external_run_target(generation_root, generation_run_name)
    errors: list[str] = []
    plan_path = run_dir / REAL_EXECUTION_PLAN_RELATIVE_PATH
    journal_path = run_dir / REAL_EXECUTION_JOURNAL_RELATIVE_PATH
    if not plan_path.is_file():
        return {"result": "FAIL", "stage": "CORRUPT", "errors": ["real_execution_plan_missing"]}
    try:
        plan = read_json(plan_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return {"result": "FAIL", "stage": "CORRUPT", "errors": ["real_execution_plan_corrupt"]}
    errors.extend(validate_execution_plan(plan))
    prompts: list[dict[str, Any]] = []
    envelopes: list[dict[str, Any]] = []
    try:
        manifest, selection, prompts, envelopes = _load_development_contract(run_dir, generation_run_name)
        if plan.get("generation_run_id") != manifest.get("generation_run_id"):
            errors.append("execution_plan_generation_identity_mismatch")
        if plan.get("pilot_selection_id") != selection.get("pilot_selection_id"):
            errors.append("execution_plan_selection_identity_mismatch")
        configuration = _configuration_parameters_from_plan(plan)
        _validate_plan_reservations_for_prompts(plan, prompts, configuration)
    except (KeyError, OSError, TypeError, ValueError) as exc:
        errors.append(str(exc))
    if not journal_path.is_file():
        errors.append("real_execution_journal_missing")
        journal: dict[str, Any] = {}
        stage = "CORRUPT"
    else:
        try:
            journal = read_json(journal_path)
            if not isinstance(journal, dict):
                raise ValueError("journal_not_object")
            if prompts and envelopes:
                _validate_journal(
                    journal, plan=plan, prompts=prompts, envelopes=envelopes, errors=errors,
                )
            _serialize_safe([journal])
            stage = _journal_stage(journal)
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"real_execution_journal_corrupt:{exc}")
            journal = {}
            stage = "CORRUPT"

    output_paths = {
        "receipts": run_dir / REAL_EXECUTION_RECEIPTS_RELATIVE_PATH,
        "raw": run_dir / PROVIDER_RAW_RESPONSES_RELATIVE_PATH,
        "candidates": run_dir / CANDIDATE_OUTPUTS_RELATIVE_PATH,
    }
    presence = {name: path.is_file() for name, path in output_paths.items()}
    receipts: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    if any(presence.values()) and not all(presence.values()):
        errors.append("partial_real_execution_artifacts")
    elif all(presence.values()):
        try:
            receipts = read_jsonl(output_paths["receipts"])
            raw_rows = read_jsonl(output_paths["raw"])
            candidates = read_jsonl(output_paths["candidates"])
        except (OSError, ValueError, json.JSONDecodeError):
            errors.append("real_execution_artifact_corrupt")
    journal_receipts, journal_raw, journal_candidates = _materialized_rows(journal) if journal else ([], [], [])
    if all(presence.values()) and (
        receipts != journal_receipts or raw_rows != journal_raw or candidates != journal_candidates
    ):
        errors.append("materialized_artifact_journal_mismatch")
    if not any(presence.values()) and (journal_receipts or journal_raw or journal_candidates):
        errors.append("materialized_artifacts_missing")
    if stage == "PREPARED" and any(presence.values()):
        errors.append("prepared_state_has_execution_artifacts")

    prompt_by_case = {row["case_id"]: row for row in prompts}
    envelope_by_case = {row["case_id"]: row for row in envelopes}
    receipt_by_id: dict[str, dict[str, Any]] = {}
    candidate_by_receipt: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(receipts):
        case_id = row.get("case_id") if isinstance(row, dict) else None
        prompt = prompt_by_case.get(case_id)
        envelope = envelope_by_case.get(case_id)
        if prompt is None or envelope is None:
            errors.append(f"receipt[{index}]:unknown_case")
            continue
        _validate_receipt_row(
            row, plan=plan, prompt=prompt, envelope=envelope, errors=errors,
            label=f"receipt[{index}]",
        )
        receipt_id = row.get("real_execution_receipt_id")
        if receipt_id in receipt_by_id:
            errors.append("duplicate_real_execution_receipt_id")
        elif isinstance(receipt_id, str):
            receipt_by_id[receipt_id] = row
    for index, row in enumerate(candidates):
        case_id = row.get("case_id") if isinstance(row, dict) else None
        prompt = prompt_by_case.get(case_id)
        envelope = envelope_by_case.get(case_id)
        if prompt is None or envelope is None:
            errors.append(f"candidate[{index}]:unknown_case")
            continue
        receipt = receipt_by_id.get(row.get("real_execution_receipt_id"))
        _validate_candidate_row(
            row, plan=plan, prompt=prompt, envelope=envelope, receipt=receipt,
            errors=errors, label=f"candidate[{index}]",
        )
        candidate_id = row.get("candidate_output_id")
        if any(existing.get("candidate_output_id") == candidate_id for existing in candidate_by_receipt.values()):
            errors.append("duplicate_candidate_output_id")
        receipt_id = row.get("real_execution_receipt_id")
        if receipt_id in candidate_by_receipt:
            errors.append("duplicate_candidate_receipt_binding")
        elif isinstance(receipt_id, str):
            candidate_by_receipt[receipt_id] = row
    for index, row in enumerate(raw_rows):
        case_id = row.get("case_id") if isinstance(row, dict) else None
        prompt = prompt_by_case.get(case_id)
        envelope = envelope_by_case.get(case_id)
        receipt = receipts[index] if index < len(receipts) else None
        candidate = candidate_by_receipt.get(receipt.get("real_execution_receipt_id")) if receipt else None
        if prompt is None or envelope is None:
            errors.append(f"raw[{index}]:unknown_case")
            continue
        _validate_raw_row(
            row, plan=plan, prompt=prompt, envelope=envelope, receipt=receipt,
            candidate=candidate, errors=errors, label=f"raw[{index}]",
        )
    if receipts and [row.get("case_id") for row in receipts] != plan.get("approved_case_ids", [])[:len(receipts)]:
        errors.append("receipt_case_order_mismatch")
    if candidates and [row.get("case_id") for row in candidates] != plan.get("approved_case_ids", [])[:len(candidates)]:
        errors.append("candidate_case_order_mismatch")
    try:
        _serialize_safe(receipts + raw_rows + candidates)
    except ValueError as exc:
        errors.append(str(exc))

    structural_errors = bool(errors)
    if structural_errors:
        stage = "CORRUPT"
    elif stage == "COMPLETED":
        if (
            len(receipts) != PILOT_CASE_COUNT or len(raw_rows) != PILOT_CASE_COUNT
            or len(candidates) != PILOT_CASE_COUNT
            or any(row.get("execution_status") != "candidate_created" for row in receipts)
            or journal.get("logical_request_count") != PILOT_CASE_COUNT
        ):
            errors.append("completed_execution_contract_mismatch")
            stage = "CORRUPT"
    elif stage == "FAILED":
        errors.append("failed_execution_requires_manual_review")
    elif stage == "INDETERMINATE":
        errors.append("indeterminate_provider_attempt_requires_manual_review")
    elif stage == "PARTIAL":
        errors.append("partial_execution_requires_manual_review")
    elif stage != "PREPARED":
        errors.append("execution_state_corrupt")
        stage = "CORRUPT"
    if require_completed and stage != "COMPLETED":
        errors.append("completed_execution_required")
    result = "PASS" if not errors and stage in {"PREPARED", "COMPLETED"} else "FAIL"
    return {
        "result": result,
        "stage": stage,
        "execution_plan_id": plan.get("execution_plan_id"),
        "logical_request_count": journal.get("logical_request_count", 0),
        "network_attempt_count": journal.get("network_attempt_count", 0),
        "request_count": plan.get("request_count"),
        "receipt_count": len(receipts),
        "provider_raw_response_count": len(raw_rows),
        "candidate_output_count": len(candidates),
        "imported_output_count": 0,
        "network_call_count": journal.get("network_attempt_count", 0),
        "errors": errors,
    }
