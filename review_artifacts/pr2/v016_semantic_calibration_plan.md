# v0.16 Semantic Calibration Plan

## Status

This document is a plan only. v0.16 has not started, no calibration labels have been created, and no v0.15 behavior is changed by this package.

## Objective

Calibrate and improve document genre, reaction family, claim ownership, claim scope, semantic claim typing, ammonia quantification, validation gates, primary eligibility, and paper status while preserving the v0.15 document-first data flow and source-grounding contract.

The calibration work must reduce semantic error without importing legacy semantic labels, hard-coding paper IDs, forcing ambiguous records into specific families, changing Gold, or allowing an LLM to create Gold directly.

## Dataset plan

### Round 1

- 300 semantic spans.
- 60 papers.
- Versioned sampling-frame export with source run, schema/profile, selection code/config, eligible counts, selected IDs, inclusion probability or selection rule, and stratum membership.
- All human fields initially blank; labeling starts only after the protocol and export are reviewed.

### Round 2

- Expand the cumulative semantic-span set to 500 after Round 1 error analysis and regression fixtures.
- Preserve Round 1 IDs and labels; never silently replace adjudicated rows.
- Use Round 1 errors to increase coverage of high-risk strata while retaining a stable evaluation holdout.

### Semantic-span coverage targets

| Stratum | Proposed coverage target |
|---|---:|
| Primary performance | 60 |
| Quantification | 50 |
| Validation | 50 |
| Reactor/process | 30 |
| External cited claims | 30 |
| Review/perspective | 20 |
| Off-target | 20 |
| Trap-only | 20 |
| Unclear/mixed family | 40 |
| Structured/text conflict | 20 |
| Other high-risk strata | 40 |

These coverage targets are not additive because a span may belong to more than one risk stratum. Round 1 remains 300 unique semantic spans. The sampling-frame export must record all memberships and the actual unique count. If an available stratum is smaller than its target, include all eligible units and record the shortfall rather than substituting an undocumented convenience sample.

Suggested selection order:

1. Include all very rare or safety-critical cases: cross-paper diagnostic candidates if any, low-trust primary candidates if any, structured/text conflicts, and rare reaction families.
2. Fill primary-performance, quantification, and validation coverage with paper diversity constraints.
3. Fill ownership, genre, off-target, trap-only, unclear/mixed, reactor/process, and residual high-risk coverage.
4. Add a deterministic general sample from the remaining frame to prevent the review set from containing only known hard cases.

Do not sample multiple near-duplicate spans from one paper when another paper can supply the same stratum. Record per-paper caps and every exception.

## Paper-level sample

The Round 1 paper sample contains 60 unique papers and explicitly covers:

- eNRR;
- LiNRR;
- NO3RR;
- NO2RR;
- NORR;
- mixed family;
- unclear family;
- review/perspective documents; and
- off-target documents.

A proposed mutually exclusive primary allocation for planning is: eNRR 8, LiNRR 6, NO3RR 10, NO2RR 4, NORR 4, mixed 5, unclear 8, review/perspective 8, and off-target 7, totaling 60. Papers may retain secondary stratum flags for analysis. If a rare category contains fewer papers than planned, include all of them, document the shortfall, and reallocate only after the full sampling frame is reported.

The paper sample should include high and low candidate counts, papers with and without primary-eligible spans where available, papers with many `needs_review` spans, and papers with varied link/validation coverage. All 203 v0.15 paper records are currently `needs_review`; this fact is a sampling-frame characteristic, not a human label.

## Labeling and split policy

- Use the 24-field protocol in `review_artifacts/pr2/v015_human_audit_protocol.md`.
- Maintain a development/calibration portion and a frozen evaluation portion at both span and paper levels.
- Keep all spans from a paper in one split to prevent paper-level leakage.
- Keep exact source offsets and stable IDs immutable throughout calibration.
- Version initial, second-review, and adjudicated labels separately.
- Record exclusions and unavailable source context; do not silently drop difficult units.
- LLM assistance, if separately authorized later, may support tooling or error exploration but cannot replace independent human labels or directly produce Gold.

