# eNH3-Bench

eNH3-Bench is a reproducible benchmark for AI-assisted extraction and validation of electrochemical ammonia synthesis literature.

The benchmark is designed around evidence-grounded claims from electrochemical nitrogen-to-ammonia studies, including eNRR, LiNRR, NO3RR, NO2RR, NORR, and mixed or unclear nitrogen-source systems. Its primary focus is not materials prediction, autonomous agents, or web applications. The core task is to extract structured evidence and assess whether reported ammonia synthesis claims are reliably supported by the source literature.

## Final Minimal Use: eNH3-TriageBench

The final minimal CLI system is eNH3-TriageBench: a local, evidence-gated literature triage workflow for electrochemical ammonia synthesis. It classifies source spans, routes evidence ledgers, scores experiment follow-up directions, exports Markdown/CSV reports, builds training datasets from reviewed outputs, and optionally trains small local scikit-learn models. It does not call APIs, scrape websites, require a GPU, or train LLMs.

Run the final triage pipeline:

```powershell
C:\Python314\python.exe scripts\run_final_triage_pipeline.py ^
  --input-dir input_raw ^
  --markdown-dir input_markdown ^
  --run-name final_pilot ^
  --converter docling ^
  --top-n 30 ^
  --max-per-paper 6 ^
  --force-reconvert
```

Build training datasets:

```powershell
C:\Python314\python.exe scripts\build_training_dataset.py --run-name final_pilot
```

Train the source-span classifier:

```powershell
C:\Python314\python.exe scripts\train_source_span_classifier.py --run-name final_pilot
```

Train the triage ranker:

```powershell
C:\Python314\python.exe scripts\train_triage_ranker.py --run-name final_pilot
```

Predict with trained models:

```powershell
C:\Python314\python.exe scripts\predict_with_trained_models.py --run-name final_pilot
```

Check final outputs:

```powershell
C:\Python314\python.exe scripts\check_final_outputs.py --run-name final_pilot
```

Optional local training dependencies:

```powershell
C:\Python314\python.exe -m pip install scikit-learn joblib
```

See `docs/final_cli_workflow.md`, `docs/final_outputs_and_meaning.md`, and `docs/training_workflow.md` for the complete workflow.

## eNH3-BoundaryLedger: claim-rights layer

eNH3-BoundaryLedger is a source-grounded claim-rights and boundary-admissibility engine for electrochemical ammonia synthesis. eNH3-TriageBench remains the supported CLI workflow name; BoundaryLedger is the scientific method layer that asks what each claim is allowed to support: product admissibility, cell metrics, reactor legibility, partial process boundaries, or only secondary/contextual use.

Build BoundaryLedger outputs after classified spans or ledgers exist:

```powershell
C:\Python314\python.exe scripts\build_evidence_bundles.py --run-name final_pilot
C:\Python314\python.exe scripts\classify_claim_rights.py --run-name final_pilot
C:\Python314\python.exe scripts\detect_hidden_taxes.py --run-name final_pilot
C:\Python314\python.exe scripts\export_boundary_ledger_report.py --run-name final_pilot
```

