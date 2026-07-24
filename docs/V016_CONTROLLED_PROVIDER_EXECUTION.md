# v0.16 Controlled Provider Execution (Phase B1B1)

Phase B1B1 is execution infrastructure, not scientific evaluation. It adds a small,
provider-neutral execution boundary around the seven-case B1B0 development pilot. It does
not authorize a model run, import an API output, judge an answer, collect a human label,
freeze an evaluation package, or release holdout material.

## Default state

The default is offline and fail closed. Preparation and validation do not read a credential
and do not open a network connection. The run entry point refuses execution unless all of
the following are present and valid:

1. the explicit `--execute-real-api` flag;
2. the exact versioned authorization scope
   `REAL_API_DEVELOPMENT_V016_B1B1`;
3. a previously prepared and internally consistent execution plan;
4. an explicitly configured OpenAI-compatible HTTPS chat-completions endpoint;
5. an explicitly configured model and generation parameters;
6. the approved seven-case B1B0 development selection, with zero holdout cases;
7. hard request, token, timeout, and retry limits;
8. a credential available only after all preceding gates pass.

There is no implicit provider, default external model, environment-driven automatic
execution, real-provider fallback, `--force` switch, or `--include-holdout` option.

## Provider boundary

`enh3bench.provider_execution.ProviderExecutionBackend` separates three operations:

- construction of a provider request from an existing B1B0 compiled prompt;
- transport execution;
- normalization of the provider response.

B1B1 implements one backend: a minimal Python standard-library HTTPS transport for the
OpenAI-compatible `/v1/chat/completions` endpoint. No provider SDK, agent framework, or
vendor-specific orchestration dependency is used. The provider payload is constructed only
from the compiled B1B0 prompt instance; the executor does not reread a paper or regenerate a
prompt.

The provider request retains the B1B0 `prompt_instance_id`, `compiled_prompt_sha256`,
`request_envelope_id`, and `request_sha256`. Transport headers are created in memory only and
are never added to the benchmark envelope or a serialized artifact.

## Authorization and credential lifecycle

The credential environment variable is `ENH3BENCH_API_KEY`. Its value is read only inside
the authorized execution function, after authorization, plan identity, endpoint identity,
development-only selection, request binding, and budget validation have passed.

The following operations never read the credential:

- B1B0 build, prompt preparation, dry run, cost estimate, and validator;
- `prepare_real_execution.py`;
- `check_real_execution.py`;
- any CLI `--help` path;
- an unauthorized `run_real_execution.py` invocation;
- the unit test suite.

The credential is not written to Git, the execution plan, request envelopes, receipts, raw
response artifacts, candidate outputs, logs, or exception messages. Endpoint URLs with user
information, query strings, fragments, non-HTTPS schemes, or unsupported paths are rejected.
Only a SHA-256 identity of the normalized safe endpoint is retained by the plan.

## Development-only gate

The evaluator-side B1B0 pilot selection manifest is the authority for execution scope. Before
execution, B1B1 requires:

- 7 selected cases;
- 7 development cases;
- 0 holdout cases;
- 7 unique approved case identities;
- exact equality among the selection, compiled prompts, and B1B0 request envelopes;
- valid prompt and request hash bindings.

Any unknown case, changed identity, holdout count, non-development selection reason, or
request-count change fails closed. Generator-visible input does not acquire a split field,
and no holdout batch is read or accepted by this executor.

## Execution plan and identity

Offline preparation writes this external-runtime artifact:

```text
execution/real_execution_plan.json
```

Its schema is `0.16-real-execution-plan.1`. The stable `RE16_...` identity binds the B1B0
generation and selection identities, backend name and version, model, safe endpoint hash,
approved request set, hard budgets, timeout, retry policy, authorization scope, and every
recorded generation parameter. It deliberately excludes creation time, absolute paths,
runtime root, and credentials.

Every result-affecting configured parameter is recorded: model, temperature, top-p, maximum
output tokens per request, optional seed, response format, and optional reasoning effort.
Unsupported parameters are not invented.

## Hard budgets, timeout, and retry

Preparation requires explicit hard limits for:

- requests (never more than seven);
- estimated input tokens;
- output tokens;
- total tokens;
- per-request timeout;
- retries (never more than two).

An optional estimated-cost limit requires an explicit pinned pricing contract. B1B1 does not
retrieve or pin provider pricing, so its current plans leave the cost limit null. Token and
request limits remain mandatory. Preflight rejects a plan before
any network operation if the approved request set cannot fit. The runner checks the remaining
budget before every request and stops when the next request cannot fit.

Retries are bounded and apply only to HTTP 408, 429, 500, 502, 503, and 504, or an explicitly
classified timeout/connection-reset failure. HTTP 400, 401, 403, 404, authorization failures,
schema failures, and other permanent failures are not retried. Backoff is finite; tests inject
a no-sleep function.

## Response and artifact boundaries

Transport success is not benchmark success. B1B1 separately checks:

1. transport and HTTP success;
2. expected provider model identity and usage fields;
3. a single response content string;
4. a single JSON object with no Markdown fence;
5. the exact closed B1B0 response, claim, and citation schemas;
6. source-span, evidence-link, and claim-reference allowlists.

External runtime layers remain distinct:

```text
provider_raw/provider_raw_responses.jsonl
execution/real_execution_receipts.jsonl
candidate_outputs/candidate_api_outputs.jsonl
```

Raw response records contain only request identity, safe provider metadata, usage, finish
reason, status, and response content. They never contain cookies, request headers, or a
credential. Receipts use schema `0.16-real-execution-receipt.1` and stable `RR16_...`
identities; they are not B1B0 fixture receipts.

A schema-valid and allowlist-valid response may become a candidate artifact using schema
`0.16-candidate-api-output.1`. Every candidate is marked `not_imported`. B1B1 never writes
`data/selective_eval/.../api_outputs.jsonl`; validation, inspection, and explicit import belong
to a later separately authorized phase.

## Offline runbook

Prepare a plan outside the repository after substituting reviewed values:

```powershell
C:\Python314\python.exe scripts\prepare_real_execution.py `
  --generation-run-name <approved-development-run> `
  --pilot-root <external-runtime-root> `
  --endpoint https://<reviewed-host>/v1/chat/completions `
  --model-id <reviewed-model> `
  --temperature 0 `
  --top-p 1 `
  --max-output-tokens-per-request 1200 `
  --response-format json_schema `
  --max-requests 7 `
  --max-input-tokens <reviewed-input-limit> `
  --max-output-tokens 8400 `
  --max-total-tokens <reviewed-total-limit> `
  --timeout-seconds 60 `
  --max-retries 2
```

Validate the prepared state offline:

```powershell
C:\Python314\python.exe scripts\check_real_execution.py `
  --generation-run-name <approved-development-run> `
  --pilot-root <external-runtime-root>
```

Invoking `run_real_execution.py` without both explicit authorization arguments fails closed.
An actual authorized invocation is intentionally outside the B1B1 infrastructure-development
task and requires a separate approval and run audit. Do not place a credential on a command
line or in an artifact.

## Phase exclusions

B1B1 has no holdout path, machine judge, human-label workflow, automatic import, freeze,
holdout release, or scientific metric. During B1B1 implementation and testing all successful
transport tests use injected local fake transports. No real provider request or model output is
created.
