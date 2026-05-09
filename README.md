# eNH3-Bench

eNH3-Bench is a reproducible benchmark for AI-assisted extraction and validation of electrochemical ammonia synthesis literature.

The benchmark is designed around evidence-grounded claims from electrochemical nitrogen-to-ammonia studies, including eNRR, LiNRR, NO3RR, NO2RR, NORR, and mixed or unclear nitrogen-source systems. Its primary focus is not materials prediction, autonomous agents, or web applications. The core task is to extract structured evidence and assess whether reported ammonia synthesis claims are reliably supported by the source literature.

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

## Using Generic Scientific Agent Skills With eNH3-Bench

Generic scientific agent skills can optionally assist eNH3-Bench construction
by helping with Markdown preparation, source-span triage, draft evidence
records, tables, and manuscript text. They are not required to run the
benchmark, are not imported as a dependency, and are not trusted as a source of
gold labels.

Any skill-assisted output is treated as machine-drafted evidence. It must pass
the eNH3-Bench schema, audit packet, review sheet, and human source-grounded
verification before it can become gold data.

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