Outputs are written under `data\boundary_ledger\{run_name}\` and `data\reports\boundary_ledger_report.{run_name}.md`. See `docs/boundary_ledger_concept.md`, `docs/claim_rights_schema.md`, and `docs/hidden_tax_rubric.md`.

### Reaction-family profiles

BoundaryLedger is eNH3-wide, with formal profiles for `eNRR`, `LiNRR`, `NO3RR`, `NO2RR`, `NORR`, `mixed`, and `unclear` records. LiNRR is the current USTC wet-lab demonstration track because it exposes the densest set of solvent, interphase, wetting, product-state, and HOR/H2 boundary burdens; it is not the only supported literature family.

Reaction-family profiles normalize or infer `reaction_family`, attach profile summaries to evidence and claim-rights outputs, apply family-specific validation gates, and keep the experiment planner scoped to LiNRR lab-demo routes by default.

```powershell
C:\Python314\python.exe scripts\generate_experiment_routes.py --run-name final_pilot --lab-profile data\lab_profiles\ustc_linnr_profile.yaml --reaction-family LiNRR
C:\Python314\python.exe scripts\generate_experiment_routes.py --run-name final_pilot --lab-profile data\lab_profiles\ustc_linnr_profile.yaml --include-families LiNRR,eNRR --no-lab-demo-only
```

See `docs/reaction_family_profiles.md`.

### Phase B: Docling provenance hardening

Phase B marks source spans as primary body text, tables, review tables, captions, references, metadata/front matter, or supplementary context before claim-rights adjudication. Docling JSON is used when available, and older runs fall back to deterministic provenance inference.

Caption records expose `support_hint_boundary` separately from `maximum_supported_boundary`; unpaired figure and scheme captions remain context-only and `unsupported_or_secondary`.

```powershell
C:\Python314\python.exe scripts\export_docling_provenance.py --run-name final_pilot
C:\Python314\python.exe scripts\attach_provenance_to_spans.py --run-name final_pilot
C:\Python314\python.exe scripts\build_evidence_bundles.py --run-name final_pilot
C:\Python314\python.exe scripts\classify_claim_rights.py --run-name final_pilot
C:\Python314\python.exe scripts\detect_hidden_taxes.py --run-name final_pilot
C:\Python314\python.exe scripts\export_boundary_ledger_report.py --run-name final_pilot
```

Check that conversion metadata and repository cover pages are isolated before span extraction:

```powershell
C:\Python314\python.exe scripts\check_front_matter_isolation.py --markdown-dir input_markdown --run-name pilot_existing_02
```

See `docs/docling_provenance_hardening.md`.

### Phase C: Optional USTC/OpenAI-compatible LLM verification

Phase C adds an optional ChatExtract-style verification layer using an OpenAI-compatible chat completions API. It verifies BoundaryLedger rule outputs against source spans and writes audit/disagreement records for human review. It does not replace the rule system and does not create gold labels.

LLM responses are strictly schema-validated. A JSON object with missing required verification keys is treated as a verification failure and routed to human review.

Low-trust provenance caps LLM verification and constrains hidden-tax detection. References, metadata, front matter, and copyright notes preserve the original LLM output as an audit signal, but trusted LLM boundaries cannot upgrade beyond the rule/provenance-constrained boundary, and hidden-tax detection avoids domain-tax cascades from low-trust text.

Mock run with no network:

```powershell
C:\Python314\python.exe scripts\verify_with_llm.py --run-name final_pilot --model mock --max-records 10 --mock
C:\Python314\python.exe scripts\compare_llm_models.py --run-name final_pilot --models mock --max-records 10 --mock
```

Real USTC-compatible API example:

```powershell
$env:USTC_API_KEY="..."
$env:USTC_BASE_URL="https://api.llm.ustc.edu.cn"
$env:USTC_MODEL="..."
C:\Python314\python.exe scripts\verify_with_llm.py --run-name final_pilot --max-records 10
```

See `docs/phase_c_ustc_api.md`.

### Phase D: Human audit and calibration

Phase D exports BoundaryLedger rule outputs, hidden-tax outputs, and optional LLM verification rows into human-review sheets. Human labels are validated on import. They do not overwrite rule ledgers, and they become gold only when imported with `--accept-as-gold`.

Export priority audit rows with optional USTC/DeepSeek verification columns:

```powershell
C:\Python314\python.exe scripts\export_human_audit_sheet.py --run-name final_pilot --llm-model deepseek-v4-pro --top-n 50 --priority-only
C:\Python314\python.exe scripts\export_review_instructions.py --run-name final_pilot
```

Import a reviewed CSV:

```powershell
C:\Python314\python.exe scripts\import_human_audit_sheet.py --run-name final_pilot --input data\human_audit\final_pilot\human_audit_sheet.reviewed.csv
```

Run calibration after reviewed records exist:

```powershell
C:\Python314\python.exe scripts\calibrate_boundary_ledger.py --run-name final_pilot
```

See `docs/human_audit_protocol.md`.

### Phase E: eNH3-BoundaryBench benchmark construction

Phase E converts validated Phase D human-reviewed records into eNH3-BoundaryBench task datasets. It builds six benchmark tasks for source-span classification, validation-gate extraction, claim-rights boundary classification, hidden-tax detection, required-control prediction, and experiment-decision ranking.

Build, split, evaluate, and document the benchmark:

```powershell
C:\Python314\python.exe scripts\build_boundary_benchmark.py --run-name final_pilot
C:\Python314\python.exe scripts\split_boundary_benchmark.py --run-name final_pilot --seed 13
C:\Python314\python.exe scripts\evaluate_boundary_benchmark.py --run-name final_pilot
C:\Python314\python.exe scripts\export_benchmark_datacard.py --run-name final_pilot
```

The builder uses `data\gold\{run_name}\human_gold_claim_rights.jsonl` when present, otherwise validated `data\human_audit\{run_name}\reviewed_audit_records.jsonl`. Unreviewed records are excluded. See `docs/boundary_benchmark_tasks.md`.

### Phase F0: Lab-constrained closed-loop experiment planner

Phase F0 converts BoundaryLedger gaps, hidden taxes, provenance constraints, optional LLM disagreements, human audit records, lab capabilities, and imported experiment results into structured experiment route cards. It is rule-based by default and does not call APIs.

```powershell
C:\Python314\python.exe scripts\init_lab_profile.py --output data\lab_profiles\ustc_linnr_profile.yaml
C:\Python314\python.exe scripts\generate_experiment_routes.py --run-name pilot_existing_02 --lab-profile data\lab_profiles\ustc_linnr_profile.yaml
C:\Python314\python.exe scripts\export_experiment_route_cards.py --run-name pilot_existing_02
C:\Python314\python.exe scripts\export_experiment_result_template.py --run-name pilot_existing_02
C:\Python314\python.exe scripts\import_experiment_results.py --run-name pilot_existing_02 --input data\experiment_results\pilot_existing_02\experiment_results.reviewed.csv
C:\Python314\python.exe scripts\evaluate_experiment_loop.py --run-name pilot_existing_02
```

See `docs/lab_constrained_experiment_planner.md` and `docs/closed_loop_workflow.md`.

## What The Benchmark Evaluates

eNH3-Bench evaluates:

- Extraction accuracy for structured paper and evidence fields.
- Unit normalization for reported performance metrics.
- Validation-status accuracy for isotope labeling, blank controls, contamination controls, and NOx screening.
- Source grounding against explicit text spans.
- Hallucination rate for unsupported extracted claims.

## Repository Scope

The initial benchmark repository provides:

- A gold-standard evidence schema.
- Annotation templates for paper spans and gold labels.
- A rule-based baseline.
- Evaluation metrics.
- A report generator.
- Documentation for a benchmark paper.

## No-API Default

The benchmark core is no-API by default. It does not require OpenAI, DeepSeek, GraphRAG, AutoGen, LangChain, cloud models, website scraping, PDF parsing, or model training. Baseline tooling is intended to run locally with lightweight Python standard-library code, with `pytest` available only as an optional development dependency.

## v0.2 Real-Paper Gold Dataset Workflow

The v0.2 scaffold prepares a ten-paper real-literature case study without adding API integrations, PDF parsing, or UI code. Paper slots are defined in `data/papers/papers.v0.2.template.csv`, manual span placeholders are defined in `data/spans/spans.v0.2.template.jsonl`, and matching gold-label templates are defined in `data/gold/gold.v0.2.template.jsonl`.

Use the local checker in template mode while source spans are still empty:

```bash
C:\Python314\python.exe scripts/check_gold_dataset.py --papers data/papers/papers.v0.2.template.csv --spans data/spans/spans.v0.2.template.jsonl --gold data/gold/gold.v0.2.template.jsonl --allow-empty-source-span
```

For a filled dataset, omit `--allow-empty-source-span` so empty gold evidence spans fail validation. The checker writes a local Markdown summary to `data/reports/gold_dataset_check.md`.

## Machine-Drafted Human-Verified Workflow

The optional v0.2 machine-drafted workflow remains local and no-API:

1. Place Markdown files in `input_markdown/`.
2. Run `C:\Python314\python.exe scripts/find_candidate_spans.py`.
3. Run `C:\Python314\python.exe scripts/run_draft_extraction.py`.
4. Run `C:\Python314\python.exe scripts/build_audit_packet.py`.
5. Manually review `data/audit/review_sheet.v0.2.csv` with `data/audit/audit_packet.v0.2.md`.
6. Run `C:\Python314\python.exe scripts/merge_reviewed_gold.py`.
7. Run `C:\Python314\python.exe scripts/check_gold_dataset.py --papers data/papers/papers.v0.2.template.csv --spans data/candidates/candidate_spans.v0.2.jsonl --gold data/gold/gold.v0.2.reviewed.jsonl`.

Draft evidence is not gold until human review accepts it.

## Lowest-Level CLI Workflow

For a minimal local run from documents to audit packet:

```powershell
# 1. Put .pdf, .docx, .txt, or .md files in input_raw\

