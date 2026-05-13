# eNH3-ToolBench Discovery Prompt

Use this prompt only for optional human-supervised literature triage. Candidate
claims are not gold labels.

Task:

Identify candidate eNH3 evidence claims from local text provided by the user.
Group candidates by reaction family: eNRR, LiNRR, NO3RR, NO2RR, NORR, mixed, or
unclear.

For each candidate, return:

- source excerpt
- candidate reaction family
- nitrogen source
- possible metrics such as FE, EE, NH3 yield, stability, or potential
- possible validation controls
- why the candidate requires human verification

Do not invent missing data. Do not treat review summaries as primary evidence.
Do not call external APIs or search the web.
