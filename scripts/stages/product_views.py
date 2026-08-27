"""Read models for the product experience.

The product asks different questions from the research programme. "What is this
instrument doing, and how confident is the system about it" is not one of the sixteen
weekly modules; it is a *view* over what those modules already produced. This file builds
those views and defines no statistic of its own: every number here is either read from a
panel column or is an arithmetic summary of rows that were computed elsewhere.

Two provenances travel separately, and the interface keeps them apart because they are
not the same kind of fact:

``market``  the real NSE cash panel, as of its last session. Prices, volumes and the
            session-over-session change are observations, not model output.
``risk``    the scored panel a fitted model produced on the evaluation split. It is a
            stored experiment result, replayed. Nothing is scored on request, because
            scoring requires the fitted model and this layer does not fit one.

Presenting the second as though it were as current as the first is the failure this
separation exists to prevent: a price from this morning beside a risk score from an
experiment reads as a live risk score unless the response says otherwise, and it says
otherwise.
"""
from __future__ import annotations

import functools

import numpy as np
import pandas as pd

from research.core import paths
from scripts.stages import live

#: How many sessions the product's price view shows by default.
DEFAULT_WINDOW = 120

#: Instruments returned by a search that matches nothing in particular.
SEARCH_LIMIT = 12

#: The lifecycle states the scored panel carries, with the product's wording for each.
#: The labels match `lib/types.ts` so a state reads the same in both experiences: this
#: renames nothing, it only chooses which of the two names is shown first. The `tone`
#: drives colour, and is a presentation decision rather than a claim about severity.
STATE_COPY: dict[str, dict[str, str]] = {
    "NORMAL": {"label": "Normal", "tone": "calm",
               "meaning": "Nothing in the evidence stood out on the sessions scored."},
    "EARLY_WARNING": {"label": "Watch", "tone": "watch",
                      "meaning": "Evidence rose above the background but has not "
                                 "persisted."},
    "EMERGING": {"label": "Emerging", "tone": "watch",
                 "meaning": "Evidence persisted long enough to open a window."},
    "ACTIVE": {"label": "Active", "tone": "elevated",
               "meaning": "The window is open and the evidence is steady."},
    "ESCALATING": {"label": "Escalating", "tone": "high",
                   "meaning": "Evidence is strengthening session over session."},
    "PEAK": {"label": "Peak", "tone": "high",
             "meaning": "The strongest point of this window."},
    "RESOLVING": {"label": "Resolving", "tone": "watch",
                  "meaning": "Evidence is receding from its strongest point."},
    "RESOLVED": {"label": "Resolved", "tone": "calm",
                 "meaning": "The window has closed and evidence is back in the "
                            "ordinary range."},
}

MODALITY_COPY: dict[str, str] = {
    "text": "Financial text",
    "image": "Chart imagery",
    "audio": "Sonified market audio",
    "video": "Rendered video",
    "market": "Price and volume",
    "microstructure": "Liquidity proxies",
    "regime": "Market regime",
    "propagation": "Cross-instrument movement",
}


# ------------------------------------------------------------------- loading ----

@functools.lru_cache(maxsize=1)
def scored() -> pd.DataFrame:
    """The stored per-instrument scores, with their risk state."""
    frame = live.per_row("FULL")
    return frame if frame is not None else pd.DataFrame()


@functools.lru_cache(maxsize=1)
def _last_session() -> pd.Timestamp:
    return live.cash_panel()["date"].max()


@functools.lru_cache(maxsize=1)
def _latest_universe() -> pd.DataFrame:
    """The most recent point-in-time universe reconstitution."""
    members = live.universe()
    latest = members["rebalance_date"].max()
    return members[members["rebalance_date"] == latest].sort_values("rank")


def _run_stamp() -> dict:
    """Which stored run the risk numbers came from."""
    log = paths.REPO_ROOT / "logs" / "stats" / "stats_14.jsonl"
    stamp = {"source": "research_artifacts/experiments/per_row_FULL.parquet"}
    if log.exists():
        lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if lines:
            import json
            try:
                last = json.loads(lines[-1])
                stamp["run_at"] = last.get("ts")
                stamp["git_commit"] = last.get("git_commit")
            except ValueError:
                pass
    return stamp


# ------------------------------------------------------------------- helpers ----

def _session_change(frame: pd.DataFrame) -> pd.DataFrame:
    """Close-to-previous-close change, from the panel's own previous close."""
    out = frame.copy()
    prev = pd.to_numeric(out.get("prev_close"), errors="coerce")
    close = pd.to_numeric(out["close"], errors="coerce")
    out["change"] = close - prev
    out["change_pct"] = np.where(prev > 0, (close - prev) / prev, np.nan)
    return out


def _num(value) -> float | None:
    """A float, or None. Never a NaN that JSON turns into an unparseable token."""
    v = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(v) else float(v)


def _recency(full: pd.DataFrame, window: pd.DataFrame) -> dict:
    """Say plainly how old the data is, and keep that separate from how far back it goes.

    Two different facts get confused on a market page. *Coverage* is where the history
    starts -- 2005 here -- and *recency* is when the most recent observation happened.
    Showing only the first invites a reader to assume the second, so both are emitted with
    distinct names and the staleness is computed rather than implied.

    ``latest_session`` is whatever the panel actually contains. If that is older than
    today, the page must say "latest available", not "latest": the difference between
    those two phrasings is the difference between reporting data and overstating it.
    """
    dates = pd.to_datetime(full["date"]).dt.normalize()
    latest = dates.max()
    prior = dates[dates < latest]
    today = pd.Timestamp.now().normalize()
    stale_days = int((today - latest).days)
    w = pd.to_datetime(window["date"]).dt.normalize()
    return {
        "latest_session": str(latest.date()),
        "previous_session": str(prior.max().date()) if not prior.empty else None,
        "window_from": str(w.min().date()),
        "window_to": str(w.max().date()),
        "window_sessions": int(len(window)),
        "coverage_from": str(dates.min().date()),
        "coverage_sessions": int(dates.nunique()),
        "checked_at": str(today.date()),
        "days_since_latest_session": stale_days,
        "is_current_as_of_today": bool(stale_days <= 0),
        "recency_label": (
            "Latest market data" if stale_days <= 0 else "Latest available market data"),
        "recency_note": (
            "The most recent session in the panel is the most recent trading day."
            if stale_days <= 0 else
            "No session later than %s has been ingested. The panel is %d day%s behind "
            "today; nothing newer is claimed."
            % (str(latest.date()), stale_days, "" if stale_days == 1 else "s")),
    }


