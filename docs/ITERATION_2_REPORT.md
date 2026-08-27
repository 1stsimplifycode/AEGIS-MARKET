# AEGIS-Market — Iteration 2 report

**Scope:** product/research experience architecture, and turning the limitations register
into an executed research programme.
**Starting state:** iteration 1 (research pipeline verified, 11-view product surface
written but unverified).
**Every number below was produced by running the code.**

---

## IMPLEMENTED

### Research substrate (runs, verified)

| Module | What it does |
|---|---|
| `research/limitations/registry.py` | 12 limitations + 5 negative findings as structured objects, each with research questions and falsifiable experiment specifications |
| `research/claims/ledger.py` | 11 claims with validity scope, plus a guard across 7 pattern families |
| `research/evaluation/information.py` | modality information decomposition, selective risk, bucketed calibration |
| `research/evaluation/temporal_analysis.py` | lead-time/precision frontier, modality lead-lag, lifecycle sub-task scoring, asynchrony sensitivity |
| `research/statistics/power.py` | empirical power curves, minimum detectable effect, required-sample extrapolation |
| `scripts/run_research_angles.py` | executes the specifications that need no external data (7 at the time; 8 after iteration 3) |

### Product surface (built and verified in iteration 3; see the addendum)

| Area | What now exists |
|---|---|
| Mode architecture | `lib/mode.tsx` — product/research as an independent axis from theme, persisted separately, forced by `/research` routes, and preserving instrument context across the switch |
| Chrome | mode toggle as the second-most prominent control, mode-aware desktop and mobile navigation, theme control, pre-paint boot script |
| Product routes | Home, Explore, Universe, Events, Instruments/[symbol], Watchlist, Settings |
| Research routes | Overview, Experiments, Ablations, Models, Datasets, XAI Lab, Statistics, Figures, Limitations (+ detail), Claim Ledger, Paper Lab, Reproducibility |
| API | risk, experiments, artifacts, research — all read-only over exported artifacts |
| Design system | two-axis tokens (`data-theme` × `data-mode`), colour-blind-safe states with text labels, skip link, reduced-motion support |

**20 pages, 4 API routes, 10 component/lib files.**

---

## TESTED / PASSED

```
pytest tests            256 passed   (was 114 in iteration 1)
ruff check              All checks passed
```

New test modules:

- `tests/unit/test_claims_and_limitations.py` — 42 tests. Asserts every guard pattern
  family fires on a known violation, that no pattern contains a control character, that
  the ledger passes its own rule, that no claim is stated at holdout scope, and that every
  experiment specification is falsifiable (control, treatment, metrics, statistical test,
  threats to validity).
- `tests/unit/test_app_surface.py` — 97 tests. Every `@/` import resolves, every page
  default-exports a component, every API route exports a method, no client hook appears in
  a server component, both mode route trees are complete, mode and theme use separate
  storage keys, the mode switch carries instrument context, and no secret sits behind
  `NEXT_PUBLIC_`.

These were **not** a typecheck and were not claimed to be one. Iteration 3 installed Node
and ran the real thing: `tsc --noEmit` reports zero errors over all 35 files, and the build
prerenders 204 pages. See the addendum.

---

## MEASURED RESULTS — seven experiments executed

Full detail in [`docs/RESEARCH_ANGLES.md`](RESEARCH_ANGLES.md).

| Experiment | Finding |
|---|---|
| **EXP-N03-1** | Sweeping the entry threshold 0.20→0.90 moves median lead time only within −10.0 to 0.0 sessions. **No operating point achieves positive lead time**, so the lateness is a property of the evidence, not the tuning. Only the microstructure proxies lead (+7 sessions, r 0.108). Resolution is the *easier* sub-task (23.5 % within 3 days) than onset (6.1 %). |
| **EXP-L10-1** | ECE rises 0.0835 → 0.3273 across uncertainty quintiles (slope +0.638): the uncertainty estimate correctly identifies where the probability should not be trusted. The coverage counterpart is **NOT MEASURABLE** and is reported as such. |
| **EXP-N04-1** | Uncertainty-weighted fusion has lower selective risk at **all 9** coverage levels despite no AUPRC advantage. Status stays PARTIAL because each arm ranks by its own uncertainty. |
| **EXP-L12-1** | The microstructure null has MDE 0.000185 against an observed 0.000176 — **uninformative, not evidence of zero contribution**. Propagation and affective nulls/effects are informative. |
| **EXP-N02-1** | The regime gap narrows as clusters increase (+5.1e-06 per cluster) and the smallest regime holds 17 episodes: consistent with **variance inflation**, not with regimes being uninformative. |
| **EXP-N01-1** | LIME crosses the 0.80 stability threshold at 6400 perturbations while still cheaper than occlusion — but its rank correlation with occlusion never leaves zero. **Stability is not agreement.** |
| **EXP-L04-2** | Detection rate is 1.0 in both the lowest and highest intensity quartile at n=36: no intensity floor visible at this sample size. |

Plus the **modality information decomposition**: microstructure looks strong alone (0.8168)
purely by riding the market block (unique 0.0002), and regime has a **negative** unique
contribution (−0.0060).

