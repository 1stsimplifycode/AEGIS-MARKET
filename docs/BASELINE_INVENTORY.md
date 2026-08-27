# Baseline inventory

State of the repository **before** any restructuring, captured by inspection rather than
by reading documentation. Every claim below was verified by running a command against the
working tree; where documentation and implementation disagreed, the implementation wins
and the disagreement is recorded.

Git commit at capture: `8774260` ("Initial commit"), branch `main`.

---

## 1. Current architecture

Two tracks that meet only at a file boundary:

```
  OFFLINE RESEARCH TRACK (Python)              DEPLOYED PRODUCT (Next.js)
  ────────────────────────────────             ──────────────────────────
  data/            raw + panel parquet
  research/        21 packages, 11 474 loc
  scripts/         8 runners, 3 493 loc
        │
        ├─ research_artifacts/  (726 files)  ──►  paper_package/
        │
        └─ scripts/export_app_data.py
                  │
                  ▼
             public/data/*.json  (19 bundles)  ──►  lib/data.ts
                                                         │
                                                    app/ (21 pages, 4 API routes)
```

The separation is deliberate and correct for Vercel: no model runs in a request path.
`lib/data.ts` reads exported JSON only, and every accessor degrades to
`dataAvailable: false` with a note naming the script that would produce the missing file.

---

## 2. Execution paths that exist today

| Command | Purpose | Status |
|---|---|---|
| `python scripts/build_panel.py` | NSE bhavcopy → cash panel | works |
| `python scripts/make_media.py` | derived image/audio/video assets | works |
| `python scripts/build_dataset.py` | 99-feature multimodal dataset | works |
| `python scripts/run_experiments.py` | 6 baselines + 32 ablation arms + statistics | works |
| `python scripts/run_research_angles.py` | 9 runnable limitation-derived experiments | works |
| `python scripts/run_lifecycle.py` | position-lifecycle analyses | works |
| `python scripts/generate_paper_artifacts.py` | 48 figures, 19 tables, manifests, paper package | works |
| `python scripts/export_app_data.py` | 19 JSON bundles for the app | works |
| `npm run build` / `lint` / `typecheck` | product build | works |

**There is no `.bat` file anywhere in the repository** (the only two matches are
`.venv/Scripts/activate.bat` and `deactivate.bat`, which belong to the virtualenv).
**There is no `STATS/` or `MULTIMODAL/` directory.** The 16 + 16 module structure is
entirely new work.

---

## 3. Canonical implementation locations

`research/` is a **library**: verified by `grep -rln "def main(" research/` returning
nothing. Every entry point lives in `scripts/`. This matters for the wrapper design — a
per-module `run.bat` cannot call a library function directly, so each module needs a thin
CLI shim that imports the canonical function and calls it.

| Package | Files | Lines | What is canonical here |
|---|---:|---:|---|
| `research/limitations/` | 1 | 1 800 | 15 limitations + 7 negative findings, 25 RQs, 23 experiment specs |
| `research/visualization/` | 3 | 1 273 | 48 figure generators, figure/table registry with captions + hashes |
| `research/claims/` | 1 | 534 | 12-claim ledger with the scope guard |
| `research/lifecycle/` | 3 | 946 | phases, states, change points, stage-differential experiment |
| `research/data/` | 3 | 725 | bhavcopy loader, universe construction, dataset assembly |
| `research/evaluation/` | 5 | 954 | metrics, experiment engine, 32 ablation arms, information decomposition, temporal analysis |
| `research/xai/` | 3 | 602 | 11 attribution methods, faithfulness/stability/agreement benchmark, sanity suite |
| `research/detection/` | 2 | 530 | episode generator (structurally isolated), risk state machine |
| `research/core/` | 6 | 611 | paths, contracts, manifests, licensing, progress, strict JSON |
| `research/text/` | 2 | 427 | affect lexicon + extractor |
| `research/audio/` | 2 | 382 | sonification + prosody feature stack |
| `research/models/` | 3 | 473 | risk model, 6 baselines, tiered model registry |
| `research/image/` | 2 | 286 | chart rasteriser + image descriptor stack |
| `research/video/` | 1 | 264 | frame-sequence feature stack |
| `research/statistics/` | 2 | 346 | cluster bootstrap, permutation, BH-FDR, power/MDE |
| `research/market/` | 1 | 231 | 18 market features + 4 microstructure proxies |
| `research/regime/` | 1 | 209 | regime detection |
| `research/propagation/` | 1 | 190 | statistical co-movement graph |
| `research/risk/` | 1 | 166 | exposure gate policy + capital consequence |
| `research/multimodal/` | 1 | 255 | 6 fusion strategies + degeneracy proof |

### Empty package stubs (verified 0 bytes)

- `research/affective/__init__.py` — affect actually lives in `research/text/affect.py`
  and `research/audio/pipeline.py`
- `research/media/__init__.py` — media generation lives in `scripts/make_media.py`
- `research/microstructure/__init__.py` — proxies live in `research/market/features.py`
  (`MICROSTRUCTURE_PROXIES`, 4 features)

### Empty scaffolding directories (verified 0 files)

- `experiments/configs/`, `experiments/manifests/`, `experiments/runners/`
- `research_artifacts/csv/`, `json/`, `latex/`, `supplementary/`

---

## 4. Feature inventory (verified by importing the module)

