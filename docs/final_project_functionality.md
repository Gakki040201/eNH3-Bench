# Final Project Functionality

eNH3-Bench can turn local documents into a human-verifiable evidence audit
packet for electrochemical ammonia synthesis literature.

## What It Can Do

- Convert local `.md`, `.txt`, `.docx`, and text-based `.pdf` files into local
  Markdown when optional local packages are installed.
- Find candidate evidence spans.
- Draft eNH3 evidence records.
- Check whether important fields are grounded in source spans.
- Generate rule-based risk feedback.
- Create an audit packet and review sheet.
- Merge human-reviewed records into gold JSONL.
- Validate gold records.
- Evaluate predictions.
- Export domain summary reports.

## What It Cannot Do

- It does not call APIs.
- It does not use OpenAI, DeepSeek, GraphRAG, LangChain, AutoGen, or web search.
- It does not train models.
- It does not provide a UI.
- It does not perform OCR.
- It does not use Docling yet.
- It does not replace human source-grounded verification.

## How It Differs From Large Agent Repositories

Large agent repositories and skill libraries help agents act. eNH3-Bench defines
what counts as trustworthy evidence for eNRR, LiNRR, NO3RR, NO2RR, and NORR
literature.

## Why CLI-Only Is Enough

For a first paper or prototype, a CLI workflow is easier to reproduce, inspect,
and test than a UI. The critical contribution is the schema, gold construction
workflow, source-grounding audit, and evaluation protocol.

## Scaling Path

- 5 papers: pilot annotation and rubric debugging.
- 50 papers: seed benchmark and baseline comparison.
- 500 papers: broader field coverage with stratified paper slots.
- 5000 papers: requires corpus management, licensing review, parallel review,
  and likely additional document-processing infrastructure.

## Human Verification Still Required

The human reviewer checks source grounding, numeric values and units, nitrogen
source, validation controls, reliability labels, and accept/reject decisions.

## Manuscript-Useful Outputs

- Gold evidence JSONL.
- Field-level evaluation reports.
- Grounding and feedback summaries.
- Domain summary tables.
- Audit packet evidence for reproducibility.
