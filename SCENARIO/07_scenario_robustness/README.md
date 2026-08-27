<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# SCENARIO-07 — Scenario robustness

| | |
|---|---|
| Category | `SCENARIO` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | `L-12` |

## Purpose

Re-run every scenario across model seeds on the market track and across fixture generator seeds on the transaction track, and report which effects keep their sign and which exceed their own seed spread.

## Research question

> Does a scenario conclusion survive re-seeding, or is it a property of one draw?

## Inputs

- `outputs/scenario/scenario_robustness.csv`

## Processing

Adapter: `scripts.stages.scenario:scenario_robustness`

Canonical implementation:

- `research/scenario/engine.py::ScenarioEngine`
- `research/scenario/transactions.py::fixture`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/scenario/scenario_robustness.csv`

## Dependencies

- `SCENARIO-02`
- `SCENARIO-03`

## How to run

```bat
REM from anywhere
SCENARIO\07_scenario_robustness\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module SCENARIO-07
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module SCENARIO-07 --check
```

## Reproducibility

Every run appends a record to `logs/scenario/scenario_07.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Two sources of variation, reported separately and never pooled: a model seed and a fixture generator seed answer different questions.

See `docs/LIMITATIONS.md` for **L-12**.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
