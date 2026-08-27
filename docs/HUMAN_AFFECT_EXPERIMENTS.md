# Human affective computing — executed experiments

Real corpora, real models, real numbers. Everything below was produced by running the
pipeline in this repository; nothing is a specification of work to be done.

## Reproduce

```bash
python scripts/fetch_affective_data.py --dataset RAVDESS_SPEECH_AUDIO
python scripts/fetch_affective_data.py --dataset RAVDESS_SPEECH_VIDEO
python scripts/fetch_affective_data.py --goemotions
python scripts/run_human_affect_experiments.py --all      # speech, text, face
python scripts/run_human_affect_experiments.py --stage face --force-face-features
python scripts/run_human_affect_fusion.py --all           # fusion, robustness, fairness
python scripts/generate_human_affect_figures.py
python scripts/export_affective_lab.py
```

Seed `20260819` throughout. Corpora are downloaded to `data/affective/` (gitignored);
manifests with SHA-256 checksums and the licence read from each source's own API are
written beside them.

## Corpora

| Dataset | Modality | Licence | Size | Role |
|---|---|---|---|---|
| **RAVDESS speech audio** | audio | CC BY-NC-SA 4.0 | 1 440 clips, 24 actors | speech emotion |
| **RAVDESS speech video** | video | CC BY-NC-SA 4.0 | 120 clips/actor | facial expression, and the audiovisual pairing |
| **GoEmotions** | text | Apache-2.0 | 58 009 examples, 207 814 rater rows | linguistic affect and label quality |

Licences were read **programmatically** from Zenodo's and the distributing repository's own
machine-readable metadata at download time, not from secondary description. No media is
redistributed here.

RAVDESS encodes emotion, intensity, statement, repetition and actor in each filename, so
the labels are exact. Actor number also gives actor sex (odd male, even female), which is
the only person-level attribute the corpus publishes and therefore the only one used.

## Protocol

**Every split is speaker-disjoint.** RAVDESS puts the actor in the filename, and a split
that ignores it lets the same voice appear in train and test; the model then recognises the
speaker rather than the emotion. `speaker_disjoint_split` is the only splitter provided, it
balances actor sex across splits, and it **raises** if there are fewer than six actors —
added after a four-actor run silently produced an empty test split.

Model family is chosen on the **validation** actors from a four-way sweep (two calibrated
SVMs, random forest, gradient boosting). The test actors are scored **once**, with the
configuration validation chose.

## Speech emotion — 8 classes, held-out speakers

| Metric | Value |
|---|---:|
| Accuracy | **0.5458** |
| Balanced accuracy | **0.5234** |
| Macro F1 | 0.5149 |
| Cohen κ | 0.4771 |
| Chance | 0.1250 |
| Majority baseline (balanced) | 0.1250 |
| ECE | 0.1034 |
| Arousal R² | **0.4387** |
| Valence R² | 0.1873 |

**4.2× chance** on eight classes with unseen speakers. Selected model: calibrated RBF SVM.

The dimensional result reproduces a known asymmetry: **arousal is far more recoverable from
acoustics than valence** (R² 0.439 against 0.187). That is what the speech-affect literature
reports, and it is why the uncertainty floors in the pipeline are set higher for valence.

Feature-family permutation importance (each family shuffled as a unit, since MFCCs are
correlated by construction):

| Family | Importance |
|---|---:|
| MFCC | +0.1688 |
| Prosody: timing | +0.1094 |
| MFCC delta | +0.0758 |
| Prosody: F0 | +0.0563 |
| Voice quality | +0.0344 |
| Prosody: energy | +0.0211 |
| Spectral | −0.0023 |

MFCCs dominate; the spectral summary contributes nothing once they are present, which is
what a negative permutation score means.

**The speech content gate accepts 100% of real RAVDESS clips.** That is the positive
control for a guard whose negative controls are all market sonification — it rejects tone
like signals without rejecting speech.

## Linguistic affect — GoEmotions, 7 Ekman classes

| Metric | Value |
|---|---:|
| Accuracy | **0.6182** |
| Balanced accuracy | 0.4646 |
| Macro F1 | 0.5036 |
| Chance | 0.1429 |
| ECE | 0.0888 |

TF-IDF over word and character n-grams into a calibrated linear classifier. Linear on
purpose: the coefficients are directly readable as exact token attributions, so the
explainability requirement is met without a surrogate.

### Label quality — the most interesting result here

GoEmotions is the only corpus in this project with multiple raters per example, which makes
this question answerable at all:

