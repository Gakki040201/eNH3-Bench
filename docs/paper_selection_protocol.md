# Paper Selection Protocol

The v0.2 case study uses ten papers selected by functional benchmark slots
rather than random sampling. This is intentional: the goal is to stress the
evidence schema and reliability rubric across known difficult claim types before
scaling to a larger benchmark.

## Why Functional Slots

Electrochemical ammonia synthesis literature is heterogeneous. A random sample
of ten papers could miss validation protocols, reassessments, Li-mediated NRR,
nitrate reduction, or nitrite / NOx systems. Functional slots guarantee that
the first real-paper case study exercises the benchmark dimensions needed for a
paper-quality evaluation: extraction, unit normalization, control recognition,
source grounding, and reliability labeling.

## Minimum Coverage

The ten-paper set should cover:

- eNRR protocol or validation guidance.
- eNRR perspective, challenge, or field-level context.
- Contamination or reassessment evidence.
- Aqueous eNRR primary claims.
- Debated eNRR claims.
- Negative-control or reassessment studies.
- Li-mediated NRR primary evidence.
- Continuous-flow or reactor-focused LiNRR evidence.
- Nitrate-to-ammonia primary evidence.
- Nitrite, nitric oxide, NOx, mixed, or unclear nitrogen-source systems.

## Inclusion Criteria

Include papers that provide at least one manually selectable span relevant to
the evidence schema. Prefer sources with clear methods, controls, metric
definitions, or validation discussion. Primary research papers should contain
extractable claims or negative results. Review or perspective papers should be
included only when they serve a benchmark role that cannot be met by primary
evidence alone.

## Exclusion Criteria

Exclude papers that cannot be handled copyright-safely, lack relevant
electrochemical ammonia synthesis content, or cannot support source-grounded
annotation. Do not include papers solely because they are highly cited if they
do not add coverage to the functional slots. Exclude sources that require
automated website scraping or PDF parsing for this phase.

## Open-Access and Copyright-Safe Handling

Record bibliographic metadata and short manually selected spans only. Do not
commit full article PDFs, full article text, or large copied sections. Use
open-access sources when possible, and keep source spans compact enough to
support the gold labels without reproducing the paper.

## Manual Source-Span Recording

For each paper, manually inspect the source outside the benchmark pipeline and
copy two to five short spans into `data/spans/spans.v0.2.template.jsonl` or a
derived filled dataset file. Record the section, paper ID, and annotation
status. The benchmark core should then operate only on the local CSV and JSONL
files.
