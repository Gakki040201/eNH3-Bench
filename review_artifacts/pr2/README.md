# PR #2 External Audit Package

## Scope

This directory is a bounded review package for:

- architecture review;
- schema review;
- bounded output review;
- human-audit preparation;
- v0.16 planning; and
- release-readiness assessment.

It freezes the v0.15 implementation boundary. The package does not change clean-room behavior or provide new semantic labels.

## Branch and commit

- Branch: `feature/v015-cleanroom-pipeline`
- HEAD before audit-package commit: `ab8235b1f825a63c3175fd4b9f4d46f6dae48986`
- Base branch at audit-package creation: `review/v014-stage-b-context`
- Pull request: `#2`
- Pull request state at audit-package creation: Draft
- Schema: `0.15-cleanroom.1`
- Profile: `document_first_cleanroom_v1`
- Runtime evidence: `data/cleanroom/enrr_cleanroom_v015_20260718/`

## Post-retarget status

PR #1 was merged with merge commit `78ab0dc51af2521afa151c845498b4f5f9cc5eef`. PR #2 is now retargeted to `feature/v014-context-aware-evidence`. This documentation update intentionally triggers a fresh pull-request CI run against the retargeted base. The engineering and scientific boundaries in the audit package are unchanged.

## Files

- `v015_architecture_audit.md`: engineering review of data flow, isolation, identity, offsets, resume behavior, atomicity, clean safety, and paper aggregation.
- `v015_schema_dictionary.md`: field-level dictionary for records, manifests, and the review-sample row.
- `v015_bounded_record_examples.md`: deterministic projections of ten real runtime records with bounded source excerpts.
- `v015_human_audit_protocol.md`: proposed labeling, reviewer, adjudication, metric, and stop-condition protocol.
- `v016_semantic_calibration_plan.md`: proposed calibration dataset, loop, acceptance gates, deliverables, and branch plan.
- `v015_release_readiness.md`: local engineering evidence, pending scientific gates, and a bounded merge recommendation.

## Evidence limitations

- Runtime outputs are gitignored and are not committed in this package.
- Record examples are bounded projections; they are not full records or full documents.
- Human-label fields remain blank. No human review is represented as completed.
- Local tests and local runtime validation remain distinct from remote CI. GitHub Actions run `29642293198`: PASS (Python 3.10 and Python 3.13 jobs). Remote exact Gold integrity was SKIPPED BY DESIGN because the authoritative Gold is local-only and intentionally not committed.
- This package does not establish scientific accuracy, scientific comparability, benchmark readiness, or plant viability.

## Review order

1. Architecture audit.
2. Schema dictionary.
3. Bounded record examples.
4. Human-audit protocol.
5. v0.16 semantic calibration plan.
6. Release-readiness checklist.
