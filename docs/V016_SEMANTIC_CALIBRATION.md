# v0.16 Phase A — Semantic Calibration Infrastructure

## Scope and safety boundary

Phase A adds a calibration-data layer over an already completed v0.15 clean-room run. It does not change clean-room classification, eligibility, paper aggregation, or schema `0.15-cleanroom.1`. The authoritative input is exactly one child of `data/cleanroom/`; the builder reads only the document ledger, source nodes, candidates, semantic spans, evidence links, paper records, final manifest, and clean-room validation summary listed in the calibration manifest.

The builder never reads legacy Stage B samples, evidence bundles, context packets, claim-rights runtime, old human audit exports, PR review artifacts, or AI-generated labels. It makes no LLM or external API call. It does not train a model, change rules, or claim scientific accuracy. Source clean-room data and Gold are read-only and are protected by before/after tree hashes.

## Version and identities

- Schema: `0.16-calibration.1`
- Profile: `human_semantic_calibration_round1_v1`
- Sampling algorithm: `v016-deterministic-strata-v1`

The schema defines `CalibrationManifest`, `CalibrationSpanItem`, `CalibrationPaperItem`, `CalibrationDocumentItem`, `CalibrationLinkItem`, `CalibrationReviewRow`, `CalibrationAdjudicationRow`, `CalibrationSummary`, and `CalibrationMetricSummary` record families.

Calibration item IDs use SHA-256 over canonical JSON containing the calibration schema version and the stable underlying ID. They are independent of run name, absolute path, traversal order, sample order, CSV row, time, and Python's built-in hash:

- span: `CC16S_<digest>` from `cleanroom_span_id`;
- paper: `CC16P_<digest>` from `paper_id`;
- document: `CC16D_<digest>` from `document_id`;
- link: `CC16L_<digest>` from `evidence_link_id`.

The v0.15 `CRN15_`, `CR15_`, and `CRL15_` identities remain unchanged and are retained as source references.

## Deterministic span sampling

For every semantic span, the sampler derives all matching strata from existing structured clean-room fields. A span is assigned to the first matching stratum in this fixed priority order; nonmatching records enter the high-risk reservoir.

| Priority | Primary stratum | Round-1 quota | Structured definition |
|---:|---|---:|---|
| 1 | `primary_performance` | 50 | primary eligible and `performance_result_claim` |
| 2 | `quantification` | 40 | quantification signal or quantification claim type |
| 3 | `validation` | 40 | validation claim or a satisfied validation gate |
| 4 | `reactor_process` | 25 | reactor or process claim type |
| 5 | `external_cited_claim` | 30 | external/cited or general-literature ownership |
| 6 | `review_perspective` | 20 | review or perspective document genre |
| 7 | `off_target` | 20 | observed LiNRR, NO2RR, NO3RR, or NORR effective family |
| 8 | `trap_only` | 20 | gas-trap signal without ammonia-quantification signal |
| 9 | `unclear_mixed_family` | 35 | unclear/mixed effective or document family |
| 10 | `structured_text_conflict` | 20 | structured gate, claim-type, or document-family conflict |

Within a stratum, ordering is the SHA-256 of `seed + schema + stable underlying ID`. A shortage selects every available record and is written as requested/available/selected/shortage; the remaining target is filled without duplication from unselected records ordered by an explicit risk score and stable sampling hash. A fill item retains its field-derived `assigned_primary_stratum`; `selection_stratum=high_risk_reservoir` records how it entered the sample. If fewer total semantic spans exist than requested, the build fails closed. Fixture-sized requests below 300 scale the published quotas proportionally with a deterministic largest-remainder rule; the production 300-item run uses the table verbatim.

## Paper, document, and link sampling

Paper sampling is independent of the span sample. It discovers the actual reaction-family, genre, and paper-status values in the source run, ensures observed family coverage, takes rare combinations first, and then uses deterministic round-robin fill. Each sampled paper must resolve to one unique document review unit. Ambiguous or insufficient paper/document mappings fail closed.

Link sampling first enforces resolvable same-paper endpoints, no self-links, and unique endpoint pairs. Its composite strata include link role, target/evidence claim types, target primary eligibility, evidence source eligibility/provenance, source-distance band, and needs-review state. Rare strata are selected by deterministic round robin. If fewer valid links exist than requested, every valid link is retained and the explicit shortage is a package warning; links are never fabricated.

## Human review labels

The only correctness labels are `yes`, `no`, `uncertain`, and `not_applicable`. Generated `reviewer_id`, `review_status`, every `human_*` label, notes, and every adjudication field are empty. `review_status` is not prefilled. A future completed row requires a reviewer and all applicable correctness fields. `no` or `uncertain` requires reviewer notes. `pass`/`fail` and any other label are rejected.

Generated review sheets are blank templates. They are not completed human audit records. No automatic output, AI audit, or rule result is copied into human fields.

## Bounded context

Scientific text is copied exactly and only truncated; it is never rewritten or summarized. Truncation adds `[bounded excerpt truncated]` inside the stated limit.

