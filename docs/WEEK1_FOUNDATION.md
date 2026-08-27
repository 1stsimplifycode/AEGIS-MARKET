# Week 1 — the market intelligence foundation

What the seven Week 1 criteria ask for, what this repository now does, and — the part
that matters most — what it still cannot do and why.

Everything below is reproducible from the repository:

```bat
python -m research.reference.acquire --years 2005:2026   REM download, with provenance
python scripts/build_week1_foundation.py                 REM derive every artifact
python -m pytest tests/week1 -q                          REM assert all seven criteria
python -m research.reference.registry                    REM the C7 delivery report
```

---

## The rule everything here follows

A value is only worth what its source is worth, so every value carries a **basis**:

| Basis | Meaning |
|---|---|
| `EXCHANGE_PUBLISHED` | Read verbatim from a file NSE published. |
| `DERIVED_FROM_EXCHANGE_DATA` | Computed from exchange files by a documented derivation. |
| `OBSERVED_IN_DATA` | Behaviour of the data, not a statement by the exchange. |
| `PROJECT_ASSUMPTION` | A choice this project made. **Never** displayed as a market rule. |

Nothing is defaulted. An input NSE does not publish is reported as unavailable, with the
URLs that were tried and the status each returned. That is why the C7 verdict below is
not a pass: closing it honestly needs data that could not be obtained, and a plausible
substitute would be worse than the gap.

---

## C1 — bitemporal store

Every record carries when it *happened* and when it *became knowable*.

- `research/core/contracts.py` — `Provenance` with `event_time`, `knowledge_time`,
  `publication_time`, `retrieval_time`; raises `LeakageError` if knowledge precedes event.
- `data/panel/cash_panel.parquet` — 8,399,065 rows, both stamps, zero nulls, invariant
  holds on every row.
- `data/panel/multimodal_dataset.parquet` — `decision_time` + `knowledge_cutoff`.
- `data/panel/text_corpus.parquet` — 300,508 documents, stamped by
  `scripts/stamp_text_corpus.py`, which refuses to write unless the content fingerprint of
  the preserved columns is unchanged. The documents are synthetic (L-04), so their stamps
  are a declared generator convention, not an observation.

## C2 — point-in-time read path

`research/data/pit.py` is the only way Week 1 reads history.

`AsOf` carries a decision time and a knowledge cutoff, and refuses a cutoff after the
decision. `as_of_frame` applies **both** bounds and **raises** on a frame with no
knowledge-time column — a knowledge-blind read cannot silently degrade into a date filter,
because that degradation is the bug.

`scripts/stages/live.py::slice_frame` — the production adapter path — now takes an `asof`
and applies it. Frames legitimately outside the market-history contract are exempt **by
name** in `NON_BITEMPORAL_FRAMES`, with a reason each; a test asserts that list does not
grow silently.

`get_evidence` is no longer test-only: `pit.evidence_for_instrument` routes the product's
instrument view through it, and `assert_same_semantics` proves the columnar and
record-level paths return identical rows over randomised cutoffs.

## C3 — validation quarantine

`research/data/quarantine.py`. Invalid records are written to `data/quarantine/` with the
original record, a reason code from a closed vocabulary, the source file, the identifiers
and the validation instant. Nothing is repaired.

Wired into `research/data/nse_bhavcopy.py`: unparseable files, null/non-positive closes,
inverted high-low, out-of-range closes, duplicate keys and bitemporal violations all land
there instead of being filtered away.

**An honest finding:** NSE's cash bhavcopy is clean. Across the full 7,861-file archive
there are zero unreadable or unknown-layout files, and a 178-file structural sample
produced zero rejects. The mechanism is therefore proven against deliberately malformed
records; the pipeline now *knows* the archive is clean instead of dropping rows nobody
counted. Out-of-scope series (SME, government bonds) are counted as scope exclusions, not
quarantined — a valid record of something this study is not about is not an invalid record.

## C4 — survivorship-free universe

Retention was already real; what was missing was an explicit statement of what happened.

`research/reference/lifecycle.py` gives every one of the 4,487 securities the panel has
ever seen a state: **2,376 ACTIVE**, **2,072 NO_LONGER_LISTED**, **39
LISTED_NOT_TRADING**. 89 of them were universe members and are gone from the live tape;
they keep their rows and their historical membership.

States are named for what the evidence supports. A security absent from NSE's current
roster is `NO_LONGER_LISTED`, not `DELISTED`, because a symbol rename is indistinguishable
from a delisting here. **`delisted_on` and `suspended_on` are null for every row** — NSE
publishes no open list, and deriving a date from the last observed session would state as
fact something only bounded by observation.

