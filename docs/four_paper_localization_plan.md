# Four-Paper Localization Plan

eNH3-ExtractBench localizes high-level workflow ideas from four materials
literature extraction frameworks. It does not claim those methods as original,
does not copy paper text, figures, results, or source code, and does not vendor
external repositories.

## Ning et al., Digital Discovery 2026

- Original task: compare extraction tools for materials literature fields such
  as bandgap values.
- Original workflow: run multiple extraction systems, compare field-level
  outputs against gold annotations, and analyze method limitations.
- Concept copied: ToolBench-style method comparison and field-level evaluation.
- Not copied: source code, benchmark data, paper text, figures, results, or
  bandgap-specific implementation.
- eNH3-localized task: compare rule baseline, eNH3-ChatExtract scaffold,
  eNH3-NERRE-style scaffold, future optional LLM methods, and human gold for
  FE, EE, NH3 yield, validation controls, reliability labels, and grounding.
- Local implementation file: `enh3bench/toolbench_evaluator.py`.
- License/reuse notes: conceptual reference only; copied_code=no in
  `docs/code_reuse_log.md`.

## Gupta et al., Communications Materials 2024

- Original task: extract structured data from polymer literature.
- Original workflow: parse a corpus, filter relevant text, extract entities or
  fields with NER/LLM components, postprocess, and store records in a database.
- Concept copied: parse-filter-extract-postprocess workflow structure.
- Not copied: code, data, database schema, PostgreSQL requirement, model calls,
  paper text, figures, or results.
- eNH3-localized task: Docling-first Markdown conversion, eNH3 paragraph
  filtering, offline rule or future model extraction, reliability postprocess,
  and JSONL/CSV evidence storage.
- Local implementation file: `enh3bench/extraction_runs.py` plus existing
  conversion, span-finding, draft extraction, and audit modules.
- License/reuse notes: conceptual reference only; copied_code=no.

## Polak & Morgan, Nature Communications 2024

- Original task: ChatExtract extracts structured scientific data through a
  relevance prompt, extraction prompt, and follow-up verification prompts.
- Original workflow: prompt chain for relevance, extraction, verification, and
  iterative checking.
- Concept copied: prompt-chain decomposition.
- Not copied: prompt text, source code, paper results, figures, or external
  runtime.
- eNH3-localized task: relevance prompt, extraction prompt, field-grounding
  prompt, and reliability prompt for eNH3 evidence fields.
- Local implementation file: `enh3bench/chatextract_chain.py`.
- License/reuse notes: conceptual reference only; copied_code=no.

## Dagdelen et al., Nature Communications 2024

- Original task: structured information extraction from scientific text using
  JSON-style relation extraction.
- Original workflow: define a structured schema, ask for JSON records from
  scientific text, and score extracted records.
- Concept copied: JSON-schema extraction and schema validation framing.
- Not copied: source code, trained models, datasets, paper text, figures, or
  results.
- eNH3-localized task: eNH3-NERRE-style JSON prompt, JSON parser, schema
  validator, and offline rule fallback.
- Local implementation file: `enh3bench/nerre_style_extractor.py`.
- License/reuse notes: conceptual reference only; copied_code=no.

## Guardrail

All localized workflows remain no-API by default. Machine outputs are not gold
labels until a human verifies source-grounded correctness.
