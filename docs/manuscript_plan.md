# Manuscript Plan

## Target Contribution

eNH3-Bench should be presented as a benchmark, not a software product. The paper
should emphasize the benchmark artifacts that make controlled comparison
possible: schema, annotation protocol, reliability rubric, baseline, metrics,
and report-generation workflow.

## Core Claims

- eNH3-Bench is a reliability-aware extraction benchmark for electrochemical
  ammonia synthesis literature.
- The benchmark covers multi-system nitrogen-to-ammonia chemistry, including
  eNRR, LiNRR, NO3RR, NO2RR, NORR, and mixed or unclear nitrogen-source systems.
- The task evaluates AI capability boundaries: extraction, normalization,
  validation-status recognition, source grounding, and hallucination control.
- Reliability labels encode evidence support and validation strength, not
  materials novelty or catalyst performance.

## Paper Structure

1. Define why electrochemical ammonia synthesis extraction is hard.
2. Introduce the evidence schema and annotation protocol.
3. Explain reliability labels and validation controls.
4. Describe synthetic examples and planned curated literature expansion.
5. Present the no-API rule baseline as a reproducible lower bound.
6. Report categorical, numeric, hallucination, and missing-field metrics.
7. Analyze errors, especially reliability-label and validation-control errors.
8. Discuss limitations and future benchmark releases.

## Positioning

The manuscript should avoid framing eNH3-Bench as a model, a materials
prediction system, an autonomous agent, or a UI. The contribution is a benchmark
for measuring whether extraction systems can stay grounded in source evidence
while respecting the reliability constraints of electrochemical ammonia
synthesis claims.
