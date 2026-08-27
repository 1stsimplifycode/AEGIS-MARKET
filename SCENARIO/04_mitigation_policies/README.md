<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# SCENARIO-04 — Mitigation policy comparison

| | |
|---|---|
| Category | `SCENARIO` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `PARTIAL` |
| Experiment | — |
| Limitations | `L-04`, `L-11`, `L-24` |

## Purpose

Compare declared exposure policies on identical scored sessions and report the simulated difference in the daily tail loss, expressed on a declared notional research base with a moving-block interval.

## Research question

> If a different exposure rule had been applied to the same evidence, how would the simulated tail have differed, and by more than its interval?

## Inputs

- `outputs/scenario/scenario_results.json`

## Processing

Adapter: `scripts.stages.scenario:mitigation_policies`

Canonical implementation:

- `research/risk/gate.py::capital_consequence`
- `research/scenario/money.py::CurrencyEstimate`
- `research/statistics/tests.py::moving_block_paired_delta`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/scenario/scenario_money.csv`

## Dependencies

- `SCENARIO-01`

## How to run

```bat
REM from anywhere
SCENARIO\04_mitigation_policies\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module SCENARIO-04
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module SCENARIO-04 --check
```

## Reproducibility

Every run appends a record to `logs/scenario/scenario_04.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

A hypothetical research exposure policy applied to historical rows. No capital was at risk, nothing was executed, and no currency figure here is money that moved. The notional is declared and scales every figure linearly.

See `docs/LIMITATIONS.md` for **L-04**, **L-11**, **L-24**.

## Status

`WRAPS_EXISTING` / `PARTIAL`
