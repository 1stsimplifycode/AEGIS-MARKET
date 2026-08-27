# NIFTY 50 and the index data layer

The NIFTY 50 is the primary market domain of this project. It is a real, published
benchmark with its own identifier, its own data layer and its own page — not a proxy, not
a reconstruction, and not a rename of anything else this repository already had.

---

## 1. Two entities that are never interchangeable

| | `NIFTY50` | `LIQUIDITY_PROXY_TOP50` |
|---|---|---|
| Type | `INDEX` | `UNIVERSE_PROXY` |
| What it is | India's large-cap benchmark, maintained by NSE Indices | Fifty instruments this project selects by trailing median traded value |
| What it has | A published level | Members, and no level at all |
| Used for | Market context, performance, volatility, drawdown | A point-in-time sampling frame for the research programme |
| Displayed as | "NIFTY 50" | "Point-in-time liquidity proxy" |

`research/data/instruments.py` carries the type on the identifier, and
`assert_type` / `assert_not_interchangeable` raise rather than allowing one to be passed
where the other is expected. `tests/unit/test_index_entity.py` asserts the separation from
both directions, including a scan of every `.tsx` file for copy that describes the proxy as
the index.

L-01 is unchanged and still true: the liquidity proxy is not index membership. What changed
is that the product no longer *needs* it to stand in for one.

## 2. Where the level comes from

NSE's daily derivatives bhavcopy, in the UDiFF format adopted in July 2024, carries
`UndrlygPric` on every contract — the closing level of the instrument the contract is
written on. Every NIFTY index derivative on a session quotes the same value, and that value
is the NIFTY 50 close as NSE published it.

```
NSE derivatives bhavcopy (read in place, never committed)
  → research/data/nse_index.py        extract + validate
  → scripts/build_index_panel.py      derive + quality report
  → data/panel/index_panel.parquet
  → scripts/stages/product_views.py   read models
  → backend/product.py                /api/indices/NIFTY50
  → app/markets/nifty-50              product and research views
```

| Field | Value |
|---|---|
| Source | NSE daily derivatives bhavcopy (UDiFF full format) |
| Location | `https://www.nseindia.com/all-reports-derivatives` |
| Field read | `UndrlygPric` on an index derivative |
| Frequency | Daily, end of session |
| `access_type` | `PUBLIC` |
| `redistribution_status` | `RESTRICTED` |
| Coverage | 521 sessions, 2024-07-08 → 2026-08-14 |
| Ingestion version | `nse-index-v1` |

**Public is not the same as redistributable.** NSE publishes these reports for anyone to
download; that is not a licence to ship them inside a repository. So this is an *ingestion
adapter*: it reads the archive in place, writes a derived series, and a test asserts no raw
bhavcopy is ever committed. Index names and levels are the property of NSE Indices Limited
and are used here for research.

## 3. What is deliberately not done

Three shortcuts would each produce a number that is not the NIFTY 50, and each is refused
in code rather than in a comment:

- **Futures are not the index.** NIFTY futures are in the same file with full OHLC. They
  carry basis and expiry effects. `usecols` never reads a contract price, and a test
  asserts it.
- **Constituents are not combined into a level.** Reproducing the index from the fifty
  closes requires the official free-float factors, capping and divisor, none of which are
  in this archive. No reconstruction is attempted.
- **History is not back-filled.** Before 2024-07-08 the bhavcopy has no underlying-price
  column, so the series starts there. The page says why rather than letting a chart imply
  the index began in 2024.

A session whose derivatives quote more than one distinct underlying value is skipped, not
averaged: a level nobody could reproduce is worse than a gap.

## 4. What the source does not carry

These travel with the data and are shown on the page beside what *is* available:

| Field | Why it is absent |
|---|---|
| `open`, `high`, `low` | The report records only the underlying's close. An index has no published intraday range here. |
| `volume` | An index is not traded and has no volume of its own. |
| `constituents` | Membership is published separately by NSE Indices and is not in this archive. |

Membership being absent has a consequence the page states: sector composition, constituent
performance, contribution analysis and index-restricted breadth are **not computable**
here. Breadth is shown across every NSE instrument that traded and labelled as such. Two
wrong answers are named and refused: the liquidity proxy is a sampling frame rather than
membership, and today's members applied to past sessions would manufacture survivorship
bias in every backward-looking number.

## 5. Derived series

All from the close, all documented:

