<!-- GENERATED FROM research_modules.yaml - edit the manifest, not this file -->
# CORPUS-01 — Traceable corpus assembly

| | |
|---|---|
| Category | `CORPUS` |
| Wrapper status | `WRAPS_EXISTING` |
| Research status | `SUPPORTED` |
| Experiment | — |
| Limitations | — |

## Purpose

Assemble the research corpus from the real sources in this tree with per-row provenance, then add copula-generated rows fitted on training data only.

## Research question

> Can a corpus at this scale be assembled so that every row states its origin, its licence and whether it was observed or generated?

## Inputs

- `data/panel/cash_panel.parquet`
- `data/panel/text_corpus.parquet`
- `data/panel/multimodal_dataset.parquet`

## Processing

Adapter: `scripts.stages.corpus:corpus_build`

Canonical implementation:

- `research/corpus/__init__.py`
- `research/corpus/build.py`
- `scripts/build_corpus.py`

This module wraps code that already exists. It defines no new statistic, feature or model.

## Outputs

- `outputs/corpus/corpus_report.json`
- `outputs/corpus/corpus_shards.csv`

## Dependencies

- none

## How to run

```bat
REM from anywhere
CORPUS\01_corpus_build\run.bat
```

```bash
# equivalently, without the .bat layer
python scripts/run_module.py --module CORPUS-01
```

Verify the wiring without executing anything:

```bash
python scripts/run_module.py --module CORPUS-01 --check
```

## Reproducibility

Every run appends a record to `logs/corpus/corpus_01.jsonl` carrying the module id, status, message, outputs, adapter, canonical implementation, git commit, environment snapshot and elapsed time.

## Limitations

Fifteen provenance columns on every row, validated by a dataclass that refuses a real sample naming a generator, a generated sample not naming one, or any sample with a blank licence. Financial splits are chronological using the modelling panel's own boundaries; human-affect splits are speaker-disjoint; annotation rows are split by text so one sentence cannot cross a split; synthetic rows are forced to train. Rows beyond the validation boundary keep the label holdout and are never relabelled test.

## Status

`WRAPS_EXISTING` / `SUPPORTED`
