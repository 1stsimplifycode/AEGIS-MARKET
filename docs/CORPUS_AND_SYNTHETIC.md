# The traceable research corpus, and what synthetic data did to it

## Reproduce

```bash
python scripts/build_corpus.py --all
python scripts/run_real_vs_synthetic.py
python scripts/run_real_vs_synthetic.py --ratio-sweep
python scripts/generate_research_validation.py
```

Or through the module interface: `CORPUS\01_corpus_build\run.bat` and siblings.

Shards land in `data/corpus/` (gitignored); reports in `outputs/corpus/`.

## What it contains

| Shard | Rows | Source | Type |
|---|---:|---|---|
| `market_daily` | 697 418 | NSE end-of-day, 182 modelled symbols | REAL |
| `financial_text` | 300 508 | in-repo financial document corpus | REAL |
| `text_annotation` | 207 814 | GoEmotions, one row per (text, rater) | REAL |
| `panel_features` | 16 558 | engineered modelling panel | REAL |
| `speech_utterance` | 1 440 | RAVDESS audio | REAL |
| `face_performance` | 720 | RAVDESS video, deduplicated | REAL |
| `synthetic_panel_features` | 40 000 | Gaussian copula on training rows | SYNTHETIC |
| `synthetic_speech_utterance` | 20 000 | Gaussian copula on training rows | SYNTHETIC |
| `synthetic_face_performance` | 20 000 | Gaussian copula on training rows | SYNTHETIC |

**1 304 458 traceable sample instances: 1 224 458 real (93.9%), 80 000 synthetic
(6.1%) — drawn from 58 728 independent units, a design effect of 22.2.**

Both numbers belong together everywhere the size is quoted. The first counts rows
that carry provenance; the second counts things that could have varied
independently. Statistical inference uses the second, which is why every interval
in this project comes from a cluster bootstrap over units, a leave-one-actor-out
fold structure, or a seed noise floor rather than from a row-count standard error
(limitation L-19).

The scale target is met **by real observations alone**, more than twice over. That matters
more than the total: synthetic rows here are a research instrument, not the way a number
was reached. Nothing is duplicated to inflate a count — the duplicate analysis below is
run precisely to make that checkable rather than assertable.

## Every row carries its own provenance

Fifteen columns on every row: `sample_id`, `source_type`, `source_dataset`, `source_id`,
`modality`, `label`, `label_source`, `synthetic_generator`, `generation_seed`,
`creation_timestamp`, `licence`, `split`, `experiment_id`, `unit`, `source_unit_id`.

A dataclass validates them and refuses:

- a `REAL` sample that names a generator, or carries a generation seed
- a `SYNTHETIC` sample that does **not** name its generator — an unnamed generator cannot
  be re-run, so the row cannot be reproduced
- any sample with a blank licence
- any value outside the closed vocabularies

The failure this prevents is silent. A generated row that loses its label is
indistinguishable from an observation, and every "trained on real data" claim downstream
becomes false without anything raising.

## Row count is not sample count

**58 728 independent units behind 1 304 458 rows — a design effect of 22.2.** The corpus
behaves statistically like one twenty-two times smaller, and an interval computed from the
row count would be roughly five times too narrow.

The units are the things that are actually independent: the instrument for market rows,
the actor for speech and video, the text for annotations. Per shard:

| Shard | Rows | Units | Design effect |
|---|---:|---:|---:|
| `market_daily` | 697 418 | 182 symbols | 3 832 |
| `financial_text` | 300 508 | 182 symbols | 1 651 |
| `text_annotation` | 207 814 | 58 009 texts | 3.6 |
| `speech_utterance` | 1 440 | 24 actors | 60 |
| `face_performance` | 720 | 12 actors | 60 |

A design effect of 3 832 is not a defect; it is what daily data on 182 instruments *is*.
Reporting it is the difference between a corpus and a number.

### Two duplicate checks, and only one of them is the leakage check

`cross_split_sources` keys on **identity** and is authoritative: a source id names exactly
one thing, so it cannot collide. It reports clean across every shard.

`cross_split_duplicates` hashes the **payload columns** and answers a different question.
On `financial_text`, whose stored payload is a credibility score, a character count and a
word count, two entirely different documents collide by construction — that shard reports a
0.99 duplicate fraction and zero actual duplication. Both numbers are kept because the
second one, read alone, would be badly misleading, and read together they say something
true: those payload columns are too coarse to identify a document.

