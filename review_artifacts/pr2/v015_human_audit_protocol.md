# Human Audit Protocol for Clean-Room Outputs

## Status and purpose

This is a proposed protocol, not a completed audit. It defines 24 human-audit fields across four audit-unit types. No label in this document or the v0.15 runtime sample has been filled. The protocol must be instantiated in a versioned review export before annotation begins.

For every categorical human field, allowed labels are exactly:

- `yes`: the named proposition is supported by inspected evidence;
- `no`: the named proposition is contradicted or demonstrably incorrect;
- `uncertain`: available evidence is insufficient or conflicting;
- `not_applicable`: the proposition does not apply to this audit unit.

Notes fields contain bounded reviewer rationale, not a categorical label. A blank categorical cell means not reviewed and must never be interpreted as one of the four labels.

## Audit units

### Document-level unit

One DocumentRecord plus its repository-relative source reference, document summary signals, section map, and enough full-document access for genre/family/scope judgment. Full document text is referenced once and is not copied into each span unit.

### Semantic-span unit

One exact `cleanroom_span_id`, its target excerpt, source locator and offsets, parent source node, immediate neighboring paragraphs, cached document assessment, and same-paper linked evidence. The span is an evidence anchor, not a standalone document conclusion.

### Paper-level unit

One PaperRecord plus its reviewed document unit, all reviewed primary candidates, relevant negative/uncertain span findings, same-paper link decisions, and aggregation reasons.

### Evidence-link unit

One `evidence_link_id`, its target and evidence endpoints, both exact excerpts and locators, paper identity, role, provenance ceiling, and context-only flag. Same-paper membership is necessary but does not prove causality or sufficiency.

## Document-level fields

| Field | Proposition labeled `yes` | When to use `not_applicable` | Notes |
|---|---|---|---|
| `human_document_genre_correct` | Automated document genre is correct | Never for a valid document unit | Compare title, abstract, methods/results structure, and publication framing |
| `human_document_family_correct` | Automated document reaction family is correct at document level | Document has no reaction-family subject | Do not force `unclear` or `mixed` into a specific family |
| `human_document_scope_correct` | Automated target/secondary/off-target document scope is correct | Scope taxonomy genuinely does not apply | Distinguish primary research, review, perspective, process/TEA, and off-target work |
| `human_document_notes` | Free-text rationale | Not categorical | Required for every `no` or `uncertain`; use repository-relative locators only |

## Span-level fields

| Field | Proposition labeled `yes` | When to use `not_applicable` | Notes |
|---|---|---|---|
| `human_span_scope_correct` | Span scope is correctly assigned | No claim-like content exists | External/cited, background, target, and unclear scope must be distinguished |
| `human_claim_ownership_correct` | Claim owner is correctly assigned | No claim is present | Do not attribute cited authors’ claims to target authors |
| `human_claim_type_correct` | Semantic claim type is correct | No claim is present | Candidate trigger kind is not the semantic type |
| `human_effective_family_correct` | Effective reaction family is correct for this anchor | Span has no family-relevant content and document inheritance is inapplicable | Keep ambiguous mixed/unclear cases unresolved |
| `human_performance_result_correct` | `performance_result_evidence` is correct | Claim type cannot be performance-bearing | Require target ammonia outcome plus result-bearing evidence |
| `human_quantification_correct` | Ammonia quantification decision is correct | Quantification is not asserted or relevant | Trap/capture alone is not analytical quantification |
| `human_validation_gate_correct` | Per-gate decisions supported by the excerpt/context are correct | No validation gate is in scope | Record gate-specific rationale in notes when any gate differs |
| `human_primary_eligibility_correct` | Primary eligibility is correct under the declared v0.15 gates | Never for an emitted semantic unit | This evaluates rule application, not broader scientific truth |
| `human_context_sufficient` | Supplied target, neighbors, and linked evidence are sufficient to judge the other fields | Never for an emitted semantic unit | Use `no` when full-document inspection is required; use `uncertain` when availability is ambiguous |
| `human_notes` | Free-text rationale | Not categorical | Required for every `no` or `uncertain`; cite offsets/locators and missing context |

## Evidence-link fields

| Field | Proposition labeled `yes` | When to use `not_applicable` | Notes |
|---|---|---|---|
| `human_link_relevant` | Evidence endpoint is relevant to the target | Endpoint cannot be inspected | Relevance does not imply sufficiency |
| `human_link_role_correct` | Assigned link role is correct | Link is irrelevant and no role applies | Check quantification, validation, gas handling, and context-hint roles separately |
| `human_link_source_eligible` | `source_eligibility` matches provenance and source boundary | Endpoint cannot be resolved | References/captions/review tables remain context only |
| `human_link_context_only_correct` | `is_context_only` is correct | Endpoint cannot be resolved | Context-only links cannot upgrade target ownership or provenance |
| `human_link_notes` | Free-text rationale | Not categorical | Required for every `no` or `uncertain`; describe causal/sufficiency limitations |

