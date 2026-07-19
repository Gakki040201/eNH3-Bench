# v0.15 Schema Dictionary

## Scope and notation

This dictionary is derived from `enh3bench/cleanroom_schema.py`, the stage constructors in `enh3bench/cleanroom_pipeline.py` and `enh3bench/paper_aggregation.py`, and the real run `data/cleanroom/enrr_cleanroom_v015_20260718/`. “Required” means declared in `REQUIRED_FIELDS` unless a table explicitly describes an emitted runtime contract that is not covered by that validator. Expected types describe the JSON representation; review CSV cells are serialized strings.

The four common fields below are required on every validated document, source-node, candidate, semantic, and paper record and are inherited by each corresponding table.

| Field | Expected type | Required | Source stage | Meaning | Allowed values / constraints | Review risk |
|---|---|---:|---|---|---|---|
| `schema_version` | string | Yes | all record stages | Independent clean-room schema identifier | Exactly `0.15-cleanroom.1` | Confusing it with audit schema 0.13 |
| `pipeline_profile` | string | Yes | all record stages | Explicit behavior profile | Exactly `document_first_cleanroom_v1` | Silent profile mixing |
| `run_name` | string | Yes | all record stages | Runtime namespace, not semantic identity | Safe run-name pattern; not used in CR15/CRN15/CRL15 IDs | Treating runs as different scientific records |
| `record_created_by_stage` | string | Yes | all record stages | Stage that emitted the record | `documents`, `source_nodes`, `candidates`, `semantics`, `links`, or `papers` as applicable | Present validator does not verify the stage value |

## DocumentRecord

| Field | Expected type | Required | Source stage | Meaning | Allowed values / constraints | Review risk |
|---|---|---:|---|---|---|---|
| `paper_id` | string | Yes | documents | Paper-scoped identifier | Non-empty; equals the run’s document key in current corpus | Paper/document aliasing |
| `document_id` | string | Yes | documents | Document identifier | Non-empty; unique in run | Filename-derived identity assumptions |
| `document_ref` | string | Yes | documents | Repository-relative input reference | `input_markdown/<document_id>.md`; no absolute path | Path leakage |
| `document_body_sha256` | string | Yes | documents | SHA-256 of canonical ledger body | 64 lowercase hexadecimal characters in observed run | Hash/body mismatch not rechecked post hoc |
| `document_character_count` | integer | Yes | documents | Character length of canonical body | Non-negative; 64,400 in first sorted example | Offset boundary errors |
| `section_count` | integer | Yes | documents | Parsed section count | Non-negative | Parser under/over-segmentation |
| `paragraph_count` | integer | Yes | documents | Parsed paragraph count | Non-negative | Parser under/over-segmentation |
| `document_genre` | string | Yes | documents | Rule-derived document genre | Observed: `primary_research`, `review`, `perspective`, `computational_study`, `process_or_tea`, `mixed`, `unclear` | Genre errors propagate to primary eligibility |
| `document_genre_confidence` | string | Yes | documents | Confidence category | Observed: `low`, `medium`, `high` | Not calibrated probability |
| `document_genre_signals` | array of strings | Yes | documents | Signals supporting genre decision | May be empty | Signal ambiguity |
| `document_reaction_family` | string | Yes | documents | Cached document-level reaction family | Observed: `eNRR`, `LiNRR`, `NO3RR`, `NO2RR`, `NORR`, `mixed`, `unclear` | Family leakage |
| `document_reaction_family_confidence` | string | Yes | documents | Family confidence category | Observed: `medium`, `high`, `unclear` | Not calibrated probability |
| `document_reaction_family_signals` | array of strings | Yes | documents | Signals supporting family decision | May be empty | Conflicting local evidence |
| `document_reaction_family_conflict` | boolean | Yes | documents | Structured/text or signal conflict flag | `true` or `false` | A missed conflict can affect primary eligibility |
| `front_matter_signals` | array | Yes | documents | Parsed front-matter cues used for document assessment | May be empty; context only | Front matter mistaken for positive evidence |
| `document_warnings` | array of strings | Yes | documents | Ledger/parser warnings for the document | May be empty | Ignored warnings |
| `document_assessment_call_count` | integer | No; emitted | documents | Audit counter for cached document assessment | `1` for every real-run document | Reassessment/per-span drift if not one |

