# The capability gate

The repository contains the complete system: sixteen weekly capabilities, thirty-two
STATS and MULTIMODAL modules, the product experience, the research experience, the NIFTY 50
index layer, evidence alignment, Scenario Lab, the XAI and affective work, and the corpus.
All of it is implemented, tested and runnable.

What a given *run* of the product exposes is a cumulative slice of that, chosen by one
number.

```
AEGIS_ACTIVE_WEEK=1     weeks 1        exposed, weeks 2-16 gated
AEGIS_ACTIVE_WEEK=5     weeks 1-5      exposed, weeks 6-16 gated
AEGIS_ACTIVE_WEEK=16    weeks 1-16     exposed          (the default)
```

Week 1 is not a smaller codebase. It is the first enabled state of the whole one.

## Why this shape

Building week 1, demonstrating it, then rebuilding the architecture for week 2 produces
sixteen projects and one of them is finished. Building everything and switching on a prefix
produces one project that can be demonstrated sixteen times. The second is what a mentor
demonstration actually needs, and it is the only one where week 1's architecture is the
same architecture week 16 ships on.

The cost of that choice is a hard requirement: a gated week must be genuinely unreachable.
Week 8 exists on disk, its artifacts are in the repository and its adapter imports cleanly.
If the gate were cosmetic, a demonstration of week 1 would be one address-bar edit away
from showing week 8. So the gate is enforced in three independent places and demonstrated
in the fourth.

## Where it is enforced

| Layer | File | What it stops |
| --- | --- | --- |
| Backend | `backend/capability.py` | Any API request for a gated week or module, however it arrives. This is the authority; the rest could be deleted and nothing would leak. |
| Proxy | `app/api/aegis/[...path]/route.ts` | The same request in a deployment with no Python process — which would otherwise be answered out of the stored artifacts. |
| Route | `middleware.ts` | A gated page rendering at all. Runs per request, before the page. |
| Interface | `lib/gate.ts` | Nothing. It decides what to *show*; it is not a control. |

The split matters. `lib/gate.ts` and the `aegis_active_week` cookie exist so navigation and
progress marks can be right without every page becoming server-rendered. Raising the cookie
by hand changes a label and changes nothing else: the middleware reads the environment, and
the backend reads its own.

## The single source of truth

`research_modules.yaml` already pairs the weeks. Each now declares where it unlocks, next
to the modules it unlocks:

```yaml
  - week: 8
    stats_module: STATS-08
    multimodal_module: MULTIMODAL-08
    gate:
      capability: detection
      enabled_from_week: 8
```

`enabled_from_week` is written out rather than assumed equal to `week`, so the unlock order
is a declaration that can be read and changed rather than an arithmetic accident. Everything
else — which routes are gated, what navigation offers, which progress marks are filled, what
the API authorises — is computed from `enabled_from_week <= active_week`. Nothing keeps a
second list.

## Three states, and why the middle one needs a name

```
ENABLED      enabled_from_week <= active_week
LOCKED       the capability exists and works; this demonstration starts earlier
UNAVAILABLE  there is no such capability
```

The gate decides what a run *exposes*. It says nothing about what exists, and the interface
has to keep those apart, because every one of these would be false about a locked week:

> Feature not implemented · Development has not started · Backend unavailable · Not found

A locked capability stays in the navigation with a lock, and says **Coming soon · available
from week N** when a reader reaches for it. It does not navigate, it issues no request, and
no part of its result is on the page. Research mode adds the sentence a reviewer needs —
that the work is implemented in the complete system and the week is a demonstration
setting.

`UNAVAILABLE` is the state that keeps that honest. `/weeks/99` is a 404 and the API answers
`UNKNOWN_WEEK`, because telling someone that a week the programme does not have is "coming
soon" promises something no launcher can deliver.

