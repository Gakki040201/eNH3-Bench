# v0.15 Clean-Room Document-First Pipeline

## Purpose and architecture

`document_first_cleanroom_v1` is an independent profile using schema `0.15-cleanroom.1`. It begins with complete Markdown documents, not legacy span outputs:

```text
raw input (optional conversion) -> Markdown -> document assessment
-> section/paragraph source nodes -> new candidate anchors -> semantic assessment
-> same-paper links -> limited paper aggregation -> review/database/validation
```

The pipeline is document-first, source-grounded, clean-room, reproducible, resume-safe, and fail-closed. It does not modify schema 0.13, Gold, historical runs, or historical `source_span_id` values. Normal execution never reads old candidate spans, evidence bundles, claim-rights ledgers, provenance files, context packets, or semantic labels.

## Stages and contracts

The fixed stages are `ingest`, `documents`, `source_nodes`, `candidates`, `semantics`, `links`, `papers`, `review`, and `validate`.

- `ingest` hashes repository-relative Markdown inputs.
- `documents` stores one genre and reaction-family assessment per document.
- `source_nodes` preserves all sections and paragraphs, exact body offsets, physical order, provenance, and maximum support roles. References, captions, review tables, front matter, and background remain present but cannot independently provide primary support.
- `candidates` generates exact, single-node anchors. Trigger rules improve recall only; they do not decide ownership, family, claim type, or primary eligibility.
- `semantics` consumes only new candidates, new document assessments, and new source provenance. Hard gates require primary research, target scope, target-author ownership, primary-admissible provenance, a supporting semantic type, compatible family signals, no structured/text conflict, and configured confidence.
- `links` creates only same-paper, non-self links. A context-only source stays context-only and cannot upgrade ownership, provenance, or family.
- `papers` creates one record for every document, including documents with no candidates. It references span IDs instead of copying full text.
- `review` creates a deterministic stratified sample with blank human fields. It is not represented as completed human review.
- `validate` writes a validation report and JSONL/CSV paper database only after checking schemas, IDs, offsets, links, manifests, path leakage, and safety counts.

## Runtime outputs

Outputs are under `data/cleanroom/{run_name}/`: `config`, `ingest`, `documents`, `source_nodes`, `candidates`, `semantics`, `links`, `papers`, `review`, `reports`, `database`, `manifests`, and optional `logs`. Runtime JSONL, CSV, Markdown reports, manifests, and logs are ignored by Git; only `data/cleanroom/.gitkeep` is retained.

Every document, source-node, candidate, semantic, and paper record explicitly carries `schema_version`, `pipeline_profile`, `run_name`, and `record_created_by_stage`. Document text is stored or referenced once; semantic and paper records do not embed full documents.

## Identity design

`cleanroom_span_id` is `CR15_` plus a stable SHA-256 prefix over document-body hash, exact start/end offsets, and candidate kind. It is independent of run name, absolute path, traversal order, and ranking. The same text in different documents cannot share an ID because the document-body hash participates. Evidence links similarly use deterministic `CRL15_` IDs derived from paper, target span, and evidence span identities. `legacy_source_span_id` is blank in normal runs and may only be populated by an explicit migration workflow.

## Clean safety

`--clean` resolves and prints the absolute target before deletion and may delete only the exact child `data/cleanroom/{run_name}`. It rejects blank names, `.`, `..`, separators/traversal, reserved `data`/`cleanroom` names, the clean-room root, the data root, and historical run `enrr_round1_oa_20260712`. Symlinks or junctions resolving outside the runtime root are rejected. `--dry-run --clean` prints the target without deleting it. It never deletes input directories, Gold, review artifacts, historical runtime paths, sibling runs, or any non-cleanroom directory.

## Manifests, atomic writes, and resume