def _announcements(symbol: str, limit: int = 25) -> dict:
    """Recent exchange announcements for one issuer, with real dissemination instants.

    The subject strings are NSE's own and are stored verbatim. Where the
    corporate-announcements feed covers a record, its dissemination timestamp is attached;
    where it does not, the row carries the session that published it and says the time is
    unavailable rather than substituting a session close.

    No impact or sentiment is assigned. The project has no model that scores an individual
    announcement, and inventing a badge here would put a claim on the page that nothing
    behind it supports.
    """
    try:
        from research.reference import announcements as an
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "why": "Announcement corpus unavailable: %s" % exc}

    try:
        corpus = an.load()
    except FileNotFoundError:
        return {"available": False,
                "why": "No announcement corpus has been acquired."}

    sym = str(symbol or "").upper().strip()
    rows = corpus[corpus["symbol"].astype(str).str.upper() == sym]
    if rows.empty:
        return {"available": False,
                "why": "No announcements for %s in the acquired corpus." % sym,
                "corpus_coverage": "%s .. %s" % (
                    pd.Timestamp(corpus["session"].min()).date(),
                    pd.Timestamp(corpus["session"].max()).date())}

    stamps = {}
    try:
        from research.reference import announcement_timestamps as at
        ts = at.load()
        ts = ts[ts["symbol"].astype(str).str.upper() == sym]
        for r in ts.itertuples(index=False):
            key = (str(pd.Timestamp(r.session).date()), str(r.subject)[:80])
            stamps[key] = str(r.disseminated_at)
    except (FileNotFoundError, Exception):  # noqa: BLE001
        stamps = {}

    rows = rows.sort_values("session", ascending=False).head(limit)
    items = []
    for r in rows.itertuples(index=False):
        session = str(pd.Timestamp(r.session).date())
        subject = str(getattr(r, "subject", "") or "").strip()
        body = str(getattr(r, "body", "") or "").strip()
        layout = str(getattr(r, "layout", "") or "")
        # Older bundle lines splice the subject into the start of the body rather than
        # publishing it separately. The parser records that as `body_only` and does not
        # repair the splice, so the leading text of the body is the only title there is.
        # It is shown as such, flagged, rather than left blank or invented.
        title = subject or " ".join(body.split()[:12])
        items.append({
            "session": session,
            "subject": subject or None,
            "title": title,
            "title_from_body": not subject,
            "layout": layout,
            "body": body[:400],
            "disseminated_at": stamps.get((session, subject[:80])) if subject else None,
            "publication_time_available": bool(
                subject and (session, subject[:80]) in stamps),
            "source": "NSE daily PR bundle (an member)",
        })

    return {
        "available": True,
        "count": int(len(rows)),
        "total_for_symbol": int(
            (corpus["symbol"].astype(str).str.upper() == sym).sum()),
        "items": items,
        "corpus_coverage": "%s .. %s" % (
            pd.Timestamp(corpus["session"].min()).date(),
            pd.Timestamp(corpus["session"].max()).date()),
        "basis": "EXCHANGE_PUBLISHED",
        "impact_scored": False,
        "impact_note": ("No impact or sentiment is attached to an individual "
                        "announcement: no model in this project scores one."),
    }


def _risk_block(symbol: str) -> dict:
    """Everything the scored panel knows about one instrument."""
    frame = scored()
    if frame.empty or "symbol" not in frame.columns:
        return {"available": False,
                "why": "No scored panel is present; run the experiment pipeline."}
    rows = frame[frame["symbol"].str.upper() == symbol.upper()].sort_values("date")
    if rows.empty:
        return {"available": False,
                "why": "This instrument is outside the scored evaluation sample, so no "
                       "risk signal exists for it. That is a property of the sample, "
                       "not a statement that the instrument is unremarkable."}

    last = rows.iloc[-1]
    state = str(last.get("risk_state", "NORMAL"))
    modalities = []
    for name in MODALITY_COPY:
        column = "contrib_%s" % name
        weight = "weight_%s" % name
        if column not in rows.columns:
            continue
        contribution = float(pd.to_numeric(rows[column], errors="coerce").mean())
        modalities.append({
            "modality": name,
            "label": MODALITY_COPY[name],
            "contribution": contribution,
            "weight": float(pd.to_numeric(rows[weight], errors="coerce").mean())
            if weight in rows.columns else None,
        })
    total = sum(abs(m["contribution"]) for m in modalities) or 1.0
    for m in modalities:
        m["share"] = abs(m["contribution"]) / total
    modalities.sort(key=lambda m: m["share"], reverse=True)

    series = [
        {"date": str(pd.Timestamp(r.date).date()),
         "risk": float(r.integrity_risk),
         "uncertainty": float(r.uncertainty)}
        for r in rows.itertuples(index=False)
    ]
    return {
        "available": True,
        "state": state,
        "state_label": STATE_COPY.get(state, {}).get("label", state.title()),
        "state_tone": STATE_COPY.get(state, {}).get("tone", "calm"),
        "state_meaning": STATE_COPY.get(state, {}).get("meaning", ""),
        "score": float(last["integrity_risk"]),
        "uncertainty": float(last["uncertainty"]),
        "coverage": float(last["coverage"]) if "coverage" in rows.columns else None,
        "sessions_scored": int(len(rows)),
        "scored_from": str(pd.Timestamp(rows["date"].min()).date()),
        "scored_to": str(pd.Timestamp(rows["date"].max()).date()),
        "modalities": modalities,
        "series": series,
        "provenance": _run_stamp(),
    }


