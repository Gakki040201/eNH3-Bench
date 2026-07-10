# Lab-Constrained Experiment Planner

## 1. Why literature criticism is not enough

BoundaryLedger identifies what published claims are allowed to support. Phase F0 turns those gaps into structured route cards that a real lab can review, edit, and execute under explicit capability constraints.

## 2. BoundaryLedger to experiment route conversion

The planner reads claim-rights records, hidden-tax records, provenance flags, optional LLM disagreements, reviewed human audit records, and any imported experiment results. It then proposes route types such as validation-gap closure, electrolyte-window testing, flow/wetting mapping, HOR boundary tests, and contamination stress tests.

## 3. USTC lab profile

The lab profile is an editable JSON/YAML capability file. Conservative defaults avoid assuming access to 15N2, NOx analytics, gas-phase NH3 capture, flow cells, GDEs, HOR coupling, or special reactors unless the profile explicitly says they are available.

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
