# v0.16 Phase B1B0 — Offline-Only Development Generation Pilot

## Contract

Phase B1B0 is a provider-neutral, fixture-only engineering pilot. It does not generate a scientific
answer and cannot produce an importable API-output artifact. Its independent versions are:

- generation run schema: `0.16-generation-run.1`;
- prompt: `v016-development-generation-v1`;
- profile: `development_seven_case_pilot_v1`;
- backend interface: `generation-backend-v1`; and
- cost estimate schema: `0.16-generation-cost.1`.

Audit schema `0.13`, Phase B1A, source span identities, the v0.15 clean-room package, Gold, and their
default behavior remain unchanged.

The only enabled backend is `fixture`. It creates request envelopes and dry-run receipts with
`network_call_performed=false`, `model_output_generated=false`, and
`importable_api_output=false`. Other backend names fail with `real_api_backend_not_enabled`.

## Seven-case selection

The pilot selects exactly one development paper for each of the seven E2E question types. An
evaluator-side deterministic optimizer requires at least two `answerable`, two `partially_answerable`,
and two `insufficient_evidence` cases, maximizes risk-tier and signal-stratum diversity, and resolves
ties with SHA-256.

Evaluator metadata and selection reasons are retained in
`pilot/pilot_selection_manifest.json`. The generator-visible
`pilot/development_pilot_batch.jsonl` contains only its exact twelve-field bounded-input allowlist. It
never contains execution state, backend identity, timestamps, split, answerability, risk,
expected-abstention, or routing metadata. Compiled model-visible prompt content has the same execution
and evaluator metadata firewall. Every case remains single-paper and every cited identity remains
case-allowlisted.

## External runtime

Production artifacts are written beneath the external root supplied by `--pilot-root`; its CLI default
is `F:\eNH3_Bench_API\v016_b1b0`. The core module has no drive-specific output path. Runtime data,
full-text documents, and generated reports are not committed to the repository.

The formal offline run is:

```powershell
C:\Python314\python.exe scripts\build_development_pilot.py `
  --pilot-root F:\eNH3_Bench_API\v016_b1b0 `
  --selective-eval-run-name enrr_selective_eval_v016_round1_20260720 `
  --generation-run-name enrr_generation_pilot_v016_b1b0_20260722

C:\Python314\python.exe scripts\prepare_generation_prompts.py `
  --pilot-root F:\eNH3_Bench_API\v016_b1b0 `
  --generation-run-name enrr_generation_pilot_v016_b1b0_20260722

C:\Python314\python.exe scripts\run_generation_dry_run.py `
  --pilot-root F:\eNH3_Bench_API\v016_b1b0 `
  --generation-run-name enrr_generation_pilot_v016_b1b0_20260722 `
  --backend fixture

C:\Python314\python.exe scripts\estimate_generation_cost.py `
  --pilot-root F:\eNH3_Bench_API\v016_b1b0 `
  --generation-run-name enrr_generation_pilot_v016_b1b0_20260722

C:\Python314\python.exe scripts\check_generation_pilot.py `
  --pilot-root F:\eNH3_Bench_API\v016_b1b0 `
  --generation-run-name enrr_generation_pilot_v016_b1b0_20260722
```

Prompt compilation writes seven schema-bound instances. The fixture dry run writes seven request
envelopes and seven receipts, but no answer text, claims, citations, answer status, provider response,
usage record, failure output, or `outputs/api_outputs.jsonl`.

## Offline token and cost estimate

The estimator uses local prompt characters to produce conservative token bounds. With no explicit
price arguments, the cost template has `estimate_status=token_only` and null price/cost fields. Optional
prices must be passed directly on the command line together with nonblank currency and pricing source
and a valid ISO date. The estimator does not retrieve prices.

## Validation and reproducibility

The validator proves the seven-case/type/paper counts, answerability diversity, development-only
boundary, prompt and request hashes, receipt nonimportability, artifact absence, metadata firewall,
source immutability, blank Phase B1A source state, and zero serialized secrets or absolute paths.

Reproducibility compares normalized hashes for selection, generator batch, compiled prompts, request
envelopes, and token estimate. Only run name, creation time, and an external-root field may be
normalized; source identities, case IDs, paper IDs, selection reasons, and all prompt/request hashes
remain binding.

Provider execution, machine judgment, human labeling, development-output import, freeze, holdout
release, scientific metrics, and Gold promotion belong to later separately authorized phases.
