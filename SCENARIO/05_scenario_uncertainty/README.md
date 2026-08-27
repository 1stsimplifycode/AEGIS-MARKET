<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# SCENARIO-05 — Scenario uncertainty

| | |
|---|---|
| Category | `SCENARIO` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | `L-12`, `L-24` |

## Purpose

Report every scenario difference with the interval around it, the test that produced the interval, and the number of assumptions the result rests on, so an unresolved difference is visible as unresolved.

## Research question

> Which scenario differences does this evidence separate from zero, and which does it leave unresolved?

## Inputs

- `outputs/scenario/scenario_uncertainty.csv`

## Processing

Adapter: `scripts.stages.scenario:scenario_uncertainty`

Canonical implementation:

- `research/statistics/tests.py::paired_bootstrap_difference`
- `research/scenario/engine.py::ScenarioEngine`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/scenario/scenario_uncertainty.csv`

## Dependencies

- `SCENARIO-02`
- `SCENARIO-03`

## How to run

```bat
REM from anywhere
SCENARIO\05_scenario_uncertainty\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module SCENARIO-05
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module SCENARIO-05 --check
```

## Reproducibility

Every run appends a record to `logs/scenario/scenario_05.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Clusters are instruments on the market track and accounts on the transaction track, because two rows sharing either are not independent draws. An interval that excludes zero establishes a difference under the scenario's assumptions, not the assumptions themselves.

See `docs/LIMITATIONS.md` for **L-12**, **L-24**.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
