# Human Minimal Verification Protocol

The human review step should be small but decisive. Reviewers do not need to
rewrite every draft record. They verify the source-grounded correctness of the
fields that matter for benchmark trust.

## Minimal Human Workload

For each machine-drafted record, the reviewer checks:

1. The source paragraph corresponds to the original paper and preserves the
   relevant wording.
2. The reaction family is correct.
3. Numerical metrics and units are supported by the source span or immediate
   context.
4. Nitrogen source is correct.
5. Isotope validation, blank controls, contamination controls, and NOx screening
   are not inferred beyond the source.
6. The proposed reliability label is reasonable under the rubric.
7. The record should be accepted, rejected, or included after a documented
   reliability override.

## Review Sheet Fields

The minimal interface is the review CSV:

- `human_decision`
- `fields_to_check`
- `correction_notes`
- `reliability_override`
- `include_in_gold`

Reviewers should use `correction_notes` for unresolved ambiguity or structured
fields that need later correction. In this phase, arbitrary correction text is
not parsed into fields automatically.

## Accept And Reject Rules

Accept a draft only when every non-empty field is source-grounded or the
remaining uncertainty is documented. Reject a draft when the source span does
not support the evidence record, when the span is too broad to audit, or when
the draft confuses review summaries with primary evidence.

Reliability overrides are allowed when the source supports a different label
than the machine draft. The reviewer does not need to rewrite the full record
unless a field is central to the benchmark analysis.
