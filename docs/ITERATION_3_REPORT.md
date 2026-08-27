# Iteration 3 — the investor decision-lifecycle framework

This iteration took a domain practitioner's working process and asked what part of it this
repository can actually test. The answer turned out to be: the temporal structure, yes; the
inputs the practitioner actually watches, no; and the headline question, not at this sample
size. All three are reported below with the numbers that support them.

---

## What was checked first, before any code

The practitioner's framework is built on revenue growth, net debt and interest coverage.
Before implementing anything, the dataset was inspected rather than assumed:

```
cash panel columns: date, symbol, series, isin, open, high, low, close, last,
                    prev_close, volume, turnover, trades, event_time, knowledge_time
fundamental / valuation columns in the 119-column dataset: 0
```

There are none. Revenue, debt, coverage, earnings, cash flow, P/E, P/B, EV/EBITDA and FCF
yield are all `NOT AVAILABLE`. This is recorded as **L-13** and **L-14** rather than papered
over with a price-derived proxy, because a proxy for revenue growth built from price is a
market signal with a misleading name.

---

## What was built

| Module | What it does |
|---|---|
| `research/lifecycle/states.py` | ENTRY / HOLDING / RESOLUTION phases; six observed states; risk bands; transition extraction and the transition matrix |
| `research/lifecycle/changepoints.py` | Binary segmentation with a variance-scaled penalty, CUSUM, per-instrument detection, and the signal-ordering analysis |
| `research/lifecycle/stages.py` | The stage-differential experiment, its within-stage noise floor, and the conflict analyses |
| `research/core/jsonio.py` | Strict-JSON writing, so no published artifact can carry a bare `NaN` |
| `scripts/run_lifecycle.py` | Runs all of it end to end and writes `research_artifacts/lifecycle/` |

Six figures (`figLC1`–`figLC6`), two tables (`table21`, `table22`), two exported bundles,
a Research-mode page at `/research/lifecycle`, and a Product-mode risk profile timeline on
every cohort instrument page.

---

## Three design decisions that carried the result

**The holdout stays frozen.** Extending the trajectories into the holdout would raise the
cohort from 35 instruments to 53. It was implemented that way first and then reverted. The
holdout is a one-shot resource reserved for the final detection evaluation (**L-11**), the
stage question is unresolvable at either cohort size, and spending it here would have
bought nothing while contradicting a commitment the rest of the repository makes.

**The scored frame was rebuilt.** `per_row_FULL.parquet` is the validation split scored for
detection, which is not the same thing as a trajectory. The model is refitted on train and
every validation row rescored, giving one continuous out-of-sample series per instrument.
No training row is scored: an in-sample stretch at the start of every trajectory would land
exactly where ENTRY is defined.

**The stage comparison splits by instrument, not by date.** Phase is position within an
instrument's window, so a temporal split would put entry rows on one side and resolution
rows on the other. The split and the stage would be the same variable and no difference
could be attributed to either. Splitting into two disjoint halves of instruments keeps all
three phases on both sides.

---

## Results

### Cohort

35 of 162 instruments have the 30+ validation sessions a trajectory needs; 3089
instrument-sessions, median 90 each; 84 change points, with every cohort instrument having
at least one; 654 band transitions (346 escalations, 308 de-escalations); a
material-change base rate of 0.624. The 127 excluded instruments correlate with listing
date and liquidity, so the cohort is not a random sample and nothing generalises to the
names left out.

### The headline question: inconclusive (N-06)

| Stage | Eval rows | Base rate | AUPRC | Lift | Top block: full / half A / half B | Reproduces? |
|---|---:|---:|---:|---:|---|---|
| ENTRY | 180 | 0.544 | 0.562 | +0.017 | image / image / microstructure | no |
| HOLDING | 1203 | 0.692 | 0.840 | +0.149 | market / market / market | yes |
| RESOLUTION | 180 | 0.361 | 0.447 | +0.086 | market / market / video | no |

The split-half columns are the whole story. Each stage's block-importance vector is
estimated twice, on two disjoint halves of the evaluation instruments. Only holding names
the same top block on the full set and on both halves — market at 0.097 permutation
importance, text at 0.039, everything else within noise of zero. Entry and resolution
disagree with themselves.

So the cross-stage correlations — −0.12 (entry vs holding), −0.33 (entry vs resolution),
−0.19 (holding vs resolution) — are unreadable rather than informative. Without the noise
floor this iteration would have reported "the informative signals differ by stage,
ρ = −0.33", which is exactly what the raw number invites.

