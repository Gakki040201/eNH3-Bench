# v0.15 Architecture Audit

## Audit boundary

The engineering audit covers the implementation at commit `ab8235b1f825a63c3175fd4b9f4d46f6dae48986`:

- `enh3bench/cleanroom_schema.py`
- `enh3bench/cleanroom_candidates.py`
- `enh3bench/cleanroom_pipeline.py`
- `enh3bench/cleanroom_output_check.py`
- `enh3bench/paper_aggregation.py`
- `scripts/run_cleanroom_pipeline.py`
- `scripts/check_cleanroom_outputs.py`

Supporting tests under `tests/test_cleanroom_*.py` and the real runtime at `data/cleanroom/enrr_cleanroom_v015_20260718/` were used as corroborating evidence. The audit does not assess scientific semantic precision, full human validation, LLM behavior, model training, or experiment comparability. No real LLM or external API was called.

## Data flow audit

| Stage | Authoritative input | Output | Deterministic identity | Failure behavior | Resume dependency | Primary risk |
|---|---|---|---|---|---|---|
| `ingest` | Sorted `*.md` files from the explicit Markdown directory | `ingest/input_manifest.json` | Repository-relative `document_ref` plus file SHA-256 | Fails when no Markdown documents exist or a file cannot be hashed | Hashes of all Markdown inputs | Conversion provenance is outside this stage when conversion occurred earlier |
| `documents` | Fresh `OrderedSourceLedger` built from the Markdown corpus | JSONL/CSV document ledger | Ledger `document_id`, `paper_id`, and `document_body_sha256` | Parser or assessment exception marks the stage and final manifest failed | Completed ingest outputs and cascade invalidation | Genre and family are rule-derived and not human-calibrated |
| `source_nodes` | Fresh ledger plus cached document assessments | Section nodes and paragraph/source nodes | `CRN15_` hash of body SHA-256 and exact start/end offsets | Serialization or source-boundary exception fails the stage | Completed document outputs and cascade invalidation | Post-hoc validation checks bounds and length, not the original Markdown slice |
| `candidates` | New source nodes plus document records | JSONL/CSV candidate spans | `CR15_` hash of body SHA-256, offsets, and candidate kind | Nonzero duplicate-offset, cross-paragraph, ID-collision, or unresolved-mapping diagnostics fail the stage | Completed source-node outputs | Regex triggers favor recall and do not establish semantic correctness |
| `semantics` | Candidate spans plus cached document records | JSONL/CSV semantic spans | Preserves `cleanroom_span_id` | Any classifier/gate/serialization exception fails the stage | Completed candidate outputs and cascade invalidation | Rule outputs require human calibration; uncertainty is intentionally fail-closed for primary eligibility |
| `links` | Semantic spans grouped by `paper_id` | Evidence-link JSONL and target index | `CRL15_` hash of paper and endpoint IDs | Cross-paper, self-link, duplicate-pair, or context-upgrade diagnostics fail the stage | Completed semantic outputs | Distance-based association is not causal proof |
| `papers` | Documents, candidates, semantics, and links | One JSONL/CSV record per document | `paper_id` and `document_id`; best evidence uses stable span IDs | Aggregation or serialization exception fails the stage | Completed links plus cascade invalidation | Any critical uncertainty can conservatively move the whole paper to `needs_review` |
| `review` | Semantics, papers, source nodes, and links | Deterministic 130-row CSV and bounded-context Markdown | Stable span IDs; seeded, stratum-aware selection | Missing endpoint/context or serialization exception fails the stage | Completed paper outputs and cascade invalidation | A stratified preparation sample is not a corpus-wide performance estimate |
| `validate` | All material run outputs | Final paper database, validation summary/report, optional comparison report | Inherited paper IDs and normalized content hashes | Any checker error fails the stage and final manifest | Completed review outputs and cascade invalidation | Structural/safety validation does not establish scientific accuracy |

Every stage is marked `running` before work and `completed` only after its outputs and hashes are recorded. Exceptions write a failed stage manifest and a failed final manifest.

## Legacy isolation audit

