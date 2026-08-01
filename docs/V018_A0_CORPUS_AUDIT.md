# M018 A0 Corpus Audit

## Acceptance snapshot

- Starting master: `ff3cb408c63f30b00c50e86bc1a2df0058292507`
- Audit schema: `0.18-asset-audit.1`
- Evidence-package schema: `0.18-evidence-package.1`
- Authoritative Gold, clean-room, calibration, and selective-eval assets: read-only
- API calls: 0
- Network calls: 0
- Credential reads: 0
- Model calls: 0
- New human labels: 0

The authoritative OA manifest represents exactly 1,034 unique, contiguous stable IDs, `P0001` through `P1034`. The complete per-paper list is in the external `audits/v018_asset_inventory.jsonl` rather than duplicated in Git.

## Coverage

| Asset | Papers | Coverage | Records |
|---|---:|---:|---:|
| Manifest-backed main document | 203 | 19.6325% | 203 documents |
| Independently inventoried SI | 0 | 0.0000% | 0 documents |
| Accepted clean-room source spans | 203 | 19.6325% | 8,837 spans |
| Existing experiment-triage records | 202 | 19.5358% | 1,787 records |
| Existing machine-drafted scientific claims | 203 | 19.6325% | 2,959 records |
| Same-paper evidence links | 118 | 11.4120% | 1,013 links |
| Accepted calibration membership | 161 | 15.5706% | — |
| Development selective-eval membership | 44 | 4.2553% | — |
| Authoritative Gold membership | 100 | 9.6712% | 100 Gold records |
| Completed human-review membership | 100 | 9.6712% | 100 reviewed records |

The 203 main-document IDs exactly match the 203 accepted clean-room document IDs. There are no orphan paper IDs and no main-document/clean-room coverage mismatches.

“Experiment record” here means an existing row in `experiment_triage_scores.enrr_round1_oa_20260712.jsonl`. It is not a newly executed physical experiment. “Scientific claim” means an existing machine-drafted evidence record in `draft_evidence.enrr_round1_oa_20260712.jsonl`; A0 extracted no new claim and did not upgrade any status.

## Asset gaps and inconsistencies

| Finding | Papers | Interpretation |
|---|---:|---|
| Supplementary manifest unavailable | 1,034 | The current acquisition workflow explicitly excludes supplementary references. SI mentions inside main text are not independent SI assets. SI therefore remains unavailable, not inferred. |
| Main document unavailable | 831 | These manifest rows lack a validated local main document. |
| Clean-room record unavailable | 831 | Clean-room coverage is limited to the same 203 validated main documents. |
| Reaction family not reported | 831 | No accepted clean-room document assessment is available for these papers. |
| Clean-room paper has no evidence link | 85 | A source-span package can exist, but no existing same-paper link is available. |
| Clean-room paper has no experiment-triage record | 1 | Experiment-level coverage is 202 of 203 clean-room papers. |
| Reaction-family conflict flag | 7 | The accepted clean-room document assessment recorded conflicting family signals. |

The audit found zero stable-ID orphans and zero main/clean-room set inconsistencies. Missing assets remain explicit. No filename-only SI inference, citation-table promotion, caption promotion, or cross-paper evidence inference was used.

Selective-eval records outside the development split were used only to create an exclusion set. Sixteen unique non-development paper IDs were excluded from selection; zero were included or serialized as pilot IDs.

## Deterministic 12-paper A1 pilot

| Order | Paper | Primary deterministic reason | Family |
|---:|---|---|---|
| 1 | `P0797` | LiNRR lane; development primary-evidence-sufficiency case with insufficient evidence | LiNRR |
| 2 | `P0425` | direct eNRR lane; development ammonia-quantification case | eNRR |
| 3 | `P0162` | ammonia-quantification lane; accepted quantification gate and development validation case | NO3RR |
| 4 | `P0255` | isotope/contamination-validation lane; accepted isotope gate and insufficient-evidence case | NO2RR |
| 5 | `P0471` | reactor/process lane; accepted reactor spans and development extraction case | unclear |
| 6 | `P0217` | claim-ownership lane; answerable development ownership case | NO3RR |
| 7 | `P0362` | insufficient-evidence lane; review article and abstention-expected quantification case | eNRR |
| 8 | `P0007` | review/perspective or negative lane; perspective scope case | unclear |
| 9 | `P0961` | reaction-family diversity with a development validation case | NORR |
| 10 | `P0241` | reaction-family diversity with a development quantification case | mixed |
| 11 | `P0960` | deterministic asset-ranked fill; development reaction-family case | eNRR |
| 12 | `P0312` | deterministic asset-ranked fill; development quantification case | NO3RR |

All 12 have a validated main document, accepted clean-room spans, existing experiment-triage records, existing machine-drafted claim records, calibration membership, development selective-eval membership, authoritative Gold membership, and completed human-review membership. Eleven also have existing evidence links; `P0797` is the deliberate no-link case, preserving a realistic package gap for A1.

The stable ordered IDs are:

```text
P0797, P0425, P0162, P0255, P0471, P0217,
P0362, P0007, P0961, P0241, P0960, P0312
```

## External outputs

The accepted audit writes only outside Git:

```text
F:\eNH3_Bench_API\v018\audits\v018_asset_inventory.jsonl
F:\eNH3_Bench_API\v018\audits\v018_asset_summary.json
F:\eNH3_Bench_API\v018\reports\v018_asset_coverage.html
F:\eNH3_Bench_API\v018\reports\v018_asset_gaps.csv
```

The tracked repository contains only the factory/contract documentation, schema, offline audit and validator code, focused tests, and the small stable-ID pilot manifest.
