<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# SCENARIO-03 — Counterfactual conditions

| | |
|---|---|
| Category | `SCENARIO` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | `L-04`, `L-09`, `L-24` |

## Purpose

Report what the model would have estimated had a channel shifted, gone offline, or arrived a session late, using the same perturbation primitives the robustness track uses and re-scoring with the same fitted model.

## Research question

> How sensitive is the risk estimate to changes in the conditions it is given, and which channel does it actually depend on?

## Inputs

- `outputs/scenario/scenario_results.json`

## Processing

Adapter: `scripts.stages.scenario:counterfactual_conditions`

Canonical implementation:

- `research/scenario/engine.py::materialise`
- `research/evaluation/robustness.py::perturb`
- `research/evaluation/robustness.py::blackout_modality`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/scenario/scenario_comparison.csv`

## Dependencies

- `SCENARIO-01`

## How to run

```bat
REM from anywhere
SCENARIO\03_counterfactual_conditions\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module SCENARIO-03
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module SCENARIO-03 --check
```

## Reproducibility

Every run appends a record to `logs/scenario/scenario_03.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

None of these conditions occurred. Each result holds only under the assumption recorded on its scenario, and the module reports the assumption count beside every effect.

See `docs/LIMITATIONS.md` for **L-04**, **L-09**, **L-24**.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