## SourceNodeRecord

| Field | Expected type | Required | Source stage | Meaning | Allowed values / constraints | Review risk |
|---|---|---:|---|---|---|---|
| `source_node_id` | string | Yes | source_nodes | Stable paragraph-node ID | `CRN15_` plus 20 uppercase hex characters | Duplicate identical-body instances |
| `paper_id` | string | Yes | source_nodes | Owning paper | Must resolve to one document | Cross-paper mapping |
| `document_id` | string | Yes | source_nodes | Owning document | Must resolve to document ledger | Orphan node |
| `section_uid` | string | Yes | source_nodes | Parsed section identity | Non-empty | Parser hierarchy error |
| `paragraph_uid` | string | Yes | source_nodes | Parsed paragraph identity | Non-empty | Context-neighbor error |
| `source_start_offset` | integer | Yes | source_nodes | Inclusive body offset | `>= 0` and `< source_end_offset` | Off-by-one error |
| `source_end_offset` | integer | Yes | source_nodes | Exclusive body offset | `<= document_character_count` | Off-by-one error |
| `source_locator` | string | Yes | source_nodes | Human-auditable document/section/paragraph locator | Repository-relative logical locator; no absolute path | Locator/offset disagreement |
| `source_order_key` | string | Yes | source_nodes | Stable lexical order key | Structured zero-padded key | Ordering drift |
| `raw_heading` | string | Yes | source_nodes | Source heading text | Empty allowed; 357 empty in real run | Missing boundary context |
| `direct_section_type` | string | Yes | source_nodes | Direct heading classification | Observed: `abstract`, `introduction`, `methods`, `results`, `results_and_discussion`, `discussion`, `conclusion`, `references`, `supplementary`, `unknown` | Section misclassification |
| `effective_section_type` | string | Yes | source_nodes | Inherited/effective section classification | Same observed categories as direct type | Incorrect inheritance |
| `document_region` | string | Yes | source_nodes | Coarse document region | Observed: `abstract`, `main_body`, `references`, `supplementary`, `unknown` | Boundary leakage |
| `source_text` | string | Yes | source_nodes | Exact paragraph anchor text | Non-empty in real run; length must equal end minus start | Full-text handling and offset integrity |
| `source_text_sha256` | string | Yes | source_nodes | Hash of `source_text` | SHA-256 hex | Text/hash mismatch |
| `provenance_type` | string | Yes | source_nodes | Evidence-source class | Observed: `primary_body`, `background`, `reference`, `figure_or_scheme_caption`, `review_table`, `front_matter`, `secondary_document_body` | Low-trust source promoted to primary |
| `maximum_support_role` | string | Yes | source_nodes | Maximum allowed evidentiary role | `primary_support`, `context_only`, `non_evidence` | Primary-support leakage |
| `previous_paragraph_uid` | string or null | No; emitted | source_nodes | Previous paragraph within document | Null at boundary | Cross-section context assumptions |
| `next_paragraph_uid` | string or null | No; emitted | source_nodes | Next paragraph within document | Null at boundary | Cross-section context assumptions |

## CandidateSpanRecord

