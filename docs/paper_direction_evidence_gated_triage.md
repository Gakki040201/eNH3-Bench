# Paper Direction: Evidence-Gated Literature Triage

eNH3-TriageBench is a literature triage system for electrochemical ammonia synthesis. Its scientific target is not keyword frequency and not generic catalyst prediction. The target is a reproducible ranking of literature-derived experimental directions according to evidence quality.

## Core Claim

Electrochemical ammonia synthesis literature contains performance claims, validation evidence, contamination warnings, protocols, review tables, and background text. These source types should not be treated as interchangeable evidence.

eNH3-TriageBench separates them before ranking experiments:

- Primary performance spans can be scored.
- Validation protocol spans guide standards but do not become performance records.
- Review tables are secondary evidence and do not become primary claims.
- Reference lists are rejected for extraction.
- Contamination and reassignment evidence is routed to a negative ledger.

## Why This Matters

High FE alone is not enough to recommend follow-up. A useful experimental direction needs source grounding, validation completeness, metric completeness, engineering relevance, and low contamination risk.

For N2-to-NH3 claims, explicit isotope validation is a hard gate for priority ranking. Claims with contamination uncertainty are penalized or deprioritized.

## Expected Manuscript Framing

The paper should frame the contribution as an evidence-gated triage benchmark and CLI workflow:

1. Convert local papers to Markdown.
2. Identify candidate spans.
3. Classify source spans.
4. Route evidence into ledgers.
5. Score primary performance records.
6. Produce triage reports and training datasets.
7. Train optional small local models from reviewed outputs.

This is a reproducibility and decision-support layer for literature review, not a substitute for human validation or new experiments.
