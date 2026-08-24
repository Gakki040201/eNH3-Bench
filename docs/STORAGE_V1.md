# Storage Architecture v1

Storage v1 separates code, active data, computation workspaces, and frozen archives. It does
not migrate data, alter M017/M018 scientific behavior, or change audit schema 0.13.

## Four authorities

1. **GitHub/repository — code authority.** Source code, schemas, tests, small configuration
   examples, and documentation belong in Git. Runtime datasets, PDFs, and full-text Markdown
   do not.
2. **`F:\eNH3_Bench_Work` — active scientific data.** On the intended workstation this is the
   active data root, supplied as `ENH3_WORK_ROOT`. The example profile contains an environment
   reference rather than this machine-specific value.
3. **COMSOL/QE workspaces — heavy computation.** Solver inputs, scratch files, checkpoints, and
   large outputs remain in their dedicated workspaces outside the active data root.
4. **OneDrive archive — frozen export only.** Its root is supplied through
   `ENH3_ARCHIVE_ROOT` or a local, uncommitted profile. OneDrive is not a live runtime
   directory and must not be used for active ingestion, extraction, modeling, or solver I/O.

The active ingestion path is:

```text
00_inbox
→ 01_corpus
→ 02_registry
→ 03_extraction
→ 04_evidence
→ 05_experiment_records
→ 06_electrolytes
→ 07_dataset_freezes
→ 08_modeling
```

Only a completed export under `07_dataset_freezes` is eligible for the archive when
`archive_only_frozen` is enabled.

## Profile contract

Copy `config/storage_profile.example.json` to `config/storage_profile.local.json` and define its
environment variables. `storage_profile.local.json` is machine-local and must never be committed.
It may contain local absolute paths such as `F:\eNH3_Bench_Work` and the workstation's local
OneDrive archive path. `config/storage_profile.example.json` remains the only committed example
profile.

The schema is `storage-1.0`. Environment placeholders use the exact `${NAME}` form; an unresolved
placeholder is an error. An archive root is never guessed. In direct-environment mode, an absent
`ENH3_ARCHIVE_ROOT` is represented as unconfigured so `preflight` can report it explicitly.

The policy defaults are copy-only frozen archives, no post-export deletion, a manifest, and
SHA256 verification. Storage v1 exposes no delete or move API. `delete_after_export=true` is
rejected.

Legacy M016/M017 roots remain available as `ENH3_PILOT_ROOT` and `ENH3_DEMO_ROOT`. When those
variables are absent, the historical M017 defaults are unchanged. Explicit M017 command-line
arguments take precedence over environment defaults.

## Commands

```powershell
python .\scripts\storage_v1.py preflight --profile .\config\storage_profile.local.json

python .\scripts\storage_v1.py manifest `
  --root F:\eNH3_Bench_Work\07_dataset_freezes\R001-DATASET-v0.1.0

python .\scripts\storage_v1.py copy-freeze `
  --source F:\eNH3_Bench_Work\07_dataset_freezes\R001-DATASET-v0.1.0 `
  --destination "$env:OneDrive\eNH3-Bench_Archive\03_DATASET_FREEZES\R001-DATASET-v0.1.0"
```

`manifest` writes JSON to standard output unless `--output` is supplied. An output file must be
outside the source freeze so manifesting cannot modify the source. `copy-freeze` rejects an
existing destination unless `--overwrite` is explicit, verifies copied sizes and hashes by
default, preserves the source, and writes an adjacent manifest by default. With a profile, the
configured policy and root boundaries are enforced. No command deletes source data.
