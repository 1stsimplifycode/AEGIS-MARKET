<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# SCENARIO-02 — Observed market conditions

| | |
|---|---|
| Category | `SCENARIO` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | `L-01`, `L-04` |

## Purpose

Report how the integrity-risk estimate behaves on strata of the evaluation split that genuinely satisfied a stated condition: the most volatile fifth of sessions, and the thinnest fifth by Amihud illiquidity.

## Research question

> Does the risk estimate read differently on sessions that were really stressed, and is the difference separated from zero?

## Inputs

- `outputs/scenario/scenario_results.json`

## Processing

Adapter: `scripts.stages.scenario:market_conditions`

Canonical implementation:

- `research/scenario/engine.py::ScenarioEngine`
- `research/scenario/market.py::CATALOGUE`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/scenario/scenario_comparison.csv`

## Dependencies

- `SCENARIO-01`

## How to run

```bat
REM from anywhere
SCENARIO\02_market_conditions\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module SCENARIO-02
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module SCENARIO-02 --check
```

## Reproducibility

Every run appends a record to `logs/scenario/scenario_02.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Rows are selected, never altered, so nothing in this module is a simulation. Produced by scripts/run_scenarios.py; the module reports that run rather than repeating it.

See `docs/LIMITATIONS.md` for **L-01**, **L-04**.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
