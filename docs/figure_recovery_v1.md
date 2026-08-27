# LiNRR Figure Data Recovery v1

This independent layer recovers provenance-bearing figure-point candidates. It does not change audit schema 0.13, historical LiNRR outputs, Gold, paper IDs, M017/M018, target-admission rules, or model-training behavior.

## Scientific contract

The flow is:

`local PDF -> figure manifest -> vector inventory -> calibration -> candidate points -> QA overlay -> same-paper binding review`

PyMuPDF is the native implementation. Captions and tick labels use born-digital PDF text geometry when present. Raster rendering is restricted to the exact figure/panel bbox and records the PDF bbox, DPI, pixel dimensions, and coordinate transform. The supported render candidates are 400 and 600 DPI; neither is presumed superior before benchmarking.

Every point remains `FIGURE_POINT_CANDIDATE`. The only binding methods are `SAME_FIGURE_SERIES`, `SAME_CAPTION_DEFINED_SERIES`, `SAME_METHOD_DEFINED_SERIES`, and `DETERMINISTIC_SAME_PAPER_INHERITANCE`. The schema rejects cross-paper binding.

Extraction status is limited to `AUTO_PASS`, `REVIEW_REQUIRED`, and `FAILED_UNSUPPORTED`. During this v1 pilot, automatic vector results remain `REVIEW_REQUIRED` until source-data benchmarks establish an acceptance gate. Ambiguous axes, axis scale, panel boundaries, series separation, legend mapping, or OCR ticks fail closed.

## Commands

Build a source-data benchmark (10-20 figures):

```powershell
python scripts/build_figure_recovery_benchmark_v1.py `
  --source-data-zip <local-source-data.zip> `
  --supplementary-pdf <local-si.pdf> `
  --paper-id P0092 `
  --bundle-id P0092_LOCAL_CURATED `
  --source-asset-id P0092_SI `
  --limit 15
```

Run a local pilot from an asset index:

```powershell
python scripts/recover_linrr_figure_data_v1.py `
  --asset-index <local-assets.json> `
  --benchmark-manifest <benchmark_manifest.json> `
  --limit 20 `
  --dpi 400 --dpi 600
```

The asset index is an object with an `assets` list. Each row contains `paper_id`, `bundle_id`, `source_asset_id`, and an absolute local `pdf_path`. The CLI enforces a maximum 40-figure pilot and never calls a web API or an LLM.

Runtime outputs are written under `F:\eNH3_Bench_Work\02_Data\Figure_Recovery\LiNRR_Figure_Recovery_v1`. Benchmark data and reports are written under `F:\eNH3_Bench_Work\04_Exports\Reports\LiNRR_Figure_Recovery_v1`. They are not repository artifacts.

Each attempted figure/panel produces:

- `qa_overlay.png`
- `calibration.json`
- `points.csv`
- `extraction_manifest.json`

Vector attempts also preserve `vector_inventory.json`; optional independent results are recorded separately.

## Third-party evaluation boundary

Third-party checkouts and weights live only under `F:\eNH3_Bench_Work\99_Scratch\Figure_Recovery_ThirdParty`.

| Project | Evaluated commit | License | Role |
| --- | --- | --- | --- |
| adamkucharski/pdf2plot | `99a8ee1d1e24a0859fea1cd06011280734ab82cb` | MIT | Architecture reference for PDF path inventory and calibration |
| jztan/pdf-mcp | `720a4fe6af83d390a681daae8bcaaa94e2a14b87` | MIT | Optional local `pdf_extract_chart` cross-check |
| t29mato/AutoLineDigitizer | `83d018d0794f9d03b69601b4a03cf4ae11cc543c` | MIT | Optional isolated ChartDete + LineFormer raster adapter |
| tdsone/extract-line-chart-data | `810a5ea96b18bd6f09757bf11e87326745f91fc6` | repository checkout inspected; dependency licenses require separate review | ChartDete/LineFormer architecture reference |
| t29mato/AutoPlot-Digitizer | `e95018b4c8afd0f8a58d4e0abd5c5a14171350c6` | MIT | Optional raster scatter/marker candidate |
| anadb/PlotDigitizer | `91a68a02b3b1983f42eac8d719babe6e68629a65` | repository checkout inspected | Manual correction/QA candidate |

No third-party code was copied or adapted into the package. The native implementation was written independently after studying the architectures. Model weights are neither downloaded by the pipeline nor committed. AutoLineDigitizer base/battery results are declined when the isolated environment or checksumable weights are absent. WebPlotDigitizer is not vendored, and no cloud AI assistance is used.

`pdf-mcp` runs through a subprocess adapter. Its result, version, decline reason, and agreement field are recorded, but it cannot promote native scientific data or resolve an ambiguous chart.

## Numeric authority and QA

Only source data, structured tables, explicit text, vector geometry, or raster geometry may supply numeric values. VLM table generation is not a numeric source class. Figure/caption/context text can identify a series but cannot become primary positive measurement support.

The QA overlay reprojects candidate points on the exact rendered region. Benchmark metrics include series assignment, point precision/recall, normalized x/y MAE, maximum absolute errors, FE percentage-point error where applicable, missing/extra point rate, axis scale, and legend labels. Reports show empirical distributions before any PASS threshold is frozen.
