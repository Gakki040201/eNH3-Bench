# Main Results Tables

## Method Comparison

| Method | Mean categorical accuracy | Mean numeric accuracy | Hallucination rate | Missing field rate |
| --- | --- | --- | --- | --- |
| rule_baseline | 79.2% | 100.0% | 0.0% | 0.0% |

## Field Performance

| Field | Type | Accuracy | Support | Missing predictions | Criterion |
| --- | --- | --- | --- | --- | --- |
| `blank_control` | categorical | 100.0% | 3/3 | 0 | exact match |
| `contamination_control` | categorical | 100.0% | 3/3 | 0 | exact match |
| `evidence_type` | categorical | 66.7% | 2/3 | 0 | exact match |
| `isotope_validation` | categorical | 66.7% | 2/3 | 0 | exact match |
| `nitrogen_source` | categorical | 100.0% | 3/3 | 0 | exact match |
| `nox_screening` | categorical | 100.0% | 3/3 | 0 | exact match |
| `reaction_family` | categorical | 100.0% | 3/3 | 0 | exact match |
| `reliability_label` | categorical | 0.0% | 0/3 | 0 | exact match |
| `energy_efficiency_percent` | numeric | 0.0% | 0/0 | 0 | within tolerance |
| `faradaic_efficiency_percent` | numeric | 100.0% | 2/2 | 0 | MAE=0, max=0 |
| `nh3_yield_value` | numeric | 100.0% | 1/1 | 0 | MAE=0, max=0 |
| `potential_value` | numeric | 100.0% | 1/1 | 0 | MAE=0, max=0 |
| `stability_hours` | numeric | 100.0% | 1/1 | 0 | MAE=0, max=0 |

## Reliability Label Summary

| Reliability-label metric | Value |
| --- | --- |
| Accuracy | 0.0% |
| Correct labels | 0 |
| Total records | 3 |
| Missing predictions | 0 |

