# eNH3-ChatExtract Reliability Prompt

Assign an eNH3 reliability label: `A`, `B`, `C`, `D`, or `Reject`.

Use only the source span and extracted record. Consider:

- explicit 15N or isotope validation
- blank controls
- contamination and NOx controls
- source grounding of numerical metrics
- whether the span is primary evidence or a review summary

Do not assign `A` to review summaries or unsupported claims. If validation
evidence is not explicit, prefer a lower-confidence label.

Return JSON only:

```json
{
  "reliability_label": "A|B|C|D|Reject",
  "reason": "short source-grounded reason"
}
```

SOURCE SPAN:
{{source_span}}

EXTRACTED RECORD:
{{extracted_record_json}}
