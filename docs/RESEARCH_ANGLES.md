# Research angles — how the boundaries became experiments

`docs/LIMITATIONS.md` remains the authoritative factual record, and nothing here weakens
any caveat in it. This document describes the layer added on top: every limitation is now
a structured object in `research/limitations/registry.py` carrying the research question it
creates and a falsifiable experiment specification — and the eight specifications that
needed no external data have been executed.

A research angle is not a research result. Every specification carries a status, and a
specification whose data does not exist is `BLOCKED` and reports no number.

## Structure of every entry

```
LIMITATION -> WHY IT EXISTS -> WHAT IT INVALIDATES -> WHAT REMAINS VALID
           -> RESEARCH QUESTION -> EXPERIMENT SPECIFICATION
           -> CURRENT EVIDENCE -> WHAT IS UNRESOLVED -> FUTURE VALIDATION
```

Categories are precise: `ENGINEERING`, `DATA`, `LICENSING`, `COMPUTATIONAL`,
`METHODOLOGICAL`, `EVALUATION`, `SCIENTIFIC_OPEN_QUESTION`,
`UNRESOLVED_NEGATIVE_RESULT`. A limitation is not automatically a failure, and the
vocabulary distinguishes `NOT MEASURED` from `NOT SUPPORTED` from `BLOCKED`.

## Registry contents (measured)

| Quantity | Count |
|---|---|
| Limitations | 12 |
| Unresolved negative results | 5 |
| Research questions | 19 |
| Experiment specifications | 18 |
| **Runnable with data on hand** | **8 — all executed** |
| Blocked by external data | 10 |

## Unresolved negative results, promoted to first-class objects

| ID | Finding | Status |
|---|---|---|
| N-01 | LIME sign consistency 0.780 against a pre-declared 0.80 threshold | `FAILED_SANITY_CHECK` |
| N-02 | Corrected regime fusion 0.9412 vs static 0.9480 | `NOT_SUPPORTED` |
| N-03 | Median lead time −10.0 sessions | `NOT_SUPPORTED` |
| N-04 | Uncertainty fusion shows no AUPRC advantage | `NOT_SUPPORTED` |
| N-05 | Propagation contributes 0.0005 AUPRC | `NOT_SUPPORTED` |

None was resolved by moving a threshold.

---

## What the executed angles measured

### EXP-N03-1 — the lateness is not a tuning choice

Sweeping the state-machine entry threshold from 0.20 to 0.90 moves median lead time only
within −10.0 to 0.0 sessions while window precision varies 0.384 to 0.653. **No operating
point achieves positive lead time.**

This converts N-03 from "the detector is tuned conservatively" into "the evidence itself
arrives late" — a stronger statement, and a more useful one, because it redirects the next
experiment from threshold tuning to evidence sourcing.

**Modality lead and lag**, computed per instrument and averaged:

| Modality | Peak lag (sessions) | Peak correlation | Reading |
|---|---|---|---|
| text | 0 | 0.746 | coincident |
| market | −5 | 0.721 | lags |
| microstructure | **+7** | 0.108 | **leads** |
| propagation | 0 | 0.119 | coincident |
| audio | −1 | 0.102 | lags |
| video | −13 | 0.087 | lags |
| image | −10 | 0.055 | lags |
| regime | −15 | 0.022 | lags |

The only channel that leads is the microstructure proxy block, weakly. Everything else is
coincident or lagging — consistent with image, video and audio being derived from the same
price series (L-09, L-06).

**Lifecycle sub-tasks scored separately**, which the single detection number hides:

| Task | n | Median error | Within 3 days |
|---|---|---|---|
| onset | 33 | +13 days | 6.1 % |
| resolution | 17 | +5 days | 23.5 % |

**Resolution is the easier sub-task**, which is the opposite of the usual assumption.

### EXP-L10-1 — the uncertainty estimate does its job

ECE rises monotonically across uncertainty quintiles from 0.0835 to 0.3273 (slope +0.638),
on equal-mass buckets of 771 rows each. Calibration degrades exactly where the model
reports being unsure, which is the behaviour an uncertainty estimate should show.

