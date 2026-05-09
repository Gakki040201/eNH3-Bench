# Domain Novelty Statement

eNH3-Bench does not claim novelty as a new generic scientific agent skill
library. Its novelty is a domain-specific benchmark task for electrochemical
ammonia synthesis literature.

## What Is New

The project contributes:

1. A multi-system eNH3 evidence schema covering eNRR, LiNRR, NO3RR, NO2RR,
   NORR, mixed systems, and unclear nitrogen-source systems.
2. A reliability-aware validation rubric with explicit treatment of isotope
   validation, blank controls, contamination controls, NOx screening, evidence
   type, and A/B/C/D/Reject labels.
3. A machine-drafted, human-verified gold construction workflow that separates
   candidate span discovery, draft extraction, audit packet review, and final
   reviewed gold merge.
4. Evaluation metrics for validation hallucination, source grounding, missing
   supported fields, categorical extraction accuracy, and numeric extraction
   error.
5. A seed dataset path for eNRR, LiNRR, NO3RR, NO2RR, and NORR literature.

## Relationship To Generic Skills

Generic scientific agent skills may help produce drafts, organize review
materials, or write reports. They do not replace the eNH3-specific schema,
rubric, or evaluator.

The central claim is:

```text
Generic scientific agent skills can draft evidence, but eNH3-Bench defines
what counts as trustworthy evidence in electrochemical ammonia synthesis.
```