Critical exports use temp-file, flush/fsync, and atomic replace. `manifests/stage_manifest.json` records status, timestamps, relative inputs/outputs, hashes, config hash, counts, warnings, errors, commit, schema, and profile for each stage. A failed stage is marked `failed`; `final_manifest.json` cannot say `completed` unless every required stage completed.

Run and clean operations use an exclusive per-run lock outside the deletable run directory, preventing concurrent writers and clean/run races. A leftover lock after an interrupted process is treated as stale and must be inspected and removed manually; it is never ignored automatically.

`--resume` verifies Markdown hashes, config hash, schema/profile, upstream output hashes, and each reusable output hash. A change invalidates that stage and all downstream stages. `--from-stage` requires `--resume` and refuses to start if any upstream stage is not reusable. No invalid output is silently reused.

## Paper aggregation

Paper status is limited to `not_evaluated`, `needs_review`, `insufficient_evidence`, `partially_supported`, or `supported_with_limitations`. Critical conflict or uncertainty yields `needs_review`; no primary result evidence yields `insufficient_evidence`; a result with incomplete controls yields `partially_supported`. Even the strongest emitted status retains explicit limitations and never means `fully_validated`, `scientifically_comparable`, `publication_ready`, or `plant_viable`.

## Reproducibility and checking

Run validation and normalized comparison with:

```powershell
C:\Python314\python.exe scripts\check_cleanroom_outputs.py `
  --run-name enrr_cleanroom_v015_repro_a `
  --compare-run enrr_cleanroom_v015_repro_b
```

Normalization ignores only run name, timestamps, and explicitly named execution-only runtime/log metadata fields. It does not rewrite arbitrary strings containing paths, semantic text, warnings, labels, IDs, offsets, or record counts. It compares documents, source nodes, candidates, semantics, links, and papers separately and reports the first differing file, record, and field.

## Failure recovery

Inspect `manifests/stage_manifest.json`, correct the input/config/code problem, and rerun with `--resume`. If source data or configuration changed, the pipeline regenerates invalidated downstream stages. Use `--clean` only when a fully fresh exact run directory is intended.

## Legacy comparison mode

`--compare-run old_run_name` is the only mode permitted to inspect legacy JSONL. It writes an isolated comparison report, marks it comparison-only, and never changes new candidate, semantic, link, or paper outputs. Normal clean-room execution has no legacy runtime dependency.

## Full command examples

Full run:

```powershell
C:\Python314\python.exe scripts\run_cleanroom_pipeline.py `
  --markdown-dir input_markdown `
  --run-name enrr_cleanroom_v015_20260718 `
  --profile document_first_cleanroom_v1 `
  --skip-conversion `
  --clean `
  --review-sample-size 130 `
  --review-seed 13
```

Resume:

```powershell
C:\Python314\python.exe scripts\run_cleanroom_pipeline.py `
  --markdown-dir input_markdown `
  --run-name enrr_cleanroom_v015_20260718 `
  --skip-conversion `
  --resume
```

Verified stage range:

```powershell
C:\Python314\python.exe scripts\run_cleanroom_pipeline.py `
  --markdown-dir input_markdown `
  --run-name enrr_cleanroom_v015_20260718 `
  --from-stage candidates `
  --to-stage papers `
  --resume
```

Raw input requires either a directory containing only Markdown or an explicit converter command using `{input_dir}` and `{markdown_dir}` placeholders.

`--clean` and `--resume` are mutually exclusive, as are `--input-dir` and `--markdown-dir`. Review sample size must be non-negative. Invalid profiles, stage ranges, configs, or converter failures stop with a non-zero exit instead of producing a completed manifest.

## Known limitations

The semantic classifier is a deterministic baseline, not a trained or LLM system. High recall is intentional, so `unclear`, `unsupported`, and `needs_review` may be common. Evidence links are bounded same-paper associations, not causal proof. Paper aggregation does not claim benchmark-grade precision, scientific comparability, publication readiness, or plant viability. No real LLM API call or model training occurs.
