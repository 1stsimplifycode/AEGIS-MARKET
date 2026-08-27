<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# CORPUS-05 — Why synthetic augmentation degrades performance

| | |
|---|---|
| Category | `CORPUS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | — |

## Purpose

Test seven candidate mechanisms against each other to explain the measured collapse under synthetic augmentation.

## Research question

> Is the degradation caused by distributional distance, or by something distributional distance does not measure?

## Inputs

- `outputs/corpus/synthetic_degradation_diagnosis.json`

## Processing

Adapter: `scripts.stages.corpus:synthetic_degradation`

Canonical implementation:

- `scripts/diagnose_synthetic_degradation.py`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/corpus/05_synthetic_degradation/diagnosis.json`

## Dependencies

- `CORPUS-03`

## How to run

```bat
REM from anywhere
CORPUS\05_synthetic_degradation\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module CORPUS-05
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module CORPUS-05 --check
```

## Reproducibility

Every run appends a record to `logs/corpus/corpus_05.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Six mechanisms are ruled out with the number that rules each one out: marginals, class balance, covariance, mode collapse, feature range and coverage-flag damage. The supported mechanism is interaction loss -- a tree ensemble separates real from generated at AUC 0.9639 while a linear model reaches 0.4952, which is chance. A linear model can only use first- and second-order structure, so that gap is exactly the structure a Gaussian copula cannot carry. This does not tune the generator to improve the headline number; it explains the number that was measured.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