| Annotator agreement | n | Model accuracy |
|---|---:|---:|
| minority / split (0.37) | 1 152 | 0.3255 |
| weak majority (0.64) | 3 942 | 0.5289 |
| strong majority (0.79) | 549 | 0.7086 |
| unanimous (1.00) | 3 059 | **0.8274** |

**Accuracy spread across agreement bands: 0.5019.** The model reaches 0.827 where the
annotators agreed and 0.326 where they split. A large part of what a headline accuracy would
call model error is **label noise**, and the ceiling is set by how much the humans agreed —
not by the model. Mean agreement across the corpus is 0.741 and only 34.7% of examples are
unanimous.

### Why the text model is not trained on RAVDESS

RAVDESS contains exactly two sentences: *"Kids are talking by the door"* and *"Dogs are
sitting by the door"*. Measured rather than assumed, the best achievable text-only
classifier on RAVDESS scores **balanced accuracy 0.1250 against a chance rate of 0.1250** —
exactly chance. Its lexical channel carries no emotion information whatsoever.

That is why the linguistic model is trained on GoEmotions, and why the RAVDESS text channel
is retained in the fusion experiment only to show what a genuinely uninformative modality
does to a fusion model.

## Facial expression — real human video

Detector: **YuNet** (OpenCV model zoo, MIT), after OpenCV 5 removed `CascadeClassifier` and
stopped shipping Haar cascades — the first implementation assumed they were still there and
failed on construction.

Expression features are **five-landmark geometry normalised by inter-ocular distance**, so
every measure is invariant to how far the person sits from the camera: mouth width, mouth
openness, mouth-corner tilt against the eye line, eye-mouth distance, nose-mouth distance,
head roll, facial asymmetry. Plus region appearance statistics and per-frame quality. Each
is aggregated over frames as mean, standard deviation, range and frame-to-frame volatility,
because an expression is a trajectory and a mean discards the dynamics.

**Face detection rate: 100.0%** across all 1 440 processed video files, zero clips with no
detection.

### Speaker-independent facial emotion, 8 classes

| Metric | Value |
|---|---:|
| Accuracy | **0.3917** |
| Balanced accuracy | **0.3828** |
| Macro F1 | 0.3486 |
| Cohen κ | 0.3039 |
| Chance | 0.1250 |
| ECE | 0.0969 |
| Valence R² | **0.2738** |
| Arousal R² | 0.0789 |

**3.1× chance** on eight classes with unseen faces. Top feature by permutation importance:
`mouth_width_ratio_mean`.

**The dimensional asymmetry inverts against speech, and that is the interesting part.**
Acoustics recover arousal far better than valence (R² 0.439 against 0.187). Faces recover
*valence* far better than arousal (0.274 against 0.079). The two modalities are not weaker
and stronger copies of one another; they are informative about different axes of affect,
which is the substantive reason to fuse them rather than an assumption that more inputs
help.

### Each performance is published twice, and counting both inflates the result

RAVDESS ships every video performance under two modality codes: `01` is the full
audiovisual recording and `02` is the same take with the audio stripped. **The pictures are
identical.** An undeduplicated video index is therefore exactly twice its true size — 1 440
files covering 720 performances.

Nothing leaks: both copies belong to the same actor, so speaker-disjoint splitting keeps
them on the same side. What breaks is the sample size, and with it every interval computed
from it — a "240-clip test set" that holds 120 distinct recordings. Because accuracy is not
biased by duplication in any obvious direction, this is invisible in the headline number.

Measured, it was not negligible: the duplicated model reported **0.4292** accuracy where
the deduplicated one reports **0.3917**. `drop_duplicate_video` is applied on load, so a
cache written before the fix heals rather than carrying the duplicates forward.

The negative control is the one that matters: **0 of 3 real rendered market charts from this
repository's own generator produce a face detection**, against 14/14 on real video frames.
The content gate is empirically real, not merely declared.

An early version of the feature set had `mouth_corner_lift` defined against the nose, which
made it algebraically −1 × mouth openness — two perfectly anti-correlated features that look
like two pieces of evidence and are one. Replaced with the corner tilt against the eye line,
which carries independent information.

### Detection runs at native resolution, and that is not an accident

Detecting on a 640-wide copy of each frame is **3.7× faster** and the bounding boxes barely
move, so the obvious optimisation looks free. It is not. On the first clip tested:

| Detection pass | eye landmark separation | reported head roll |
|---|---:|---:|
| native 1280×720 | 0.1 px | **−0.01°** |
| downscaled to 640 | 9.7 px | 3.65° |
| re-detected in a padded crop | 16.7 px | 6.88° |

