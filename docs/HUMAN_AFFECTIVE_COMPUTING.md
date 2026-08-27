# Human-media affective computing (Stream B)

Regenerate with `python scripts/run_trust.py` and the `HUMAN_AFFECT/*/run.bat` modules.

## The correction this implements

An earlier report marked facial affect **NOT APPLICABLE** because the repository contained
no human video. That conflated two different claims: *the current data has no faces* is a
data gap, whereas *facial affect is not applicable* removes a requirement. The right
statement separates four axes:

| | capability | implementation | dataset | validation |
|---|---|---|---|---|
| Human facial expression | SUPPORTED | PARTIAL | PENDING | NOT YET EXECUTED |

That tells a reader what exists, what is missing and what would fix it. "NOT APPLICABLE"
told them to stop asking.

## Two streams, never conflated

```
STREAM A — market-derived            STREAM B — human media
market data, rendered charts,        real human speech, real human video,
market sonification, generated       transcripts of what a person said
financial text
        │                                     │
research/{market,image,audio,        research/human_affect/
          video,text}                          │
        │                                     │
        └──────────► research-level cross-modal analysis ◄──────┘
                     (only where scientifically justified)
```

Stream A is **unchanged**. Stream B is additive.

### The separation is enforced, not documented

Two layers, because either alone is insufficient:

- **Structural** — every asset declares a `MediaKind` at ingestion and the gate rejects on
  that declaration. Always active, needs no model, works with nothing installed.
- **Content** — where a signal test exists, the gate also verifies the content matches the
  declaration, so a *mislabelled* asset is caught rather than trusted.

`HUMAN_AFFECT-02` executes all of it against this repository's own `sonify()` output, not
a mock. Current result: **9 of 9 checks hold.**

| Check | Result |
|---|---|
| Declared sonification → speech pipeline | REFUSED (structural) |
| Sonification **mislabelled as human speech** → speech pipeline | REFUSED (content) |
| Declared chart image → face pipeline | REFUSED (structural) |
| Declared chart video → face pipeline | REFUSED (structural) |
| Deception / hiring / clinical / identity requests | REFUSED (4/4) |
| Labelled development fixture | ACCEPTED — the gate is not a blanket refusal |

The content gate rejects in **both** directions: tone-like signals (the sonifier produces
sine tones with harmonics, verified against `research/audio/sonify.py`) and signals with
essentially no voicing. The second rule was added because the first version passed a noise
burst, which the tone test alone could not catch.

## What is implemented and executing

| Component | State |
|---|---|
| Dataset registry with licence gate | implemented, executes |
| Audio quality (level, clipping, silence, coarse SNR, DC) | implemented, executes |
| Frame quality (resolution, exposure, contrast, Laplacian focus) | implemented, executes |
| Voice activity detection (adaptive energy + ZCR) | implemented, executes |
| 22 prosodic and spectral descriptors | implemented, executes |
| Dimensional affect with uncertainty | implemented, executes |
| Timestamped segmentation | implemented, executes |
| Frame sampling from video | implemented, executes |
| Expression descriptors within a face region | implemented, executes |
| Temporal dynamics (onset, peak, range, volatility) | implemented, executes |
| Provenance and privacy controls | implemented, executes |
| **Face detection** | **BLOCKED — no backend installed** |
| **ASR / transcription** | **BLOCKED — no local backend** |
| **Categorical emotion** | **BLOCKED — no annotated corpus** |

### The DSP is validated by construction

The synthetic fixture is built with a known pitch (~130 Hz), a known pause interval and a
known syllable rate. The extractor recovers **F0 median 128 Hz** and **4 pauses**, which is
what makes it a working implementation rather than code that runs.

## What is blocked, and by what exactly

| Blocker | Consequence | Remedy |
|---|---|---|
| No licence-verified human corpus | Every pipeline runs only on labelled fixtures | Verify a registered dataset's licence locally, download it, record checksums |
| No face-detection backend | Detection reports BLOCKED; everything around it runs | `pip install opencv-python` or `mediapipe` |
| No local ASR | No transcript, so no human text affect | Install a local model (faster-whisper, whisper.cpp) |
| **No licence-clear affect-annotated financial audiovisual corpus** | Domain shift cannot be measured at all | Open problem — registered explicitly as `FINANCIAL_INTERVIEW_CORPUS` |

**There is deliberately no fallback face detector.** A skin-tone or edge heuristic returns
plausible rectangles on a photograph *and* on a candlestick chart. Reporting BLOCKED is the
honest outcome; a heuristic would be the dishonest one.

## Dataset registry

Four entries: RAVDESS, CREMA-D, TESS (general) and `FINANCIAL_INTERVIEW_CORPUS` (the gap).

**Every entry is `licence_verified: False`.** The licence text was not read in the
environment that wrote the registry, and recording an unread licence as fact would be
fabrication. `assert_usable()` refuses any unverified dataset, so the honest default is
also the safe one. Verification is a deliberate local act requiring a written note.

No media is downloaded automatically and none is committed. Copyrighted broadcast footage
is never downloaded or redistributed; where only reference is permitted, metadata and a URL
are stored instead.

## Synthetic fixtures

Used **only** as clearly-labelled development conditions, so the code paths execute and the
blocker stays visible instead of the module writing nothing. Every artifact produced from
one carries:

> SYNTHETIC DEVELOPMENT FIXTURE: pipeline test only. This is not real human speech and no
> research claim may rest on it.

No synthetic face or voice is ever presented as real.

## Prohibited inferences

Refused by `assert_no_forbidden_inference`, matched through 27 trigger phrases rather than
one canonical word each — the first version keyed only on "recruitment" and let "candidate
ranking for hiring" straight through.

| Refused | Why |
|---|---|
| Deception / truthfulness / credibility | Observable affect cannot establish any of them |
| Identity, face matching, speaker recognition | Expression analysis is not identity analysis |
| Candidate ranking, hiring, interview scoring | Scope is financial-media research |
| Clinical or mental-health inference | Clinical determinations, not affective measurements |

A test walks the AST of `face.py` to confirm no identity-related symbol exists: face
matching is **absent**, not disabled.

## Privacy

Derived features are the output. Raw media is referenced by path and SHA-256 and never
copied into repository outputs, so nothing under `outputs/` contains a waveform or a frame.
No identity representation is computed anywhere. Provenance records state explicitly that
`raw_media_copied` and `identity_representation_computed` are both false.

## Research questions this opens

| ID | Question | Status |
|---|---|---|
| RQ-A1 | Do human speech and facial signals add information beyond financial text and market data? | NOT YET EXECUTED |
| RQ-A2 | How does temporal alignment affect multimodal affective extraction from interviews? | NOT YET EXECUTED |
| RQ-A3 | How robust are affective signals under missing or corrupted audio/video? | NOT YET EXECUTED |
| RQ-A4 | Do general-domain affective models transfer to financial media? | BLOCKED — no financial corpus |
| RQ-A5 | Does multimodal affective fusion improve calibration over unimodal? | NOT YET EXECUTED |
| RQ-A6 | How stable and faithful are explanations of multimodal affective signals? | PARTIAL (Stream A only, and its stability check fails) |

## Honest verdict

The architecture supports human multimodal affective research. The implementation is real
for speech and partial for face. **Nothing has been validated against human ground truth,
because no licence-verified human corpus is present.** Until that changes, no claim about
human affect in financial media is supportable from this repository, and the pipeline says
so at every output rather than filling the gap with a fixture and hoping nobody checks.