def _observations(risk: dict, market: dict) -> list[str]:
    """Short, factual sentences a reader can act on without a glossary.

    Deliberately few and deliberately plain. Each one names what was observed and, where
    it matters, what bounds it; none of them names a model, a metric or an experiment,
    because those belong to the layer underneath this one.
    """
    out: list[str] = []
    if risk.get("available"):
        top = risk["modalities"][0] if risk["modalities"] else None
        if top:
            out.append("%s carried most of the signal on the sessions scored, at %.0f%% "
                       "of the total contribution."
                       % (top["label"], 100 * top["share"]))
        if risk["uncertainty"] > 0.5:
            out.append("The modalities disagreed on these sessions, so the signal is "
                       "less settled than the number alone suggests.")
        elif risk["uncertainty"] < 0.2:
            out.append("The modalities largely agreed on these sessions.")
        if risk.get("coverage") is not None and risk["coverage"] < 0.8:
            out.append("Only %.0f%% of the evidence blocks were present, so this reading "
                       "rests on part of the picture."
                       % (100 * risk["coverage"]))
    if market.get("available") and market.get("sessions"):
        out.append("Price history covers %d sessions to %s."
                   % (market["sessions"], market["last_session"]))
    return out


# ------------------------------------------------------------- the read models ----

def market_overview() -> dict:
    """What the market did on its last session, and how the sample is behaving.

    Breadth and turnover are counts over the real panel. The risk mix beside them is the
    distribution of stored risk states, which describes the evaluation sample rather than
    today, and the payload says which is which.
    """
    panel = live.cash_panel()
    last = _last_session()
    day = _session_change(panel[panel["date"] == last])
    changes = day["change_pct"].dropna()

    universe = _latest_universe()
    members = set(universe["symbol"].str.upper())
    tracked = day[day["symbol"].str.upper().isin(members)]
    tracked_changes = tracked["change_pct"].dropna()

    frame = scored()
    mix = []
    if not frame.empty and "risk_state" in frame.columns:
        latest = frame.sort_values("date").groupby("symbol").tail(1)
        counts = latest["risk_state"].value_counts()
        for state, n in counts.items():
            copy = STATE_COPY.get(str(state), {})
            mix.append({"state": str(state),
                        "label": copy.get("label", str(state).title()),
                        "tone": copy.get("tone", "calm"),
                        "instruments": int(n)})
        mix.sort(key=lambda m: m["instruments"], reverse=True)

    return {
        "market": {
            "available": True,
            "last_session": str(last.date()),
            "instruments_traded": int(len(day)),
            "advancing": int((changes > 0).sum()),
            "declining": int((changes < 0).sum()),
            "unchanged": int((changes == 0).sum()),
            "median_change_pct": float(changes.median()) if len(changes) else None,
            "turnover": float(pd.to_numeric(day.get("turnover"),
                                            errors="coerce").sum()),
            "source": "data/panel/cash_panel.parquet",
            "note": "Observed NSE cash-market data for the last session in the panel.",
        },
        "tracked": {
            "name": "Point-in-time liquidity proxy, top 50 by traded value",
            "instruments": int(len(universe)),
            "advancing": int((tracked_changes > 0).sum()),
            "declining": int((tracked_changes < 0).sum()),
            "median_change_pct": float(tracked_changes.median())
            if len(tracked_changes) else None,
            "caveat": "Reconstructed by this project from traded value. It is not the "
                      "Nifty 50 and does not reproduce index membership.",
        },
        "risk_mix": {
            "available": bool(mix),
            "states": mix,
            "instruments": int(sum(m["instruments"] for m in mix)),
            "note": "The distribution of stored risk states across the scored "
                    "evaluation sample. It describes that sample, not this session.",
            "provenance": _run_stamp(),
        },
    }


def instrument(symbol: str, window: int = DEFAULT_WINDOW,
               as_of: str | None = None) -> dict:
    """One instrument, as the product presents it: price, signal, evidence mix.

    The price history is read point-in-time like everything else. With no ``as_of`` the
    cutoff is now, which admits every published session -- but it goes through the same
    bounded read rather than around it, so asking for a past instant needs no separate
    code path and cannot accidentally skip the knowledge bound.
    """
    from research.data import pit

    sym = str(symbol or "").upper().strip()
    panel = live.cash_panel()
    rows = panel[panel["symbol"].str.upper() == sym].sort_values("date")
    if rows.empty:
        return {"found": False, "symbol": sym,
                "why": "No instrument with that symbol is in the panel."}

    asof = pit.AsOf.after_publication(as_of) if as_of else pit.AsOf.latest()
    rows = pit.as_of_frame(rows, asof)
    pit.assert_no_leakage(rows, asof)
    if rows.empty:
        return {"found": False, "symbol": sym,
                "why": "Nothing was knowable about %s at %s." % (sym, asof)}

    tail = _session_change(rows.tail(max(20, min(int(window), 750))))
    last = tail.iloc[-1]
    first_close = float(tail["close"].iloc[0])
    last_close = float(last["close"])

    risk = _risk_block(sym)
    universe = _latest_universe()
    member = universe[universe["symbol"].str.upper() == sym]

    market = {
        "available": True,
        "last_session": str(pd.Timestamp(last["date"]).date()),
        "close": last_close,
        "change": float(last["change"]) if pd.notna(last["change"]) else None,
        "change_pct": float(last["change_pct"]) if pd.notna(last["change_pct"]) else None,
        "window_change_pct": (last_close - first_close) / first_close
        if first_close else None,
        "sessions": int(len(tail)),
        "volume": float(pd.to_numeric(last.get("volume"), errors="coerce")),
        "turnover": float(pd.to_numeric(last.get("turnover"), errors="coerce")),
        "history_from": str(pd.Timestamp(rows["date"].min()).date()),
        # Real OHLC straight off the panel. Nothing is reconstructed from close: a candle
        # whose open and high were invented from the closing price would look like a
        # market observation and would not be one.
        "series": [
            {
                "date": str(pd.Timestamp(r.date).date()),
                "close": float(r.close),
                "open": _num(getattr(r, "open", None)),
                "high": _num(getattr(r, "high", None)),
                "low": _num(getattr(r, "low", None)),
                "volume": _num(getattr(r, "volume", None)),
                "turnover": _num(getattr(r, "turnover", None)),
            }
            for r in tail.itertuples(index=False)
        ],
        "ohlc_source": "data/panel/cash_panel.parquet columns open/high/low/close",
        "ohlc_complete": bool(
            tail[["open", "high", "low", "close"]].notna().all().all()
            if {"open", "high", "low", "close"}.issubset(tail.columns) else False),
        "source": "data/panel/cash_panel.parquet",
    }
    market.update(_recency(rows, tail))

    # Indicators are DERIVED from these closes, not published by the exchange. They are
    # computed over the same window the chart draws so the panels share its x-axis, and
    # they carry their own conventions so a reader can reproduce them.
    from research.market import indicators as ind
    _dates = [str(pd.Timestamp(r.date).date()) for r in tail.itertuples(index=False)]
    _closes = [float(r.close) for r in tail.itertuples(index=False)]
    market["indicators"] = ind.series(_dates, _closes)
    market["direction"] = ind.direction(_dates, _closes, market["change_pct"])

    # The Week 1 market-intelligence foundation: lifecycle state, the corporate actions
    # the exchange announced, the band it actually applies, and what was knowable when.
    # Read live from the same artifacts the C1-C7 tests assert against, so the page
    # cannot show a market fact the research layer would not stand behind.
    from . import week1_foundation as w1
    from . import week2_foundation as w2

    return {
        "found": True,
        "symbol": sym,
        "tracked": bool(len(member)),
        "tracked_rank": int(member["rank"].iloc[0]) if len(member) else None,
        "market": market,
        "risk": risk,
        "foundation": w1.instrument_context(sym),
        # Week 2: realised variance, price impact, arrival dispersion and the liquidity
        # state, each read from the artifacts the C1-C7 suite asserts against.
        "liquidity": w2.instrument_liquidity(sym),
        "observations": _observations(risk, market),
        "announcements": _announcements(sym),
    }