RAVDESS is recorded on a fixed, level camera, so roll near zero is the correct answer and
the faster passes invent several degrees of head pose that is not in the recording. The
coarse-to-fine variant is worse than the plain downscale because the crop's aspect ratio
falls outside what the detector was tuned for. Since the boxes agree in all three cases, a
box-level check would not have caught this at all.

`DETECT_MAX_EDGE = 0` and a test asserts it, because this is precisely the constant a later
performance pass would quietly raise.

The speed came from elsewhere instead: reusing one detector across a sweep rather than
reloading the ONNX graph per clip, decoding through ffmpeg's own `fps` filter rather than
iterating and discarding frames in Python, single-precision luma in the quality pass, and
seven worker processes each pinned to one OpenCV thread.

## Fusion, robustness, fairness

Audio and video are joined on **clip identity** — the same utterance by the same actor
recorded simultaneously — not paired by label. The split is computed once over the
intersection and applied to both, so an actor cannot be in audio-train and face-test.

Late fusion over calibrated posteriors, with weights grid-searched on validation. The
pooling is geometric (log-opinion), whose defining property is a **veto**: a class any
modality rules out is suppressed. Measured example in the `fuse()` docstring — an earlier
docstring claimed it was globally more conservative, which is false; it is more deferential
to agreement, and the winning class gets *sharper*.

**Every non-empty subset of the three modalities is scored**, on the same held-out actors:
audio, face, text, audio+face, audio+text, face+text, audio+face+text. Seven arms rather
than a fused-versus-best-single comparison, because "fusion helps" should be a claim about
the whole lattice and not about one chosen baseline.

The third arm is the RAVDESS lexical channel, and it is included **because** it carries
nothing: the corpus speaks two fixed sentences, measured at exactly chance above. A model is
genuinely fit on it rather than stubbed with a uniform vector, so what enters the fusion is
a real trained channel that happens to be uninformative. A fusion scheme that cannot absorb
a null modality without losing accuracy is fragile in a way an audio-plus-video table would
never reveal.

### Ablation over every modality subset

720 aligned performances, 12 actors, speaker-disjoint, scored once on the held-out actors.

| Subset | Accuracy | Balanced | Macro F1 | ECE |
|---|---:|---:|---:|---:|
| audio only | 0.4667 | 0.4688 | 0.4637 | 0.1673 |
| face only | 0.3583 | 0.3672 | 0.3309 | 0.4018 |
| text only | 0.1333 | **0.1250** | 0.0526 | 0.1885 |
| **audio + face** | **0.5917** | **0.5938** | **0.5959** | 0.2513 |
| audio + text | 0.4667 | 0.4688 | 0.4637 | 0.1673 |
| face + text | 0.3583 | 0.3672 | 0.3309 | 0.4018 |
| audio + face + text | 0.5917 | 0.5938 | 0.5959 | 0.2513 |

**Fusion gains +0.1250 balanced accuracy over the best single modality** (0.5938 against
0.4688). Given the inverted valence/arousal asymmetry above, that is the expected direction
rather than a surprise — but it is measured, and the table would have shown it if it had
gone the other way.

**The null modality costs exactly nothing.** The text arm lands on 0.1250 balanced accuracy
against a chance rate of 0.1250 — exactly chance, as the earlier information analysis
predicted. Validation assigned it a weight of 0.000, and every subset containing it is
*identical to the same subset without it*, to four decimal places. That is the property the
arm was included to test: a fusion scheme that cannot absorb an uninformative input without
losing accuracy is fragile in a way an audio-plus-video table would never reveal. Weights
were `audio 0.889, face 0.111, text 0.000`.

One implementation detail decided whether this table was readable at all. Weights are
fitted for the full ensemble, where a useless modality correctly receives zero. Carried
into a single-modality subset unchanged, an all-zero weighting makes the geometric pool
uniform and the arm scores the base rate of whichever class sorts first — which prints as
"this modality is worthless" when what happened is that it was switched off. Weights are
renormalised within each subset; the fix moved a face-only arm in a development run from
0.1250 (exactly chance, the artefact) to its real 0.3333.

### Disagreement predicts error

The two modalities name the same emotion on only **24.2%** of test clips, and the
Jensen-Shannon divergence between their posteriors tracks whether the fused prediction is
right:

| JS divergence | n | Fused accuracy |
|---|---:|---:|
| 0.130 – 0.367 | 30 | 0.6000 |
| 0.367 – 0.453 | 30 | 0.6667 |
| 0.453 – 0.569 | 30 | 0.6667 |
| 0.569 – 0.904 | 30 | **0.4333** |

The highest-disagreement quartile is the one the fused model gets wrong most often. Cross-
modal disagreement is therefore usable as an uncertainty signal that neither modality
produces on its own.

