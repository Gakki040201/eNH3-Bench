# Claim-Rights Schema

The claim-rights ledger records the admissible scientific boundary for each source-grounded eNH3 claim.

## Claim types

- performance_claim: a primary NH3 performance or metric claim.
- validation_claim: a statement about validation, quantification, or controls.
- reactor_claim: a claim involving flow cells, GDEs, HOR, anode reactions, outlets, or stability.
- process_claim: a claim gesturing toward process or plant relevance.
- protocol_claim: a guideline or protocol statement.
- negative_evidence_claim: contamination, reassignment, or false-positive evidence.
- secondary_summary_claim: review-table or literature-summary content.
- unsupported_claim: reference-list, computational-only, context-only, or otherwise unsupported content.

## Supported boundaries

- unsupported_or_secondary: cannot support a primary eNH3 performance claim.
- product_admissibility: can inform whether NH3 attribution and quantification are admissible.
- cell_metric: can support cell-level metrics such as FE, yield, current density, voltage, and runtime.
- reactor_legibility: can support reactor-level interpretation when reactor type, flow/HOR/GDE context, runtime, outlet product state, and failure/wetting disclosures are present.
- process_partial: can support a partial process boundary when product split, capture route, solvent inventory, hydrogen boundary, and voltage basis are disclosed.
- plant_facing_insufficient: gestures toward plant or process relevance but lacks closure around recycle, auxiliary loads, TEA, or first-failure behavior.

## Validation gates

- isotope_15N
- blank_control
- nox_control
- contamination_control
- quantification_method

These gates are recorded as yes, no, missing, or unclear. N2-to-NH3 claims without explicit 15N cannot exceed the cell_metric boundary.

## Missing boundary fields

Missing fields are grouped by boundary:

- product_admissibility: ammonia quantification, 15N, blank, NOx, and contamination controls.
- cell_metric: FE, NH3 yield, current density, potential or voltage, charge or runtime, and electrode area.
- reactor_legibility: reactor type, flow rate, active area, GDE/SSC, HOR/anode reaction, runtime, outlet product state, and wetting/failure disclosure.
- process_partial: gas/liquid product split, capture route, solvent inventory, electrolyte recycle, hydrogen source, auxiliary loads, voltage basis, and first failure signal.

## Required controls

The ledger recommends controls when a claim needs them:

- N2-to-NH3 without 15N: add 15N2 isotope validation.
- Missing blank: add Ar/N2-free blank.
- Missing NOx control: add NOx/nitrate/nitrite screening.
- HOR claim: add H2-off/HOR-off control.
- Flow reactor claim: add gas/liquid product accounting and wetting/flooding diagnosis.

## Provenance-constrained claim rights

Phase B adds provenance fields to claim-rights records:

- provenance_type
- provenance_confidence
- provenance_signals
- is_primary_admissible
- is_secondary_or_context
- is_reject_or_low_trust
- provenance_constrained
- text_class_provenance_conflict

Provenance dominates text class when they disagree. A span labelled primary_performance but inferred as reference, bibliography, metadata, front_matter, or copyright_note is treated as unsupported_or_secondary with admissibility_status reject_or_low_trust_provenance.

Review-table provenance maps to secondary_summary_claim and secondary_only. Figure and scheme captions default to context_only_caption and require pair_with_primary_body_text. Ordinary table provenance cannot exceed cell_metric without paired evidence. Supplementary provenance adds supplementary_requires_crosscheck.
