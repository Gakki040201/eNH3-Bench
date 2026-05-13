# eNH3-ExtractBench Method Mapping

| Source framework | Original design | eNH3-localized design |
| --- | --- | --- |
| Ning 2026 | Compare ChemDataExtractor, BERT-PSIE, ChatExtract, LangChain, and Kimi for bandgap extraction. | Compare rule baseline, eNH3-ChatExtract, eNH3-NERRE-style, future optional LLM methods, and human gold for FE, EE, NH3 yield, validation controls, reliability labels, and source grounding. |
| Gupta 2024 | Parse polymer corpus, heuristic filtering, NER/LLM extraction, postprocess, and database storage. | Docling Markdown conversion, eNH3 paragraph filtering, rule or optional model extraction, reliability postprocess, and JSONL/CSV evidence database. |
| Polak & Morgan 2024 | ChatExtract relevance prompt, extraction prompt, and follow-up verification prompts. | eNH3 relevance prompt, extraction prompt, field-grounding prompt, and reliability prompt. |
| Dagdelen 2024 | NERRE structured JSON relation extraction from sentence or paragraph. | JSON schema extraction of eNH3 evidence records from source spans. |

## Local Method Families

- `enh3_chatextract_rule`: no-API ChatExtract-style scaffold with rule fallback.
- `enh3_nerre_rule`: no-API NERRE-style JSON scaffold with rule fallback.
- Future optional methods: local or API model methods may be added only when
  explicitly enabled and logged.
- Human gold: reviewed JSONL records remain the evaluation target.

## Evaluation Targets

- Field-level accuracy.
- Numeric tolerance for FE, EE, NH3 yield, potential, and stability.
- Missing field rate.
- Unsupported validation yes rate.
- Reliability label agreement.
- Source grounding coverage.
