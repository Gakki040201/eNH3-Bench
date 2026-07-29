# v0.16 Controlled Provider Execution (Phase B1B1/B1B2)

Phase B1B1 is execution infrastructure, not scientific evaluation. It adds a small,
profile-explicit execution boundary around the seven-case B1B0 development pilot. It does
not authorize a model run, import an API output, judge an answer, collect a human label,
freeze an evaluation package, or release holdout material.

## Default state

The default is offline and fail closed. Preparation and validation do not read a credential
and do not open a network connection. The run entry point refuses execution unless all of
the following are present and valid:

1. the explicit `--execute-real-api` flag;
2. one exact versioned authorization scope from the fail-closed allowlist;
3. a previously prepared and internally consistent execution plan;
4. an explicitly configured OpenAI-compatible HTTPS chat-completions endpoint;
5. an explicitly configured model and generation parameters;
6. the approved seven-case B1B0 development selection, with zero holdout cases;
7. hard logical-request, network-attempt, token-reservation, timeout, and retry limits;
8. an atomically acquired exclusive execution lock;
9. a credential available only after all preceding gates pass.

The allowlist contains exactly the original commissioning scope
`REAL_API_DEVELOPMENT_V016_B1B2_7CASE` and the timeout-recovery scope
`REAL_API_RECOVERY_V016_B1B2_7CASE_TIMEOUT900`. Matching is case-sensitive equality:
there are no aliases, prefixes, substring matches, or fallbacks.

There is no implicit provider, default external model, environment-driven automatic
execution, real-provider fallback, `--force` switch, or `--include-holdout` option.

## Provider boundary

`enh3bench.provider_execution.ProviderExecutionBackend` separates three operations:

- construction of a provider request from an existing B1B0 compiled prompt;
- one auditable transport attempt (`execute_once`);
- normalization of the provider response.

B1B1 implements one backend: a minimal Python standard-library HTTPS transport for the
OpenAI-compatible `/v1/chat/completions` endpoint. The generic profile is
`generic-openai-compatible-v1`; the separately fail-closed USTC gateway commissioning profile is
documented in `V016_USTC_LLM_DEEPSEEK_V4_PROFILE.md`. No provider SDK, agent framework, or
vendor-specific orchestration dependency is used. The provider payload is constructed only
from the compiled B1B0 prompt instance; the executor does not reread a paper or regenerate a
prompt.

The provider request retains the B1B0 `prompt_instance_id`, `compiled_prompt_sha256`,
`request_envelope_id`, and `request_sha256`. Transport headers are created in memory only and
are never added to the benchmark envelope or a serialized artifact.

## Authorization and credential lifecycle

Authorization has two stages. Before the plan is read, the runner requires both
`execute_real_api=true` and one exact allowlisted supplied scope. After the plan is safely
loaded and validated, the runner requires exact equality between the supplied scope and the
plan's serialized `authorization_scope`. A commissioning authorization cannot run a recovery
plan, and a recovery authorization cannot run a commissioning plan. Unknown values and plan
mismatches fail before credential access, backend construction, provider transport, or
journal-attempt mutation; the supplied value is never replaced with a plan value.

The credential environment variable is `ENH3BENCH_API_KEY`. Its value is read only inside
the authorized execution function, after authorization, plan identity, endpoint identity,
development-only selection, request binding, budget validation, backend validation, and the
locked runtime-state recheck have passed.

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

Its schema is `0.16-real-execution-plan.3`. The stable `RE16_...` identity binds the B1B0
generation and selection identities, backend name and version, model, safe endpoint hash,
provider profile, approved request set, logical-request and network-attempt caps, hard token-reservation
method and bounds, timeout, retry policy, authorization scope, and every recorded generation
parameter. It deliberately excludes creation time, absolute paths, runtime root, and
credentials.

Adding the second exact authorization value does not change the serialized shape. Existing
schema `.3` commissioning plans remain valid, and the selected authorization scope continues
to participate in the stable RE16 identity. Offline preparation accepts an explicit
`--authorization-scope`; its backward-compatible default is the original commissioning
scope.

Every configured provider parameter is recorded: model, provider profile, thinking mode,
temperature, top-p, maximum output tokens per request, optional seed, response format, and
optional reasoning effort. Inactive or unverified USTC parameters are recorded as null and
omitted from the actual provider payload. Unsupported parameters are not invented. The provider interface is
`provider-execution-v3`; the backend version is
`openai-compatible-chat-completions-v3`.

For the USTC profile, A1's `4096` value is only an offline reference fixture and is not a
provider-profile constant or a claimed gateway limit. A2 must freeze exactly one reviewed
positive `max_tokens` value; the payload, token reservations, and RE16 identity bind that
selected value.

## Hard budgets, timeout, and retry

Preparation requires explicit hard limits for:

- logical scientific requests (`max_requests`, never more than seven);
- actual provider HTTP attempts including retries (`max_network_attempts`);
- reserved input tokens;
- output tokens;
- total tokens;
- per-request timeout;
- retries (never more than two).

`max_requests` is not an HTTP-attempt count. The attempt cap must be at least the logical
request count and no greater than `max_requests * (1 + max_retries)`. The execution layer,
not the backend, checks and consumes this global cap immediately before each transport call.
Therefore `network_call_count <= max_network_attempts` even when several cases retry.

An optional estimated-cost limit requires an explicit pinned pricing contract. B1B1 does not
retrieve or pin provider pricing, so its current plans leave the cost limit null. Token and
request limits remain mandatory. The historical `ceil(payload_bytes / 4)` value remains an
informational `estimated_input_tokens` only. Hard preflight instead uses the provider-neutral
`utf8_payload_byte_upper_bound_v1` reservation: every UTF-8 provider-payload byte reserves one
input token. The plan records per-request and total input reservations plus output and total
reservations. Each retry consumes a fresh reservation. Insufficient input, output, total, or
network-attempt budget fails before the transport is called; reported provider usage is then
checked again after the response.

