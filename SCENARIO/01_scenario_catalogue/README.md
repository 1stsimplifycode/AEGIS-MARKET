<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# SCENARIO-01 — Scenario catalogue

| | |
|---|---|
| Category | `SCENARIO` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | — |

## Purpose

Emit every declared scenario as a record carrying its baseline, its intervention assumption, the features it affects, its constraints, its expected effect and the simulation method by which its rows are obtained, and refuse any scenario that omits one of them.

## Research question

> Can every scenario in this project be reported together with the assumption it rests on, or is there one whose result could be quoted bare?

## Inputs

- none (this module needs no data)

## Processing

Adapter: `scripts.stages.scenario:scenario_catalogue`

Canonical implementation:

- `research/scenario/spec.py::ScenarioSpec`
- `research/scenario/market.py::CATALOGUE`
- `research/scenario/transactions.py::CATALOGUE`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/scenario/scenario_catalogue.json`

## Dependencies

- none

## How to run

```bat
REM from anywhere
SCENARIO\01_scenario_catalogue\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module SCENARIO-01
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module SCENARIO-01 --check
```

## Reproducibility

Every run appends a record to `logs/scenario/scenario_01.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

A scenario is a record rather than a function precisely so that the catalogue can be serialised, diffed and shown beside its results. The module fails rather than warns when a scenario is unreportable.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
