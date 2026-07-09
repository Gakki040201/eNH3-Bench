# eNH3-BoundaryLedger Concept

eNH3-BoundaryLedger is a source-grounded claim-rights and boundary-admissibility engine for electrochemical ammonia synthesis. It keeps the existing eNH3-TriageBench CLI workflow, but adds a scientific method layer that asks what a claim is allowed to support.

The layer is not generic RAG. Retrieval and synthesis systems can help gather evidence, but BoundaryLedger adjudicates the admissible boundary of each claim after eNH3-specific validation gates, reactor disclosures, process-boundary fields, and hidden engineering taxes are checked.

## What it absorbs

- OpenScholar-style systems motivate evidence bundles, citation grounding, and self-feedback.
- PaperQA2-style systems motivate agentic evidence gathering and explicit insufficient-information outcomes.
- ChatExtract-style systems motivate follow-up verification and uncertainty prompts.
- Dagdelen-style systems motivate schema-constrained JSON extraction.
- Docling-style conversion motivates document provenance and stable source spans.

BoundaryLedger does not reproduce those systems. It does not vendor external code, call APIs, or turn machine extraction into gold evidence. It uses local records to ask a narrower eNH3 question: what boundary may this source span support?

## Claim-rights question

A performance value is not automatically a process claim. A review table is not primary evidence. A protocol guideline can inform validation requirements but cannot become a primary performance result. A flow or HOR reactor claim may be reactor-legible while still lacking hydrogen logistics, outlet product state, capture route, or recycle closure.

BoundaryLedger therefore records the maximum supported boundary:

- unsupported_or_secondary
- product_admissibility
- cell_metric
- reactor_legibility
- process_partial
- plant_facing_insufficient

This turns extraction into adjudication: the output says both what was found and what the claim is allowed to mean.
