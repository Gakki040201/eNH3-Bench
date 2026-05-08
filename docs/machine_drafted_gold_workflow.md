# Machine-Drafted, Human-Verified Gold Workflow

Phase 7 adds a local workflow for turning Markdown source notes into reviewed
gold evidence records:

```text
local Markdown documents
-> candidate evidence span discovery
-> draft evidence extraction
-> audit packet generation
-> human review sheet
-> reviewed gold JSONL merge
```

No external APIs, LLMs, PDF parsers, website scraping, or UI tools are used in
this workflow. The machine step is a rule-based drafting assistant, not a source
of gold labels.

## Workflow Steps

1. Place local Markdown documents in `input_markdown/`.
2. Run `scripts/find_candidate_spans.py` to produce candidate source spans in
   `data/candidates/`.
3. Run `scripts/run_draft_extraction.py` to create draft EvidenceRecord-like
   JSONL in `data/drafts/`.
4. Run `scripts/build_audit_packet.py` to create a Markdown audit packet and a
   CSV review sheet in `data/audit/`.
5. Human reviewers inspect the audit packet, verify source-grounded correctness,
   and fill the review sheet.
6. Run `scripts/merge_reviewed_gold.py` to include accepted drafts in reviewed
   gold JSONL.
7. Run `scripts/check_gold_dataset.py` on the reviewed gold file before using it
   for evaluation.

## Human Review Contract

Draft evidence is not gold until reviewed. The rule system can find candidate
spans and prefill obvious fields such as reaction family, nitrogen source,
Faradaic efficiency, ammonia yield, and validation controls. Human reviewers are
responsible for deciding whether each field is actually supported by the source
span.

The review sheet is the minimal manual interface. It records:

- `human_decision`
- `fields_to_check`
- `correction_notes`
- `reliability_override`
- `include_in_gold`

Corrections are notes-only in this phase. The merge step does not attempt to
parse arbitrary correction text into structured fields.

## Copyright Caution

Raw PDFs and full converted Markdown should remain local and private unless the
source license permits redistribution. Commit only compact source spans and
benchmark metadata needed for evidence grounding.