| Block | Features |
|---|---:|
| text | 20 |
| audio | 19 |
| market | 18 |
| video | 14 |
| image | 12 |
| regime | 7 |
| propagation | 5 |
| microstructure | 4 |
| **total** | **99** |

Dataset version `dataset-v1`; the assembled panel is 16 558 rows × 119 columns over 182
symbols, split train 9 351 (2015-04-07 → 2021-12-31) / validation 3 855 (2022 → 2023) /
holdout 3 352 (2024-01-01 → 2026-08-14).

---

## 5. Datasets and media

| Path | Contents |
|---|---|
| `data/panel/cash_panel.parquet` | NSE cash bhavcopy, 15 columns |
| `data/panel/universe.parquet` | point-in-time liquidity-proxy universe |
| `data/panel/episode_labels.parquet` | synthetic injected episodes |
| `data/panel/text_corpus.parquet` | generated text corpus |
| `data/panel/multimodal_dataset.parquet` | assembled 119-column dataset |
| `data/media/{images,audio,video,references}/` | derived media + reference metadata |

No copyrighted third-party media is stored; `data/media/references/` holds metadata only.

---

## 6. Models

`research/models/registry.py` declares tiers with honest status:

- **Tier 1 — status `RUN`**: lexicon affect extractor, image descriptor stack, audio
  prosody stack, video frame stack, HistGradientBoosting risk learner. Everything reported
  in this release uses Tier 1.
- **Tier 2 — status `NOT RUN`**: FinBERT-class transformer, CLIP/SigLIP-class encoder,
  Whisper-class ASR.
- **Tier 3 — status `NOT RUN`**: video-language model.

Verified against `requirements.txt`, which deliberately does not pin torch, transformers,
librosa or opencv.

---

## 7. Tests (baseline, verified by running)

```
pytest tests/ -q   →  542 passed in 126.42s
ruff check .       →  All checks passed
tsc --noEmit       →  exit 0
eslint .           →  exit 0
next build         →  210 static pages
```

| Suite | Lines | Covers |
|---|---:|---|
| `tests/unit/test_non_advisory.py` | 288 | advisory-language scan, lifecycle transactional scan, disclaimer |
| `tests/unit/test_lifecycle.py` | 272 | change points against known shifts, phases, bucket partitioning |
| `tests/leakage/test_leakage_suite.py` | 224 | L1–L6 leakage tests (blocking in CI) |
| `tests/multimodal/test_modalities.py` | 220 | per-modality feature contracts |
| `tests/integration/test_end_to_end.py` | 216 | pipeline end to end |
| `tests/unit/test_claims_and_limitations.py` | 181 | claim guard fires, registry integrity |
| `tests/xai/test_xai.py` | 171 | attribution methods, sanity suite |
| `tests/property/test_invariants.py` | 147 | invariants |
| `tests/unit/test_app_surface.py` | 146 | route/page surface |
| `tests/unit/test_exported_bundles.py` | 95 | strict JSON over bundles **and** 202 research artifacts |
| `tests/property/test_regime_degeneracy.py` | 92 | fusion degeneracy proof |

The 542 total includes 202 parametrised artifact-parsing cases.

---

## 8. Frontend

21 pages, 4 API routes, 8 components, 3 lib modules.

- Product Mode: `/`, `/explore`, `/universe`, `/events`, `/watchlist`, `/settings`,
  `/instruments/[symbol]`
- Research Mode: `/research` + `ablations`, `claims`, `datasets`, `experiments`,
  `figures`, `lifecycle`, `limitations` (+ `[id]`), `models`, `paper-lab`,
  `reproducibility`, `statistics`, `xai`
- Mode is an axis independent of theme (`lib/mode.tsx`, separate storage keys)
- API: `/api/artifacts`, `/api/experiments`, `/api/research`, `/api/risk` — all
  `force-static`, all reading exported bundles, no computation

---

## 9. Deployment

`vercel.json`: Next.js framework, region `bom1`, `maxDuration` 30 s on API routes.
`next.config.mjs`: strict mode, security headers, no powered-by header.
`package.json`: Next 15.5.23, React 19, TypeScript 5.7.3, Node ≥ 20. Three runtime
dependencies only. No deployment has been performed (recorded as L-03).

---

## 10. Known limitations already registered

15 limitations (L-01 … L-15) and 7 negative findings (N-01 … N-07), each with category,
status, invalidated claims, what remains valid, research questions and experiment
specifications. 11 specifications runnable now, 12 blocked on external data.

---

## 11. Discrepancies found between documentation and implementation

These are recorded rather than silently fixed.

1. **`CLAIM-12` cites latency figures with no backing artifact.** The ledger states
   "p50 latency 5.9–10.0 ms and p95 17.1–32.9 ms over 20 samples per route". No file under
   `research_artifacts/` contains those numbers; they were measured ad-hoc and hand-typed.
   Under the provenance rule this is an unbacked number.
2. **`CLAIM-12` is stale.** It says "204 pages including 162 instrument routes and 17
   limitation routes"; the current build produces 210 pages and 22 limitation routes.
3. **`operational_metrics(peak_memory_mb=…)` is never called with a value.** Verified:
   the only references are the definition itself and a registry mention. No memory is
   measured anywhere; `grep psutil` returns nothing.
4. **Three package stubs and four artifact directories are empty**, listed in §3.
5. **`experiments/` at the repository root is empty scaffolding** — the real experiment
   bundles live in `research_artifacts/experiment_reports/`.
