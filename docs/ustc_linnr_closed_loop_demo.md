# USTC Li-NRR Closed-Loop Demo

eNH3-BoundaryLedger remains reaction-family wide. It supports eNRR, LiNRR, NO3RR, NO2RR, NORR, mixed, and unclear nitrogen-source records for claim-rights and boundary-admissibility review.

The USTC wet-lab demonstration is LiNRR only by default. LiNRR is used because it is boundary dense: dry electrolyte handling, Li salt and solvent state, water/proton donor windows, SSC/PtAuSSC state, flow/wetting behavior, outlet product accounting, interphase resistance, and optional HOR/H2 coupling can all change what a claim is allowed to support.

## Route cards are not SOPs

Generated route cards are planning artifacts. They do not replace local lab SOPs, safety approvals, chemical handling rules, gas handling rules, or human scientific review.

The `ustc-linnr-realistic` profile records capability assumptions and SOP anchor points, but actual experimental execution must follow local USTC lab procedures.

## Minimum report fields

Patch C route cards include minimum report fields derived from the LiNRR SOP envelope:

- OCV, pump speed, voltage/current/runtime traces
- water content before/mid/after
- electrolyte resistance before/after
- SSC/PtAuSSC before-after photos
- IC NH4, HCl trap NH4, SSC soak solution NH4
- gas-line, liquid-line, leak, back-suction, and pump status
- SOP deviations and operator failure notes

## Claim boundary upgrade rules

A successful route can update only the measured BoundaryLedger fields it closes. Baseline repeatability can strengthen cell-metric support. Validation closure can strengthen product admissibility when mandatory controls pass. Flow, HOR, and outlet-product routes can support reactor legibility for the measured LiNRR setup.

No route card establishes plant/process readiness by itself. No route card generalizes beyond the tested LiNRR setup. Failed controls, missing raw records, or unresolved contamination block boundary upgrades.

## Non-LiNRR families

Non-LiNRR records can still produce literature and audit recommendations when explicitly included. They are not USTC wet-lab demonstration routes by default.