| Question | Result | Evidence |
|---|---|---|
| Does the normal path read legacy candidates? | PASS | `CleanroomPipeline._stage_candidates()` calls only `generate_candidate_spans()` over `_source_nodes()` and `_documents()`; `generate_candidate_spans()` states and implements no legacy runtime access. |
| Does it read evidence bundles? | PASS | The audited clean-room modules do not import `enh3bench.evidence_bundle` and do not open `evidence_bundles.jsonl`. |
| Does it read claim-rights outputs? | PASS | The clean-room path uses `assess_claim_ownership()` from `enh3bench/claim_ownership.py`; it does not import the legacy `enh3bench/claim_rights.py` or open `claim_rights_ledger.jsonl`. |
| Does it read old provenance? | PASS | Provenance is assigned from fresh source nodes by `_source_boundary()`; no legacy provenance ledger is loaded. |
| Does it read old context packets? | PASS | No clean-room module imports `enh3bench.context_packet` or opens context-packet outputs. |
| Is compare-run isolated? | PASS WITH LIMITATION | `_legacy_comparison_report()` is reachable only with explicit `compare_run`; it lists matching JSONL paths into a report and sets `legacy_semantics_imported` to false. It does not parse those records or feed them into semantics. The report is an inventory, not a semantic comparison. |
| Can legacy semantic labels change new output? | PASS | `tests/test_cleanroom_no_legacy_dependency.py` injects a deliberately wrong legacy label and verifies normal/comparison normalized outputs remain equal. |

Overall legacy-isolation conclusion: **PASS WITH LIMITATION**. The normal pipeline is isolated. Explicit comparison mode is report-only and intentionally provides only a bounded file inventory.

## Identity audit

| Property | `cleanroom_span_id` | `source_node_id` | `evidence_link_id` |
|---|---|---|---|
| Constructor | `make_cleanroom_span_id()` | `make_source_node_id()` | `make_evidence_link_id()` |
| Inputs | Document-body SHA-256, start, end, candidate kind | Document-body SHA-256, start, end | `paper_id`, target span ID, evidence span ID |
| Deterministic | Yes | Yes | Yes |
| Run-name independent | Yes | Yes | Yes |
| Path independent | Yes | Yes | Yes, transitively through endpoint IDs |
| Traversal-order independent | Yes; candidates are sorted after construction | Yes; ledger nodes are emitted in sorted document order | Yes; links are sorted after construction |
| Offset sensitive | Yes | Yes | Yes, transitively through endpoint IDs |
| Document scoped | Content-document scoped through body SHA-256 | Content-document scoped through body SHA-256 | Explicitly paper scoped |
| Collision diagnostics | Candidate and final checker duplicate-ID diagnostics | Final checker duplicate-ID diagnostic | Missing and duplicate link-ID diagnostics |

The IDs do not use a ranking, absolute path, run name, or legacy `source_span_id`. A limitation remains for byte-identical duplicate documents: equal body hashes and equal offsets can generate equal node/span IDs. The pipeline fails closed when the resulting duplicate IDs are detected, but it does not disambiguate duplicate document instances.

## Offset and provenance audit

- Source nodes carry integer `source_start_offset` and `source_end_offset`, exact `source_text`, a SHA-256, and a structured `source_locator`.
- Candidate offsets are node offsets plus local window offsets. `cleanroom_output_check.validate_cleanroom_run()` verifies that every candidate is bounded by one source node and equals the corresponding node-text slice.
- `summarize_candidates()` and the output checker both diagnose cross-paragraph candidates. The real run reports zero.
- `_source_boundary()` makes references, figure/scheme captions, and review tables `context_only`; front matter is `non_evidence`. `_hard_gate_failures()` requires `maximum_support_role == primary_support`, so these sources cannot become primary positive support.
- Introduction/background-like sections and non-primary documents are context-only. Front matter can inform document-level assessment through `_document_front_record()`, but front-matter source nodes cannot serve as evidence.
- The post-hoc checker verifies source-node offset bounds and text length, then verifies candidate-to-node slicing. It does not reopen the authoritative Markdown and compare every node with the original document slice; that is a follow-up integrity opportunity.

Result: **PASS WITH LIMITATION**.

## Resume and atomicity audit

- Each completed stage records input files, input SHA-256 values, configuration SHA-256, output files, output SHA-256 values, counts, warnings, and errors.
- `_stage_reusable()` requires completed status, equal configuration hash, equal current input hashes, existing output files, and equal output hashes.
- `_invalidate_changed_stages()` invalidates the first non-reusable stage and every downstream completed/running/failed stage.
- A requested noninitial `from_stage` requires resume and completed reusable upstream stages.
- Before work, the final manifest is changed from a possible old completed state to `running`. Any exception produces a failed stage and failed final manifest.
- `atomic_write_text()` writes a same-directory temporary file, flushes and `fsync`s it, then uses replace semantics with bounded Windows retry. CSV uses the same temporary/replace pattern. A replace failure removes the temporary file and preserves the prior destination.
- `_exclusive_run_lock()` uses exclusive file creation outside the run directory. Concurrent or stale locks refuse both execution and clean. Stale locks are not automatically expired; operator inspection is required.
- Local resume verification matched all six normalized output sets to the full run. Independent reproducibility runs also matched all six normalized hashes.
- `code_commit` is recorded in each stage state but is not an input to `_stage_reusable()`. Resuming unchanged inputs/configuration after changing code can reuse prior stage output. For the frozen commit and recorded release runs this did not change observed output, but the cache contract should include an implementation-version decision in a future version.

