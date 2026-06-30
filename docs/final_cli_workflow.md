# Final CLI Workflow

All commands are local. They do not call APIs or require a GPU.

## 1. Run Final Pilot

```powershell
C:\Python314\python.exe scripts\run_final_triage_pipeline.py ^
  --input-dir input_raw ^
  --markdown-dir input_markdown ^
  --run-name final_pilot ^
  --converter docling ^
  --top-n 30 ^
  --max-per-paper 6 ^
  --force-reconvert
```

Use `--converter basic` for a no-extra-dependency text/Markdown smoke run.

## 2. Inspect Outputs

```powershell
C:\Python314\python.exe scripts\check_final_outputs.py --run-name final_pilot
```

Open:

- `data\reports\experiment_triage_report.final_pilot.md`
- `data\reports\experiment_triage_table.final_pilot.csv`
- `data\ledgers\final_pilot\classified_spans.csv`

## 3. Build Training Dataset

```powershell
C:\Python314\python.exe scripts\build_training_dataset.py --run-name final_pilot
```

This creates:

- `data\training\source_span_training.final_pilot.csv`
- `data\training\triage_training.final_pilot.csv`

## 4. Train Models

Install the optional local training packages if needed:

```powershell
C:\Python314\python.exe -m pip install scikit-learn joblib
```

Then run:

```powershell
C:\Python314\python.exe scripts\train_source_span_classifier.py --run-name final_pilot
C:\Python314\python.exe scripts\train_triage_ranker.py --run-name final_pilot
```

## 5. Predict Next Run

After training, run predictions against the same run or another run with compatible outputs:

```powershell
C:\Python314\python.exe scripts\predict_with_trained_models.py --run-name final_pilot
```

Outputs:

- `data\reports\model_predictions.final_pilot.csv`
- `data\reports\model_predictions.final_pilot.md`

## 6. Export Paper Tables

For the existing domain summary workflow after reviewed gold exists:

```powershell
C:\Python314\python.exe scripts\export_domain_report.py ^
  --gold data\gold\gold.v0.2.reviewed.jsonl ^
  --output-md data\reports\domain_report.v0.2.md ^
  --output-table paper\tables\domain_summary.v0.2.md
```

The triage table for the final run is exported by the final pipeline and can be regenerated with:

```powershell
C:\Python314\python.exe scripts\export_experiment_triage_report.py --run-name final_pilot
```