| Field | Expected type | Required | Source stage | Meaning | Allowed values / constraints | Review risk |
|---|---|---:|---|---|---|---|
| `cleanroom_span_id` | string | Yes | candidates | Stable exact-anchor identity | `CR15_` plus 20 uppercase hex characters | Collision on duplicate content instances |
| `source_node_id` | string | Yes | candidates | Parent paragraph node | Must resolve in source-node ledger | Orphan span |
| `paper_id` | string | Yes | candidates | Owning paper | Must match parent node | Cross-paper mapping |
| `document_id` | string | Yes | candidates | Owning document | Must match parent node | Cross-document mapping |
| `candidate_kind` | string | Yes | candidates | Highest-priority trigger family, not semantic claim type | Observed: `quantification_signal`, `validation_signal`, `performance_signal`, `reactor_signal`, `process_signal`, `energy_boundary_signal`, `product_state_signal`, `control_signal`, `general_ammonia_context` | Trigger mistaken for conclusion |
| `source_start_offset` | integer | Yes | candidates | Inclusive candidate offset | Inside exactly one parent node | Cross-paragraph span |
| `source_end_offset` | integer | Yes | candidates | Exclusive candidate offset | Greater than start; inside parent node | Cross-paragraph span |
| `source_locator` | string | Yes | candidates | Parent locator plus `CRANCHOR:start-end` | Logical, not absolute | Locator/offset disagreement |
| `source_order_key` | string | Yes | candidates | Stable source ordering plus offsets | Lexically sortable | Traversal-order drift |
| `source_text` | string | Yes | candidates | Exact node-text slice | Maximum configured size 3,000 characters | Treating excerpt as full-document conclusion |
| `source_text_sha256` | string | Yes | candidates | Hash of exact candidate text | SHA-256 hex | Text/hash mismatch |
| `trigger_signals` | array of strings | Yes | candidates | All trigger families matched | Non-empty | Recall/precision tradeoff |
| `candidate_score` | number | Yes | candidates | Recall-priority heuristic score | Current formula capped at 1.0 | Not a calibrated probability |
| `candidate_priority` | integer | Yes | candidates | Trigger precedence index plus one | Positive integer | Mistaken as evidence strength |
| `generation_method` | string | Yes | candidates | Window construction method | Observed: `whole_source_node`, `bounded_sentence_window` | Sentence splitting artifacts |
| `legacy_source_span_id` | string | No; emitted | candidates | Deliberately blank compatibility boundary | Empty in all 8,837 records | Accidental legacy linkage |
| `document_genre` | string | No; emitted | candidates | Cached document genre | Same as DocumentRecord | Stale cache |
| `document_reaction_family` | string | No; emitted | candidates | Cached family | Same as DocumentRecord | Stale cache |
| `document_reaction_family_signals` | array | No; emitted | candidates | Cached family signals | May be empty | Signal overinterpretation |
| `provenance_type` | string | No; emitted | candidates | Inherited node provenance | Same as SourceNodeRecord | Low-trust promotion |
| `maximum_support_role` | string | No; emitted | candidates | Inherited evidence ceiling | Same as SourceNodeRecord | Low-trust promotion |
| `raw_heading` | string | No; emitted | candidates | Inherited heading | Empty allowed | Missing context |
| `direct_section_type` | string | No; emitted | candidates | Inherited direct section | Source-node categories | Boundary error |
| `effective_section_type` | string | No; emitted | candidates | Inherited effective section | Source-node categories | Boundary error |
| `document_region` | string | No; emitted | candidates | Inherited region | Source-node categories | Boundary error |
| `paragraph_uid` | string | No; emitted | candidates | Parent paragraph UID | Non-empty | Mapping error |
| `section_uid` | string | No; emitted | candidates | Parent section UID | Non-empty | Mapping error |

## SemanticSpanRecord

The semantic record carries all candidate fields forward. The table below covers every semantic-specific required field and the important inherited/derived non-required fields used for audit and aggregation.

