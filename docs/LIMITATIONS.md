# AEGIS-Market — Limitations register

Read this before any result. Each entry names what is missing, why, what was done instead,
and which claims it invalidates. Nothing here is hedging: these are the boundaries of what
the current release can support.

---

## L-01 — Historical index membership is not available

**What is missing.** A licence-clear, point-in-time list of Nifty-50 constituents by date.

**Why.** No free source with redistribution rights was located. Reconstructing one from
secondary web sources would produce an unverifiable artifact, and fabricating one is
prohibited (spec §85).

**What was done instead.** The research universe is a **point-in-time liquidity-proxy
universe**: at each monthly rebalance, the top 50 symbols by trailing median traded value,
estimated only from sessions strictly preceding the rebalance. It is survivorship-safe by
construction — measured churn is 2.59 entries and 2.59 exits per rebalance across 257
rebalances, with 270 distinct symbols ever selected out of a 50-name universe.

**Invalidated claims.** Nothing may be described as a result "on the Nifty 50". Results are
on a liquidity-proxy universe of NSE large-cap equities. Any comparison to index-level
literature is therefore indicative, not like-for-like.

---

## L-02 — True microstructure is not measured

**What is missing.** Order-book depth, signed order-flow imbalance, VPIN, cancellation
behaviour, execution aggression.

**Why.** NSE does not publish historical Level-2 data openly.

**What was done instead.** Four daily-aggregate proxies computed from the bhavcopy:
average trade size, its z-score, trade-count z-score, and turnover-per-trade z-score. The
six unmeasurable fields are emitted as `NaN` with a stated reason and appear in the
coverage table as `NOT MEASURED` rather than being quietly absent.

**Invalidated claims.** No claim about order-book dynamics, liquidity provision or
predatory order behaviour. The "microstructure" ablation arm tests the *proxies* only.

**Additional gap.** Trade counts are absent from bhavcopy files before roughly 2011;
measured coverage of the `trades` column over 2005–2026 is **0.7815**. Those rows carry
`NaN` for every trades-derived proxy — never zero, since a zero trade count is a
meaningful value that would corrupt the feature.

---

## L-03 — Product build verified; deployment not performed

**RESOLVED (iteration 3).** Node.js 24.19.0 was installed and the application now builds.

**What is now verified.** `tsc --noEmit` passes over all 35 project files with zero
errors. ESLint is clean. `next build` prerenders **204 pages**, including all 162
instrument routes and 17 limitation routes via `generateStaticParams`. All 20 checked
routes return HTTP 200 with server-rendered content against the running production
server, and artifact-to-page value parity holds (AUPRC 0.941166 renders as 0.941; minimum
detectable effect 0.000185 renders exactly). Local p50 latency is 5.9–10.0 ms and p95
17.1–32.9 ms over 20 samples per route, with no model call in the request path.

**What building it exposed.** Two defects that every Python test had passed over:

1. **The exporter emitted bare `NaN`**, which is not valid JSON. `JSON.parse` rejects the
   whole document, so the entire statistics page silently rendered as "data not
   available" while `json.loads` on the Python side accepted it happily. Fixed by
   sanitising non-finite floats and writing with `allow_nan=False`, and locked by
   `tests/unit/test_exported_bundles.py`, which parses every bundle with `parse_constant`
   set to reject.
2. **`useSearchParams` in the mode provider opted the whole client tree out of
   prerendering**, so `/settings` and `/watchlist` shipped a blank 9.4 KB shell until
   JavaScript loaded — directly against the "never show blank screens" requirement. Fixed
   by isolating the query read into a leaf component behind its own Suspense boundary;
   those pages now server-render at 14.6 KB and 12.3 KB.

**What remains unverified.** Deployment to Vercel itself. Cold starts, edge caching and
artifact freshness under a real deployment are unmeasured, so "builds and serves locally"
is the supported claim and "is deployed" is not.

## L-04 — Episode labels are synthetic

**What is missing.** An open, labelled corpus of NSE market-integrity incidents aligned to
instruments and dates.

**Why.** None exists publicly. Labelling real companies as subjects of manipulation from
inference would be both fabrication and defamation.