The capabilities themselves are declared in `research_modules.yaml` under
`product_capabilities:`, named for what a reader does rather than for the week that built
them, and exported to `public/data/capabilities.json`. The navigation is generated from
that bundle; a test fails if a component names a capability or fixes a week number in
place.

## Product capability unlock rationale

`enabled_from_week` means **the first capstone week in which the complete product
capability is intentionally exposed to a reader**.

It does not mean the first week in which some underlying code related to the capability
exists. Almost every capability has code present from week 1 — the repository is complete —
so "when does the code exist" would answer 1 for all ten and say nothing. `MULTIMODAL-01`
already imports `research/detection/episodes.py`, and that does not make event detection a
week 1 capability.

The rule applied below: **a capability unlocks in the week whose modules first deliver the
thing the capability is named for.** Where a capability spans several weeks, it unlocks at
the first week a reader can actually use it, not the week it is finally complete.

### The verified mapping

| Capability | Enabled week | STATS | MULTIMODAL | Evidence |
| --- | --- | --- | --- | --- |
| Market overview | 1 | — | — | Reads `lib/product` and the index layer. No weekly module; market context is available from week 1 by design. |
| NIFTY 50 | 1 | — | — | `research/data/nse_index.py`. Explicitly never gated: a week 1 demonstration that cannot show the benchmark is a fragment. |
| Instruments | 1 | — | — | `/markets` reads the product read models, not `STATS-02`. Week 2 *characterises* the universe statistically; the instrument list does not depend on it. |
| Evidence explorer | 1 | — | — | `research/data/alignment.py`, ungated market context. Week 1's own result already carries the three evidence marks. |
| Scenario Lab | 1 | — | — | Backed by the `SCENARIO` modules, which are outside the sixteen-week pairing. |
| **Multimodal evidence** | **5** | STATS-05 Regime statistics | MULTIMODAL-05 Image feature block | A modality becomes evidence when its feature block enters the dataset: `TEXT_BLOCK` at 3, `IMAGE_BLOCK` at 5, `AUDIO_BLOCK` at 7, `VIDEO_BLOCK` at 9. Week 5 is the first week two modalities are readable on one instrument-day. |
| Event detection | 8 | STATS-08 Episode and event statistics | MULTIMODAL-08 Video generation | `research/detection/episodes.py::GeneratorConfig`, `state.py::windows_from_frame`. Week 8 is where episodes become counts, durations, intensities and a per-instrument distribution. The week's own question is "What unusual periods are in this data?" |
| Calibration | 11 | STATS-11 Calibration and uncertainty | MULTIMODAL-11 Cross-modal temporal alignment | Reliability curve, expected calibration error, Brier score and the selective-risk curve. The week's question is "How confident should the signal be taken to be?" |
| Robustness | 15 | STATS-15 Robustness and generalization | MULTIMODAL-15 Modality missingness | Performance under noise, corruption, induced missingness and reduced training data; degradation as modalities are withheld. The week's question is "What happens when the data gets worse?" |
| Explainability | 16 | STATS-16 Multi-seed and significance | MULTIMODAL-16 Multimodal explanation and XAI benchmark | `research/xai/{methods,benchmark,sanity}.py`. The only weekly module that reaches `research/xai/` — which is also why the capability audit records XAI as NOT_APPLICABLE for the other fifteen weeks. |

#### Two different things sit behind Audio evidence

They are gated together and must never be described together.

* **MULTIMODAL-07 audio prosody** computes prosodic descriptors over a *sonification of a
  price series*. There is no speech and no speaker. It is a feature block in the
  multimodal dataset.
* **AUDIO_MODEL_V1** classifies *human speech* against the RAVDESS annotation — the
  emotion an actor was directed to portray.

The week is unchanged at 7 because the capability's meaning has not changed: week 7 is
where audio becomes readable evidence. What the trained model adds is a workflow behind
that same gate, not a new capability, so no entry in `research_modules.yaml` moved.