The companion coverage analysis is **NOT MEASURABLE** here: coverage takes only two
well-populated values (0.875 and 1.0). An earlier version of this analysis reported a
confident-looking slope of +0.62 against coverage — an artifact of quantile bins collapsing
onto duplicate edges and counting the same rows twice. The analysis now detects the
degenerate case and refuses to fit a line to it.

### EXP-N04-1 — AUPRC was the wrong metric for that arm

Uncertainty-weighted fusion has lower selective risk than static attention at **all nine**
coverage levels (mean difference −0.038), alongside ECE 0.0631 versus 0.1227.

Its status stays `PARTIAL`, not `SUPPORTED`. Each arm ranks rows by its own uncertainty, so
an arm whose uncertainty is merely self-consistent flatters itself on this metric, and most
of the full-coverage gap is an operating-point effect rather than genuine selection.

### EXP-L12-1 — one null result is uninformative, two are not

| Comparison | Minimum detectable effect | Observed difference | Informative |
|---|---|---|---|
| NO_MICROSTRUCTURE | 0.000185 | 0.000176 | **no** |
| NO_PROPAGATION | 0.000304 | 0.000506 | yes |
| NO_AFFECTIVE | 0.026191 | 0.088370 | yes |

The microstructure null is **not** evidence that the contribution is zero: the study could
not have detected an effect that small. Measured bootstrap scaling exponents run −0.49 to
−0.72, bracketing the textbook −0.5, which indicates the resampler behaves as expected
under clustering.

### EXP-N02-1 — a mechanism for the regime result

The static-versus-corrected gap narrows as episode clusters increase (trend
+5.1 × 10⁻⁶ per cluster), and the smallest regime holds only 17 validation episodes
(36 / 33 / 33 / 17 across the four regimes).

That is consistent with **variance inflation from per-regime parameters** rather than with
regimes being uninformative — a boundary condition for regime-aware fusion, not a verdict
on it. The competing explanation, redundancy between the regime block and the market block,
predicts a flat gap and is not what was observed.

### EXP-N01-1 — stability is not agreement

| Perturbations | Sign consistency | Passes 0.80 | Rank corr vs occlusion | Seconds |
|---|---|---|---|---|
| 400 | 0.770 | no | +0.260 | 0.039 |
| 800 | 0.784 | no | +0.058 | 0.058 |
| 1600 | 0.790 | no | −0.054 | 0.065 |
| 3200 | 0.790 | no | +0.004 | 0.101 |
| 6400 | **0.804** | **yes** | −0.018 | 0.169 |

LIME becomes self-consistent at 6400 perturbations and remains cheaper than occlusion
(0.397 s). But its rank correlation against occlusion never departs from zero. **A method
can be perfectly reproducible and still rank features differently from every other
method** — so N-01 resolves into a sharper finding than "LIME is unstable".

### EXP-L03-1 — the static-artifact architecture holds

Executed once Node.js was installed. Every sampled value renders in the served HTML
identical to its source artifact: AUPRC 0.941166 → 0.941, minimum detectable effect
0.000185 → 0.000185, text peak correlation 0.746175 → 0.746. Local latency is p50
5.9–10.0 ms and p95 17.1–32.9 ms over 20 samples per route, with no model call in the
request path.

Reaching that state exposed two defects no Python test could have caught:

- **The exporter emitted bare `NaN`.** Invalid JSON; `JSON.parse` rejects the whole
  document, so the statistics page silently rendered "data not available" while
  `json.loads` accepted the same bytes without complaint. Fixed, and now locked by a test
  that parses every bundle with `parse_constant` set to reject.
- **`useSearchParams` in the mode provider disabled prerendering for the whole client
  tree**, shipping `/settings` and `/watchlist` as blank 9.4 KB shells. Fixed by isolating
  the query read to a leaf; they now server-render at 14.6 KB and 12.3 KB.

Cold starts and edge caching on Vercel remain unmeasured, so the supported claim is
"builds and serves locally", not "is deployed".

### EXP-L04-2 — detection is not intensity-limited at this sample size

Across 36 validation episodes, detection rate is 1.0 in both the lowest and the highest
peak-intensity quartile, while intensity correlates with peak score at ρ = 0.28. Intensity
moves the score without moving detectability, so no intensity floor is visible here. With
36 episodes this is a weak observation and is labelled as one.

