# AEGIS-Market — Iteration 1 report

**Date:** 2026-08-18 · **Starting state:** empty repository (1 commit, 14-byte README) ·
**Every number below was produced by running the code, not estimated.**

---

## IMPLEMENTED

| Area | What now exists |
|---|---|
| Data | NSE cash bhavcopy ingestion for **both** archive layouts, bitemporal stamping, PIT liquidity-proxy universe |
| Contracts | `Provenance`, `EvidenceRecord`, `BitemporalStore`, `get_evidence`, `RiskState`, `RiskAssessment` |
| Market | 18 market features, 4 microstructure proxies, 6 declared-and-`NOT MEASURED` fields |
| Regime | GMM regimes, BIC order selection under a pre-declared admissibility rule, bootstrap stability, shuffle null |
| Text | AFAL v1 lexicon (447 terms), exact token-level affect over 15 dimensions |
| Image | Descriptor stack, patch occlusion, fast chart rasteriser, OCR adapter |
| Audio | Prosody/spectral DSP, FFT-batched pitch, market sonification |
| Video | Frame sampling, scene detection, audio branch, licence gate, reference artifacts |
| Fusion | 6 strategies; regime-degeneracy proof and two corrections |
| Model | Per-modality calibrated learners, uncertainty from disagreement + coverage |
| Temporal | Hysteresis state machine, risk windows, censored resolution |
| Propagation | PIT correlation graph, neighbour-stress features |
| Risk | Monotone exposure gate, control/treatment capital consequence with block bootstrap |
| XAI | Permutation, occlusion (incl. group/modality), KernelSHAP, LIME, counterfactual, IG, gradient×input, PDP/ICE/ALE, faithfulness, agreement, sanity suite |
| Statistics | Cluster bootstrap, paired bootstrap, permutation, sign-flip, Benjamini-Hochberg |
| Experiments | Declarative engine, 32 arms, per-arm artifact bundles, reproducibility manifests |
| Artifacts | Figure/table registries, captions (md/tex/json), journal style, paper package |
| Product | Next.js app: 11 views, 3 read-only API routes, server-rendered SVG charts |
| Docs | Audit, gap matrix, architecture, limitations, data licensing, non-advisory policy |

**Files created (measured):** 35 research modules · 6 scripts · 7 test modules ·
23 app/component/lib files · 7 docs · 8 configuration files. **Files modified:** README.md
(replaced). Nothing pre-existing was deleted.

---

## TESTED / PASSED

```
pytest tests            114 passed        (leakage 11 · property 48 · unit 6 ·
                                           multimodal 26 · xai 14 · integration 9)
ruff check              All checks passed
```

**Reproducibility, verified rather than asserted.** The entire experiment suite was
re-executed from scratch after the final code changes and compared against the reported
numbers:

```
arms compared: 32          auprc / auroc / f1 / ece      max abs diff 0.000e+00
stat rows:     31          delta / ci_low / ci_high /
                           p_value / adjusted_p          max abs diff 0.000e+00
                           significance flags            identical
```

Bit-identical, including the 600-resample cluster bootstrap, because every resampler is
seeded from the recorded seed.

Verifications that would have caught a fabricated result:

| Check | Measured outcome |
|---|---|
| L1 randomised as-of, 200 random cutoffs | no record ever returned past its cutoff |
| L2 future shift | features bit-identical after truncating the future |
| L3 restatement | value as of 2024-04-01 is 10.0, as of 2024-06-01 is 4.0 |
| L4 survivorship | forward-looking list refuses historical dates; PIT universe shows churn |
| L5 coverage substitution | zero-coverage modality gets exactly 0 weight; changing its score moves nothing |
| L6 threshold provenance | operating threshold is a function of the training split alone |
| Regime degeneracy | max weight difference **< 1e-12** across 27 parameter combinations |
| Pitch ground truth | 110/140/220/330 Hz recovered within **0.5 %**; white noise correctly unvoiced |
| Pause fraction | 0.38 measured against 0.40 by construction |
| Scene detection | hard cut at frame 5 detected; static clip reports none |
| IG completeness | ∑attributions − (f(x)−f(b)) < **1e-3** |
| Faithfulness discriminates | true attribution deletion-AUC < reversed attribution's |
| Sanity rejects randomised model | ρ = **0.013** against a label-shuffled refit |
| Gate monotonicity | non-increasing over 2,001 grid points, in every uncertainty setting |
| Generator isolation | AST scan: no detector module imports the episode generator |
| Non-advisory scan | zero advisory tokens across `app/`, `components/`, `lib/` |

---

## FAILED / NOT PASSED

