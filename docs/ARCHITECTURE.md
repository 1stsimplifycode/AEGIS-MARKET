# AEGIS-Market — Architecture

Two tracks that share contracts and nothing else. That separation is the single most
important structural decision in the system, and it is what makes the product deployable on
Vercel while the research runs anywhere.

```
                        ┌─────────────────────────────────────────┐
   RESEARCH TRACK       │  runs offline, on a workstation or CI   │
   (Python)             └─────────────────────────────────────────┘

   NSE cash archive ──▶ nse_bhavcopy ──▶ cash_panel.parquet
   (external, read-only)                        │
                                                ├──▶ universe (PIT liquidity proxy)
                                                │
   synthetic episodes ──▶ inject ──────────────▶ injected panel
                                                │
                                                ├──▶ market features + micro proxies
                                                ├──▶ regimes (fitted on train only)
                                                ├──▶ text corpus ──▶ affect (AFAL v1)
                                                ├──▶ chart rasters ──▶ image features
                                                ├──▶ sonification ──▶ audio features
                                                ├──▶ chart clips ──▶ video features
                                                └──▶ correlation graph ──▶ propagation
                                                          │
                                            multimodal_dataset.parquet
                                                          │
                          ┌───────────────────────────────┴──────────────────────┐
                          ▼                                                      ▼
              per-modality learners                                   ablation arms (32)
                          │                                                      │
                    fusion layer  ◀── regime, coverage, confidence               │
                          │                                                      │
        integrity risk · uncertainty · coverage                                  │
                          │                                                      │
              temporal state machine ──▶ risk windows                            │
                          │                                                      │
                    XAI + sanity ────────────────────────────────────────────────┤
                          │                                                      │
              research exposure gate ──▶ capital consequence                     │
                          │                                                      │
                          └──────────▶ figures · tables · captions · statistics ◀┘
                                                          │
                                     export_app_data.py ──┤──▶ paper_package/
                                                          ▼
                        ┌─────────────────────────────────────────┐
   PRODUCT TRACK        │  public/data/*.json  (static bundles)   │
   (Next.js on Vercel)  └─────────────────────────────────────────┘
                                                          │
                        11 views · 3 read-only API routes · no model in the request path
```

## Why the product reads static JSON

Spec §62 forbids long training, GPU inference, heavy video processing and multi-hour
backtests inside normal Vercel requests. The strongest way to honour that is to make it
structurally impossible: the app has no Python, no parquet reader and no model. It reads
bundles that `scripts/export_app_data.py` produced, so:

- the product cannot display a number the research pipeline did not produce;
- a deployment has zero external dependencies, so it is reproducible;
- both the app and the paper trace to the same run identifier.

The `api` data mode exists for a future inference service (`INFERENCE_SERVICE_URL`) but is
not the default and is not required.

## Module map

| Path | Responsibility |
|---|---|
| `research/core/contracts.py` | `Provenance`, `EvidenceRecord`, `BitemporalStore`, `get_evidence`, `RiskState`, `RiskAssessment` |
| `research/core/licensing.py` | `MediaLicenseChecker`, licence registries, `LicenseViolation` |
| `research/core/manifest.py` | reproducibility manifests, environment snapshot, hashes |
| `research/core/progress.py` | stage timing that survives a buffered pipe |
| `research/data/nse_bhavcopy.py` | both bhavcopy layouts, bitemporal stamping |
| `research/data/universe.py` | PIT liquidity-proxy universe; survivorship guard |
| `research/data/dataset.py` | multimodal assembly, modality blocks, coverage flags |
| `research/market/features.py` | market features and microstructure proxies |
| `research/regime/detection.py` | GMM regimes, order selection, stability, shuffle null |
| `research/text/{lexicon,affect}.py` | AFAL v1 lexicon; exact token-level affect |
| `research/image/{pipeline,chartgen}.py` | image descriptors, occlusion, fast chart rasteriser |
| `research/audio/{pipeline,sonify}.py` | prosody/spectral DSP; market sonification |
| `research/video/pipeline.py` | frame sampling, scene changes, audio branch, licence gate |
| `research/multimodal/fusion.py` | six fusion strategies; the degeneracy result |
| `research/models/{risk_model,baselines,registry}.py` | per-modality learners, baselines, model tiers |
| `research/detection/{episodes,state}.py` | episode generator; temporal state machine |
| `research/propagation/graph.py` | PIT correlation graph, neighbour-stress features |
| `research/risk/gate.py` | monotone exposure gate, capital consequence |
| `research/xai/{methods,benchmark,sanity}.py` | attributions, faithfulness, sanity suite |
| `research/statistics/tests.py` | cluster bootstrap, paired tests, permutation, BH-FDR |
| `research/evaluation/{experiment,ablations,metrics}.py` | experiment engine, 32 arms, metrics |
| `research/visualization/{style,registry,figures}.py` | journal style, registries, figure generators |

## The bitemporal contract

Four timestamps per record, and the distinction between them is the point:

| field | meaning |
|---|---|
| `event_time` | when the thing described happened |
| `publication_time` | when a publisher first made it public |
| `knowledge_time` | when *this system* could first have acted on this exact value |
| `retrieval_time` | when it was fetched |

`get_evidence(store, instrument, decision_time, knowledge_cutoff)` is the only retrieval
path. It rejects a cutoff after the decision time, hides records whose knowledge time
exceeds the cutoff, and resolves competing versions of the same fact to the latest one
visible at the cutoff — so a restatement cannot leak backwards. All six leakage tests
attack this one function and the feature pipeline behind it.

For the market panel the knowledge-time policy is explicit and is a modelling decision, not
a fact: the cash bhavcopy for date *D* is stamped `event_time` 15:30 IST and
`knowledge_time` 18:00 IST.

## The fusion layer

Per-modality calibrated scores in, one risk estimate out. A modality with zero coverage is
excluded, never imputed — a mean substitution would let an absent modality vote, and a
leakage test asserts it cannot.

Uncertainty is not a learned scalar. It combines two measurable quantities: disagreement
between the modalities that *are* present, and how much of the stack is missing. With no
evidence at all the output is 0.5 with uncertainty 1.0.

## Deployment topology

```
Vercel (Next.js)  ──▶ static JSON bundles           [always]
                  ──▶ Postgres for metadata          [optional]
                  ──▶ object storage for media       [optional]
                  ──▶ inference service              [optional]

Research runner   ──▶ object storage ──▶ export ──▶ repository/public/data
```

Nothing in the request path exceeds tens of milliseconds, because nothing in the request
path computes anything.

## Security posture

Secrets are server-only; a CI job fails the build if anything secret-looking appears behind
`NEXT_PUBLIC_`. API routes validate the instrument identifier against a strict pattern
before use. Security headers are set in `next.config.mjs`. Static analysis (`bandit`) and a
dependency audit (`pip-audit`) run in CI. Model loading is limited to scikit-learn objects
constructed in-process; no pickle is loaded from an untrusted path.

## What is deliberately absent

- No scraper. Market data comes from a local archive; media is generated here or
  referenced by URL.
- No pickled model artifacts checked in — models are refit from the recorded seed.
- No torch/transformers in the deployed path, and none in the reported results (L-08).
- No holdout evaluation until the freeze is complete (L-11).