def search(query: str, limit: int = SEARCH_LIMIT) -> dict:
    """Instrument lookup by symbol fragment, ranked by how the market uses them.

    Ranked by traded value rather than alphabetically: someone typing three letters
    wants the instrument those letters most likely mean, and traded value is the closest
    honest proxy for that without a name index this project does not have.
    """
    q = str(query or "").upper().strip()
    universe = _latest_universe()
    panel = live.cash_panel()
    last = _last_session()
    day = _session_change(panel[panel["date"] == last])
    turnover = dict(zip(day["symbol"].str.upper(),
                        pd.to_numeric(day.get("turnover"), errors="coerce").fillna(0.0),
                        strict=False))
    change = dict(zip(day["symbol"].str.upper(), day["change_pct"], strict=False))

    frame = scored()
    scored_symbols: dict[str, str] = {}
    if not frame.empty and "risk_state" in frame.columns:
        latest = frame.sort_values("date").groupby("symbol").tail(1)
        scored_symbols = dict(zip(latest["symbol"].str.upper(),
                                  latest["risk_state"].astype(str), strict=False))

    pool = sorted({*day["symbol"].str.upper()})
    if q:
        starts = [s for s in pool if s.startswith(q)]
        contains = [s for s in pool if q in s and not s.startswith(q)]
        matches = starts + contains
    else:
        matches = sorted(universe["symbol"].str.upper())

    matches.sort(key=lambda s: (not s.startswith(q), -turnover.get(s, 0.0)))
    members = set(universe["symbol"].str.upper())

    results = []
    for s in matches[:max(1, min(int(limit), 50))]:
        state = scored_symbols.get(s)
        results.append({
            "symbol": s,
            "tracked": s in members,
            "analysed": state is not None,
            "state": state,
            "state_label": STATE_COPY.get(state or "", {}).get("label"),
            "state_tone": STATE_COPY.get(state or "", {}).get("tone"),
            "change_pct": float(change.get(s)) if pd.notna(change.get(s, np.nan))
            else None,
            "turnover": float(turnover.get(s, 0.0)),
        })
    return {
        "query": q,
        "matches": int(len(matches)),
        "results": results,
        "note": "Ranked by traded value on the last session, exact prefixes first.",
    }


def attention(limit: int = 8) -> dict:
    """Instruments whose stored signal stands out, for the home page's second fold.

    Not a list to act on and not ordered by anything a reader should read as severity
    beyond what it says: these are the scored instruments whose last stored state was
    something other than normal, most recently scored first.
    """
    frame = scored()
    if frame.empty:
        return {"available": False, "rows": [],
                "why": "No scored panel is present."}
    latest = frame.sort_values("date").groupby("symbol").tail(1)
    standout = latest[latest["risk_state"].astype(str) != "NORMAL"]
    standout = standout.sort_values(["integrity_risk"], ascending=False)

    rows = []
    for r in standout.head(max(1, min(int(limit), 40))).itertuples(index=False):
        state = str(r.risk_state)
        rows.append({
            "symbol": str(r.symbol),
            "state": state,
            "state_label": STATE_COPY.get(state, {}).get("label", state.title()),
            "state_tone": STATE_COPY.get(state, {}).get("tone", "calm"),
            "score": float(r.integrity_risk),
            "uncertainty": float(r.uncertainty),
            "date": str(pd.Timestamp(r.date).date()),
        })
    return {
        "available": True,
        "rows": rows,
        "total": int(len(standout)),
        "scored": int(len(latest)),
        "note": "Instruments whose last stored assessment was not Normal. Read as "
                "'worth looking at', not as a ranking of severity.",
        "provenance": _run_stamp(),
    }


# ------------------------------------------------------------------- indices ----
#
# An index is a different object from an equity and from the liquidity proxy, and these
# read models keep it that way. `index_overview` answers "what is the benchmark doing";
# `index_detail` answers "and what does its history look like". Neither of them touches
# the proxy, and the proxy's read models never produce a level.


@functools.lru_cache(maxsize=1)
def index_panel() -> pd.DataFrame:
    """The ingested index levels, or an empty frame when none have been built."""
    path = paths.PANEL / "index_panel.parquet"
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def _index_unavailable(index_id: str) -> dict:
    from research.data import nse_index as ix

    spec = ix.INDEX_REGISTRY.get(index_id)
    return {
        "available": False,
        "instrument_id": index_id,
        "instrument_type": "INDEX",
        "display_name": spec.display_name if spec else index_id,
        "why": ("No index panel has been built. The level is read from NSE's derivatives "
                "bhavcopy, which this repository does not carry: point AEGIS_NSE_ARCHIVE "
                "at a downloaded archive and run scripts/build_index_panel.py."),
        "remedy": "python scripts/build_index_panel.py",
    }


