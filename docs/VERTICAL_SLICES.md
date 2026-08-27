# The sixteen vertical slices

Each week of the programme is one statistical module paired with the multimodal module of
the same index, and each pair is reachable end to end: a browser sends a selection, the
Python service validates it, the canonical research implementation runs on the real data,
and a structured response comes back carrying what it computed and how.

This document records what actually runs, what does not, and how each of those was
checked. It is the acceptance record for the interactive layer.

---

## 1. What "end to end" means here

```
browser control  →  /api/aegis/…            (Next.js route handler, allowlisted)
                 →  /api/…                  (Python service, backend/server.py)
                 →  backend/registry.py     (validate against the declared schema)
                 →  backend/service.py      (resolve the module, choose the path)
                 →  scripts/stages/*.py     (the adapter — dispatch only, no science)
                 →  research/**             (the canonical implementation)
                 →  data/panel/*.parquet    (the real data)
                 →  one response contract   (backend/contract.py)
                 →  the run panel           (components/run/)
```

Every arrow is real. Nothing on the page is a constant, nothing is a fixture, and the
frontend contains no computed metric of its own: the numbers a panel renders arrived in
the response it is rendering.

## 2. The two execution modes, and why they are labelled

Every response says which of two things happened, in a badge above the numbers:

| Mode | Badge | What it means |
| --- | --- | --- |
| `LIVE_COMPUTATION` | Live computation | The canonical implementation ran during this request, on the slice that was selected. These numbers did not exist before the request. |
| `VERIFIED_ARTIFACT` | Verified experiment result | A previously executed run is being replayed from its provenance-stamped artifact. Nothing was computed; the run identifier and commit that produced the numbers travel with them. |

`backend/contract.py` refuses to emit a response that confuses them. A `LIVE_COMPUTATION`
carrying a prior run identifier and a `VERIFIED_ARTIFACT` naming no artifact are both
rejected before the response leaves the service, and the rejection is reported as a
backend defect rather than shipped.

Twenty-nine of the thirty-two modules compute live. Three do not, and each says why:

| Module | Why it cannot run on request |
| --- | --- |
| `STATS-13` Baseline comparison | Regenerating it refits every arm and overwrites artifacts the claim ledger cites. No request may do that. |
| `MULTIMODAL-08` Video generation | Rendering and encoding clips takes minutes and writes to the media directory. |
| `MULTIMODAL-16` Explanation benchmark | Needs a fitted model and a fitted surrogate; both take minutes and come from the paper pipeline. |

A protected module is a separate question from a live one. Eight modules regenerate
artifacts the documentation cites, and none of them can be regenerated from a request —
but most can still *analyse* live, because analysing writes nothing. `MULTIMODAL-01` is
the clearest case: its corpus is protected, its live analysis reads that corpus and
returns numbers, and the response says both.

## 3. The weekly acceptance matrix

`STATS` and `MULTIMODAL` columns record the execution mode: **live** means the canonical
code runs on request, **artifact** means a labelled replay. `E2E` is ticked only where the
complete flow — control, request, validation, canonical call, response, render — has
actually been exercised.

| Week | STATS | MULTIMODAL | Backend | UI | E2E |
| ---: | --- | --- | :---: | :---: | :---: |
| 1 | 01 Data and integrity profile — live | 01 Text corpus ingestion — live | ✓ | ✓ | ✓ |
| 2 | 02 Universe and survivorship — live | 02 Text affect extraction — live | ✓ | ✓ | ✓ |
| 3 | 03 Descriptive distributions — live | 03 Text feature block — live | ✓ | ✓ | ✓ |
| 4 | 04 Microstructure proxies — live | 04 Image asset generation — live | ✓ | ✓ | ✓ |
| 5 | 05 Regime statistics — live | 05 Image feature block — live | ✓ | ✓ | ✓ |
| 6 | 06 Dependence and propagation — live | 06 Audio sonification — live | ✓ | ✓ | ✓ |
| 7 | 07 Tail and extreme risk — live | 07 Audio prosody proxies — live | ✓ | ✓ | ✓ |
| 8 | 08 Episode statistics — live | 08 Video generation — artifact | ✓ | ✓ | ✓ |
| 9 | 09 Leakage verification — live | 09 Video feature block — live | ✓ | ✓ | ✓ |
| 10 | 10 Validation metrics — live | 10 Media licensing — live | ✓ | ✓ | ✓ |
| 11 | 11 Calibration — live | 11 Cross-modal alignment — live | ✓ | ✓ | ✓ |
| 12 | 12 Error analysis — live | 12 Dataset assembly — live | ✓ | ✓ | ✓ |
| 13 | 13 Baseline comparison — artifact | 13 Fusion degeneracy proof — live | ✓ | ✓ | ✓ |
| 14 | 14 Ablation study — live | 14 Information decomposition — live | ✓ | ✓ | ✓ |
| 15 | 15 Robustness — live | 15 Modality missingness — live | ✓ | ✓ | ✓ |
| 16 | 16 Multi-seed significance — live | 16 Explanation benchmark — artifact | ✓ | ✓ | ✓ |