**What was done instead.** Synthetic episodes are injected into the **real** price panel:
phase-structured intensity profiles perturb returns, volume, turnover and trade counts, and
a matched text corpus is generated. Generator parameters are structurally isolated from
every detector (asserted by an AST-level test), background days also carry media and a
fraction of them carry alarming text with no episode behind them, and features are
recomputed from the modified bars so a detector sees only data.

**Invalidated claims.** **Every detection metric in this repository describes behaviour on
injected episodes.** No number here is evidence that the system detects real-world market
manipulation. That claim would require a labelled incident corpus and a fresh evaluation.

---

## L-05 — Acoustic affect proxies are uncalibrated

**What is missing.** Listener-labelled financial audio to calibrate arousal and valence
proxies against human judgement.

**What was done instead.** Each proxy is a documented monotone transform of measured
acoustics, named `*_proxy` where it is one. The underlying estimators *are* validated
against analytic ground truth: pitch is recovered to within 0.5 % on 220 Hz, 140 Hz and
180 Hz test tones, white noise is correctly reported unvoiced, and a signal constructed
with 40 % silence measures 0.38 pause fraction.

**Invalidated claims.** No claim of validated emotion recognition. Nothing infers a
speaker's internal state.

---

## L-06 — The audio modality operates on sonification, not speech

**What is missing.** A licence-clear corpus of earnings-call or interview audio aligned to
the panel's instruments and dates.

**What was done instead.** The audio channel is fed a deterministic **sonification** of the
market series (pitch tracks realised volatility, amplitude tracks turnover, harmonic
richness tracks abnormal return). It is a real waveform carrying real information about the
instrument-day, processed by the same DSP path a recording would take, and every result
carrying the audio modality is tagged accordingly.

**Invalidated claims.** No claim about prosody, vocal uncertainty or speaker affect on real
recordings. Those are `NOT MEASURED`. The pipeline accepts genuine recordings unchanged, so
this is a data gap and not an architectural one.

---

## L-07 — The propagation graph is purely statistical

**What is missing.** A licence-clear NSE sector, index-weight or ownership mapping.

**What was done instead.** Edges are trailing return correlations above 0.25, estimated
strictly before each decision date.

**Invalidated claims.** An edge asserts co-movement, not an economic, sectoral or causal
relationship.

---

## L-08 — Tier-2 and Tier-3 models were not run

`torch`, `transformers`, `librosa` and OpenCV are deliberately not installed. Every
transformer, CLIP-class and video-language entry in `research/models/registry.py` carries
status `NOT RUN`, and no metric is reported for any of them. The adapter interface exists;
installing weights is the only missing step.

**Consequence.** The reported multimodal performance is that of a Tier-1, CPU-only,
fully inspectable stack. A learned-embedding stack would plausibly do better on the image
and video channels, and that comparison is unmeasured.

---

## L-09 — Image and video channels are views of the same underlying series

In the current release the chart images and chart clips are **rendered from the price
panel**. They are genuine images and genuine video, and the pipelines genuinely process
them, but their information content largely overlaps the market block. This is visible and
expected in the ablation table, where `IMAGE_ONLY` and `VIDEO_ONLY` score far below
`MARKET_ONLY`.

**Consequence.** The image and video ablation arms measure whether the *visual* channel
recovers information from a chart, not whether independent visual evidence adds
information. The latter needs a licence-clear corpus of real financial imagery.

---

## L-10 — Calibration is imperfect and reported as such

Expected calibration error for the full stack is materially above zero. The fusion layer
averages calibrated per-modality scores, which does not itself guarantee a calibrated
output. Reliability diagrams and ECE are published rather than smoothed away; any
downstream use of the score as a probability should account for this.

---

## L-11 — The final holdout has not been evaluated

The `holdout` split (2024-01-01 onward) is frozen and untouched. Every reported number is
on `validation` (2022-01-01 to 2023-12-31). The holdout may be evaluated **once**, after
models, features, thresholds, fusion, XAI methods, figure definitions and the evaluation
protocol are frozen (spec §55, §84).

**Consequence.** No result in this release is an out-of-sample result in the strict sense.

---

## L-12 — Statistical power

Episode counts are in the low hundreds and cluster-bootstrap intervals are correspondingly
wide. Several ablation differences are not distinguishable from zero at a 5 %
false-discovery rate. Where that is the case the table says so, and no narrative is built
on a difference the interval does not support.

---

## L-13 — Company fundamentals are not available