## Paper-level fields

| Field | Proposition labeled `yes` | When to use `not_applicable` | Notes |
|---|---|---|---|
| `human_paper_status_correct` | Paper status follows reviewed evidence and declared aggregation rules | No valid paper unit exists | Keep engineering status distinct from scientific/benchmark release |
| `human_primary_evidence_sufficient` | Reviewed primary evidence is sufficient for the paper-level engineering status | Status is `not_evaluated` | This is not experiment comparability |
| `human_validation_summary_correct` | Aggregated validation counts/reasons match reviewed spans | No validation claim exists | Absence must not be inferred from missing excerpts alone |
| `human_limitations_complete` | Material evidence and aggregation limitations are recorded | Never for a valid paper unit | Include uncertainty, context-only sources, and comparability boundary |
| `human_paper_notes` | Free-text rationale | Not categorical | Required for every `no` or `uncertain`; reference reviewed unit IDs |

## Decision rules

- Review or perspective material used as primary support: `no` for primary eligibility/source eligibility.
- A claim by externally cited authors assigned to target authors: `no` for ownership correctness.
- An `unclear` or `mixed` reaction family used as primary without explicit disambiguation: `no` for primary-eligibility correctness.
- Trap/capture/acid-scrubber handling without analytical ammonia measurement used as quantification: `no` for quantification correctness.
- Non-ammonia reaction activity treated as ammonia performance: `no` for performance-result correctness.
- Reference-list, figure/scheme-caption-only, or review-table-only primary support: `no` for source eligibility and primary eligibility.
- A target claim whose bounded excerpt and neighbors are insufficient: `uncertain` for the affected semantic field and `no` or `uncertain` for `human_context_sufficient`, with missing context named.
- Missing evidence must not be assumed to be absent or present. Use `uncertain` and request the necessary document location.
- A same-paper evidence link does not prove causality, validation completeness, ownership, or sufficiency.
- Automated `needs_review` is not a human `no`; reviewers label each proposition independently.

## Reviewer workflow

1. Read the document summary and the document-level source once.
2. Inspect the exact target excerpt and its offsets/locator.
3. Inspect the preceding and following paragraphs; expand within the same document when necessary.
4. Inspect each linked evidence endpoint and its provenance ceiling.
5. Verify that the logical source locator resolves to the displayed exact text.
6. Fill every applicable categorical field with one of the four allowed labels.
7. Add notes for every `no` or `uncertain`, including the specific evidence or missing context.
8. Escalate reviewer conflicts, ownership inversions, family ambiguity, cross-paper evidence, and potential source-boundary errors.

Reviewers should judge evidence before consulting aggregate paper status where practical, to reduce automation anchoring.

## Adjudication

1. A first reviewer labels every selected unit.
2. A second reviewer independently reviews every `no` and `uncertain`, plus a predefined agreement sample of `yes` labels.
3. A domain adjudicator resolves disagreements using the authoritative same-document source and records the decision rationale.
4. The adjudicated export is immutable, versioned, content-hashed, and retains pre-adjudication labels for agreement analysis.
5. Promotion to Gold requires a separate proposal, updated integrity baseline, and explicit approval. Reviewed outputs do not become Gold automatically.

## Metrics

- **Field precision:** correct positive predictions divided by all automated positive predictions for a named field and defined human-positive mapping.
- **Field recall:** correct positive predictions divided by all human-positive units for that field.
- **Macro-F1:** unweighted mean of per-class or per-family F1 values; report included/excluded classes and support.
- **Abstention rate:** automated `unclear`/`needs_review`/unsupported decisions divided by eligible units under a declared mapping.
- **Inter-reviewer agreement:** report raw agreement and a chance-corrected statistic per field, with missing/`not_applicable` handling stated.
- **Stratum error rate:** errors divided by reviewed units within each documented sampling stratum.
- **Paper-level agreement:** agreement between automated and adjudicated `paper_admissibility_status`, with a confusion matrix.

Every metric must include numerator, denominator, sampling frame, confidence interval where appropriate, and missing-data policy. A deliberately stratified review sample cannot be directly converted into corpus-wide precision or recall without documented sampling weights and a representative design.

## Stop conditions

Pause expansion of annotation and open an engineering error-taxonomy review if any of the following appears systematic rather than isolated:

- reaction-family leakage across eNRR, LiNRR, NO3RR, NO2RR, NORR, mixed, or unclear;
- claim-ownership inversion between target and cited authors;
- off-target activity promoted to ammonia-primary evidence;
- quantification/trap confusion;
- references, captions, review tables, front matter, or secondary documents promoted to primary support;
- any cross-paper evidence support;
- repeated locator/offset mismatch or insufficient context that prevents reliable labeling.

Do not increase sample size merely to dilute a known systematic error. Define the error, add a regression fixture, and rerun the governed calibration loop first.