Every row was run through `POST /api/weeks/{n}/run` with the declared defaults and
returned `OK` for both halves.

`typical_seconds` in the manifest is measured, not estimated, and the interface shows it
on the button before anyone presses it. Measured on the development machine, with the
declared defaults:

| Runtime | Modules |
| --- | --- |
| under a second | STATS-02, 04, 05, 08, 10, 12, 14; MULTIMODAL-01, 02, 03, 05, 07, 09, 10, 12, 13, 14 |
| one to nine seconds | STATS-01, 03, 06, 07, 09, 11; MULTIMODAL-04, 06 |
| forty to sixty-five seconds | STATS-15, 16; MULTIMODAL-11, 15 |

The four slow ones fit a model or run thousands of permutations during the request. They
are excluded from the default end-to-end run and covered by `AEGIS_E2E_SLOW=1`.

## 4. A week is one feature, not two panels

The weekly page leads with the question the pair answers, one action, the headline
figures, the picture, what was observed and how far it goes. The per-module detail sits
one disclosure below that, and the research view adds the wiring.

What the page leads with is **declared in the manifest**, not decided in a component:

```yaml
  - week: 1
    feature:
      product_question: What is every other number here built on?
      story: >-
        Profiles the rows behind the analysis and reads the text stream that
        accompanies them, so the size and completeness of the evidence base is
        known before anything is concluded from it.
      headline:
        - {module: STATS-01, metric: rows, label: Instrument-sessions}
        - {module: STATS-01, metric: instruments, label: Instruments}
        - {module: MULTIMODAL-01, metric: documents, label: Documents}
        - {module: STATS-01, metric: positive_rate, label: Sessions inside an episode}
      primary_visual:
        module: STATS-01
        series: block_coverage
        label_column: block
        value_column: mean_non_null_fraction
```

That is what makes it checkable. `tests/unit/test_week_features.py` runs all 32 modules
and asserts every declared metric key, series key and column name is one the module
actually returns, with rows to draw — 149 assertions. A declaration that stops matching
its module fails the suite instead of rendering a dash where a number belongs. The
component contains no metric key of its own, and a test asserts that too.

Module pages answer to both names: `/stats/01` for a mentor asking by number,
`/stats/data-integrity` for a reader clicking a capability. Both prerender; neither is a
redirect.

## 5. What each module lets you change

The controls are declared in `research_modules.yaml` under each module's `analysis:`
block, exported to `public/data/weeks.json`, rendered by `components/run/Controls.tsx`,
and validated by `backend/registry.py`. One declaration, so a control that exists is a
control the service accepts.

Interesting parameters, rather than an exhaustive list:

- **STATS-10** — the threshold. The default is the one selected on the training split; set
  it yourself and the response says so, because a threshold chosen by looking at
  evaluation metrics is not a selection procedure and the number stops being evidence
  about unseen data.
- **STATS-11** — the bin count. Expected calibration error is a function of the binning as
  much as of the model, so the control is exposed rather than fixed.
- **STATS-15** — the failure mode and its severity. `stale` is a delayed feed, which is
  far more common in production than noise and invisible to a null check.
- **STATS-16** — which arms to pool. The seed noise floor is the scale every other
  comparison in the project should be read against.
- **MULTIMODAL-04 / 06** — an instrument and a window. The chart is rendered and read back,
  or the prices are sonified and the waveform analysed, during the request.
- **MULTIMODAL-13** — the degeneracy proof's construction. The claim is algebraic, so it
  should survive any parameterisation: turn the regime term up to a hundred and the
  difference stays at machine precision.

## 6. Uploading a document

One module accepts a file: **MULTIMODAL-02** takes a plain-text document and scores it
with the same lexicon extractor the corpus path uses. `POST /api/uploads/text` reads it and
returns the text; the text then travels as an ordinary run parameter and is validated with
everything else. The endpoint itself executes nothing.

