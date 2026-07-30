# M017 Runnable Evidence-Grounded Web Demo

## What M017 is

M017 is the first complete local browser demonstration for eNH3-Bench. It presents the
seven frozen B1B0 development cases, their questions, and their bounded evidence; runs a
deterministic fixture by default; and can optionally send one selected case to the configured
USTC model after an explicitly live-enabled startup.

This is a product demonstration, not a benchmark release. Fixture output is not scientific
output. Live output is not automatically accepted into the benchmark.

## Separation from M016

The M017 demo is an independent execution path. It does not prepare or consume an RE16,
use the M016 authorization scopes, update the M016 journal, acquire the M016 execution lock,
create benchmark candidate outputs, import results, judge answers, create human labels, or
release holdout material. M016 runtimes are not modified.

M017 reuses only read-only scientific inputs and safe constants:

- the frozen B1B0 development selection;
- compiled prompts and request-envelope bindings;
- bounded evidence blocks;
- the USTC endpoint/profile identity;
- common canonical JSON behavior.

## Architecture

The vertical slice intentionally has few moving parts:

- `enh3bench/demo_v017.py`: case repository, tolerant parser, one-worker job queue, sanitized
  atomic run store, explicit live transport, model preflight, and standard-library HTTP server;
- `scripts/run_demo_v017.py`: Python 3.10+ command-line entry point;
- `scripts/start_demo_v017.ps1`: safe fixture/live launcher;
- `demo_v017/static/`: vanilla HTML, CSS, and JavaScript;
- `demo_v017/fixtures/fixture_outputs.json`: seven deterministic non-scientific fixtures;
- `<demo-root>/runs/`: one sanitized JSON record per run, outside Git.

The server uses `ThreadingHTTPServer` for local HTTP handling and
`ThreadPoolExecutor(max_workers=1)` for the execution queue. Browser run creation returns
HTTP 202 immediately and the UI polls the run record about once per second. No database,
WebSocket, frontend framework, bundler, cloud service, authentication, or analytics is used.

## Fixture mode

Fixture mode is the default and requires no credential. It performs no provider network call.
Every case returns the same clearly marked path-confirmation message, empty claims and
citations, and the warning `DEMO_FIXTURE_NOT_MODEL_OUTPUT`.

The exact Fixture summary is:

> Fixture 已验证案例加载、异步执行、结果持久化、浏览器轮询和界面渲染的完整链路。此内容不是模型生成的科学结论。

Exact launcher command:

```powershell
powershell -ExecutionPolicy Bypass `
  -File scripts\start_demo_v017.ps1 `
  -Fixture
```

The recommended direct Python equivalent is:

```powershell
C:\Python314\python.exe scripts\run_demo_v017.py `
  --pilot-root F:\eNH3_Bench_API\v016_b1b0 `
  --generation-run-name enrr_generation_pilot_v016_b1b0_20260722 `
  --demo-root F:\eNH3_Bench_API\v017_demo_runtime
```

Open <http://127.0.0.1:8765> after the server starts.

The PowerShell launcher selects Python in this order: `C:\Python314\python.exe` when
present, `python.exe`, `python`, then `py -3`. It rejects versions older than Python 3.10.

## Live mode

Live controls are unavailable unless the server process was started explicitly with live API
enabled. The browser cannot enable them. The PowerShell launcher securely prompts for the
key, places it only in the current process environment, starts Python with
`--enable-live-api`, and removes the environment variable in a `finally` block after the
server exits.

Exact launcher command:

```powershell
powershell -ExecutionPolicy Bypass `
  -File scripts\start_demo_v017.ps1 `
  -Live
```

The key must never be entered in a command-line argument, source file, plan, fixture, browser
field, or run record. It is read from `ENH3BENCH_API_KEY` only inside an explicit model
preflight or live run. It is not read at import, startup, health checks, case browsing, or
fixture execution. It is never printed, hashed, returned to the browser, persisted, or logged.

Live requests may consume USTC project tokens. Automatic retries are disabled. A manual
rerun is a separate provider request. The default client waiting ceiling is 900 seconds; it
is not a provider service guarantee.

## Model preflight flow

1. Start with `-Live` and open the local page.
2. Click **检查新 Key 的模型权限**.
3. The server reads the key for that operation and makes exactly one GET request to
   `https://api.llm.ustc.edu.cn/v1/models`.
4. The browser receives only status, HTTP status, model count, target-model visibility,
   latency, timestamp, and a safe error code.
5. Live remains disabled unless status is `succeeded`, HTTP status is 200, and the target
   model is visible. This browser-session state resets on refresh.
6. A successful preflight does not automatically send a chat completion.

Preflight is never invoked automatically at startup.

## Single-case live run flow

