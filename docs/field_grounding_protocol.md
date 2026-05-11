# Field Grounding Protocol

Every extracted field should be linked back to the source span. eNH3-Bench uses
local rule-based grounding checks to help the human reviewer identify fields
that require closer inspection.

## Grounding Status

- `explicit`: the value is supported by an explicit pattern in `source_span`.
- `missing`: the draft field is empty.
- `inferred`: the draft contains a value but the source span does not explicitly
  support it.
- `unclear`: the field value is itself unclear, unknown, no, or not applicable
  and cannot be directly grounded as a positive claim.

## Validation Fields

Positive validation fields require explicit source evidence. The pipeline must
not infer positive controls from absence of evidence.

- `isotope_validation=yes` requires 15N, 15N2, 15NH4, isotope, or isotopic
  wording.
- `blank_control=yes` requires blank, Ar, N2-free, or control wording.
- `contamination_control=yes` requires contamination, impurity, background
  ammonia, nitrate, nitrite, or NOx wording.
- `nox_screening=yes` requires NOx, nitrate, nitrite, NO2, NO3, or screening
  wording.

Review summaries must not become primary evidence unless clearly marked.