- target and linked-evidence excerpts: at most 700 characters;
- preceding and following context: at most 500 characters each;
- document front matter: at most 700 characters;
- link target and evidence excerpts: at most 700 characters each.

Preceding/following context resolves through adjacent v0.15 source nodes in the same paper and document. Source locator and exact offsets remain present. The package contains no complete document, PDF bytes, full-text Markdown, absolute input path, or cross-paper evidence context.

## Package layout

Each runtime is an ignored child of `data/calibration/<calibration_run_name>/`:

```text
manifests/calibration_manifest.json
sampling/{span,paper,document,link}_sampling_frame.jsonl
review/{span,paper,document,link}_review.csv
review/adjudication_template.csv
reports/calibration_summary.json
reports/stratum_coverage.csv
reports/validation_summary.json
reports/calibration_metrics_template.json
previews/calibration_preview.md
```

A completed base package must contain exactly those fifteen files. The only declared post-review addition is `reports/calibration_metrics_summary.json`. Any other attachment is rejected; binary files and extra Markdown are never silently skipped.

The preview contains only five span, three paper, three document, and three link examples. It explicitly states that labels are blank, the preview is not a completed audit, and the sample does not establish corpus-wide precision.

## Validation and reproducibility

`scripts/check_calibration_package.py` recomputes calibration IDs and sampling hashes; validates required fields, schema/profile, labels, source IDs, offsets and source-node slices, exact authoritative adjacency, every same-paper linked-evidence endpoint, excerpt limits, counts, shortages, input/output hashes, and paper/document alignment; and scans for absolute/user paths, secrets, full-document fields, duplicates, and nonblank human/adjudication fields. Review rows are aligned to sampling frames by calibration item ID. Only the declared human fields may change; every automatic value is schema-aware decoded from CSV and compared to its typed JSONL value. A completed manifest is permitted only after source manifest completion, source validation PASS, required sample counts, zero unresolved/duplicate IDs, zero unsafe embeddings/paths/labels, and zero validation errors.

Output integrity avoids a recursive manifest/summary dependency. During construction, a `building` manifest is paired with an explicit `PENDING` validation summary. Successful validation produces a final `PASS` summary; its SHA-256 is stored in the completed manifest and the summary is also included in `output_file_hashes`. The manifest excludes only its own bytes. Review CSV byte hashes remain provenance records but are not enforced after generation because human fields are intentionally mutable; deletion, extra rows, duplicate observations, schema changes, and automatic-field tampering are instead detected structurally against immutable sampling frames. Missing or unexpected files are independently rejected by the strict package inventory.

The builder refuses to overwrite any existing package unless `--clean` is explicit. Cleaning accepts only an exact child of the calibration root, rejects reserved/traversal/current-directory and symlink/junction targets, protects siblings and clean-room data, and uses an exclusive run lock. `--dry-run` performs no deletion or build.

Reproducibility comparison removes only `calibration_run_name` and timestamps, then hashes the four sampling frames and four review sheets. With identical source, seed, schema, profile, and sizes, different run names must have identical normalized hashes.

## Metrics and adjudication

Phase A reports completeness, label distributions, uncertain/not-applicable rates, reviewer agreement, Cohen's kappa, correctness counts, and per-stratum error rates. Row completeness is completed review rows divided by total review rows. Item coverage is the number of unique items with at least one completed reviewer divided by total unique items. Reviewer coverage separately reports reviewer count and row/completed-row counts per reviewer. With blank labels the inferential metrics are `null`/`not_available`, with missing rows and items reported. It never fabricates or mixes denominators.

The audit mapping covers document genre, reaction family, claim ownership, claim type, primary eligibility, quantification, validation, paper status, and link relevance/role. A human `yes` means that an automatic assertion is correct; it does not mean that the underlying automatic class is the class `yes`. Therefore correctness precision is reported separately, while class-label recall and macro-F1 remain unavailable until corrected class labels exist. The metrics CLI optionally accepts explicit predicted/corrected class pairs for multiclass precision, recall, confusion counts, and macro-F1.

The adjudication template reserves reviewer summaries, disagreements, adjudicator identity/status, adjudicated correctness, `corrected_label`, and notes. It performs no automatic adjudication.

## Round-1 manual workflow

1. Build the package from a completed, validated v0.15 clean-room run.
2. Run the independent package validator with `--require-blank-human-fields` before distribution.
3. Assign reviewers without altering source or automatic fields.
4. Review bounded items and fill only the designated human fields; document every `no` or `uncertain` decision.
5. Import independent reviewer copies without collapsing duplicate reviewer observations.
6. Summarize completeness and agreement; adjudicate disagreements manually in a separate copy.
7. Compute correctness and, only where explicit corrected labels exist, class-label metrics.
8. Treat rule-calibration or Gold promotion as a separate future phase.

No calibration metric is valid until human review and adjudication are completed. Promotion to Gold requires a separate integrity-baseline update and explicit user approval. Blank templates, sampled records, and adjudication placeholders are never Gold.
