# v0.15 Release Readiness

## Repository state

- Branch: `feature/v015-cleanroom-pipeline`
- HEAD before audit-package commit: `ab8235b1f825a63c3175fd4b9f4d46f6dae48986`
- Pull request: `#2`, `feature/v015-cleanroom-pipeline` → `review/v014-stage-b-context`
- Base commit observed locally: `72f5b4db9b28f347761011b43c5d324cc8b7fafa`
- Pull request state: Draft.
- Implementation commits above base before the audit-package commit: 3.
- Implementation changed files above base before the audit-package commit: 24, comprising 5 implementation modules, 2 scripts, 13 test/helper files, and 4 documentation/runtime-boundary files. Publication adds this seven-file documentation package in a separate fourth commit.
- Local/remote branch parity at audit start: ahead 0, behind 0; both resolved to the stated HEAD after `git fetch origin`.
- GitHub Actions run `29642293198`: PASS.
  - Python 3.10 job: PASS.
  - Python 3.13 job: PASS.
  - Checkout, Python setup, installation, `pip check`, compileall, unittest, and authoritative Gold availability reporting: PASS in both jobs as applicable.
  - Remote exact Gold integrity: SKIPPED BY DESIGN because the authoritative Gold is local-only and intentionally not committed.

Changed-file inventory above base:

```text
.gitignore
README.md
data/cleanroom/.gitkeep
docs/V015_CLEANROOM_PIPELINE.md
enh3bench/cleanroom_candidates.py
enh3bench/cleanroom_output_check.py
enh3bench/cleanroom_pipeline.py
enh3bench/cleanroom_schema.py
enh3bench/paper_aggregation.py
scripts/check_cleanroom_outputs.py
scripts/run_cleanroom_pipeline.py
tests/cleanroom_test_helpers.py
tests/test_cleanroom_candidate_generation.py
tests/test_cleanroom_cli.py
tests/test_cleanroom_manifest.py
tests/test_cleanroom_no_legacy_dependency.py
tests/test_cleanroom_output_check.py
tests/test_cleanroom_paper_aggregation.py
tests/test_cleanroom_pipeline.py
tests/test_cleanroom_pipeline_clean.py
tests/test_cleanroom_pipeline_resume.py
tests/test_cleanroom_reproducibility.py
tests/test_cleanroom_schema.py
tests/test_cleanroom_span_identity.py
```

## Local verification

### Code and tests

- `python -m compileall enh3bench scripts`: PASS locally.
- `python -m unittest discover`: 640 tests, OK locally.
- These local results and the verified remote jobs are separate evidence layers.

### Exact Gold integrity

| Artifact | Record count | SHA-256 | Result |
|---|---:|---|---|
| Authoritative Gold JSONL | 100 | `D6D39C6908A281D36F2DF20A4F5876B7E91DF87FDBBAD5C7C499A4D2655D236D` | PASS |
| Authoritative Gold CSV | 100 | `1087068AF6A8E5BEA9F3273FE3C439CE3BA1B20711D9C6E64B5661EB564AFAEF` | PASS |

`git diff --name-only -- data/gold` is empty. No Gold file was edited.

### Real clean-room run

- Run: `data/cleanroom/enrr_cleanroom_v015_20260718/`
- Profile: `document_first_cleanroom_v1`
- Schema: `0.15-cleanroom.1`
- Output checker: PASS, 0 errors, 0 warnings.

| Runtime measure | Observed |
|---|---:|
| Documents | 203 |
| Source nodes | 25,193 |
| Candidate spans | 8,837 |
| Semantic spans | 8,837 |
| Primary-eligible spans | 348 |
| Needs-review spans | 7,113 |
| Unclear-family spans | 3,481 |
| Evidence links | 1,013 |
| Paper records | 203 |
| Paper status `needs_review` | 203 |
| Review sample rows | 130 |

### Resume and reproducibility

- Resume run `enrr_cleanroom_v015_resume_release` validated PASS and matched the primary run for all six normalized output sets.
- The candidate output retained SHA-256 `4D2A22DCC1660D01B9BF3DA40188ED00997CAAA102AC040928281EA8D12A98CE`, byte length 24,037,060, and its recorded modification time across the partial-to-resume check.
- Independent runs `enrr_cleanroom_v015_release_repro_a` and `enrr_cleanroom_v015_release_repro_b` both validated PASS and reported `reproducibility_match: true`.

| Normalized output | Matching SHA-256 |
|---|---|
| Documents | `8813087f0678133a79a144bf38a9f2c01e8e1990a65ea6b394fbf36289d85c32` |
| Source nodes | `b66f98be9c69bb1a4f9d6ae9f4887ebf6732d15fe764db7f4253b731e15b0fed` |
| Candidate spans | `3eac4009024629f4520cc1e5c89d62eabb2e58c804ca8c2aaceb5e7741ce392b` |
| Semantic spans | `39a862834a9f33f4ca28b14636f75c78585e0ef39f33f1f40b1e624ab9898c3c` |
| Evidence links | `f259d9ace7e1ecd4fc13c1b8936e615a41b2e9695fb0689ad401b248c630eb81` |
| Paper records | `989792cdd37ee45af5cd10f665181f9791000dcd9449459d27bd23dda6bc698c` |

### Safety and review-sample diagnostics

All of the following real-run diagnostics are zero:

