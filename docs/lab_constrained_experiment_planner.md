# Lab-Constrained Experiment Planner

## 1. Why literature criticism is not enough

BoundaryLedger identifies what published claims are allowed to support. Phase F0 turns those gaps into structured route cards that a real lab can review, edit, and execute under explicit capability constraints.

## 2. BoundaryLedger to experiment route conversion

The planner reads claim-rights records, hidden-tax records, provenance flags, optional LLM disagreements, reviewed human audit records, and any imported experiment results. It then proposes route types such as validation-gap closure, electrolyte-window testing, flow/wetting mapping, HOR boundary tests, and contamination stress tests.

## 3. USTC lab profile

The lab profile is an editable JSON/YAML capability file. Conservative defaults avoid assuming access to 15N2, NOx analytics, gas-phase NH3 capture, flow cells, GDEs, HOR coupling, or special reactors unless the profile explicitly says they are available.

Patch C adds an optional `ustc-linnr-realistic` profile template grounded in the USTC Li-NRR SOP capability envelope. It enables flow/SSC/HOR, glovebox and drying, Karl Fischer water analysis, IC sampling, gas/liquid line handling, SSC/PtAuSSC preparation, and post-experiment reporting fields, while keeping `isotopic_15N2_available=false` and `can_do_15N_control=false` until edited.

```powershell
C:\Python314\python.exe scripts\init_lab_profile.py --profile-template ustc-linnr-realistic --output data\lab_profiles\ustc_linnr_profile.local.yaml --overwrite
```

## 4. Route priority scoring

Routes gain priority when they close common validation gaps, test frequent hidden taxes, are feasible in the lab profile, address LLM/rule disagreements, or link to human-reviewed priority experiments. Routes lose priority when critical capabilities are missing, evidence is mostly secondary, or required controls are infeasible.

## 5. Required controls

Route cards list required, feasible, and infeasible controls separately. Missing mandatory controls prevent a result from being marked as successful during result import.

## 6. Hidden-tax targeted experiments

Hidden taxes become testable route targets: solvent management, interphase resistance, wetting/outlet capture, hydrogen logistics, contamination, and incomplete measurement matrices.

## 7. LLM role and limitations

LLM refinement is optional. It can refine wording, rationale, and diagnosis-tree text only. It cannot add absent lab capabilities, remove mandatory controls, or upgrade route priority when critical controls are unavailable.

## 8. Experiment result import

The result template preserves raw values as strings when units are unclear. Import validation checks route IDs, status labels, failed mandatory controls, and missing required measurements.

## 9. Prediction-vs-experiment loop

Closed-loop evaluation compares generated routes with imported results, counting success, partial, failed, invalid, hidden-tax confirmations, control failures, and next-round route suggestions.

## 10. How this supports a high-level manuscript

Phase F0 connects literature admissibility to executable, auditable experiments. It supports a manuscript argument that eNH3 literature mining can drive closed-loop, lab-constrained experimental planning without treating LLM output or unreviewed literature as gold evidence.

## F0.0 Lab capability grounding

The realistic USTC Li-NRR profile records SOP-relevant capabilities but does not contain a wet-lab protocol. Local lab safety review and approved SOPs govern actual execution.

## F0.1 Admission gate

LiNRR is the default wet-lab demonstration family. Other eNH3 reaction families remain supported by BoundaryLedger and can produce literature/audit recommendations, but they are not USTC wet-lab route cards by default.

## F0.2 Baseline repeatability

`baseline_repeatability` establishes reproducibility before variable screening. It requires three water-content measurements, electrolyte resistance before/after, SSC/PtAuSSC photos, and voltage/current/runtime reporting.

## F0.3 Electrolyte, water, and proton donor windows

`water_content_window`, `proton_donor_window`, and `salt_solvent_window` target LiNRR solvent-management uncertainty without claiming process readiness.

## F0.4 Interphase resistance

`interphase_resistance` adds before/after resistance, photos, electrolyte color, and failure-mode reporting to diagnose renewal and passivation burdens.

## F0.5 Flow, wetting, and product state

`flow_wetting` and `outlet_product_split` track gas/liquid/trap/SSC ammonia accounting plus leak, back-suction, and pump status.

## F0.6 HOR proton economy

`HOR_proton_economy` requires H2-off and HOR-off controls and records anode/cathode potential and H2 observations when HOR capabilities are present.

## F0.7 Result import and claim update

Imported result templates preserve SOP-derived raw fields such as OCV, pump speed, water content before/mid/after, IC NH4, HCl trap NH4, SSC soak NH4, photos, line status, and operator failure notes. A successful route can update only the measured boundary fields it actually closes.