**What is missing.** Revenue growth, net debt, interest coverage, earnings, cash flow and
profitability. The NSE cash bhavcopy carries price, volume and trade counts only, and no
licence-clear point-in-time fundamentals source was obtained.

**Why it matters more than the other data gaps.** The position-lifecycle framework this
release implements came from a domain practitioner whose actual process is built on
exactly these three quantities: check revenue growth, check net debt, check whether
interest coverage still holds. The temporal structure of that process is implemented here.
The inputs are not.

**Why.** Point-in-time fundamentals need a disclosure timestamp kept separate from the
financial period. Applying a quarter's figures from the quarter end rather than the filing
date leaks weeks of future information into every historical decision, and vendor data
frequently gets that timestamp wrong. A source without it is worse than no source.

**What was done instead.** Nothing was substituted. A price-derived stand-in for revenue
growth is a market signal wearing a fundamental label, and labelling it otherwise would be
the fabrication the spec prohibits. The lifecycle analysis runs over market,
microstructure, regime, propagation and the four multimodal blocks, and says so wherever
it appears.

**Invalidated claims.** Anything about fundamental deterioration preceding, accompanying or
following a risk-state change. Anything about revenue growth, net debt or interest
coverage at all. Any claim that this release implements the practitioner framework in
full.

---

## L-14 — Valuation measures are not available

P/E, P/B, EV/EBITDA and free-cash-flow yield each need an accounting quantity from L-13.
Price alone is not a valuation, and no price-only quantity is presented as one. Nothing may
be described as cheap, rich, or re-rating.

---

## L-15 — The position lifecycle is analytical, not observed

No real position, holding period or investor decision exists in this dataset. Each
instrument's risk trajectory is segmented into ENTRY, HOLDING and RESOLUTION by position
within the analysis window. Those are phases of an *estimate*, not of anyone's holding.

The segmentation is mechanical and identical for every instrument, so a stage comparison
compares like with like — but nothing in it licenses a statement about what an investor
did, would have done, or should do. EXP-L15-1 re-runs the whole stage comparison with
phases anchored on the first detected change point instead of on window position; the
importance rankings correlate at **−0.71** (entry) and **+0.52** (resolution) between the
two definitions, and the holding stage cannot be compared at all: under the change-point
definition every holding row sits within ten sessions of a detected change, so the target
is positive everywhere and AUPRC is undefined. That is reported as INSUFFICIENT DATA rather
than as a number, and it is one more reason the stage comparison is inconclusive.

---

## N-06 — Stage-differential informativeness is inconclusive at this sample size

The headline lifecycle question — do the informative signals differ between entry, holding
and resolution? — was run, and the honest answer is that this sample cannot resolve it.

Each stage gets its own model on a common target (a material change in the risk profile
within ten sessions), and per-block permutation importance is compared across stages. The
comparison is only readable against a noise floor, so each stage's importance vector is
also estimated twice on two disjoint halves of the evaluation instruments:

| Stage | Eval rows | Base rate | AUPRC | Lift | Top block, full set | Top block, half A / half B | Reproduces? |
|---|---:|---:|---:|---:|---|---|---|
| ENTRY | 180 | 0.544 | 0.562 | +0.017 | image | image / microstructure | no |
| HOLDING | 1203 | 0.692 | 0.840 | +0.149 | market | market / market | yes |
| RESOLUTION | 180 | 0.361 | 0.447 | +0.086 | market | market / video | no |

Only the holding phase names the same top block on the full evaluation set and on both
halves, and there the ranking is clear: market at 0.097 permutation importance, text at
0.039, every other block within noise of zero. Entry and resolution disagree with
themselves, so the cross-stage correlations of −0.12 (entry vs holding), −0.33 (entry vs
resolution) and −0.19 (holding vs resolution) are unreadable rather than informative.

Note also how little the entry-stage model achieves: AUPRC 0.562 against a base rate of
0.544, a lift of +0.017. A block ranking extracted from a model that barely beats its base
rate would carry little information even if it were stable.

**Why the sample cannot simply be grown.** Phase is assigned by position, so entry
contributes at most ten sessions per instrument. With 35 cohort instruments that caps entry
at 350 rows however long the panel runs. This needs more instruments, not more history —
and the holdout, which would add 18, stays frozen (L-11).

