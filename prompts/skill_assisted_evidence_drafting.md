# Skill-Assisted Evidence Drafting Prompt

Use this prompt when an agent drafts provisional evidence records from local
Markdown or selected source spans.

```text
Task:
Draft eNH3-Bench evidence records using the existing EvidenceRecord schema.

Rules:
- Return null for unstated optional fields.
- Return unclear for unstated validation-control status fields.
- Do not infer isotope validation, blank controls, contamination controls, or
  NOx screening.
- Distinguish review_summary from primary_claim.
- Preserve source_span wording exactly from the provided paragraph.
- Do not merge claims from multiple paragraphs unless the task explicitly
  provides them as one source span.
- Flag high-risk fields, especially reliability_label, nitrogen_source,
  isotope_validation, blank_control, contamination_control, nox_screening,
  nh3_yield_unit, and potential_reference.
- Draft records are not gold until human review accepts them.

Output:
- JSONL-compatible draft records.
- A list of high-risk fields for each record.
- Notes explaining which fields require human verification.
```