## Splits

| Data | Policy |
|---|---|
| financial | chronological, reusing the modelling panel's own boundaries |
| human affect | speaker-disjoint; no actor in two splits |
| text annotations | split by **text**, so one sentence cannot cross a split |
| synthetic | forced to `train`; barred from validation and test |
| frozen holdout | rows beyond the validation boundary keep the label `holdout`, never `test` |

**Test is 100% real.** The builder forces it and the ablation runner aborts if a single
synthetic row reaches an evaluation split.

## Synthetic data made the model dramatically worse

Three seeds, both arms scored on the same real validation rows:

| Arm | AUPRC | AUROC |
|---|---:|---:|
| `REAL_ONLY` | **0.9390 ± 0.0020** | 0.9645 |
| `REAL_PLUS_SYNTH` | **0.3870 ± 0.0266** | 0.6049 |

**−0.5521 AUPRC.** Sixty-three times the seed noise floor STATS-16 measured on this same
pipeline. This is not a marginal effect and it is not seed variance. It is also, as the
ratio sweep below shows, entirely an artefact of *how much* synthetic data was added — at a
quarter of the training set the same generator costs nothing.

### The generator is not broken, which is the interesting part

The obvious explanation would be a bad generator. It is not:

| Check | Value | Reading |
|---|---:|---|
| mean KS statistic | 0.0024 | marginals reproduced almost exactly |
| max KS statistic | 0.0067 | no column is badly wrong |
| mean correlation error | 0.0254 | pairwise structure preserved |
| memorisation distance ratio | 1.421 | synthetic rows sit *further* from real rows than real rows sit from each other |
| exact copies | 0 | nothing was reproduced verbatim |

By every measure a copula is designed to satisfy, this generator succeeded. It reproduces
each marginal by construction and it holds the correlation matrix to within 0.025. And the
detector still collapses.

The reason is what a Gaussian copula cannot represent: **dependence beyond second order**.
The integrity signal this model detects lives in higher-order interactions among the
modality blocks, and a generator matching every marginal and every pairwise correlation
still destroys it. Diluting the training set four-to-one with rows that are marginally
perfect and structurally empty teaches the model a distribution that does not contain the
thing it is looking for.

This is the result §39 asks for, in the direction it did not assume: **synthetic data
hurts here, and it hurts while passing its own fidelity tests.** A pipeline that reported
only the runs where augmentation helped would have shown none of this.

### The ratio changes the answer completely

The headline arms sit at an 81% synthetic share, so on their own they cannot separate *this
generator is inadequate* from *any four-to-one dilution would do this*. The sweep holds the
real training rows fixed and varies only how much generated data sits beside them:

| Synthetic share | Synthetic rows | AUPRC | Against real-only |
|---|---:|---:|---:|
| 0% | 0 | 0.9412 | baseline |
| 10% | 1 039 | **0.9439** | +0.0027 |
| 25% | 3 117 | **0.9429** | +0.0017 |
| 50% | 9 351 | 0.9076 | −0.0336 |
| 75% | 28 053 | 0.3856 | −0.5556 |
| 81% | 39 865 | 0.3613 | −0.5799 |

**Largest harmless share: 25%.** Up to a quarter of the training set, synthetic rows cost
nothing measurable — both differences sit inside the seed noise floor, and at 10% the point
estimate is nominally above baseline. Past that it degrades, and between 50% and 75% it
falls off a cliff: a third of the AUPRC disappears over that one step.

So the honest statement is not "synthetic data is useless here". It is:

> This generator produces rows that are individually plausible — marginals near-exact,
> pairwise correlations within 0.025, no memorisation — and that carry none of the
> higher-order structure the detector depends on. Up to about a quarter of the training
> set they are harmless ballast. Beyond half, they are actively teaching the model a
> distribution in which the target signal does not exist.

The headline arms alone would have supported the much cruder and much less useful claim.
That is why the sweep exists.

## What this does not say

- **Not "synthetic data is useless."** One generator family, one dataset, one task. A
  generator that models higher-order dependence might behave differently, and this
  experiment does not test one.
- **Not a statement about the affective shards.** The ablation runs on the financial
  panel. The synthetic speech and face shards exist in the corpus and were checked for
  fidelity and memorisation, but no downstream model was trained on them.
- **The design effect is not a flaw to be corrected.** It is a property of the data, and
  the only wrong response to it is to ignore it when computing an interval.