# 2. Convert local files to Markdown
C:\Python314\python.exe scripts\convert_local_documents.py

# 3. Create candidate spans, draft evidence, audit packet, and review CSV
C:\Python314\python.exe scripts\run_minimal_review_pipeline.py

# 4. Human review
# Open data\audit\audit_packet.v0.2.md
# Open data\audit\review_sheet.v0.2.csv
# Fill accept/reject/include_in_gold/reliability_override/correction_notes

# 5. Merge accepted reviewed records into gold JSONL
C:\Python314\python.exe scripts\merge_reviewed_gold.py

# 6. Validate reviewed gold
C:\Python314\python.exe scripts\check_gold_dataset.py --papers data\papers\papers.v0.2.template.csv --spans data\candidates\candidate_spans.v0.2.jsonl --gold data\gold\gold.v0.2.reviewed.jsonl

# 7. Evaluate predictions after a prediction file exists
C:\Python314\python.exe scripts\evaluate_predictions.py --gold data\gold\gold.v0.2.reviewed.jsonl --pred data\predictions\your_predictions.jsonl

# 8. Export domain summary after reviewed gold exists
C:\Python314\python.exe scripts\export_domain_report.py --gold data\gold\gold.v0.2.reviewed.jsonl --output-md data\reports\domain_report.v0.2.md
```

DOCX and text-based PDF conversion use optional local packages only:
`python-docx` for `.docx` and `pymupdf` for text-based `.pdf`. Unsupported
scanned PDFs should be manually converted or deferred to a future Docling/OCR
workflow. Converted Markdown remains local/private and should not be published
as full copyrighted text unless licensed.

For higher-quality paper conversion, install optional local converters:

```powershell
C:\Python314\python.exe -m pip install docling markitdown pymupdf
```

Recommended Docling-first rerun for local PDFs:

```powershell
C:\Python314\python.exe scripts\run_enh3_scholar.py ^
  --input-dir input_raw ^
  --markdown-dir input_markdown ^
  --run-name v0.2_docling ^
  --top-n 20 ^
  --max-per-paper 5 ^
  --converter docling ^
  --force-reconvert ^
  --clean-markdown ^
  --stop-at audit
