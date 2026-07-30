from __future__ import annotations

import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

import requests

from enh3bench.demo_v017 import (
    API_KEY_ENVIRONMENT_VARIABLE,
    DEMO_RUN_FIELDS,
    EXPECTED_CASE_IDS,
    FIXTURE_MESSAGE,
    FIXTURE_WARNING,
    REQUEST_BODY_SIZE_LIMIT,
    CaseRepository,
    DemoConfig,
    DemoConfigurationError,
    DemoHTTPServer,
    DemoSafeError,
    DemoService,
    FixtureRepository,
    TERMINAL_RUN_STATES,
    USTC_MODELS_ENDPOINT,
    build_live_payload,
    parse_demo_content,
)


ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "demo_v017/static"
FIXTURE_PATH = ROOT / "demo_v017/fixtures/fixture_outputs.json"
APP_PATH = STATIC_ROOT / "app.js"
HTML_PATH = STATIC_ROOT / "index.html"
STYLES_PATH = STATIC_ROOT / "styles.css"
LAUNCHER_PATH = ROOT / "scripts/start_demo_v017.ps1"


class FakeResponse:
    def __init__(self, status_code: int = 200, body: object | None = None) -> None:
        self.status_code = status_code
        self.body = body

    def json(self) -> object:
        if isinstance(self.body, BaseException):
            raise self.body
        return self.body


