<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# CORPUS-03 — Does synthetic training data help or harm?

| | |
|---|---|
| Category | `CORPUS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | — |

## Purpose

Fit on real rows alone and on real plus generated rows, score both on the same real evaluation rows, and sweep the synthetic share of the training set.

## Research question

> Does adding copula-generated rows to training improve or degrade generalization measured on real data?

## Inputs

- `outputs/corpus/corpus_report.json`

## Processing

Adapter: `scripts.stages.corpus:real_vs_synthetic`

Canonical implementation:

- `research/corpus/synthesis.py`
- `scripts/run_real_vs_synthetic.py`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/corpus/real_vs_synthetic.json`
- `outputs/corpus/real_vs_synthetic.csv`

## Dependencies

- `CORPUS-01`

## How to run

```bat
REM from anywhere
CORPUS\03_real_vs_synthetic\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module CORPUS-03
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module CORPUS-03 --check
```

## Reproducibility

Every run appends a record to `logs/corpus/corpus_03.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Both arms are scored on the same real rows and the runner aborts if any synthetic row reaches an evaluation split. The generator is checked for memorisation by nearest-neighbour distance against the real data, scaled by the real statistics so a verbatim copy cannot hide behind separate standardisation. The result is reported whichever way it falls.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