**XAI sign consistency: FAIL.** LIME re-run under three seeds agrees on attribution sign
for **0.780** of features, below the 0.80 threshold declared before the run. Combined with
LIME's near-zero rank agreement with occlusion (ρ = −0.042), the conclusion is that **LIME
is not reliable on this model** and no claim is built on it. The threshold was *not* lowered
to make it pass.

**Regime conditioning does not help.** `NO_REGIME` scores AUPRC 0.9471 against `FULL`
0.9412 — a **+0.0060 improvement from removing it** (95 % CI 0.0022–0.0110, BH-adjusted
p = 0.0021). RQ9 is **not supported** in this iteration.

**Early detection: not achieved.** Median lead time is **−10 sessions** and mean
−8.5: the system identifies episodes roughly two weeks *after* onset. RQ5 is **not
supported**.

### Bugs the checks caught before they reached a result

Three worth naming, because each would have produced a plausible but wrong artifact:

1. **A shadowed module alias.** A local `xs` in the paper script shadowed the `xai.sanity`
   alias, making the sanity-suite call an `UnboundLocalError` that the artifact guard would
   have swallowed as a silent skip. Found by `ruff` (F823).
2. **A silently empty feature block.** `attach_propagation` merged onto pre-existing
   placeholder columns, producing `_x`/`_y` suffixes and leaving the propagation block
   entirely NaN — the ablation arm would have "tested" nothing. Found by inspecting
   coverage (`cov_propagation = 0.0`); the function now raises rather than merging into
   suffixed columns.
3. **A degenerate feature.** The return-entropy feature was originally binned on the
   window's own quantiles, which makes every window uniform by construction and pins the
   value near 1.0. Found by looking at its variance (std 0.0000 before, 0.0896 after the
   switch to sigma-based edges).

A fourth was introduced *by tooling*: an aggressive lint autofix rewrote
`{k: v for k, v in df.groupby(...)}` as `dict(df.groupby(...))`, which raises because
pandas exposes `GroupBy.keys` as a string. The integration test caught it; the sites now
carry a `noqa` and an explanation.

---

## MEASURED RESULTS

### Data (real)

| Quantity | Value |
|---|---|
| Panel rows | 8,399,065 |
| Symbols | 4,487 |
| Sessions | 5,337 (2005-01-03 → 2026-08-14) |
| `trades` column coverage | 0.7815 (absent pre-2011; NaN, never zero) |
| Universe rebalances | 257 |
| Distinct universe members ever | 270 for a 50-name universe |
| Churn | 2.59 entries and 2.59 exits per rebalance |
| Dataset | 16,558 rows × 119 columns |
| Positive rate | 0.2229 |
| Splits | train 9,351 · validation 3,855 · **holdout 3,352 (untouched)** |
| Modality coverage | text 0.734 · image 1.000 · audio 1.000 · video 1.000 · market 1.000 · micro 1.000 · regime 1.000 · propagation 0.985 |

### Regimes

k = 4 selected: lowest BIC (14,238.2) among orders meeting the pre-declared rule (minimum
occupancy ≥ 0.05, persistence ≥ 0.50); k = 5 and k = 6 rejected. Bootstrap stability
ARI 0.624 (5–95 %: 0.389–0.789). Shuffle null: observed persistence 0.532 vs null mean
0.373, **p = 0.0164**.

### Detection (validation, positive rate 0.2438)

| Model | AUPRC | AUROC | F1 | ECE |
|---|---|---|---|---|
| **AEGIS full stack** | **0.9412** | 0.9651 | 0.9052 | 0.1227 |
| Static-attention fusion | 0.9480 | 0.9673 | 0.9052 | 0.1934 |
| Market only | 0.8160 | 0.8699 | 0.7287 | 0.0216 |
| Text only | 0.7973 | 0.8690 | 0.7826 | 0.1054 |
| Sentiment only (valence) | 0.6042 | 0.7410 | 0.5970 | 0.0254 |
| Statistical anomaly (unlearned) | 0.2830 | 0.5767 | 0.4082 | 0.2491 |
| Image only | 0.2373 | 0.4872 | 0.2489 | 0.0307 |
| Audio only | 0.2573 | 0.5300 | 0.3364 | 0.0505 |
| Video only | 0.2566 | 0.5106 | 0.1860 | 0.0455 |

AUPRC lift over the no-skill baseline: **3.86×**.

### Ablation, with FDR-controlled significance

26 of 31 paired comparisons are significant at a 5 % false-discovery rate.

