# Lowest-Level CLI Workflow

This workflow is for users with minimal programming experience. It automates
everything before human verification while keeping the benchmark local and
no-API.

## What You Need

- Local `.md`, `.txt`, or optionally `.docx` files.
- `C:\Python314\python.exe`
- No API keys.
- No PDF parser.
- No UI.

PDF conversion is intentionally deferred. Convert PDFs to Markdown manually for
now, or wait for a future adapter.

## Step 1: Put Files In `input_raw/`

Place local `.md`, `.txt`, or `.docx` files in:

```powershell
input_raw\
```

Raw PDFs and full converted paper text should stay local and private unless the
source license permits redistribution.

## Step 2: Convert Local Documents To Markdown

```powershell
C:\Python314\python.exe scripts\convert_local_documents.py
```

This writes Markdown files to `input_markdown/` and a conversion manifest to
`data/reports/document_conversion_manifest.json`.

## Step 3: Run The Minimal Review Pipeline

```powershell
C:\Python314\python.exe scripts\run_minimal_review_pipeline.py
```

This creates:

- `data/candidates/candidate_spans.v0.2.jsonl`
- `data/drafts/draft_evidence.v0.2.jsonl`
- `data/audit/audit_packet.v0.2.md`
- `data/audit/review_sheet.v0.2.csv`
- `data/audit/HUMAN_VERIFICATION_INSTRUCTIONS.md`
- `data/reports/workflow_manifest.v0.2.json`

## Step 4: Human Verification

Open:

- `data/audit/audit_packet.v0.2.md`
- `data/audit/review_sheet.v0.2.csv`

For each row, mark:

- `human_decision`
- `include_in_gold`
- `reliability_override` if needed
- `correction_notes` if uncertainty remains

Draft evidence is not gold until this step is complete.

## Step 5: Merge Reviewed Gold

```powershell
C:\Python314\python.exe scripts\merge_reviewed_gold.py
```

This writes reviewed records to `data/gold/gold.v0.2.reviewed.jsonl`.

## Step 6: Check The Gold Dataset

```powershell
C:\Python314\python.exe scripts\check_gold_dataset.py --papers data\papers\papers.v0.2.template.csv --spans data\candidates\candidate_spans.v0.2.jsonl --gold data\gold\gold.v0.2.reviewed.jsonl
```

## Step 7: Run Evaluation

After predictions exist for the reviewed dataset, run the evaluation script with
the reviewed gold file and prediction file.

```powershell
C:\Python314\python.exe scripts\evaluate_predictions.py --gold data\gold\gold.v0.2.reviewed.jsonl --pred data\predictions\your_predictions.jsonl
```