| Field | Expected type | Required | Source stage | Meaning | Allowed values / constraints | Review risk |
|---|---|---:|---|---|---|---|
| `cleanroom_span_id` | string | Yes | semantics | Preserved candidate identity | Must equal originating candidate ID | Identity drift |
| `source_node_id` | string | Yes | semantics | Preserved source-node identity | Must resolve | Orphan semantic record |
| `paper_id` | string | Yes | semantics | Owning paper | Must match candidate/node | Cross-paper leakage |
| `document_id` | string | Yes | semantics | Owning document | Must match candidate/node | Cross-document leakage |
| `document_genre` | string | Yes | semantics | Cached document genre | DocumentRecord categories | Genre leakage |
| `document_reaction_family` | string | Yes | semantics | Cached document family | DocumentRecord families | Family leakage |
| `effective_reaction_family` | string | Yes | semantics | Local high-confidence family if explicit, otherwise cached family | Observed: `eNRR`, `LiNRR`, `NO3RR`, `NO2RR`, `NORR`, `mixed`, `unclear` | Forced classification or incorrect override |
| `span_claim_scope` | string | Yes | semantics | Scope of the exact anchor | Observed: `target_document`, `external_or_cited_work`, `background_or_review`, `secondary_context`, `unclear` | Scope inversion |
| `document_scope` | string | Yes | semantics | Document-aware scope decision | Same observed categories | Scope inversion |
| `claim_ownership` | string | Yes | semantics | Owner of the claim | Observed: `target_authors`, `external_or_cited_authors`, `general_literature`, `secondary_context`, `unclear` | External claim attributed to target authors |
| `semantic_claim_type` | string | Yes | semantics | Rule-derived semantic type | Observed: `performance_result_claim`, `performance_context_claim`, `ammonia_quantification_claim`, `validation_claim`, `reactor_claim`, `process_claim`, `protocol_claim`, `mechanism_claim`, `gas_purification_or_capture_claim`, `secondary_context_claim`, `untyped_claim` | Type error propagates to eligibility |
| `semantic_claim_type_confidence` | string | Yes | semantics | Type confidence category | `low`, `medium`, `high` | Not a calibrated probability |
| `performance_result_evidence` | boolean | Yes | semantics | Target reaction outcome plus result-bearing evidence | `true` or `false` | Non-ammonia activity treated as ammonia performance |
| `quantitative_performance_evidence` | boolean | Yes | semantics | Quantitative performance support | `true` or `false` | Numeric context mistaken for result |
| `target_ammonia_reaction_outcome_anchor` | boolean | Yes | semantics | Explicit target ammonia reaction/outcome anchor | `true` or `false` | Off-target primary support |
| `ammonia_quantification_signal` | boolean | Yes | semantics | Analytical ammonia measurement signal | `true` or `false` | Trap/handling confused with quantification |
| `gas_purification_trap_signal` | boolean | Yes | semantics | Gas handling, trapping, or capture signal | `true` or `false` | Trap-only evidence promoted |
| `validation_gate_decisions` | object | Yes | semantics | Per-gate `satisfied`, source, signals, and conflict | Eleven named gates in current profile | Structured/text conflict missed |
| `primary_semantic_eligibility` | boolean | Yes | semantics | True only when no hard-gate failure exists | `true` or `false`; 348 true in real run | Mistaken for scientific truth |
| `hard_gate_failures` | array of strings | Yes | semantics | Explicit failed primary gates | Empty iff primary eligible in current implementation | Missing failure explanation |
| `semantic_warnings` | array of strings | Yes | semantics | Context/provenance warnings | May be empty | Ignored warning |
| `needs_review` | boolean | Yes | semantics | Explicit unresolved uncertainty/conflict indicator | `true` or `false`; 7,113 true in real run | Mistaken for an adverse human label |
| `needs_review_reasons` | array of strings | Yes | semantics | Reasons for review escalation | May be empty | Incomplete uncertainty taxonomy |
| `source_start_offset` | integer | No; inherited/emitted | candidates | Exact inclusive anchor | Inside parent node | Offset error |
| `source_end_offset` | integer | No; inherited/emitted | candidates | Exact exclusive anchor | Inside parent node | Offset error |
| `source_locator` | string | No; inherited/emitted | candidates | Logical exact locator | No absolute path | Locator leak/drift |
| `source_text` | string | No; inherited/emitted | candidates | Exact bounded anchor | Not a standalone full-document conclusion | Overgeneralization |
| `source_text_sha256` | string | No; inherited/emitted | candidates | Anchor hash | SHA-256 hex | Text/hash mismatch |
| `maximum_support_role` | string | No; inherited/emitted | source_nodes | Evidence ceiling | `primary_support`, `context_only`, `non_evidence` | Low-trust primary |
| `provenance_type` | string | No; inherited/emitted | source_nodes | Source class | SourceNodeRecord categories | Low-trust primary |
| `effective_reaction_family_source` | string | No; emitted | semantics | Family decision source | Observed: `cached_document_assessment`, `cached_document_uncertainty`, `explicit_high_confidence_target_span` | Local/document override ambiguity |
| `document_target_reaction_family_conflict` | boolean | No; emitted | semantics | Explicit local/document family conflict | `true` or `false` | Missed conflict |
| `target_explicit_reaction_family` | string | No; emitted | semantics | Explicit local family or `unclear` | Supported families plus `unclear` | False local override |
| `semantic_outcome` | string | No; emitted | semantics | Operational outcome after gates | `primary_eligible`, `secondary_context`, `needs_review`, `unsupported` | Confusing outcome with human judgment |
| `semantic_claim_type_score` | integer | No; emitted | semantics | Ordinal confidence score used for paper ranking | Current mapping 0–3 | Mistaken as probability |
| `structured_gate_text_conflict` | boolean | No; emitted | semantics | Any structured/text gate conflict | `true` or `false` | Conflict leakage |
| `structured_quantification_present` | boolean | No; emitted | semantics | Structured quantification cue | `true` or `false` | Structured field trusted without text |
| `mass_spectrometry_quantification_signal` | boolean | No; emitted | semantics | Method-specific quantification cue | `true` or `false` | Method presence mistaken for valid result |
| `enzymatic_quantification_signal` | boolean | No; emitted | semantics | Method-specific quantification cue | `true` or `false` | Method presence mistaken for valid result |
| `non_ammonia_reaction_activity` | boolean | No; emitted | semantics | Off-target activity cue | `true` or `false` | Off-target primary error |
| `legacy_claim_type` | string | No; emitted | semantics | Deliberately blank legacy boundary | Empty in all real-run records | Accidental legacy import |
| `legacy_reaction_family` | string | No; emitted | semantics | Deliberately non-informative legacy boundary | `unclear` in current output | Accidental legacy import |
| `semantic_eligibility_schema_version` | string | No; emitted | semantics | Version of semantic-eligibility rules | Explicit version from classifier | Version mixing |

