# Reaction-Family Profiles

eNH3-BoundaryLedger is an eNH3-wide claim-rights and boundary-admissibility engine. It is not Li-NRR-only. The platform supports electrochemical ammonia synthesis records across eNRR, LiNRR, NO3RR, NO2RR, NORR, mixed, and unclear nitrogen-source systems.

LiNRR is the current wet-lab demonstration track because it is boundary dense: solvent inventory, Li salt, water/proton donor windows, SEI/interphase renewal, GDE/SSC wetting, gas/liquid product accounting, and optional HOR/H2 coupling can all change what a claim is allowed to support.

## Supported families

- `eNRR`: N2-to-NH3 electrochemical nitrogen reduction. Product admission emphasizes 15N2 validation, blanks, NOx/contamination controls, and ammonia quantification.
- `LiNRR`: Li/Li+-mediated N2-to-NH3. It inherits N2 validation gates and adds Li salt, solvent, proton donor, water content, interphase, wetting, product-state, and HOR/H2 boundary fields.
- `NO3RR`: nitrate-to-NH3. It requires nitrate/nitrite source accounting and nitrogen mass balance rather than 15N2 by default.
- `NO2RR`: nitrite-to-NH3. It follows the same source-accounting logic as nitrate reduction, with nitrite source definition.
- `NORR`: NO-to-NH3. It emphasizes NO source purity, NOx balance, gas handling blanks, and ammonia quantification.
- `mixed`: multiple or ambiguous nitrogen sources. It requires nitrogen-source disambiguation before stronger claim rights.
- `unclear`: conservative fallback when the source span does not identify the ammonia nitrogen source.

## Validation gates

For eNRR and LiNRR, 15N2 isotope validation remains central to N2-to-NH3 claim rights. For NO3RR, NO2RR, and NORR, the default validation problem is source accounting and nitrogen balance, not 15N2.

Mixed and unclear records add `nitrogen_source_disambiguation` as a missing boundary field until the source is clarified.

## Hidden taxes

LiNRR can trigger the full current hidden-tax set: solvent management, interphase/resistance renewal, wetting/outlet capture, hydrogen logistics, contamination, and measurement-matrix taxes.

NO3RR, NO2RR, NORR, mixed, and unclear profiles are conservative. Explicit nitrate/nitrite/NO or contamination context can still create contamination and measurement-matrix audit needs, but LiNRR-specific solvent/interphase/HOR taxes are not treated as profile-default burdens for nitrate, nitrite, or NO reduction.

## Experiment planning

The experiment planner defaults to the USTC LiNRR wet-lab demonstration scope:

```powershell
C:\Python314\python.exe scripts\generate_experiment_routes.py --run-name final_pilot --lab-profile data\lab_profiles\ustc_linnr_profile.yaml
```

The default is equivalent to `--reaction-family LiNRR --lab-demo-only`. Other families can be included for literature/audit planning with `--include-families`, and `--no-lab-demo-only` can be used when the caller explicitly wants non-LiNRR recommendations emitted as out-of-scope route cards.
