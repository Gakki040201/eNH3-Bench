# eNH3-ChatExtract Relevance Prompt

You are checking whether a source span contains evidence relevant to
electrochemical ammonia synthesis.

Return JSON only:

```json
{
  "decision": "yes|no|unclear",
  "reason": "short source-grounded reason"
}
```

Relevant evidence may include eNRR, LiNRR, NO3RR, NO2RR, NORR, NH3 yield,
Faradaic efficiency, energy efficiency, potential, stability, isotope
validation, blank controls, contamination controls, NOx screening, detection
method, catalyst, electrolyte, or reactor details.

Do not infer missing claims.

SOURCE SPAN:
{{source_span}}
