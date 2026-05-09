# Skill-Assisted Markdown Conversion Prompt

Use this prompt when a generic scientific agent skill or local document helper
assists conversion of legally accessible paper text into Markdown notes.

```text
Task:
Convert the provided local paper text or extracted content into structured
Markdown for eNH3-Bench annotation.

Rules:
- Preserve original wording for any candidate source spans.
- Do not summarize source spans that may be used for evidence annotation.
- Use headings that reflect the source structure when available.
- Mark uncertain sections with [uncertain section].
- Mark tables or figure captions clearly.
- Do not invent missing data.
- Do not infer validation controls from background knowledge.
- Do not add claims that are not present in the source text.
- Keep copyright-sensitive content local unless the source license permits
  redistribution.

Output:
- Structured Markdown.
- A short list of sections likely to contain eNH3 evidence.
- A short list of sections that should not be treated as primary evidence.
```
