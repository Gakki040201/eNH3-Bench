# eNH3-ChatExtract Extraction Prompt

Extract eNH3 evidence fields from the source span.

Return one JSON object only. Use `null` for unstated numeric or free-text fields.
Use `unclear` or `unknown` for unstated categorical fields. Do not infer
validation controls.

Required fields:

```text
record_id
paper_id
source_span
method_name
reaction_family
nitrogen_source
catalyst
electrolyte
reactor_type
potential
FE_percent
EE_percent
NH3_yield
NH3_yield_unit
stability
isotope_validation
blank_control
contamination_control
nox_screening
detection_method
reliability_label
extraction_confidence
source_grounding_status
notes
```

Distinguish review summaries from primary evidence in `notes`.

SOURCE SPAN:
{{source_span}}
