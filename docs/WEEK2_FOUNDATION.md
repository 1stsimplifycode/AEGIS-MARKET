# Week 2 — market, liquidity and statistical foundations

What the seven Week 2 criteria ask for, what this repository now computes, and where the
data runs out.

This layer is **additive**. The repository's own Week 2 (`STATS-02` universe/survivorship,
`MULTIMODAL-02` text affect) is untouched, as are all sixteen weeks, their launchers, their
gates and `research_modules.yaml`.

```bat
python scripts/build_week2_foundation.py --acquire   REM fetch intraday, then build
python scripts/build_week2_foundation.py             REM build from what is on disk
python -m pytest tests/week2 -q                      REM assert all seven criteria
```

---

## The data question, answered first

The daily NSE bhavcopy cannot produce realised variance, price impact, or anything else
that needs within-session variation. That is why the previous audit returned
NOT_SATISFIED on C1, C2, C5 and C6, and it was right.

What changed is that **genuine intraday NSE bars were obtained** — from a commercial
redistributor, not from NSE. That distinction is carried in the data, not in a footnote:

| | |
|---|---|
| Provider | Yahoo Finance chart API v8 |
| Basis | `THIRD_PARTY_REDISTRIBUTOR` — **never** `EXCHANGE_PUBLISHED` |
| Coverage | 2026-06-03 … 2026-08-25, 59 sessions, 50 universe members |
| Volume | 626,856 bars (1m: 126,880 / 2m: 282,755 / 5m: 217,221) |
| Sessions | 09:15–15:30 IST, matching NSE's cash session |
| Recorded | `data/reference/reference_manifest.json`, with licence, checksum and coverage |

**The hard limit:** roughly 7 days of 1-minute and 60 days of 5-minute bars. This supports
recent-window estimation. It does **not** support the 2005–2026 study period the daily
panel covers, and the manifest says so.

**What was refused:** splitting a daily OHLC into synthetic intraday ticks. Four numbers
contain no path, and inventing one would produce a realised variance that measures the
invention. `test_daily_bars_cannot_masquerade_as_intraday` enforces this.

---

## C1 — realised variance

`research/market/realised_variance.py`. Estimator: `RV_t = Σ r_{t,i}²`.

The frequency is a bias–variance trade-off, and the target was fixed **before** any RV was
computed (`PRECISION_TARGET`, module-level): relative standard error ≤ 0.25, noise share
≤ 0.10. Every candidate was measured:

| minutes | returns/session | mean RV | rel. SE | noise share | verdict |
|---|---|---|---|---|---|
| 1 | 361.5 | 1.667e-04 | 0.074 | **0.121** | rejected — noise |
| **2** | **180.9** | **1.613e-04** | **0.105** | **0.063** | **selected** |
| 5 | 72.1 | 1.381e-04 | 0.167 | 0.029 | qualifies |
| 10 | 36.1 | 1.353e-04 | 0.236 | 0.015 | qualifies |
| 15 | 23.8 | 1.196e-04 | **0.289** | 0.011 | rejected — sampling error |
| 30 | 12.0 | 1.227e-04 | **0.408** | 0.006 | rejected — sampling error |

Rule: reject on either bound, then take the **finest** survivor. Nothing downstream
participates in the decision.

*A methodological correction worth recording:* the first implementation estimated noise
variance separately at each frequency, and rejected every candidate. That was wrong — the
first-order autocovariance at 15 or 30 minutes measures genuine mean reversion, not the
bid-ask bounce, so the noise estimate rose with the interval, which is backwards. Noise is
now estimated once at the finest frequency and the implied bias propagated as `2·n_f·var`.
The noise share now falls monotonically, which a test asserts.

**Output:** `data/reference/realised_variance.parquet` — 1,559 (symbol, session) rows,
50 symbols, 32 sessions, every row carrying `rv_relative_standard_error = sqrt(2/n)`.

## C2 — price impact

`research/market/price_impact.py`. Kyle's specification per security:
`r_i = α + λ·S_i + e_i`, fitted by OLS with **HC1 heteroskedasticity-robust** standard
errors (intraday variance is strongly time-varying; the classical formula would understate
uncertainty exactly when it matters).

**50 estimates, 50 standard errors.** Median λ = 6.36e-09, median SE = 1.19e-09, median
t = 4.26, **47/50 significant at 5%**, median R² = 0.339, median n = 5,556 bars.

`validate()` raises `MissingUncertainty` if any estimate lacks a standard error, and every
consumer calls it — so a coefficient cannot travel without its uncertainty. Four negative
controls assert this fails when the field is dropped, nulled, zeroed, or summarised.

**The signing caveat, stated everywhere it appears:** NSE publishes no trade direction.
Signs come from the **tick test**, basis `INFERRED_BY_PUBLISHED_RULE`. It misclassifies
some bars and attenuates λ toward zero, so these coefficients are conservative and are not
an exchange statement about order flow. The carried-forward share (mean 7.5%) is reported
per security so the reader can see how much of the signing was assumption.

## C3 — Amihud

The existing implementation (`research/market/features.py:209-211`,
`mean(|r| / turnover)` over 21 sessions) is unchanged. What was missing was the cross-check,
now computed from the real estimates:

**Spearman ρ = 0.289, p = 0.0418, n = 50, 95% CI [0.003, 0.531]**
**Kendall τ = 0.220, p = 0.0244**

The daily proxy and the intraday regression rank securities compatibly — significant, but
modestly so, and the interval nearly touches zero. That is reported as it stands.

## C4 — distribution-free thresholds

`research/market/thresholds.py`. **Budget first**: `FALSE_ALARM_BUDGET = 0.01`, a
module constant with a written rationale (≈250 sessions/year → two or three alarms per
instrument per year; a review-capacity number, not a tuned one).

