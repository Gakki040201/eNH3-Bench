# Human Audit Protocol

Phase D adds a human audit and calibration layer for eNH3-BoundaryLedger. The goal is to compare rule BoundaryLedger outputs and optional LLM verification outputs against explicit human labels without overwriting either machine output.

Human labels are not automatic truth. A label becomes gold only when a reviewer marks the row as reviewed, all required human fields validate, and the reviewed CSV is imported with `--accept-as-gold`.

## What counts as reviewed

A record is reviewed only when all of the following are true:

- `human_review_status` is `reviewed`
- `human_text_class` is filled
- `human_maximum_supported_boundary` is filled
- `human_admissibility_status` is filled
- `human_experiment_decision` is filled

Use `needs_second_reviewer` when the source span is ambiguous. Use `excluded` for rows that should not enter calibration. Empty exported human fields are allowed, but empty reviewed records are invalid on import.

## Allowed labels

Human text classes:

- `primary_performance`
- `primary_performance_with_validation`
- `protocol_guideline`
- `review_table`
- `figure_caption`
- `reference_list`
- `contamination_detection_evidence`
- `contamination_reassignment_evidence`
- `computational_screening`
- `background_context`
- `unknown`

Human maximum supported boundaries:

- `unsupported_or_secondary`
- `product_admissibility`
- `cell_metric`
- `reactor_legibility`
- `process_partial`
- `plant_facing_insufficient`

Human admissibility statuses:

- `accept`
- `accept_with_controls`
- `metric_only_or_validation_incomplete`
- `secondary_only`
- `context_only_caption`
- `protocol_only`
- `negative_evidence`
- `computational_only`
- `reject`
- `reject_or_low_trust_provenance`
- `unclear_needs_second_reviewer`

Human experiment decisions:

- `priority_experiment`
- `control_required`
- `discard_as_secondary`
- `negative_warning`
- `protocol_reference`
- `insufficient_evidence`
- `needs_second_reviewer`

Human hidden taxes:

- `solvent_management_tax`
- `resistance_or_renewal_tax`
- `wetting_outlet_capture_tax`
- `hydrogen_logistics_tax`
- `contamination_tax`
- `measurement_matrix_tax`

Validation gate labels:

- `explicit`
- `missing`
- `unclear`
- `secondary_only`
- `not_applicable`

## Labeling guidance

For `human_text_class`, label what the source span is, not what the paper as a whole might contain. A protocol sentence stays `protocol_guideline`; a reference list stays `reference_list`; a review summary stays `review_table` even when it contains performance values.

For `human_maximum_supported_boundary`, label the strongest boundary the span can support from its own source text and provenance. Use `unsupported_or_secondary` for references, bibliography, review tables, metadata, and low-trust spans unless primary body evidence is explicitly paired.

For `human_admissibility_status`, separate acceptance from required controls. Use `accept_with_controls` or `metric_only_or_validation_incomplete` when useful metrics exist but validation, blank, NOx, contamination, or measurement-matrix fields are incomplete.

For `human_required_controls`, enter semicolon-separated controls such as `15N2 isotope validation; Ar/N2-free blank; NOx/nitrate/nitrite screening`.

For `human_hidden_tax`, enter semicolon-separated labels from the allowed hidden-tax list. Leave blank only when no hidden tax applies.

For `human_experiment_decision`, choose the next action: prioritize the experiment, require controls, discard as secondary, keep as negative warning, use as protocol reference, mark insufficient evidence, or request a second reviewer.

## Examples

Reference list: label `reference_list`, `unsupported_or_secondary`, and `reject` or `reject_or_low_trust_provenance`. Do not extract primary performance from citations.

Review table: label `review_table`, `unsupported_or_secondary`, and `secondary_only`. Trace the row to a primary source before stronger claim rights.

Figure caption: label `figure_caption` and normally `context_only_caption`. Promote only if the row is explicitly paired with primary body evidence.

Primary Li-NRR performance without 15N: label as primary performance if the span is primary text, but do not treat the N2-to-NH3 attribution as fully accepted. Require `15N2 isotope validation` and use `metric_only_or_validation_incomplete` or `accept_with_controls`.

Flow or HOR claim without product state: do not exceed `reactor_legibility`; require outlet product state, gas/liquid accounting, wetting or flooding disclosure, and hydrogen source/HOR controls.

Process claim without capture or solvent inventory: label at most `process_partial` or `plant_facing_insufficient`. Require capture route, solvent inventory, recycle or replacement, auxiliary loads, and hydrogen boundary closure.

## Import and calibration

Export a sheet:

```powershell
C:\Python314\python.exe scripts\export_human_audit_sheet.py --run-name final_pilot --llm-model deepseek-v4-pro --top-n 50 --priority-only
```

Generate local instructions:

```powershell
C:\Python314\python.exe scripts\export_review_instructions.py --run-name final_pilot
```

Import a reviewed sheet without gold export:

```powershell
C:\Python314\python.exe scripts\import_human_audit_sheet.py --run-name final_pilot --input data\human_audit\final_pilot\human_audit_sheet.reviewed.csv
```

Import reviewed labels as explicit human gold:

```powershell
C:\Python314\python.exe scripts\import_human_audit_sheet.py --run-name final_pilot --input data\human_audit\final_pilot\human_audit_sheet.reviewed.csv --accept-as-gold
```

Run calibration after reviewed records exist:

```powershell
C:\Python314\python.exe scripts\calibrate_boundary_ledger.py --run-name final_pilot
```