## Calibration loop

```text
human audit
→ error taxonomy
→ minimal rule change
→ regression fixture
→ rerun clean-room
→ compare changed labels
→ repeat
```

For each loop:

1. Freeze and hash the reviewed input set.
2. Produce field- and stratum-specific error tables with bounded examples.
3. State one minimal rule hypothesis and its expected affected population.
4. Add regression fixtures for the observed error and protected counterexamples.
5. Implement only on `feature/v016-semantic-calibration` under an explicit v0.16 profile/schema decision.
6. Run the full tests, exact Gold integrity, a new clean-room run, resume verification, and normalized reproducibility comparison.
7. Compare every changed semantic and paper label, including regressions outside the target stratum.
8. Accept, revise, or revert the rule based on the frozen evaluation portion; document the decision.

Prohibited calibration tactics:

- hard-coding individual `paper_id` values or title fragments to obtain desired labels;
- forcing `unclear` or `mixed` into a specific family merely to lower abstention;
- editing authoritative Gold without its separate approval/integrity process;
- allowing an LLM output to become Gold without governed human review;
- copying full documents into every span/context record;
- linking evidence across `paper_id` boundaries.

## Error taxonomy

At minimum, categorize errors as:

- document genre false primary or false secondary;
- reaction-family false positive, false negative, mixed/unclear handling, or local/document conflict;
- target/external/general-literature ownership inversion;
- target/background/off-target scope error;
- claim-type confusion, especially performance result versus context/mechanism;
- ammonia quantification versus trap/capture handling;
- validation gate false positive, false negative, or structured/text conflict;
- low-trust provenance promoted to primary;
- off-target ammonia-primary promotion;
- insufficient-context judgment;
- evidence-link relevance/role/source-eligibility error;
- paper aggregation error caused by span error versus aggregation-rule error.

Each category must retain counts, denominators, affected strata, bounded evidence, root-cause hypothesis, rule change, and regression fixture.

## Acceptance gates

The following are **proposed gates**, not metrics achieved by v0.15:

| Gate | Proposed threshold |
|---|---:|
| Document genre macro-F1 | `>= 0.95` |
| Reaction family macro-F1 | `>= 0.90` |
| LiNRR/eNRR/NO3RR precision | `>= 0.95` for each named family |
| Primary eligibility precision | `>= 0.95` |
| Primary eligibility recall | `>= 0.70` |
| Quantification precision | `>= 0.95` |
| Validation-gate precision | `>= 0.95` |
| External-ownership false-positive rate | `< 0.01` |
| Off-target ammonia-primary false-positive rate | `< 0.01` |
| Cross-paper support | `0` |
| Low-trust primary support | `0` |

Before applying a gate, define its human-positive mapping, denominator, treatment of `uncertain`/`not_applicable`, minimum class support, confidence interval, split, and whether the threshold applies to the frozen evaluation portion. Report both point estimates and raw confusion counts. Do not claim corpus-wide results from unweighted high-risk strata.

## Deliverables

- Versioned reviewed document labels.
- Versioned reviewed semantic-span labels.
- Versioned reviewed evidence-link labels.
- Versioned reviewed paper labels.
- Sampling-frame and selection report.
- Error taxonomy with bounded examples.
- Calibration report with metric definitions, raw counts, confidence intervals, and limitations.
- Immutable reviewed set with content hashes and adjudication provenance.
- Candidate Gold proposal, kept separate from authoritative Gold until explicit approval.
- Regression tests covering corrected errors and protected counterexamples.

Runtime outputs, source PDFs, and full-text Markdown remain excluded from commits.

## Branch plan

Use `feature/v016-semantic-calibration`, created only from the stable commit produced after v0.15 is merged and locally/remote verified. Do not create it from this uncommitted review-artifact working tree or from an arbitrary unmerged commit. Branch creation, implementation, model/LLM use, and Gold promotion are outside this package and have not started.
