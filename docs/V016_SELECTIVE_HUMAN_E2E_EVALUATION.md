# v0.16 Selective Human Calibration and End-to-End API Evaluation

## Phase B1A status and scope

Phase B1A builds deterministic evaluation infrastructure and a blank runtime package. It does not run
an API, create an API answer, call a machine judge, collect a human label, establish scientific
accuracy, validate the benchmark, calibrate a judge, or authorize a Gold update. A future real API or
judge run requires separate explicit authorization.

The 520-item calibration package is a candidate pool, not a mandatory
full-human-review workload.

Human reviewers primarily assess end-to-end API outputs.

Intermediate human review is selective and is used only for calibration,
diagnosis, and escalation.

No API output, machine judgment, or human label is generated in Phase B1A.

The source v0.16 calibration package, its v0.15 clean-room source, Gold, and the existing calibration
schema remain immutable. Phase B1A defines the independent schema `0.16-selective-eval.1` and profile
`selective_human_anchor_and_e2e_api_v1`.

## Why the default is no longer 520 x 2

The original 520-row package remains valuable as a deterministic candidate pool and structural
validation surface. Requiring two people to re-check every intermediate row would spend most of the
human budget on facts that software can verify exactly: IDs, same-paper constraints, offsets, hashes,
row alignment, bounded context, and schema conformance. It would also shift attention away from the
scientific language, citation use, limitations, and uncertainty in the final API answer.

The Phase B1A human budget is therefore 24 intermediate anchors with two independent reviewers (48
observations) plus 48 future E2E answers with two independent reviewers (96 observations). Only the
second workload becomes active after separately authorized API generation. The other 496 intermediate
items are not routed to routine human review. They remain available for deterministic checks, risk
scoring, and conditional traceback.

## Evaluation layers and boundaries

Layer 0 performs full deterministic validation at zero human cost. Layer 1 assigns an explainable,
non-probabilistic structured risk score to all 520 items. Layer 2 selects 24 intermediate human anchors
for calibration and diagnosis. Layer 3 reserves double review of all 48 future final API answers. Layer
4 escalates failures, disagreement, low confidence, drift, unsupported claims, unresolvable citations,
or unexpected schema categories.

Programs should prove structural facts. Humans should judge scientific meaning and whether an answer's
language is warranted by its cited evidence. An intermediate anchor is not a reference answer and does
not turn a Stage B evidence span into a full-document conclusion. References, captions, and review
tables can supply context but cannot become primary positive support. Evidence never crosses a
`paper_id` boundary.

## Deterministic risk and routing

`structured_risk_router_v1` emits a score from 0 to 100, a tier, reason objects with raw and applied
weights, a machine route, and a human route. Correlated reasons are retained for diagnosis but share an
explicit group cap. For example, `needs_review`, derived primary ineligibility, and related hard-gate
failures do not count as independent severe errors when they express the same upstream fact. The score
is a deterministic triage index, not a probability and not a learned model output.

- T0 is structurally stable and normally receives deterministic validation only.
- T1 receives final-output review without default intermediate escalation.
- T2 receives final-output review and is eligible for an intermediate anchor or failure traceback.
- T3 identifies high review or failure risk. It requires escalation, but it does not by itself require
  abstention.

Risk tier and case action are deliberately separate. Every case records `answerability_status` as
`answerable`, `partially_answerable`, `insufficient_evidence`, or `out_of_scope`, plus reproducible
answerability reasons derived from the case type and bounded sources. Only the last two statuses set
`abstention_expected`. Thus an off-target paper can still have an answerable scope question, missing
primary evidence can support a defensible negative assessment, and incomplete quantification,
validation, or reactor reporting can support a partial answer that names what is missing.

The round-one 16 answerable / 16 partially answerable / 16 insufficient-evidence composition is a
deliberately constructed evaluation mix, not an estimate of prevalence in the calibration pool or the
scientific corpus. `abstention_expected` is a pre-generation routing expectation rather than a reference
answer or human truth. A later schema-valid API output and independent human review may overturn that
expectation; the discrepancy must be retained for analysis rather than silently rewriting the case.

High confidence is not proof of correctness, and machine agreement is not human correctness. The anchor
selection combines category rarity, risk, diversity, and a fixed SHA-256 rank. A deterministic random
sentinel remains in the span anchors so that drift or blind spots outside the highest-risk tail can be
observed.

Additional routing hooks cover disagreement between two or more judges, unsupported claims,
unresolvable citation endpoints, answer/risk conflicts, new reaction families or document genres,
model or prompt changes, and drift-sentinel failure.

## Development and sealed holdout

