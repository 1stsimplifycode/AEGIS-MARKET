# Robustness, generalization and seed variance (STATS-15, STATS-16)

Two modules that ask what the headline numbers do **not** establish: where the detector
stops working, and how much of the difference between arms is the random seed.

## Reproduce

```bash
python scripts/run_robustness_generalization.py --all
python scripts/run_multiseed.py --seeds 10
```

Or through the module interface:

```bat
STATS\15_robustness_generalization\run.bat
STATS\16_multiseed_significance\run.bat
```

Outputs land in `outputs/stats/15_robustness_generalization/` and
`outputs/stats/16_multiseed_significance/`. Nothing under `research_artifacts/` is
touched, so the cited figures cannot be silently rewritten by either run.

## The frozen holdout is not used, and that is enforced in code

Both modules work inside `train` and `validation` only.

This matters most for STATS-15. Cross-period generalization asks whether a model fitted on
history works on what comes next, and the most recent data in this project *is* the frozen
holdout — so the experiment that most needs new data is exactly the one standing next to
the data it is not allowed to read. A comment would not be enough:

```python
def assert_no_holdout(frame: pd.DataFrame, where: str) -> None:
    n = int((frame["split"] == "holdout").sum())
    if n:
        raise HoldoutTouched(...)
```

Every frame that reaches a model passes through it, on both the training and the
evaluation side, and a test constructs a frame containing holdout rows to confirm it
raises.

STATS-16 applies the same rule for a different reason: repeating a measurement on the
holdout across ten seeds is ten looks at the data the freeze exists to protect.

## STATS-15 — robustness

Five degradations, applied **to the evaluation inputs only**, with the model fitted once
on clean data.

Fitting once is the whole point. Refitting on corrupted data would measure whether the
learner can adapt to a new noise regime — a different and considerably easier question
than what happens to a deployed model when its feed degrades.

| Degradation | What it simulates |
|---|---|
| `gaussian` | measurement noise, scaled to each feature's own standard deviation |
| `dropout` | a partial feed outage, values simply absent |
| `stale` | a **delayed** feed: rows carry the previous observation for that symbol |
| `outliers` | a unit or decimal-point error upstream |
| modality blackout | a whole modality going dark, coverage flag included |

Two details that decide whether the numbers mean anything:

**Noise is scaled per feature.** A single absolute noise level applied across a panel
would obliterate a column measured in basis points while leaving a column measured in
counts untouched, and the result would describe the units, not the model.

**A blackout clears the coverage flag as well as the columns.** The fusion layer reads a
coverage flag, so a modality whose columns are NaN but whose flag still reads 1.0 keeps
voting. Blanking columns alone is exactly how an induced-missingness result comes out too
optimistic.

The training-size curve subsamples **whole symbols**, not rows. Rows from one instrument
are serially dependent, so dropping random rows leaves nearly every instrument still
represented and understates how much the model depends on breadth.

## STATS-15 — generalization

**Cross-period** is an expanding window: fit on everything up to a cut date, score the
next block, move the cut forward. This is the question a deployed detector actually faces.
A random split does not answer it, because it lets the model see the future of the very
period it is scored on.

**Cross-instrument** partitions the tickers into disjoint groups and fits on one side,
scores the other. No symbol appears on both sides, which is what separates "learned
something about market behaviour" from "learned something about these particular tickers".

**Cross-dataset is BLOCKED and reported as blocked.** There is one dataset in this
project, so there is nothing to transfer to. It appears in the output as a `BLOCKED`
record with the reason and what would unblock it, rather than being quietly omitted — an
absent row in a generalization table reads as an untested axis, and a fabricated one would
be worse.

**Adversarial robustness is NOT RUN.** Every corruption here is random. An adversarial
claim needs a threat model and an attacker who can see the detector, which is a different
experiment; nothing in this module licenses one.

## STATS-15 — what was measured

Clean reference on validation: **AUPRC 0.9412**. 13 206 rows in train and validation;
**3 352 holdout rows read zero times**.

### Input degradation

| Corruption | 0.05 | 0.10 | 0.25 | 0.50 |
|---|---:|---:|---:|---:|
| gaussian noise | 0.7895 | 0.6249 | 0.4360 | **0.3723** |
| outliers | 0.8617 | 0.8011 | 0.6844 | 0.5714 |
| dropout | 0.9206 | 0.9051 | 0.8259 | 0.6941 |
| stale feed | 0.9373 | 0.9338 | 0.9144 | 0.8937 |

The ordering is the result. **Noise is by far the worst failure and a stale feed is by far
the mildest** — at the heaviest setting, noise costs 0.569 AUPRC while serving yesterday's
values for half the rows costs 0.047. A detector fed delayed data degrades gracefully; the
same detector fed noisy data collapses to little better than a coin weighted by prevalence.
Those are different operational risks and a single "robustness" number would hide the
distinction entirely.

### Modality blackout

Taking each modality fully offline, coverage flag included:

| Modality offline | AUPRC | Cost |
|---|---:|---:|
| text | 0.8171 | **−0.1240** |
| market | 0.8278 | **−0.1134** |
| video | 0.9403 | −0.0008 |
| regime | 0.9407 | −0.0005 |
| image | 0.9409 | −0.0003 |
| audio | 0.9410 | −0.0002 |
| microstructure, propagation | 0.9411 | −0.0001 |

