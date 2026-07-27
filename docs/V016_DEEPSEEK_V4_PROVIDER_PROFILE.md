# v0.16 DeepSeek V4 Pro Provider Profile

Phase B1B2-A1 defines an offline-only compatibility profile for a future seven-case
DeepSeek V4 Pro scientific commissioning. It does not authorize generation. No real
DeepSeek request, real credential read, provider network call, model output, candidate
output, import, judgment, human label, or holdout release occurred in this phase.

## Canonical profile

The profile is `deepseek-v4-pro-thinking-json-v1` and fails closed unless all effective
provider settings are exactly:

| Setting | Canonical value |
| --- | --- |
| Endpoint safe identity | `https://api.deepseek.com/v1/chat/completions` |
| Model | `deepseek-v4-pro` |
| Thinking | `enabled` |
| Reasoning effort | `high` |
| Response format | `json_object` |
| Provider output ceiling | `max_tokens=4096` |
| Temperature | inactive; recorded as null and not sent |
| Top-p | inactive; recorded as null and not sent |
| Seed | unused; recorded as null and not sent |

`medium` is rejected rather than normalized to `high`. `max` is also rejected by this
high-only commissioning profile; supporting it would require a separately explicit profile.
`json_schema`, `deepseek-chat`, and `deepseek-reasoner` are not accepted by this profile.

## Exact provider payload boundary

The provider-visible top-level payload has exactly these fields:

```json
{
  "model": "deepseek-v4-pro",
  "messages": [
    {"role": "system", "content": "<existing prompt_contract_text>"},
    {"role": "user", "content": "<canonical generator-visible bounded contract>"}
  ],
  "max_tokens": 4096,
  "response_format": {"type": "json_object"},
  "thinking": {"type": "enabled"},
  "reasoning_effort": "high"
}
```

The request does not send `temperature`, `top_p`, `seed`, provider `json_schema`, `strict`,
tools, streaming controls, evaluator metadata, holdout metadata, or credentials. The two
messages retain the existing B1B0 evidence firewall: the system message is the unchanged
prompt contract, and the user message is only the canonical generator-visible bounded
contract.

Input-token estimation and hard reservation are recomputed from this actual payload. They
are never copied from a GPT plan or entered by hand.

## Scientific response authority

DeepSeek JSON Output only constrains `message.content` to JSON. The unchanged eNH3-Bench
internal response contract remains authoritative for the closed response structure, claim
and citation uniqueness, allowlists, claim/source binding, source-or-link requirements, and
scientific semantics.

Thinking responses may contain `message.reasoning_content`. It is chain-of-thought, not the
benchmark answer. Normalization uses only `message.content`; `reasoning_content` is never
serialized, imported, copied into a candidate or response object, logged, persisted, or
treated as scientific evidence.

## Execution-plan identity and phase boundary

The execution-plan schema is `0.16-real-execution-plan.3`, the provider interface is
`provider-execution-v3`, and the backend version is
`openai-compatible-chat-completions-v3`. The plan records top-level `provider_profile` and
records `thinking_mode`, `reasoning_effort`, `response_format`, `max_output_tokens`,
`temperature`, `top_p`, and `seed` under `generation_parameters`. Provider profile and all
generation parameters participate in the stable RE16 identity.

The external GPT plan `RE16_1DFFBE00A76C65D59E99` is superseded and remains an immutable
audit artifact. It must not be executed, resumed, deleted, overwritten, or mutated. This
phase does not create a replacement plan. Phase B1B2-A2 may create a fresh external DeepSeek
plan only after this compatibility patch is merged and separately authorized. B1B2-B remains
blocked.

## Future offline preparation shape

After merge and separate A2 authorization, the provider portion of the preparation command
is expected to be:

```powershell
--provider-profile deepseek-v4-pro-thinking-json-v1 `
--endpoint https://api.deepseek.com/v1/chat/completions `
--model-id deepseek-v4-pro `
--thinking-mode enabled `
--reasoning-effort high `
--response-format json_object `
--max-output-tokens-per-request 4096
```

It must omit `--temperature`, `--top-p`, and `--seed`. No such real execution plan was
created during B1B2-A1, and no real DeepSeek request has occurred yet.
