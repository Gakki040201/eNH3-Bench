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


REAL_EXECUTION_PLAN_SCHEMA_VERSION = "0.16-real-execution-plan.1"
REAL_EXECUTION_RECEIPT_SCHEMA_VERSION = "0.16-real-execution-receipt.1"
CANDIDATE_OUTPUT_SCHEMA_VERSION = "0.16-candidate-api-output.1"
PROVIDER_RAW_RESPONSE_SCHEMA_VERSION = "0.16-provider-raw-response.1"
PROVIDER_EXECUTION_INTERFACE_VERSION = "provider-execution-v1"
OPENAI_COMPATIBLE_BACKEND_NAME = "openai-compatible-http"
OPENAI_COMPATIBLE_BACKEND_VERSION = "openai-compatible-chat-completions-v1"
REAL_API_AUTHORIZATION_SCOPE = "REAL_API_DEVELOPMENT_V016_B1B1"
API_KEY_ENVIRONMENT_VARIABLE = "ENH3BENCH_API_KEY"
REAL_EXECUTION_PLAN_ID_PREFIX = "RE16"
REAL_EXECUTION_RECEIPT_ID_PREFIX = "RR16"
CANDIDATE_OUTPUT_ID_PREFIX = "CO16"
TRANSIENT_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
MAX_REAL_REQUESTS = 7
MAX_ALLOWED_RETRIES = 2

REAL_EXECUTION_PLAN_RELATIVE_PATH = Path("execution/real_execution_plan.json")
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
    temperature: float
    top_p: float
    max_output_tokens: int
    seed: int | None
    response_format: str
    reasoning_effort: str | None = None

    def validate(self) -> None:
        safe_endpoint_identity(self.endpoint)
        _require_nonblank(self.model_id, "model_configuration_missing")
        if not isinstance(self.temperature, (int, float)) or not math.isfinite(self.temperature):
            raise ValueError("invalid_temperature")
        if not 0 <= self.temperature <= 2:
            raise ValueError("invalid_temperature")
        if not isinstance(self.top_p, (int, float)) or not math.isfinite(self.top_p):
            raise ValueError("invalid_top_p")
        if not 0 < self.top_p <= 1:
            raise ValueError("invalid_top_p")
        if not isinstance(self.max_output_tokens, int) or self.max_output_tokens <= 0:
            raise ValueError("invalid_generation_max_output_tokens")
        if self.seed is not None and not isinstance(self.seed, int):
            raise ValueError("invalid_seed")
        if self.response_format not in {"json_object", "json_schema"}:
            raise ValueError("invalid_response_format")
        if self.reasoning_effort not in {None, "low", "medium", "high"}:
            raise ValueError("invalid_reasoning_effort")


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
        self.attempt_count = 0


@runtime_checkable
class ProviderExecutionBackend(Protocol):
    backend_name: str
    backend_version: str

    def prepare_request(
        self, prompt_instance: dict[str, Any], request_envelope: dict[str, Any],
        configuration: ProviderConfiguration,
    ) -> dict[str, Any]: ...

    def execute(
        self, prepared_request: dict[str, Any], *, api_key: str, timeout_seconds: float,
        max_retries: int,
    ) -> tuple[TransportResponse, int]: ...

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
        "temperature": float(configuration.temperature),
        "top_p": float(configuration.top_p),
        "max_output_tokens": configuration.max_output_tokens,
        "seed": configuration.seed,
        "response_format": configuration.response_format,
        "reasoning_effort": configuration.reasoning_effort,
    }


def _provider_payload(prompt: dict[str, Any], configuration: ProviderConfiguration) -> dict[str, Any]:
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
        "temperature": float(configuration.temperature),
        "top_p": float(configuration.top_p),
        "max_tokens": configuration.max_output_tokens,
    }
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


