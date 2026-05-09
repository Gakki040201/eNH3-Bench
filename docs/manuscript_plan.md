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

## Relationship To Generic Scientific Agent Skill Libraries

Generic scientific agent skill libraries provide execution aids for agents:
document handling, scientific writing, review workflows, data analysis, and
tool-specific guidance. eNH3-Bench is not positioned as a competing generic
skill library. It is a benchmark and evaluation protocol that defines a
domain-specific task: extracting, validating, normalizing, and auditing
electrochemical ammonia synthesis evidence.

The manuscript should state that generic skills may help draft evidence or
prepare review materials, but eNH3-specific schema validation, reliability
rubrics, source grounding, and human verification determine what counts as
trusted benchmark gold.

## Lowest-Level CLI Workflow Positioning

The lowest-level CLI workflow should be described as a reproducibility layer for
non-programmer users. It converts local `.md` and `.txt` documents into
Markdown, discovers candidate spans, drafts evidence, and builds an audit
packet before stopping for human verification. It deliberately avoids PDF
parsing, Docling, APIs, GraphRAG, and UI code so that the benchmark remains a
transparent source-grounded evaluation protocol rather than an autonomous
literature-mining system.

## v0.2 Milestone

The v0.2 alpha milestone should add the first real-paper gold dataset case
study:

- 10 papers selected by functional benchmark slots.
- 20-50 manually selected source spans.
- 20-50 gold evidence records.
- First real benchmark evaluation using the local baseline and evaluator.

This milestone should remain no-API by default. It should not add automated PDF
parsing, cloud model execution, or UI workflows.
