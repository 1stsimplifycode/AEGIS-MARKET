# Closure phase: what the seeds, the second VLM family and the diagnosis showed

Everything here is measured. Three of the results are negative, and they are the most
useful ones.

## Reproduce

```bash
python scripts/run_multimodal_multiseed.py --tier both --seeds 5
python scripts/run_vlm_family_comparison.py --all
python scripts/run_fusion_strategies.py --seeds 5
python scripts/run_multimodal_robustness.py --seeds 3
python scripts/run_multimodal_xai_fairness.py --seeds 3
python scripts/diagnose_synthetic_degradation.py
python scripts/generate_paper_tables.py
python scripts/generate_research_figures.py
```

## Multimodal multi-seed (§1)

Two tiers, because the vision-language channel covers only part of the corpus and shrinking
every other arm to match it would waste 640 clips. Leave-one-actor-out, speaker-disjoint,
five seeds; seeds vary only the learner, so the spread is seed variance alone.

### Full tier — 720 performances, 12 actors

| Arm | Balanced accuracy | sd | min | max | 95% CI on the mean |
|---|---:|---:|---:|---:|---|
| **AUDIO+FACE** | **0.5219** | 0.0091 | 0.5091 | 0.5339 | 0.5139 – 0.5298 |
| TEXT+AUDIO+FACE | 0.5180 | 0.0073 | 0.5117 | 0.5299 | 0.5116 – 0.5243 |
| TEXT+AUDIO | 0.4409 | 0.0059 | 0.4349 | 0.4479 | 0.4357 – 0.4461 |
| AUDIO | 0.4396 | 0.0067 | 0.4297 | 0.4479 | 0.4337 – 0.4454 |
| TEXT+FACE | 0.3898 | 0.0119 | 0.3789 | 0.4062 | 0.3794 – 0.4003 |
| FACE | 0.3885 | 0.0086 | 0.3828 | 0.4036 | 0.3810 – 0.3961 |
| TEXT | 0.1250 | **0.0000** | 0.1250 | 0.1250 | 0.1250 – 0.1250 |

Pooled seed sd **0.0078**; 95% noise floor **0.0217**.

**AUDIO+FACE beats the best unimodal arm by +0.0823 — nearly four times the noise floor, so
the multimodal gain is established.** The text control lands on exactly 0.1250 with zero
variance across all five seeds, which is what a channel carrying no information looks like.

### Vision-language tier — 80 clips, 4 actors, all 15 subsets

Pooled seed sd **0.0269**; 95% noise floor **0.0745**. Best arm TEXT+AUDIO+FACE 0.4075, a
gain of +0.0425 over AUDIO — **below the floor, so not established on this tier.**

| Arm | Balanced accuracy | sd |
|---|---:|---:|
| TEXT+AUDIO+FACE | 0.4075 | 0.0288 |
| TEXT+AUDIO+FACE+VLM | 0.4075 | 0.0326 |
| AUDIO+FACE+VLM | 0.3950 | 0.0288 |
| AUDIO+FACE | 0.3900 | 0.0271 |
| AUDIO | 0.3650 | 0.0418 |
| AUDIO+VLM | 0.3625 | 0.0250 |
| FACE | 0.2600 | 0.0105 |
| FACE+VLM | **0.2500** | 0.0153 |
| VLM | 0.2425 | 0.0143 |
| TEXT | 0.0900 | 0.0163 |

Note **FACE+VLM (0.2500) is below FACE alone (0.2600)** and the full-plus-VLM arm is
identical to the full arm without it. Across five seeds the VLM channel adds nothing
measurable.

## Two VLM families (§2)

Florence-2 remains blocked (KI-08). The second family is **BLIP-VQA** — a ViT-B/16 encoder
with a BERT encoder-decoder and a question-answering head, against SmolVLM's SigLIP tower
feeding a Llama decoder. Genuinely different architecture *and* different interaction mode.

| | SmolVLM-256M | BLIP-VQA-base |
|---|---|---|
| Family | SmolVLM | BLIP |
| Parameters | 256M | 385M |
| Licence | Apache-2.0 | BSD-3-Clause |
| Mode | free-form description | question answering |
| **Seconds per image** | **43.0** | **7.2** |
| Ungrounded terms | 0 in 160 | 0 in 80 |

### The hallucination battery — six classes, one contains a face