Result: **PASS WITH LIMITATION**.

## Clean safety audit

- `resolve_clean_target()` permits only a validated exact child of the resolved clean-room root.
- It refuses blank, dot, traversal, reserved root tokens, and the authoritative historical run name.
- It checks both symbolic links and Windows junctions before resolving the target.
- `clean()` deletes only the resolved run child while holding the per-run lock; sibling directories are untouched.
- Dry-run prints the exact target and does not delete it.
- Tests cover valid deletion, dry-run, historical/refused names, traversal, data/root tokens, exact-child behavior, sibling protection, symlink/junction refusal, and active-lock refusal.

Result: **PASS**.

## Paper aggregation audit

`aggregate_paper_records()` iterates the sorted document ledger, so every document receives exactly one paper record even when it has no candidates. It counts candidates, semantic spans, primary-eligible spans, claim types, secondary context, links, validation gates, quantification signals, performance results, and reactor/process claims.

The status rules are deliberately conservative:

1. Any document conflict, any `needs_review` semantic span, or a document family of `unclear`/`mixed` yields `needs_review`.
2. Otherwise, no primary-eligible result-bearing evidence yields `insufficient_evidence`.
3. A result with fewer than two observed required-control categories yields `partially_supported`.
4. Otherwise the record is `supported_with_limitations`, with scientific comparability explicitly unestablished.

Primary counts use only spans that passed all hard gates. `secondary_context_count` is separate, and links do not upgrade ownership or provenance. `best_evidence_span_ids` is limited to ten stable IDs ranked by semantic confidence and source offset.

The real run has 203 document records and 203 paper records; all 203 are `needs_review`. That outcome is conservative but valid under the implemented rules because paper status is an explainable aggregation of unresolved span/document uncertainty, not a claim of paper failure. It also demonstrates why human calibration is required before scientific or benchmark release.

Result: **PASS WITH LIMITATION**.

## Findings

### P0 critical

None identified.

### P1 merge blocker

None identified.

No P0 or P1 issue identified within the audited engineering boundary.

### P2 follow-up

1. **Schema enforcement is presence-oriented and incomplete across record families.** `validate_record()` checks required-key presence, schema/profile equality, and paper status, but it does not enforce field types. Evidence links, stage/final manifests, and review rows use ad hoc checks rather than a complete required-field schema. Add versioned validators without changing the v0.15 export contract.
2. **Post-hoc source-node validation does not re-slice authoritative Markdown.** The checker validates document bounds, node text length, and candidate-to-node slicing, but not node text against the source document body. Add an optional profile/versioned verification path that reopens the declared document and checks the exact slice or a ledger-backed body hash.
3. **Resume reuse does not compare recorded `code_commit`.** The manifest records it, but `_stage_reusable()` considers only status, configuration, input hashes, and output hashes. Define an explicit implementation-fingerprint policy before relying on resume across code revisions.
4. **Content-identical document instances share node/span identity inputs.** Body hash plus offsets is stable and path independent, but two byte-identical documents can collide. Current diagnostics fail closed; a future schema should decide whether duplicate documents are deduplicated or instance-disambiguated.

### P3 documentation

1. **Stale locks require manual recovery.** This is safe by default, but an operator procedure should state how to verify that a process is absent before removing a stale `.lock` file.

## Verdict

**ENGINEERING PASS WITH NON-BLOCKING LIMITATIONS**

The audited implementation is document-first, isolated from legacy semantic runtime inputs, deterministic under the tested run-name variation, exact at the candidate-to-source-node boundary, fail-closed for low-trust primary support, paper-scoped for links, and guarded for resume, atomic replacement, and cleaning. The real run passes all configured safety diagnostics, and resume/reproducibility comparisons match. The P2/P3 findings bound what remains: stronger schema/type enforcement, authoritative source re-slicing, code-aware resume policy, duplicate-document identity policy, and stale-lock operating guidance. None of these results establishes human semantic accuracy or scientific comparability.
