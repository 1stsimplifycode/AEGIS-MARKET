# AEGIS-Market

**Adaptive Evidence-Gated Integrity System for Rare-Event Market Risk**

A multimodal market-integrity risk intelligence platform and reproducible research
framework for NSE large-cap equities.

> AEGIS-Market provides research-oriented market-integrity risk analysis and does not
> provide financial advice or recommendations to buy, sell, or hold securities.

That sentence is enforced by a test, not by convention — see [`docs/NON_ADVISORY.md`](docs/NON_ADVISORY.md).

---

## What this is

Two tracks over one set of contracts:

**Product** — a Next.js dashboard that answers, for an instrument and a date: when did
integrity risk emerge, what evidence supported it, what did each modality show, did they
agree, when did the risk window peak, has it resolved, what did the explanation attribute
the decision to, and how uncertain is any of it.

**Research** — a pipeline that turns the same machinery into experiments: 32 ablation arms,
cluster-bootstrap intervals, permutation and paired tests with FDR control, an XAI
faithfulness and sanity benchmark, a temporal-window evaluation, a capital-consequence
study, and a `paper_package/` regenerable by one command.

**Scenario Lab** — the same fitted models put under stated conditions: what the system
would have reported on sessions that really were volatile or thin, what it would have
reported had a channel shifted or gone offline, and how a different declared exposure rule
would have changed the simulated tail. Every condition states its baseline, its assumption
and whether its rows occurred or were altered.

The whole is an explainable, uncertainty-aware multimodal financial risk-intelligence and
scenario-analysis platform, evaluated primarily on NIFTY-50 and related Indian financial
data. The pipeline is `observe → detect → explain → quantify uncertainty → simulate →
compare`, and it stops there.

## What this is not

Not financial advice, portfolio management, stock selection, price prediction, trading
automation, or brokerage. Not an AI stock picker. Not a claim to detect real-world
manipulation — see L-04 below.

It also performs no action. No order is placed, no payment is blocked, no account is
frozen, nothing is approved or rejected, and no customer is contacted. The Scenario Lab's
guard refuses any purpose that routes it toward one of those, and every trigger is tested
(L-24, `tests/unit/test_scenario.py`).

---

## Read this before any number

