# Annotation Guideline

This guide defines how to create gold evidence records for eNH3-Bench. Annotate
only what is supported by the selected source span and nearby paper context.
Do not infer missing details from outside knowledge.

## Source Span

Select the smallest source span that supports the evidence record. A span may
come from the abstract, results, methods, supplementary text, a table, a figure
caption, or a review table. The span should contain the claim, metric, or
validation statement being annotated.

Use `source_section` to mark where the span came from. If the location is not
clear, use `unknown`.

## Reaction Family

Assign the primary nitrogen-to-ammonia pathway described by the span:

- `eNRR` for electrochemical N2 reduction systems.
- `LiNRR` for lithium-mediated nitrogen reduction systems.
- `NO3RR` for nitrate reduction to ammonia.
- `NO2RR` for nitrite reduction to ammonia.
- `NORR` for nitric oxide reduction to ammonia.
- `mixed` when more than one nitrogen source or pathway is central.
- `unclear` when the span does not clearly identify the pathway.

## Nitrogen Source

Record the nitrogen source directly supported by the span. Use `15N2` when the
span explicitly discusses labeled nitrogen gas. Use `unknown` when the span
reports ammonia but does not identify the nitrogen source.

## Metrics

Extract numeric metrics only when they are explicitly grounded:

- Potential: fill `potential_value`, `potential_unit`, and
  `potential_reference` together when possible.
- Current density: convert to `current_density_mA_cm2` only when the reported
  value is already in mA cm-2 or can be safely normalized from the span.
- Faradaic efficiency: fill `faradaic_efficiency_percent`.
- Ammonia yield: preserve the original value and unit in `nh3_yield_value` and
  `nh3_yield_unit`; use normalized fields only when the normalization rule is
  explicit.
- Stability: fill `stability_hours` when a duration is reported.
- Detection: record the named method, such as indophenol blue, ion
  chromatography, NMR, or another stated assay.

Leave fields as `null` when the span does not support them.

## Validation Controls

Use `yes`, `no`, or `unclear` for these fields:

- `blank_control`: blank, gas-switching, open-circuit, or no-catalyst controls.
- `contamination_control`: checks of electrolyte, gas feed, catalyst,
  membrane, ambient ammonia, or other contamination routes.
- `nox_screening`: screening for nitrate, nitrite, NO, NO2, NOx, or related
  nitrogen oxides.

Use `isotope_validation` values as follows:

- `yes`: isotope labeling is reported and supports the nitrogen source.
- `no`: isotope validation is explicitly absent or failed.
- `unclear`: the span does not establish whether isotope validation was done.
- `not_applicable`: isotope validation is not expected for the annotated
  reaction family or evidence type.

## Reliability Label

Assign reliability based on source-grounded support:

- `A`: strong primary evidence with appropriate validation and controls.
- `B`: source-grounded evidence with minor missing or unclear validation detail.
- `C`: weak evidence with important validation gaps.
- `D`: very weak evidence with major ambiguity or missing controls.
- `Reject`: the span does not support the candidate evidence record.

For N2 reduction claims, avoid `A` unless isotope validation is present. Review
summaries should normally not receive `A` because they are not direct primary
evidence.

## Source Grounding

Every non-null field should be traceable to the source span or immediate paper
context. Do not fill catalyst, electrolyte, reactor, membrane, metric, or
control fields from memory. If a value is plausible but not grounded, leave it
blank and explain the uncertainty in `gold_notes`.
