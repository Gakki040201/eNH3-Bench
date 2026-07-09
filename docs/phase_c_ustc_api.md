# Phase C: Optional USTC/OpenAI-Compatible LLM Verification

Phase C adds an optional LLM verification layer for eNH3-BoundaryLedger. It uses an OpenAI-compatible chat completions API, including USTC-compatible endpoints such as `https://api.llm.ustc.edu.cn`.

## Goal

The verifier asks whether a source span explicitly supports the rule-based BoundaryLedger output: text class, extracted fields, validation gates, maximum supported boundary, missing fields, hidden taxes, required controls, overclaim risk, and recommended experiments.

It does not replace BoundaryLedger rules. It does not create gold labels. It produces audit signals, disagreement rows, and model-comparison reports for human review.

## Relation to other systems

- OpenScholar and PaperQA2 retrieve and synthesize evidence. Phase C assumes BoundaryLedger already has source spans and asks a verification question.
- ChatExtract motivates follow-up verification. Phase C is closest to this pattern, but constrained to eNH3 claim rights and source text.
- Dagdelen-style extraction motivates structured JSON output. Phase C uses strict JSON but does not turn LLM output into extracted truth.

## Environment configuration

The client reads:

- `LLM_API_KEY` or `USTC_API_KEY`
- `LLM_BASE_URL` or `USTC_BASE_URL`
- `LLM_MODEL` or `USTC_MODEL`

PowerShell example:

```powershell
$env:USTC_API_KEY="..."
$env:USTC_BASE_URL="https://api.llm.ustc.edu.cn"
$env:USTC_MODEL="..."
```

The base URL is normalized internally:

- `https://api.llm.ustc.edu.cn`
- `https://api.llm.ustc.edu.cn/v1`
- `https://api.llm.ustc.edu.cn/v1/chat/completions`

all resolve to the chat completions endpoint.

## Commands

Mock smoke test with no network:

```powershell
C:\Python314\python.exe scripts\verify_with_llm.py --run-name final_pilot --model mock --max-records 10 --mock
```

Real API verification:

```powershell
C:\Python314\python.exe scripts\verify_with_llm.py --run-name final_pilot --max-records 10
```

Model comparison:

```powershell
C:\Python314\python.exe scripts\compare_llm_models.py --run-name final_pilot --models mock --max-records 10 --mock
```

## Output files

- `data/llm_verification/{run_name}/{model}/llm_verified_claims.jsonl`
- `data/llm_verification/{run_name}/{model}/llm_verified_claims.csv`
- `data/llm_verification/{run_name}/{model}/llm_failures.jsonl`
- `data/model_runs/{run_name}/llm_model_comparison_table.csv`
- `data/reports/llm_model_comparison_report.{run_name}.md`

## Safety notes

- Do not commit `.env` or API keys.
- Do not upload full copyrighted PDFs or raw full documents to the API.
- Use source spans only.
- LLM output is an audit signal, not gold.
- Human review is required before any label becomes gold evidence.

## Phase D handoff

LLM verification outputs should be exported into Phase D human audit sheets before they are used for any calibration or gold-label workflow:

```powershell
C:\Python314\python.exe scripts\export_human_audit_sheet.py --run-name final_pilot --llm-model deepseek-v4-pro --top-n 50 --priority-only
C:\Python314\python.exe scripts\export_review_instructions.py --run-name final_pilot
```

The LLM fields remain separate from the rule fields in the audit sheet. They become comparison columns for human review, not replacements for BoundaryLedger rule outputs.
