# eNH3-BoundaryLedger Concept

eNH3-BoundaryLedger is a source-grounded claim-rights and boundary-admissibility engine for electrochemical ammonia synthesis. It keeps the existing eNH3-TriageBench CLI workflow, but adds a scientific method layer that asks what a claim is allowed to support.

The layer is not generic RAG. Retrieval and synthesis systems can help gather evidence, but BoundaryLedger adjudicates the admissible boundary of each claim after eNH3-specific validation gates, reactor disclosures, process-boundary fields, and hidden engineering taxes are checked.

## What it absorbs

- OpenScholar-style systems motivate evidence bundles, citation grounding, and self-feedback.
- PaperQA2-style systems motivate agentic evidence gathering and explicit insufficient-information outcomes.
- ChatExtract-style systems motivate follow-up verification and uncertainty prompts.
- Dagdelen-style systems motivate schema-constrained JSON extraction.
- Docling-style conversion motivates document provenance and stable source spans.

BoundaryLedger does not reproduce those systems. It does not vendor external code, call APIs, or turn machine extraction into gold evidence. It uses local records to ask a narrower eNH3 question: what boundary may this source span support?

## Claim-rights question

A performance value is not automatically a process claim. A review table is not primary evidence. A protocol guideline can inform validation requirements but cannot become a primary performance result. A flow or HOR reactor claim may be reactor-legible while still lacking hydrogen logistics, outlet product state, capture route, or recycle closure.

BoundaryLedger therefore records the maximum supported boundary:

- unsupported_or_secondary
- product_admissibility
- cell_metric
- reactor_legibility
- process_partial
- plant_facing_insufficient

This turns extraction into adjudication: the output says both what was found and what the claim is allowed to mean.

## Phase B provenance layer

Phase B adds provenance hardening before evidence bundles and claim-rights adjudication. Each span receives a provenance type such as body, methods, results, table, review_table, figure_caption, reference, bibliography, front_matter, metadata, supplementary, or unknown.

This matters because the same eNH3 vocabulary appears in primary experimental prose, review tables, captions, references, conversion metadata, and supplementary material. Provenance now constrains claim rights:

- reference, bibliography, front matter, metadata, and copyright-note spans are low trust for primary performance boundaries;
- review tables remain secondary-only;
- captions are context-only unless paired with primary body text;
- ordinary tables are capped at cell-metric use unless paired with stronger body evidence;
- supplementary evidence requires cross-checking.

Docling JSON can provide document-structure signals when available. Old runs still work because BoundaryLedger falls back to deterministic provenance inference from text and section labels.

## Phase C and Phase D audit chain

Phase C can add optional OpenAI-compatible LLM verification. The LLM checks the rule output against the source span and records disagreements such as a more permissive boundary, a more conservative boundary, missing-control disagreements, or text-class disagreements. These LLM rows are audit signals only; they do not replace the rule ledger and do not create gold labels.

Phase D adds human audit and calibration. It exports the rule ledger, hidden-tax ledger, and optional LLM verification rows into `data/human_audit/{run_name}/human_audit_sheet.csv` and `.jsonl`. Reviewers fill only the `human_*` fields. Reviewed records are imported into `data/human_audit/{run_name}/reviewed_audit_records.*`; gold outputs under `data/gold/{run_name}/` are created only when import is run with `--accept-as-gold`.

Calibration then compares:

- BoundaryLedger rule boundaries against human boundaries;
- LLM verification boundaries against human boundaries;
- required-control labels against human labels;
- hidden-tax labels against human labels;
- overclaim and underclaim rates for future rule refinement.

This keeps the core sequence explicit: deterministic rules remain the source rule ledger, LLM output remains a verifier/auditor, and human labels become gold only after explicit validation and import.