class OpenAICompatibleHTTPBackend:
    """Minimal standard-library transport for one compatible chat-completions endpoint."""

    backend_name = OPENAI_COMPATIBLE_BACKEND_NAME
    backend_version = OPENAI_COMPATIBLE_BACKEND_VERSION

    def __init__(
        self,
        *,
        endpoint: str,
        transport: Callable[[str, bytes, dict[str, str], float], TransportResponse] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        safe_endpoint_identity(endpoint)
        self._endpoint = endpoint
        self._transport = transport or self._stdlib_transport
        self._sleep = sleep

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

    def execute(
        self, prepared_request: dict[str, Any], *, api_key: str, timeout_seconds: float,
        max_retries: int,
    ) -> tuple[TransportResponse, int]:
        if not str(api_key or ""):
            raise ValueError("provider_credential_missing")
        body = canonical_json(prepared_request["provider_payload"]).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }
        attempt_count = 0
        while True:
            attempt_count += 1
            try:
                response = self._transport(self._endpoint, body, headers, timeout_seconds)
            except ProviderTransportError as exc:
                if exc.transient and attempt_count <= max_retries:
                    self._sleep(min(2 ** (attempt_count - 1), 4))
                    continue
                exc.attempt_count = attempt_count
                raise
            if response.status_code in TRANSIENT_HTTP_STATUSES and attempt_count <= max_retries:
                self._sleep(min(2 ** (attempt_count - 1), 4))
                continue
            return response, attempt_count

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
        return {
            "provider_response_id": str(value.get("id") or ""),
            "model_id": model,
            "finish_reason": str(choices[0].get("finish_reason") or ""),
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
        "model_id": plan["model_id"],
        "endpoint_origin_hash": plan["endpoint_origin_hash"],
        "request_count": plan["request_count"],
        "development_case_count": plan["development_case_count"],
        "holdout_case_count": plan["holdout_case_count"],
        "max_requests": plan["max_requests"],
        "max_input_tokens": plan["max_input_tokens"],
        "max_output_tokens": plan["max_output_tokens"],
        "max_total_tokens": plan["max_total_tokens"],
        "max_estimated_cost": plan["max_estimated_cost"],
        "currency": plan["currency"],
        "timeout_seconds": plan["timeout_seconds"],
        "max_retries": plan["max_retries"],
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
    if budget.max_output_tokens < configuration.max_output_tokens * PILOT_CASE_COUNT:
        raise ValueError("output_token_budget_preflight_failed")
    run_dir = resolve_external_run_target(generation_root, generation_run_name)
    manifest, selection, prompts, _ = _load_development_contract(run_dir, generation_run_name)
    estimated_input_tokens = sum(estimate_request_input_tokens(row, configuration) for row in prompts)
    estimated_total_tokens = estimated_input_tokens + configuration.max_output_tokens * PILOT_CASE_COUNT
    if estimated_input_tokens > budget.max_input_tokens:
        raise ValueError("input_token_budget_preflight_failed")
    if estimated_total_tokens > budget.max_total_tokens:
        raise ValueError("total_token_budget_preflight_failed")
    plan = {
        "schema_version": REAL_EXECUTION_PLAN_SCHEMA_VERSION,
        "provider_interface_version": PROVIDER_EXECUTION_INTERFACE_VERSION,
        "generation_run_id": manifest["generation_run_id"],
        "pilot_selection_id": selection["pilot_selection_id"],
        "provider_backend_name": OPENAI_COMPATIBLE_BACKEND_NAME,
        "provider_backend_version": OPENAI_COMPATIBLE_BACKEND_VERSION,
        "model_id": configuration.model_id,
        "endpoint_origin_hash": endpoint_origin_hash(configuration.endpoint),
        "request_count": PILOT_CASE_COUNT,
        "development_case_count": PILOT_CASE_COUNT,
        "holdout_case_count": 0,
        "approved_case_ids": [row["case_id"] for row in selection["selected_cases"]],
        "estimated_input_tokens": estimated_input_tokens,
        "estimated_max_output_tokens": configuration.max_output_tokens * PILOT_CASE_COUNT,
        "estimated_max_total_tokens": estimated_total_tokens,
        "max_requests": budget.max_requests,
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
    if plan_path.exists():
        existing = read_json(plan_path)
        if not resume:
            raise FileExistsError("real_execution_plan_already_exists")
        if existing.get("execution_plan_id") != plan["execution_plan_id"]:
            raise ValueError("resume_execution_plan_mismatch")
        return existing
    write_json(plan_path, plan)
    return plan


def validate_execution_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "schema_version", "provider_interface_version", "execution_plan_id",
        "generation_run_id", "pilot_selection_id", "provider_backend_name",
        "provider_backend_version", "model_id", "endpoint_origin_hash", "request_count",
        "development_case_count", "holdout_case_count", "approved_case_ids",
        "estimated_input_tokens", "estimated_max_output_tokens", "estimated_max_total_tokens",
        "max_requests", "max_input_tokens", "max_output_tokens", "max_total_tokens",
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
    try:
        ExecutionBudget(
            max_requests=plan["max_requests"], max_input_tokens=plan["max_input_tokens"],
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
    allowlist_errors: list[str] = []
    if len(claim_ids) != len(value["claims"]):
        allowlist_errors.append("duplicate_claim_id")
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
) -> dict[str, Any]:
    """Execute an approved plan; this is the sole credential-reading entry point."""

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
    output_paths = (
        run_dir / REAL_EXECUTION_RECEIPTS_RELATIVE_PATH,
        run_dir / PROVIDER_RAW_RESPONSES_RELATIVE_PATH,
        run_dir / CANDIDATE_OUTPUTS_RELATIVE_PATH,
    )
    if any(path.exists() for path in output_paths):
        if resume and all(path.exists() for path in output_paths):
            return check_real_execution(
                generation_run_name=generation_run_name, generation_root=generation_root,
                require_completed=True,
            )
        raise FileExistsError("real_execution_artifacts_already_exist")
    # This is intentionally the first and only credential access, after all prior gates.
    api_key = (credential_reader or os.environ.get)(API_KEY_ENVIRONMENT_VARIABLE)
    if not api_key:
        raise ValueError("provider_credential_missing")
    selected_backend = backend or OpenAICompatibleHTTPBackend(endpoint=endpoint)
    if (
        selected_backend.backend_name != plan["provider_backend_name"]
        or selected_backend.backend_version != plan["provider_backend_version"]
    ):
        raise ValueError("provider_backend_contract_mismatch")

    receipts: list[dict[str, Any]] = []
    raw_responses: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    consumed_input = consumed_output = consumed_total = 0
    for prompt, envelope in zip(prompts, envelopes):
        if len(receipts) >= plan["max_requests"]:
            raise ValueError("remaining_request_budget_exhausted")
        estimated_input = estimate_request_input_tokens(prompt, configuration)
        if consumed_input + estimated_input > plan["max_input_tokens"]:
            raise ValueError("remaining_input_token_budget_insufficient")
        if consumed_output + configuration.max_output_tokens > plan["max_output_tokens"]:
            raise ValueError("remaining_output_token_budget_insufficient")
        if consumed_total + estimated_input + configuration.max_output_tokens > plan["max_total_tokens"]:
            raise ValueError("remaining_total_token_budget_insufficient")
        prepared = selected_backend.prepare_request(prompt, envelope, configuration)
        started = _utc_now()
        response: TransportResponse | None = None
        normalized: dict[str, Any] | None = None
        attempts = 0
        try:
            response, attempts = selected_backend.execute(
                prepared, api_key=api_key, timeout_seconds=plan["timeout_seconds"],
                max_retries=plan["max_retries"],
            )
            normalized = selected_backend.normalize_provider_response(
                response, expected_model_id=plan["model_id"],
            )
            if _SECRET_TEXT.search(normalized["response_content"]):
                raise ValueError("secret_in_model_output")
            response_object, _ = _parse_candidate_response(normalized["response_content"], prompt)
            consumed_input += normalized["input_token_count"]
            consumed_output += normalized["output_token_count"]
            consumed_total += normalized["total_token_count"]
            if (
                consumed_input > plan["max_input_tokens"]
                or consumed_output > plan["max_output_tokens"]
                or consumed_total > plan["max_total_tokens"]
            ):
                raise ValueError("provider_usage_exceeded_hard_budget")
        except (OSError, ValueError, ProviderTransportError) as exc:
            if isinstance(exc, ProviderTransportError):
                attempts = exc.attempt_count
            completed = _utc_now()
            error_code = _safe_error_code(exc)
            receipts.append(_failed_receipt(
                plan=plan, prepared=prepared, attempt_count=attempts, response=response,
                normalized=normalized, started_at_utc=started, completed_at_utc=completed,
                safe_error_code=error_code,
            ))
            raw_responses.append(_safe_failure_raw_response(
                plan=plan, prepared=prepared, attempt_count=attempts, response=response,
                normalized=normalized, safe_error_code=error_code,
            ))
            _serialize_safe(receipts + raw_responses + candidates)
            write_jsonl(run_dir / REAL_EXECUTION_RECEIPTS_RELATIVE_PATH, receipts)
            write_jsonl(run_dir / PROVIDER_RAW_RESPONSES_RELATIVE_PATH, raw_responses)
            write_jsonl(run_dir / CANDIDATE_OUTPUTS_RELATIVE_PATH, candidates)
            raise
        completed = _utc_now()
        receipt = _receipt(
            plan=plan, prepared=prepared, attempt_count=attempts, http_status=response.status_code,
            normalized=normalized, parse_success=True, schema_success=True, allowlist_success=True,
            started_at_utc=started, completed_at_utc=completed, safe_error_code=None,
        )
        receipts.append(receipt)
        raw_responses.append(_safe_raw_response(
            plan=plan, prepared=prepared, normalized=normalized,
            http_status=response.status_code, attempt_count=attempts,
        ))
        candidates.append(_candidate_output(
            plan=plan, receipt=receipt, prepared=prepared,
            response_object=response_object, created_at_utc=completed,
        ))
    _serialize_safe(receipts + raw_responses + candidates)
    write_jsonl(run_dir / REAL_EXECUTION_RECEIPTS_RELATIVE_PATH, receipts)
    write_jsonl(run_dir / PROVIDER_RAW_RESPONSES_RELATIVE_PATH, raw_responses)
    write_jsonl(run_dir / CANDIDATE_OUTPUTS_RELATIVE_PATH, candidates)
    return {
        "result": "PASS",
        "execution_plan_id": plan["execution_plan_id"],
        "request_count": len(receipts),
        "network_call_count": sum(row["attempt_count"] for row in receipts),
        "candidate_output_count": len(candidates),
        "imported_output_count": 0,
    }


def check_real_execution(
    *,
    generation_run_name: str,
    generation_root: str | Path,
    require_completed: bool = False,
) -> dict[str, Any]:
    """Offline validator.  It never reads an environment variable or opens a network."""

    run_dir = resolve_external_run_target(generation_root, generation_run_name)
    errors: list[str] = []
    plan_path = run_dir / REAL_EXECUTION_PLAN_RELATIVE_PATH
    if not plan_path.is_file():
        errors.append("real_execution_plan_missing")
        return {"result": "FAIL", "stage": "missing", "errors": errors}
    plan = read_json(plan_path)
    errors.extend(validate_execution_plan(plan))
    try:
        manifest, selection, _, _ = _load_development_contract(run_dir, generation_run_name)
        if plan.get("generation_run_id") != manifest.get("generation_run_id"):
            errors.append("execution_plan_generation_identity_mismatch")
        if plan.get("pilot_selection_id") != selection.get("pilot_selection_id"):
            errors.append("execution_plan_selection_identity_mismatch")
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
    output_paths = {
        "receipts": run_dir / REAL_EXECUTION_RECEIPTS_RELATIVE_PATH,
        "raw": run_dir / PROVIDER_RAW_RESPONSES_RELATIVE_PATH,
        "candidates": run_dir / CANDIDATE_OUTPUTS_RELATIVE_PATH,
    }
    presence = {name: path.is_file() for name, path in output_paths.items()}
    if any(presence.values()) and not all(presence.values()):
        errors.append("partial_real_execution_artifacts")
    if require_completed and not all(presence.values()):
        errors.append("completed_real_execution_artifacts_missing")
    receipt_count = raw_count = candidate_count = 0
    if all(presence.values()):
        receipts = read_jsonl(output_paths["receipts"])
        raw = read_jsonl(output_paths["raw"])
        candidates = read_jsonl(output_paths["candidates"])
        receipt_count, raw_count, candidate_count = len(receipts), len(raw), len(candidates)
        failed = any(row.get("execution_status") == "failed" for row in receipts)
        if failed:
            if not (1 <= receipt_count <= plan.get("request_count", 0)):
                errors.append("failed_execution_receipt_count_mismatch")
            if raw_count != receipt_count or candidate_count >= receipt_count:
                errors.append("failed_execution_artifact_count_mismatch")
        elif not (receipt_count == raw_count == candidate_count == plan.get("request_count")):
            errors.append("real_execution_artifact_count_mismatch")
        if any(row.get("execution_plan_id") != plan.get("execution_plan_id") for row in receipts + raw + candidates):
            errors.append("real_execution_plan_binding_mismatch")
        if any(row.get("import_status") != "not_imported" for row in candidates):
            errors.append("candidate_import_boundary_failed")
        try:
            _serialize_safe(receipts + raw + candidates)
        except ValueError as exc:
            errors.append(str(exc))
    return {
        "result": "PASS" if not errors else "FAIL",
        "stage": (
            "failed_not_imported" if all(presence.values()) and any(
                row.get("execution_status") == "failed"
                for row in read_jsonl(output_paths["receipts"])
            ) else "completed_not_imported" if all(presence.values()) else "prepared"
        ),
        "execution_plan_id": plan.get("execution_plan_id"),
        "request_count": plan.get("request_count"),
        "receipt_count": receipt_count,
        "provider_raw_response_count": raw_count,
        "candidate_output_count": candidate_count,
        "imported_output_count": 0,
        "network_call_count": sum(
            row.get("attempt_count", 0) for row in read_jsonl(output_paths["receipts"])
        ) if all(presence.values()) else 0,
        "errors": errors,
    }
