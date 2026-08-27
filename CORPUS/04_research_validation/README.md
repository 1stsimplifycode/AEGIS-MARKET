<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# CORPUS-04 — Consolidated research validation and scorecard

| | |
|---|---|
| Category | `CORPUS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `PARTIAL` |
| Experiment | — |
| Limitations | — |

## Purpose

Fill fifteen research dimensions for both tracks from artifacts on disk and gate the headline claims against the numbers that decide them.

## Research question

> Which research dimensions are actually evidenced, and which headline claims survive contact with the results?

## Inputs

- none (this module needs no data)

## Processing

Adapter: `scripts.stages.corpus:research_validation`

Canonical implementation:

- `research/validation/__init__.py`
- `scripts/generate_research_validation.py`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/research_validation/validation_summary.json`
- `outputs/research_validation/research_validation_report.md`

## Dependencies

- `CORPUS-01`
- `CORPUS-03`

## How to run

```bat
REM from anywhere
CORPUS\04_research_validation\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module CORPUS-04
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module CORPUS-04 --check
```

## Reproducibility

Every run appends a record to `logs/corpus/corpus_04.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

A cell cannot read SUPPORTED without an evidence file behind it: the dataclass refuses to construct one. Dimensions with no artifact report NOT RUN and name what would produce one. The claim gate returns SUPPORTED, QUALIFIED or NOT SUPPORTED per claim, and a claim the evidence contradicts is recorded as contradicted rather than dropped.

## Status

`WRAPS_EXISTING` / `PARTIAL`