| Removing | Δ AUPRC vs full | 95 % CI | adj. p | Verdict |
|---|---|---|---|---|
| text | 0.1239 | 0.0922–0.1559 | 0.0021 | large, significant |
| market | 0.1131 | 0.0834–0.1476 | 0.0021 | large, significant |
| **affective representation** | **0.0888** | 0.0632–0.1163 | 0.0021 | **large, significant (RQ3 supported)** |
| video | 0.0011 | 0.0001–0.0023 | 0.0278 | significant but negligible |
| image | 0.0008 | 0.0003–0.0014 | 0.0021 | significant but negligible |
| audio | 0.0006 | 0.0003–0.0011 | 0.0021 | significant but negligible |
| propagation | 0.0005 | 0.0002–0.0009 | 0.0021 | significant but negligible |
| microstructure proxies | 0.0002 | −0.000006–0.0004 | 0.0689 | not significant |
| regime conditioning | **−0.0060** | −0.0110–−0.0022 | 0.0021 | significant, wrong direction |

Sentiment-only 0.6042 → full affective text 0.7973 is a **+0.193 AUPRC** gain, the clearest
single result in the iteration: affective representation substantially outperforms
sentiment polarity, which is exactly the distinction the specification insists on.

### Regime degeneracy (spec §57)

`FUSION_REGIME_INHERITED` and `FUSION_STATIC` agree to **all six reported decimals**
(0.948033 / 0.967259 / 0.905158 / 0.193376) on independently executed arms, and the
analytic cancellation is verified at < 1e-12. The inherited formulation is not
regime-conditioned. The corrected formulation does vary by regime — and performs
**worse** here (0.9412), which is reported rather than buried.

### Temporal

| Metric | Value |
|---|---|
| True windows / predicted / matched | 36 / 56 / 33 |
| Detection rate | 0.917 |
| False-alarm windows | 23 |
| Median lead time | **−10.0 sessions** (late) |
| Mean absolute onset error | 13.2 days |
| Mean temporal IoU | 0.391 |
| Premature resolution rate | 0.030 |
| Delayed resolution rate | 0.576 |

### Capital consequence (hypothetical research policy — not advice)

| Metric | Control | Treatment | Δ | Significance |
|---|---|---|---|---|
| CVaR (5 %, daily) | −0.03641 | −0.03121 | **+0.00520** | 95 % CI +0.0026 to +0.0079, **p = 0.0005** |
| Max drawdown | −0.5336 | −0.4740 | +0.0596 | 95 % CI −0.053 to +0.090, **p = 0.412** (not significant) |
| Annualised volatility | 0.2182 | 0.1859 | −0.0324 | — |
| Total return | −0.3141 | −0.3297 | −0.0156 | opportunity cost |
| Mean exposure cap | — | 0.828 | — | — |

**Tail-loss reduction is statistically supported; the drawdown improvement is not.** Return
*levels* are meaningless here — injected episodes are adverse by construction — only the
control-versus-treatment difference is interpretable.

### XAI

| Method | Deletion AUC ↓ | Insertion AUC ↑ | Comprehensiveness | Seconds |
|---|---|---|---|---|
| Occlusion | **0.0298** | **0.9286** | 0.9942 | 0.46 |
| KernelSHAP | 0.0290 | 0.9279 | 0.9909 | 1.00 |
| LIME | 0.0371 | 0.9256 | 0.9891 | 0.02 |
| Counterfactual | 0.0588 | 0.9247 | 0.9828 | 0.43 |

Agreement (Spearman): occlusion↔KernelSHAP 0.472 · KernelSHAP↔counterfactual 0.332 ·
occlusion↔counterfactual 0.224 · occlusion↔LIME −0.042.

Sanity: sparsity **PASS** (0.998 of mass in the top 10) · model randomisation **PASS**
(ρ = 0.013) · sign consistency **FAIL** (0.780 < 0.80).

---

## ARTIFACTS GENERATED

- **35 figures** (25 main, 10 supplementary) × 3 formats each = 105 files, plus 35 caption
  triples (md/tex/json). **Zero recorded as NOT GENERATED.**
- **15 tables** × 4 formats (csv/json/md/tex).
- Statistics: modality contribution, global importance, XAI sanity, capital consequence and
  its significance, uncertainty bins, coverage bins, missing-modality robustness,
  propagation edges, temporal per-window, regime degeneracy.
- `paper_package/` — 6.5 MB, self-contained, with its own README of standing caveats.
- Reproducibility manifests recording commit, seed, dataset hash, package versions, OS.
- `public/data/` — 10 JSON bundles totalling 2.7 MB for the product surface.

Regeneration is one command: `python scripts/generate_paper_artifacts.py` (99 s).

---

## NOT IMPLEMENTED / NOT RUN

