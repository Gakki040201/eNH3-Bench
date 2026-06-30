# VS Code Minimal Training Guide

This project does not need a UI app. VS Code is only used as an editor and terminal.

## Open The Repo

1. Open VS Code.
2. Choose `File > Open Folder`.
3. Select the eNH3-Bench repository folder.
4. Open the integrated terminal with `Terminal > New Terminal`.

## Run The Final Pipeline

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

For a text-only smoke test, use `--converter basic`.

## Inspect Outputs

Open these files from the VS Code Explorer:

- `data\reports\experiment_triage_report.final_pilot.md`
- `data\reports\experiment_triage_table.final_pilot.csv`
- `data\ledgers\final_pilot\classified_spans.csv`

## Build Training CSVs

```powershell
C:\Python314\python.exe scripts\build_training_dataset.py --run-name final_pilot
```

Inspect:

- `data\training\source_span_training.final_pilot.csv`
- `data\training\triage_training.final_pilot.csv`

## Train Small Local Models

```powershell
C:\Python314\python.exe -m pip install scikit-learn joblib
C:\Python314\python.exe scripts\train_source_span_classifier.py --run-name final_pilot
C:\Python314\python.exe scripts\train_triage_ranker.py --run-name final_pilot
```

The models are CLI artifacts saved under `models\`. VS Code is not doing the training; the integrated terminal is running the same CLI commands as any other shell.