def index_detail(index_id: str = "NIFTY50", window: int = 250) -> dict:
    """One index: its level, what it has done, and what this source cannot tell you.

    The unavailable fields travel with the available ones. An index page that showed a
    close and said nothing about the absence of an intraday range invites a reader to
    assume the range was simply not interesting today, rather than never published.
    """
    from research.data import nse_index as ix

    panel = index_panel()
    spec = ix.INDEX_REGISTRY.get(index_id)
    if spec is None:
        return {"available": False, "instrument_id": index_id,
                "why": "%s is not an index this project ingests." % index_id}
    if panel.empty:
        return _index_unavailable(index_id)

    rows = panel[panel["index_id"] == index_id].sort_values("date")
    if rows.empty:
        return _index_unavailable(index_id)

    sessions = max(20, min(int(window), 2000))
    tail = rows.tail(sessions)
    last = rows.iloc[-1]
    first_in_window = float(tail["close"].iloc[0])
    close = float(last["close"])

    def value(name):
        v = last.get(name)
        return float(v) if v is not None and pd.notna(v) else None

    coverage = ix.coverage(panel, index_id)
    return {
        "available": True,
        "instrument_id": spec.instrument_id,
        "instrument_type": spec.instrument_type.value,
        "display_name": spec.display_name,
        "description": spec.description,
        "last_session": str(pd.Timestamp(last["date"]).date()),
        "close": close,
        "change": value("change"),
        "change_pct": value("return_pct"),
        "previous_close": value("prev_close"),
        "volatility_20d": value("volatility_20d"),
        "drawdown": value("drawdown"),
        "high_52w": value("high_52w"),
        "low_52w": value("low_52w"),
        "window_sessions": int(len(tail)),
        "window_change_pct": (close - first_in_window) / first_in_window
        if first_in_window else None,
        "series": [
            {"date": str(pd.Timestamp(r.date).date()), "close": float(r.close)}
            for r in tail.itertuples(index=False)
        ],
        "coverage": coverage,
        "provenance": spec.provenance.to_dict() if spec.provenance else None,
        "available_fields": list(spec.available_fields),
        "unavailable_fields": dict(spec.unavailable_fields),
        "recency": ("LATEST_AVAILABLE_SESSION"),
        "recency_note": ("End-of-session data from a daily published report. This is the "
                         "latest available session, not a live or delayed quote."),
        "constituents": index_constituents(index_id),
    }


def index_constituents(index_id: str = "NIFTY50") -> dict:
    """Index membership, which this archive does not carry.

    Saying so is the whole function. NSE Indices publishes membership separately; the
    bhavcopy does not contain it, and there is no honest way to recover it from prices.
    Two wrong answers are available and both are refused: the fifty largest instruments by
    traded value are the liquidity proxy and not the index, and today's membership applied
    to history would manufacture survivorship bias in every backward-looking number.
    """
    from research.data import nse_index as ix

    spec = ix.INDEX_REGISTRY.get(index_id)
    return {
        "available": False,
        "count": None,
        "why": ("Index membership is published by NSE Indices as a separate file and is "
                "not present in the derivatives bhavcopy this project ingests."),
        "what_would_be_needed": (
            "The official constituent list with its effective dates. With it, "
            "constituent performance, sector composition and contribution analysis "
            "become computable; without it they are not."),
        "not_substituted_by": {
            "liquidity_proxy": (
                "This project's point-in-time liquidity proxy holds fifty instruments "
                "selected by traded value. It is a sampling frame, not index membership, "
                "and the two are kept as different entities for exactly this reason."),
            "current_membership_applied_to_history": (
                "Using today's members for past sessions would introduce survivorship "
                "bias into every historical statistic computed from them."),
        },
        "declared_unavailable_in_registry": bool(
            spec and "constituents" in spec.unavailable_fields),
    }


def index_overview(index_id: str = "NIFTY50") -> dict:
    """The benchmark card: level, move, range, and how far the history goes."""
    detail = index_detail(index_id, window=250)
    if not detail.get("available"):
        return detail
    keep = ("available", "instrument_id", "instrument_type", "display_name",
            "description", "last_session", "close", "change", "change_pct",
            "volatility_20d", "drawdown", "high_52w", "low_52w",
            "window_change_pct", "recency", "recency_note", "coverage",
            "provenance", "unavailable_fields")
    card = {k: detail[k] for k in keep if k in detail}
    card["series"] = detail["series"][-60:]
    return card


def indices() -> dict:
    """Every index whose level has been ingested, primary first."""
    from research.data import nse_index as ix

    panel = index_panel()
    if panel.empty:
        return {"available": False, "rows": [], **_index_unavailable(ix.PRIMARY)}
    rows = []
    for index_id in [ix.PRIMARY, *[i for i in ix.INDEX_REGISTRY if i != ix.PRIMARY]]:
        detail = index_detail(index_id, window=60)
        if detail.get("available"):
            rows.append({k: detail[k] for k in
                         ("instrument_id", "instrument_type", "display_name",
                          "close", "change_pct", "last_session", "series")})
    return {"available": bool(rows), "rows": rows, "primary": ix.PRIMARY}