| Stimulus class | Contains a face | SmolVLM claims a face | BLIP claims a face |
|---|---|---:|---:|
| human_face | yes | 0.667 | **1.000** |
| market_chart | no | **1.000** | **0.000** |
| research_figure | no | **1.000** | **0.000** |
| text_only | no | **1.000** | **0.000** |
| empty_background | no | **1.000** | **0.000** |
| noise | no | **1.000** | **0.000** |

**SmolVLM claims a face in every one of the 15 faceless stimuli and misses it in one of
three real ones. BLIP-VQA gets all 18 right.** The specialised YuNet detector also reports
no face on rendered charts.

That is the sharpest result in the closure phase, and it is about *interaction mode* as much
as architecture: a model asked to describe a face will describe one, while a model asked
whether a person is present can say no. **The practical consequence is a design rule: ask
the grounding question first and gate on it.**

BLIP has its own failure, in the opposite direction. Its per-region answers are nearly
constant — `eyebrows: raised` for **80 of 80** clips, mouth open for 78, eyes open for 79.
Only head direction varies. It is well grounded and largely uninformative; SmolVLM
hallucinates but varies. Neither is a detector.

## Does the VLM add information? (§7)

Measured three ways, all agreeing:

| Evidence | Result |
|---|---|
| Group permutation importance | VLM **+0.0042 ± 0.0072** against AUDIO +0.1458 ± 0.0331 and FACE +0.1458 ± 0.0500 |
| Five-seed ablation | FACE+VLM 0.2500 vs FACE 0.2600; full+VLM identical to full |
| Latency cost | +43 s per image for SmolVLM, +7.2 s for BLIP |

The VLM block's importance is smaller than its own standard deviation. The claim
*"VLM-derived visual information adds value beyond the specialised facial model"* is
recorded as **NOT SUPPORTED** — measured, not assumed, and not hidden.

What the VLM *does* provide: a readable rationale. It is labelled a **model-generated
visual rationale**, never an explanation, because no faithfulness evaluation of it exists.

## Why synthetic augmentation collapses (§4)

Seven candidate mechanisms, each measured. **Six ruled out:**

| Mechanism | Measurement | Verdict |
|---|---|---|
| marginal mismatch | mean KS 0.0028 | ruled out |
| label shift | positive rate ratio 1.01 | ruled out |
| covariance distortion | mean correlation error 0.0216 | ruled out |
| mode collapse | effective rank ratio 1.11 | ruled out |
| feature scale | 0.0000 out of training range | ruled out |
| coverage-flag damage | 0.988 binary | ruled out |
| **interaction loss** | **tree AUC 0.9639 vs linear AUC 0.4952** | **SUPPORTED** |

A linear model — which can only use first- and second-order structure — **cannot separate
real from generated at all** (0.4952 is chance). A tree ensemble separates them at 0.9639.
The entire difference lives in interactions, which is precisely what a Gaussian copula
cannot represent.

**Research claim, supported:** *uncontrolled synthetic augmentation can degrade predictive
performance despite low measured distributional distance.*

The generator was not tuned to improve the number. The number was explained.

## Fusion rules (§8), and a correction

**Correction first.** An earlier report of mine put speech 0.5458, face 0.3917, text 0.6182
and fusion 0.5938 side by side, inviting the reading that fusion underperforms text. They
are not comparable: 0.6182 is accuracy on GoEmotions over 7 classes; 0.5938 is balanced
accuracy on RAVDESS over 8. **On RAVDESS the text channel scores exactly chance (0.1250)**
and fusion is far above every unimodal arm. The comparison was the error, not the fusion.

Five rules, one corpus, one metric, one split, five seeds:

| Rule | Balanced accuracy | sd | ECE |
|---|---:|---:|---:|
| uncertainty-weighted | 0.5289 | 0.0101 | 0.3686 |
| **validation-weighted** | **0.5292** | 0.0099 | 0.2478 |
| late | 0.5247 | 0.0076 | 0.2570 |
| early | 0.5219 | 0.0091 | 0.1804 |
| text-only control | 0.1250 | 0.0000 | 0.1590 |

Spread between the four real rules: **0.0073, against a noise floor of 0.0229 — no rule is
established as best.** The accuracy ordering is inside the noise; the calibration ordering
is not, and early fusion is by some distance the best calibrated.

### A defect this comparison exposed

The first run put validation-weighted fusion at 0.3885 with ECE 0.0700 — *exactly*
face-alone's numbers. The weight grid was being fitted against the forest's predictions on
its own training rows, which are close to memorised, so the search optimised a fiction and
collapsed to a degenerate face-only solution. Refitting on **out-of-bag** posteriors moved
it to 0.5292. Two numbers matching another arm to four decimal places is what gave it away.

