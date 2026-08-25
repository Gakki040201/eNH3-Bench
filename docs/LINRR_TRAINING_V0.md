# LiNRR Training Dataset and Literature Shadow Predictor v0

This milestone introduces an independent condition-record schema and does not modify audit schema 0.13, Gold files, source span IDs, or the P0001–P1034 registry.

## Scientific boundary

The legacy 1,787-row experiment-triage asset is candidate evidence, not Gold training data. Curated bundle membership and paper-level review likewise do not confer experiment-row authority. Every record is admitted independently through the v0 gates in `schemas/training_admission_v0.schema.json`.

One immediate child directory of each configured inbox root is one acquisition bundle and a hard ownership boundary. Asset hashes and exact locators are retained. DOI exact matches reuse registry IDs; title-only matches remain review-required; unmatched bundles retain deterministic `NEWBUNDLE_<hash>` identities. No registry mutation occurs.

Battery additive records are descriptor priors only. Battery CE, capacity, and cycle-life values are never NH3 targets. Fixed-nitrogen additives such as LiNO3 are flagged and excluded from automatic LiNRR recommendation. Candidate screening is outside this milestone.

## Runtime commands

Runtime scientific outputs are written outside Git:

```powershell
python scripts/build_linrr_training_v0.py
python scripts/train_linrr_shadow_v0.py
```

The builder refuses to overwrite an existing v0 dataset, report directory, or workbook. The predictor likewise refuses to overwrite an existing modeling directory.

The predictor uses paper-grouped `GroupKFold` only. The formal fitting gate requires at least 25 eligible FE rows and at least five unique paper groups. Fewer observations produce `INSUFFICIENT_MODELING_DATA` artifacts and no model binary. Any fitted output is explicitly a literature shadow model, not prospective proof or an optimization engine.

## Legacy mapping

The runtime `legacy_triage_field_mapping.csv` is generated after inspecting the actual JSONL schema. Only present fields are mapped. Units are carried verbatim unless conversion is mathematically unambiguous; incompatible NH3-rate units are never combined.
