# Final Outputs And Meaning

eNH3-TriageBench turns local paper text into evidence-gated experiment triage outputs. It does not call APIs, scrape websites, or train large language models.

## Core Run Outputs

`data/candidates/candidate_spans.{run_name}.jsonl`
: Candidate source spans selected from local Markdown files.

`data/ledgers/{run_name}/classified_spans.jsonl`
: Every candidate span with `text_class`, confidence, routing reasons, extraction permission, and gold eligibility.

`data/ledgers/{run_name}/performance_ledger.jsonl`
: Primary performance spans that may support performance extraction and triage scoring.

`data/ledgers/{run_name}/negative_evidence_ledger.jsonl`
: Contamination, reassignment, false-positive, or other negative evidence spans.

`data/ledgers/{run_name}/validation_protocol_ledger.jsonl`
: Protocol and control-guideline spans. These guide validation standards but are not treated as primary performance evidence.

`data/ledgers/{run_name}/secondary_review_ledger.jsonl`
: Review tables and literature-summary spans. These are secondary context, not primary evidence.

`data/ledgers/{run_name}/rejected_or_context.jsonl`
: Reference lists, figure captions without paired primary prose, background context, computational-only screening, and unknown spans.

Each ledger also has a `.csv` export for spreadsheet review.

## Triage Outputs

`data/reports/experiment_triage_scores.{run_name}.jsonl`
: Scored primary performance records with metric completeness, validation completeness, source grounding, engineering relevance, contamination penalty, final score, and recommendation.

`data/reports/experiment_triage_table.{run_name}.csv`
: Spreadsheet-ready triage table.

`data/reports/experiment_triage_report.{run_name}.md`
: Human-readable report covering evidence attrition, ledger distribution, high-priority directions, conditional directions, high-risk claims, and dataset-use warnings.

`data/reports/final_workflow_manifest.{run_name}.json`
: Machine-readable manifest of the run and output paths.

## Training Outputs

`data/training/source_span_training.{run_name}.csv`
: Training rows for source-span classification. If no human labels exist, labels are weak rule labels.

`data/training/triage_training.{run_name}.csv`
: Training rows for recommendation/ranking. If no human recommendations exist, labels are weak rule labels.

`models/source_span_classifier.{run_name}.joblib`
: Optional local scikit-learn source-span classifier.

`models/triage_ranker.{run_name}.joblib`
: Optional local scikit-learn recommendation model.

`data/reports/model_predictions.{run_name}.csv`
: Predictions from the optional trained models.