| Series | Definition |
|---|---|
| `return_pct` | Session-over-session change in the close. |
| `log_return` | Natural log of the close ratio. |
| `volatility_20d` | Sample standard deviation of daily log returns over 20 sessions, annualised by √252. |
| `drawdown` | Close over the running maximum *within the ingested window*, minus one. Not an all-time drawdown. |
| `high_52w` / `low_52w` | Rolling 252-session extremes, expanding while fewer sessions exist. |

## 6. Recency

The product distinguishes four states and this data is the third:

`LIVE` · `DELAYED` · **`LATEST_AVAILABLE_SESSION`** · `HISTORICAL`

Every surface showing the level says "Latest available session" with the date. There is no
real-time feed and nothing implies one.

## 7. Data quality

`scripts/build_index_panel.py` writes, on every run:

```
outputs/data_quality/nifty50_data_quality_report.json
outputs/data_quality/nifty50_data_quality.csv
```

Checked by name: duplicate sessions · missing business days · null closes · non-positive
closes · unexpected session-over-session moves (>10%, flagged never filtered) · a single
unambiguous level per session per index · trading-date normalisation without timezone
conversion.

Current result for NIFTY 50: **521 sessions, 0 duplicates, 0 nulls, 0 non-positive, 0
anomalous moves.** Missing business days are reported and expected to be non-zero — NSE
observes roughly a dozen trading holidays a year — so what matters is a change in the
count, not the count.

## 8. Two levels of evidence

The index has no evidence of its own, and the product says so in the shape of the page
rather than in a footnote:

| Level | What it is | Where it appears |
|---|---|---|
| **Market context** | Financial text and panel sessions that fall inside the index window. 57,085 documents across 165 instruments, 2,728 instrument-sessions. Evidence *about the market over the same period*. | The NIFTY 50 page, beside the chart |
| **Instrument evidence** | The model's assessments, which are instrument-level and cover their own evaluation window. | Instrument pages, Analysis |

No document, image or clip is attributed to the index. Whether an instrument is one of the
fifty is exactly the fact the data does not carry, so an index-level media association
would be one nobody could check.

**The two windows do not overlap.** The index series covers 2024-07-08 → 2026-08-14; the
model's evaluation window covers 2022-01-03 → 2023-12-29. They share **0 sessions**. That
is a property of the data, and `figIDX05_evidence.png` draws it rather than describing it —
the shaded evaluation window sits entirely to the left of the index series.

## 9. Evidence alignment (L-25)

The index window and the model's evaluation window **share zero sessions**. That is not a
warning string anywhere in this system — it is a computed value, recomputed on every
request from the sessions each source holds.

`research/data/alignment.py` takes two coverage windows and returns a status:

| Status | When |
|---|---|
| `ALIGNED` | shared sessions ≥ 80% of the shorter window, and ≥ 5 of them |
| `PARTIAL` | they meet, but over less than that |
| `NOT_ALIGNED` | no shared session |
| `UNKNOWN` | one source holds no sessions, so the question has no answer yet |

Measured today across the pairs the interface presents:

| Pair | Overlap | Ratio | Status |
|---|---:|---:|---|
| NIFTY 50 × model evidence | 0 | 0.000 | `NOT_ALIGNED` |
| NIFTY 50 × text corpus | 521 | 1.000 | `ALIGNED` |
| NIFTY 50 × multimodal panel | 507 | 0.973 | `ALIGNED` |
| Model evidence × text corpus | 493 | 1.000 | `ALIGNED` |

The gap is **specific**. The benchmark is aligned with the evidence it actually overlaps;
only the stored model evaluation is out of reach. Reporting everything as unaligned would
be its own error.

**The refusal is enforceable.** `require_alignment` raises `NotTemporallyAligned`; the
Scenario Lab consults the same gate and declines to offer a combined scenario, saying how
many sessions such a scenario would cover. Side-by-side presentation stays permitted in
every state — showing two things is not claiming a relationship between them.

**Nothing is hardcoded.** A test asserts that no date literal appears in the alignment
module, and another feeds it a series reaching back over the evaluation window and checks
the status becomes `ALIGNED` with no code change. The day an overlapping source is
ingested, the product starts reporting the relationship on its own.

Recorded as **L-25** in the limitations registry — category `DATA`, status `MEASURED`,
with the claims it invalidates, two open research questions, a designed experiment
(`EXP-L25-1`), and forbidden phrasings wired into the claim guard (`nifty 50 risk score`,
`index-level risk signal`, …). Surfaced at `/research/alignment`, on the NIFTY 50 page, on
every weekly page and in the Scenario Lab.

```
outputs/alignment/evidence_alignment.json    the matrix, with every pair's arithmetic
outputs/alignment/evidence_alignment.csv     the same, flat
outputs/alignment/figures/figALN01_windows   every source's coverage on one timeline
```

