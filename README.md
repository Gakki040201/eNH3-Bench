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