**42 figures** (was 35) and **17 tables** (was 15), zero recorded as NOT GENERATED.

---

## BUGS CAUGHT

Three worth naming, because each would have shipped something that looked right:

1. **The claim guard was a no-op.** An edit wrote its word boundaries as literal control
   characters (0x08 rather than `\b`). Every real-world pattern became unmatchable; the
   module imported, ran, and reported zero problems. "AEGIS detects market manipulation"
   passed. Found by probing it deliberately rather than trusting a clean run. The boundary
   is now applied in one tested helper, and tests assert each family fires.
2. **A spurious calibration trend.** The coverage-versus-ECE analysis reported a confident
   +0.62 slope. Coverage has five distinct values; the quantile bins collapsed onto
   duplicate edges and counted the same rows twice. Now detected and reported as NOT
   MEASURABLE.
3. **A second module-alias shadowing.** A local `reg` DataFrame shadowed the limitations
   registry alias inside the paper generator, silently skipping two tables — the same
   failure mode as iteration 1's `xs` shadowing, caught this time by the skip counter
   being non-zero.

---

## NOT IMPLEMENTED / NOT RUN

| Item | Status | Reason |
|---|---|---|
| Vercel deployment | **NOT RUN** | Build and local serve verified in iteration 3; hosting not performed |
| 10 experiment specifications | **BLOCKED** | Await external data that does not exist |
| Case-study packages | **NOT BUILT** | Need licence-clear media per episode |
| Holdout evaluation | **NOT RUN** | Correct: freeze first (L-11) |
| Tier-2/3 models | **NOT RUN** | Weights not installed (L-08) |

---

## HONEST NOTES ON THE BRIEF

Two requirements could not be met as literally written, and were met in substance instead:

**"NIFTY 50 must be the primary product experience."** No licence-clear point-in-time
Nifty-50 constituent history exists (L-01), and the follow-up brief explicitly forbids
calling the current universe the Nifty 50. The product is therefore built around an
*explicit universe object* with its provenance, churn and caveat surfaced on the Universe
page, in the footer, and in every evidence boundary. The hierarchy the brief asks for —
universe → group → instrument → event → evidence — is intact. Only the label is honest.
Supplying a constituent list turns the same UI into a genuine Nifty-50 experience with no
code change.

**"Sector map."** No licence-clear NSE sector mapping exists (L-07). Grouping is by
measured return co-movement and is called a *statistical cluster*, never a sector, with the
basis stated on the page.

---

## CURRENT MATURITY

| Track | Maturity |
|---|---|
| Research substrate | **research-grade**, executed and reproducible |
| Limitations → experiments | **operational** — 7 of 18 specifications executed, 11 blocked and labelled |
| Claim ledger and guard | **enforced** — fails the build on scope creep, tested against its own rule |
| Product surface | **builds and serves**; not deployed (L-03 addendum) |
| Research conclusions | **preliminary** — synthetic labels, holdout frozen |


---

# Iteration 3 addendum — the build, actually run

Node.js 24.19.0 was installed, and L-03 is discharged.

| Check | Result |
|---|---|
| `tsc --noEmit` | **0 errors** across 35 project files |
| `eslint .` | clean (migrated off the deprecated `next lint` to a flat config) |
| `next build` | **204 pages prerendered**, including 162 instrument routes and 17 limitation routes |
| Route verification | **26 of 26** routes return HTTP 200 with server-rendered content |
| Artifact parity | 6 of 6 sampled values render identical to source |
| Latency | p50 5.9–10.0 ms, p95 17.1–32.9 ms over 20 samples per route |
| `npm audit` | critical vulnerabilities: **0** (Next upgraded 15.1.6 → 15.5.23 for CVE-2025-66478) |

**Two defects the build exposed that no Python test could have.**

1. **The exporter emitted bare `NaN`** — invalid JSON. `JSON.parse` rejects the entire
   document, so `/research/statistics` silently rendered "data not available" in the
   browser while `json.loads` read the identical bytes without complaint on the Python
   side. Every Python test passed throughout. Fixed by sanitising non-finite floats and
   writing with `allow_nan=False`; locked by `tests/unit/test_exported_bundles.py`, which
   parses every bundle the way a browser would.
2. **`useSearchParams` in the mode provider opted the whole client tree out of
   prerendering**, so `/settings` and `/watchlist` served a blank 9.4 KB shell until
   JavaScript loaded — directly against the "never show blank screens" requirement. Fixed
   by isolating the query read into a leaf behind its own Suspense boundary; those pages
   now server-render at 14.6 KB and 12.3 KB.

Both are the kind of defect that only appears when the thing is actually run. That is the
argument for having run it.

**Registry effect.** Runnable specifications rose from 7 to **8 of 18**; blocked fell from
11 to **10**. `CLAIM-12` records the build and parity result at `ENGINEERING` scope, with
"the product is deployed on Vercel" and "the system is production-ready" listed as
restatements the guard must reject.

**What is still not done.** No Vercel deployment has been performed, so cold starts and
edge caching are unmeasured. The remaining ten specifications are blocked on external data
that does not exist, and the holdout stays frozen.
