# M018 A1 12-Paper Evidence-Package Pilot

## Scope

M018 A1 deterministically assembles the frozen paper order `P0797`, `P0425`, `P0162`, `P0255`, `P0471`, `P0217`, `P0362`, `P0007`, `P0961`, `P0241`, `P0960`, and `P0312`. It uses only existing accepted assets and schema `0.18-evidence-package.1`. It does not call a model, generate or rewrite a scientific claim, create a human label, inspect a credential, access a holdout case, mutate Gold/review/calibration/selective-eval data, or rewrite a clean-room source-span ID.

Generated packages and reports remain outside Git beneath the selected runtime root. The reusable library contains no drive-specific default; only the Windows-facing builder CLI defaults to `F:\eNH3_Bench_API\v018`.

## Source use and exact binding

The builder checks the frozen A0 manifest, accepted A0 inventory, validated OA acquisition state, accepted clean-room validation summary, clean-room document ledger and spans, existing experiment-triage records, existing machine-drafted evidence records, and existing same-paper clean-room links. It does not read selective-eval records or sealed holdout content during A1 assembly.

The main source document is the clean-room ledger's source-root-relative Markdown document because its accepted body hash and offsets control the exact clean-room anchors. OA manifest acceptance remains a required availability gate. The accepted document loader recomputes the body hash; a mismatch fails before package publication.

Each package includes all accepted clean-room spans for its paper. Existing `cleanroom_span_id` values are copied unchanged and ordered by document, start offset, end offset, and ID. The small provenance-type adapter maps accepted clean-room categories to the frozen package enum; it never changes text or support semantics.

Experiment-triage and machine-drafted evidence records use legacy anchors rather than clean-room IDs. A1 therefore binds:

- an experiment only when its exact accepted source text and exact offsets resolve to one clean-room span;
- a claim only when its exact accepted `source_span` text resolves to one clean-room span;
- an evidence link only when its accepted target resolves to exactly one included claim and its evidence span is present in the same paper.

An ambiguous or absent binding is omitted and queued. No fuzzy matching, generated anchor, rewritten text, or inferred merge is allowed. The experiment measurement allowlist copies existing accepted fields only. `None` or an absent field becomes `not_reported`; an explicit empty, `missing`, or `unresolved` marker becomes `missing`; zero and false remain reported zero and false.

## Status preservation

Real A1 claims remain `machine_drafted` because the accepted assets do not provide exact claim-level review or Gold mappings. Paper-level completed-review and Gold membership are retained in coverage reporting and produce review-queue items; they do not promote any claim or package. A directly mapped reviewed or Gold claim is supported by the library only when an explicit direct record reference and reviewer ID are supplied. Machine-drafted packages always have an empty reviewer list.

P0797 intentionally has no accepted evidence link. Its package remains valid with claims and spans, an empty `evidence_links` array, the warning `existing_evidence_links_unavailable`, and a deterministic review-queue item. No EL18 record is fabricated.

Supplementary availability is always `not_reported` in A1 because A0 found no independent accepted SI manifest. Filename fragments, citations, phrases in the main text, or nearby files are never used to infer SI. The supplementary document entry has null `source_ref` and `sha256`. `missing` remains reserved for an accepted assertion that a required SI asset exists but is unavailable.

## Stable identities and hashes

DOC18, EXP18, CLM18, EL18, review-queue, and EP18 identities are SHA-256-derived from schema version plus stable source identities and bindings. They exclude timestamps, paths outside the accepted relative reference, machine/user identity, runtime root, list position, and formatting. The package contains no creation timestamp.

The package content hash reuses `canonical_content_sha256()` from the accepted independent validator. Every package is written, read back, independently validated, and rehashed before it can enter the package set. The package-set tree hash covers, in relative-path order, all four per-paper files and the JSON/CSV/HTML index. The build summary is excluded from its own tree hash to avoid circularity.

## Quality gates and warnings

Every package records the original required gates plus:

- `source_document_integrity`
- `source_span_integrity`
- `experiment_span_binding`
- `claim_status_provenance`
- `evidence_link_integrity`
- `supplementary_status_explicit`
- `package_hash_integrity`
- `deterministic_ordering`

A required gate failure stops publication. Nonfatal gaps remain explicit warnings and review-queue entries, including unavailable accepted links, unbound legacy records, reaction-family conflicts, absent SI authority, and paper-level review/Gold membership without claim-level mapping.

## Runtime commands

Build all 12 packages after the A0 inventory exists:

```powershell
C:\Python314\python.exe scripts\build_v018_evidence_packages.py `
  --pilot-manifest data\manifests\v018_a1_pilot_corpus.json `
  --runtime-root F:\eNH3_Bench_API\v018 `
  --audit-inventory F:\eNH3_Bench_API\v018\audits\v018_asset_inventory.jsonl `
  --clean
```

Build one frozen pilot paper:

```powershell
C:\Python314\python.exe scripts\build_v018_evidence_packages.py `
  --runtime-root F:\eNH3_Bench_API\v018 `
  --audit-inventory F:\eNH3_Bench_API\v018\audits\v018_asset_inventory.jsonl `
  --paper-id P0797 `
  --clean
```

Unknown or nonpilot IDs fail closed. Without `--clean`, an existing named A1 output is not replaced. With `--clean`, the builder validates a staging tree before atomically replacing only the named A1 package directories and A1 report files. It never deletes A0 audits or unrelated runtime files.

Validate an individual package:

```powershell
C:\Python314\python.exe scripts\check_v018_evidence_package.py `
  --package F:\eNH3_Bench_API\v018\packages\P0797\evidence_package.json
```

Validate the complete set:

```powershell
C:\Python314\python.exe scripts\check_v018_evidence_package_set.py `
  --runtime-root F:\eNH3_Bench_API\v018 `
  --pilot-manifest data\manifests\v018_a1_pilot_corpus.json
```

The set stage is `COMPLETE`, `INCOMPLETE`, or `INVALID`; only `COMPLETE` returns `PASS`. The validator requires exactly the 12 frozen directories, every package/coverage/review file, exact index order and hashes, matching summary counts and tree hash, no extra package directory, and 12 independent package-validator passes.

## External output contract

Each `packages/P####/` directory contains `evidence_package.json`, `coverage_report.json`, self-contained `coverage_report.html`, and `review_queue.csv`. The runtime `reports/` directory contains JSON, CSV, and self-contained HTML package indexes plus `v018_a1_build_summary.json`.

HTML uses embedded CSS only, escapes every dynamic value, contains no external JavaScript, remote font, CDN, analytics, or network dependency, and does not reproduce full document text. Every coverage report visibly states “Deterministically assembled from existing accepted assets” and “No new scientific claim was generated in M018 A1”.