Three decisions worth stating:

- **Nothing is written to disk.** The obvious design — save to a temporary directory,
  analyse, delete — has failure modes this one does not: a crash between write and delete
  leaves the file, the temporary path is a filesystem location a bug could widen, and
  "cleaned up" is a property to be maintained rather than one that holds by construction.
  A document small enough to score is small enough to hold in memory.
- **Text only, and the refusal says why.** Accepting an image, an audio clip or a video
  would mean running affect extraction over a real person's face or voice on request,
  which is the inference the affective guards exist to refuse (L-19,
  `research/human_affect/guards.py`). An upload of another kind is rejected by name and
  by content type, with that reason.
- **The scores are not a reading of the author.** The response leads with the lexicon
  match rate, because a dimension named for an emotion is a count of words from a list,
  and a document outside the financial domain the list was built for will match almost
  nothing. The panel says so rather than presenting a confident zero.

Limits: 1 MB per upload, 20,000 characters kept, `.txt`/`.md`/`.csv`/`.text`/`.log`, and
the filename is stripped of anything path-like before it is echoed back.

## 7. Refusals

A refusal is a first-class outcome and is rendered as an explanation, never as an empty
panel or a fabricated zero.

| Status | HTTP | When |
| --- | ---: | --- |
| `INVALID_INPUT` | 400 | A value failed its declared bounds, or a parameter was not declared at all. Misspelling a parameter is refused rather than silently defaulted. |
| `INSUFFICIENT_DATA` | 422 | The selection was valid but left too little data. A slice with eleven rows does not produce a small result; it produces a meaningless one. |
| `INPUTS_MISSING` | 409 | A required file is not on disk. Distinct from the above: here the request was reasonable and the pipeline has not run. |
| `PROTECTED` | 200 | The module regenerates cited artifacts. The verified result is served; regeneration needs a deliberate terminal command. |
| `NOT_YET_EXECUTED` | 501 | The module's contract exists and its science does not. |
| `UNKNOWN_MODULE` / `UNKNOWN_WEEK` | 404 | No such identifier. |
| `BACKEND_UNAVAILABLE` | 200 | No Python service is reachable — see §9. |

Every refusal carries a `reason` and a `remedy`. An error with no remedy is a dead end.

## 8. What cannot be reached from a request

- **A shell.** Inputs arrive as validated primitives in a dict. `backend/server.py` builds
  no command line and `backend/service.py` never constructs one. The single subprocess in
  the whole surface is `STATS-09`, which runs the leakage suite with a fixed argument list
  containing no value from the request.
- **The filesystem.** Artifact paths are repository-relative everywhere, and
  `Response.check` refuses any response containing an absolute path. Reads are confined to
  an allowlist of four directories and to `.json` files.
- **`--force`.** It is not a parameter of any module, no route accepts it, and a test
  asserts that no declared input is named anything like it. A protected artifact cannot be
  regenerated over the network, and the end-to-end suite checks the artifacts are byte
  identical after a protected module is run through the API.
- **Another origin's browser tab.** The service answers browser requests only from
  configured origins; `AEGIS_ALLOWED_ORIGINS` defaults to localhost.

Secrets, environment variables, interpreter paths and internal hostnames never appear in a
response. `AEGIS_BACKEND_URL` may carry a host, a port and a token; the browser learns
only whether the backend was `reachable` or `unavailable`.

## 9. Running it, and the deployment boundary

Locally:

```
weeks\week_1\run.bat            one week: backend, interface, and its page
weeks\week_1\run.bat research   the same page, opened in research view

run_dev.bat                      both services, no particular week
run_dev.bat backend              python -m backend.server   (127.0.0.1:8787)
run_dev.bat frontend             npm run dev                (localhost:3000)
```

`weeks/week_1 .. weeks/week_16` are generated from the manifest's `weeks:` block by
`python scripts/validate_structure.py --write`, the same way `STATS/` and `MULTIMODAL/`
are generated from `modules:`. Each folder holds the launcher, a `README.md` naming the
week's two modules and every parameter they accept, and `week.json` — the registry entry
the backend derives, so the folder cannot describe a route or an artifact the modules do
not have. Editing one by hand is reported as drift.

There is no per-week copy of the interface. The page is one Next.js route,
`app/weeks/[week]/page.tsx`; sixteen copies of it would be sixteen things to keep in
agreement, and both experiences already live in that single page.

