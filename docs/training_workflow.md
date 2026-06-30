# Training Workflow

The training workflow builds small local scikit-learn models from reviewed eNH3-TriageBench outputs. It does not train an LLM, call a hosted model, use a GPU, or predict catalyst quality from structure alone.

## What Gets Trained

`train_source_span_classifier.py`
: A TF-IDF plus LogisticRegression text classifier for source-span classes such as `primary_performance`, `review_table`, and `contamination_detection_evidence`.

`train_triage_ranker.py`
: A small recommendation classifier for `priority_follow_up`, `conditional_follow_up`, `insufficient_evidence`, and `deprioritize`.

If a dataset has one label class or fewer than 20 labeled rows, the trainer still writes a smoke model and a report warning that the model is not production-useful.

## Minimum Useful Size

For a useful source-span classifier, target at least 20 to 50 reviewed examples per common class.

For a useful triage ranker, target at least 50 to 100 reviewed performance records spanning all recommendation labels. Include negative and insufficient-evidence cases; otherwise the model will over-rank incomplete claims.

## Weak Labels Versus Human Labels

If no human labels are available, `build_training_dataset.py` writes weak rule labels and marks `label_source=weak_rule_label`.

Weak labels are useful for smoke testing the CLI and verifying that model files can be produced. They should not be treated as scientific truth.

Human-reviewed labels come from review sheets or reviewed gold outputs and are marked `label_source=human_review`. These labels improve the model because humans verify source grounding, correct field extraction mistakes, and apply evidence-gated recommendation rules.

## Commands

```powershell
C:\Python314\python.exe scripts\build_training_dataset.py --run-name final_pilot
C:\Python314\python.exe -m pip install scikit-learn joblib
C:\Python314\python.exe scripts\train_source_span_classifier.py --run-name final_pilot
C:\Python314\python.exe scripts\train_triage_ranker.py --run-name final_pilot
C:\Python314\python.exe scripts\predict_with_trained_models.py --run-name final_pilot
```