### Robustness — corruption applied to the signal, not the features

The waveform and the pixels are degraded and the **entire feature pipeline is re-run** over
them. Feature-space noise would be far cheaper and would answer a different question.
Baselines on the 60-clip subset: audio 0.5244, face 0.3400 balanced accuracy.

| Modality | Corruption | 0.10 | 0.25 | 0.50 |
|---|---|---:|---:|---:|
| audio | gaussian noise | 0.2805 | 0.2944 | 0.2845 |
| audio | dropout | 0.4412 | 0.2793 | **0.1593** |
| audio | clipping | 0.5244 | 0.5105 | 0.4927 |
| audio | low-pass | 0.4597 | 0.4493 | 0.4758 |
| face | blur | 0.3067 | 0.2779 | 0.2892 |
| face | darkness | 0.3053 | 0.2550 | 0.2899 |
| face | occlusion | 0.3310 | **0.1250** | **0.1250** |
| face | noise | 0.3357 | 0.3179 | 0.2444 |

Three things worth reading off this table.

**Additive noise is the worst audio failure, and it is not gradual.** Even the mildest
level costs 0.24 balanced accuracy and the further levels cost no more — the acoustic
features degrade at the first sign of broadband noise rather than sliding.

**Clipping is nearly free; dropout is catastrophic.** A recording that is too loud stays
usable (−0.03 at the heaviest setting). A recording with half its samples missing collapses
to 0.159, below the 0.125 chance line's neighbourhood. Loudness damage and absence damage
are not the same kind of problem, and a single "audio robustness" number would hide that.

**Occlusion fails through the detector, visibly.** At severity 0.25 the face detection rate
is still 0.979 but accuracy is already at chance; at 0.50 detection collapses to **0.002**
and the model reports chance rather than guessing. That is the correct failure mode: the
pipeline says it cannot see a face instead of producing a confident answer from nothing.

#### The low-pass row was measuring nothing, and said so by being too clean

The first run reported low-pass degradation of **exactly +0.0000 at all three severities** —
identical to four decimal places, which is not what robustness looks like.

The corruption was real, and it was landing where the model could not see it. Severity was
defined as a fraction of the *source* spectrum; RAVDESS is captured at 48 kHz while the
speech features resample to 16 kHz, so even severity 0.5 only removed 12–24 kHz, entirely
above the 8 kHz the features analyse. Severity is now defined against the analysed band,
and the same sweep reports −0.065 / −0.075 / −0.049. A test asserts that a stronger low-pass
moves the MFCCs further.

Random corruption only — nothing here licenses an adversarial claim, which is a different
property requiring an attacker model.

### Performance across groups

| Grouping | Value | n | Accuracy | 95% Wilson interval |
|---|---|---:|---:|---|
| actor sex | female | 60 | 0.5333 | 0.409 – 0.654 |
| actor sex | male | 60 | 0.6500 | 0.524 – 0.758 |
| intensity | normal | 64 | 0.4844 | 0.366 – 0.604 |
| intensity | strong | 56 | 0.7143 | 0.585 – 0.816 |
| statement | "Kids are talking by the door" | 60 | 0.6167 | 0.490 – 0.729 |
| statement | "Dogs are sitting by the door" | 60 | 0.5667 | 0.441 – 0.684 |

**Every interval overlaps, so none of these gaps is established.** The largest raw gap is
0.230 by emotional intensity — strongly portrayed emotions are easier to read, which is
what one would expect — but with 56 and 64 clips the intervals still overlap and the honest
report is *unestablished*, not *unfair* and not *fair*. Reporting the point estimates alone
would support a confident claim in either direction that this sample cannot carry.

Fairness uses the metadata RAVDESS actually publishes — actor sex, emotional intensity,
spoken statement — with Wilson intervals, and reports a gap whose intervals overlap as
**unestablished** rather than as unfairness. No demographic attribute is invented.

## What these results do not support

- **Acted, not spontaneous.** RAVDESS actors portray emotions on cue in a studio. Financial
  media is spontaneous, and transfer is an open question, not a result.
- **Not financial-domain.** These corpora are general-domain. The domain-shift experiment
  needs a licence-clear affect-annotated financial audiovisual corpus, and none has been
  identified.
- **Valence and arousal are derived**, from a declared circumplex mapping of the categorical
  labels. RAVDESS ships no continuous annotations, so the regression scores are against
  mapped values rather than human dimensional ratings.
- **No advisory output, and no prohibited inference.** Nothing produces a trading signal.
  Deception, identity, clinical state and employment suitability are refused by executed
  guards, not by policy.