| Item | Status | Reason |
|---|---|---|
| Next.js build, typecheck, lint | **NOT VERIFIED** | no Node.js in the environment (L-03) |
| Tier-2/Tier-3 models (FinBERT, CLIP, Whisper, VLM) | **NOT RUN** | weights not installed (L-08) |
| OCR, ASR | **NOT AVAILABLE** | no engine installed; empty output, never invented |
| True microstructure (depth, OFI, VPIN, cancellations) | **NOT MEASURED** | not published openly (L-02) |
| Historical Nifty-50 membership | **NOT OBTAINED** | no licence-clear source (L-01) |
| Real speech audio | **NOT MEASURED** | no licence-clear corpus; sonification used (L-06) |
| Case-study packages | **NOT BUILT** | needs licence-clear media per episode |
| Final holdout evaluation | **NOT RUN** | correct: freeze first (L-11) |
| Postgres / object storage | **NOT PROVISIONED** | schema and adapters written; static bundles used |
| Auth, SAST in CI, audit logging | **PARTIAL** | secret scan and header policy written; auth needs a deploy target |

---

## RESEARCH LIMITATIONS

12 entries in `docs/LIMITATIONS.md`. The five that bound every claim: synthetic episode
labels (L-04), liquidity-proxy universe rather than the Nifty 50 (L-01), sonified rather
than spoken audio (L-06), unmeasured true microstructure (L-02), untouched holdout (L-11).
A sixth is worth surfacing: **image and video are renderings of the same price series**
(L-09), which is why they score at chance alone and why their ablation arms measure
visual-channel recovery rather than independent visual evidence.

---

## RQ STATUS

| RQ | Status | Evidence |
|---|---|---|
| RQ1 multimodal improves detection | **supported** | 0.9412 vs 0.8160 market-only, 0.7973 text-only |
| RQ2 each modality adds information | **partial** | text and market yes; image/audio/video significant but negligible (L-09) |
| RQ3 affect beats sentiment | **supported** | 0.7973 vs 0.6042; removing affect costs 0.0888 |
| RQ4 temporal modelling | **partial** | state machine yields windows; no point-anomaly arm run |
| RQ5 early detection | **not supported** | median lead −10 sessions |
| RQ6 resolution identified | **partial** | 0.917 detection, but 0.576 delayed resolution |
| RQ7 propagation improves detection | **negligible** | Δ 0.0005 |
| RQ8 uncertainty fusion cuts false positives | **not supported** | uncertainty-weighted arm 0.9455 < static 0.9480 |
| RQ9 corrected regime fusion wins | **not supported** | 0.9412 < 0.9480 static |
| RQ10 gating cuts tail consequences | **supported for CVaR** | +0.0052, p = 0.0005; drawdown p = 0.412 |
| RQ11 synthetic data helps rare-event detection | **not run** | needs a real-label comparison |
| RQ12 cross-cycle generalisation | **not run** | holdout frozen (L-11) |
| RQ-X1 XAI identifies responsible evidence | **supported** | comprehensiveness 0.994; modality occlusion implemented |
| RQ-X2 explanations faithful | **supported** | deletion 0.030 vs insertion 0.929 |
| RQ-X3 explanations stable | **not supported for LIME** | sign consistency 0.780 |
| RQ-X4 methods agree | **partial** | 0.47 occlusion↔SHAP; LIME disagrees |
| RQ-X5 modality attribution | **supported** | exact score×weight decomposition plus group occlusion |
| RQ-X6 counterfactual resolution conditions | **supported** | greedy sparse search reports reached/not-reached |

---

## Q1 READINESS — honest assessment

The **software** is comprehensive. The **research** is not yet publishable, and the gap is
data, not engineering:

**What would survive review now.** The regime-degeneracy result (an analytic finding with
numerical and empirical confirmation), the affect-versus-sentiment margin, the
reproducibility apparatus, the leakage-test suite, and the negative results reported at
equal prominence.

**What blocks submission.** Detection performance is measured on **synthetic** episodes
(L-04) — no reviewer should accept that as evidence about market manipulation, and neither
should the authors. Until a labelled incident corpus exists, the honest framing of this work
is *a method and evaluation framework, demonstrated on injected episodes*, not *a
manipulation detector*.

**Next dependency, in order.** (1) A labelled or expert-adjudicated incident corpus for the
NSE universe. (2) Licence-clear point-in-time index membership. (3) A licence-clear
financial audio corpus, which converts L-06 from a limitation into a result. (4) Only then:
freeze and evaluate the holdout, once.

---

## CURRENT MATURITY

| Track | Maturity |
|---|---|
| Data ingestion, PIT correctness | **production-grade**, tested against six leakage attacks |
| Market / regime / text | **research-grade**, validated |
| Image / audio / video | **functional**, validated against analytic ground truth, data-limited |
| Fusion, model, temporal, gate | **research-grade** |
| XAI | **research-grade**, with one honest failure |
| Statistics, experiments, artifacts | **research-grade**, fully automated |
| Product surface | **written, build unverified** (L-03) |
| Research conclusions | **preliminary** — synthetic labels, holdout frozen |