**What must not be said.** That entry-phase risk is driven by different signals; that any
modality matters more at entry; that image leads at entry — the last is what the full
evaluation set shows and it does not survive a split-half check.

---

## N-07 — Signal conflict predicts forward change only through the risk level

Rows where the modalities disagree with the fused estimate show a forward material-change
rate of 0.976 against 0.480 where they agree: an unconditional difference of +0.496 that
looks like a strong result and is not one.

Conflict is defined against the same 0.5 threshold that separates the MODERATE and
ELEVATED bands, so a row can only register conflict when the estimate already sits near or
above that line — which is exactly where a forward transition is close to certain whatever
the modalities are doing. Mean risk is 0.610 on conflicting rows against 0.124 on agreeing
ones; these are not comparable populations.

The coupling is tight enough that **only one risk decile out of ten** holds enough rows
both with and without conflict to support a comparison at all. Within that decile the
difference is **−0.005**. That the other nine deciles cannot be compared is itself part of
the result, and the analysis reports which strata were excluded rather than pooling
silently over the ones that qualified.

The unconditional figure is retained in the artifacts alongside the stratified one, because
the gap between them is the finding.

---

## L-16 — No licence-clear affect-annotated financial audiovisual corpus

**What is established.** General-domain affective validation is COMPLETED: 720
speaker-disjoint RAVDESS performances for speech and face, 207,814 GoEmotions annotations
for text.

**What is not.** Transfer of those models to financial communication is NOT AVAILABLE.
Five candidate corpora were assessed against six acceptance requirements and none
qualified:

| Candidate | Financial domain | Human affect annotation | Licence usable | Disqualification |
|---|---|---|---|---|
| MAEC | yes | no | research use | labels are market outcomes; training on them would be predicting returns and calling it emotion |
| MDRM | yes | no | research use | no affect annotation, and audio only — no video track |
| CMU-MOSEI | no | yes | CC BY-NC-SA 4.0 | general-domain opinion video; calling it the financial domain would be relabelling |
| IEMOCAP | no | yes | signed academic licence | general-domain acted dialogue, and the licence is not machine-verifiable at download |
| CNBC / Bloomberg / Reuters broadcast | yes | no | all rights reserved | copyrighted, unlicensed for redistribution, unannotated; never downloaded |

**Why this is a limitation and not a gap to be papered over.** The obvious shortcut is to
call CMU-MOSEI the financial domain, or to derive affect labels from a model and train on
them. Both would convert an absence of evidence into an appearance of evidence. Neither is
done.

**What would unblock it.** One corpus meeting all six requirements: audiovisual recordings
of humans, financial or business subject matter, human-rated affect annotations, speaker
identifiers, at least six speakers, and a licence verifiable at download. Annotating an
existing licence-clear financial audiovisual corpus for affect would close the gap without
new recordings. The transfer module is implemented and runs unchanged the day such a
corpus exists.

Artifact: `outputs/human_affect/16_financial_domain_transfer/transfer.json`.

---

## L-17 — Vision-language descriptions include visual claims the image does not support

**What was measured.** An 18-stimulus battery, 15 of which contain no human face.

| Model | False face claims (of 15) | True face claims (of 3) | Seconds per image |
|---|---|---|---|
| SmolVLM-256M | 15 | 2 | 43.0 |
| BLIP-VQA-base | 0 | 3 | 7.2 |

**Why neither model is called superior.** BLIP-VQA answered the eyebrow question with
*raised* for all 80 clips, and the mouth question with *open* for 78 of 80. A constant
answer cannot be wrong on a battery that only asks whether a face is present, and it
cannot be informative on clips that differ. The two failures are different, not ordered.

**Consequence.** Vision-language output is one observation channel beside the landmark
pipeline. It is never a label, a target, or ground truth, and no downstream number is
derived from it as though it were an annotation.

Artifact: `outputs/human_affect/15_vlm_family_comparison/family_comparison.json`.

---

## L-18 — Calibration and predictive accuracy are separate axes

On the 80-clip vision-language tier, the best-calibrated arm is not the most accurate one:

| Arm | Accuracy | ECE | Confidence − accuracy |
|---|---|---|---|
| VLM | 0.2375 | 0.0954 | +0.0728 |
| TEXT | 0.1000 | 0.1267 | +0.0785 |
| AUDIO | 0.3417 | 0.1397 | −0.0759 |
| FACE | 0.2625 | 0.1512 | +0.0376 |
| AUDIO+FACE | 0.3833 | 0.1513 | −0.1101 |
| FULL | 0.3958 | 0.1635 | −0.1321 |

The best-calibrated arm is the second-weakest predictor, and the strongest predictor is
the worst calibrated. TEXT is the most overconfident arm in the study while carrying the
least predictive information — its two features cannot separate eight classes, and its
confidence does not reflect that.

**Consequence.** No arm is described as best without naming the metric, and low ECE is
never reported as evidence of predictive quality. ECE is computed under one declared
definition throughout: equal-mass bins, ten bins, on the predicted-class confidence.

Artifact: `outputs/human_affect/14_xai_calibration_representation/xai.json`.

---

## L-19 — Row count overstates the effective sample size

The corpus holds **1,304,458 traceable sample instances** drawn from **58,728 independent
units**, a **design effect of 22.2** rows per unit. Per shard it is far higher: 3,832 on
daily market data, 1,642 on financial text.

This distinction must appear wherever the corpus size is reported. The correct phrasing is
*traceable sample instances*. The phrase *independent observations* is forbidden and is
scanned for, because it would license intervals the data does not support.

Splits are additionally not unit-disjoint: 159 units appear in both train and validation,
158 in both holdout and validation, 151 in both holdout and train, and 3 in both test and
train. Content-level cross-split contamination is checked separately and is clean on every
shard except financial text, where 8 hashes covering 16 rows collide.

**Consequence.** Every interval reported in this study comes from a cluster bootstrap over
units, a leave-one-actor-out fold structure, or a seed noise floor — never from a
row-count standard error.

Artifact: `outputs/corpus/corpus_report.json`.

---

## L-20 — Vision-language evidence is bounded to small CPU-class models

The branch runs SmolVLM-256M, SmolVLM-500M and BLIP-VQA-base on CPU. SmolVLM costs 43.0
seconds per image and BLIP-VQA 7.2. That throughput is the reason the vision-language tier
covers 80 clips and 4 actors rather than the full 720 and 12, and the reason its seed noise
floor is 0.0745 balanced accuracy against 0.0217 on the full tier — an order of magnitude
coarser.

**Consequence.** Nothing here supports a statement about vision-language models in
general, and no difference on that tier smaller than 0.0745 balanced accuracy is
established. Two families are compared on identical stimuli so that a family-specific
failure remains separable from a general one.

---

## N-08 — No fusion rule is established as superior to the others

| Rule | Balanced accuracy | sd | 95% CI | ECE |
|---|---|---|---|---|
| weighted | 0.5292 | 0.0099 | 0.5205 – 0.5379 | 0.2478 |
| uncertainty | 0.5289 | 0.0101 | 0.5200 – 0.5378 | 0.3686 |
| late | 0.5247 | 0.0076 | 0.5181 – 0.5314 | 0.2570 |
| early | 0.5219 | 0.0091 | 0.5139 – 0.5298 | 0.1804 |

The spread between the four is **0.0073** against a 95% seed noise floor of **0.0229**.
Re-seeding alone moves the arms further than the rules move each other, so the ordering is
not evidence. The highest point estimate is reported as the highest point estimate and
nothing more.

What *is* established on the same corpus: fusing AUDIO and FACE exceeds the best single
modality by 0.0823 balanced accuracy, which does clear the 0.0217 floor of the full tier.
Fusion helps; the choice of fusion rule is unresolved on accuracy and clearly separated on
calibration.

Artifact: `outputs/human_affect/12_fusion_strategies/fusion_strategies.json`.

---

## N-09 — Synthetic augmentation degrades real-data performance

| Synthetic share of training set | AUPRC on real validation rows |
|---|---|
| 0% | 0.9412 |
| 10% | 0.9439 |
| 25% | 0.9429 |
| 50% | 0.9076 |
| 75% | 0.3856 |
| 81% | 0.3613 |

At the configured 40,000-row augmentation the paired result is REAL ONLY **0.9390**
against REAL + SYNTHETIC **0.3870**, a difference of −0.5521 against a seed noise floor of
0.0088.

**Why it happens.** Six mechanisms were measured; five are not supported.

