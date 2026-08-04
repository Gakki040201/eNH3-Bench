# M018 A2A Evidence-to-Design Compiler

## Boundary

M018 A2A is a deterministic, offline contract layer. It defines a design ontology, compiles evidence and explicitly configured capability information into design problems, validates executable-design-card skeletons, routes simulation questions without launching a simulator, and emits short rule-based critic findings.

It is not a literature-review UI, a claim-labelling system, a final electrolyte predictor, a COMSOL/DFT/MD solver, an experimental robot, or a Top-11 recommendation system. It never calls a model or provider and does not generate or rank scientific candidates.

## Schemas

The four contracts use JSON Schema draft 2020-12 and reject unknown fields:

- `schemas/v018_design_problem.schema.json`
- `schemas/v018_design_card.schema.json`
- `schemas/v018_critic_result.schema.json`
- `schemas/v018_simulation_job.schema.json`

Serialized paths are relative POSIX paths. Validators also reject secret-like fields and values, reasoning or chain-of-thought fields, hidden labels, machine hostnames, user names, and absolute paths. IDs are SHA-256-derived from stable semantic identities. Content hashes use canonical UTF-8 JSON with sorted keys and compact separators, excluding only the `content_hash` field itself.

## Evidence boundary

The real A2A problem targets LiNRR closed-loop discovery, but it is a design-space definition rather than a candidate set. The frozen A1 pilot contains exactly one LiNRR-labelled package, P0797. The compiler explicitly marks only that package as `direct_design_evidence`; the other reaction families receive an explicit validation-pattern or methodological-context role. All A1 review statuses remain unchanged. The output states that the pilot is not a sufficient LiNRR training corpus.

Reported, derived, assumed, unknown, and not-applicable variable values remain distinct. Reported facts require evidence references. Derived and assumed values must be explicit and visibly labelled. Unknown values stay null. A2A never fills missing scientific values.

## Design problem and objectives

The compiler includes electrolyte, electrode/current-collector, electrochemical-operation, reactor/chamber, and process/product-handling variables. Each objective remains separate with its direction, unit, source, target, acceptable threshold, weight, hard/soft status, and uncertainty method. A2A does not create an aggregate score.

## Cards and critics

A card is executable only when all required variables are specified, units validate, every hard constraint passes, the safety gate is present and not rejected, controls and measurements are listed, and a falsification criterion exists. Tracked cards are synthetic fixtures labelled `NON_SCIENTIFIC_FIXTURE`.

The deterministic critics cover evidence, chemistry, electrochemistry, engineering, and safety/capability. They serialize only short findings and resolutions—never hidden reasoning. Blocking is reserved for fail verdicts. Representative rules include missing LiNRR water content, proton donor without concentration, current density without area, flow without geometry, pressure without a reactor rating, context-only positive support, missing NH3 controls, and incomplete COMSOL/DFT/MD inputs.

## Simulation routing and human gates

Routes distinguish `surrogate`, `COMSOL`, `DFT`, `MD`, `no_simulation`, and `human_required`. COMSOL, DFT, and MD jobs are contracts only and always require the expensive-simulation human gate. A2A never launches a simulator.

The five gates are:

- `GATE_SIMULATION_EXPENSIVE`
- `GATE_EXPERIMENT_SAFETY`
- `GATE_EXPERIMENT_EXECUTION`
- `GATE_RESULT_ACCEPTANCE`
- `GATE_MODEL_UPDATE`

The deterministic compiler leaves their decisions and decision provenance null. It does not fabricate approvals.

## External runtime

Build the real problem and deterministic reports outside Git:

```powershell
C:\Python314\python.exe scripts\build_v018_design_problem.py `
  --a1-runtime-root F:\eNH3_Bench_API\v018 `
  --runtime-root F:\eNH3_Bench_API\v018\design_compiler `
  --clean
```

The runtime contains `inputs`, `problems`, `cards`, `critics`, `simulations`, `reports`, and `logs`. The tracked repository contains schemas, code, tests, documentation, and synthetic fixtures only. Required generated artifacts are:

- `problems/linnr_discovery_problem.json`
- `reports/linnr_design_space_inventory.json`
- `reports/linnr_design_space_inventory.html`
- `reports/linnr_missing_inputs.csv`

The HTML is self-contained and deterministic. The inventory fixes candidate, recommendation, and simulator-run counts at zero.

Validate individual artifacts with the corresponding scripts:

```powershell
C:\Python314\python.exe scripts\check_v018_design_problem.py --problem <relative-or-external-path>
C:\Python314\python.exe scripts\check_v018_design_card.py --card <relative-or-external-path>
C:\Python314\python.exe scripts\check_v018_critic_result.py --critic <relative-or-external-path>
C:\Python314\python.exe scripts\check_v018_simulation_job.py --job <relative-or-external-path>
```

## Safety counters

The A2A baseline performs zero credential checks or reads, provider/model calls, new scientific claims, human labels, Gold mutations, holdout reads, COMSOL runs, DFT runs, and MD runs.
