# Ultimate CLI Smoke Test

Use this smoke test on local non-copyrighted toy files or short notes.

## 1. Put Files Into `input_raw/`

```powershell
New-Item -ItemType Directory -Force input_raw
Set-Content input_raw\toy_linrr.txt "Li-mediated N2 reduction produced NH3 at 10.5 nmol s-1 cm-2 with 62% FE, 15N2 isotope labeling, and blank control."
Set-Content input_raw\toy_no3rr.txt "Nitrate reduction to ammonia reached 85% Faradaic efficiency using NO3- electrolyte."
```

## 2. Run The Unified Runner

```powershell
C:\Python314\python.exe scripts\run_enh3_scholar.py --input-dir input_raw --markdown-dir input_markdown --run-name v0.2 --top-n 8 --max-per-paper 3 --stop-at audit
```

## 3. Open Audit Packet And Review Sheet

Open:

- `data/audit/audit_packet.v0.2.md`
- `data/audit/review_sheet.v0.2.csv`

## 4. Merge Reviewed Gold

After filling the review sheet:

```powershell
C:\Python314\python.exe scripts\merge_reviewed_gold.py
```

## 5. Check Dataset

```powershell
C:\Python314\python.exe scripts\check_gold_dataset.py --papers data\papers\papers.v0.2.template.csv --spans data\candidates\candidate_spans.v0.2.jsonl --gold data\gold\gold.v0.2.reviewed.jsonl
```

## 6. Evaluate Predictions

```powershell
C:\Python314\python.exe scripts\evaluate_predictions.py --gold data\gold\gold.v0.2.reviewed.jsonl --pred data\predictions\your_predictions.jsonl
```

## 7. Export Domain Report

```powershell
C:\Python314\python.exe scripts\export_domain_report.py --gold data\gold\gold.v0.2.reviewed.jsonl --output-md data\reports\domain_report.v0.2.md
```