def index_series(index_id: str = "NIFTY50", date_from: str | None = None,
                 date_to: str | None = None) -> dict:
    """The index series with every derived column the panel carries.

    All four views the product offers — level, return, volatility, drawdown — come from
    here as columns. The interface picks which to draw and computes none of them: a
    percentage change worked out in the browser is a number with no provenance, and the
    panel already carries it with one.
    """
    from research.data import nse_index as ix

    panel = index_panel()
    if panel.empty or index_id not in ix.INDEX_REGISTRY:
        return _index_unavailable(index_id)
    rows = panel[panel["index_id"] == index_id].sort_values("date")
    if rows.empty:
        return _index_unavailable(index_id)

    full_from = str(pd.Timestamp(rows["date"].min()).date())
    full_to = str(pd.Timestamp(rows["date"].max()).date())
    if date_from:
        rows = rows[rows["date"] >= pd.Timestamp(date_from)]
    if date_to:
        rows = rows[rows["date"] <= pd.Timestamp(date_to)]
    if rows.empty:
        return {"available": False, "instrument_id": index_id,
                "why": "No sessions between %s and %s. The series covers %s to %s."
                       % (date_from, date_to, full_from, full_to)}

    def maybe(v):
        return float(v) if v is not None and pd.notna(v) else None

    return {
        "available": True,
        "instrument_id": index_id,
        "instrument_type": "INDEX",
        "display_name": ix.INDEX_REGISTRY[index_id].display_name,
        "sessions": int(len(rows)),
        "from": str(pd.Timestamp(rows["date"].min()).date()),
        "to": str(pd.Timestamp(rows["date"].max()).date()),
        "full_from": full_from,
        "full_to": full_to,
        "series": [
            {"date": str(pd.Timestamp(r.date).date()),
             "close": float(r.close),
             "return_pct": maybe(r.return_pct),
             "volatility_20d": maybe(r.volatility_20d),
             "drawdown": maybe(r.drawdown)}
            for r in rows.itertuples(index=False)
        ],
        "views": [
            {"key": "close", "label": "Level", "unit": "points",
             "note": "The closing level NSE published for the session."},
            {"key": "return_pct", "label": "Daily change",
             "unit": "percent", "note": "Session-over-session change in the level."},
            {"key": "volatility_20d", "label": "Volatility",
             "unit": "percent",
             "note": "Standard deviation of daily log returns over 20 sessions, "
                     "annualised. Blank for the first 19 sessions of the series."},
            {"key": "drawdown", "label": "Drawdown",
             "unit": "percent",
             "note": "How far below its highest point the level has been, measured "
                     "within this series rather than all time."},
        ],
        "recency": "LATEST_AVAILABLE_SESSION",
    }


def index_context(index_id: str = "NIFTY50") -> dict:
    """What else this project observed over the sessions the index covers.

    Two levels, kept apart because they are different claims:

    **Market context.** Documents and sessions this project holds that fall inside the
    index window. They are evidence about the market over the same period; none of them
    is evidence *about the index*, and the payload never says otherwise.

    **Instrument evidence.** The model's assessments, which live in their own window. The
    two windows do not necessarily overlap, and where they do not, the honest answer is
    the non-overlap itself rather than a chart with nothing in it.
    """
    from research.data import nse_index as ix

    panel_rows = index_panel()
    if panel_rows.empty or index_id not in ix.INDEX_REGISTRY:
        return _index_unavailable(index_id)
    idx = panel_rows[panel_rows["index_id"] == index_id].sort_values("date")
    if idx.empty:
        return _index_unavailable(index_id)

    lo, hi = idx["date"].min(), idx["date"].max()

    corpus = live.text_corpus()
    docs = corpus[(corpus["date"] >= lo) & (corpus["date"] <= hi)]
    kinds = (docs["doc_kind"].astype(str).value_counts()
             .rename_axis("doc_kind").reset_index(name="documents"))

    modelling = live.panel()
    rows_in_window = modelling[(modelling["date"] >= lo) & (modelling["date"] <= hi)]

    scored_rows = scored()
    assessed_from = assessed_to = None
    overlap = 0
    if not scored_rows.empty:
        assessed_from = str(pd.Timestamp(scored_rows["date"].min()).date())
        assessed_to = str(pd.Timestamp(scored_rows["date"].max()).date())
        index_days = set(pd.to_datetime(idx["date"]).dt.normalize())
        scored_days = set(pd.to_datetime(scored_rows["date"]).dt.normalize())
        overlap = len(index_days & scored_days)

    return {
        "available": True,
        "instrument_id": index_id,
        "display_name": ix.INDEX_REGISTRY[index_id].display_name,
        "window": {"from": str(pd.Timestamp(lo).date()),
                   "to": str(pd.Timestamp(hi).date()),
                   "sessions": int(len(idx))},
        "market_context": {
            "level": "MARKET",
            "documents": int(len(docs)),
            "instruments_with_documents": int(docs["symbol"].nunique()) if len(docs)
            else 0,
            "by_kind": [{"doc_kind": str(r.doc_kind), "documents": int(r.documents)}
                        for r in kinds.itertuples(index=False)],
            "panel_sessions": int(len(rows_in_window)),
            "panel_instruments": int(rows_in_window["symbol"].nunique())
            if len(rows_in_window) else 0,
            "reading": ("Evidence this project holds for sessions inside the index "
                        "window. It describes the market over the same period. None of "
                        "it is linked to the index itself: index membership is not in "
                        "the data, so no document can be attributed to the benchmark."),
        },
        "instrument_evidence": {
            "level": "INSTRUMENT",
            "assessed_from": assessed_from,
            "assessed_to": assessed_to,
            "assessed_rows": int(len(scored_rows)),
            "overlapping_sessions": int(overlap),
            "reading": (
                "Model assessments are instrument-level and cover their own evaluation "
                "window. Where that window does not meet the index window, no assessment "
                "falls inside the period charted above — which is a fact about coverage, "
                "not a finding about the market."),
        },
        "coverage_note": (
            "The index series covers %s to %s. The assessed sessions cover %s to %s. "
            "They share %d session%s."
            % (str(pd.Timestamp(lo).date()), str(pd.Timestamp(hi).date()),
               assessed_from or "nothing", assessed_to or "nothing",
               overlap, "" if overlap == 1 else "s")),
    }


# ----------------------------------------------------------- evidence alignment ----
#
# Which of this project's sources can be spoken about together, computed rather than
# remembered. The pairs below are the ones the product and the research programme
# actually put beside each other; adding a source here is what makes it checkable.


#: The sources whose coverage the alignment layer knows how to read. Each entry names how
#: to get its sessions; nothing here assumes what the answer will be.
ALIGNMENT_SOURCES = ("NIFTY50", "MODEL_EVIDENCE", "TEXT_CORPUS", "PANEL",
                     "LIQUIDITY_PROXY_TOP50")


