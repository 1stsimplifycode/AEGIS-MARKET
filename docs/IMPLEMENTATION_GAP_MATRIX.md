# AEGIS-Market — Implementation Gap Matrix

Derived from the audit (`docs/REPOSITORY_AUDIT.md`). Because the repository was greenfield,
**the pre-existing state of every row below is ABSENT**. The matrix therefore records what the
specification requires, what blocks it, and which iteration it is assigned to.

Legend — `Iter`: **1** = this session, **2+** = queued. `Blocker` names the *hard* dependency.

**Status column added after execution** — see `docs/ITERATION_REPORT.md` for the measured
numbers behind each `DONE`.

| # | Spec § | Capability | Pre-existing | Blocker | Iter | Status |
|---|---|---|---|---|---|---|
| G01 | 62,67 | Repo scaffold, deps, env, licences | ABSENT | — | 1 | DONE |
| G02 | 25,27 | Provenance record + bitemporal contracts | ABSENT | — | 1 | DONE |
| G03 | 26 | `get_evidence(instrument, decision_time, knowledge_cutoff)` | ABSENT | — | 1 | DONE |
| G04 | 56 | Leakage tests L1–L6 | ABSENT | — | 1 | DONE (11 tests) |
| G05 | 4 | NSE cash panel, 1994–2026, both bhavcopy formats | ABSENT | — | 1 | DONE (8.4M rows) |
| G06 | 4 | **Historical Nifty-50 membership** | ABSENT | **No licence-clear source found** | blocked — see L-01 | BLOCKED (L-01) |
| G07 | 4 | PIT liquidity-proxy universe (survivorship-safe substitute for G06) | ABSENT | — | 1 | DONE (257 rebalances) |
| G08 | 28 | Market features (returns, vol, entropy, Hurst, gaps, …) | ABSENT | — | 1 | DONE (18 features) |
| G09 | 29 | Microstructure adapter + proxies | ABSENT | No open L2/order-book history | 1 (proxy only) | DONE (4 proxies; 6 NOT MEASURED) |
| G10 | 30 | Regime detection + validation | ABSENT | — | 1 | DONE (k=4, p=0.016) |
| G11 | 10 | Text ingest + affective text features | ABSENT | — | 1 | DONE (447 terms) |
| G12 | 11 | Image pipeline (embeddings, visual affect, OCR adapter) | ABSENT | Tesseract binary absent → OCR degrades honestly | 1 | DONE (OCR NOT AVAILABLE) |
| G13 | 12 | Audio pipeline (prosody, pitch, rate, pauses, arousal) | ABSENT | — | 1 | DONE (pitch within 0.5%) |
| G14 | 13 | Video pipeline (frames, scenes, audio, transcript, temporal) | ABSENT | ffmpeg via imageio-ffmpeg | 1 | DONE (cut detection verified) |
| G15 | 14,15,16,51,52 | Media licence gate + reference-only artifacts | ABSENT | — | 1 | DONE |
| G16 | 17 | Affective representation (valence/arousal/uncertainty/hype…) | ABSENT | — | 1 | DONE |
| G17 | 18 | Fusion: early/late/static/attention/regime-cond/uncertainty | ABSENT | — | 1 | DONE (6 strategies) |
| G18 | 57 | **Regime-degeneracy proof + corrected formulation** | ABSENT | — | 1 | DONE (<1e-12) |
| G19 | 19,59 | `MultimodalModelAdapter` + tiered model registry | ABSENT | Tier-2/3 weights not installed → `NOT RUN` | 1 (Tier-1 only) | DONE (Tier 1 RUN; Tier 2/3 NOT RUN) |
| G20 | 20–24 | XAI stack + benchmark + sanity checks | ABSENT | — | 1 | DONE (1 sanity FAIL reported) |
| G21 | 6,8 | Temporal risk state machine, `t_entry`/`t_exit`, `W_e` | ABSENT | — | 1 | DONE |
| G22 | 32 | Cross-instrument propagation graph | ABSENT | — | 1 | DONE (5 features) |
| G23 | 33,34 | Risk gate + capital-consequence (CVaR, MDD, turnover) | ABSENT | — | 1 | DONE (CVaR p=0.0005) |
| G24 | 31 | Synthetic episode generator (generator/detector separation) | ABSENT | — | 1 | DONE (140 episodes) |
| G25 | 35,82,83 | Experiment engine + reproducibility manifest | ABSENT | — | 1 | DONE |
| G26 | 36,37,71 | Ablation framework (17 arms) | ABSENT | — | 1 | DONE (32 arms) |
| G27 | 48 | Statistics (bootstrap CI, permutation, paired, FDR) | ABSENT | — | 1 | DONE (BH-FDR) |
| G28 | 38–41,75,76 | Figure engine + registry + journal styles | ABSENT | — | 1 | DONE (35 figures) |
| G29 | 42,47 | Table engine (csv/json/md/tex) | ABSENT | — | 1 | DONE (15 tables x 4 formats) |
| G30 | 45,46,80,87 | `generate_paper_artifacts.py` + captions + paper package | ABSENT | — | 1 | DONE (99s regeneration) |
| G31 | 49,74 | Error taxonomy + plots | ABSENT | — | 1 | DONE |
| G32 | 72,73 | Baselines + metric suite | ABSENT | — | 1 | DONE (7 baselines) |
| G33 | 50 | Case-study packages | ABSENT | Needs real licence-clear media | 2 | DEFERRED (needs media) |
| G34 | 55,84 | Frozen final holdout, executed once | ABSENT | Must follow full freeze | 2 | DEFERRED (freeze first) |
| G35 | 62,68,69 | Next.js/Vercel dashboard (11 views) | ABSENT | **Node.js absent** → written, build unverified | 1 (written) | WRITTEN, BUILD NOT VERIFIED (L-03) |
| G36 | 64,65 | Postgres schema + object storage | ABSENT | No DB provisioned | 1 (schema + local adapter) | PARTIAL (static bundles) |
| G37 | 66 | Auth, secrets, SAST, audit log | ABSENT | Needs deploy target | 2 | PARTIAL (secret scan, headers) |
| G38 | 89 | CI/CD pipeline | ABSENT | Node absent → JS jobs unverifiable | 1 (written) | WRITTEN (JS jobs unverified) |
| G39 | 3 | Non-advisory enforcement (tested, not just stated) | ABSENT | — | 1 | DONE (scan passes) |

## Hard blockers carried forward

- **L-01 Historical index membership.** No free, licence-clear, point-in-time Nifty-50
  constituent history was located. Fabricating one is prohibited (§85). Mitigation: the
  research universe is a **point-in-time liquidity-proxy universe** computed from the NSE panel
  itself, which is survivorship-safe by construction and fully reproducible. It is *not* the
  Nifty 50 and is never labelled as such.
- **L-02 Microstructure.** NSE does not publish historical order-book depth openly. Only
  bhavcopy-derived proxies (trade-size, turnover-per-trade, trade-count anomaly) are computed.
  True OFI/VPIN/depth are `NOT MEASURED`.
- **L-03 Node.js.** Product-track build/test cannot be executed here.
- **L-04 Labels.** Market-integrity *incidents* have no open labelled corpus for NSE. Detection
  metrics in iteration 1 are computed on **synthetic episodes injected into real market data**
  with generator/detector parameter separation (§31). This is stated everywhere the numbers
  appear and is **not** a claim of real-world manipulation detection performance.
