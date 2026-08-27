# The vision-language branch

A VLM here is a **second, independent way of looking at the frames** the specialised facial
pipeline already measures. It is not a replacement for that pipeline and it is not ground
truth. The question is whether a general vision-language model sees anything five-landmark
geometry does not, and the only way to answer it is to run both on the same frames.

## Reproduce

```bash
python scripts/run_vlm_experiments.py --stage describe --backend smolvlm-256m
python scripts/run_vlm_experiments.py --stage describe --backend smolvlm-500m
python scripts/run_vlm_experiments.py --stage temporal --stage consistency --stage robustness
python scripts/run_vlm_ablation.py
```

Or `HUMAN_AFFECT\09_vlm_visual_observation\run.bat` and `10_vlm_ablation\run.bat`.

## Hardware decided the models

Intel i7-8665U, 8 logical cores, 15.8 GB RAM, **no CUDA device**. That rules out the
3B-and-up families outright — a single frame through Qwen2.5-VL-3B on this CPU is minutes,
and a study needs hundreds of frames. What fits:

| Model | Params | Licence | Role | Measured cost |
|---|---|---|---|---|
| SmolVLM-256M-Instruct | 256M | Apache-2.0 | primary | **76.1 s/frame** |
| SmolVLM-500M-Instruct | 500M | Apache-2.0 | secondary | **89.4 s/frame** |

Florence-2-base was fetched and attempted as a third, architecturally different backend.
It fails to run under transformers 5.15: its bundled remote code reads
`forced_bos_token_id` off a config object that no longer carries it. Recorded as blocked
rather than worked around, because pinning an older transformers to accommodate it would
have broken the two models that do run.

**The two backends share an architecture family.** The cross-model comparison below is
weaker for it: it tests whether *capacity* changes what is reported, not whether a
different architecture would see something else.

## The evaluated subset is not the corpus

At ~80 s/frame, the VLM sees a stratified sample: **80 clips, balanced across all eight
emotions, drawn from four held-out actors**, one peak frame each, described by both models
— 160 observations. Held-out actors on purpose, since the facial model being compared
against was fitted on the training actors.

Every inference is cached on the image content, so re-running the analysis is free and an
interrupted run resumes where it stopped. No output exists for a frame a model did not
actually see.

## Prompts ask for evidence, and the guard fires before the model loads

A vision-language model will answer "is this person lying" fluently and at length, and the
answer is indistinguishable **in form** from a description of a mouth position. Nothing
downstream can tell them apart, so the refusal happens before the forward pass:

```python
assert_prompt_is_observational(prompt)   # raises UnsafePromptError
```

Blocked: deception, truthfulness, credibility, nervousness, identity, recruitment
suitability, clinical state, demographic inference, and any prompt asking for an investment
action. A test asserts the runner refuses such a prompt *without loading the model*.

The prompts actually used ask only for the visible position of the mouth, eyes, eyebrows
and head.

## What the models reported

| | SmolVLM-256M | SmolVLM-500M |
|---|---:|---:|
| Observations | 80 | 80 |
| Regions described per output | 2.39 | **3.05** |
| Words per output | 19.5 | 25.6 |
| Mean token log-probability | −0.494 | −0.489 |
| **Ungrounded-term rate** | **0.000** | **0.000** |

**Neither model produced a single ungrounded term across 160 descriptions.** No
"nervous", no "dishonest", no "confident". The observational framing held for both. This
is measured rather than enforced — the parser counts such terms rather than filtering
them, because the rate is a property of the model and suppressing it would hide exactly
the behaviour worth knowing about.

### The two models look at different parts of the face

| Region | 256M | 500M |
|---|---:|---:|
| eyes | 0.59 | **1.00** |
| eyebrows | 0.57 | **1.00** |
| mouth | **0.70** | 0.24 |
| head | 0.25 | **0.74** |
| framing | 0.28 | 0.07 |

The larger model describes eyes and eyebrows in *every* output and the mouth in barely a
quarter; the smaller one is the reverse. These are not two grades of the same reading. They
are different readings.

### Cross-model agreement is low (RQ-V4)

On the same 80 frames with the same prompt:

- **Region agreement: 0.5425** — they agree on which regions to describe about half the time
- **Word overlap (Jaccard): 0.2678**

Same architecture family, same image, same instruction, roughly one word in four shared.
An example, on a clip labelled *angry*:

> **256M** — "The person is looking to the right of the image. His mouth is open, and his
> eyes are wide open. His eyebrows are furrowed…"
>
> **500M** — "The person has a **surprised expression**. His eyes are wide open and his
> eyebrows are furrowed. His mouth is open and his lips are parted."

Both descriptions are defensible readings of the pixels. They are not the same reading, and
the second volunteers a categorical label nobody asked for. **A single VLM's description
should not be treated as a measurement**, and this number is what bounds that.