**Two modalities carry essentially all of it.** Losing text or market costs about 0.12
AUPRC each; losing any of the other six costs less than 0.001 — within the seed noise floor
STATS-16 measures below, which is to say indistinguishable from losing nothing. This is a
sharper statement than the ablation table gives, because it is measured at inference time
on a model that was trained with every modality present.

### Training-set size

Subsampled by symbol, so "less data" means fewer instruments rather than a thinner sample
of the same ones:

| Fraction of symbols | Symbols | AUPRC |
|---|---:|---:|
| 10% | 16 | 0.6166 |
| 25% | 40 | 0.8839 |
| 50% | 80 | 0.9161 |
| 75% | 121 | 0.9355 |
| 100% | 161 | 0.9412 |

Most of the performance arrives by 50 instruments and the curve is close to flat after 75%,
so the detector is not starved of data at the current universe size.

### Generalization

| Fold | Train through | Evaluate | AUPRC |
|---|---|---|---:|
| 1 | 2017-01-19 | 2017-01-20 → 2018-10-15 | **0.7919** |
| 2 | 2018-10-15 | 2018-10-16 → 2020-07-16 | 0.8979 |
| 3 | 2020-07-16 | 2020-07-17 → 2022-04-06 | 0.9308 |
| 4 | 2022-04-06 | 2022-04-07 → 2023-12-29 | 0.9444 |

Forward-in-time transfer averages 0.8913 and **rises monotonically across folds**, from
0.792 to 0.944. The earliest fold is much the weakest, which is what a short training
history predicts; the trend does not separate "more history" from "later periods are
easier", and this design cannot.

| Instrument group | Held-out symbols | AUPRC |
|---|---:|---:|
| 1 | 43 | 0.9292 |
| 2 | 43 | 0.9431 |
| 3 | 43 | 0.9580 |
| 4 | 42 | 0.9330 |

Cross-instrument transfer averages **0.9408** with a range of 0.029 — close to the clean
in-sample 0.9412. **The detector transfers across instruments far more readily than across
time.** Whatever it has learned is not ticker-specific, and the binding constraint is the
period it was fitted on rather than the universe it was fitted on.

Cross-dataset transfer: **BLOCKED**, one dataset exists.

## STATS-16 — seed variance

Every headline number in this project has so far been a single run, which cannot
distinguish *this arm is better* from *this arm drew a luckier seed*.

Every ablation arm is refitted across a declared seed ladder — fixed in source, not drawn,
so a rerun reproduces the same set — and the repeated measurements go to the machinery
that already existed in `research/statistics/`: cluster bootstrap, paired sign-flip
permutation, Benjamini-Hochberg. Nothing statistical is invented here. What was missing was
the driver that produces repeated measurements for those functions to consume.

### Two variances, kept apart

Conflating these is the usual way a seed study overstates its own precision.

| | What it measures |
|---|---|
| **across seeds** | spread of a metric over seeds on one fixed evaluation set — seed variance and nothing else |
| **within run** | cluster bootstrap interval within a single run — sampling variance of the evaluation set |

Both are reported. They answer different questions and neither substitutes for the other.

### The noise floor

The pooled within-arm standard deviation across seeds gives a floor. **A difference
smaller than that floor is reported as not established, whatever it looked like in a single
run.**

Differences that dissolve are listed in the output alongside the ones that survive, under
`differences_within_seed_noise`, rather than filtered away. A seed study that reports only
its surviving findings has reproduced the problem it was built to detect.

Pairing is on seed, which removes the run-to-run variation both arms share. P-values are
then corrected across arms with Benjamini-Hochberg — with 32 arms, reporting uncorrected
p-values would manufacture a significant finding by volume.

### What it measured

320 fits, all successful. **Pooled seed standard deviation 0.00316 AUPRC; 95% noise floor
0.00877.** 30 of 31 arm differences survive correction.

The one that does not is `FUSION_REGIME_CORRECTED`, whose mean difference against `FULL` is
exactly zero — because it *is* `FULL`, the same configuration under a second name. A seed
study that could not recover that would not be worth running.

### The identical-column check that found a missing implementation

Comparing the per-seed vectors rather than only their means turned up three groups of arms
that are identical to machine precision on all ten seeds:

| Group | Verdict |
|---|---|
| `FULL` = `FUSION_REGIME_CORRECTED` | correct — same configuration, two names |
| `FUSION_REGIME_INHERITED` = `FUSION_STATIC` = `NO_UNCERTAINTY` | correct — the section-57 degeneracy, plus one alias |
| `FUSION_EARLY` = `FUSION_LATE` | **a defect** |

The third had no reason to hold. `fusion_strategy="early"` was accepted as valid, but
`Fusion.weights` mapped it onto the same all-zero logits as `late` and nothing anywhere
concatenated the feature blocks, so the FUSION_EARLY arm *was* FUSION_LATE under another
label. In a single run this surfaced as two adjacent rows agreeing to four decimals, which
reads as "early and late fusion perform comparably" — a plausible, publishable-sounding
result with no experiment behind it.

Early fusion is now implemented as one learner over the union of every modality's columns.
Measured across the same ten seeds: **early 0.9306 ± 0.0010 against late 0.9472 ± 0.0015**.
Late fusion wins, the difference survives correction, and it is now a measurement rather
than an artefact of two arms sharing one code path. Recorded as KI-07, including the fact
that the previously cited ablation artifacts still carry the old row.
