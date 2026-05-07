# Reliability Rubric

Reliability labels describe whether a reported ammonia synthesis claim is
supported by source-grounded controls and measurement context. Labels are not
judgments of catalyst quality or performance novelty.

## Label A

High-reliability evidence. The source span and surrounding paper report a
primary ammonia synthesis claim with isotope validation when applicable,
appropriate blanks, contamination controls, and screening for relevant NOx or
nitrogen-containing impurities. Reported metrics are internally consistent and
grounded in explicit methods or tables.

Use sparingly. A record with `reliability_label = A` should normally have
`isotope_validation = yes` unless isotope validation is genuinely not
applicable to the reaction family.

## Label B

Moderate-reliability evidence. The claim is source-grounded and has several key
controls, but one important validation detail is incomplete, unclear, or only
partially described. Metrics are extractable, but normalization or control
coverage may require caution.

## Label C

Low-reliability evidence. The claim is present in the source, but validation is
thin, ambiguous, or missing in important areas. Examples include unclear blank
controls, limited contamination discussion, missing isotope validation for N2
reduction, or insufficient method detail for the reported metric.

## Label D

Very low-reliability evidence. The source contains a reported ammonia outcome,
but the claim lacks core validation support, is poorly grounded, or has major
ambiguity about nitrogen source, controls, or measurement method.

## Label Reject

Reject the candidate evidence. Use this label when the extracted span does not
support an ammonia synthesis claim, is unsupported by the cited text, describes
an unrelated system, duplicates another accepted record without adding evidence,
or is contradicted by reassessment or control evidence.

## Review Summaries

Review-table and review-summary entries can be useful for benchmark coverage,
but they usually should not receive `A` because they are not direct primary
evidence. Prefer `B`, `C`, `D`, or `Reject` depending on the grounding and
detail available in the review source.