### Modality information decomposition

| Modality | Alone | Unique | Redundant | Conflict rate |
|---|---|---|---|---|
| text | 0.7973 | **0.1239** | 0.6734 | 0.116 |
| market | 0.8160 | **0.1131** | 0.7029 | 0.029 |
| video | 0.2566 | 0.0011 | 0.2555 | 0.150 |
| image | 0.2373 | 0.0008 | 0.2365 | 0.150 |
| audio | 0.2573 | 0.0006 | 0.2567 | 0.150 |
| propagation | — | 0.0005 | — | — |
| microstructure | 0.8168 | 0.0002 | 0.8166 | 0.151 |
| regime | — | **−0.0060** | — | — |

Two readings the ablation table alone could not give:

- **Microstructure looks strong alone (0.8168) purely because it rides on the market
  block.** Its unique contribution is 0.0002 — and by EXP-L12-1, that is below what this
  sample could resolve anyway.
- **Regime has a negative unique contribution**: it costs performance when present.

This is an operational decomposition in AUPRC, not a formal partial information
decomposition — those need joint distributions this sample cannot support (L-12) — and it
is labelled as such wherever it appears.

---

## The claim ledger and its guard

`research/claims/ledger.py` records 11 claims, each with evidence, experiment, bounding
limitations and a **validity scope**. Nine are `SUPPORTED`, one `PARTIAL`, one
`NOT_SUPPORTED`. **None is stated at out-of-sample scope**, because the holdout is frozen.

An automated guard refuses text asserting more than its scope supports, across seven
pattern families: real-world detection, generalisation, universal claims in either
direction, advisory phrasing, readiness, anticipation, and per-limitation forbidden
phrasings. Universal *negatives* matter as much as positives here: "multimodality does not
help" is exactly as unsupported as "multimodality helps", and it is the form that slips
past review because it sounds appropriately modest.

Each claim carries example restatements the guard **must** catch, and the ledger is checked
against its own rule on every test run.

That last part is not decoration. **The guard shipped broken once.** An edit wrote its word
boundaries as literal control characters (0x08 instead of `\b`); every real-world pattern
became unmatchable; the module still imported, still ran, and still reported zero problems.
Nothing caught it except reading the output of a deliberate probe. The tests now assert
that every pattern family fires on a known violation and that no pattern contains a control
character, and the boundary is applied in one tested helper rather than written inline.

## Priority order for unblocking

0. ~~A Node.js runtime (L-03)~~ — **done in iteration 3**; the build half of L-03 is
   discharged and its experiment executed.
1. **Adjudicated real incident labels** (L-04) — without them every detection number
   remains a statement about injected episodes.
2. **Licence-clear point-in-time index membership** (L-01).
3. **Licence-clear financial speech** (L-06) — converts audio from sonification into
   independent acoustic evidence.
4. **Independent real financial imagery** (L-09).
5. **A true Level-2 microstructure sample** (L-02).
6. **Tier-2 / Tier-3 model weights** (L-08).
7. **A completed freeze**, then the holdout, once (L-11).

Items 1–5 are external. No amount of engineering in this repository produces them, and
inventing them is prohibited.


## The position lifecycle — a domain framework turned into an experiment

A domain practitioner described their actual process: before taking a position, weigh risk
against reward and fix a reference level in advance; while holding, watch revenue growth,
net debt and interest coverage; at the end, decide whether the original reasoning still
holds. That is a description of how one person works, not evidence about markets, and it
is treated here as a *hypothesis source* rather than as ground truth.

Two things had to happen before it could become research. First, the transactional content
had to be stripped: this repository must never produce a reference price, a target, a size
or a timing instruction, so the framework enters only as an observational segmentation of a
risk trajectory, and `tests/unit/test_non_advisory.py` now scans for the transactional
vocabulary specifically. The cohort is 35 instruments and 3089 sessions drawn from the
validation split; the holdout stays frozen (L-11), which costs 18 instruments and changes
no conclusion below. Second, the empirical claim had to be isolated from the parts the
data cannot address.