The Next.js app proxies to whatever `AEGIS_BACKEND_URL` names. Set
`AEGIS_BACKEND_TOKEN` on both sides if the service is reachable from anywhere but the
machine it runs on.

**Vercel has no long-lived Python process**, and this project does not pretend otherwise.
A deployment without a reachable backend still serves every page: the controls render, the
research evidence renders, and a run request returns the module's stored,
provenance-stamped result labelled `VERIFIED_ARTIFACT` alongside a `BACKEND_UNAVAILABLE`
notice saying that the inputs on the form were **not** applied and nothing was computed.
The response echoes empty inputs, so there is no way to read it as a live answer.

To get live computation in a deployment, run the Python service somewhere that supports a
persistent process and point `AEGIS_BACKEND_URL` at it. What must never happen is the
third option: presenting a stored result under a live label because the deployment target
made the real thing inconvenient.

## 10. How this is checked

| Check | What it holds |
| --- | --- |
| `tests/integration/test_backend_e2e.py` | Starts the real server on an ephemeral port and drives it over the socket. Two different slices must return different numbers; a replay must never wear a live label; a protected artifact must be byte identical after an API run; every refusal must carry a remedy; no response may contain an absolute path. |
| `tests/unit/test_backend_contract.py` | Every declared input is one the adapter accepts, bounded, and renderable. Every artifact-only module states a reason. `force` is not a parameter anywhere. Defaults validate. |
| `tests/unit/test_exported_bundles.py` | No bundle served to a browser contains an absolute path or a location outside the repository. |
| `tests/unit/test_non_advisory.py` | No advisory language anywhere in the app surface. |
| `scripts/validate_structure.py` | The manifest, the directory tree, the runners and the adapters still agree. |
| `tests/unit/test_capability_gate.py` | The cumulative week gate at all sixteen active weeks, and — against a live server — that no gated week or module can be read or run over the API. See [`CAPABILITY_GATE.md`](CAPABILITY_GATE.md). |
| `scripts/audit_weekly_capability.py` | All sixteen slices, traced from the manifest declaration through the adapter to the canonical implementation and back: declared headlines exist, declared chart columns exist and carry rows, provenance names what ran, no backend figure appears as a literal in the frontend, and each week's launcher actually starts. Writes `research_artifacts/weekly_capability_audit.{json,csv}`. |
| `tools/browser/check_interactive.mjs` | Opens a real Chrome, presses the real buttons, and matches the figures on screen against the bytes of the HTTP response the browser received. |
| `tests/unit/test_boot_script.py` | The inline first-paint script parses as JavaScript once the template literal has been evaluated. |

Run the slow half — the three modules that fit a model during the request — with
`AEGIS_E2E_SLOW=1 python -m pytest tests/integration/test_backend_e2e.py`.

### Clicking the buttons

Everything above verifies the request behind a button. It does not verify that pressing the
button causes that request, because none of it renders a page — and that gap is where the
ordinary frontend failures live: a handler on the wrong element, a control that stays
disabled, a component that throws while hydrating, a result that arrives and is never drawn.

    npm run check:browser              headless, starts its own backend and interface
    npm run check:browser -- --headful watch it happen

It starts the analysis backend and the interface on ephemeral ports, drives Chrome over the
DevTools protocol, and clicks. It builds into `.next-check/` rather than `.next`, because a
dev server and a production build that share one output directory leave the two
interleaved — and what surfaces then is `__webpack_modules__[moduleId] is not a
function` out of `_document.js`, or a route that answers 404 because the manifest on
disk belongs to the other build. Neither is an application fault, and both cost an hour
to diagnose. `AEGIS_DIST_DIR` in `next.config.mjs` is what keeps them apart.

Clicks go through `Input.dispatchMouseEvent` at the element's real coordinates rather
than `element.click()`, so a button that is covered, zero-sized or disabled fails
instead of passing. Nothing is installed for it: Chrome is already present
and Node has had a WebSocket client built in since v22.

It found one thing that every other check missed. The inline boot script in
`app/layout.tsx` was written in a plain template literal, which ate the backslash in `\/`
and shipped `/^/(stats|...)(/|$)/` to the browser. That is a syntax error, raised while the
script is parsed — before the `try` around it exists — so the whole function silently never
ran, and the mode and theme it exists to set before the first paint were never set. Three
`SyntaxError`s on every page load, and no visible symptom beyond a flash.
