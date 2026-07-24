from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest import mock
import uuid

from enh3bench.e2e_eval_package import build_selective_eval_package
from enh3bench.e2e_eval_schema import canonical_json, read_json, read_jsonl, write_json, write_jsonl
from enh3bench.generation_pilot import (
    RESPONSE_JSON_SCHEMA,
    build_development_pilot,
    prepare_generation_prompts,
    run_generation_dry_run,
)
from enh3bench.provider_execution import (
    API_KEY_ENVIRONMENT_VARIABLE,
    CANDIDATE_OUTPUT_SCHEMA_VERSION,
    MAX_ALLOWED_RETRIES,
    OPENAI_COMPATIBLE_BACKEND_NAME,
    OPENAI_COMPATIBLE_BACKEND_VERSION,
    PROVIDER_EXECUTION_INTERFACE_VERSION,
    PROVIDER_RAW_RESPONSE_SCHEMA_VERSION,
    REAL_API_AUTHORIZATION_SCOPE,
    REAL_EXECUTION_PLAN_SCHEMA_VERSION,
    REAL_EXECUTION_RECEIPT_SCHEMA_VERSION,
    TRANSIENT_HTTP_STATUSES,
    ExecutionBudget,
    OpenAICompatibleHTTPBackend,
    ProviderConfiguration,
    ProviderExecutionBackend,
    ProviderTransportError,
    TransportResponse,
    authorize_real_execution,
    check_real_execution,
    endpoint_origin_hash,
    is_retryable_http_status,
    prepare_real_execution,
    run_real_execution,
    safe_endpoint_identity,
    validate_execution_plan,
)
from scripts import check_real_execution as check_cli
from scripts import prepare_real_execution as prepare_cli
from scripts import run_real_execution as run_cli
from tests.selective_eval_test_helpers import create_source_calibration_fixture


ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://example.invalid/v1/chat/completions"
MODEL_ID = "test-compatible-model-v1"
TEST_CREDENTIAL = "TEST_ONLY_NOT_A_REAL_SECRET"


class QueueTransport:
    def __init__(self, responses: list[TransportResponse | BaseException]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, bytes, dict[str, str], float]] = []

    def __call__(
        self, endpoint: str, body: bytes, headers: dict[str, str], timeout: float,
    ) -> TransportResponse:
        self.calls.append((endpoint, body, dict(headers), timeout))
        if not self.responses:
            raise AssertionError("fake_transport_response_queue_exhausted")
        value = self.responses.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value


def valid_model_object() -> dict:
    return {
        "answer_text": "",
        "answer_status": "abstained",
        "confidence_statement": "Bounded evidence only.",
        "claims": [],
        "citations": [],
        "limitations": ["Test-only local transport response."],
        "abstention_reason": "Insufficient bounded evidence.",
    }