Running the sonified market audio through the speech model, or describing its output as
human affect, is prohibited. `tests/unit/test_audio_model.py` enforces the separation
structurally: the audio model package must not import the sonifier, and the surface must
offer nothing the sonifier produced.

### The analysis sections

`/analysis` is a permanent product destination and is never gated. Its sections are,
because each is built from a module that arrives at a particular week. A section reads its
data only when its capability is enabled, so a locked result is never loaded, never
rendered and never serialised into the page.

| Capability | Enabled week | STATS | MULTIMODAL | Evidence |
| --- | --- | --- | --- | --- |
| Foundation analysis | 1 | — | — | Reads the market overview product read model, the same source the home page uses. No weekly module. |
| Text evidence | 3 | — | MULTIMODAL-03 Text feature block | `research/data/dataset.py::TEXT_BLOCK`. |
| Image evidence | 5 | — | MULTIMODAL-05 Image feature block | `research/image/pipeline.py`, `IMAGE_BLOCK`. |
| Audio evidence | 7 | — | MULTIMODAL-07 Audio prosody | `research/audio/pipeline.py`, `AUDIO_BLOCK`. Also gates the speech workflow backed by `AUDIO_MODEL_V1` (`backend/audio_analysis.py`, `research/models/audio/`) — see the note below. |
| Event analysis | 8 | STATS-08 Episode and event statistics | — | `windows.json` is written by `research.detection.state::windows_from_frame`, STATS-08's own canonical. |
| Video evidence | 9 | — | MULTIMODAL-09 Video feature block | `research/video/pipeline.py`, `VIDEO_BLOCK`. |
| Evidence contribution analysis | 14 | — | MULTIMODAL-14 Modality information decomposition | `modality_info.json` is written from `research/evaluation/information.py::decomposition`. This is the section that leaked. |

### What the audit changed

Four of the five inferred mappings were supported by the repository and were kept. One was
not.

**Multimodal evidence moved from week 3 to week 5.** Week 3 is `MULTIMODAL-03 Text feature
block` — text, and only text. The product already has text evidence from week 1, when
`MULTIMODAL-01` ingests the corpus, so week 3 adds no modality a reader did not have. The
modality pipeline is the same shape four times over:

```
text    01 corpus ingestion  → 02 affect extraction → 03 TEXT_BLOCK
image   04 chart generation                         → 05 IMAGE_BLOCK
audio   06 sonification                             → 07 AUDIO_BLOCK
video   08 video generation                         → 09 VIDEO_BLOCK
```

If text counts as evidence at its block (3), then image counts as evidence at its block
(5), and week 5 is the first week the word *multimodal* is true of what a reader can see.
Week 3 was an inference from "the first feature block after the panel", which is a fact
about the construction order rather than about the capability.

Two readings were considered and rejected. Week 4 — where the chart images are generated —
gives a second modality as *assets* but not as evidence entering the model, and would make
image evidence arrive one step earlier in its pipeline than text evidence did in its own.
Week 12 — `MULTIMODAL-12 Multimodal dataset assembly`, where all eight blocks become the
99-feature dataset — is where the capability is *complete*, not where it becomes usable;
unlocking there would withhold seven weeks of readable image, audio and video evidence.

No capability was invented to fill a week, and none was moved to balance the progression.
Weeks 2, 3, 4, 6, 7, 9, 10, 12, 13 and 14 unlock no product capability of their own. Their
weekly features remain reachable as weekly features — the capability list is a second view
of the programme, not a replacement for it.

## What is never gated

The market context. NIFTY 50, evidence alignment, the instrument and index pages, the
product read models, Scenario Lab, and the affective and corpus modules are available from
week 1 onward.

This is deliberate rather than an oversight. A week 1 demonstration that could not show the
index it reads everything against would be a fragment, not a product — and the brief is
explicit that the verified NIFTY 50 implementation is not to be gated away. Modules outside
the `STATS`/`MULTIMODAL` pairing return `None` from `required_week_for_module` and are never
asked about again.