1. Select one of the seven frozen cases.
2. Inspect its question and bounded evidence.
3. Select **LIVE API**.
4. Click **运行所选案例**.
5. Confirm the native browser dialog showing the selected case, model, `max_tokens`, timeout,
   one-request/no-retry policy, and possible project-token consumption.
6. Only after confirmation, the server persists a queued record and returns HTTP 202.
7. The single worker reads the key, builds the frozen case payload, and makes exactly one POST
   to the configured `/v1/chat/completions` endpoint.
8. The UI polls until the run is structured, unstructured, or failed.

There is no arbitrary prompt input. The live payload contains exactly `model`, `messages`,
and `max_tokens`. The default requested model is `deepseek-v4-pro`; the default
`max_tokens` value is 4096. Normal answer content may be retained, while
`reasoning_content`, headers, and credentials are discarded.

## HTTP routes

| Route | Purpose |
| --- | --- |
| `GET /health` | Server status, version, and live-enabled flag |
| `GET /api/config` | Safe provider/demo configuration |
| `GET /api/cases` | Seven canonical case summaries |
| `GET /api/cases/{case_id}` | Safe case detail and bounded evidence |
| `POST /api/preflight/models` | Explicit, live-only model-list check |
| `POST /api/runs` | Queue one fixture or live run; returns HTTP 202 |
| `GET /api/runs/{run_id}` | Complete sanitized run record |
| `GET /api/runs?limit=20` | Newest-first sanitized history |
| `GET /` | Web application |
| `GET /static/app.js` | Local JavaScript |
| `GET /static/styles.css` | Local CSS |

## Run records

Each run is atomically written to:

```text
F:\eNH3_Bench_API\v017_demo_runtime\runs\<run_id>.json
```

The root can be changed with `--demo-root` or `-DemoRoot`, but it must remain outside the
repository. The schema is `0.17-demo-run.1`. Records contain safe case, status, timing,
model, response ID, HTTP, finish reason, usage, parse, answer, citation, warning, and safe
error fields.

Records exclude the key, Authorization header, request headers, complete request, complete
compiled prompt, credential hash, Windows username, repository path, provider reasoning,
benchmark judgment, and Gold labels.

Run states are:

- `queued`
- `running`
- `succeeded_structured`
- `succeeded_unstructured`
- `failed`

## Tolerant parser levels

The demo preserves readable answers even when formatting is imperfect:

1. `strict_json`: direct JSON object parsing;
2. `fenced_json`: remove one surrounding Markdown JSON fence, then parse;
3. `extracted_json`: parse the first balanced JSON object within surrounding prose;
4. `unstructured_text`: retain readable text when JSON parsing fails.

The last three levels display visible warnings. Unstructured text is not represented as
schema-valid benchmark output. Missing citations are never fabricated.

## Configuration

`scripts/run_demo_v017.py` supports:

- `--pilot-root`
- `--generation-run-name`
- `--demo-root`
- `--host` (default `127.0.0.1`)
- `--port` (default `8765`)
- `--endpoint` (default USTC chat-completions endpoint)
- `--model-id` (default `deepseek-v4-pro`)
- `--timeout-seconds` (default `900`)
- `--max-output-tokens` (default `4096`)
- `--enable-live-api` (off by default)

The PowerShell launcher additionally supports `-PilotRoot`, `-GenerationRunName`,
`-DemoRoot`, and `-Port`.

## Stop the server

Press `Ctrl+C` in the terminal running the server. The HTTP server stops, the one-worker
executor shuts down, and live launcher cleanup removes the process environment variable.

## Known limitations

- It is a single-user local demo with one execution worker.
- There is no cancellation endpoint for an in-flight provider request.
- Run history is local JSON, not a database.
- Tolerant parsing improves display continuity but does not constitute benchmark validation.
- The UI does not import, score, judge, or review results.
- A client timeout cannot determine whether a provider completed work server-side.

## Troubleshooting

**Startup says `pilot_root_missing` or `generation_run_missing`:** verify the frozen B1B0
root and generation run name. Do not point the demo at a holdout or M016 execution runtime.

**Startup reports a case/order/binding mismatch:** the demo requires the exact canonical
seven-case B1B0 package. Do not rewrite the source package; restore or select the reviewed
frozen runtime.

**`demo_root_must_be_outside_repository`:** choose an external directory such as
`F:\eNH3_Bench_API\v017_demo_runtime`.

**Live controls are disabled:** stop the fixture server and restart with `-Live`, then complete
a successful explicit model preflight. The browser cannot elevate fixture-only startup, and
each page refresh requires another preflight.

**`credential_missing`:** stop the server and use the secure `-Live` launcher again. Do not
place the key in a command or file.

**Timeout or connection failure:** the run record contains only a safe category. Automatic
retry is disabled; clicking run again would create a new provider request and may consume
additional tokens.
