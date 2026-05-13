# eNH3-NERRE-Style JSON Schema Prompt

Extract structured eNH3 evidence from the sentence or paragraph.

Return JSON only. Return either one object or an array of objects if the span
contains multiple distinct evidence claims.

Each object must contain:

```text
record_id, paper_id, source_span, method_name, reaction_family, nitrogen_source,
catalyst, electrolyte, reactor_type, potential, FE_percent, EE_percent,
NH3_yield, NH3_yield_unit, stability, isotope_validation, blank_control,
contamination_control, nox_screening, detection_method, reliability_label,
extraction_confidence, source_grounding_status, notes
```

Use `null` for unstated values. Do not invent validation controls. Preserve the
source wording in `source_span`.

SOURCE SPAN:
{{source_span}}