## What a gated request looks like

Nothing is stubbed, hidden or deleted, so a gated capability answers rather than vanishing.

```json
{
  "status": "FEATURE_NOT_ENABLED",
  "active_week": 1,
  "required_week": 8,
  "error": {
    "code": "FEATURE_NOT_ENABLED",
    "reason": "Week 8 is not enabled in this demonstration build. Week 1 is available; weeks 2 to 16 are not.",
    "remedy": "Set AEGIS_ACTIVE_WEEK=8 — locally, weeks\\week_8\\run.bat does that for you."
  }
}
```

HTTP 403, not 404: the route exists and the capability is real. A reader who reaches
`/weeks/8` in a browser gets the same statement as a page, at the address they typed —
rewritten rather than redirected, so the question they asked is still visible.

`FEATURE_NOT_ENABLED` joins the existing refusal vocabulary in `backend/__init__.py`. It is
a refusal, not a failure: nothing is missing, nothing broke, and nothing is protected.

## Running a week

The canonical launcher is per week, next to that week's README and its exported payload.

```
weeks\week_1\run.bat              week 1, product view
weeks\week_1\run.bat research     the same page, research view
run_week_01.bat                   a wrapper at the repository root, same thing
```

Each sets its own `AEGIS_ACTIVE_WEEK`, starts the backend with it, starts the interface, and
opens `/weeks/N`. Both experiences are that one page; the masthead toggle switches between
them, and the `research` argument opens it already switched. There is no second application
and no `/weeks/1/research` route.

The root wrappers carry no logic — they call the launcher and pass their arguments through,
so there is nothing in them that can disagree with it.

## Research execution is not product exposure

These are different things and the gate touches only one of them.

```
run_all_research.bat              the full research pipeline
STATS\run_all_stats.bat           every STATS module
MULTIMODAL\run_all_multimodal.bat every MULTIMODAL module
python -m pytest                  the whole suite, over the whole repository
python scripts/validate_structure.py
```

None of these read `AEGIS_ACTIVE_WEEK`, and a test asserts they do not. The gate defaults to
the complete system precisely so that ordinary work never has to opt out of it: a
demonstration opts *into* a smaller surface.

## Deployment

`AEGIS_ACTIVE_WEEK` is an environment variable, and the BAT files are local convenience.
Vercel depends on neither.

The middleware reads the variable per request, so moving a deployment from week 1 to week 2
is an environment change rather than a code change — the pages themselves are unchanged and
stay statically prerendered. `/weeks/1?mode=research` reaches the same state as
`weeks\week_1\run.bat research`.

## How it is checked

| Check | What it holds |
| --- | --- |
| `tests/unit/test_capability_gate.py` | The exact enabled set at every one of the sixteen active weeks. Then, against a live server started with `AEGIS_ACTIVE_WEEK=1`, that every future week and every future module is refused over the API — read and run, both halves — with no metric, series or observation anywhere in the refusal. |
| `npm run check:browser` | The same gate through a real browser: a gated page renders no feature, a gated module page has no runner, `fetch` from the page to a gated endpoint returns 403, and week 1 still computes. |
| `scripts/validate_structure.py` | Every launcher and wrapper still matches the manifest. |

The browser suite runs as a week-1 demonstration by default, so the feature and the gate are
verified against one process rather than two configurations that could drift apart. It then
restarts with every week enabled and drives weeks 1, 4, 8, 12 and 16 end to end, and restarts
again at week 8 to check the line falls between 8 and 9 in the routes and in the API alike.

## The gate is not the same claim as the slice

That a week can be *exposed* says nothing about whether it works. The two are checked
separately, and the second is the harder one:
[`scripts/audit_weekly_capability.py`](../scripts/audit_weekly_capability.py) runs every
week and traces it from the manifest declaration through the adapter into the canonical
research code and back out. Its verdicts are in
`research_artifacts/weekly_capability_audit.json` and `.csv`.