def provider_response(
    *, status: int = 200, model: str = MODEL_ID, content: str | None = None,
    prompt_tokens: int = 10, completion_tokens: int = 5,
) -> TransportResponse:
    body = {
        "id": "test-response-id",
        "model": model,
        "choices": [{
            "message": {"role": "assistant", "content": content or canonical_json(valid_model_object())},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
    return TransportResponse(status, json.dumps(body).encode("utf-8"))


class ProviderExecutionV016Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name)
        cls.calibration_root = cls.base / "source/calibration"
        create_source_calibration_fixture(cls.calibration_root, "calibration_fixture")
        cls.eval_root = cls.base / "source/selective_eval"
        build_selective_eval_package(
            source_calibration_run_name="calibration_fixture",
            source_calibration_root=cls.calibration_root,
            selective_eval_run_name="eval",
            selective_eval_root=cls.eval_root,
            clean=True,
            validate_source_package=False,
        )
        cls.output_root = cls.base / "external/v016_b1b1"
        cls.baseline_name = "baseline"
        build_development_pilot(
            selective_eval_run_name="eval",
            selective_eval_root=cls.eval_root,
            source_calibration_root=cls.calibration_root,
            generation_run_name=cls.baseline_name,
            generation_root=cls.output_root,
            validate_source_package=False,
        )
        prepare_generation_prompts(
            generation_run_name=cls.baseline_name, generation_root=cls.output_root,
        )
        run_generation_dry_run(
            generation_run_name=cls.baseline_name, generation_root=cls.output_root,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def _copy_baseline(self, prefix: str) -> tuple[Path, str, Path]:
        root = self.output_root / f"copy_{prefix}_{uuid.uuid4().hex}"
        name = self.baseline_name
        target = root / name
        shutil.copytree(self.output_root / self.baseline_name, target)
        return root, name, target

    def _configuration(self, **overrides: object) -> ProviderConfiguration:
        values: dict[str, object] = {
            "endpoint": ENDPOINT,
            "model_id": MODEL_ID,
            "temperature": 0.0,
            "top_p": 1.0,
            "max_output_tokens": 100,
            "seed": 17,
            "response_format": "json_schema",
            "reasoning_effort": None,
        }
        values.update(overrides)
        return ProviderConfiguration(**values)  # type: ignore[arg-type]

    def _budget(self, **overrides: object) -> ExecutionBudget:
        values: dict[str, object] = {
            "max_requests": 7,
            "max_input_tokens": 100_000,
            "max_output_tokens": 700,
            "max_total_tokens": 100_700,
            "timeout_seconds": 60.0,
            "max_retries": 2,
            "max_estimated_cost": None,
            "currency": None,
        }
        values.update(overrides)
        return ExecutionBudget(**values)  # type: ignore[arg-type]

    def _prepare(
        self, prefix: str, *, configuration: ProviderConfiguration | None = None,
        budget: ExecutionBudget | None = None, created_at: str = "2026-07-24T00:00:00Z",
    ) -> tuple[Path, str, Path, dict]:
        root, name, target = self._copy_baseline(prefix)
        plan = prepare_real_execution(
            generation_run_name=name,
            generation_root=root,
            configuration=configuration or self._configuration(),
            budget=budget or self._budget(),
            created_at_utc=created_at,
        )
        return root, name, target, plan

    def _backend(self, responses: list[TransportResponse | BaseException]) -> tuple[OpenAICompatibleHTTPBackend, QueueTransport]:
        transport = QueueTransport(responses)
        backend = OpenAICompatibleHTTPBackend(
            endpoint=ENDPOINT, transport=transport, sleep=lambda _: None,
        )
        return backend, transport

    def _run_success(self, prefix: str) -> tuple[Path, str, Path, dict, QueueTransport]:
        root, name, target, _ = self._prepare(prefix)
        backend, transport = self._backend([provider_response() for _ in range(7)])
        result = run_real_execution(
            generation_run_name=name,
            generation_root=root,
            endpoint=ENDPOINT,
            execute_real_api=True,
            authorization=REAL_API_AUTHORIZATION_SCOPE,
            credential_reader=lambda _: TEST_CREDENTIAL,
            backend=backend,
        )
        return root, name, target, result, transport

    def test_01_schema_and_backend_constants_are_versioned(self) -> None:
        self.assertEqual(REAL_EXECUTION_PLAN_SCHEMA_VERSION, "0.16-real-execution-plan.1")
        self.assertEqual(REAL_EXECUTION_RECEIPT_SCHEMA_VERSION, "0.16-real-execution-receipt.1")
        self.assertEqual(CANDIDATE_OUTPUT_SCHEMA_VERSION, "0.16-candidate-api-output.1")
        self.assertEqual(PROVIDER_RAW_RESPONSE_SCHEMA_VERSION, "0.16-provider-raw-response.1")
        self.assertEqual(PROVIDER_EXECUTION_INTERFACE_VERSION, "provider-execution-v1")

    def test_02_only_one_provider_backend_is_defined(self) -> None:
        self.assertEqual(OPENAI_COMPATIBLE_BACKEND_NAME, "openai-compatible-http")
        self.assertEqual(OPENAI_COMPATIBLE_BACKEND_VERSION, "openai-compatible-chat-completions-v1")

    def test_03_backend_satisfies_provider_protocol(self) -> None:
        self.assertIsInstance(OpenAICompatibleHTTPBackend(endpoint=ENDPOINT), ProviderExecutionBackend)

    def test_04_endpoint_requires_https(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires_https"):
            safe_endpoint_identity("http://example.invalid/v1/chat/completions")

    def test_05_endpoint_requires_single_supported_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported_provider_endpoint"):
            safe_endpoint_identity("https://example.invalid/v1/responses")

    def test_06_endpoint_rejects_userinfo(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsafe_provider_endpoint"):
            safe_endpoint_identity("https://user:password@example.invalid/v1/chat/completions")

    def test_07_endpoint_rejects_query_and_fragment(self) -> None:
        for endpoint in (
            "https://example.invalid/v1/chat/completions?key=value",
            "https://example.invalid/v1/chat/completions#fragment",
        ):
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(ValueError, "unsafe"):
                safe_endpoint_identity(endpoint)

    def test_08_endpoint_identity_is_case_and_default_port_stable(self) -> None:
        self.assertEqual(
            endpoint_origin_hash("https://EXAMPLE.invalid:443/v1/chat/completions"),
            endpoint_origin_hash(ENDPOINT),
        )

    def test_09_provider_configuration_requires_model(self) -> None:
        with self.assertRaisesRegex(ValueError, "model_configuration_missing"):
            self._configuration(model_id="").validate()

    def test_10_provider_generation_parameters_are_bounded(self) -> None:
        invalid = (
            self._configuration(temperature=-0.1),
            self._configuration(top_p=0.0),
            self._configuration(max_output_tokens=0),
            self._configuration(response_format="text"),
        )
        for configuration in invalid:
            with self.subTest(configuration=configuration), self.assertRaises(ValueError):
                configuration.validate()

    def test_11_budget_rejects_more_than_seven_requests(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_max_requests"):
            self._budget(max_requests=8).validate()

    def test_12_budget_rejects_request_count_above_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "request_budget_exceeded"):
            self._budget(max_requests=6).validate(request_count=7)

    def test_13_budget_requires_positive_token_limits(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_max_input_tokens"):
            self._budget(max_input_tokens=0).validate()

    def test_14_budget_requires_total_to_cover_components(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid_total_token_budget"):
            self._budget(max_total_tokens=500).validate()

    def test_15_cost_budget_requires_currency(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires_currency"):
            self._budget(max_estimated_cost=1.0).validate()

    def test_16_timeout_is_mandatory_and_finite(self) -> None:
        for timeout in (0, -1, float("inf")):
            with self.subTest(timeout=timeout), self.assertRaisesRegex(ValueError, "timeout"):
                self._budget(timeout_seconds=timeout).validate()

    def test_17_retry_cap_is_two(self) -> None:
        self.assertEqual(MAX_ALLOWED_RETRIES, 2)
        with self.assertRaisesRegex(ValueError, "invalid_max_retries"):
            self._budget(max_retries=3).validate()

    def test_18_retry_classification_is_exact(self) -> None:
        self.assertEqual(TRANSIENT_HTTP_STATUSES, {408, 429, 500, 502, 503, 504})
        self.assertTrue(all(is_retryable_http_status(value) for value in TRANSIENT_HTTP_STATUSES))
        self.assertFalse(any(is_retryable_http_status(value) for value in (400, 401, 403, 404)))

    def test_19_prepare_writes_offline_plan(self) -> None:
        _, _, target, plan = self._prepare("plan")
        self.assertEqual(read_json(target / "execution/real_execution_plan.json"), plan)
        self.assertRegex(plan["execution_plan_id"], r"^RE16_[0-9A-F]{20}$")

    def test_20_plan_contains_seven_development_and_zero_holdout(self) -> None:
        _, _, _, plan = self._prepare("counts")
        self.assertEqual(plan["request_count"], 7)
        self.assertEqual(plan["development_case_count"], 7)
        self.assertEqual(plan["holdout_case_count"], 0)
        self.assertEqual(len(plan["approved_case_ids"]), 7)

    def test_21_plan_serializes_hash_not_raw_endpoint(self) -> None:
        _, _, target, plan = self._prepare("endpoint_hash")
        text = (target / "execution/real_execution_plan.json").read_text(encoding="utf-8")
        self.assertNotIn(ENDPOINT, text)
        self.assertEqual(plan["endpoint_origin_hash"], endpoint_origin_hash(ENDPOINT))

    def test_22_plan_does_not_serialize_credential_or_absolute_path(self) -> None:
        _, _, target, _ = self._prepare("safe_plan")
        text = (target / "execution/real_execution_plan.json").read_text(encoding="utf-8")
        self.assertNotIn(API_KEY_ENVIRONMENT_VARIABLE, text)
        self.assertNotIn(TEST_CREDENTIAL, text)
        self.assertNotIn(str(target), text)

    def test_23_plan_identity_excludes_time_and_runtime_root(self) -> None:
        _, _, _, first = self._prepare("stable_a", created_at="2026-07-24T00:00:00Z")
        _, _, _, second = self._prepare("stable_b", created_at="2027-01-01T00:00:00Z")
        self.assertEqual(first["execution_plan_id"], second["execution_plan_id"])

    def test_24_plan_identity_binds_model(self) -> None:
        _, _, _, first = self._prepare("model_a")
        _, _, _, second = self._prepare("model_b", configuration=self._configuration(model_id="other-model"))
        self.assertNotEqual(first["execution_plan_id"], second["execution_plan_id"])

    def test_25_plan_identity_binds_budget_timeout_and_retry(self) -> None:
        _, _, _, baseline = self._prepare("identity_base")
        variations = (
            self._budget(max_input_tokens=100_001, max_total_tokens=100_701),
            self._budget(timeout_seconds=61),
            self._budget(max_retries=1),
        )
        for index, budget in enumerate(variations):
            with self.subTest(index=index):
                _, _, _, plan = self._prepare(f"identity_{index}", budget=budget)
                self.assertNotEqual(baseline["execution_plan_id"], plan["execution_plan_id"])

    def test_26_duplicate_plan_is_refused(self) -> None:
        root, name, _, _ = self._prepare("duplicate")
        with self.assertRaisesRegex(FileExistsError, "already_exists"):
            prepare_real_execution(
                generation_run_name=name, generation_root=root,
                configuration=self._configuration(), budget=self._budget(),
            )

    def test_27_resume_accepts_exact_plan(self) -> None:
        root, name, _, plan = self._prepare("resume")
        resumed = prepare_real_execution(
            generation_run_name=name, generation_root=root,
            configuration=self._configuration(), budget=self._budget(), resume=True,
        )
        self.assertEqual(resumed["execution_plan_id"], plan["execution_plan_id"])

    def test_28_resume_rejects_changed_plan(self) -> None:
        root, name, _, _ = self._prepare("resume_mismatch")
        with self.assertRaisesRegex(ValueError, "resume_execution_plan_mismatch"):
            prepare_real_execution(
                generation_run_name=name, generation_root=root,
                configuration=self._configuration(model_id="changed-model"),
                budget=self._budget(), resume=True,
            )

    def test_29_holdout_manifest_is_rejected(self) -> None:
        root, name, target = self._copy_baseline("holdout")
        path = target / "pilot/pilot_selection_manifest.json"
        value = read_json(path)
        value["development_case_count"] = 6
        value["holdout_case_count"] = 1
        write_json(path, value)
        with self.assertRaisesRegex(ValueError, "development_only|holdout"):
            prepare_real_execution(
                generation_run_name=name, generation_root=root,
                configuration=self._configuration(), budget=self._budget(),
            )

    def test_30_unknown_case_is_rejected(self) -> None:
        root, name, target = self._copy_baseline("unknown")
        path = target / "pilot/pilot_selection_manifest.json"
        value = read_json(path)
        value["selected_cases"][0]["case_id"] = "unknown-case"
        write_json(path, value)
        with self.assertRaisesRegex(ValueError, "unknown_or_unapproved_case"):
            prepare_real_execution(
                generation_run_name=name, generation_root=root,
                configuration=self._configuration(), budget=self._budget(),
            )

    def test_31_request_sha_binding_is_checked(self) -> None:
        root, name, target = self._copy_baseline("request_sha")
        path = target / "execution/request_envelopes.jsonl"
        rows = read_jsonl(path)
        rows[0]["request_sha256"] = "0" * 64
        write_jsonl(path, rows)
        with self.assertRaisesRegex(ValueError, "request_sha_binding_mismatch"):
            prepare_real_execution(
                generation_run_name=name, generation_root=root,
                configuration=self._configuration(), budget=self._budget(),
            )

    def test_32_compiled_prompt_sha_binding_is_checked(self) -> None:
        root, name, target = self._copy_baseline("prompt_sha")
        path = target / "prompts/compiled_prompt_instances.jsonl"
        rows = read_jsonl(path)
        rows[0]["question"] = "tampered question"
        write_jsonl(path, rows)
        with self.assertRaisesRegex(ValueError, "compiled_prompt_sha_binding_mismatch"):
            prepare_real_execution(
                generation_run_name=name, generation_root=root,
                configuration=self._configuration(), budget=self._budget(),
            )

    def test_33_response_schema_contract_is_checked(self) -> None:
        root, name, target = self._copy_baseline("response_schema")
        path = target / "prompts/compiled_prompt_instances.jsonl"
        rows = read_jsonl(path)
        rows[0]["response_json_schema"] = {"type": "object"}
        stable = {key: value for key, value in rows[0].items() if key != "compiled_prompt_sha256"}
        from enh3bench.e2e_eval_schema import sha256_bytes
        rows[0]["compiled_prompt_sha256"] = sha256_bytes(canonical_json(stable).encode("utf-8"))
        envelope_path = target / "execution/request_envelopes.jsonl"
        envelopes = read_jsonl(envelope_path)
        envelopes[0]["compiled_prompt_sha256"] = rows[0]["compiled_prompt_sha256"]
        write_jsonl(path, rows)
        write_jsonl(envelope_path, envelopes)
        with self.assertRaisesRegex(ValueError, "response_schema_contract_mismatch"):
            prepare_real_execution(
                generation_run_name=name, generation_root=root,
                configuration=self._configuration(), budget=self._budget(),
            )

    def test_34_input_token_budget_fails_preflight(self) -> None:
        with self.assertRaisesRegex(ValueError, "input_token_budget_preflight_failed"):
            self._prepare(
                "input_budget", budget=self._budget(max_input_tokens=1, max_total_tokens=701),
            )

    def test_35_output_token_budget_fails_preflight(self) -> None:
        with self.assertRaisesRegex(ValueError, "output_token_budget_preflight_failed"):
            self._prepare("output_budget", budget=self._budget(max_output_tokens=699))

    def test_36_total_token_budget_fails_preflight(self) -> None:
        _, _, _, reference = self._prepare("total_budget_reference")
        estimated_input = reference["estimated_input_tokens"]
        with self.assertRaisesRegex(ValueError, "total_token_budget_preflight_failed"):
            self._prepare(
                "total_budget",
                budget=self._budget(
                    max_input_tokens=estimated_input, max_total_tokens=estimated_input,
                ),
            )

    def test_37_validator_accepts_prepared_stage_offline(self) -> None:
        root, name, _, plan = self._prepare("check_prepared")
        result = check_real_execution(generation_run_name=name, generation_root=root)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["stage"], "prepared")
        self.assertEqual(result["execution_plan_id"], plan["execution_plan_id"])

    def test_38_validator_detects_plan_identity_tampering(self) -> None:
        root, name, target, _ = self._prepare("check_tamper")
        path = target / "execution/real_execution_plan.json"
        value = read_json(path)
        value["model_id"] = "tampered-model"
        write_json(path, value)
        result = check_real_execution(generation_run_name=name, generation_root=root)
        self.assertEqual(result["result"], "FAIL")
        self.assertIn("execution_plan_identity_mismatch", result["errors"])

    def test_39_default_execution_fails_closed_before_credential(self) -> None:
        calls: list[str] = []
        with self.assertRaisesRegex(ValueError, "real_api_execution_not_authorized"):
            run_real_execution(
                generation_run_name="missing", generation_root=self.output_root,
                endpoint=ENDPOINT, credential_reader=lambda name: calls.append(name) or TEST_CREDENTIAL,
            )
        self.assertEqual(calls, [])

    def test_40_flag_only_fails_closed_before_credential(self) -> None:
        calls: list[str] = []
        with self.assertRaisesRegex(ValueError, "real_api_execution_not_authorized"):
            run_real_execution(
                generation_run_name="missing", generation_root=self.output_root,
                endpoint=ENDPOINT, execute_real_api=True,
                credential_reader=lambda name: calls.append(name) or TEST_CREDENTIAL,
            )
        self.assertEqual(calls, [])

    def test_41_authorization_token_only_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "real_api_execution_not_authorized"):
            authorize_real_execution(
                execute_real_api=False, authorization=REAL_API_AUTHORIZATION_SCOPE,
            )

    def test_42_wrong_authorization_scope_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "real_api_execution_not_authorized"):
            authorize_real_execution(execute_real_api=True, authorization="REAL_API")

    def test_43_missing_credential_fails_only_after_authorization(self) -> None:
        root, name, _, _ = self._prepare("missing_credential")
        calls: list[str] = []
        with self.assertRaisesRegex(ValueError, "provider_credential_missing"):
            run_real_execution(
                generation_run_name=name, generation_root=root, endpoint=ENDPOINT,
                execute_real_api=True, authorization=REAL_API_AUTHORIZATION_SCOPE,
                credential_reader=lambda key: calls.append(key) or None,
            )
        self.assertEqual(calls, [API_KEY_ENVIRONMENT_VARIABLE])

    def test_44_prepare_never_reads_credential(self) -> None:
        original_get = os.environ.get
        def guarded_get(key: str, default: object = None) -> object:
            if key == API_KEY_ENVIRONMENT_VARIABLE:
                raise AssertionError("credential read")
            return original_get(key, default)
        with mock.patch.object(os._Environ, "get", side_effect=guarded_get):
            self._prepare("no_credential_prepare")

    def test_45_validator_never_reads_credential(self) -> None:
        root, name, _, _ = self._prepare("no_credential_check")
        original_get = os.environ.get
        def guarded_get(key: str, default: object = None) -> object:
            if key == API_KEY_ENVIRONMENT_VARIABLE:
                raise AssertionError("credential read")
            return original_get(key, default)
        with mock.patch.object(os._Environ, "get", side_effect=guarded_get):
            self.assertEqual(
                check_real_execution(generation_run_name=name, generation_root=root)["result"], "PASS",
            )

    def test_46_help_never_reads_credential(self) -> None:
        original_get = os.environ.get
        def guarded_get(key: str, default: object = None) -> object:
            if key == API_KEY_ENVIRONMENT_VARIABLE:
                raise AssertionError("credential read")
            return original_get(key, default)
        for module in (prepare_cli, run_cli, check_cli):
            with self.subTest(module=module.__name__), mock.patch.object(
                os._Environ, "get", side_effect=guarded_get
            ), redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as context:
                module.main(["--help"])
            self.assertEqual(context.exception.code, 0)

    def test_47_run_cli_without_authorization_fails_closed(self) -> None:
        with redirect_stderr(io.StringIO()):
            result = run_cli.main([
                "--generation-run-name", "missing", "--pilot-root", str(self.output_root),
                "--endpoint", ENDPOINT,
            ])
        self.assertEqual(result, 1)

    def test_48_provider_request_binds_b1b0_hashes_without_headers(self) -> None:
        _, _, target, _ = self._prepare("request_shape")
        prompt = read_jsonl(target / "prompts/compiled_prompt_instances.jsonl")[0]
        envelope = read_jsonl(target / "execution/request_envelopes.jsonl")[0]
        backend = OpenAICompatibleHTTPBackend(endpoint=ENDPOINT)
        prepared = backend.prepare_request(prompt, envelope, self._configuration())
        self.assertEqual(prepared["request_sha256"], envelope["request_sha256"])
        self.assertEqual(prepared["compiled_prompt_sha256"], prompt["compiled_prompt_sha256"])
        self.assertNotIn("headers", prepared)
        self.assertNotIn("authorization", canonical_json(prepared).casefold())

    def test_49_provider_payload_uses_exact_b1b0_response_schema(self) -> None:
        _, _, target, _ = self._prepare("payload_schema")
        prompt = read_jsonl(target / "prompts/compiled_prompt_instances.jsonl")[0]
        envelope = read_jsonl(target / "execution/request_envelopes.jsonl")[0]
        prepared = OpenAICompatibleHTTPBackend(endpoint=ENDPOINT).prepare_request(
            prompt, envelope, self._configuration(),
        )
        schema = prepared["provider_payload"]["response_format"]["json_schema"]["schema"]
        self.assertEqual(schema, RESPONSE_JSON_SCHEMA)

    def test_50_explicit_timeout_is_forwarded_to_transport(self) -> None:
        backend, transport = self._backend([provider_response()])
        backend.execute(
            {"provider_payload": {"model": MODEL_ID}}, api_key=TEST_CREDENTIAL,
            timeout_seconds=37.5, max_retries=0,
        )
        self.assertEqual(transport.calls[0][3], 37.5)

    def test_51_http_401_is_not_retried(self) -> None:
        backend, transport = self._backend([TransportResponse(401, b"{}")])
        response, attempts = backend.execute(
            {"provider_payload": {}}, api_key=TEST_CREDENTIAL, timeout_seconds=1, max_retries=2,
        )
        self.assertEqual((response.status_code, attempts, len(transport.calls)), (401, 1, 1))

    def test_52_http_429_is_retried(self) -> None:
        backend, transport = self._backend([TransportResponse(429, b"{}"), provider_response()])
        response, attempts = backend.execute(
            {"provider_payload": {}}, api_key=TEST_CREDENTIAL, timeout_seconds=1, max_retries=2,
        )
        self.assertEqual((response.status_code, attempts, len(transport.calls)), (200, 2, 2))

    def test_53_http_500_is_retried(self) -> None:
        backend, transport = self._backend([TransportResponse(500, b"{}"), provider_response()])
        _, attempts = backend.execute(
            {"provider_payload": {}}, api_key=TEST_CREDENTIAL, timeout_seconds=1, max_retries=2,
        )
        self.assertEqual((attempts, len(transport.calls)), (2, 2))

    def test_54_retry_cap_is_enforced(self) -> None:
        backend, transport = self._backend([TransportResponse(503, b"{}") for _ in range(3)])
        response, attempts = backend.execute(
            {"provider_payload": {}}, api_key=TEST_CREDENTIAL, timeout_seconds=1, max_retries=2,
        )
        self.assertEqual((response.status_code, attempts, len(transport.calls)), (503, 3, 3))

    def test_55_transient_connection_failure_is_retried(self) -> None:
        backend, transport = self._backend([
            ProviderTransportError("provider_connection_reset", transient=True), provider_response(),
        ])
        _, attempts = backend.execute(
            {"provider_payload": {}}, api_key=TEST_CREDENTIAL, timeout_seconds=1, max_retries=2,
        )
        self.assertEqual((attempts, len(transport.calls)), (2, 2))

    def test_56_nontransient_transport_failure_is_not_retried(self) -> None:
        backend, transport = self._backend([
            ProviderTransportError("provider_transport_failure", transient=False),
        ])
        with self.assertRaisesRegex(ProviderTransportError, "provider_transport_failure"):
            backend.execute(
                {"provider_payload": {}}, api_key=TEST_CREDENTIAL,
                timeout_seconds=1, max_retries=2,
            )
        self.assertEqual(len(transport.calls), 1)

    def test_57_provider_response_normalization_is_separate(self) -> None:
        normalized = OpenAICompatibleHTTPBackend(endpoint=ENDPOINT).normalize_provider_response(
            provider_response(), expected_model_id=MODEL_ID,
        )
        self.assertEqual(normalized["model_id"], MODEL_ID)
        self.assertEqual(normalized["total_token_count"], 15)
        self.assertIsInstance(normalized["response_content"], str)

    def test_58_provider_model_mismatch_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "provider_model_mismatch"):
            OpenAICompatibleHTTPBackend(endpoint=ENDPOINT).normalize_provider_response(
                provider_response(model="other-model"), expected_model_id=MODEL_ID,
            )

    def test_59_malformed_provider_json_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "provider_response_not_json"):
            OpenAICompatibleHTTPBackend(endpoint=ENDPOINT).normalize_provider_response(
                TransportResponse(200, b"not-json"), expected_model_id=MODEL_ID,
            )

    def test_60_provider_usage_must_balance(self) -> None:
        response = json.loads(provider_response().body)
        response["usage"]["total_tokens"] = 999
        with self.assertRaisesRegex(ValueError, "provider_usage_total_mismatch"):
            OpenAICompatibleHTTPBackend(endpoint=ENDPOINT).normalize_provider_response(
                TransportResponse(200, json.dumps(response).encode()), expected_model_id=MODEL_ID,
            )

    def test_61_markdown_fence_is_rejected(self) -> None:
        root, name, _, _ = self._prepare("markdown")
        backend, _ = self._backend([
            provider_response(content="```json\n" + canonical_json(valid_model_object()) + "\n```")
        ])
        with self.assertRaisesRegex(ValueError, "markdown_fence_forbidden"):
            run_real_execution(
                generation_run_name=name, generation_root=root, endpoint=ENDPOINT,
                execute_real_api=True, authorization=REAL_API_AUTHORIZATION_SCOPE,
                credential_reader=lambda _: TEST_CREDENTIAL, backend=backend,
            )

    def test_62_unknown_response_field_is_rejected(self) -> None:
        root, name, _, _ = self._prepare("unknown_response")
        value = valid_model_object()
        value["unknown"] = True
        backend, _ = self._backend([provider_response(content=canonical_json(value))])
        with self.assertRaisesRegex(ValueError, "model_output_schema_invalid"):
            run_real_execution(
                generation_run_name=name, generation_root=root, endpoint=ENDPOINT,
                execute_real_api=True, authorization=REAL_API_AUTHORIZATION_SCOPE,
                credential_reader=lambda _: TEST_CREDENTIAL, backend=backend,
            )

    def test_63_wrong_claim_schema_is_rejected(self) -> None:
        root, name, _, _ = self._prepare("claim_schema")
        value = valid_model_object()
        value["claims"] = [{"claim_id": "claim-1"}]
        backend, _ = self._backend([provider_response(content=canonical_json(value))])
        with self.assertRaisesRegex(ValueError, "model_output_schema_invalid"):
            run_real_execution(
                generation_run_name=name, generation_root=root, endpoint=ENDPOINT,
                execute_real_api=True, authorization=REAL_API_AUTHORIZATION_SCOPE,
                credential_reader=lambda _: TEST_CREDENTIAL, backend=backend,
            )

    def test_64_citation_allowlist_is_enforced(self) -> None:
        root, name, _, _ = self._prepare("allowlist")
        value = valid_model_object()
        value["claims"] = [{
            "claim_id": "claim-1", "claim_text": "Unsupported test claim",
            "claim_type": "author_result", "supporting_source_span_ids": ["unknown-span"],
            "supporting_evidence_link_ids": [], "support_status": "supported",
        }]
        backend, _ = self._backend([provider_response(content=canonical_json(value))])
        with self.assertRaisesRegex(ValueError, "citation_allowlist_invalid"):
            run_real_execution(
                generation_run_name=name, generation_root=root, endpoint=ENDPOINT,
                execute_real_api=True, authorization=REAL_API_AUTHORIZATION_SCOPE,
                credential_reader=lambda _: TEST_CREDENTIAL, backend=backend,
            )

    def test_65_fake_transport_executes_exactly_seven_requests(self) -> None:
        _, _, _, result, transport = self._run_success("seven")
        self.assertEqual(result["request_count"], 7)
        self.assertEqual(result["network_call_count"], 7)
        self.assertEqual(len(transport.calls), 7)

    def test_66_success_writes_distinct_raw_receipt_and_candidate_layers(self) -> None:
        _, _, target, _, _ = self._run_success("layers")
        self.assertEqual(len(read_jsonl(target / "provider_raw/provider_raw_responses.jsonl")), 7)
        self.assertEqual(len(read_jsonl(target / "execution/real_execution_receipts.jsonl")), 7)
        candidates = read_jsonl(target / "candidate_outputs/candidate_api_outputs.jsonl")
        self.assertEqual(len(candidates), 7)
        self.assertTrue(all(row["import_status"] == "not_imported" for row in candidates))

    def test_67_receipt_ids_are_stable_across_runtime_roots(self) -> None:
        _, _, first_target, _, _ = self._run_success("receipt_a")
        _, _, second_target, _, _ = self._run_success("receipt_b")
        first = read_jsonl(first_target / "execution/real_execution_receipts.jsonl")
        second = read_jsonl(second_target / "execution/real_execution_receipts.jsonl")
        self.assertEqual(
            [row["real_execution_receipt_id"] for row in first],
            [row["real_execution_receipt_id"] for row in second],
        )

    def test_68_candidate_ids_are_stable_across_runtime_roots(self) -> None:
        _, _, first_target, _, _ = self._run_success("candidate_a")
        _, _, second_target, _, _ = self._run_success("candidate_b")
        first = read_jsonl(first_target / "candidate_outputs/candidate_api_outputs.jsonl")
        second = read_jsonl(second_target / "candidate_outputs/candidate_api_outputs.jsonl")
        self.assertEqual(
            [row["candidate_output_id"] for row in first],
            [row["candidate_output_id"] for row in second],
        )

    def test_69_authorization_header_and_credential_are_not_serialized(self) -> None:
        _, _, target, _, transport = self._run_success("no_header")
        self.assertTrue(all(call[2]["Authorization"] == f"Bearer {TEST_CREDENTIAL}" for call in transport.calls))
        serialized = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                target / "execution/real_execution_plan.json",
                target / "execution/real_execution_receipts.jsonl",
                target / "provider_raw/provider_raw_responses.jsonl",
                target / "candidate_outputs/candidate_api_outputs.jsonl",
            )
        )
        self.assertNotIn(TEST_CREDENTIAL, serialized)
        self.assertNotIn("Authorization", serialized)

    def test_70_secret_like_raw_response_is_not_serialized(self) -> None:
        root, name, target, _ = self._prepare("raw_secret")
        value = valid_model_object()
        value["limitations"] = ["Authorization: " + "Bearer " + TEST_CREDENTIAL]
        backend, _ = self._backend([
            provider_response(content=canonical_json(value)) for _ in range(7)
        ])
        with self.assertRaisesRegex(ValueError, "secret_in_model_output"):
            run_real_execution(
                generation_run_name=name, generation_root=root, endpoint=ENDPOINT,
                execute_real_api=True, authorization=REAL_API_AUTHORIZATION_SCOPE,
                credential_reader=lambda _: TEST_CREDENTIAL, backend=backend,
            )
        raw_text = (target / "provider_raw/provider_raw_responses.jsonl").read_text(encoding="utf-8")
        receipts = read_jsonl(target / "execution/real_execution_receipts.jsonl")
        self.assertNotIn(TEST_CREDENTIAL, raw_text)
        self.assertIn("[REDACTED_SENSITIVE_TEXT]", raw_text)
        self.assertEqual(receipts[0]["execution_status"], "failed")
        self.assertEqual(receipts[0]["safe_error_code"], "secret_in_model_output")

    def test_71_completed_validator_passes_without_import(self) -> None:
        root, name, _, _, _ = self._run_success("completed_check")
        result = check_real_execution(
            generation_run_name=name, generation_root=root, require_completed=True,
        )
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["stage"], "completed_not_imported")
        self.assertEqual(result["imported_output_count"], 0)

    def test_72_resume_returns_completed_validation_without_new_calls(self) -> None:
        root, name, _, _, _ = self._run_success("resume_completed")
        calls: list[str] = []
        result = run_real_execution(
            generation_run_name=name, generation_root=root, endpoint=ENDPOINT,
            execute_real_api=True, authorization=REAL_API_AUTHORIZATION_SCOPE,
            credential_reader=lambda key: calls.append(key) or TEST_CREDENTIAL,
            resume=True,
        )
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(calls, [])

    def test_73_duplicate_execution_is_refused(self) -> None:
        root, name, _, _, _ = self._run_success("duplicate_execution")
        with self.assertRaisesRegex(FileExistsError, "already_exist"):
            run_real_execution(
                generation_run_name=name, generation_root=root, endpoint=ENDPOINT,
                execute_real_api=True, authorization=REAL_API_AUTHORIZATION_SCOPE,
                credential_reader=lambda _: TEST_CREDENTIAL,
            )

    def test_74_partial_execution_artifacts_fail_validation(self) -> None:
        root, name, target, _ = self._prepare("partial")
        write_jsonl(target / "execution/real_execution_receipts.jsonl", [])
        result = check_real_execution(generation_run_name=name, generation_root=root)
        self.assertEqual(result["result"], "FAIL")
        self.assertIn("partial_real_execution_artifacts", result["errors"])

    def test_75_candidate_outputs_never_enter_selective_eval_source(self) -> None:
        self._run_success("no_import")
        source = self.eval_root / "eval"
        self.assertFalse(any(path.name == "api_outputs.jsonl" for path in source.rglob("*")))

    def test_76_runtime_artifacts_are_external_to_repository(self) -> None:
        _, _, target, _ = self._prepare("external")
        with self.assertRaises(ValueError):
            target.resolve().relative_to(ROOT.resolve())

    def test_77_preparation_and_validation_do_not_open_public_network(self) -> None:
        with mock.patch.object(socket, "create_connection", side_effect=AssertionError("public network")):
            root, name, _, _ = self._prepare("network_firewall")
            self.assertEqual(
                check_real_execution(generation_run_name=name, generation_root=root)["result"], "PASS",
            )

    def test_78_authorized_test_execution_uses_only_injected_transport(self) -> None:
        root, name, _, _ = self._prepare("fake_only")
        backend, transport = self._backend([provider_response() for _ in range(7)])
        with mock.patch.object(
            socket, "create_connection", side_effect=AssertionError("public network")
        ), mock.patch(
            "enh3bench.provider_execution.urllib_request.urlopen",
            side_effect=AssertionError("public network"),
        ):
            result = run_real_execution(
                generation_run_name=name, generation_root=root, endpoint=ENDPOINT,
                execute_real_api=True, authorization=REAL_API_AUTHORIZATION_SCOPE,
                credential_reader=lambda _: TEST_CREDENTIAL, backend=backend,
            )
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(len(transport.calls), 7)

    def test_79_plan_validator_rejects_windows_and_posix_paths(self) -> None:
        _, _, _, plan = self._prepare("paths")
        for model in (r"C:\Users\person\model", "/home/person/model"):
            value = deepcopy(plan)
            value["model_id"] = model
            errors = validate_execution_plan(value)
            self.assertIn("absolute_path_in_execution_plan", errors)

    def test_80_plan_validator_rejects_secret_text(self) -> None:
        _, _, _, plan = self._prepare("plan_secret")
        value = deepcopy(plan)
        value["model_id"] = "Authorization: " + "Bearer " + TEST_CREDENTIAL
        self.assertIn("secret_in_execution_plan", validate_execution_plan(value))

    def test_81_plan_write_is_atomic_on_replace_failure(self) -> None:
        root, name, target = self._copy_baseline("atomic")
        with mock.patch(
            "enh3bench.e2e_eval_schema.os.replace", side_effect=OSError("injected replace failure")
        ), self.assertRaisesRegex(OSError, "injected replace failure"):
            prepare_real_execution(
                generation_run_name=name, generation_root=root,
                configuration=self._configuration(), budget=self._budget(),
            )
        plan_path = target / "execution/real_execution_plan.json"
        self.assertFalse(plan_path.exists())
        self.assertEqual(list(plan_path.parent.glob(".real_execution_plan.json.*")), [])

    def test_82_prepare_cli_succeeds_offline(self) -> None:
        root, name, target = self._copy_baseline("prepare_cli")
        with redirect_stdout(io.StringIO()):
            result = prepare_cli.main([
                "--generation-run-name", name,
                "--pilot-root", str(root),
                "--endpoint", ENDPOINT,
                "--model-id", MODEL_ID,
                "--temperature", "0",
                "--top-p", "1",
                "--max-output-tokens-per-request", "100",
                "--response-format", "json_schema",
                "--max-requests", "7",
                "--max-input-tokens", "100000",
                "--max-output-tokens", "700",
                "--max-total-tokens", "100700",
                "--timeout-seconds", "60",
                "--max-retries", "2",
            ])
        self.assertEqual(result, 0)
        self.assertTrue((target / "execution/real_execution_plan.json").is_file())

    def test_83_check_cli_accepts_prepared_stage_offline(self) -> None:
        root, name, _, _ = self._prepare("check_cli")
        output = io.StringIO()
        with redirect_stdout(output):
            result = check_cli.main([
                "--generation-run-name", name, "--pilot-root", str(root),
            ])
        self.assertEqual(result, 0)
        self.assertIn("check_real_execution: PASS", output.getvalue())

    def test_84_cost_budget_fails_closed_without_pinned_pricing(self) -> None:
        with self.assertRaisesRegex(ValueError, "cost_budget_requires_explicit_pricing"):
            self._budget(max_estimated_cost=1.0, currency="USD").validate()

    def test_85_provider_usage_overrun_stops_with_failure_receipt(self) -> None:
        root, name, target, _ = self._prepare("usage_overrun")
        backend, transport = self._backend([
            provider_response(prompt_tokens=100_001, completion_tokens=5),
        ])
        with self.assertRaisesRegex(ValueError, "provider_usage_exceeded_hard_budget"):
            run_real_execution(
                generation_run_name=name, generation_root=root, endpoint=ENDPOINT,
                execute_real_api=True, authorization=REAL_API_AUTHORIZATION_SCOPE,
                credential_reader=lambda _: TEST_CREDENTIAL, backend=backend,
            )
        receipts = read_jsonl(target / "execution/real_execution_receipts.jsonl")
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0]["execution_status"], "failed")
        self.assertEqual(receipts[0]["safe_error_code"], "provider_usage_exceeded_hard_budget")


if __name__ == "__main__":
    unittest.main()
