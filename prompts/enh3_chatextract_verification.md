# eNH3-ChatExtract Verification Prompt

Verify each extracted field against the source span.

Return JSON only:

```json
[
  {
    "field": "field_name",
    "value": "extracted value",
    "grounding_status": "explicit|missing|inferred|unclear",
    "evidence_snippet": "short exact-support snippet or null",
    "risk_flag": "risk message or null"
  }
]
```

Rules:

- Numeric fields require nearby numeric support.
- Validation fields marked `yes` require explicit source text.
- Do not infer isotope validation, blank control, contamination control, or NOx
  screening from absence of discussion.
- Unsupported validation `yes` values should be flagged and downgraded in notes.

SOURCE SPAN:
{{source_span}}

EXTRACTED RECORD:
{{extracted_record_json}}
