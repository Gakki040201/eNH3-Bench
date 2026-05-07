# Field Schema

eNH3-Bench uses two core records: `PaperRecord` for paper-level metadata and
`EvidenceRecord` for evidence-grounded claims or validation statements.

## PaperRecord

| Field | Type | Allowed values | Example | Notes |
| --- | --- | --- | --- | --- |
| `paper_id` | `str` | Non-empty string | `P001` | Stable local identifier. |
| `title` | `str` | Any string | `Validation protocol for electrochemical ammonia synthesis` | Paper title. |
| `doi` | `str | None` | DOI or `None` | `10.0000/example1` | Use placeholder DOI only for examples. |
| `year` | `int | None` | Four-digit year or `None` | `2024` | Publication or preprint year. |
| `journal` | `str | None` | Any string or `None` | `Example Journal` | Journal, server, or venue. |
| `article_type` | `str` | `primary_research`, `review`, `perspective`, `protocol`, `reassessment`, `preprint`, `unknown` | `protocol` | Describes the publication type. |
| `open_access` | `bool | None` | `true`, `false`, or `None` | `true` | Whether the paper is openly accessible. |
| `source_file` | `str | None` | Path or `None` | `data/papers/P001.txt` | Local source file reference when available. |
| `notes` | `str | None` | Any string or `None` | `Example record` | Curator notes. |

## EvidenceRecord

| Field | Type | Allowed values | Example | Notes |
| --- | --- | --- | --- | --- |
| `evidence_id` | `str` | Non-empty string | `E001` | Stable local evidence identifier. |
| `paper_id` | `str` | Non-empty string | `P001` | Links to `PaperRecord.paper_id`. |
| `source_span` | `str` | Non-empty string | `The authors report 15N2 validation...` | Exact supporting text span. |
| `source_section` | `str` | `abstract`, `results`, `methods`, `supplementary`, `table`, `figure_caption`, `review_table`, `unknown` | `methods` | Source location for the span. |
| `reaction_family` | `str` | `eNRR`, `LiNRR`, `NO3RR`, `NO2RR`, `NORR`, `mixed`, `unclear` | `LiNRR` | Main reaction family. |
| `nitrogen_source` | `str` | `N2`, `15N2`, `NO3-`, `NO2-`, `NO`, `NOx`, `catalyst_impurity`, `unknown` | `15N2` | Reported nitrogen source. |
| `catalyst` | `str | None` | Any string or `None` | `Ru/C` | Reported catalyst. |
| `catalyst_class` | `str | None` | Any string or `None` | `metal catalyst` | Coarse catalyst category. |
| `electrolyte` | `str | None` | Any string or `None` | `0.1 M KOH` | Electrolyte composition. |
| `reactor_type` | `str | None` | Any string or `None` | `H-cell` | Reactor or cell type. |
| `membrane` | `str | None` | Any string or `None` | `Nafion 117` | Separator or membrane. |
| `potential_value` | `float | None` | Numeric value or `None` | `-0.2` | Applied potential value. |
| `potential_unit` | `str | None` | Any string or `None` | `V` | Potential unit. |
| `potential_reference` | `str | None` | Any string or `None` | `vs RHE` | Reference electrode scale. |
| `current_density_mA_cm2` | `float | None` | Numeric value or `None` | `15.0` | Current density in mA cm-2. |
| `faradaic_efficiency_percent` | `float | None` | Numeric value or `None` | `62.0` | Faradaic efficiency as percent. |
| `nh3_yield_value` | `float | None` | Numeric value or `None` | `4.2` | Reported ammonia yield before normalization. |
| `nh3_yield_unit` | `str | None` | Any string or `None` | `ug h-1 cm-2` | Original reported yield unit. |
| `nh3_yield_normalized_value` | `float | None` | Numeric value or `None` | `4.2` | Normalized yield value. |
| `nh3_yield_normalized_unit` | `str | None` | Any string or `None` | `ug h-1 cm-2` | Benchmark-normalized unit. |
| `energy_efficiency_percent` | `float | None` | Numeric value or `None` | `12.5` | Energy efficiency as percent. |
| `stability_hours` | `float | None` | Numeric value or `None` | `24.0` | Stability test duration. |
| `detection_method` | `str | None` | Any string or `None` | `indophenol blue and ion chromatography` | NH3 detection method. |
| `isotope_validation` | `str` | `yes`, `no`, `unclear`, `not_applicable` | `yes` | Whether isotope labeling supports the claim. |
| `blank_control` | `str` | `yes`, `no`, `unclear` | `yes` | Whether blank controls are reported. |
| `contamination_control` | `str` | `yes`, `no`, `unclear` | `yes` | Whether contamination controls are reported. |
| `nox_screening` | `str` | `yes`, `no`, `unclear` | `yes` | Whether NOx species are screened. |
| `reliability_label` | `str` | `A`, `B`, `C`, `D`, `Reject` | `B` | Gold reliability label. |
| `evidence_type` | `str` | `primary_claim`, `control_experiment`, `negative_result`, `reassessment`, `review_summary` | `primary_claim` | Evidence category. |
| `gold_notes` | `str | None` | Any string or `None` | `Strong controls but limited stability data.` | Curator rationale. |

## Example Evidence Record

```json
{
  "evidence_id": "E002",
  "paper_id": "P002",
  "source_span": "The Li-mediated N2 reduction experiment reported 62% FE for NH3 with 15N2 confirmation.",
  "source_section": "results",
  "reaction_family": "LiNRR",
  "nitrogen_source": "15N2",
  "catalyst": "stainless steel",
  "catalyst_class": "metal electrode",
  "electrolyte": "Li salt in ether electrolyte",
  "reactor_type": "divided cell",
  "membrane": "porous separator",
  "potential_value": null,
  "potential_unit": null,
  "potential_reference": null,
  "current_density_mA_cm2": 5.0,
  "faradaic_efficiency_percent": 62.0,
  "nh3_yield_value": 10.5,
  "nh3_yield_unit": "nmol s-1 cm-2",
  "nh3_yield_normalized_value": null,
  "nh3_yield_normalized_unit": null,
  "energy_efficiency_percent": null,
  "stability_hours": 6.0,
  "detection_method": "indophenol blue and 1H NMR",
  "isotope_validation": "yes",
  "blank_control": "yes",
  "contamination_control": "yes",
  "nox_screening": "unclear",
  "reliability_label": "B",
  "evidence_type": "primary_claim",
  "gold_notes": "Example-only record, not real literature evidence."
}
```
