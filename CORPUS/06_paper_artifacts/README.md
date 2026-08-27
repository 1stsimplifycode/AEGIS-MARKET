<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# CORPUS-06 — Paper tables and figures

| | |
|---|---|
| Category | `CORPUS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | — |

## Purpose

Generate every paper table and figure from executed artifacts, recording any that cannot be produced together with the command that would produce them.

## Research question

> Can every published table and figure be regenerated from artifacts on disk?

## Inputs

- none (this module needs no data)

## Processing

Adapter: `scripts.stages.corpus:paper_artifacts`

Canonical implementation:

- `scripts/generate_paper_tables.py`
- `scripts/generate_research_figures.py`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/paper_tables/tables.json`
- `outputs/research_figures/figures.json`

## Dependencies

- `CORPUS-01`
- `CORPUS-04`

## How to run

```bat
REM from anywhere
CORPUS\06_paper_artifacts\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module CORPUS-06
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module CORPUS-06 --check
```

## Reproducibility

Every run appends a record to `logs/corpus/corpus_06.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

A table or figure whose source artifact is missing is recorded as NOT GENERATED with the command that would produce it, never emitted empty: an empty table in a paper directory reads as a result of zero, and a placeholder figure is indistinguishable from a real one.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
