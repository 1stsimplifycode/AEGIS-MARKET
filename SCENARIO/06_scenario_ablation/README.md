<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# SCENARIO-06 — Scenario ablation

| | |
|---|---|
| Category | `SCENARIO` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `PARTIAL` |
| Experiment | — |
| Limitations | `L-09`, `L-12` |

## Purpose

Re-run the whole market catalogue under five modality subsets and report whether each scenario's effect keeps the direction it had on the full stack.

## Research question

> Is a scenario conclusion a property of the condition, or of one modality block happening to be present?

## Inputs

- `outputs/scenario/scenario_ablation.csv`

## Processing

Adapter: `scripts.stages.scenario:scenario_ablation`

Canonical implementation:

- `research/scenario/market.py::ABLATION_SUBSETS`
- `research/scenario/engine.py::ScenarioEngine`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/scenario/scenario_ablation.csv`

## Dependencies

- `SCENARIO-02`
- `SCENARIO-03`

## How to run

```bat
REM from anywhere
SCENARIO\06_scenario_ablation\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module SCENARIO-06
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module SCENARIO-06 --check
```

## Reproducibility

Every run appends a record to `logs/scenario/scenario_06.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

One model seed per subset. The question is whether the direction and rough size of an effect persist; the seed spread that would bound each cell is SCENARIO-07's job.

See `docs/LIMITATIONS.md` for **L-09**, **L-12**.

## Status

`WRAPS_EXISTING` / `PARTIAL`