def coverage_window(source_id: str):
    """One source's coverage, as the set of sessions it holds.

    Sessions rather than a range: two sources can span the same years and still share
    almost nothing, and only the intersection answers whether they can be discussed
    together.
    """
    from research.data import nse_index as ix
    from research.data.alignment import CoverageWindow

    if source_id in ix.INDEX_REGISTRY:
        panel = index_panel()
        rows = (panel[panel["index_id"] == source_id]
                if not panel.empty else pd.DataFrame(columns=["date"]))
        spec = ix.INDEX_REGISTRY[source_id]
        return CoverageWindow.from_dates(
            source_id, "INDEX", spec.display_name, rows.get("date", []),
            note="Published index level, read from NSE's daily derivatives report.")

    if source_id == "MODEL_EVIDENCE":
        rows = scored()
        return CoverageWindow.from_dates(
            "MODEL_EVIDENCE", "MODEL_OUTPUT", "model evidence",
            rows.get("date", []) if not rows.empty else [],
            note="Sessions the fitted model scored, from the stored evaluation run.")

    if source_id == "TEXT_CORPUS":
        return CoverageWindow.from_dates(
            "TEXT_CORPUS", "MEDIA", "financial text corpus",
            live.text_corpus()["date"],
            note="Documents aligned to instruments and sessions.")

    if source_id == "PANEL":
        return CoverageWindow.from_dates(
            "PANEL", "FEATURE_PANEL", "multimodal panel", live.panel()["date"],
            note="Assembled instrument-day rows across every modality block.")

    if source_id == "LIQUIDITY_PROXY_TOP50":
        return CoverageWindow.from_dates(
            "LIQUIDITY_PROXY_TOP50", "UNIVERSE_PROXY",
            "point-in-time liquidity proxy", live.universe()["rebalance_date"],
            note="Reconstitution dates of the research sampling frame. A sampling "
                 "frame, not an index.")

    return CoverageWindow.from_dates(source_id, "UNKNOWN", source_id, [])


#: The pairs the interface puts beside each other, and why each one matters.
ALIGNMENT_PAIRS = (
    ("NIFTY50", "MODEL_EVIDENCE",
     "Whether the benchmark can be used as a market variable alongside the existing "
     "model results."),
    ("NIFTY50", "TEXT_CORPUS",
     "Whether financial text exists for the sessions the index covers."),
    ("NIFTY50", "PANEL",
     "Whether assembled feature rows exist for the sessions the index covers."),
    ("MODEL_EVIDENCE", "TEXT_CORPUS",
     "Whether the text evidence covers the sessions the model scored."),
)


def alignment(source_a: str = "NIFTY50", source_b: str = "MODEL_EVIDENCE") -> dict:
    """The temporal relationship between two sources, as a value.

    The status is computed on every call. It reads NOT_ALIGNED today because the
    arithmetic says so; give the project a NIFTY 50 series covering the evaluation window
    and the same code will read ALIGNED with nothing edited.
    """
    from research.data.alignment import align

    a, b = coverage_window(source_a), coverage_window(source_b)
    return align(a, b).to_dict()


def alignment_matrix() -> dict:
    """Every pair the interface shows, with what each one permits.

    The headline pair is the index against the model evidence, because that is the one a
    reader is most likely to assume without checking.
    """
    from research.data.alignment import ALIGNMENT_VERSION, align

    rows = []
    for a_id, b_id, why in ALIGNMENT_PAIRS:
        a, b = coverage_window(a_id), coverage_window(b_id)
        result = align(a, b)
        rows.append({**result.to_dict(), "why_it_matters": why})

    headline = rows[0] if rows else None
    aligned = sum(1 for r in rows if r["alignment_status"] == "ALIGNED")
    return {
        "available": True,
        "alignment_version": ALIGNMENT_VERSION,
        "pairs": rows,
        "headline": headline,
        "counts": {
            "pairs": len(rows),
            "aligned": aligned,
            "partial": sum(1 for r in rows if r["alignment_status"] == "PARTIAL"),
            "not_aligned": sum(1 for r in rows
                               if r["alignment_status"] == "NOT_ALIGNED"),
        },
        "sources": [coverage_window(s).to_dict() for s in ALIGNMENT_SOURCES],
        "reading": (
            "Two sources can each be correct and still have nothing to say about each "
            "other, because they cover different sessions. Every status here is computed "
            "from the sessions each source actually holds; none is stored, and none is "
            "assumed."),
        "future_path": (
            "A pair reading NOT_ALIGNED becomes ALIGNED as soon as a source covering the "
            "other's sessions is ingested — either a licence-compatible NIFTY 50 series "
            "reaching back over the evaluation window, or a model evaluation rerun on a "
            "period the verified index series covers. Neither is simulated here."),
    }


def combined_analysis_permitted(source_a: str, source_b: str, what: str) -> dict:
    """Whether a result may be built about two sources at once, and why not if not.

    The gate the Scenario Lab and any future combined analysis consult. It returns a
    refusal rather than an empty result, because a combined figure covering no shared
    sessions looks exactly like one that covers many.
    """
    from research.data.alignment import (
        AlignmentStatus,
        NotTemporallyAligned,
        align,
        require_alignment,
    )

    a, b = coverage_window(source_a), coverage_window(source_b)
    result = align(a, b)
    try:
        require_alignment(result, what, allow_partial=True)
    except NotTemporallyAligned as exc:
        return {
            "permitted": False,
            "what": what,
            "status": result.status.value,
            "reason": str(exc),
            "remedy": (
                "Present the two side by side instead, or ingest a source covering the "
                "sessions both need. Nothing is combined across a gap."),
            "alignment": result.to_dict(),
        }
    return {
        "permitted": True,
        "what": what,
        "status": result.status.value,
        "caveat": ("Overlap is partial: any combined result covers only the shared "
                   "sessions and must say so."
                   if result.status is AlignmentStatus.PARTIAL else ""),
        "alignment": result.to_dict(),
    }


