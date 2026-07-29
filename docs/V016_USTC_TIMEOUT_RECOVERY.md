# v0.16 USTC Timeout-Recovery Authorization Boundary

## Preserved incident

The original failed execution plan is `RE16_E4174709F5F9EAAE50F1`. It is classified exactly
as `client_observed_timeout_after_request_dispatch`: the client dispatched one request and
observed its 180-second waiting ceiling without receiving an HTTP response locally.
Provider-side completion is unknown. This boundary does not claim that the server did or did
not complete the request, and provider-side token consumption cannot be determined from the
local artifacts alone.

The original runtime is immutable and must never be resumed. Its timeout artifact is retained
for audit and is not included as a successful benchmark output.

Preserved incident identities:

- ZIP SHA-256: `d169b1abb66b14d4743726fa0d20ad871f707c3bf1bc506f84f9458b20671c8c`
- sanitized manifest SHA-256: `43f9edeca432917b20a750a1eeef3eccca674f00374ff6b461753436eebb169a`

## Recovery authorization

Recovery requires all three of the following:

1. a new external runtime;
2. a new RE16 execution plan;
3. the exact authorization scope
   `REAL_API_RECOVERY_V016_B1B2_7CASE_TIMEOUT900`.

The original commissioning scope `REAL_API_DEVELOPMENT_V016_B1B2_7CASE` remains unchanged and
continues to identify commissioning plans, including the preserved failed plan. Neither scope
can authorize a plan carrying the other scope.

The recovery scope accepts only this contract:

| Field | Exact value |
| --- | --- |
| provider profile | `ustc-llm-deepseek-v4-pro-v1` |
| model | `deepseek-v4-pro` |
| endpoint | `https://api.llm.ustc.edu.cn/v1/chat/completions` |
| requests / development / holdout | `7 / 7 / 0` |
| maximum logical requests | `7` |
| maximum network attempts | `7` |
| retries | `0` |
| client timeout | `900 seconds` |
| `max_tokens` | `8192` |
| temperature / top-p / seed | `null / null / null` |
| response format / reasoning effort / thinking mode | `null / null / null` |

The same seven development cases remain selected. The provider payload remains exactly
`model`, `messages`, and `max_tokens`; no provider parameter is added. The 900-second value is
a client waiting ceiling, not a USTC service guarantee.

Preparation is offline and must pass the recovery scope explicitly:

```powershell
--authorization-scope REAL_API_RECOVERY_V016_B1B2_7CASE_TIMEOUT900
```

Creating or executing that future plan requires a separate explicit authorization. This BR1
patch creates neither a recovery runtime nor a recovery RE16 and sends no provider request.

## Credential boundary

The key must never be stored in source code, execution plans, manifests, journals, receipts,
raw-response records, candidate outputs, or logs. Unknown authorization values and plan-scope
mismatches fail before credential access, provider transport, or journal-attempt mutation.
