# Closed-Loop Workflow

## 1. Initialize lab profile

```powershell
C:\Python314\python.exe scripts\init_lab_profile.py --profile-template ustc-linnr-realistic --output data\lab_profiles\ustc_linnr_profile.local.yaml --overwrite
```

## 2. Edit lab profile

Open the generated profile and set only capabilities that are actually available in the lab. Keep `isotopic_15N2_available` and `can_do_15N_control` false unless 15N2 validation is actually available.

## 3. Run BoundaryLedger

```powershell
C:\Python314\python.exe scripts\build_evidence_bundles.py --run-name pilot_existing_02
C:\Python314\python.exe scripts\classify_claim_rights.py --run-name pilot_existing_02
C:\Python314\python.exe scripts\detect_hidden_taxes.py --run-name pilot_existing_02
```

## 4. Generate experiment routes

```powershell
C:\Python314\python.exe scripts\generate_experiment_routes.py --run-name pilot_existing_02 --reaction-family LiNRR --lab-demo-only --include-sop-fields --lab-profile data\lab_profiles\ustc_linnr_profile.local.yaml
```

## 5. Export route cards

```powershell
C:\Python314\python.exe scripts\export_experiment_route_cards.py --run-name pilot_existing_02
```

## 6. Export result template

```powershell
C:\Python314\python.exe scripts\export_experiment_result_template.py --run-name pilot_existing_02
```

## 7. Import reviewed results

```powershell
C:\Python314\python.exe scripts\import_experiment_results.py --run-name pilot_existing_02 --input data\experiment_results\pilot_existing_02\experiment_results.reviewed.csv
```

## 8. Evaluate closed loop

```powershell
C:\Python314\python.exe scripts\evaluate_experiment_loop.py --run-name pilot_existing_02
```

## 9. Generate next-round suggestions

The closed-loop report lists route revision recommendations and next-round route suggestions. These are planning signals, not automatic scientific conclusions.

## F0 staged Li-NRR loop

- F0.0: Ground the editable lab profile in actual USTC Li-NRR capabilities.
- F0.1: Admit only LiNRR as the default wet-lab demonstration family.
- F0.2: Run baseline repeatability before variable screening.
- F0.3: Use water/proton donor/salt-solvent windows to close electrolyte ambiguity.
- F0.4: Use interphase resistance and postmortem fields to diagnose renewal burdens.
- F0.5: Use flow/wetting/outlet split routes for product-state accounting.
- F0.6: Use HOR routes only when H2/HOR capabilities are enabled.
- F0.7: Import reviewed results and update only the claim boundaries supported by measured controls and raw records.
