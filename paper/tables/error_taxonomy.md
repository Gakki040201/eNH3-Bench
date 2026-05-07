# Error Taxonomy

| Error category | Signal | Interpretation |
| --- | --- | --- |
| Categorical disagreement | `evidence_type`, `isotope_validation`, `reliability_label` | Gold and prediction labels differ after normalization. |
| Numeric extraction error | none observed | Predicted numeric values are missing or outside tolerance. |
| Unsupported filled field | 0.0% | Prediction fills fields that are empty in gold. |
| Omitted supported field | 0.0% | Prediction leaves fields empty even though gold contains support. |
| Missing prediction entry | none observed | Aligned prediction record or field value is absent. |

