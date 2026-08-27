<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# SCENARIO-08 — Transaction risk interface and corpus search

| | |
|---|---|
| Category | `SCENARIO` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `BLOCKED` |
| Experiment | — |
| Limitations | `L-23`, `L-04` |

## Purpose

Record the six requirements a transaction corpus would have to meet, the five candidates assessed against them, the specific disqualification for each, and the declared synthetic fixture the interface is exercised on until one qualifies.

## Research question

> Can this framework be applied to transaction risk on evidence rather than on a fixture, and if not, exactly what is missing?

## Inputs

- none (this module needs no data)

## Processing

Adapter: `scripts.stages.scenario:transaction_risk`

Canonical implementation:

- `research/scenario/transactions.py::CANDIDATES`
- `research/scenario/transactions.py::fixture`
- `research/models/baselines.py::zscore_composite`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/scenario/transaction_corpus_search.json`

## Dependencies

- none

## How to run

```bat
REM from anywhere
SCENARIO\08_transaction_risk\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module SCENARIO-08
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module SCENARIO-08 --check
```

## Reproducibility

Every run appends a record to `logs/scenario/scenario_08.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Reports BLOCKED because no qualifying corpus was identified. The interface is complete and runs unchanged the day one exists. Nothing here is described as a measurement of a payments system, and no general-purpose dataset is relabelled as one.

See `docs/LIMITATIONS.md` for **L-23**, **L-04**.

## Status

`WRAPS_EXISTING` / `BLOCKED`