# ------------------------------------------------------- evidence for a period ----
#
# "What evidence does this project actually hold for the sessions this index covers?"
# is a product question, and the alignment layer already answers the hard part of it.
# This shapes that answer into cards: one per source, each carrying the status, the
# session counts behind it, and two registers of wording.
#
# Two questions are kept apart here, because conflating them is the easiest mistake
# available:
#
#   Q1  Does this source cover the same sessions as the index?   -> alignment
#   Q2  Does any experiment actually use the index?              -> provenance
#
# An aligned dataset is not evidence for a model that never read it. Q1 is answered per
# pair below; Q2 is answered once, and the answer is currently no.


#: The sources a reader would expect to see for a market period, in the order they are
#: most likely to ask about them. Each carries the words the product uses for it, which
#: are deliberately not the words the research programme uses.
EVIDENCE_SOURCES = (
    {
        "source_id": "TEXT_CORPUS",
        "product_label": "Market text",
        "research_label": "financial text corpus",
        "product_blurb": "Financial commentary aligned to instruments and sessions.",
        "href": "/multimodal/text-corpus",
    },
    {
        "source_id": "PANEL",
        "product_label": "Multimodal evidence",
        "research_label": "multimodal feature panel",
        "product_blurb": "Assembled market, text, image, audio and video features.",
        "href": "/multimodal/dataset-assembly",
    },
    {
        "source_id": "MODEL_EVIDENCE",
        "product_label": "Historical model evidence",
        "research_label": "stored model evaluation",
        "product_blurb": "Assessments the fitted model produced on its own "
                          "evaluation period.",
        "href": "/analysis",
    },
)

#: How a status reads in each register. The product gets a verdict and a sentence; the
#: research view gets the arithmetic, which lives on the pair itself.
STATUS_COPY = {
    "ALIGNED": {
        "badge": "Aligned",
        "mark": "check",
        "tone": "calm",
        "product": "Covers the same market sessions.",
    },
    "PARTIAL": {
        "badge": "Partly aligned",
        "mark": "partial",
        "tone": "watch",
        "product": "Covers part of this period.",
    },
    "NOT_ALIGNED": {
        "badge": "Not aligned",
        "mark": "cross",
        "tone": "elevated",
        "product": "Covers a different period.",
    },
    "UNKNOWN": {
        "badge": "Not measured",
        "mark": "unknown",
        "tone": "watch",
        "product": "Not enough data to compare periods yet.",
    },
}


def _period_label(start: str | None, end: str | None) -> str:
    """A period as a reader would say it: two years, or one if they match."""
    if not start or not end:
        return "—"
    a, b = start[:4], end[:4]
    return a if a == b else "%s–%s" % (a, b)


def evidence_summary(index_id: str = "NIFTY50") -> dict:
    """What evidence exists for the sessions an index covers, source by source.

    Every status is the alignment layer's, computed for that specific pair. That
    specificity is the point: the stored model evaluation not overlapping the index says
    nothing about whether the text corpus does, and treating one verdict as the answer
    for all of them would throw away the two sources that *are* aligned.
    """
    from research.data.alignment import align

    index_window = coverage_window(index_id)
    if index_window.n_sessions == 0:
        return {
            "available": False,
            "index_id": index_id,
            "why": ("No index panel has been built, so there is no period to find "
                    "evidence for."),
            "remedy": "python scripts/build_index_panel.py",
        }

    cards = []
    for spec in EVIDENCE_SOURCES:
        other = coverage_window(spec["source_id"])
        result = align(index_window, other)
        status = result.status.value
        copy = STATUS_COPY.get(status, STATUS_COPY["UNKNOWN"])
        cards.append({
            **spec,
            "kind": other.kind,
            "status": status,
            "badge": copy["badge"],
            "mark": copy["mark"],
            "tone": copy["tone"],
            "product_status": copy["product"],
            "period": _period_label(
                other.start.isoformat() if other.start else None,
                other.end.isoformat() if other.end else None),
            "period_from": other.start.isoformat() if other.start else None,
            "period_to": other.end.isoformat() if other.end else None,
            "source_sessions": other.n_sessions,
            "index_sessions": index_window.n_sessions,
            "shared_sessions": result.overlap_sessions,
            "overlap_from": result.overlap_start.isoformat()
            if result.overlap_start else None,
            "overlap_to": result.overlap_end.isoformat() if result.overlap_end else None,
            "coverage_ratio": result.coverage_ratio,
            "summary": result.summary,
            "permits": result.permits,
            "source_note": other.note,
        })

    aligned = [c for c in cards if c["status"] == "ALIGNED"]
    partial = [c for c in cards if c["status"] == "PARTIAL"]
    not_aligned = [c for c in cards if c["status"] == "NOT_ALIGNED"]

    if aligned and not not_aligned:
        headline = "Evidence covers this whole market period."
    elif aligned:
        headline = ("%s cover this market period. %s from a different one."
                    % (_join([c["product_label"] for c in aligned]),
                       _join([c["product_label"] for c in not_aligned])))
    else:
        headline = "No evidence source covers this market period."

    return {
        "available": True,
        "index_id": index_id,
        "index_label": index_window.label,
        "index_from": index_window.start.isoformat() if index_window.start else None,
        "index_to": index_window.end.isoformat() if index_window.end else None,
        "index_sessions": index_window.n_sessions,
        "index_period": _period_label(
            index_window.start.isoformat() if index_window.start else None,
            index_window.end.isoformat() if index_window.end else None),
        "sources": cards,
        "counts": {
            "aligned": len(aligned),
            "partial": len(partial),
            "not_aligned": len(not_aligned),
            "total": len(cards),
        },
        "headline": headline,
        # Q2, answered once and kept apart from Q1 above.
        "experiments_using_index": {
            "count": 0,
            "answer": False,
            "product_note": ("The analysis in this project was run on individual "
                             "instruments, not on the benchmark itself."),
            "research_note": (
                "Alignment says two sources cover the same sessions. It does not say an "
                "experiment used them together: no experiment in this project takes the "
                "index as an input, so an aligned source is available evidence rather "
                "than evidence already used."),
        },
    }


def _join(labels: list[str]) -> str:
    if not labels:
        return "Nothing"
    if len(labels) == 1:
        return labels[0]
    return "%s and %s" % (", ".join(labels[:-1]), labels[-1])
