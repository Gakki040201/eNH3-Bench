# v0.16 USTC LLM Gateway DeepSeek V4 Pro Profile

Phase B1B2-A1 defines an offline-only compatibility profile for a future seven-case
scientific commissioning. The provider-facing boundary is the University of Science and
Technology of China Large Model Public Service Platform, not the DeepSeek public API.

No real API request, USTC gateway call, credential read, model output, candidate output,
import, judgment, human label, or holdout release occurred in this phase.

## Gateway and requested model identity

The fail-closed provider profile is `ustc-llm-deepseek-v4-pro-v1`.

| Identity | Canonical value |
| --- | --- |
| Gateway provider | USTC Large Model Public Service Platform |
| Gateway endpoint | `https://api.llm.ustc.edu.cn/v1/chat/completions` |
| Requested underlying model | `deepseek-v4-pro` |
| Authorization scope | `REAL_API_DEVELOPMENT_V016_B1B2_7CASE` |

`ENH3BENCH_API_KEY` contains a USTC platform project API key. It is not described or
treated as a DeepSeek official API key. The USTC key may authorize multiple models; the
request payload's exact `model` field selects the requested model.

Scientific attribution requires one explicit model ID. The profile therefore rejects
`smart/default`, `smart/reasoning`, `deepseek-v4-flash-ascend`, `deepseek-chat`,
`deepseek-reasoner`, and every other model ID. No smart-routing alias is translated to
`deepseek-v4-pro`. A successful response must also report exactly `deepseek-v4-pro` in its
`model` field.

## Minimal verified provider payload

The USTC profile sends exactly three top-level fields. This A1 example uses the non-canonical
reference fixture value `4096`:

```json
{
  "model": "deepseek-v4-pro",
  "messages": [
    {"role": "system", "content": "<existing prompt_contract_text>"},
    {"role": "user", "content": "<canonical generator-visible bounded contract>"}
  ],
  "max_tokens": 4096
}
```

The two messages retain the unchanged B1B0 evidence firewall. The system content is the
frozen prompt contract; the user content is only the canonical generator-visible bounded
contract.

This patch does not send or claim USTC support for direct-DeepSeek-specific `thinking` or
`reasoning_effort` parameters. It also does not send provider `response_format`,
`temperature`, `top_p`, `seed`, `json_schema`, `strict`, tools, streaming controls,
evaluator metadata, holdout metadata, or credentials. USTC forwarding or honoring any of
those parameters remains unverified and must not be inferred from DeepSeek public-cloud
behavior.

Input-token estimation, hard reservation, and `provider_request_sha256` are computed from
the exact three-field payload. They are not copied from a GPT or direct-DeepSeek plan.

## Scientific output authority

The unchanged eNH3-Bench prompt contract and internal validator remain authoritative.
Provider-side structured-output enforcement is not assumed. `message.content` must parse as
one JSON object and pass the frozen response schema, claim/citation uniqueness, allowlists,
claim/source binding, source-or-link requirements, and scientific semantic checks.
Malformed or non-JSON output fails closed.

Normalization still requires HTTP 2xx, a JSON response body, exactly one choice, string
`message.content`, valid usage arithmetic, a nonblank provider response ID,
`finish_reason=stop`, and response model identity equal to the explicitly requested
`deepseek-v4-pro`. Any additional gateway response field such as `reasoning_content` is not
benchmark output and is never serialized or persisted.

## Temporary max_tokens and A2 boundary

The A1 compatibility tests may use `max_tokens=4096` as a deterministic reference fixture.
`4096` is not canonical and is not enforced by the provider profile. The profile requires
only a positive integer; A1 does not select the final execution ceiling and makes no claim
about a USTC maximum output-token limit.

Phase B1B2-A2 must independently check the USTC model-service contract and gateway behavior,
verify the key-visible model list, and freeze exactly one per-request `max_tokens` value in a
fresh external execution plan. That selected value is recorded in
`generation_parameters.max_output_tokens`, used verbatim by the provider payload, included in
the output and total token reservations, and bound into the RE16 identity.

## Execution identity and superseded artifact

The execution-plan schema is `0.16-real-execution-plan.3`, the provider interface is
`provider-execution-v3`, and the backend version is
`openai-compatible-chat-completions-v3`. RE16 binds the USTC provider profile, exact gateway
endpoint hash, explicit requested model, B1B2 authorization scope, request set, budgets,
and all recorded effective or explicitly absent generation parameters.

The external GPT plan `RE16_1DFFBE00A76C65D59E99` remains superseded and immutable. It
must not be executed, resumed, deleted, overwritten, or mutated. A2 must create a fresh USTC
gateway plan only after this patch is merged and separately authorized. B1B2-B remains
blocked.

## Future offline preparation shape

After merge and separate A2 authorization, the provider portion of the offline preparation
command is expected to use:

```powershell
--provider-profile ustc-llm-deepseek-v4-pro-v1 `
--endpoint https://api.llm.ustc.edu.cn/v1/chat/completions `
--model-id deepseek-v4-pro `
--max-output-tokens-per-request <A2-verified-value>
```

It must not use `smart/default` or `smart/reasoning`. Until separately verified, it must
also omit `--thinking-mode`, `--reasoning-effort`, `--response-format`, `--temperature`,
`--top-p`, and `--seed`. No execution plan or real request is created by B1B2-A1.
