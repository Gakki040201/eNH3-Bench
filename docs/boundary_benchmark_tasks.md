# eNH3-BoundaryBench Tasks

eNH3-BoundaryBench turns Phase D human-reviewed BoundaryLedger records into benchmark tasks for eNH3-specific claim-rights adjudication. It is not a generic retrieval, question-answering, or property-extraction benchmark. It asks what a literature source span is allowed to support after provenance, validation controls, hidden engineering taxes, and follow-up experiment needs are considered.

## Why this benchmark is needed

Electrochemical ammonia synthesis claims often mix reported product signals, validation controls, reactor claims, process gestures, review summaries, captions, and references. Generic extraction can find values, but it does not decide whether a value supports product admissibility, cell metrics, reactor legibility, partial process boundaries, or only secondary/contextual use.

BoundaryBench evaluates that adjudication step directly.

## Six tasks

1. `source_span_classification`: classify the source span type.
2. `validation_gate_extraction`: identify 15N, blank, NOx, contamination, and quantification support.
3. `claim_rights_boundary_classification`: predict maximum supported boundary and admissibility status.
4. `hidden_tax_detection`: detect hidden engineering or measurement burdens.
5. `required_control_prediction`: predict controls needed before stronger claims are allowed.
6. `experiment_decision_ranking`: decide whether the span should drive priority experiments, controls, warnings, protocol references, rejection, or second review.

## Inputs and outputs

Every task row retains source text, provenance type, provenance confidence, paper/document identifiers, rule fields, optional LLM verification fields, reviewer id, and notes. Task-specific `gold_*` fields come only from reviewed human labels.

The builder exports:

- `data/benchmarks/{run_name}/{task_name}.jsonl`
- `data/benchmarks/{run_name}/{task_name}.csv`
- `data/benchmarks/{run_name}/benchmark_manifest.json`
- `data/reports/boundary_benchmark_summary.{run_name}.md`

## Gold labels

Gold labels are loaded first from `data/gold/{run_name}/human_gold_claim_rights.jsonl`. If no explicit gold export exists, the builder can fall back to `data/human_audit/{run_name}/reviewed_audit_records.jsonl`.

Rows are included only when:

- `human_review_status` is `reviewed`;
- required human fields are present;
- human labels validate against the Phase D schema.

Unreviewed, invalid, excluded, or second-review rows are not benchmark gold.

## Baselines

The rule baseline uses BoundaryLedger fields such as `rule_text_class`, `rule_maximum_supported_boundary`, validation gates, detected taxes, required controls, and risk flags.

The LLM baseline is optional. It is evaluated only when LLM prediction fields exist. LLM fields are not gold labels.

## Metrics

Single-label tasks use accuracy and macro F1.

Boundary classification also reports overclaim and underclaim rates. A prediction is an overclaim when its boundary rank is greater than the human boundary rank:

`unsupported_or_secondary < product_admissibility < cell_metric < reactor_legibility < process_partial < plant_facing_insufficient`

Multilabel tasks use exact match, mean Jaccard, and per-label precision/recall/F1 where feasible. Required-control prediction also reports key-control recall for 15N, blank, NOx, HOR-off, and gas/liquid accounting controls.

Experiment-decision ranking evaluates a binary priority target where `priority_experiment`, `control_required`, and `negative_warning` count as priority.

## Why split by paper_id

Multiple records from the same paper share methods, provenance, terminology, and reporting style. Splitting by `paper_id` reduces leakage between train/dev/test. If `paper_id` is absent, splitting falls back to `document_id`, then `source_span_id`.

## Commands

```powershell
C:\Python314\python.exe scripts\build_boundary_benchmark.py --run-name final_pilot
C:\Python314\python.exe scripts\split_boundary_benchmark.py --run-name final_pilot --seed 13
C:\Python314\python.exe scripts\evaluate_boundary_benchmark.py --run-name final_pilot
C:\Python314\python.exe scripts\export_benchmark_datacard.py --run-name final_pilot
```
