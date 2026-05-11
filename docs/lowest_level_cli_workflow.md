# Lowest-Level CLI Workflow

This workflow is for users with minimal programming experience. It automates
everything before human verification while keeping the benchmark local and
no-API.

## What You Need

- Local `.md`, `.txt`, `.docx`, or text-based `.pdf` files.
- `C:\Python314\python.exe`
- No API keys.
- No UI.

DOCX conversion uses optional `python-docx` when installed. Text-based PDF
conversion should use Docling first when installed, then MarkItDown, then
PyMuPDF/basic fallback. Scanned PDFs are unsupported in this phase and should be
manually converted or deferred to a future Docling/OCR workflow.

## Step 1: Put Files In `input_raw/`

Place local `.md`, `.txt`, `.docx`, or text-based `.pdf` files in:

```powershell
input_raw\
```

Raw files and full converted Markdown should stay local and private unless the
source license permits redistribution.

## Step 2: Convert Local Documents To Markdown

```powershell
C:\Python314\python.exe scripts\convert_local_documents.py
```

This writes Markdown files to `input_markdown/` and a conversion manifest to
`data/reports/document_conversion_manifest.json`.

Unsupported files are recorded in the manifest instead of stopping the run.
Install optional local packages only if needed:

```powershell
C:\Python314\python.exe -m pip install docling markitdown pymupdf
```

Recommended high-quality Docling-first run:

```powershell
C:\Python314\python.exe scripts\run_enh3_scholar.py ^
  --input-dir input_raw ^
  --markdown-dir input_markdown ^
  --run-name v0.2_docling ^
  --top-n 20 ^
  --max-per-paper 5 ^
  --converter docling ^
  --force-reconvert ^
  --clean-markdown ^
  --stop-at audit
```

Fallback auto run:

```powershell
C:\Python314\python.exe scripts\run_enh3_scholar.py ^
  --input-dir input_raw ^
  --markdown-dir input_markdown ^
  --run-name v0.2_auto ^
  --top-n 20 ^
  --max-per-paper 5 ^
  --converter auto ^
  --force-reconvert ^
  --clean-markdown ^
  --stop-at audit
```

Use Docling first for paper PDFs. Use `auto` if Docling is not installed or a
specific file fails. MarkItDown is inspired by generic skill-style document
processing workflows, but eNH3-Bench uses it only as an optional Python package,
not as vendored skill code.

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

## Skill-Style Boundary

This conversion layer follows a skill-style document-processing workflow, but it
does not import, vendor, or depend on `scientific-agent-skills`. Generic skills
can guide Codex behavior conceptually, while eNH3-Bench remains self-contained.
Human verification is still required before any draft record becomes gold.
Audit quality depends on conversion quality, and full converted Markdown should
remain local/private unless licensed.
