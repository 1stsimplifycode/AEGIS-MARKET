<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# CORPUS-02 — Duplication, contamination and effective sample size

| | |
|---|---|
| Category | `CORPUS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | — |

## Purpose

Measure whether the row count is a sample count: exact and near duplicates, cross-split contamination, and the design effect against independent units.

## Research question

> How many independent observations does this corpus actually contain, and does any content appear on both sides of a split?

## Inputs

- `outputs/corpus/corpus_report.json`

## Processing

Adapter: `scripts.stages.corpus:corpus_quality`

Canonical implementation:

- `research/corpus/quality.py`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/corpus/02_corpus_quality/quality.json`

## Dependencies

- `CORPUS-01`

## How to run

```bat
REM from anywhere
CORPUS\02_corpus_quality\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module CORPUS-02
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module CORPUS-02 --check
```

## Reproducibility

Every run appends a record to `logs/corpus/corpus_02.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

A row count is not a sample count. Rows sharing a recording, an instrument or a text are not independent draws, so the design effect is reported beside every total and inference is expected to use the unit count. Near-duplicate rate is estimated from a bounded random sample of row pairs because all-pairs comparison is quadratic, and the sample size is reported rather than the truncation being silent.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
