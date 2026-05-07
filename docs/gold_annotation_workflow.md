# Gold Annotation Workflow

This workflow describes how to turn the v0.2 paper slots into source spans and
gold `EvidenceRecord` entries.

## Select Source Spans

Select two to five compact source spans per paper. Each span should support one
claim, metric set, control statement, negative result, reassessment statement,
or review summary. Prefer spans from methods, results, supplementary text,
tables, or figure captions when annotating primary evidence. Use review-table
or perspective spans only when the benchmark slot calls for secondary context.

## Annotate Metrics

Fill metric fields only when the span or immediate context directly supports
the value:

- `potential_value`, `potential_unit`, and `potential_reference`
- `current_density_mA_cm2`
- `faradaic_efficiency_percent`
- `nh3_yield_value` and `nh3_yield_unit`
- normalized NH3 yield fields when a documented normalization rule is applied
- `energy_efficiency_percent`
- `stability_hours`

Preserve the reported unit before normalization. Leave fields as `null` when
the support is absent or ambiguous.

## Mark Validation Controls

Use `yes`, `no`, or `unclear` for blank, contamination, and NOx controls. Use
`isotope_validation = yes` only when labeled-isotope evidence is explicitly
reported and supports the nitrogen source. Use `not_applicable` when isotope
validation is not expected for the reaction family or evidence type.

## Avoid Review-Summary Leakage

Do not treat review summaries, perspectives, or challenge papers as primary
evidence. If a span summarizes another paper, set `evidence_type` to
`review_summary` unless the record is clearly about the review's own analysis.
Do not assign reliability label `A` to review summaries unless the benchmark
maintainers explicitly decide the summary is being evaluated as a secondary
evidence object.

## Assign Reliability Labels

Assign labels using the reliability rubric:

- `A`: strong source-grounded primary evidence with appropriate validation and
  controls.
- `B`: source-grounded evidence with minor missing or unclear validation detail.
- `C`: weak evidence with important validation gaps.
- `D`: very weak evidence with major ambiguity or missing controls.
- `Reject`: the span does not support the candidate evidence record or is
  contradicted by stronger control evidence.

For N2 reduction claims, avoid `A` unless isotope validation is present. For
NO3RR, NO2RR, and NORR, focus on nitrogen source, product detection, competing
nitrogen species, and whether controls support the claimed pathway.

## Document Uncertainty

Use `gold_notes` to record uncertainty, assumptions, and curator rationale.
Explain when a field is left blank because the span does not support it. Keep
notes short but specific enough for adjudication.