## EvidenceLinkRecord

Evidence links are emitted as a stable runtime record, but `REQUIRED_FIELDS` does not currently declare a formal `evidence_link` entry. “Emitted” below means present in all 1,013 real-run rows; this gap is finding P2-1 in the architecture audit.

| Field | Expected type | Required | Source stage | Meaning | Allowed values / constraints | Review risk |
|---|---|---:|---|---|---|---|
| `schema_version` | string | Emitted | links | Clean-room schema | `0.15-cleanroom.1` | Unvalidated version drift |
| `pipeline_profile` | string | Emitted | links | Behavior profile | `document_first_cleanroom_v1` | Profile mixing |
| `run_name` | string | Emitted | links | Runtime namespace | Safe run name | Run conflation |
| `record_created_by_stage` | string | Emitted | links | Creator stage | `links` | Stage drift |
| `evidence_link_id` | string | Emitted | links | Stable link identity | `CRL15_` plus 20 uppercase hex characters; unique/non-empty checked | Collision |
| `target_cleanroom_span_id` | string | Emitted | links | Result-bearing target endpoint | Must resolve to same-paper semantic span | Cross-paper or self-link |
| `evidence_cleanroom_span_id` | string | Emitted | links | Supporting/context endpoint | Must resolve to same-paper semantic span and differ from target | Cross-paper or self-link |
| `paper_id` | string | Emitted | links | Shared paper scope | Must equal both endpoint papers | Cross-paper support |
| `link_roles` | array of strings | Emitted | links | Evidence role(s) | `quantification_support`, `validation_support`, `gas_handling_context`, or fallback `context_hint` | Role overclaim |
| `link_score` | number | Emitted | links | Bounded source-distance score | Current floor 0.1; not causal/confidence probability | Causality inference |
| `link_signals` | array of strings | Emitted | links | Same-paper, distance, and role signals | Includes `same_paper` and `bounded_source_distance` | Same paper mistaken for causality |
| `source_eligibility` | string | Emitted | links | Endpoint source ceiling | `primary_admissible` or `context_only` | Context-only upgrade |
| `is_context_only` | boolean | Emitted | links | Context-only endpoint flag | `true` or `false` | Primary upgrade |
| `link_warnings` | array of strings | Emitted | links | Non-upgrade and context warnings | Always states link does not upgrade ownership/provenance | Ignored warning |

## PaperRecord

