# OpenScholar-Inspired Design Notes

## What OpenScholar Does

OpenScholar is an open scientific RAG-style system with a datastore, retriever,
reranker, self-feedback, citation verification, and benchmark evaluation ideas
such as ScholarQABench.

## What eNH3-Bench Does

eNH3-Bench is a lightweight local benchmark workflow for electrochemical
ammonia synthesis evidence extraction:

- Local paper corpus in raw or Markdown form.
- Local Markdown conversion.
- Candidate evidence span discovery.
- eNH3-specific schema.
- Rule-based draft extraction.
- Field-level source grounding.
- Reliability audit and rule feedback.
- Minimal human verification.
- Field-level evaluation and domain reports.

## Key Distinction

OpenScholar evaluates long-form literature synthesis. eNH3-Bench evaluates
field-level evidence extraction and reliability validation.

eNH3-Bench is novel as a specialized low-code adaptation because it defines:

- A domain-specific eNH3 evidence schema.
- eNRR / LiNRR / NO3RR / NO2RR / NORR validation controls.
- Field-level source grounding.
- Validation hallucination metrics.
- A minimal human verification protocol.

This is not a top-tier-scale RAG system and does not claim to match
OpenScholar.
