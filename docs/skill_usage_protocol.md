# Generic Scientific Skill Usage Protocol

eNH3-Bench may use generic scientific agent skills as optional execution aids
during benchmark construction. These aids can improve productivity, but they do
not define the benchmark task, the gold labels, or the reliability criteria.

## Allowed Uses

Generic skills may assist with:

- Markdown conversion from local, legally accessible paper notes or extracted
  text.
- Candidate source-span selection.
- Draft evidence extraction.
- Table formatting and report drafting.
- Scientific writing and manuscript organization.
- Review checklists and consistency audits.

These uses are optional. The repository must remain reproducible without
scientific-agent-skills installed.

## Boundary Between Generic Skills and eNH3-Bench

Generic scientific skills can help an agent act more effectively, but eNH3-Bench
defines whether the result is scientifically trustworthy for electrochemical
ammonia synthesis evidence. In this project, trust is determined by:

- The eNH3-Bench schema.
- The reliability rubric.
- Source-grounded human verification.
- Local validation scripts.
- Evaluation metrics for extraction, validation status, hallucination, and
  missing fields.

## Gold-Label Rule

No external skill output becomes gold evidence without human verification.

All machine-drafted records must:

1. Pass eNH3-specific schema validation.
2. Preserve source spans without invented wording.
3. Be checked against the source paragraph by a human reviewer.
4. Be accepted through the review sheet or equivalent documented review step.

Drafts from generic skills, rule baselines, or agents are provisional records,
not gold labels.

## Reproducibility

The benchmark core must continue to run with local Python standard-library code.
The optional use of generic skills should be reported as workflow assistance,
not as a required dependency or a hidden source of labels.
