# M017 D2 Seven-Case Batch Demo

## Scope and safety boundary

M017 D2 extends the accepted D1 local Demo; it is not M016 benchmark execution. It does
not create or update an RE16, mutate M016 external runtimes, run machine judgment, create
human labels, access holdout material, or import results into the benchmark. Demo results
are never automatically imported or accepted.

The browser submits only `{"mode":"fixture"}` or `{"mode":"live"}`. The server derives
exactly these seven frozen development cases in canonical order:

1. `EC16_CEEE6E048F7B34D28600`
2. `EC16_019B2E986566533635D0`
3. `EC16_F1CE2281BF67967C6F5F`
4. `EC16_EB62B436C9FD7F8D1242`
5. `EC16_47CBB413B6F7B9E4FE62`
6. `EC16_7263EBEC21D9DF523A7D`
7. `EC16_83242FA9E17F52D12567`

Arbitrary, reordered, missing, duplicate, or additional case lists are not accepted.

## D1 single-case workflow

D1 remains available unchanged: select one case, choose Fixture or a preflight-enabled Live
mode, submit, poll the DR17 record, and render its structured, tolerant, unstructured, or
failed result. Fixture needs no credential and makes no provider request. A Live single run
has one request attempt and no automatic retry.

## D2 batch workflow

The **七案例批量运行** panel runs all seven cases sequentially. Batch submission creates a
queued DB17 record and queues one coordinator on the same
`ThreadPoolExecutor(max_workers=1)` used by single-case execution. The coordinator creates
a normal DR17 child record for each case and invokes the existing child execution path
synchronously. It never recursively submits a child to the one-worker queue.

After each child reaches a terminal state, the DB17 record is atomically updated. An
individual provider, parsing, timeout, or credential failure is recorded on that child and
does not stop later cases. Automatic retries are disabled. A Live batch therefore makes at
most seven POST attempts—one per case. Manually rerunning a Live batch creates a new batch
and may create up to seven new provider requests.

## Response boundaries and failure diagnostics

A structured child response must be a complete top-level object with a non-empty string
`answer_text` or `summary`, `claims` as a list, and `citations` as a list. Additional fields
are allowed. Nested claim or citation JSON fragments do not qualify. For a non-truncated
child, readable provider text is preserved as `unstructured_text` with
`DEMO_JSON_FRAGMENT_NOT_TOP_LEVEL_RESPONSE`; the Demo never fabricates claims or citations.

`finish_reason=length` always produces a failed child with
`provider_output_truncated` and `DEMO_PROVIDER_OUTPUT_TRUNCATED_LENGTH`. Readable partial
content remains in its DR17 record and new batch reports show a prominent **Partial provider
output preserved / Not a complete scientific answer** warning. The batch table shows the
child as `failed`, its error column shows `provider_output_truncated`, later cases continue,
and the terminal batch is `completed_with_failures` after all seven attempts.

`provider_empty_content` remains a failed child and may include
`DEMO_FINAL_CONTENT_EMPTY`. Safe HTTP status, reported model, response ID, finish reason,
usage, and latency remain visible when supplied. Missing values are displayed as
`N/A · not supplied by provider`. Any `reasoning_content` is discarded: it is never shown,
persisted, or repurposed as an answer. Neither truncation nor empty final content triggers an
automatic retry.

The browser shows exact per-case states and an exact `n / 7 completed` counter; it does not
show a fabricated percentage. Completed child rows provide **打开案例结果**, which reuses
the D1 single-result renderer. Batch-history rows reopen the saved summary and progress
table.

## Fixture batch

Fixture batch execution is offline, needs no preflight or confirmation, reads no credential,
and performs no provider request. Its aggregate token totals are zero and the UI/report say
**No provider request occurred** and **Fixture — not model-generated scientific output**.

## Live batch

Live remains disabled by default. Start the server explicitly in Live mode, run the existing
model preflight, and wait for a successful result that confirms `deepseek-v4-pro` is visible.
Preflight state is browser-session state and resets on refresh; it never starts a batch.

Immediately before Live submission, one browser confirmation states the model, per-case
`max_tokens`, per-case timeout, seven-attempt maximum, zero-retry policy, failure
continuation, and potential USTC project-token consumption. Cancelling creates no DB17 or
DR17 record and sends no provider request.

The server must remain running throughout execution. Do not refresh the browser during an
active Live batch. There is no in-flight cancellation endpoint.

## Lifecycle and aggregation

Batch schema `0.17-demo-batch.1` supports:

- `queued`: persisted and waiting for the shared worker;
- `running`: the coordinator is attempting the canonical sequence;
- `completed`: all seven child runs succeeded;
- `completed_with_failures`: all seven were attempted and at least one failed;
- `failed`: an internal coordinator failure prevented completion of the sequence.

`latency_seconds` is batch wall-clock elapsed time.
`aggregate_child_latency_seconds` is the sum of terminal child latencies; it is a distinct
metric. Prompt, completion, and total token counts are summed independently from safe child
usage. Missing usage contributes zero to aggregates and remains `null` on that item; it is
never fabricated.

## External storage and reports

All generated artifacts remain outside Git under the configured Demo root:

```text
<demo-root>\runs\DR17_<20 uppercase hex>.json
<demo-root>\batches\DB17_<20 uppercase hex>.json
<demo-root>\reports\DB17_<20 uppercase hex>.html
```

Child answers remain only in DR17 records. The DB17 JSON contains safe summaries rather
than complete prompts or evidence. Batch and child records exclude credentials,
Authorization/request headers, reasoning content, complete compiled prompts, absolute
repository paths, usernames, benchmark judgments, and Gold labels.

The terminal HTML report is self-contained: no CDN, remote font, external JavaScript,
analytics, or network dependency. It includes aggregate metrics and escaped per-case
questions, answers, warnings, safe provider metadata, claims, and citations. Use **打开批次报告**
or `GET /api/batches/{batch_id}/report` after it is ready.

Existing `0.17-demo-run.1` DR17 and `0.17-demo-batch.1` DB17 records remain readable and
are not migrated or rewritten. D2A adds no serialized field, so newly generated records
retain those schema versions. Only newly generated reports use the improved warnings.

## HTTP API

| Route | Purpose |
| --- | --- |
| `POST /api/batches` | Queue the canonical Fixture or Live batch; HTTP 202 |
| `GET /api/batches/{batch_id}` | Complete sanitized DB17 record |
| `GET /api/batches?limit=20` | Newest-first safe batch summaries |
| `GET /api/batches/{batch_id}/report` | Terminal self-contained HTML report |

The report route returns HTTP 409 with `batch_report_not_ready` until the report is ready.
Malformed IDs and path traversal are rejected; there is no arbitrary filesystem route.

## Start and stop

Use the same launcher documented in [V017_DEMO.md](V017_DEMO.md). Fixture is the safe
default. Press `Ctrl+C` in the server terminal to stop it; the HTTP server and one-worker
executor shut down cleanly.

For a later targeted manual rerun with a larger per-case output limit, use the explicit Live
flow and confirmation:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\start_demo_v017.ps1 `
  -Live `
  -MaxOutputTokens 8192 `
  -TimeoutSeconds 900
```

`MaxOutputTokens` must be a positive integer and `TimeoutSeconds` a positive finite number;
their defaults remain `4096` and `900`. This command is documented for later manual use and
does not imply a retry or resume mechanism.
