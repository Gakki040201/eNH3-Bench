# OpenScholar-Style Adaptation

eNH3-Bench includes a unified CLI runner inspired by the pipeline organization
style of OpenScholar. It does not copy OpenScholar code.

## What Is Adapted Conceptually

- OpenScholar run-style entrypoint -> `scripts/run_enh3_scholar.py`.
- Retriever/reranker pattern -> keyword candidate span discovery with `top_n`
  and `max_per_paper` limits.
- Citation verification pattern -> eNH3 field-level grounding checks.
- Self-feedback pattern -> local rule-based draft feedback.
- ScholarQABench-style evaluation thinking -> eNH3-Bench field-level
  extraction and reliability validation metrics.

## What Is Not Included

eNH3-Bench does not use OpenScholar datastore code, trained retrievers,
rerankers, LLM calls, APIs, or web search. It is not a top-tier-scale scientific
RAG system and does not claim to match OpenScholar's scale.

OpenScholar evaluates long-form scientific synthesis. eNH3-Bench evaluates
field-level evidence extraction and reliability validation for electrochemical
ammonia synthesis literature.
