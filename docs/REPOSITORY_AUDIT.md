# AEGIS-Market — Repository Audit

**Audit date:** 2026-08-18
**Auditor:** implementation engineer (this session)
**Target:** https://github.com/1stsimplifycode/AEGIS-MARKET
**Method:** `git clone --depth 50`, full-tree enumeration, history inspection.

---

## A1. Remote repository state (measured, not assumed)

| Property | Measured value |
|---|---|
| Clone succeeded | yes (public) |
| Branches | `main` only (`origin/HEAD -> origin/main`) |
| Commits | **1** — `8774260 Initial commit` |
| Tracked files | **1** — `README.md` |
| README size | 14 bytes (`# AEGIS-MARKET`) |
| Source files | 0 |
| Tests | 0 |
| Dependency manifests | none (`package.json`, `requirements.txt`, `pyproject.toml` all absent) |
| Deployment config | none (`vercel.json`, `next.config.*` absent) |
| CI config | none (`.github/` absent) |
| Datasets | none |
| Models | none |
| Documentation | none |
| Licence file | none |

**Verdict: the repository is greenfield.** Nothing in the prompt's assumed architecture exists.
No stack decision has been recorded anywhere in the repository. Every architectural claim in
this build is therefore a *decision made now*, not a discovery.

## A2. Local context discovered outside the repository

The working directory (`C:\Users\abcom\Downloads`) contains prior AEGIS-Market planning
documents and — materially — a **separate, unrelated prior research project** with a large
real NSE dataset already downloaded.

### A2.1 Planning documents (PDF/DOCX, not code)

- `AEGIS_Market_Documentation.pdf`
- `AEGIS-Market_16-Week_Execution_Roadmap.pdf`
- `AEGIS-Market_Weekly_Architecture_Build_Plan.pdf`
- `AEGIS-Market_Guide_Meeting_Minutes_Weeks_1-16.{pdf,docx}`

These are planning artifacts. They are **not** an implementation and were not treated as one.

### A2.2 Prior project: `capstone project/beta layer`

An independent research repository (`git`, 6 commits, latest
`57ff41f Measured cash census; finalise corpus totals`) on a *different* research question
("Hierarchical Regime-Aware Portfolio Policy for the Nifty 50" — breadth saturation under the
Fundamental Law of Active Management). Its own README states: *"Not a multimodal system.
There is no fusion layer anywhere in the design."*

**It is not AEGIS-Market.** However it contains an asset of direct value:

| Asset | Measured value |
|---|---|
| NSE **cash** bhavcopy archive | 7,861 trading days, 1994-11-03 → 2026-08-14, 419 MB, 11,811,152 rows |
| NSE **F&O** bhavcopy archive | 6,461 trading days, 2000 → 2026-08, 2.4 GB, 182,096,005 rows (39.95 % traded) |
| Collector | `src/data/collectors/nse_bhavcopy.py` |
| Validators | `src/data/validators/{corpus_stats,verify_download}.py` |
| Research method docs | 30+ files on bias control, point-in-time correctness, survivorship |

**Format census (measured by this audit, not assumed):**

- Legacy format `cmDDMMMYYYYbhav.csv` — from `cm_19941103.zip` to `cm_20240705.zip`
- UDiFF format `BhavCopy_NSE_CM_0_0_0_YYYYMMDD_F_0000.csv` — from `cm_20240708.zip` onward
- Exactly one transition point; both formats verified by direct read.

**Decision:** AEGIS-Market ingests this archive as a **read-only external source**. It is not
copied into the repository. Its licence status is recorded in `docs/DATA_LICENSING.md`.
This is the single reason a real market-data track exists at all in iteration 1 — without it
the market modality would have been `NOT MEASURED`.

## A3. Toolchain audit (measured)

| Tool | Status |
|---|---|
| Python | **3.12.10 present** |
| pip | 25.0.1 present |
| git | 2.55.0.windows.3 present |
| **Node.js / npm** | **ABSENT** — searched `PATH`, `Program Files\nodejs`, `LOCALAPPDATA\Programs\nodejs`, `nvm`, `nvs`, `volta`. Not installed. |
| GPU | not probed; assume none |
| Scientific Python stack | was absent; installed into `.venv` by this session (see A4) |

**Consequence (load-bearing, stated up front):** the Next.js/Vercel product surface can be
**written** but **cannot be built, typechecked, linted or run** in this environment. Any claim
that the product track "works" would be unverifiable. It is therefore reported as
`WRITTEN — BUILD NOT VERIFIED` until Node is installed, and the research track — which *can*
be executed and verified here — is the priority for iteration 1.

## A4. Environment provisioned by this session

`.venv` (Python 3.12.10), verified imports:

```
numpy 2.5.2      pandas 3.0.5     scipy 1.18.0     scikit-learn 1.9.0
matplotlib 3.11.1 pyarrow 25.0.1  duckdb 1.5.5     statsmodels 0.14.6
networkx 3.6.1   shap 0.52.0      soundfile 0.14.0 imageio 2.37.4
Pillow 12.3.0    pytest 9.1.1     PyYAML 6.0.3
```

Deliberately **not** installed: `torch`, `transformers`, `librosa`, `opencv`. Rationale in
`docs/MODEL_LICENSING.md` — Tier-2/Tier-3 model evaluation is an offline research activity and
its absence must be reported as `NOT RUN`, never simulated.

## A5. What this audit forbids

1. No claim that any component "already existed". Everything is new.
2. No historical Nifty-50 constituent list may be asserted — none was found in any local or
   licence-clear source. See `docs/LIMITATIONS.md` L-01.
3. No image/audio/video corpus exists locally. Those modalities must be built against
   real files the user supplies or open-licensed data — never against invented media.
4. The Node-absent finding may not be papered over.
