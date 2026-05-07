# Evaluation Protocol

eNH3-Bench compares prediction JSONL files against gold `EvidenceRecord` JSONL
files. Records are aligned by `evidence_id`; unmatched gold records count as
missing predictions for field-level evaluation.

## Inputs

Default example evaluation:

```bash
python scripts/run_rule_baseline.py
python scripts/evaluate_predictions.py
```

The evaluator does not call APIs, scrape websites, parse PDFs, or require cloud
models. It reads local JSONL files only.

## Categorical Fields

Categorical fields are evaluated by normalized exact match:

- `reaction_family`
- `nitrogen_source`
- `isotope_validation`
- `blank_control`
- `contamination_control`
- `nox_screening`
- `reliability_label`
- `evidence_type`

Normalization trims whitespace, collapses repeated whitespace, and compares
case-insensitively. Accuracy is `correct / total gold records`.

## Numeric Fields

Numeric fields are evaluated with absolute or relative tolerance:

- `faradaic_efficiency_percent`
- `nh3_yield_value`
- `energy_efficiency_percent`
- `stability_hours`
- `potential_value`

The report includes the number of gold values, values within tolerance, missing
predictions, mean absolute error, and maximum absolute error. Numeric accuracy
is `within_tolerance / total_gold_values`, excluding gold records where the
field is empty.

Default tolerances are intentionally narrow:

- Potential values: absolute tolerance of `0.01`.
- Faradaic and energy efficiency: absolute tolerance of `0.1`.
- NH3 yield and stability hours: relative tolerance of `0.01`.

## Hallucination Rate

Hallucination rate measures unsupported filled fields:

```text
non-empty prediction where the aligned gold field is empty
/ all non-empty prediction field values
```

This catches prediction fields that add catalyst, metric, control, or label
claims not present in the gold record.

## Missing Field Rate

Missing field rate measures omitted gold-supported fields:

```text
empty prediction where the aligned gold field is non-empty
/ all non-empty gold field values
```

This catches extraction failures where the gold record contains a supported
claim but the prediction leaves the field blank.

## Reports

`scripts/evaluate_predictions.py` writes:

- `data/reports/evaluation_report.example.json`
- `data/reports/evaluation_report.example.md`

The Markdown report includes field-level accuracy, numeric error summaries,
hallucination rate, missing field rate, and a brief interpretation suitable for
benchmark-paper development notes.
