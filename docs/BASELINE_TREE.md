# Baseline repository tree

Captured before any restructuring. Git commit `8774260` (branch `main`).
Excludes `.venv/`, `node_modules/`, `.next/`, `__pycache__/`, caches.

```text
AEGIS-MARKET/
├── .github/  (1 files)
│   └── workflows/  (1 files)
│       └── ci.yml
├── app/  (27 files)
│   ├── api/  (4 files)
│   │   ├── artifacts/  (1 files)
│   │   │   └── route.ts
│   │   ├── experiments/  (1 files)
│   │   │   └── route.ts
│   │   ├── research/  (1 files)
│   │   │   └── route.ts
│   │   └── risk/  (1 files)
│   │       └── route.ts
│   ├── events/  (1 files)
│   │   └── page.tsx
│   ├── explore/  (1 files)
│   │   └── page.tsx
│   ├── instruments/  (1 files)
│   │   └── [symbol]/  (1 files)
│   │       └── page.tsx
│   ├── research/  (14 files)
│   │   ├── ablations/  (1 files)
│   │   │   └── page.tsx
│   │   ├── claims/  (1 files)
│   │   │   └── page.tsx
│   │   ├── datasets/  (1 files)
│   │   │   └── page.tsx
│   │   ├── experiments/  (1 files)
│   │   │   └── page.tsx
│   │   ├── figures/  (1 files)
│   │   │   └── page.tsx
│   │   ├── lifecycle/  (1 files)
│   │   │   └── page.tsx
│   │   ├── limitations/  (2 files)
│   │   │   ├── [id]/  (1 files)
│   │   │   └── page.tsx
│   │   ├── models/  (1 files)
│   │   │   └── page.tsx
│   │   ├── paper-lab/  (1 files)
│   │   │   └── page.tsx
│   │   ├── reproducibility/  (1 files)
│   │   │   └── page.tsx
│   │   ├── statistics/  (1 files)
│   │   │   └── page.tsx
│   │   ├── xai/  (1 files)
│   │   │   └── page.tsx
│   │   └── page.tsx
│   ├── settings/  (1 files)
│   │   └── page.tsx
│   ├── universe/  (1 files)
│   │   └── page.tsx
│   ├── watchlist/  (1 files)
│   │   └── page.tsx
│   ├── globals.css
│   ├── layout.tsx
│   └── page.tsx
├── components/  (8 files)
│   ├── research/  (1 files)
│   │   └── AngleSections.tsx
│   ├── risk/  (2 files)
│   │   ├── RiskProfileTimeline.tsx
│   │   └── RiskTrace.tsx
│   ├── ui/  (4 files)
│   │   ├── Chrome.tsx
│   │   ├── NonAdvisoryNotice.tsx
│   │   ├── Primitives.tsx
│   │   └── SubjectRegistrar.tsx
│   └── visualization/  (1 files)
│       └── Sparkline.tsx
├── data/  (17 files)
│   ├── cache/  (0 files)
│   ├── media/  (11 files)
│   │   ├── audio/  (4 files)
│   │   │   ├── noise_burst.wav
│   │   │   ├── speechlike_180hz.wav
│   │   │   ├── tone_220hz.wav
│   │   │   └── voiced_140hz.wav
│   │   ├── images/  (3 files)
│   │   │   ├── chart_hdfcbank.png
│   │   │   ├── chart_icicibank.png
│   │   │   └── chart_reliance.png
│   │   ├── references/  (3 files)
│   │   │   ├── media_ref_1b62c9f5a86634c3.json
│   │   │   ├── media_ref_3ca0b266da4f7058.json
│   │   │   └── media_ref_784e69ac233ab7a1.json
│   │   └── video/  (1 files)
│   │       └── chart_hdfcbank.mp4
│   └── panel/  (6 files)
│       ├── _assembly_checkpoint_20260818.parquet
│       ├── cash_panel.parquet
│       ├── episode_labels.parquet
│       ├── multimodal_dataset.parquet
│       ├── text_corpus.parquet
│       └── universe.parquet
├── docs/  (10 files)
│   ├── ARCHITECTURE.md
│   ├── DATA_LICENSING.md
│   ├── IMPLEMENTATION_GAP_MATRIX.md
│   ├── ITERATION_2_REPORT.md
│   ├── ITERATION_3_REPORT.md
│   ├── ITERATION_REPORT.md
│   ├── LIMITATIONS.md
│   ├── NON_ADVISORY.md
│   ├── REPOSITORY_AUDIT.md
│   └── RESEARCH_ANGLES.md
├── experiments/  (0 files)
│   ├── configs/  (0 files)
│   ├── manifests/  (0 files)
│   └── runners/  (0 files)
├── lib/  (3 files)
│   ├── data.ts
│   ├── mode.tsx
│   └── types.ts
├── paper_package/  (481 files)
├── public/  (19 files)
│   └── data/  (19 files)
│       ├── affective.json
│       ├── assessments.json
│       ├── claims.json
│       ├── clusters.json
│       ├── coverage.json
│       ├── evidence.json
│       ├── experiments.json
│       ├── figures.json
│       ├── lifecycle.json
│       ├── lifecycle_trajectories.json
│       ├── limitations.json
│       ├── modality_info.json
│       ├── propagation.json
│       ├── provenance.json
│       ├── reproducibility.json
│       ├── research_angles.json
│       ├── statistics.json
│       ├── universe.json
│       └── windows.json
├── research/  (130 files)
│   ├── affective/  (1 files)
│   │   └── __init__.py
│   ├── audio/  (6 files)
│   │   ├── __init__.py
│   │   ├── pipeline.py
│   │   └── sonify.py
│   ├── claims/  (4 files)
│   │   ├── __init__.py
│   │   └── ledger.py
│   ├── core/  (14 files)
│   │   ├── __init__.py
│   │   ├── contracts.py
│   │   ├── jsonio.py
│   │   ├── licensing.py
│   │   ├── manifest.py
│   │   ├── paths.py
│   │   └── progress.py
│   ├── data/  (7 files)
│   │   ├── __init__.py
│   │   ├── dataset.py
│   │   ├── nse_bhavcopy.py
│   │   └── universe.py
│   ├── detection/  (6 files)
│   │   ├── __init__.py
│   │   ├── episodes.py
│   │   └── state.py
│   ├── evaluation/  (12 files)
│   │   ├── __init__.py
│   │   ├── ablations.py
│   │   ├── experiment.py
│   │   ├── information.py
│   │   ├── metrics.py
│   │   └── temporal_analysis.py
│   ├── image/  (6 files)
│   │   ├── __init__.py
│   │   ├── chartgen.py
│   │   └── pipeline.py
│   ├── lifecycle/  (8 files)
│   │   ├── __init__.py
│   │   ├── changepoints.py
│   │   ├── stages.py
│   │   └── states.py
│   ├── limitations/  (4 files)
│   │   ├── __init__.py
│   │   └── registry.py
│   ├── market/  (4 files)
│   │   ├── __init__.py
│   │   └── features.py
│   ├── media/  (1 files)
│   │   └── __init__.py
│   ├── microstructure/  (1 files)
│   │   └── __init__.py
│   ├── models/  (6 files)
│   │   ├── __init__.py
│   │   ├── baselines.py
│   │   ├── registry.py
│   │   └── risk_model.py
│   ├── multimodal/  (4 files)
│   │   ├── __init__.py
│   │   └── fusion.py
│   ├── propagation/  (4 files)
│   │   ├── __init__.py
│   │   └── graph.py
│   ├── regime/  (4 files)
│   │   ├── __init__.py
│   │   └── detection.py
│   ├── risk/  (4 files)
│   │   ├── __init__.py
│   │   └── gate.py
│   ├── statistics/  (6 files)
│   │   ├── __init__.py
│   │   ├── power.py
│   │   └── tests.py
│   ├── text/  (6 files)
│   │   ├── __init__.py
│   │   ├── affect.py
│   │   └── lexicon.py
│   ├── video/  (4 files)
│   │   ├── __init__.py
│   │   └── pipeline.py
│   ├── visualization/  (8 files)
│   │   ├── __init__.py
│   │   ├── figures.py
│   │   ├── registry.py
│   │   └── style.py
│   ├── xai/  (8 files)
│   │   ├── __init__.py
│   │   ├── benchmark.py
│   │   ├── methods.py
│   │   └── sanity.py
│   └── __init__.py
├── research_artifacts/  (726 files)
├── scripts/  (8 files)
│   ├── build_dataset.py
│   ├── build_panel.py
│   ├── export_app_data.py
│   ├── generate_paper_artifacts.py
│   ├── make_media.py
│   ├── run_experiments.py
│   ├── run_lifecycle.py
│   └── run_research_angles.py
├── tests/  (22 files)
│   ├── integration/  (2 files)
│   │   └── test_end_to_end.py
│   ├── leakage/  (2 files)
│   │   └── test_leakage_suite.py
│   ├── multimodal/  (2 files)
│   │   └── test_modalities.py
│   ├── property/  (4 files)
│   │   ├── test_invariants.py
│   │   └── test_regime_degeneracy.py
│   ├── unit/  (10 files)
│   │   ├── test_app_surface.py
│   │   ├── test_claims_and_limitations.py
│   │   ├── test_exported_bundles.py
│   │   ├── test_lifecycle.py
│   │   └── test_non_advisory.py
│   └── xai/  (2 files)
│       └── test_xai.py
├── .env.example
├── .gitignore
├── README.md
├── eslint.config.mjs
├── next-env.d.ts
├── next.config.mjs
├── package-lock.json
├── package.json
├── pyproject.toml
├── requirements.txt
├── tsconfig.json
├── tsconfig.tsbuildinfo
└── vercel.json
```
