# Affective computing: Stream A (market-derived)

> **Superseded in part.** This document describes **Stream A only** — the affective
> feature pipeline over market-derived signals and generated text. Its earlier conclusion
> that facial affect is "NOT APPLICABLE" was wrong: that was a data gap, not the removal
> of a requirement. Human-media affective computing is now an implemented capability
> described in **[HUMAN_AFFECTIVE_COMPUTING.md](HUMAN_AFFECTIVE_COMPUTING.md)**, and
> capability status is reported on four axes rather than one.

## What Stream A actually does

Regenerate with `python scripts/run_trust.py`; the machine-readable form is
`outputs/trust/affective_audit.json`.

## The headline, stated plainly

**AEGIS-Market operates an affective *feature* pipeline over market-derived signals and
generated text. It is not a human-affect system.** Nothing it processes contains a human
voice, a human face, or a human-annotated affective label.

That distinction is the whole point of this document, because the module names invite
exactly the wrong reading:

| What the name suggests | What is actually implemented |
|---|---|
| speech emotion recognition | prosodic descriptors of a **sonification** of price and volume. No speech, no speaker, no voice. |
| facial expression analysis | eight low-level visual statistics of a **rendered chart**. There is no face in any frame. |
| video affect | temporal deltas of those same chart statistics. |
| text affect | a lexicon over a **generated** corpus, so the affect is a property of the generator, not of a writer. |

Within Stream A there is no face to analyse, and building an action-unit extractor for
chart images would produce numbers with no referent — which is why the facial pipeline
**refuses chart input outright** rather than processing it. Facial affect as a *capability*
is SUPPORTED and implemented in Stream B; what is absent here is a face in this stream's
data, which is a different statement.

## Checklist verdict

**NOT A COMPLETE AFFECTIVE COMPUTING PIPELINE: 7 of 21 items unmet.**

| Status | Count |
|---|---:|
| SUPPORTED | 9 |
| PARTIAL | 5 |
| BLOCKED | 3 |
| NOT MEASURED | 2 |
| NOT RUN | 2 |

The four items that matter most, and why they are not satisfied:

- **Validated representation — BLOCKED.** Dimensional (valence, arousal) and categorical
  (six emotions) representations are both implemented, and neither has been validated
  against anything, because no human-annotated affective labels exist in the project. This
  is the single largest gap and it is a data limitation, not an engineering one.
- **Label quality — BLOCKED.** There are no annotators, so there is no inter-rater
  agreement to compute and no label noise to characterise.
- **Domain shift — BLOCKED.** No general-domain affective dataset is present and no
  financial-domain labelled affective dataset was obtainable, so there are no two domains
  between which to measure a shift.
- **Signal-quality assessment — NOT MEASURED.** Coverage flags record *presence*, and
  presence is not quality. For sonified audio and rendered charts, SNR and frame quality
  would be properties of the renderer rather than of a recording, so the measure needs
  redefining before it would mean anything.

What *is* satisfied: preprocessing, temporal modelling, context modelling, cross-modal
alignment, fusion strategy comparison, disagreement preservation, provenance, privacy and
reproducibility.

## Prohibited capabilities

None of these is implemented, and a test scans the source tree to keep it that way.

| Capability | Why it is refused |
|---|---|
| Deception detection | Observable affective signals do not license an inference about truthfulness. A system that scored credibility from prosody would be wrong in a way that harms the person scored. |
| Psychological diagnosis | Mental-health states are clinical determinations. No feature here is diagnostic of anything. |
| Candidate or recruitment scoring | Scoped to financial-media research. Employment decisions carry legal and ethical obligations this project does not meet. |
| Speaker identification | Expression analysis is not identity analysis. No identity embedding, face matching or speaker recognition exists. |

## Terminology discipline

The left column asserts an internal state from an external signal. The right column
describes what was measured.

| Never | Instead |
|---|---|
| the speaker is anxious | elevated acoustic arousal-related feature |
| the person is nervous | estimated arousal proxy above its baseline |
| the speaker is lying | NOT INFERABLE |
| detected emotion | model-estimated affective dimension |
| sentiment proves X | affective signal is statistically associated with X |

The pipeline keeps observation, model estimate and interpretation as separate stages, and
the system never concludes that an affective signal proves anything about market integrity.
The answerable form is: *is this affective signal statistically associated with the
research-defined event under the evaluated conditions?*

## Open research questions

| ID | Question | Status |
|---|---|---|
| RQ-AFF-1 | Do lexicon-derived affective dimensions over generated text carry information beyond market features? | PARTIAL — text-only AUPRC 0.806 against a 0.244 positive rate, but the corpus is generated alongside the episodes, so some association is built in |
| RQ-AFF-2 | Would acoustic affect proxies over real speech behave like those over sonified data? | BLOCKED — the two share a feature extractor and nothing else |
| RQ-AFF-3 | Does cross-modal affective disagreement carry information the individual scores do not? | NOT SUPPORTED — +0.496 unconditionally collapses to −0.005 once risk is held fixed (N-07) |
| RQ-AFF-4 | How stable are multimodal affective explanations across seeds, regimes and modalities? | PARTIAL — 0.780 sign consistency across seeds, below the 0.800 threshold (N-01); regimes and modalities unmeasured |
| RQ-AFF-5 | Do affective feature distributions and model performance differ across instruments, sectors and regimes? | NOT MEASURED — runnable now; it is the fairness harness |

## What would change the verdict

Licence-clear financial speech or interview media, with the data governance that personal
data requires, plus human affective annotations with more than one annotator. Until then
the honest description is the one at the top of this page, and calling the component
"multimodal affective AI" would be the overclaim the field is full of.
