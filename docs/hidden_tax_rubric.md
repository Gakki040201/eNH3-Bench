# Hidden-Tax Rubric

Hidden taxes are boundary burdens that can be hidden behind an apparently strong eNH3 claim. They do not prove a claim false by themselves. They flag what must be measured or controlled before a claim can be compared across product, reactor, or process boundaries.

## solvent_management_tax

Triggered by electrolyte, solvent, donor, additive, water, Li salt, or related inventory language. Missing disclosures commonly include solvent inventory, replacement or recycle, donor consumption, and electrolyte composition drift.

## resistance_or_renewal_tax

Triggered by SEI, interphase, passivation, resistance, impedance, or renewal language. Missing disclosures commonly include impedance over runtime, passivation onset, renewal schedule, and whether the same cell can sustain the reported performance.

## wetting_outlet_capture_tax

Triggered by flow, GDE, SSC, gas diffusion, outlet, flooding, wetting, or capture language. Missing disclosures commonly include outlet product state, gas/liquid product split, wetting/flooding diagnosis, and capture efficiency.

## hydrogen_logistics_tax

Triggered by HOR, hydrogen oxidation, H2, or proton-economy language. Missing disclosures commonly include the hydrogen source boundary, H2 consumption, HOR-off controls, and whether hydrogen logistics are inside the claimed system boundary.

## contamination_tax

Triggered by contamination, NOx, nitrate, nitrite, background ammonia, false-positive, or impurity language. Missing disclosures commonly include NOx/nitrate/nitrite screening, background ammonia, blanks, and contaminant mass balance.

## measurement_matrix_tax

Triggered when FE is reported without the broader matrix needed for boundary comparison: NH3 yield, energy efficiency, voltage or potential, current density, runtime or stability, and product state.

## Hidden tax under low-trust provenance

Reference, bibliography, front-matter, metadata, and copyright-note text should not trigger full domain-tax cascades from glued keywords or literature titles. Under low-trust provenance, performance-like text can still receive `measurement_matrix_tax`, and explicit contamination/background-ammonia language can still receive `contamination_tax`.

Domain-specific taxes such as `solvent_management_tax`, `resistance_or_renewal_tax`, `wetting_outlet_capture_tax`, and `hydrogen_logistics_tax` require primary body/results/methods evidence or an explicitly primary-admissible record. Primary body text is required before low-trust text can establish reactor, solvent, hydrogen, or process-boundary hidden taxes.

## Secondary-context hidden tax constraints

Review tables, ordinary tables, and secondary summaries are context records. They can flag audit needs, but they cannot establish primary hidden-tax burdens without paired primary body evidence.

For `review_table`, `table`, and `secondary_review` provenance, keyword-only domain cascades are constrained. Electrolyte, solvent, SEI, resistance, flow, GDE, outlet, capture, HOR, or H2 terms do not by themselves trigger `solvent_management_tax`, `resistance_or_renewal_tax`, `wetting_outlet_capture_tax`, or `hydrogen_logistics_tax`. Performance-like table context can retain `measurement_matrix_tax` as an audit hint, and explicit contamination, NOx, nitrate, nitrite, or background-ammonia language can retain `contamination_tax`.

These records must carry `primary_body_text_pairing_required` and should be paired with body/results/methods text before any domain-specific hidden tax is treated as established evidence.

Severity is low, medium, or high. High severity is used for multiple hidden taxes, high-FE incomplete metric claims, or contamination paired with incomplete metric disclosure.