The entry model is also weak in absolute terms: AUPRC 0.562 against a base rate of 0.544.
A ranking extracted from a model with a lift of +0.017 would be thin even if it were stable.

### Signal ordering

| Block | n | Median offset | Reading |
|---|---:|---:|---|
| propagation | 21 | −6 | shifts before the risk estimate |
| audio | 29 | −1 | shifts before |
| video | 33 | −1 | shifts before |
| image | 25 | 0 | coincident |
| text | 35 | 0 | coincident |
| microstructure | 10 | +5 | shifts after |
| market | 33 | +6 | shifts after |
| regime | — | — | withheld, below the ten-instrument floor |

Ordering among the model's own inputs; not causal, and fundamentals are absent entirely.

### Signal conflict: a confound, quantified (N-07)

Unconditionally, conflicting rows show a forward material-change rate of 0.976 against
0.480 — a difference of **+0.496**. Conflict is defined against the same 0.5 threshold that
separates the MODERATE and ELEVATED bands, so conflicting rows sit at high risk by
construction: mean risk 0.610 against 0.124.

The coupling is tight enough that only **one risk decile out of ten** contains enough rows
both with and without conflict to compare. Within it the difference is **−0.005**. The nine
strata that could not be compared are listed in the output rather than dropped, because
which strata qualify is part of the finding.

### Phase definition sensitivity (EXP-L15-1)

Re-running with phases anchored on the first detected change point instead of on window
position gives rank correlations of **−0.71** (entry) and **+0.52** (resolution) against the
original definition. Holding cannot be compared at all: under the change-point definition
every holding row lies within ten sessions of a detected change, so the target is positive
everywhere and AUPRC is undefined — reported as INSUFFICIENT DATA rather than as a number.
Two of three stages fail the sensitivity check outright.

---

## Bugs found and fixed during this iteration

1. **Conflict buckets double-counted.** Quantile edges on a five-valued variable put every
   row sitting on a repeated edge into two adjacent buckets: 4798 + 1552 = 6350 rows
   reported from a 5783-row frame. Fixed by grouping discrete variables by exact value, and
   the function now raises if its buckets fail to partition the input. Regression test:
   `test_conflict_buckets_partition_the_frame`. Same failure class as the calibration-bin
   bug in iteration 2.
2. **A cross-stage correlation with no noise floor.** The first run reported a bare ρ with
   nothing to read it against. Adding the within-stage split-half estimate turned an
   apparent finding into a correctly-labelled null.
3. **A top-1 check that could pass on a near-tie.** Comparing only the two halves to each
   other let a stage qualify while disagreeing with the estimate from all the data. The
   check now includes the full-set ranking, which is what correctly disqualified resolution.
4. **The mobile navigation silently repointed.** `MOBILE_RESEARCH` indexed into
   `RESEARCH_NAV` by position, so inserting the Lifecycle entry moved the fourth mobile tab
   from Limitations to Figures. Now selected by href.
5. **The non-advisory scan caught its own author.** Three passages of new copy named the
   forbidden actions in order to deny them. The copy was rewritten and the enumeration moved
   into one canonical component that the scan strips, so any other occurrence anywhere in
   the app is a real finding. The extended guard was then verified by injecting
   "Suggested entry price 120 with a stop loss at 100" and confirming it fails, then
   removing it.
6. **Bare `NaN` in published research artifacts.** `lifecycle.json` and
   `research_angles.json` were valid to `json.loads` and rejected by every strict parser —
   the same defect fixed for the app bundles in iteration 2, still live in the artifacts the
   paper package ships. Fixed with `research/core/jsonio.py` and a test that now parses all
   202 research artifacts the way a browser would.

---

## Verification

```
pytest                    542 passed
ruff check .              clean
tsc --noEmit              clean
eslint .                  clean
next build                210 static pages
```

The rendered `/research/lifecycle` HTML was checked for real values rather than trusting
the build: it contains the cohort counts, the INCONCLUSIVE readings and the stratified
difference, not a "data not available" placeholder.

---

## Registry state

15 limitations, 7 negative findings, 25 research questions, 23 experiment specifications:
11 runnable now, 12 blocked on external data. Every blocked specification names exactly what
data would unblock it.

## What is still not known

- Whether fundamentals lead market signals into a risk-state change (**EXP-L13-1**, blocked).
- Whether fundamentals add incremental detection power (**EXP-L13-2**, blocked).
- How large a cohort makes the entry-phase ranking reproducible (**EXP-N06-1**, runnable).
- Whether a disagreement measure that shares no threshold with the band edges carries any
  information (**EXP-N07-1**, runnable).