Splits are assigned only at `paper_id` level using a fixed seed and SHA-256. The 48 E2E cases use 36
development papers and 12 sealed holdout papers. Each case uses exactly one paper; cross-paper synthesis
is forbidden. The same paper can never enter both splits. Development results can support error analysis.
Holdout human answers and anchor results must remain sealed until prompts, rules, and routing thresholds
are frozen. Deterministic schema, count, source-resolution, and case-type coverage checks are allowed,
but holdout outcomes cannot be used to tune thresholds, prompts, or case selection.

The split manifest records case and anchor IDs for every selected paper. Anchors outside the 48 case
papers use the same global paper split function. A holdout anchor is diagnostic only after unsealing and
cannot be used for iterative prompt adjustment.

The generator-visible batch is deliberately narrower than the evaluator case frame. It contains only
the question, answer contract, bounded context, citation allowlists, stable source identity, and the fact
that abstention is allowed. It never exposes split, risk tier or reasons, answerability labels,
`abstention_expected`, evaluator routes, or expected verdicts. `abstention_allowed=true` gives the future
generator permission to decline an unsupported answer; it does not reveal an evaluator expectation.

Batch export defaults to the 36 development cases. Holdout export is a separate 12-case operation and
requires a freeze manifest produced by `create_holdout_freeze_manifest.py`. The command first validates
the complete source calibration package and selective-evaluation package. It requires exactly 36 API
outputs whose case IDs are exactly the development IDs; any holdout, unknown, duplicate, failed, or
provenance-incomplete output prevents freezing. Each accepted output must be a completed generation with
`api_call_performed=true`, a nonblank model family and prompt version, and nonempty generation parameters.
It computes hashes from the
actual package manifest, case frame, generator batch, prompt bytes, canonical generation-parameter JSON,
and the stable-case-sorted development outputs; callers do not supply those hashes as declarations.
The record also binds source identity, prompt and model-family versions, risk/question/answer-contract
versions, and case counts. Development results, routing rules, and the prompt must all be frozen. There
is no uncontrolled `all` export mode, and the freeze manifest contains no labels, answers, credentials,
reference answers, holdout outputs, or generation secrets.

The declared model family, prompt version, and canonical parameter object must match every development
output, and all 36 outputs must use the same values. The freeze records both the declared configuration
and the configuration observed in development outputs. A terminal `failed` output may be retained as an
auditable generation failure only when it contains no answer, claims, or citations and records a failure
reason or limitation; it does not count toward development completion or generation completeness and
cannot unlock holdout.

Holdout export recomputes every bound hash. A change to the prompt, parameters, development outputs,
case frame, generator batch, package manifest, run identity, or source identity invalidates the freeze.
A successful export atomically writes the 12-row generator-visible batch and an adjacent
`holdout_release_manifest.json` binding the freeze hash and exported-batch hash. An identical second
release is reported as already released; a nonidentical release is rejected. This is tool-level,
auditable sealing, not cryptographic access control: a person with direct filesystem write permission
can bypass the CLI and must be governed by the review protocol and storage controls.
Immediately before release, the CLI again requires exactly the same 36 development-only successful
outputs and verifies that there are no holdout outputs, holdout machine judgments, or completed holdout
human-review rows. Freeze manifests, exported holdout batches, and release records must be written
outside the runtime directory so an export cannot invalidate package inventory. Both production CLIs
perform full source-package validation; test fixtures exercise lower-level helpers or use the real
read-only calibration package rather than disabling that validation in user-facing commands.

## Single-paper E2E cases and bounded context

The case profile is `single_paper_scientific_answer_v1`. It covers paper scope, reaction family, primary
evidence sufficiency, ammonia quantification, validation reliability, reactor/process extraction, and
claim ownership. Questions are practical scientific questions, not requests to confirm an automatic
classification. Each case contains bounded excerpts plus explicit source-span and evidence-link
allowlists. No PDF, full-text Markdown, or full document body enters the package.

No reference-answer prose is generated. Instead, a structured answer contract requires separation of
observation from inference, allowlisted citations for scientific claims, explicit missing evidence, a
limitations section, and an uncertainty or abstention statement.

## API output contract

A future imported output records `answer_text`, `answer_status`, `confidence_statement`, structured
claims, citations, limitations, an abstention reason, generation model and prompt identities, generation
parameters, source case ID, and source manifest SHA-256. Allowed answer statuses are `answered`,
`partially_answered`, `abstained`, and `failed`.

Each claim includes a claim ID, text, type, supporting allowlisted source-span and evidence-link IDs, and
one of `supported`, `partially_supported`, `unsupported`, or `uncertain`. The importer rejects unknown
cases or fields, duplicate outputs, source-identity mismatch, malformed or claimless answered outputs,
substantive content in an abstention, and citations outside the case allowlist. Row validation finishes
before atomic installation, and full package validation follows it with rollback on failure, so no
partial or invalid imported file remains. Export and import commands perform no network call.