| Mechanism | Measurement | Supported |
|---|---|---|
| marginal mismatch | mean KS 0.0028 | no |
| label shift | positive-rate ratio 1.01 | no |
| covariance distortion | mean pairwise correlation error 0.0216 | no |
| mode collapse | effective-rank ratio 1.11 | no |
| feature scale | 0.0000 out-of-range values | no |
| coverage-flag damage | worst flag 0.988 binary | no |
| **interaction loss** | **tree AUC 0.9639 vs linear 0.4952, gap 0.4687** | **yes** |

A Gaussian copula reproduces every marginal and the rank correlation by construction, and
cannot represent dependence beyond second order. The generated rows are marginally correct
and interaction-free, and diluting the training set with them teaches a distribution in
which the target signal does not exist.

**The result is preserved, not optimised away.** The research question it supports is
*under what conditions does synthetic augmentation improve or degrade predictive
performance*, and one condition is now measured: at or below a 25% share on this task, it
is harmless within the seed noise floor.

Artifacts: `outputs/corpus/real_vs_synthetic.json`,
`outputs/corpus/synthetic_ratio_sweep.json`,
`outputs/corpus/05_synthetic_degradation/diagnosis.json`.

---

## N-10 — The vision-language block adds no measurable predictive information beyond the facial block

On the 80-clip tier: FACE 0.2600, FACE+VLM 0.2500; TEXT+AUDIO+FACE 0.4075,
TEXT+AUDIO+FACE+VLM 0.4075. Group permutation importance puts the vision-language block at
0.0042 against 0.1458 for AUDIO and 0.1458 for FACE.

Every one of those differences is inside the tier's 0.0745 seed noise floor, in both
directions. That FACE+VLM sits below FACE is **not** evidence of interference, and the
result is not reported as one.

**What the channel does carry.** It reaches 0.2425 balanced accuracy alone against a
0.1250 chance rate, so it is not empty, and it is the best-calibrated arm on the tier at
ECE 0.0954. Its value in this system is a second, independent way of looking at the same
frames and a human-readable visual rationale — not a predictive contribution.

Artifacts: `outputs/human_affect/11_multimodal_multiseed/multiseed.json`,
`outputs/human_affect/14_xai_calibration_representation/xai.json`.

---

## L-21 - Group-wise analysis is representation analysis, not demographic fairness

Four grouping variables are evaluated. Only one of them is an attribute of a person.

| Grouping | Kind | Best | Worst | Gap | n per group | Reading |
|---|---|---|---|---|---|---|
| actor sex | published person-level metadata | male 0.4615 | female 0.3659 | 0.0957 | 39 / 41 | intervals overlap - unestablished |
| spoken statement | recording condition | statement 2 | statement 1 | 0.1138 | 43 / 37 | intervals overlap - unestablished |
| voiced fraction | measured condition | lower | higher | 0.0250 | 40 / 40 | intervals overlap - unestablished |
| emotional intensity | recording condition | strong | normal | 0.0076 | 36 / 44 | intervals overlap - unestablished |
| face detection quality | measured condition | constant across all 80 clips | - | - | 80 | cannot separate groups |

**Why it is not called fairness.** Age, ethnicity, first language and accent are not
published with the corpus. Inferring them from the recordings would mean constructing
sensitive attributes from biometrics, which is not done here under any framing. The
correct name for what was run is group-wise robustness and representation analysis, and
that is the name used on every surface.

**What overlapping intervals mean.** They mean no difference is established at n between
36 and 44 per group. They do not mean no difference exists, and the register forbids
writing it that way.

---

## L-22 - Affect labels are acted portrayals, not internal states

RAVDESS labels name the emotion an actor was instructed to portray. A model that matches
them recognises an intended portrayal under studio conditions. GoEmotions labels name what
third-party raters read into a comment: mean agreement 0.741, 34.7% of examples unanimous,
and model accuracy running from 0.326 where raters split to 0.827 where they agreed.

**Consequence for every surface.** Outputs are named model-estimated affective signal,
observable expression-related feature, acoustic affective signal and linguistic affective
signal. Nothing in this repository states what a recorded person felt, intended or
concealed. Deception inference, stress inference, trustworthiness inference and identity
recognition are outside scope and are not implemented; facial features are five-landmark
geometry normalised by inter-ocular distance, and no identity representation is computed
anywhere.