| Field | Expected type | Required | Source stage | Meaning | Allowed values / constraints | Review risk |
|---|---|---:|---|---|---|---|
| `paper_id` | string | Yes | papers | Paper identity | One record per DocumentRecord | Missing/duplicate paper |
| `document_id` | string | Yes | papers | Source document | Must resolve | Orphan paper |
| `document_genre` | string | Yes | papers | Cached genre | DocumentRecord categories | Genre propagation |
| `document_reaction_family` | string | Yes | papers | Cached family | DocumentRecord families | Family propagation |
| `document_conflicts` | array of strings | Yes | papers | Deduplicated document conflicts | May be empty | Conflict suppression |
| `candidate_span_count` | integer | Yes | papers | Candidate count for paper | Non-negative | Count mismatch |
| `semantic_span_count` | integer | Yes | papers | Semantic count for paper | Equals candidate count in current profile | Count mismatch |
| `primary_eligible_span_count` | integer | Yes | papers | Primary-eligible semantic count | Non-negative, no greater than semantic count | Eligibility inflation |
| `primary_claim_counts` | object | Yes | papers | Primary count by semantic type | Non-negative integer values | Secondary/primary mixing |
| `secondary_context_count` | integer | Yes | papers | `secondary_context` semantic outcomes | Non-negative | Context promoted as primary |
| `evidence_link_count` | integer | Yes | papers | Same-paper link count | Non-negative | Link-count mismatch |
| `validation_gate_summary` | object | Yes | papers | Per-gate satisfied counts among primary spans | Non-negative integers | Counts mistaken for adequacy |
| `quantification_summary` | object | Yes | papers | Primary quantification and trap-only counts | Non-negative integers | Trap/quantification confusion |
| `performance_summary` | object | Yes | papers | Primary result and quantitative-result counts | Non-negative integers | Result overclaim |
| `reactor_process_summary` | object | Yes | papers | Reactor/process span counts | Non-negative integers | Context/type errors |
| `paper_admissibility_status` | string | Yes | papers | Conservative engineering aggregation status | `not_evaluated`, `needs_review`, `insufficient_evidence`, `partially_supported`, `supported_with_limitations` | Mistaken for human/scientific verdict |
| `paper_admissibility_reasons` | array of strings | Yes | papers | Explainable status reasons | Non-empty in current implementation | Incomplete explanation |
| `best_evidence_span_ids` | array of strings | Yes | papers | Up to ten ranked primary span IDs | Stable same-paper IDs | Ranking mistaken for proof |
| `review_priority` | string | Yes | papers | Operational review priority | `high`, `medium`, or `normal` | Priority mistaken for quality |
| `paper_warnings` | array of strings | Yes | papers | Aggregation/scientific-limit warnings | Includes limited-aggregation and comparability warning | Ignored limitations |
| `document_record_id` | string | No; emitted | papers | Alias to document record | Equals `document_id` | Alias divergence |
| `document_ref` | string | No; emitted | papers | Repository-relative source reference | No absolute path | Path leakage |

## StageManifest

The stage manifest is an emitted object, not a `validate_record()` record type.

| Field | Expected type | Required | Source stage | Meaning | Allowed values / constraints | Review risk |
|---|---|---:|---|---|---|---|
| `schema_version` | string | Emitted top-level | orchestration | Manifest schema | `0.15-cleanroom.1` | Version drift |
| `pipeline_profile` | string | Emitted top-level | orchestration | Run profile | `document_first_cleanroom_v1` | Profile drift |
| `run_name` | string | Emitted top-level | orchestration | Run namespace | Safe run name | Run conflation |
| `stages` | object | Emitted top-level | orchestration | Map of all nine stage states | Keys: `ingest`, `documents`, `source_nodes`, `candidates`, `semantics`, `links`, `papers`, `review`, `validate` | Missing stage |
| `stage_name` | string | Emitted per stage | orchestration | Stage key echoed in state | One of nine stages | Key/value mismatch |
| `status` | string | Emitted per stage | orchestration | Lifecycle state | `not_started`, `running`, `completed`, `failed`, `invalidated` | Stale completed marker |
| `started_at` | string or null | Emitted per stage | orchestration | UTC start time | ISO-8601 or null | Runtime-specific value |
| `finished_at` | string or null | Emitted per stage | orchestration | UTC completion/failure time | ISO-8601 or null | Runtime-specific value |
| `input_files` | array of strings | Emitted per stage | orchestration | Immediate stage input paths | Run/input-relative | Incomplete dependency declaration |
| `input_sha256` | object | Emitted per stage | orchestration | Input hashes by relative path | SHA-256 values | Hash drift |
| `config_sha256` | string | Emitted per stage | orchestration | Canonical configuration hash | SHA-256 hex after completion | Config reuse error |
| `output_files` | array of strings | Emitted per stage | orchestration | Stage output paths | Run-relative | Missing output |
| `output_sha256` | object | Emitted per stage | orchestration | Output hashes by relative path | SHA-256 values | Corruption/stale output |
| `record_counts` | object | Emitted per stage | orchestration | Stage-specific counts | Non-negative diagnostic values | Count inconsistency |
| `warnings` | array of strings | Emitted per stage | orchestration | Stage warnings | May be empty | Ignored warning |
| `errors` | array of strings | Emitted per stage | orchestration | Stage errors | Empty on completed stage | Completed-with-error contradiction |
| `code_commit` | string | Emitted per stage | orchestration | Git commit recorded when manifest state initialized | Commit SHA or `unknown`; not currently a reuse gate | Cross-code resume |
| `schema_version` | string | Emitted per stage | orchestration | Stage schema | `0.15-cleanroom.1` | Version drift |
| `pipeline_profile` | string | Emitted per stage | orchestration | Stage profile | `document_first_cleanroom_v1` | Profile drift |