### The research question, as posed

> Do the statistically informative signals associated with initial risk differ from those
> associated with subsequent risk-state transitions and resolution?

### The design

* **One common target across stages** — a material change in the risk profile within ten
  sessions, defined as a band transition *or* a move of at least 0.15 so the target is not
  an artifact of where the band edges sit. Comparing stages on different targets would
  make any difference uninterpretable.
* **A separate model per stage**, so a difference in block importance is not a statement
  about where one shared model spent its capacity.
* **A split by instrument, not by date.** This is the design decision that matters most.
  Phase is defined by position within an instrument's window, so a temporal split would
  place entry rows almost entirely on one side and resolution rows on the other — the
  split and the stage would be the same variable and nothing could be attributed.
* **A within-stage noise floor.** Each stage's importance vector is estimated twice, on
  two disjoint halves of the evaluation instruments. A cross-stage correlation means
  nothing without it.

### The result: inconclusive, and that is the finding

| Stage | Eval rows | Base rate | AUPRC | Lift | Top block (full / half A / half B) | Reproduces? |
|---|---:|---:|---:|---:|---|---|
| ENTRY | 180 | 0.544 | 0.562 | +0.017 | image / image / microstructure | no |
| HOLDING | 1203 | 0.692 | 0.840 | +0.149 | market / market / market | yes |
| RESOLUTION | 180 | 0.361 | 0.447 | +0.086 | market / market / video | no |

Only the holding phase names the same top block everywhere: market at 0.097 permutation
importance, text at 0.039, every other block within noise of zero. Entry and resolution
disagree with themselves across halves of their own evaluation set, so the cross-stage
correlations of −0.12, −0.33 and −0.19 are unreadable rather than informative. The entry
model also achieves a lift of only +0.017 over its base rate, so even a stable ranking there
would be thin.

Reported as **N-06**. The sample cannot be grown by extending the panel: entry contributes
ten sessions per instrument by construction, so it scales with the cohort, not with
history. **EXP-N06-1** specifies the subsampling learning curve that would estimate how
large a cohort is needed.

### The one result that did survive, and the one that did not

**Signal ordering.** Every one of the 35 cohort instruments has at least one detected
change point, 84 in total. The propagation block's own change point precedes the fused
estimate's by a median of 6 sessions (n=21); audio and video lead by 1 (n=29, n=33); image
and text are coincident; microstructure follows by 5 (n=10) and market by 6 (n=33). Blocks
contributing fewer than ten instruments get no directional reading at all — the regime
block does not clear the floor, and a median over a handful of instruments is a coin flip
in the shape of a statistic. This is ordering among the model's own inputs and is not
causal.

**Signal conflict.** Rows where the modalities disagree with the fused estimate showed a
forward material-change rate of 0.976 against 0.480 — an unconditional difference of +0.496
that survived exactly as long as it took to check it. Conflict is defined against the same
0.5 threshold that separates the MODERATE and ELEVATED bands, so conflicting rows sit at
high risk by construction: mean risk 0.610 against 0.124. Only one risk decile out of ten
holds enough rows on both sides to compare, and within it the difference is −0.005.
Reported as **N-07**, with the unconditional figure kept beside the stratified one because
the gap between them is the point.

### Is the stage result an artifact of the definition?

**EXP-L15-1** re-runs the whole comparison with phases anchored on the first detected change
point rather than on window position. Entry correlates at −0.71 and resolution at +0.52
between the two definitions; holding cannot be compared at all, because under the
change-point definition every holding row lies within ten sessions of a detected change and
the target becomes positive everywhere. Two of three stages therefore fail the sensitivity
check outright, which is a second, independent reason not to report a stage effect.

### What the framework still cannot address

The practitioner's process centres on revenue growth, net debt and interest coverage. None
of the three exists in this dataset (**L-13**), and no price-derived proxy was substituted,
because a price series wearing a fundamental label is still a price series. **EXP-L13-1**
and **EXP-L13-2** are specified in full and are blocked on point-in-time fundamentals with
disclosure timestamps. Valuation is blocked for the same reason (**L-14**), and no real
holding period is observed anywhere (**L-15**).