## The negative control is the most important number here (RQ-V2)

Rendered matplotlib figures — confusion matrices, calibration plots — contain **no human
face**. Asked to describe the mouth, eyes, eyebrows and head of "the person in this image",
SmolVLM-256M described facial regions in **4 of 6** of them.

**Face-region hallucination rate: 0.667.**

The contrast with the specialised detector is stark and it is measured on comparable
inputs: **YuNet detects a face in 0 of 3 rendered market charts** and reports NO FACE
DETECTED. The landmark pipeline refuses; the vision-language model confabulates.

This is not a reason to discard the VLM. It is the number that says how its output must be
read: **a VLM description is evidence about the model, not a detection.** Anything built on
it needs an independent detector to establish that there is a face there at all — which is
exactly the arrangement here, where YuNet gates and the VLM describes.

## Rephrasing the same request changes the answer

Twenty frames, two wordings of the *same* observational request — "describe the observable
facial-expression-related features…" against "looking only at what is visible, report the
mouth position, eye openness, eyebrow position and head orientation…":

| | Value |
|---|---:|
| Word overlap (Jaccard) | **0.252** |
| Region overlap (Jaccard) | **0.286** |
| Identical outputs | **0.000** |

Not one of the twenty produced the same text, and the two wordings agree on which regions
to mention barely a quarter of the time. Decoding is greedy, so this is not sampling noise:
it is genuine sensitivity to phrasing. Reported as a property of the method, and the reason
`PROMPT_VERSION` is stored on every observation — a result produced under one wording is not
comparable to one produced under another.

## Stability under pixel corruption (RQ-V2)

Twelve frames, severity 0.25, against each frame's own clean description:

| Corruption | Identical | Word overlap | Regions described | Ungrounded terms |
|---|---:|---:|---:|---:|
| blur | 0.000 | 0.440 | −0.58 | **+0.00** |
| darkness | 0.167 | 0.531 | −0.67 | **+0.00** |
| noise | 0.167 | 0.445 | −1.25 | **+0.00** |
| occlusion | 0.000 | **0.360** | +0.50 | **+0.00** |

Occlusion disturbs the description most and noise costs the most observable content. The
column that matters for safety is the last one: **degrading the image never pushed either
model into speculation.** Corrupted inputs produced fewer or different observations, not
invented psychological ones.

Random corruption only. Nothing here licenses an adversarial claim.

## Temporal behaviour

Ten clips, three timestamped frames each. **90% of clips produce a changing description**
across their frames, with adjacent-frame word overlap of 0.453. A model returning one fixed
sentence per clip would be reading the scene rather than the expression; this one is not,
though the 0.453 overlap should be read alongside the 0.252 paraphrase overlap above — some
of that change is instability rather than signal.

## Does the VLM add anything? (RQ-V1, RQ-V3)

Leave-one-actor-out cross-validation over the 80-clip subset, every fold speaker-disjoint,
8 classes, chance 0.1250:

| Subset | Balanced accuracy |
|---|---:|
| TEXT | 0.0875 |
| VLM | **0.2500** |
| FACE | 0.2625 |
| FACE+VLM | 0.2750 |
| VLM+AUDIO | 0.3125 |
| AUDIO+TEXT | 0.3500 |
| AUDIO | 0.3750 |
| FACE+VLM+AUDIO | 0.4125 |
| FACE+AUDIO | 0.4250 |
| FACE+VLM+AUDIO+TEXT | 0.4250 |
| **FACE+AUDIO+TEXT** | **0.4375** |

Two results worth separating.

**The VLM channel carries real signal.** VLM alone reaches **0.2500 — twice chance, and
statistically indistinguishable from the specialised landmark model's 0.2625** — using
nothing but which regions the description mentioned, its length, its token likelihood and a
20-word bag. The model was never asked about emotion. That a caption produced under a
purely observational prompt supports 2× chance emotion classification is the substantive
finding here.

**It is largely redundant with what the facial model already measures.** Adding VLM to FACE
gains **+0.0125**; adding it to FACE+AUDIO+TEXT costs **−0.0125**. On 80 clips from 4
actors neither is resolvable, so the honest verdict is *no difference this sample can
establish* — not "it helps" and not "it is useless".

Reported as **QUALIFIED** in the claim gate for that reason.

## What this does not support

- **Not a calibrated confidence.** The stored `mean_token_logprob` is the likelihood the
  decoder produced. It is named as such and nothing treats it as a calibrated probability,
  because it is not one.
- **Not architecture diversity.** Two sizes of SmolVLM. Florence-2 is blocked, and no
  conclusion here covers architectures that were not run.
- **Not the whole corpus.** 80 clips, 4 actors, one frame each. Effects smaller than a few
  points are below what this sample resolves, and the subset size is printed beside every
  number for that reason.
- **No identity, ever.** Nothing in this branch computes or stores a representation capable
  of matching one person to another.