```

Fallback auto mode tries Docling, then MarkItDown, then local PyMuPDF/basic
conversion:

```powershell
C:\Python314\python.exe scripts\run_enh3_scholar.py ^
  --input-dir input_raw ^
  --markdown-dir input_markdown ^
  --run-name v0.2_auto ^
  --top-n 20 ^
  --max-per-paper 5 ^
  --converter auto ^
  --force-reconvert ^
  --clean-markdown ^
  --stop-at audit
```

Use Docling first for paper PDFs. Use `auto` if Docling is unavailable or a
specific file fails. MarkItDown is an optional Python package fallback; this
repository does not vendor or import scientific-agent-skills.

## One-Command OpenScholar-Style Local Run

The unified runner performs local conversion, candidate span discovery, draft
extraction, field grounding, rule feedback, audit packet export, review-sheet
export, and manifest writing:

```powershell
C:\Python314\python.exe scripts\run_enh3_scholar.py --input-dir input_raw --markdown-dir input_markdown --run-name v0.2 --top-n 8 --max-per-paper 3 --stop-at audit
```

This is an OpenScholar-inspired local workflow pattern, not an OpenScholar
fork. It does not use OpenScholar code, datastore, APIs, retrievers, LLMs, or
web search.

For a plain-language overview of the final repository functionality, see
`docs/final_project_functionality.md`.

## eNH3-ExtractBench: Four-Framework Localization

eNH3-Bench now includes a lightweight eNH3-ExtractBench layer localized from
four materials-literature extraction frameworks:

1. OpenScholar-style local runner for document-to-audit workflows.
2. Docling-first conversion for local paper files.
3. eNH3-ChatExtract prompt chain with an offline rule fallback.
4. eNH3-NERRE-style JSON extraction scaffold with an offline rule fallback.
5. ToolBench-style method comparison across gold records and method outputs.

This is not a fork or reproduction of those systems. It does not vendor external
repositories, does not call APIs by default, and does not make machine outputs
into gold without human verification.

Run offline extraction method scaffolds after candidate spans exist:

```powershell
C:\Python314\python.exe scripts\run_enh3_chatextract.py --spans data\candidates\candidate_spans.v0.2_docling.jsonl --run-name v0.4_pilot
C:\Python314\python.exe scripts\run_enh3_nerre_style.py --spans data\candidates\candidate_spans.v0.2_docling.jsonl --run-name v0.4_pilot
```

Evaluate method outputs against reviewed gold:

```powershell
C:\Python314\python.exe scripts\evaluate_extraction_runs.py --gold data\gold\gold.v0.2.reviewed.jsonl --run-name v0.4_pilot
C:\Python314\python.exe scripts\build_extraction_comparison_report.py --comparison-json data\extraction_runs\v0.4_pilot\comparison_report.json
```

See `docs/eNH3_ExtractBench_final_design.md` and
`docs/four_paper_localization_plan.md` for the localization guardrails.

## Using Generic Scientific Agent Skills With eNH3-Bench

Generic scientific agent skills can optionally assist eNH3-Bench construction
by helping with Markdown preparation, source-span triage, draft evidence
records, tables, and manuscript text. They are not required to run the
benchmark, are not imported as a dependency, and are not trusted as a source of
gold labels.

Any skill-assisted output is treated as machine-drafted evidence. It must pass
the eNH3-Bench schema, audit packet, review sheet, and human source-grounded
verification before it can become gold data.

## External Code Reuse And Attribution

OpenScholar is an Apache-2.0 project that may serve as an external conceptual
reference for pipeline organization. eNH3-Bench does not vendor OpenScholar,
does not import it, and does not imply endorsement by OpenScholar authors.

Any future copied or modified external code must be recorded in
`docs/code_reuse_log.md`, retain required attribution notices, and follow the
reuse protocol in `docs/external_reference_protocol.md`.

## Planned Data Layout

```text
data/
  papers/       Paper-level metadata and input manifests.
  spans/        Source spans selected for annotation.
  gold/         Gold-standard evidence records.
  predictions/  Local model or baseline predictions, ignored by default.
  reports/      Generated evaluation reports, ignored by default.
```

## Development

Install development extras only if you want to run the pytest suite:

```bash
python -m pip install -e ".[dev]"
```

The benchmark core should remain runnable without external services.