## FinalManifest

| Field | Expected type | Required | Source stage | Meaning | Allowed values / constraints | Review risk |
|---|---|---:|---|---|---|---|
| `schema_version` | string | Emitted | orchestration | Final schema | `0.15-cleanroom.1` | Version drift |
| `pipeline_profile` | string | Emitted | orchestration | Final profile | `document_first_cleanroom_v1` | Profile drift |
| `run_name` | string | Emitted | orchestration | Run namespace | Safe run name | Run conflation |
| `pipeline_status` | string | Emitted | orchestration | Overall lifecycle result | `running`, `partial`, `completed`, or `failed` | Stale success claim |
| `failed_stages` | array of strings | Emitted | orchestration | Failed-stage names | Empty on valid completion | Hidden failure |
| `completed_stages` | array of strings | Emitted | orchestration | Completed stages | All nine required for completed run | Partial run mistaken for complete |
| `created_at` | string | Emitted | orchestration | Manifest write timestamp | ISO-8601 UTC | Reproducibility noise |
| `stage_manifest` | string | Emitted | orchestration | Relative stage-manifest path | `manifests/stage_manifest.json` | Broken pointer |

## ReviewSampleRow

All fields are CSV strings on disk. JSON-like lists are canonical JSON strings; booleans serialize as text. The first 14 operational fields are emitted for review context. The six `human_*` fields are intentionally blank in all 130 real-run rows.

| Field | Expected type | Required | Source stage | Meaning | Allowed values / constraints | Review risk |
|---|---|---:|---|---|---|---|
| `run_name` | CSV string | Emitted | review | Run namespace | Safe run name | Run conflation |
| `cleanroom_span_id` | CSV string | Emitted | review | Review-unit span ID | Unique in sample | Duplicate review unit |
| `paper_id` | CSV string | Emitted | review | Owning paper | Same as semantic record | Cross-paper review |
| `document_ref` | CSV string | Emitted | review | Repository-relative source | No absolute path | Path leakage |
| `review_stratum` | CSV string | Emitted | review | Deterministic sampling stratum | Current `_review_stratum()` categories | Stratum mistaken for prediction truth |
| `target_text` | CSV string | Emitted | review | Exact target excerpt | Bounded candidate text, not full document | Excerpt insufficiency |
| `previous_paragraph` | CSV string | Emitted | review | Neighbor context | Empty only if unavailable | Context boundary |
| `following_paragraph` | CSV string | Emitted | review | Neighbor context | Empty only if unavailable | Context boundary |
| `linked_evidence_span_ids` | JSON-array CSV string | Emitted | review | Same-paper evidence IDs | May be `[]` | Link mistaken for causality |
| `paper_admissibility_status` | CSV string | Emitted | review | Current paper aggregation | Current status vocabulary | Automation treated as human label |
| `semantic_claim_type` | CSV string | Emitted | review | Current rule output | Semantic type vocabulary | Automation treated as human label |
| `effective_reaction_family` | CSV string | Emitted | review | Current rule output | Family vocabulary | Automation treated as human label |
| `primary_semantic_eligibility` | boolean CSV string | Emitted | review | Current hard-gate output | `True` or `False` serialization | Automation treated as human label |
| `needs_review` | boolean CSV string | Emitted | review | Current uncertainty output | `True` or `False` serialization | Mistaken for completed review |
| `human_scope_correct` | CSV string | Emitted blank | human audit | Reviewer judgment placeholder | Blank in release sample; protocol labels later | Premature label entry |
| `human_ownership_correct` | CSV string | Emitted blank | human audit | Reviewer judgment placeholder | Blank in release sample | Premature label entry |
| `human_claim_type_correct` | CSV string | Emitted blank | human audit | Reviewer judgment placeholder | Blank in release sample | Premature label entry |
| `human_family_correct` | CSV string | Emitted blank | human audit | Reviewer judgment placeholder | Blank in release sample | Premature label entry |
| `human_primary_eligibility_correct` | CSV string | Emitted blank | human audit | Reviewer judgment placeholder | Blank in release sample | Premature label entry |
| `human_notes` | CSV string | Emitted blank | human audit | Free-text reviewer notes placeholder | Blank in release sample | Personal/sensitive content if unmanaged |