Method: **conformal empirical quantile** with the finite-sample `⌈(n+1)(1−α)⌉` correction —
exact coverage under exchangeability for *any* distribution. Verified across normal,
lognormal, Pareto and bimodal samples.

Applied to a Week 2 liquidity feature (realised variance) and to the stress score, **not**
only to the model risk score. Realised: **14 anomalies in 1,559 rows = 0.90%** against a
1% budget.

A Gaussian threshold is computed *as a labelled comparison only*. On a Pareto sample it
misses the budget by more than 3× the conformal miss.

## C5 — trade arrival, and the Week 8 dependency

`research/market/arrival.py`, fitted to NSE's own `TOTALTRADES`/`TtlNbOfTxsExctd`.

Poisson MLE vs negative binomial, decided by the Fano factor with a χ² dispersion test.
**All 50 symbols are overdispersed** (median Fano = 42,322, NB k = 3.16, p ≈ 0). Daily
trade counts are nothing like Poisson.

**The dependency is structural:**

```
research.market.arrival
  → data/reference/week2_overdispersion.json     (published by the Week 2 build)
  → research.detection.count_events.CountEventDetector
  → scripts/stages/stats.py::episode_event_statistics   (STATS-08)
```

The detector's band is `λ + z·√λ·sd_inflation`, `sd_inflation = √Fano = 205.7`.
`CountEventDetector` **cannot be constructed without** an `OverdispersionResult` — `None`
raises, a bare float raises, and there is no Poisson fallback. A test greps the source to
confirm none exists.

**The result does real work:** on 151,648 scored sessions a Poisson band would call
**72,642** of them events. The Week 2 correction leaves **2,081**.

STATS-08 keeps its original episode summary untouched; the count-event block is additive,
and MULTIMODAL-08 video generation is unchanged.

## C6 — liquidity state vector

`research/market/liquidity.py`.
`L = [realised_variance, price_impact_lambda, amihud, arrival_fano]` — every component a
real Week 2 estimator, none invented to pad the vector.

Normalised by **robust z** (`(x − median)/(1.4826·MAD)`) — median/MAD because these
distributions are skewed and one extreme security would otherwise flatten the rest.

Produced for **1,559 (symbol, session) observations**, not a 50-row cross-section. The
stress gate fired on **14**, driven by realised variance (8) and price impact (6).

**Attribution is arithmetic:** `contribution_j = z_j / Σ_{z_k>0} z_k`, computed from the
row's own z-scores. An AST test asserts `attribute()` contains no string constant except
its docstring and the `"z_%s"` column template, and an end-to-end test spikes one estimator
and asserts the gate blames the other.

## C7 — finance inputs

`research/reference/week2_inputs.py`. **2 of 5 fully available.**

| Input | State | Consumed | Why |
|---|---|---|---|
| Traded value | **OBTAINED** | ✓ | `TOTTRDVAL`/`TtlTrfVal` → `turnover`, 8.4M rows, 2005–2026 |
| Session calendar | **OBTAINED** | ✓ | **5,337 realised sessions**, verified against the archive |
| Order-flow signing | PARTIAL | ✓ | `INFERRED_BY_PUBLISHED_RULE` (tick test) — NSE publishes no direction |
| Circuit regime | PARTIAL | ✓ | Historical band-hits obtained; band *width* history does not exist |
| ASM/GSM regime | PARTIAL | ✗ | Current snapshot; historical membership confirmed unobtainable |

### The closure pass

A second investigation went after the three PARTIAL inputs. One moved.

**Circuit regime — half closed.** NSE's daily PR bundle (`PRddmmyy.zip`) contains
`bhddmmyyyy.csv`, described by the bundle's own readme as *"a list of securities which have
hit their price bands during the day"*. The archive resolves back to **2010-01-04** (2009
and earlier answer 404). Acquired: **50,382 band-hit records, 254 sessions, 2,393 symbols**
(27,524 upper / 22,858 lower), `EXCHANGE_PUBLISHED`.

The phrase "circuit regime" covers two things and only one was obtainable:

- *the realisation* — which securities were pinned at a limit, when, in which direction.
  **Obtained historically and consumed.**
- *the schedule* — the band width applicable to each security on each past session.
  **Not available.** NSE publishes today's widths only, and no width is ever attached to a
  past session.

So the input stays PARTIAL, but it is now consumed:
`research.market.liquidity::validate_against_band_hits` checks the stress gate against this
independent exchange fact. Securities the gate calls stressed hit a circuit band on
**7.14%** of those sessions against a **2.89%** base rate — a **2.47× lift**, computed, not
asserted.

**ASM/GSM — confirmed unobtainable.** `api/reportASM?date=…` returns a response
**byte-identical** to the undated call (sha256 `00ad4f47217e`), so the parameter is ignored
and no historical membership is served. Dated archive CSVs answer 404. It stays a snapshot
and stays unconsumed.

**Order-flow direction — confirmed unobtainable.** `sec_bhavdata_full` (200 OK) carries
`DELIV_QTY` and `DELIV_PER` but **no aggressor field**; the MTO delivery file likewise;
`api/quote-equity?section=trade_info` answers 403. Signing stays the tick test, labelled
`INFERRED_BY_PUBLISHED_RULE`.

**Session calendar — verified.** All 5,337 calendar sessions are backed by a real
`cm_YYYYMMDD.zip` and equal the panel's distinct dates exactly. The 2,524 archive dates not
present are all pre-2005, outside the panel window. Weekdays only, no weekends.

---

## Honest scope

Four criteria rest on intraday bars covering **59 recent sessions for 50 securities**. They
are real and the estimates are sound for that window. They are not a claim about 2005–2026,
and the artifacts, the manifest and the product all say which window they describe.