- duplicate document, source-node, clean-room span, evidence-link ID, link-pair, and review-sample IDs;
- unresolved source mappings, invalid offsets, and cross-paragraph candidates;
- cross-paper links, self-links, and context-only primary upgrades;
- reference, caption, or review-table primary support;
- absolute runtime paths in exports;
- completed manifest with a failed/incomplete stage;
- filled human review fields; and
- full-document embedding in review rows.

No real LLM or external API call was made during implementation verification or this audit preparation.

## Engineering gates

| Gate | Required | Observed | Status | Evidence |
|---|---|---|---|---|
| Clean-room legacy isolation | Normal path independent of legacy runtime semantics | No legacy candidates, bundles, claim-rights, provenance, or context packets are read; explicit compare mode is report-only | PASS | `enh3bench/cleanroom_pipeline.py`; `tests/test_cleanroom_no_legacy_dependency.py` |
| Document-first input | New Markdown/ledger is authoritative | Ingest and fresh `OrderedSourceLedger` lead every stage | PASS | `_stage_ingest()`, `_build_ledger()` |
| One assessment per document | Genre/family cached once | 203 documents and assessment count 203; every record has call count 1 | PASS | `_stage_documents()` and real ledger |
| Stable IDs | Deterministic and run/path/order independent | CR15/CRN15/CRL15 constructors exclude run/path/order; normalized runs match | PASS WITH LIMITATION | `cleanroom_schema.py`; duplicate identical documents fail closed but are not disambiguated |
| Exact offsets | Bounded exact evidence anchors | Invalid offset 0, cross-paragraph 0, unresolved mapping 0 | PASS WITH LIMITATION | Checker verifies node bounds/length and candidate node-slice; it does not re-slice original Markdown |
| Same-paper links | No cross-paper evidence | Cross-paper 0 | PASS | Link construction and output checker |
| No self links | Target differs from evidence | Self-link 0 | PASS | Link diagnostics |
| Paper-record completeness | One record per document, including no-candidate documents | 203 documents and 203 paper records | PASS | `aggregate_paper_records()` and checker |
| Resume integrity | Reuse only verified unchanged stage output | Resume run matches primary run across six normalized outputs | PASS WITH LIMITATION | Code commit is recorded but not a reuse predicate |
| Atomic writes | Existing destination preserved on failed replace | Temporary-file, flush/fsync, replace/retry; failure test passes | PASS | `atomic_write_text()`, `write_csv()`, schema tests |
| Clean safety | Exact child only; protect roots, siblings, links, active runs | Target validation and dedicated tests cover all required refusal cases | PASS | `resolve_clean_target()`, clean tests |
| Runtime isolation | Outputs excluded from commit and absolute paths | Runtime gitignored; absolute path diagnostic 0 | PASS | `.gitignore`, checker |
| Gold immutability | No Gold change and exact hashes retained | Diff empty; both expected hashes/counts pass | PASS | Exact Gold integrity check |
| Review fields blank | No premature human label | 130 rows; filled human-field count 0 | PASS | Review CSV and checker |
| No real LLM/API | No call without authorization | No call made | PASS | Execution boundary for this work |

## Scientific gates

| Gate | Current status | Reason |
|---|---|---|
| Human semantic precision | pending | No governed human labels exist |
| Paper-status accuracy | pending | All 203 statuses are automated conservative aggregations |
| Reaction-family macro-F1 | pending | No adjudicated calibration/evaluation set |
| Quantification precision | pending | No adjudicated labels |
| Validation precision | pending | No adjudicated labels |
| Scientific comparability | not implemented | v0.15 records source-grounded evidence but does not normalize experiments for comparison |

The engineering checker’s PASS must not be represented as scientific accuracy, benchmark readiness, or plant viability.

## Merge recommendation

**KEEP DRAFT**

Rationale:

- Remote CI is verified PASS for Python 3.10 and Python 3.13 in run `29642293198`; remote exact Gold integrity was correctly skipped because authoritative Gold is intentionally local-only.
- External review of this audit package itself remains pending while PR #2 remains Draft.
- Engineering merge: the local and remote engineering boundary passes with four P2 and one P3 non-blocking limitations documented in `v015_architecture_audit.md`; acceptance of this audit package remains a review step.
- Scientific release: not ready. Human semantic precision, family accuracy, quantification precision, validation precision, and paper-status accuracy are pending.
- Benchmark release: not ready. No versioned adjudicated evaluation set or accepted scientific gates exist.

Engineering merge readiness is distinct from scientific and benchmark readiness. Remote CI no longer blocks the engineering evidence, but external review of the audit package remains pending and semantic calibration remains proposed future v0.16 work.

## Post-merge conditions

Before starting v0.16:

1. Complete external review of this audit package and retain the verified GitHub Actions run `29642293198` as remote engineering evidence.
2. Merge v0.15 to a stable commit through the normal review process; do not branch v0.16 from an arbitrary unmerged working tree.
3. Review and approve the 24-field human-audit protocol and its labeling guide.
4. Generate and hash the 300-span/60-paper Round 1 sampling frame with all human fields blank.
5. Define split, adjudication, metric, confidence-interval, and missing-data policies.
6. Decide explicit v0.16 schema/profile boundaries for any changed behavior.
7. Preserve audit schema 0.13 behavior, stable existing `source_span_id` values, Gold integrity, same-paper links, and low-trust source restrictions.
8. Obtain separate explicit approval before any Gold edit or any real LLM/API call.