Five facts that determine how every result in this repository may be read. The full
register is [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

| ID | Constraint |
|---|---|
| **L-04** | **Episode labels are synthetic**, injected into the real NSE price panel. No open labelled corpus of NSE integrity incidents exists. Every detection metric describes behaviour on injected episodes. |
| **L-01** | The research **sampling frame** is a point-in-time liquidity proxy (top 50 by trailing median traded value). It is **not** index membership and is never displayed as the NIFTY 50 — the index is a separate first-class entity with its own data layer ([`docs/INDEX_DATA.md`](docs/INDEX_DATA.md)). NIFTY 50 constituent history remains unavailable, so nothing is conditioned on it. |
| **L-06** | The audio modality operates on a **sonification** of market data, not speech. Claims about real prosody are `NOT MEASURED`. |
| **L-02** | True microstructure (order-book depth, OFI, VPIN) is **`NOT MEASURED`**. Only daily-aggregate proxies exist. |
| **L-11** | The **final holdout is untouched**. Reported numbers are on the validation split. |
| **L-25** | The verified NIFTY 50 series (2024-07-08 →) and the model evaluation window (→ 2023-12-29) **share zero sessions**. The benchmark is market context, never an evaluation variable for the existing results. Computed, not asserted — see [`/research/alignment`](docs/INDEX_DATA.md). |

The application itself builds and serves: 35 files typechecked with zero errors, 204 pages
prerendered, every route verified to return server-rendered content. It has **not** been
deployed to Vercel, so cold-start and edge behaviour are unmeasured.

The market data, by contrast, is entirely real: 8,399,065 rows across 4,487 symbols and
5,337 trading sessions, 2005-01-03 to 2026-08-14, parsed from both NSE bhavcopy layouts.
The **NIFTY 50 index level** is read from NSE's own daily derivatives report — 521 sessions
from 2024-07-08, the first session whose format carries an underlying price. It is the
published level, not a reconstruction.

---

## Quick start

```bash
# research track
python -m venv .venv && .venv/Scripts/activate      # or source .venv/bin/activate
pip install -r requirements.txt

export AEGIS_NSE_ARCHIVE=/path/to/nse/raw           # directory containing cm/ and fo/
python scripts/build_panel.py                       # ~4 min  -> cash panel + PIT universe
python scripts/build_index_panel.py                 # ~90 s   -> NIFTY 50 + NSE index panel
python scripts/build_alignment_report.py            # ~15 s   -> evidence-alignment matrix
python scripts/make_media.py                        # ~1 min  -> licence-clear media corpus
python scripts/build_dataset.py                     # ~30 min -> multimodal dataset
python scripts/run_experiments.py                   # ~10 min -> 32 arms + statistics
python scripts/run_research_angles.py               # ~1 min  -> the 7 runnable experiments
python scripts/generate_paper_artifacts.py          # ~2 min  -> 42 figures, 17 tables
python scripts/run_scenarios.py                     # ~15 min -> the Scenario Lab
run_paper_consolidation.bat                         # ~1 min  -> tables, figures, ledger
python scripts/export_app_data.py                   # ~15 s   -> public/data/*.json

pytest                                              # full test suite
```

`run_paper_consolidation.bat` regenerates the 15 paper tables, the 19 research figures,
the claim ledger, the evidence matrix, the reproducibility map and the eleven-property
scorecard, then rebuilds the module bundle the interface reads. It exits non-zero if any
claim cites an artifact that is not on disk, so a claim cannot outlive its evidence.

```bash
# product track (Node 20+; verified on 24.19.0)
npm install
npm run typecheck && npm run lint && npm run build   # 253 pages prerendered
npm start                                            # production server on :3000
```

```bash
# interactive track: the analysis backend and the interface together
run_dev.bat                                          # both, on :8787 and :3000
run_dev.bat backend                                  # python -m backend.server only

weeks\week_1\run.bat                                 # one week, product view
weeks\week_1\run.bat research                        # the same page, research view
```

The interface reads stored results without the backend and says so; it computes only when
`AEGIS_BACKEND_URL` names a reachable service. Twenty-nine of the thirty-two weekly
modules run their canonical implementation on request, on the slice a reader selects; the
other three replay a provenance-stamped artifact and are labelled as replays. Which of the
two happened is stated on every result — see
[`docs/VERTICAL_SLICES.md`](docs/VERTICAL_SLICES.md).

### One system, exposed a week at a time

The repository holds every week. A run of the product exposes a cumulative slice of it,
chosen by `AEGIS_ACTIVE_WEEK` — week 1 exposes week 1, week 5 exposes weeks 1 to 5, and the
default exposes all sixteen. Each weekly launcher sets its own, so a demonstration shows
one capability without the rest of the programme in the way.

A gated week is not deleted, stubbed or hidden. It answers `FEATURE_NOT_ENABLED` with the
week that would show it, and it answers that way to a browser, to the API and to a
deployment with no backend alike — the gate is server-side in three places, and the
interface's copy of the rule is a label rather than a control. Week 1 is not a smaller
codebase; it is the first enabled state of the whole one. See
[`docs/CAPABILITY_GATE.md`](docs/CAPABILITY_GATE.md).

Research execution is a separate thing and is never gated: `run_all_research.bat`, the
per-category runners, the test suite and the structural validators all operate on the
complete repository.

`--resume` on `build_dataset.py` reuses the assembly checkpoint, which is the expensive
stage.

---

## Repository layout

```
weeks/        week_1 .. week_16 - one launcher and one contract per weekly slice;
              `weeks\week_1\run.bat` starts the backend, the interface and that
              week's page. Generated from the manifest, like STATS/ and MULTIMODAL/
backend/      the orchestration layer: registry (the manifest's schema), contract
              (one response shape, with the rules it must satisfy), service
              (resolve, validate, dispatch), server (stdlib HTTP, eight routes)
research/     core/ data/ market/ regime/ text/ image/ audio/ video/ multimodal/
              models/ xai/ detection/ propagation/ risk/ statistics/ visualization/
              evaluation/ limitations/ claims/ scenario/
scripts/      build_panel · make_media · build_dataset · run_experiments
              run_research_angles · generate_paper_artifacts · export_app_data
app/          Next.js App Router — 4 read-only API routes:
              product   /  /explore  /universe  /events  /instruments/[symbol]
                        /watchlist  /settings
              modules   /stats/[16 routes]  /multimodal/[16 routes]
                        /scenario/[8 routes]  /weeks/[16 routes]
                        each with a product and a research experience,
                        and a run panel wherever the module computes live
              research  /research  …/experiments  …/ablations  …/models  …/datasets
                        …/xai  …/statistics  …/figures  …/tables  …/artifacts
                        …/limitations[/id]  …/claims  …/paper-lab
                        …/reproducibility
components/   ui/ risk/ research/ visualization/ modules/
lib/          mode.tsx (product/research architecture) · data.ts · types.ts
              modules.ts (server accessors) · moduleTypes.ts (isomorphic)
tests/        unit/ property/ integration/ leakage/ multimodal/ xai/
docs/         audit · gap matrix · architecture · limitations · research angles
              licensing · non-advisory · iteration reports
```

## Two experiences, one system

`PRODUCT` answers **what is happening**: integrity state, event timeline, evidence,
plain-language explanation. `RESEARCH` answers **how do we know**: experiments, ablations,
statistical tests, attributions, limitations, claim ledger, reproducibility.

They read the same underlying outputs — only the depth differs. The toggle is the second
control in the masthead, mode and theme are independent preferences with separate storage,
a `/research` URL activates research mode on arrival, and switching mode carries the
instrument you are viewing rather than returning you to Home.

The 32 research modules make this literal. Each has one page holding both experiences,
rendered from one exported record, with CSS keyed on the `data-mode` attribute deciding
which is visible — so the two views are in the same prerendered HTML and cannot disagree
about a number. Product mode answers what the module observed, how far it goes and what
bounds it; Research mode adds the experiment metadata, the artifact paths, the statistical
test, the figures, the tables, the claims and the limitations. Switching depth on a module
page keeps the module, and `?mode=research` in a shared link opens research mode on the
first frame.

Product mode is not permitted to state more than research mode supports. The claim guard
that checks the paper text is run over the interface text by the test suite, so
"weighted fusion is better" fails a test rather than reaching a reader.

---

## Design decisions worth knowing

**Point-in-time correctness is one function.** Every retrieval goes through
`get_evidence(store, instrument, decision_time, knowledge_cutoff)`. It rejects a cutoff
after the decision time, hides records whose knowledge time exceeds the cutoff, and
resolves restatements to the version visible at the cutoff. All six leakage tests (L1–L6)
attack that function and the feature pipeline behind it.

**Absent evidence is excluded, never imputed.** A modality with zero coverage receives zero
fusion weight; with no evidence at all the output is 0.5 with uncertainty 1.0. Substituting
a mean would let an absent modality vote.

**The regime-conditioned fusion bug is proved, not patched.** Adding a regime term to every
softmax numerator cancels exactly under normalisation, so the "regime-conditioned"
formulation is algebraically identical to static attention. Both the inherited and two
corrected formulations are implemented; the equality is asserted numerically over a
parameter grid, and it also shows up empirically — the two arms agree to six decimals in the
ablation table. See `research/multimodal/fusion.py`.

**Text explanations are exact.** The affect extractor is lexicon-based, so per-token
attributions are the computation itself rather than an approximation of it. That is what
makes the XAI faithfulness benchmark meaningful instead of circular.

**Generator and detector are structurally isolated.** No detector module may import the
episode generator; an AST-level test enforces it. Background days also carry media, and a
fraction of them carry alarming text with no episode behind it, so modality presence and
text tone are not the label.

**Unmeasurable things are named.** Six microstructure fields are emitted as `NaN` with a
stated reason and appear as `NOT MEASURED` in the coverage table. OCR and ASR report
`NOT AVAILABLE` rather than inventing text. Every Tier-2 and Tier-3 model carries status
`NOT RUN`.

**Limitations are a research programme, not a disclaimer.** Each of the 12 limitations and
5 negative findings is a structured object carrying the research question it creates and a
falsifiable experiment specification. Seven specifications needed no external data and have
been executed; eleven are `BLOCKED` and name the data that would unblock them. A blocked
specification never carries a number.

**Claims cannot outgrow their evidence.** Eleven claims each carry a validity scope, and an
automated guard refuses text asserting more than that scope supports — including universal
*negatives*, which are exactly as unsupported as universal positives and slip past review
more easily. The guard is tested against known violations, because it once shipped as a
silent no-op.

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/REPOSITORY_AUDIT.md`](docs/REPOSITORY_AUDIT.md) | measured state of the repository and toolchain before this work |
| [`docs/IMPLEMENTATION_GAP_MATRIX.md`](docs/IMPLEMENTATION_GAP_MATRIX.md) | 39 capabilities, blockers, iteration assignment |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | both tracks, module map, bitemporal contract, deployment |
| [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) | 22 limitations and 10 negative findings, each with the claims it invalidates |
| [`docs/DATA_LICENSING.md`](docs/DATA_LICENSING.md) | dataset registry: used, referenced only, not obtained |
| [`docs/NON_ADVISORY.md`](docs/NON_ADVISORY.md) | the policy and its four enforcement mechanisms |
| [`docs/RESEARCH_ANGLES.md`](docs/RESEARCH_ANGLES.md) | how each limitation became an experiment, and what the seven executed ones measured |
| [`docs/ITERATION_REPORT.md`](docs/ITERATION_REPORT.md) | iteration 1: the research pipeline |
| [`docs/ITERATION_2_REPORT.md`](docs/ITERATION_2_REPORT.md) | iteration 2: the two-mode product and the research programme |
| [`docs/PAPER_CONSOLIDATION.md`](docs/PAPER_CONSOLIDATION.md) | the central narrative, the claim ledger, the eleven-property scorecard, and the map from every paper number to the code that produced it |
| [`docs/SCENARIO_LAB.md`](docs/SCENARIO_LAB.md) | counterfactual and observed-condition analysis, what it found, and what it refuses to do |
| [`docs/INDEX_DATA.md`](docs/INDEX_DATA.md) | the NIFTY 50 index data layer: source, licence position, coverage, what the source does not carry, and why the liquidity proxy is a separate entity |
| [`docs/VERTICAL_SLICES.md`](docs/VERTICAL_SLICES.md) | the sixteen weekly slices end to end: what computes live, what replays a verified artifact, the acceptance matrix, and the deployment boundary |
| [`docs/CAPABILITY_GATE.md`](docs/CAPABILITY_GATE.md) | how one repository is demonstrated a week at a time: the cumulative model, the three places it is enforced, and why research execution is not product exposure |

---

## Principles

Open data only. No access control circumvented, no paywall bypassed, no robots directive
ignored. No copyrighted media downloaded, rehosted or redistributed. No fabricated metrics,
datasets, figures, XAI values or media. No future information in a historical decision. No
advisory output on any surface. Where something could not be measured, the artifact says
`NOT MEASURED`, `NOT RUN`, `BLOCKED` or `FAILED`, and says why.
