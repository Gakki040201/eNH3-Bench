# M018 Evidence Asset Factory

## Scope

M018 A0 freezes an offline, deterministic contract for auditing existing evidence assets and assembling one evidence package per stable paper. It does not extract new scientific claims, call a model, read credentials, access provider services, create human labels, or mutate Gold. Schema `0.13`, schema `0.15-cleanroom.1`, and every existing `source_span_id` remain unchanged.

The new package schema is `0.18-evidence-package.1`. It is independent of the earlier schemas and reuses their records by reference; it is not a second clean-room implementation.

## Source precedence

The audit uses accepted manifests and validator outputs before file discovery:

1. `data/reports/oa_download_manifest.jsonl` defines the represented stable `P####` paper universe and validated main-PDF acquisition state.
2. The accepted `enrr_cleanroom_v015_20260718` validation summary must be `PASS`. Its document ledger, semantic spans, paper records, and same-paper evidence links provide clean-room coverage.
3. The accepted `enrr_calibration_v016_round1_20260719` validation summary must be `PASS`; reproduction runs are not counted again.
4. The accepted `enrr_selective_eval_v016_round1_20260720` validation summary must be `PASS`. Only records explicitly marked `development` contribute membership or pilot signals. Non-development paper IDs are collected only into an exclusion set and never enter the pilot.
5. The authoritative `enrr_round1_oa_20260712` Gold and reviewed human-audit records provide Gold and completed-review membership.
6. Existing machine-drafted evidence records and experiment-triage records provide claim and experiment-record counts. These counts describe existing records; they do not upgrade them to human-reviewed or Gold evidence.

A main document is available only when the acquisition manifest provides a repository-relative location, a SHA-256 digest, and `valid_pdf` or `existing_valid_pdf`. A filename by itself is insufficient. Supplementary availability requires an independent supplementary-asset manifest. Mentions such as “Supplementary Fig.” inside a main article do not establish that SI exists locally.

## Offline audit

Run:

```powershell
C:\Python314\python.exe scripts\audit_v018_evidence_assets.py `
  --repository-root . `
  --runtime-root F:\eNH3_Bench_API\v018 `
  --pilot-manifest data\manifests\v018_a1_pilot_corpus.json
```

The runtime root must resolve outside the repository. The command creates this fixed layout:

```text
F:\eNH3_Bench_API\v018\
  audits\
  packages\
  reports\
  review\
  logs\
```

It writes:

- `audits/v018_asset_inventory.jsonl`
- `audits/v018_asset_summary.json`
- `reports/v018_asset_coverage.html`
- `reports/v018_asset_gaps.csv`

The exports contain no full document, PDF bytes, absolute source path, credentials, hidden labels, or model reasoning. Output ordering, JSON key ordering, pilot ranking, warning ordering, and HTML/CSV row ordering are deterministic.

## Inventory grain

The inventory grain is one stable `P####` paper. Long document-first identifiers are retained in their source assets and mapped to their unchanged stable paper prefix; they are not rewritten.

Each row records:

- main, supplementary, and clean-room availability;
- exact clean-room span, machine-drafted scientific-claim, experiment-triage, and same-paper evidence-link counts;
- accepted calibration, development selective-eval, Gold, and completed human-review membership;
- document genre, reaction family, validation-gate counts, reactor/process span count, and development case signals when available;
- only repository-relative known source locations;
- explicit missingness and inconsistency warnings.

Duplicate stable IDs in the authoritative paper manifest fail the audit. Orphan asset IDs are reported in the summary. Missing assets remain inventory rows rather than disappearing from the denominator.

## Per-paper evidence-package contract

`schemas/v018_evidence_package.schema.json` requires:

- `schema_version`
- `package_id`
- `paper_id`
- `source_documents`
- `source_spans`
- `experiment_records`
- `scientific_claims`
- `evidence_links`
- `quality_gates`
- `review_status`
- `provenance`
- `package_hashes`

All record families reject unknown fields. Stable IDs are unique within and across the package. Every nested `paper_id` must equal the package paper. Existing source-span IDs may be referenced unchanged.

### Documents and spans

`source_documents.document_type` is either `main` or `supplementary`. `availability_status` is one of:

- `available`: requires a relative source reference and lowercase SHA-256;
- `missing`: the expected asset was sought or required but is absent;
- `not_reported`: the source provides no report of that asset.

`missing` and `not_reported` are never collapsed. A valid package requires exactly one available main document. Supplementary entries are optional and may explicitly record either missing state.

A source span is an exact bounded evidence anchor. It binds to an available source document, preserves an existing stable span ID when reused, carries exact offsets and text, and records provenance. References, captions, review tables, and supplementary spans may remain context but never gain primary support merely by being packaged.

### Experiments, claims, and links

Every experiment record binds to this one paper and to at least one source span. Each measurement is an object with explicit `reported`, `missing`, or `not_reported` status; only `reported` may contain a value.

Every scientific claim binds to at least one in-package source span. Claims and evidence links cannot cross a paper boundary. A link must resolve both its claim and source span, and the linked span must already be cited by that claim.

Claim and package states are distinct ordered states:

- `machine_drafted`
- `human_reviewed`
- `gold_accepted`

A package cannot contain a claim at a higher state than the package review state. Human-reviewed and Gold-accepted packages require reviewer IDs; machine-drafted packages must not claim human reviewers.

### Quality, provenance, and hashes

The package declares checks for unique IDs, relative paths, same-paper binding, claim-span binding, absence of secrets, and absence of hidden labels. `quality_gates.passed` must equal the conjunction of their statuses.

Provenance contains only the producer class, deterministic generation method, repository/package-relative source references, and code commit. Credential, authorization, token, password, cookie, hidden-label, reasoning, or chain-of-thought fields are forbidden recursively. Common credential-shaped values are also rejected.

`package_hashes.content_sha256` is SHA-256 over canonical JSON excluding the `package_hashes` object. `source_document_hashes` must exactly match all available source documents.

Validate a package with:

```powershell
C:\Python314\python.exe scripts\check_v018_evidence_package.py `
  --package F:\eNH3_Bench_API\v018\packages\P0001.json
```

The validator returns nonzero for malformed JSON, missing fields, unknown fields, invalid IDs, unavailable main documents, unsafe paths, invalid status transitions, unbound spans or claims, cross-paper links, secrets, hidden labels, reasoning fields, failed/not-run gates represented as passed, or hash mismatches.

## Deterministic A1 pilot rule

Eligible papers must have a manifest-backed main document, accepted clean-room record, at least one exact source span, at least one existing machine-drafted claim record, and at least one experiment-triage record. Any paper marked outside the development split is excluded.

Selection then:

1. fills, in fixed order, LiNRR, direct eNRR, ammonia quantification, isotope/contamination validation, reactor/process extraction, claim ownership, insufficient evidence, and review/perspective or non-target-negative lanes;
2. adds uncovered reaction families in the fixed order LiNRR, eNRR, NO3RR, NO2RR, NORR, mixed, unclear;
3. fills to exactly 12 using a stable score favoring Gold, completed human review, development selective-eval, calibration, links, experiment records, claims, and span coverage, with `paper_id` as the final tie-breaker.

The tracked manifest stores only paper IDs, selection reasons, reaction-family coverage, and expected asset categories. The audit fails if the manifest differs from a recomputed selection.