Imported API outputs and machine judgments are optional derived package artifacts. When present, the
independent package validator revalidates every row against the case, template, stable ID, source hash,
claim and citation allowlists, and same-paper boundary. Partial imports are allowed and reported with
imported and missing counts. Machine judgments require an already valid imported API output and remain
machine observations rather than human truth.

Package import writes only the standard package paths. An arbitrary destination requires explicit
`--export-only`, which validates and exports without claiming package installation. Package installation
uses an atomic write followed by full package validation; failure removes the new artifact and restores
the pre-import package tree. Existing artifacts are never overwritten.

Abstention is an allowed and sometimes expected scientific outcome. It should be used when bounded
evidence cannot support a defensible answer. Abstention does not bypass review: reviewers assess whether
it was appropriate and useful.

## Machine judge interface

The blank multi-judge schema covers answer correctness, citation entailment and completeness, claim
ownership, reaction family, quantification, validation, uncertainty calibration, abstention
appropriateness, unsupported-claim count, and overall usefulness. Every dimension retains score,
verdict, confidence, rationale, evidence, judge model, and judge prompt version. Verdicts are `pass`,
`fail`, `uncertain`, and `not_applicable`.

Two stable judge slots demonstrate multiple-judge support without using judge identity in stable IDs.
Judge identity remains attached to imported observations. Judge disagreement is preserved and never
silently collapsed. A judge consensus is not human truth and cannot overwrite a human result.
Multiple judges can also share correlated errors when they use similar models, prompts, or evidence,
so numerical agreement must not be interpreted as independent validation. Phase B1A supplies only blank
templates and fixture/mock validation; it calls no judge.

## Final-answer human review and citation review

Every future E2E output receives independent R1 and R2 rows. Reviewers assess answer correctness,
citation entailment and completeness, reaction family, ownership, quantification, validation,
uncertainty, abstention, unsupported claims, and scientific usefulness. `no` or `uncertain` requires a
note. The overall verdict is one of `pass`, `minor_revision`, `major_revision`, `reject`, or `uncertain`.
`review_status=completed` is accepted only when every required label and the overall verdict are filled,
the stable output ID matches the same case, and that case has a valid imported API output. Reviewer slots
are fixed to `reviewer_1/R1` and `reviewer_2/R2`; duplicate case/reviewer observations are invalid. A
`no` or `uncertain` label without notes is invalid. Partial rows remain available for work in progress but
do not count toward completed-review coverage.

`human_corrected_answer` is blank by default and is used only when a reviewer must supply a corrected
answer. It is not an automatically generated reference answer. Citation-level review checks whether each
claim is supported and whether the set of citations is complete, without accepting a structurally valid
ID as proof of entailment.

Adjudication is separate and blank. It begins only after independent reviews are locked, records the
fields in disagreement, and never automatically selects a reviewer. The machine judge cannot adjudicate
human disagreement by itself.

## Metrics, drift, and future operation

With blank outputs and reviews, evaluation status is `not_available`. In metrics schema
`0.16-e2e-metrics.1`, the approved metric algorithms are not implemented: precision, pass rate, kappa,
judge-human agreement, unsupported-claim rate, abstention correctness, citation entailment, citation
completeness, and every other metric value must remain `null`, even when artifact coverage is complete.
The reason is `metric computation requires a separately approved metrics implementation`. Implementing
those calculations requires a separately approved change and a metric-schema version bump.
Future summaries keep generation completion, case answerability, human final-output assessment, machine
judge assessment, judge-human agreement, abstention correctness, citation entailment, citation
completeness, and unsupported-claim rate separate. Risk tier and expected answer action are never used
as human truth. Metrics become meaningful only after an authorized generation run and completed
independent human review.

The package validator derives, rather than accepts, the current stage: `blank`, `generated`, `judged`,
or `human_reviewed`. Generation completeness means 48 valid outputs covering 48 distinct cases. Human
review completeness means 96 valid, output-aligned rows with exactly R1 and R2 for every case. Machine
judgment completeness means 96 valid observations with two distinct judge observations per case.
`human_metrics_ready`, `judge_metrics_ready`, and `judge_human_metrics_ready` combine those exact coverage
conditions independently; a merely nonempty artifact is never sufficient. Optional metrics summaries
are compared field by field with the authoritative summarizer output. A stale summary or any non-null
unimplemented metric is rejected.

Drift monitoring should retain the random sentinel and track prompt version, model version, new reaction
families, new genres, risk-tier shifts, citation failures, and disagreement rates. A model or prompt
change is an escalation condition and does not inherit prior validation automatically.

To operate a future real run, first freeze development choices, explicitly authorize the API and judge
providers, export the generation batch, import schema-valid outputs, collect R1/R2 reviews, preserve
judge identities and disagreement, adjudicate manually, and only then summarize. Gold promotion remains
a separate process requiring an integrity-baseline update and explicit approval.
