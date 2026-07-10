# Closed-Loop Workflow

## 1. Initialize lab profile

```powershell
C:\Python314\python.exe scripts\init_lab_profile.py --output data\lab_profiles\ustc_linnr_profile.yaml
```

## 2. Edit lab profile

Open the generated profile and set only capabilities that are actually available in the lab.

## 3. Run BoundaryLedger

```powershell
C:\Python314\python.exe scripts\build_evidence_bundles.py --run-name pilot_existing_02
C:\Python314\python.exe scripts\classify_claim_rights.py --run-name pilot_existing_02
C:\Python314\python.exe scripts\detect_hidden_taxes.py --run-name pilot_existing_02
```

## 4. Generate experiment routes

```powershell
C:\Python314\python.exe scripts\generate_experiment_routes.py --run-name pilot_existing_02 --lab-profile data\lab_profiles\ustc_linnr_profile.yaml
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