## Identity stability contract

- `cleanroom_span_id = SHA-256(document_body_sha256, source_start_offset, source_end_offset, candidate_kind)` truncated to 20 uppercase hex characters with `CR15_` prefix.
- `source_node_id = SHA-256(document_body_sha256:start:end)` truncated with `CRN15_` prefix.
- `evidence_link_id = SHA-256(paper_id, target_cleanroom_span_id, evidence_cleanroom_span_id)` over canonical JSON, truncated with `CRL15_` prefix.
- Run name, absolute path, ranking, and traversal order are excluded.
- Changing an offset, candidate kind, document content hash, paper scope, or link endpoint changes the applicable identity.
- Duplicate IDs are diagnostics and fail the validated run; identical full document bodies remain an explicit duplicate-instance limitation.

## Null and empty-string conventions

- JSON uses `null` for unavailable neighboring paragraph UIDs at document boundaries.
- Empty arrays/objects mean no observed signals, warnings, failures, links, or counts in that category; they do not mean that a reviewer verified absence.
- Candidate `legacy_source_span_id` and semantic `legacy_claim_type` are deliberately empty strings. They must not be populated from legacy runtime outputs.
- Review `human_*` fields are empty strings until a governed human-audit export is created. Blank means “not reviewed,” not `no`, `uncertain`, or `not_applicable`.
- CSV serialization writes `None` as an empty cell and arrays/objects as canonical JSON strings.

## Reported versus inferred semantics

- Source text, offsets, hashes, locators, trigger matches, and parsed document structure are reported/extracted engineering data.
- Genre, reaction family, scope, ownership, claim type, validation-gate decisions, primary eligibility, `needs_review`, link roles, and paper status are rule-inferred outputs.
- A reported numeric phrase is not automatically quantitative performance evidence. A detected analytical method is not automatically valid ammonia quantification.
- A same-paper evidence link reports a bounded association; it does not prove causality, ownership, or sufficiency.
- Paper status is a conservative aggregation, not a human or scientific verdict.

## Fields not yet supported

- No completed human labels are part of schema `0.15-cleanroom.1`.
- No calibrated probability, corpus-wide precision/recall, inter-reviewer agreement, or adjudication status is emitted.
- No scientific comparability, normalized experimental-condition comparison, plant viability, or benchmark-release decision is implemented.
- EvidenceLinkRecord, StageManifest, FinalManifest, and ReviewSampleRow lack complete `REQUIRED_FIELDS` plus type validation in the current validator.
- No implementation fingerprint is enforced during resume beyond the recorded but unchecked `code_commit`.

## Backward compatibility boundary

Schema `0.15-cleanroom.1` and profile `document_first_cleanroom_v1` are independent additions. They do not replace, rewrite, or change audit schema `0.13` or its default export behavior. Existing `source_span_id` values are not rewritten; the new pipeline uses independent `CR15_`, `CRN15_`, and `CRL15_` identities. Any future incompatible behavior requires an explicit profile or independent schema version.