def successful_body(content: str | None = None) -> dict:
    return {
        "id": "provider-response-1",
        "model": "deepseek-v4-pro",
        "choices": [{
            "finish_reason": "stop",
            "message": {
                "content": content or json.dumps({
                    "answer_text": "Safe test answer.",
                    "claims": [],
                    "citations": [],
                }),
                "reasoning_content": "must be discarded",
            },
        }],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


class FakeHTTPClient:
    def __init__(
        self,
        *,
        get_result: FakeResponse | BaseException | None = None,
        post_result: FakeResponse | BaseException | None = None,
    ) -> None:
        self.get_result = get_result or FakeResponse(200, {"data": [{"id": "deepseek-v4-pro"}]})
        self.post_result = post_result or FakeResponse(200, successful_body())
        self.get_calls: list[tuple] = []
        self.post_calls: list[tuple] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.get_calls.append((url, kwargs))
        if isinstance(self.get_result, BaseException):
            raise self.get_result
        return self.get_result

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.post_calls.append((url, kwargs))
        if isinstance(self.post_result, BaseException):
            raise self.post_result
        return self.post_result


def synthetic_contract(run_name: str) -> tuple[dict, dict, list[dict], list[dict]]:
    selected = []
    prompts = []
    envelopes = []
    answerability = [
        "answerable", "partially_answerable", "insufficient_evidence", "answerable",
        "partially_answerable", "insufficient_evidence", "partially_answerable",
    ]
    for index, case_id in enumerate(EXPECTED_CASE_IDS, start=1):
        paper_id = f"P{index:04d}_DEMO"
        case_type = f"task_type_{index}"
        prompt_id = f"GP16_TEST_{index}"
        compiled_hash = f"{index:064x}"
        selected.append({
            "case_id": case_id,
            "paper_id": paper_id,
            "case_type": case_type,
            "answerability_status": answerability[index - 1],
        })
        prompts.append({
            "case_id": case_id,
            "paper_id": paper_id,
            "case_type": case_type,
            "question": f"What does bounded evidence support for case {index}?",
            "required_answer_sections": ["answer"],
            "expected_answer_contract": {"case_type": case_type},
            "allowed_source_span_ids": [f"S{index:03d}"],
            "allowed_evidence_link_ids": [],
            "bounded_source_context": [{
                "context_role": "primary_evidence",
                "source_span_id": f"S{index:03d}",
                "evidence_link_id": None,
                "source_node_id": f"N{index:03d}",
                "excerpt": f"Bounded development evidence {index}.",
            }],
            "prompt_contract_text": "Return evidence-grounded JSON only.",
            "response_json_schema": {"type": "object"},
            "prompt_instance_id": prompt_id,
            "prompt_version": "v016-test",
            "compiled_prompt_sha256": compiled_hash,
        })
        envelopes.append({
            "case_id": case_id,
            "paper_id": paper_id,
            "prompt_instance_id": prompt_id,
            "compiled_prompt_sha256": compiled_hash,
            "request_envelope_id": f"RQ16_TEST_{index}",
            "request_sha256": f"{index + 20:064x}",
        })
    return (
        {"generation_run_name": run_name, "generation_run_id": "GR16_TEST"},
        {"selected_cases": selected, "pilot_selection_id": "PS16_TEST"},
        prompts,
        envelopes,
    )


class DemoV017Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repository_root = self.base / "repository"
        self.repository_root.mkdir()
        self.pilot_root = self.base / "pilot"
        self.run_name = "frozen_development_test"
        (self.pilot_root / self.run_name).mkdir(parents=True)
        self.demo_root = self.base / "demo_runtime"
        self.contract = synthetic_contract(self.run_name)
        self.loader_calls: list[tuple[Path, str]] = []
        self.services: list[DemoService] = []
        self.servers: list[tuple[DemoHTTPServer, threading.Thread]] = []

    def tearDown(self) -> None:
        for server, thread in self.servers:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
        for service in self.services:
            service.shutdown(wait=True)
        self.temporary.cleanup()

    def loader(self, run_dir: Path, run_name: str):
        self.loader_calls.append((run_dir, run_name))
        return self.contract

    def cases(self) -> CaseRepository:
        return CaseRepository(self.pilot_root, self.run_name, contract_loader=self.loader)

    def config(self, *, live_enabled: bool = False, demo_root: Path | None = None) -> DemoConfig:
        return DemoConfig(
            pilot_root=self.pilot_root,
            generation_run_name=self.run_name,
            demo_root=demo_root or self.demo_root,
            host="127.0.0.1",
            port=0,
            live_enabled=live_enabled,
            repository_root=self.repository_root,
        )

    def service(
        self,
        *,
        live_enabled: bool = False,
        http_client: FakeHTTPClient | None = None,
        credential_reader=None,
        demo_root: Path | None = None,
    ) -> DemoService:
        reader = credential_reader or (lambda _: (_ for _ in ()).throw(AssertionError("credential read")))
        service = DemoService(
            self.config(live_enabled=live_enabled, demo_root=demo_root),
            self.cases(),
            FixtureRepository(FIXTURE_PATH),
            http_client=http_client or FakeHTTPClient(
                get_result=AssertionError("network GET"), post_result=AssertionError("network POST"),
            ),
            credential_reader=reader,
        )
        self.services.append(service)
        return service

    def start_http(self, service: DemoService) -> tuple[str, int]:
        server = DemoHTTPServer(("127.0.0.1", 0), service, STATIC_ROOT)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append((server, thread))
        return server.server_address[0], server.server_address[1]

    def request(
        self,
        address: tuple[str, int],
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, bytes, dict[str, str]]:
        connection = http.client.HTTPConnection(*address, timeout=5)
        request_headers = dict(headers or {})
        if body is not None and "Content-Length" not in request_headers:
            request_headers["Content-Length"] = str(len(body))
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        payload = response.read()
        result_headers = {key.lower(): value for key, value in response.getheaders()}
        status = response.status
        connection.close()
        return status, payload, result_headers

    def wait_terminal(self, service: DemoService, run_id: str, timeout: float = 3) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            record = service.get_run(run_id)
            if record["status"] in TERMINAL_RUN_STATES:
                return record
            time.sleep(0.01)
        self.fail(f"run did not become terminal: {run_id}")

    def test_01_exact_seven_case_order_is_loaded(self) -> None:
        self.assertEqual([row["case_id"] for row in self.cases().summaries()], list(EXPECTED_CASE_IDS))

    def test_02_missing_source_package_fails_clearly(self) -> None:
        with self.assertRaisesRegex(DemoConfigurationError, "pilot_root_missing"):
            CaseRepository(self.base / "missing", self.run_name, contract_loader=self.loader)

    def test_03_unknown_case_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(DemoSafeError, "unknown_case_id"):
            self.cases().detail("EC16_UNKNOWN")

    def test_04_fixture_mode_reads_no_credential(self) -> None:
        service = self.service()
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="fixture")
        self.assertEqual(self.wait_terminal(service, queued["run_id"])["status"], "succeeded_structured")

    def test_05_fixture_mode_makes_no_network_call(self) -> None:
        client = FakeHTTPClient(get_result=AssertionError("GET"), post_result=AssertionError("POST"))
        service = self.service(http_client=client)
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="fixture")
        self.wait_terminal(service, queued["run_id"])
        self.assertEqual((client.get_calls, client.post_calls), ([], []))

    def test_06_fixture_run_completes_and_persists(self) -> None:
        service = self.service()
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[1], mode="fixture")
        record = self.wait_terminal(service, queued["run_id"])
        self.assertEqual(record["status"], "succeeded_structured")
        self.assertTrue((self.demo_root / "runs" / f"{queued['run_id']}.json").is_file())
        self.assertEqual(set(record), DEMO_RUN_FIELDS)

    def test_07_fixture_warning_is_present(self) -> None:
        service = self.service()
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[2], mode="fixture")
        record = self.wait_terminal(service, queued["run_id"])
        self.assertIn(FIXTURE_WARNING, record["warnings"])
        self.assertEqual(record["answer_text"], FIXTURE_MESSAGE)

    def test_08_run_record_excludes_credential_fields(self) -> None:
        service = self.service()
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="fixture")
        self.wait_terminal(service, queued["run_id"])
        text = (self.demo_root / "runs" / f"{queued['run_id']}.json").read_text(encoding="utf-8").lower()
        self.assertNotIn("api_key", text)
        self.assertNotIn("credential_hash", text)

    def test_09_run_record_excludes_authorization_headers(self) -> None:
        service = self.service()
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="fixture")
        self.wait_terminal(service, queued["run_id"])
        text = (self.demo_root / "runs" / f"{queued['run_id']}.json").read_text(encoding="utf-8").lower()
        self.assertNotIn("authorization", text)
        self.assertNotIn("bearer ", text)

    def test_10_run_record_excludes_reasoning_content(self) -> None:
        content = json.dumps({
            "answer_text": "Visible answer", "claims": [], "citations": [],
            "reasoning_content": "hidden nested reasoning",
        })
        client = FakeHTTPClient(post_result=FakeResponse(200, successful_body(content)))
        service = self.service(live_enabled=True, http_client=client, credential_reader=lambda _: "test-key")
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="live")
        self.wait_terminal(service, queued["run_id"])
        text = (self.demo_root / "runs" / f"{queued['run_id']}.json").read_text(encoding="utf-8")
        self.assertNotIn("reasoning_content", text)
        self.assertNotIn("hidden nested reasoning", text)

    def test_11_strict_json_parsing(self) -> None:
        result = parse_demo_content('{"answer_text":"strict","citations":[]}')
        self.assertEqual((result["parse_level"], result["answer_text"]), ("strict_json", "strict"))

    def test_12_fenced_json_parsing(self) -> None:
        result = parse_demo_content('```json\n{"answer_text":"fenced","citations":[]}\n```')
        self.assertEqual(result["parse_level"], "fenced_json")
        self.assertIn("DEMO_TOLERANT_PARSE_FENCED_JSON", result["warnings"])

    def test_13_balanced_json_extraction(self) -> None:
        result = parse_demo_content('Preface {"answer_text":"extracted","nested":{"x":"}"}} suffix')
        self.assertEqual((result["parse_level"], result["answer_text"]), ("extracted_json", "extracted"))

    def test_14_unstructured_text_is_preserved(self) -> None:
        result = parse_demo_content("Readable scientific prose without JSON.")
        self.assertEqual(result["parse_level"], "unstructured_text")
        self.assertEqual(result["answer_text"], "Readable scientific prose without JSON.")

    def test_15_empty_provider_content_fails(self) -> None:
        body = successful_body(" ")
        body["choices"][0]["message"]["content"] = " "
        service = self.service(
            live_enabled=True,
            http_client=FakeHTTPClient(post_result=FakeResponse(200, body)),
            credential_reader=lambda _: "test-key",
        )
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="live")
        record = self.wait_terminal(service, queued["run_id"])
        self.assertEqual((record["status"], record["safe_error_code"]), ("failed", "provider_empty_content"))

    def test_16_live_mode_is_disabled_by_default(self) -> None:
        service = self.service()
        self.assertFalse(service.config_view()["live_enabled"])
        with self.assertRaisesRegex(DemoSafeError, "live_api_disabled"):
            service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="live")

    def test_17_browser_cannot_enable_live_mode(self) -> None:
        service = self.service()
        address = self.start_http(service)
        body = json.dumps({"case_id": EXPECTED_CASE_IDS[0], "mode": "live"}).encode()
        status, payload, _ = self.request(address, "POST", "/api/runs", body, {"Content-Type": "application/json"})
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(payload)["safe_error_code"], "live_api_disabled")

    def test_18_missing_credential_fails_safely(self) -> None:
        client = FakeHTTPClient()
        service = self.service(live_enabled=True, http_client=client, credential_reader=lambda _: None)
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="live")
        record = self.wait_terminal(service, queued["run_id"])
        self.assertEqual(record["safe_error_code"], "credential_missing")
        self.assertEqual(client.post_calls, [])

    def test_19_fake_models_preflight_reports_target_visibility(self) -> None:
        client = FakeHTTPClient(get_result=FakeResponse(200, {"data": [
            {"id": "other-model", "private": "ignored"}, {"id": "deepseek-v4-pro"},
        ]}))
        service = self.service(live_enabled=True, http_client=client, credential_reader=lambda _: "test-key")
        result = service.preflight_models()
        self.assertEqual((result["status"], result["model_count"], result["target_model_visible"]), ("succeeded", 2, True))
        self.assertEqual(set(result), {
            "status", "http_status", "model_count", "target_model", "target_model_visible",
            "latency_seconds", "checked_at_utc", "safe_error_code",
        })

    def test_20_fake_models_preflight_makes_exactly_one_get(self) -> None:
        client = FakeHTTPClient()
        service = self.service(live_enabled=True, http_client=client, credential_reader=lambda _: "test-key")
        service.preflight_models()
        self.assertEqual(len(client.get_calls), 1)
        self.assertEqual(client.get_calls[0][0], USTC_MODELS_ENDPOINT)

    def test_21_fake_live_run_makes_exactly_one_post(self) -> None:
        client = FakeHTTPClient()
        service = self.service(live_enabled=True, http_client=client, credential_reader=lambda _: "test-key")
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="live")
        self.assertEqual(self.wait_terminal(service, queued["run_id"])["status"], "succeeded_structured")
        self.assertEqual(len(client.post_calls), 1)

    def test_22_fake_live_run_has_zero_retries(self) -> None:
        client = FakeHTTPClient(post_result=FakeResponse(500, {"error": "safe fake"}))
        service = self.service(live_enabled=True, http_client=client, credential_reader=lambda _: "test-key")
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="live")
        record = self.wait_terminal(service, queued["run_id"])
        self.assertEqual(record["status"], "failed")
        self.assertEqual(len(client.post_calls), 1)

    def test_23_fake_live_payload_has_exact_three_fields(self) -> None:
        payload = build_live_payload(self.cases().prompt(EXPECTED_CASE_IDS[0]), model_id="deepseek-v4-pro", max_output_tokens=4096)
        self.assertEqual(set(payload), {"model", "messages", "max_tokens"})

    def test_24_fake_live_run_uses_configured_timeout(self) -> None:
        client = FakeHTTPClient()
        service = self.service(live_enabled=True, http_client=client, credential_reader=lambda _: "test-key")
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="live")
        self.wait_terminal(service, queued["run_id"])
        self.assertEqual(client.post_calls[0][1]["timeout"], 900.0)

    def test_25_fake_live_run_persists_safe_usage(self) -> None:
        service = self.service(live_enabled=True, http_client=FakeHTTPClient(), credential_reader=lambda _: "test-key")
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="live")
        record = self.wait_terminal(service, queued["run_id"])
        self.assertEqual(record["usage"], {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18})

    def test_26_fake_provider_timeout_is_classified(self) -> None:
        client = FakeHTTPClient(post_result=requests.Timeout("fake timeout"))
        service = self.service(live_enabled=True, http_client=client, credential_reader=lambda _: "test-key")
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="live")
        self.assertEqual(self.wait_terminal(service, queued["run_id"])["safe_error_code"], "provider_timeout")
        self.assertEqual(len(client.post_calls), 1)

    def test_27_fake_http_401_is_unauthorized(self) -> None:
        client = FakeHTTPClient(post_result=FakeResponse(401, {"detail": "ignored"}))
        service = self.service(live_enabled=True, http_client=client, credential_reader=lambda _: "test-key")
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="live")
        record = self.wait_terminal(service, queued["run_id"])
        self.assertEqual((record["safe_error_code"], record["http_status"]), ("provider_unauthorized", 401))

    def test_28_background_post_returns_202_immediately(self) -> None:
        service = self.service()
        address = self.start_http(service)
        body = json.dumps({"case_id": EXPECTED_CASE_IDS[0], "mode": "fixture"}).encode()
        started = time.monotonic()
        status, payload, _ = self.request(address, "POST", "/api/runs", body, {"Content-Type": "application/json"})
        elapsed = time.monotonic() - started
        self.assertEqual(status, 202)
        self.assertLess(elapsed, 1.0)
        self.assertEqual(json.loads(payload)["status"], "queued")

    def test_29_run_polling_reaches_terminal_state(self) -> None:
        service = self.service()
        address = self.start_http(service)
        body = json.dumps({"case_id": EXPECTED_CASE_IDS[0], "mode": "fixture"}).encode()
        _, payload, _ = self.request(address, "POST", "/api/runs", body, {"Content-Type": "application/json"})
        poll_url = json.loads(payload)["poll_url"]
        deadline = time.monotonic() + 3
        record = None
        while time.monotonic() < deadline:
            status, payload, _ = self.request(address, "GET", poll_url)
            self.assertEqual(status, 200)
            record = json.loads(payload)
            if record["status"] in TERMINAL_RUN_STATES:
                break
            time.sleep(0.02)
        self.assertIn(record["status"], TERMINAL_RUN_STATES)

    def test_30_history_is_newest_first(self) -> None:
        service = self.service()
        first = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="fixture")
        self.wait_terminal(service, first["run_id"])
        time.sleep(0.01)
        second = service.submit_run(case_id=EXPECTED_CASE_IDS[1], mode="fixture")
        self.wait_terminal(service, second["run_id"])
        self.assertEqual([row["run_id"] for row in service.history(2)], [second["run_id"], first["run_id"]])

    def test_31_request_body_size_limit(self) -> None:
        service = self.service()
        address = self.start_http(service)
        body = b"{" + b"x" * REQUEST_BODY_SIZE_LIMIT + b"}"
        status, payload, _ = self.request(address, "POST", "/api/runs", body, {"Content-Type": "application/json"})
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(payload)["safe_error_code"], "request_body_too_large")

    def test_32_api_path_traversal_is_rejected(self) -> None:
        service = self.service()
        address = self.start_http(service)
        status, payload, _ = self.request(address, "GET", "/api/cases/%2e%2e/secret")
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(payload)["safe_error_code"], "api_path_invalid")

    def test_33_static_assets_are_served(self) -> None:
        service = self.service()
        address = self.start_http(service)
        for path, mime in (("/", "text/html"), ("/static/app.js", "text/javascript"), ("/static/styles.css", "text/css")):
            status, payload, headers = self.request(address, "GET", path)
            self.assertEqual(status, 200)
            self.assertTrue(payload)
            self.assertIn(mime, headers["content-type"])

    def test_34_health_endpoint(self) -> None:
        service = self.service()
        address = self.start_http(service)
        status, payload, _ = self.request(address, "GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload), {"status": "ok", "version": "M017-D0-D1", "live_enabled": False})

    def test_35_no_m016_runtime_file_is_modified(self) -> None:
        sentinel = self.pilot_root / self.run_name / "m016_sentinel.json"
        sentinel.write_text('{"immutable":true}\n', encoding="utf-8")
        before = sentinel.read_bytes()
        service = self.service()
        queued = service.submit_run(case_id=EXPECTED_CASE_IDS[0], mode="fixture")
        self.wait_terminal(service, queued["run_id"])
        self.assertEqual(sentinel.read_bytes(), before)
        self.assertEqual([path.name for path in (self.pilot_root / self.run_name).iterdir()], ["m016_sentinel.json"])

    def test_36_global_hidden_rule_overrides_component_display(self) -> None:
        css = STYLES_PATH.read_text(encoding="utf-8")
        self.assertIn("[hidden] {\n  display: none !important;\n}", css)

    def test_37_fixture_summary_is_chinese_primary_and_non_scientific(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        summaries = {row["structured_output"]["summary"] for row in fixture["outputs"]}
        self.assertEqual(summaries, {FIXTURE_MESSAGE})
        self.assertIn("此内容不是模型生成的科学结论", FIXTURE_MESSAGE)

    def test_38_all_fixture_claims_are_empty(self) -> None:
        outputs = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["outputs"]
        self.assertTrue(all(row["structured_output"]["claims"] == [] for row in outputs))

    def test_39_all_fixture_citations_are_empty(self) -> None:
        outputs = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["outputs"]
        self.assertTrue(all(row["structured_output"]["citations"] == [] for row in outputs))

    def test_40_all_fixture_warnings_and_display_flags_are_safe(self) -> None:
        outputs = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["outputs"]
        for row in outputs:
            self.assertIn(FIXTURE_WARNING, row["warnings"])
            self.assertEqual(
                row["structured_output"]["display_metadata"],
                {"fixture": True, "scientific_conclusion": False},
            )

    def test_41_metadata_panel_contains_provider(self) -> None:
        html = HTML_PATH.read_text(encoding="utf-8")
        self.assertIn("<dt>Provider</dt>", html)

    def test_42_metadata_values_have_explicit_ids(self) -> None:
        html = HTML_PATH.read_text(encoding="utf-8")
        expected = {
            "metadata-provider", "metadata-configured-model", "metadata-reported-model",
            "metadata-response-id", "metadata-http-status", "metadata-finish-reason",
            "metadata-latency", "metadata-usage", "metadata-timeout", "metadata-max-tokens",
        }
        self.assertTrue(all(f'id="{value}"' in html for value in expected))
        self.assertNotIn('querySelectorAll("dd")', APP_PATH.read_text(encoding="utf-8"))

    def test_43_fixture_configured_model_is_marked_not_called(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        self.assertIn("`${record.requested_model} · not called`", app)
        self.assertIn('fixture ? "deterministic-fixture"', app)

    def test_44_fixture_http_fields_say_no_provider_request(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        self.assertIn('const noProviderRequest = "N/A · no provider request";', app)
        self.assertIn('$("metadata-response-id").textContent = fixture ? noProviderRequest', app)
        self.assertIn('$("metadata-http-status").textContent = fixture ? noProviderRequest', app)
        self.assertIn('$("metadata-finish-reason").textContent = fixture ? noProviderRequest', app)
        self.assertIn('$("metadata-usage").textContent = fixture ? noProviderRequest', app)

    def test_45_fixture_timeout_and_max_tokens_are_marked_not_used(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        self.assertIn("`${record.timeout_seconds}s · not used by fixture`", app)
        self.assertIn("`${record.max_output_tokens} · not used by fixture`", app)

    def test_46_live_radio_starts_disabled_even_when_live_is_configured(self) -> None:
        html = HTML_PATH.read_text(encoding="utf-8")
        app = APP_PATH.read_text(encoding="utf-8")
        self.assertIn('id="live-mode" type="radio" name="mode" value="live" disabled', html)
        self.assertIn('$("live-mode").disabled = true;', app)
        self.assertNotIn('$("live-mode").disabled = !config.live_enabled;', app)

    def test_47_successful_visible_preflight_enables_live(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        condition = (
            'result.status === "succeeded" && result.http_status === 200 '
            '&& result.target_model_visible === true'
        )
        self.assertIn(condition, app)
        self.assertIn('$("live-mode").disabled = !passed;', app)
        self.assertIn('preflight-success', app)

    def test_48_target_invisible_preflight_keeps_live_disabled(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        self.assertIn('if (!passed) selectFixtureMode();', app)
        self.assertIn('if (!passed) lines.push("Live 执行仍处于禁用状态。");', app)

    def test_49_failed_preflight_keeps_live_disabled_and_fixture_selected(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        catch_block = app.split('} catch (error) {', 3)[-1].split('} finally {', 1)[0]
        self.assertIn('state.preflightPassed = false;', catch_block)
        self.assertIn('$("live-mode").disabled = true;', catch_block)
        self.assertIn('selectFixtureMode();', catch_block)

    def test_50_refresh_requires_new_preflight_by_construction(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        self.assertIn('preflightPassed: false,', app)
        render_config = app.split("function renderConfig(config)", 1)[1].split("function renderCaseList", 1)[0]
        self.assertIn('state.preflightPassed = false;', render_config)
        self.assertNotIn("localStorage", app)

    def test_51_live_confirmation_cancellation_sends_no_run_post(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        run_function = app.split("async function runSelectedCase()", 1)[1].split("async function pollRun", 1)[0]
        cancel_block = run_function.split("if (!confirmed) {", 1)[1].split("}", 1)[0]
        self.assertIn("return;", cancel_block)
        self.assertNotIn('api("/api/runs"', cancel_block)
        self.assertLess(run_function.index("if (!confirmed)"), run_function.index('api("/api/runs"'))

    def test_52_live_confirmation_acceptance_has_exactly_one_run_post(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        run_function = app.split("async function runSelectedCase()", 1)[1].split("async function pollRun", 1)[0]
        self.assertEqual(run_function.count('api("/api/runs"'), 1)
        for required in (
            "state.selectedCase.case_id", "state.config.model", "state.config.max_output_tokens",
            "state.config.timeout_seconds", "一次 POST 请求", "不自动重试", "USTC 项目 Token",
        ):
            self.assertIn(required, run_function)

    def test_53_fixture_run_requires_no_confirmation(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        run_function = app.split("async function runSelectedCase()", 1)[1].split("async function pollRun", 1)[0]
        self.assertIn('if (mode === "live") {', run_function)
        self.assertEqual(run_function.count("window.confirm("), 1)

    def test_54_double_click_protection_prevents_duplicate_submission(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        run_function = app.split("async function runSelectedCase()", 1)[1].split("async function pollRun", 1)[0]
        self.assertIn("if (!state.selectedCase || state.runInProgress) return;", run_function)
        self.assertIn("state.runInProgress = true;", run_function)
        self.assertLess(run_function.index("state.runInProgress = true;"), run_function.index('api("/api/runs"'))
        self.assertGreaterEqual(app.count("state.runInProgress = false;"), 4)

    def test_55_truncated_case_metadata_has_title_and_aria_labels(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        for required in (
            'node.title = text;', 'node.setAttribute("aria-label"', '"完整案例 ID"',
            '"完整任务类型"', '"完整可回答性"', '"完整论文 ID"',
            'locator.title = String(block.source_locator);', '完整证据来源定位',
        ):
            self.assertIn(required, app)

    def test_56_launcher_has_ordered_python_fallbacks(self) -> None:
        script = LAUNCHER_PATH.read_text(encoding="utf-8")
        positions = [
            script.index('"C:\\Python314\\python.exe"'),
            script.index("Get-Command python.exe"),
            script.index("Get-Command python "),
            script.index("Get-Command py "),
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('$PythonPrefixArguments = @("-3")', script)
        self.assertIn('if ($PythonVersion -lt [version]"3.10")', script)

    def test_57_launcher_clears_process_key_and_bstr_in_finally(self) -> None:
        script = LAUNCHER_PATH.read_text(encoding="utf-8")
        finally_block = script.split("    finally {", 1)[1]
        self.assertIn("Remove-Item Env:ENH3BENCH_API_KEY", finally_block)
        self.assertIn("Remove-Variable ProcessKey", finally_block)
        self.assertIn("ZeroFreeBSTR($KeyPointer)", finally_block)

    def test_58_fixture_launcher_branch_has_no_credential_operation(self) -> None:
        script = LAUNCHER_PATH.read_text(encoding="utf-8")
        fixture_branch = script.rsplit("else {", 1)[1]
        self.assertIn("& $PythonCommand @PythonPrefixArguments @Arguments", fixture_branch)
        self.assertNotIn("ENH3BENCH_API_KEY", fixture_branch)
        self.assertNotIn("Read-Host", fixture_branch)


if __name__ == "__main__":
    unittest.main()