One genuinely historical surveillance fact *is* available and is surfaced: the bhavcopy's
`BE` series code marks the trade-for-trade segment, per session, across the archive.

## C5 — corporate actions and divisor reconciliation

**41,643 corporate actions, 2005–2026**, from NSE's own feed, parsed into price factors and
reconciled against the price series.

A measurement that was checked and found false, recorded so it is not repeated: **NSE does
not restate `prev_close` on ex-dates.** There is no exchange-published adjustment factor to
read off, so the reconciliation is a residual test — applying the announced factor must
turn an impossible one-day move into an ordinary one. On the **1,030 corroborated
price-affecting actions** the median |raw return| of **51.5%** becomes **3.3%**.

`research/market/index_construction.py` maintains a divisor across corporate actions and
rebalances. Over the full history the reconciled index has **zero** sessions with a daily
move above 25%; the unreconciled one has **12**. Max |daily log return| falls from
**0.5066** to **0.1701**.

The worked example in the test suite is real and named: **RELIANCE, bonus 1:1, ex-date
2024-10-28**, from `data/reference/corporate_actions.json`.

This index is **not** the NIFTY 50 and is never labelled as one — NSE Indices' free-float
factors and capping rules are not published openly and are not reconstructed.

## C6 — log return convention

`research/market/returns.py` is the single definition: `r_t = ln(P_t / P_{t-1})`.

Corporate actions are divided out *before* the log. `attach_log_returns` pairs each close
with the bhavcopy's own `prev_close`, so a gap in the panel cannot manufacture a return
across it.

Enforcement is programmatic: `tests/week1/test_c6_log_returns.py` reads the source of every
foundation module and fails if one computes a return with `pct_change` or converts back to
simple returns.

The frozen `ret_1d`/`ret_5d`/`ret_21d` columns that trained models already consume are
*simple* returns. They are left untouched and named in `LEGACY_SIMPLE_RETURN_COLUMNS`;
silently redefining an input that existing artifacts depend on would corrupt results this
change has no business touching. New work reads `logret_1d/5d/21d`.

## C7 — finance inputs

**8 of 12 delivered, 3 fully satisfying. This criterion does not pass.**

| Input | State | Source |
|---|---|---|
| Index composition | PARTIAL | `ind_nifty50list.csv` — current only; no PIT history published |
| Index review cycle | **OBTAINED** | Methodology PDF, quoted: *"The review of Nifty 50 is undertaken semi-annually…"* (p. 21) |
| Corporate actions | **OBTAINED** | 41,643 records, 2005–2026 |
| Ex-date conventions | **OBTAINED** | `exDate`/`recDate` per action |
| Delisting | PARTIAL | Listing roster gives "still listed"; no delisting dates or reasons |
| Suspension | **UNAVAILABLE** | Every endpoint 404/503 |
| ASM / GSM | PARTIAL | Current lists only; no historical membership |
| Circuit bands | PARTIAL | `sec_list.csv` `Band` column — current snapshot only |
| Settlement cycle | **UNAVAILABLE** | Endpoint returns "No Data Found" |
| Market timings | PARTIAL | Holiday calendar obtained; **no session clock times published** |
| Auction windows | **UNAVAILABLE** | No endpoint publishes them |
| Block-deal windows | **UNAVAILABLE** | Endpoint returns trades, not the window |

Several "PARTIAL" entries are partial for the same reason: the artifact is a **current
snapshot**, and a bitemporal system needs history. A 2026 circuit band cannot answer what
band applied in 2015.

### What was removed

`MAX_PRICE_DEVIATION = 0.20` in `backend/trading.py` is no longer presented as a market
rule. It is labelled **"Platform guard (not an exchange rule)"**, and the exchange's actual
band is reported beside it from `sec_list.csv` — or reported as not available, never
defaulted to the guard's value.

`CLOSE_IST = 15:30` and `PUBLISH_IST = 18:00` are declared `PROJECT_ASSUMPTION` in
`research/reference/sessions.py` and rendered as such. The publication instant is the more
consequential of the two: the knowledge boundary of the entire panel rests on it, and no
acquired artifact states it.

---

## Licensing

NSE publishes these reports for public download; that is not permission to redistribute.
The acquired payloads are gitignored. `data/reference/reference_manifest.json` — provider,
URL, licence, retrieval instant, checksum, byte count, temporal coverage, and the HTTP
status of every attempt — **is** committed, so the provenance is auditable without the
files.