## Multimodal robustness (§11)

Clean baseline 0.5208. Fitted once on clean training folds; only the evaluation side is
degraded.

| Condition | Balanced accuracy | Δ |
|---|---:|---:|
| **missing audio** | **0.1467** | **−0.3741** |
| missing face | 0.2010 | −0.3199 |
| **misaligned audio** | **0.2548** | **−0.2661** |
| **misaligned face** | **0.3273** | **−0.1936** |
| dropout audio 0.50 | 0.3698 | −0.1510 |
| dropout face 0.50 | 0.4167 | −0.1042 |
| noise audio 0.50 | 0.4931 | −0.0278 |
| noise face 0.50 | 0.5082 | −0.0126 |
| missing text | 0.5191 | −0.0017 |
| noise/dropout text | 0.5195 – 0.5208 | ≈0 |

**Misalignment is the result worth having.** Rows of one block are permuted *within each
actor*, so the speaker and the label distribution are unchanged and only the
audio-video correspondence is destroyed. It costs 0.19–0.27 — more than heavy noise on
either stream. **The fusion gain genuinely comes from the pairing, not from having two
feature sets.** Had this been near zero, the whole audiovisual design would have been
decorative.

Text is unaffected by anything, which is the same null-channel signature seen everywhere
else.

## Calibration (§9)

| Arm | Accuracy | Mean confidence | Confidence − accuracy | ECE | Brier |
|---|---:|---:|---:|---:|---:|
| **VLM** | 0.2375 | 0.3103 | +0.0728 | **0.0954** | 0.8880 |
| TEXT | 0.1000 | 0.1785 | **+0.0785** | 0.1267 | 0.9041 |
| AUDIO | 0.3417 | 0.2658 | −0.0759 | 0.1397 | 0.8003 |
| FACE | 0.2625 | 0.3001 | +0.0376 | 0.1512 | 0.8365 |
| AUDIO+FACE | 0.3833 | 0.2732 | −0.1101 | 0.1513 | 0.7726 |
| FULL | 0.3958 | 0.2637 | −0.1321 | 0.1635 | **0.7759** |

Best calibrated: **VLM** — the least accurate arm. Most overconfident: **TEXT**, the arm
with no information. Most *under*confident: FULL, the most accurate. **Calibration quality
and accuracy run in opposite directions here**, so an arm cannot be chosen on ECE alone.

## Representation (§15)

Not demographic fairness, and not called it. RAVDESS publishes actor sex and nothing else
about the people, so no other person-level attribute is analysed and none is inferred. The
remaining groups are recording conditions the pipeline measures for itself.

| Grouping | Best | Worst | Gap | Reading |
|---|---|---|---:|---|
| statement | 2 | 1 | +0.1138 | intervals overlap — unestablished |
| actor sex | male | female | +0.0957 | intervals overlap — unestablished |
| voiced fraction | lower | higher | +0.0250 | intervals overlap — unestablished |
| intensity | strong | normal | +0.0076 | intervals overlap — unestablished |

**All four gaps are unestablished at this sample size.** Every group carries its n and a
Wilson interval; none of these is reported as fairness or as unfairness.

## Financial-domain transfer (§12)

- General-domain affective validation: **COMPLETED**
- Financial-domain affective validation: **NOT AVAILABLE**
- Financial-domain transfer: **LIMITATION**

Five candidate corpora were considered and each is recorded with its specific
disqualification:

| Corpus | Financial | Affect-annotated | Why not |
|---|---|---|---|
| MAEC | yes | **no** | labels are market outcomes; training on them is return prediction wearing an affective label |
| MDRM | yes | **no** | no affect annotation, and audio only |
| CMU-MOSEI | **no** | yes | general-domain opinion video; using it as "financial" would be relabelling |
| IEMOCAP | **no** | yes | general-domain acted dialogue; licence not machine-verifiable at download |
| CNBC/Bloomberg/Reuters | yes | **no** | copyrighted, unannotated, never downloaded |

`validate_target_domain()` **refuses** a general-domain corpus offered as the financial one,
because a transfer number computed that way would measure corpus identity. The interface is
complete and the experiment runs unchanged the moment a qualifying corpus exists — the
nearest miss is a licence-clear financial audiovisual corpus that someone annotates for
affect, which needs no new recordings.
