# External AI Tools Absorption Plan

BoundaryLedger absorbs concepts from external scientific AI tools without copying code, depending on APIs, or changing the no-API local workflow.

## OpenScholar

Absorbed concept: evidence bundle, citation grounding, and self-feedback.

BoundaryLedger adaptation: each classified span becomes an evidence bundle with provenance, source text, classification fields, extraction permissions, and grounding status. Claim-rights outputs are source-grounded and include reasoning.

## PaperQA2

Absorbed concept: agentic evidence gathering and explicit insufficient-information outcomes.

BoundaryLedger adaptation: missing boundary fields and required controls make insufficient information explicit rather than filling gaps by inference.

## ChatExtract

Absorbed concept: follow-up verification and uncertainty prompts.

BoundaryLedger adaptation: recommended_experiment and required_controls fields convert uncertainty into concrete follow-up controls, such as 15N2 validation, Ar/N2-free blanks, NOx screening, HOR-off controls, and flow product accounting.

## Dagdelen

Absorbed concept: schema-constrained JSON extraction from scientific text.

BoundaryLedger adaptation: extracted fields are preserved in evidence bundles, but the method then adjudicates what boundary those fields are allowed to support.

## MatSciBERT

Absorbed concept: baseline classifier only.

BoundaryLedger adaptation: text classification can be improved by local classifiers, but claim rights are still rule-auditable and source-grounded. A classifier label is not a scientific result.

## Docling

Absorbed concept: document conversion and provenance.

BoundaryLedger adaptation: converted source spans can carry document identifiers, source sections, and source text into evidence bundles. Conversion quality remains a provenance and verification issue, not proof of claim admissibility.