## 10. What the product does with it

The alignment layer is consulted, never reimplemented. `evidence_summary` shapes its
per-pair verdicts into cards; the interface renders them and decides nothing.

**Product mode** — a mark, a verdict, a sentence:

```
Evidence available
✓ Market text    ✓ Multimodal evidence    ○ Historical model evidence   [Explore →]
```

On the NIFTY 50 page each becomes a card: source, period, shared sessions, verdict, and
one action — *View evidence* where aligned, *Why?* where not.

**Research mode** — the same cards gain the coverage ratio, both windows, the overlap
range and whether combined analysis is permitted.

**Decided per source, never per page.** The stored model evaluation not overlapping the
index says nothing about the text corpus, and the Scenario Lab reflects that:

| Source | Verdict |
|---|---|
| Market text | ✓ Aligned — can be combined with the benchmark |
| Multimodal evidence | ✓ Aligned — can be combined with the benchmark |
| Historical model evidence | ○ Not aligned — cannot be combined with the benchmark |

**Available is not used.** Alignment answers *does this source cover the same sessions*.
It does not answer *did an experiment use them together* — and the answer to the second is
currently no: **0 experiments** in this project take the index as an input. The disclosure
on the evidence section says so in both registers, because "evidence is available" and
"evidence was used" are different claims.

Endpoint: `GET /api/evidence/{index_id}`. Components: `EvidenceStatusBadge`,
`EvidenceAlignmentCard`, `EvidenceCoverageSummary`, `EvidenceStrip`, `EvidenceSection` —
one family, used on the home page, the NIFTY 50 page, all sixteen weekly pages and the
Scenario Lab, so no two surfaces can disagree.

Guarded by `tests/unit/test_evidence_product.py`: no session count, coverage ratio or
assigned status may appear in the interface (a lookbehind distinguishes `=== 'ALIGNED'`,
which reads the backend's answer, from `= 'ALIGNED'`, which would invent one), every
surface showing evidence must call `getEvidenceSummary`, and the Scenario Lab must iterate
the sources rather than apply one verdict to all.

## 11. Research artifacts

`scripts/generate_index_artifacts.py` writes to `outputs/index/`:

| Artifact | Contents |
|---|---|
| `index_statistics.json` | Level, daily-change distribution (mean, sd, skew, excess kurtosis), volatility, drawdown, coverage, provenance |
| `nifty50_returns.csv` | Per-session level, change, log return, rolling volatility, drawdown, 52-week extremes |
| `figIDX01_level` | The closing level over 521 sessions |
| `figIDX02_volatility` | Rolling 20-session annualised volatility |
| `figIDX03_drawdown` | Drawdown from the running maximum |
| `figIDX04_returns` | Daily-change distribution |
| `figIDX05_evidence` | The index window against this project's evidence volume and evaluation window |

Measured over the ingested series: total change **+0.19%**, worst drawdown **−15.77%**,
current 20-session annualised volatility **9.5%**.

## 12. Where it appears

| Surface | What it shows |
|---|---|
| Home | The benchmark card: level, session move, 52-week range, volatility, drawdown |
| `/markets/nifty-50` | Product: performance, breadth, constituents state. Research: source, licence, coverage, methodology, unavailable fields, quality |
| Primary navigation | A destination of its own, ahead of the instrument list |
| Search | `NIFTY`, `NIFTY 50`, `NIFTY50`, `^NSEI`, `NSEI` all resolve to the index, and none resolve to the proxy |
| Weekly pages | A market-context strip above every week, so the sixteen slices share one domain |
| Watchlist | Followable alongside instruments, with its kind recorded |
| Scenario Lab | Market context above the scenarios, with the index level marked as an observation and the scenarios as model output |
| `/api/indices`, `/api/indices/{id}`, `/api/indices/{id}/series`, `/api/indices/{id}/context` | The backend read models, behind the same allowlisted proxy as everything else |

## 13. Rebuilding it

```bash
export AEGIS_NSE_ARCHIVE=/path/to/nse/raw     # directory containing cm/ and fo/
python scripts/build_index_panel.py           # ~90s  -> index panel + quality report
python scripts/generate_index_artifacts.py    # ~12s  -> statistics, CSV, five figures
python scripts/build_alignment_report.py      # ~15s  -> the alignment matrix + figure
python scripts/export_product.py              # ~130s -> public/data/market.json
```

Without the archive the index is **unavailable**, and every surface says so with the
command that would fix it. Nothing is substituted for it.