Retries are bounded and apply only to HTTP 408, 429, 500, 502, 503, and 504, or an explicitly
classified timeout/connection-reset failure. HTTP 400, 401, 403, 404, authorization failures,
schema failures, and other permanent failures are not retried. Backoff is finite; tests inject
a no-sleep function.

The recovery scope is narrower than the general budget rules. It requires the exact USTC
profile and endpoint identity, model `deepseek-v4-pro`, seven development requests, zero
holdout requests, `max_requests=7`, `max_network_attempts=7`, `max_retries=0`, a 900-second
client timeout, and `generation_parameters.max_output_tokens=8192`. Temperature, top-p,
seed, response format, reasoning effort, and thinking mode must all remain null. The provider
payload remains exactly `model`, `messages`, and `max_tokens`. The 900-second timeout is only
a client waiting ceiling, not a USTC service guarantee.

That recovery scope is also bound to generation run
`GR16_C9D719692BE1DE6DBF2A`, pilot selection `PS16_AB353BA2BE4E7CC83737`,
and the exact canonical ordered `approved_case_ids` listed in
`V016_USTC_TIMEOUT_RECOVERY.md`. Exact list equality is required: another seven-case package
or a reordering of the approved cases is not authorized. These identity restrictions apply
only to the recovery scope; the original commissioning scope and existing schema `.3`
commissioning plans remain unchanged.

## Exclusive execution lock

The runner atomically creates the external-runtime lock with OS-level exclusive creation:

```text
execution/real_execution.lock
```

The lock is acquired before authorization for every prepared runtime and retained across
runtime reload, plan and development-contract validation, budget and backend validation,
runtime-state recheck, the single credential read, all provider attempts, journal mutation,
artifact materialization, and final strict self-validation. A concurrent or later runner that
finds the lock fails immediately with `real_execution_lock_held`, before credential access or
provider transport. It does not wait or retry.

Normal Python exception paths release the lock in `finally`. `KeyboardInterrupt` and
`SystemExit` also release it, but they do not convert an `attempt_started` journal record into
a terminal state. A hard process crash can leave the lock in place. Any pre-existing or
orphaned lock requires manual review: the runner never removes one based on PID, modification
time, or age.

## Durable journal, resume safety, and final validation

The external runtime contains an atomic write-ahead authority:

```text
execution/real_execution_journal.json
```

Its schema is `0.16-real-execution-journal.1`. Before every billable attempt, the runner
atomically records `attempt_started` with the plan, request, prompt, case, per-request attempt,
and global network-attempt identities. After transport it atomically records
`terminal_success` or `terminal_failure`, including enough safe terminal data to validate and
materialize the raw, receipt, and candidate layers.

If a process dies after `attempt_started` and before its terminal record, that attempt is
`INDETERMINATE`: manual review is required and automatic resend is forbidden. Resume classifies
runtime state as `PREPARED`, `COMPLETED`, `FAILED`, `INDETERMINATE`, `PARTIAL`, or `CORRUPT`.
Only `COMPLETED` is accepted offline, with zero credential reads and zero network calls.
Failed, indeterminate, partial, and corrupt states all fail closed before credential access.
`require_completed=True` requires exactly seven successful receipts, seven safe raw responses,
seven valid nonimported candidates, and no failed or indeterminate attempt.

After writing journal state `completed`, the runner does not construct or return PASS directly.
While it still owns the execution lock, it calls the strict offline validator with
`require_completed=True`. It returns only when the validator reports both `result=PASS` and
`stage=COMPLETED`; otherwise it raises `completed_execution_self_validation_failed`. This
self-validation performs no additional credential read or provider call.

## Response and artifact boundaries

Transport success is not benchmark success. B1B1 separately checks:

1. transport and HTTP success;
2. a nonblank string provider response ID;
3. an exact `finish_reason` of `stop`;
4. expected provider model identity and usage fields;
5. a single response content string;
6. a single JSON object with no Markdown fence;
7. the exact closed B1B0 response, claim, and citation schemas;
8. source-span, evidence-link, and claim-reference allowlists.

Missing or blank response IDs fail with `provider_response_id_missing`. Any incomplete or
unknown finish reason—including `length`, `content_filter`, `tool_calls`, or an empty value—
fails with `provider_finish_reason_not_complete`, even when the returned content is parseable
JSON. The strict offline validator independently enforces both conditions for every successful
raw response and retains the journal, receipt, raw-response, and candidate bindings.

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
  --authorization-scope REAL_API_DEVELOPMENT_V016_B1B2_7CASE `
  --endpoint https://<reviewed-host>/v1/chat/completions `
  --model-id <reviewed-model> `
  --temperature 0 `
  --top-p 1 `
  --max-output-tokens-per-request 1200 `
  --response-format json_schema `
  --max-requests 7 `
  --max-network-attempts 7 `
  --max-input-tokens <reviewed-input-limit> `
  --max-output-tokens 8400 `
  --max-total-tokens <reviewed-total-limit> `
  --timeout-seconds 60 `
  --max-retries 2
```

Any future timeout-recovery preparation must instead explicitly pass
`--authorization-scope REAL_API_RECOVERY_V016_B1B2_7CASE_TIMEOUT900` together with the exact
recovery contract documented in `V016_USTC_TIMEOUT_RECOVERY.md`. That future operation
requires separate authorization and must create a new external runtime and new RE16; the
preserved failed plan must never be resumed.

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