---

## L-23 - No licence-clear, labelled, feature-interpretable transaction corpus

The transaction-risk track executes on a **declared synthetic development fixture**. Five
corpora were assessed against six requirements and none satisfied all of them.

| Corpus | Transaction-level | Human labels | Named features | Entity id | Licence verifiable | Disqualification |
|---|---|---|---|---|---|---|
| IEEE-CIS Fraud Detection | yes | yes | no | yes | no | obfuscated features, so no scenario can name what it changes; licence is competition rules accepted in a browser |
| ULB Credit Card Fraud | yes | yes | no | no | yes | 28 unnamed principal components and no account id. The licence is fine; the data cannot carry a scenario |
| PaySim | yes | no | yes | yes | yes | simulator output: its labels belong to that simulator |
| Bank / processor internal | yes | yes | yes | yes | no | not public, not licensed. Never requested, never obtained |
| NPCI / UPI published statistics | no | no | yes | no | yes | aggregates, not records |

**The requirement most of them fail** is that a scenario must be able to *name the feature
it changes*. An assumption about an unnamed principal component cannot be stated, so a
corpus of anonymised components cannot carry a counterfactual however good its labels are.

**What the fixture is.** 6,000 rows across 400 accounts, a declared 14.7% elevated rate,
and a label rule written into the artifact:

```
1.10*amount_z_vs_account + 0.85*amount_24h_z + 1.40*counterparty_novelty
+ 0.70*cross_border + 0.55*device_changed - 0.0009*account_age_days + N(0,1)
```

thresholded at the (1 - elevated_rate) quantile. Stating the rule is the point: a reader
can see exactly why any scorer does well on it, and therefore why no claim rests on it.

**Consequence.** Every transaction figure in this project carries the fixture caveat. The
interface accepts a frame plus a column mapping and runs unchanged the day a qualifying
corpus exists.

Artifact: `outputs/scenario/transaction_corpus_search.json`.

---

## L-24 - Counterfactual simulation is not causal inference

The Scenario Lab reports what a fitted model **would have estimated** had its inputs or its
declared decision rule been different. That is a statement about the model under an
assumption, not about what would have happened in the world.

Three simulation methods, named on every result, because they mean different things:

| Method | What it does | What it can support |
|---|---|---|
| `OBSERVED_STRATUM` | selects rows that really occurred and satisfy a condition | model behaviour on real rows |
| `COUNTERFACTUAL` | alters rows under a stated assumption and re-scores | model sensitivity to that assumption |
| `POLICY_COUNTERFACTUAL` | holds rows, model and scores fixed and changes a declared rule | the difference attributable to that rule, under that policy |

**Why a counterfactual here is not causal.** Establishing that a real intervention would
have produced the outcome additionally requires that the alteration correspond to the
intervention, that nothing else move with it, and that the model remain valid under the
altered distribution. None of the three is established, and the third is unlikely: a
two-sigma shift in every text feature at once is not a distribution the model was fitted
on.

**Forbidden phrasings**, enforced by the claim guard: *the intervention caused*, *would
have prevented*, *recovered*, *the scenario proves*, *causal effect of the policy*.

**Currency figures.** Every rupee value in this project is a modelled difference in a tail
statistic multiplied by a declared notional research base of ₹100,000,000, or an
accounting fact about a declared referral threshold on the fixture. `is_observed` is false
on every row of `outputs/scenario/scenario_money.csv`, because no intervention was ever
performed and nothing was recovered.

---

## Standing prohibitions

The following are never done anywhere in this repository, and the ones that can be tested
are tested:

- no fabricated metrics, datasets, event counts, XAI values, figures or media;
- no copyrighted media downloaded, rehosted or redistributed;
- no advisory output (buy/sell/hold/target/allocation) on any surface, and no
  transactional reading of the lifecycle vocabulary — no entry or exit price,
  level, size or timing is produced or derivable, and that is scanned for;
- no future information in a historical decision;
- no forward-looking constituent list used for a historical date;
- no missing modality imputed so that it can vote;
- no operating threshold selected on evaluation data;
- no order, payment, approval, block or contact is ever executed, and the Scenario Lab's guard refuses any purpose that routes it toward one;
- no currency figure is stated as observed, recovered or prevented: every one is a simulated quantity on a declared notional base, and that is checked.
