# eNH3-ExtractBench Final Design

eNH3-ExtractBench is the field-level extraction and method-comparison layer on
top of eNH3-Bench.

Top-level design:

```text
eNH3-ExtractBench =
  Docling conversion
  + optional LLM/Codex-assisted discovery prompts
  + ChatExtract-style prompt chain
  + NERRE-style JSON extraction
  + ToolBench-style evaluation
```

The current implementation runs offline with rule fallbacks. LLM or API use is
future optional work and must be explicitly enabled by the user.

## Pipeline

```text
local documents
-> Docling-first Markdown conversion
-> optional Codex-assisted candidate discovery prompt
-> eNH3 candidate span discovery
-> eNH3-ChatExtract or eNH3-NERRE-style extraction
-> field grounding and rule feedback
-> human audit packet
-> reviewed gold JSONL
-> ToolBench-style method comparison
```

## Localized Framework Ideas

- ToolBench-style comparison: compare extraction methods on the same gold
  eNH3 fields.
- Parse-filter-extract-postprocess: convert documents, filter candidate
  paragraphs, extract records, and postprocess reliability risks.
- ChatExtract-style prompt chain: relevance, extraction, verification, and
  reliability prompts.
- NERRE-style JSON extraction: structured JSON records validated against an
  eNH3-specific schema.

## What It Does Not Do

- It does not call APIs by default.
- It does not vendor external repositories.
- It does not require PostgreSQL.
- It does not train models.
- It does not provide a UI.
- It does not make machine drafts into gold without human review.

## First Usable Outputs

- `data/extraction_runs/{run_name}/enh3_chatextract_rule.jsonl`
- `data/extraction_runs/{run_name}/enh3_nerre_rule.jsonl`
- `data/extraction_runs/{run_name}/comparison_report.md`

These generated outputs are ignored by default and should be regenerated from
local inputs when needed.
