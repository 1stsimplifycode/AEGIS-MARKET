"""The Week 1 market-intelligence foundation, as the product consumes it.

One module between the research layer and the interface, so that a page cannot render a
market fact the research layer would not stand behind. Everything here is derived from the
artifacts on disk at request time; nothing is hardcoded, and anything unavailable is
returned as unavailable with the reason rather than omitted (an omitted field renders as
a blank, and a blank reads as "nothing to report" rather than "we could not obtain this").

The functions are deliberately shaped like the product's questions:

``instrument_context``   corporate actions, lifecycle state and price band for one symbol
``point_in_time_view``   what was knowable about a symbol at a chosen instant
``market_session``       session facts, graded, plus the holiday calendar
``reference_status``     the twelve-input delivery report
"""
from __future__ import annotations

import functools
import json

import pandas as pd

from research.core import paths
from research.data import pit
from research.data import quarantine as Q
from research.reference import Basis, registry, sessions
from research.reference import index_methodology as IM
from research.reference import lifecycle as LC

from . import live

WEEK1_VERSION = "week1-foundation-v1"


def _unavailable(what: str, why: str, remedy: str = "") -> dict:
    return {"available": False, "what": what, "why": why,
            "remedy": remedy or "Run scripts/build_week1_foundation.py."}


@functools.lru_cache(maxsize=1)
def adjustments() -> pd.DataFrame | None:
    p = paths.REFERENCE / "corporate_action_adjustments.parquet"
    return pd.read_parquet(p) if p.exists() else None


@functools.lru_cache(maxsize=1)
def all_actions() -> pd.DataFrame | None:
    p = paths.REFERENCE / "corporate_actions.parquet"
    return pd.read_parquet(p) if p.exists() else None


@functools.lru_cache(maxsize=1)
def lifecycle() -> pd.DataFrame | None:
    p = paths.REFERENCE / "security_lifecycle.parquet"
    return pd.read_parquet(p) if p.exists() else None


@functools.lru_cache(maxsize=1)
def price_bands() -> pd.DataFrame | None:
    """Exchange-published price bands. Not a constant, not a default."""
    p = paths.REFERENCE / "sec_list_price_bands.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df.columns = [str(c).strip() for c in df.columns]
    df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()
    return df


@functools.lru_cache(maxsize=1)
def index_levels() -> pd.DataFrame | None:
    p = paths.PANEL / "index_reconciled.parquet"
    return pd.read_parquet(p) if p.exists() else None


# -- the product's questions ------------------------------------------------------------

def price_band(symbol: str) -> dict:
    """The band the exchange applies, or an explicit refusal.

    Never returns a default. A missing band is reported as missing, because a number here
    would look exactly like a rule and be neither.
    """
    sym = str(symbol or "").upper().strip()
    bands = price_bands()
    if bands is None:
        return _unavailable("Circuit band",
                            "NSE's securities list has not been acquired.",
                            "Run python -m research.reference.acquire.")
    row = bands[bands["Symbol"] == sym]
    if row.empty:
        return _unavailable("Circuit band",
                            "%s is not in NSE's current securities list." % sym,
                            "The security may be delisted; see its lifecycle state.")
    raw = str(row.iloc[0]["Band"]).strip()
    remarks = str(row.iloc[0].get("Remarks", "")).strip()
    return {
        "available": True,
        "band": None if raw.lower() == "no band" else raw,
        "band_label": "No band" if raw.lower() == "no band" else "%s%%" % raw,
        "series": str(row.iloc[0].get("Series", "")).strip(),
        "surveillance_remark": None if remarks in ("-", "", "nan") else remarks,
        "basis": str(Basis.EXCHANGE_PUBLISHED),
        "source": "NSE sec_list.csv",
        "temporal_coverage": "current snapshot; NSE publishes no historical band series",
    }


def corporate_action_context(symbol: str, limit: int = 12) -> dict:
    """Every corporate action the exchange announced for this symbol."""
    sym = str(symbol or "").upper().strip()
    actions = all_actions()
    if actions is None:
        return _unavailable("Corporate actions",
                            "The corporate-action feed has not been built.")
    rows = actions[actions["symbol"] == sym].sort_values("ex_date", ascending=False)
    if rows.empty:
        return {"available": True, "count": 0, "actions": [],
                "note": "NSE announced no corporate action for %s in 2005-2026." % sym}

    price_affecting = rows[
        (rows["combined_price_factor"] - 1.0).abs() > 1e-6]
    out = []
    for r in rows.head(limit).itertuples(index=False):
        out.append({
            "ex_date": str(pd.Timestamp(r.ex_date).date()),
            "subject": r.subject,
            "action_type": r.action_type,
            "price_factor": (float(r.combined_price_factor)
                             if pd.notna(r.combined_price_factor) else None),
            "status": r.status,
            "raw_return": float(r.raw_return) if pd.notna(r.raw_return) else None,
            "adjusted_return": (float(r.adjusted_return)
                                if pd.notna(r.adjusted_return) else None),
        })
    return {
        "available": True,
        "count": int(len(rows)),
        "price_affecting": int(len(price_affecting)),
        "actions": out,
        "basis": str(Basis.EXCHANGE_PUBLISHED),
        "source": "NSE corporate-action feed",
    }


def security_status(symbol: str) -> dict:
    """Lifecycle state, with the basis on which it is asserted."""
    sym = str(symbol or "").upper().strip()
    lc = lifecycle()
    if lc is None:
        return _unavailable("Security status", "The lifecycle table has not been built.")
    row = lc[lc["symbol"] == sym]
    if row.empty:
        return _unavailable("Security status",
                            "%s has never appeared in the panel." % sym)
    d = row.iloc[0].to_dict()
    state = LC.LifecycleState(d["state"])
    return {
        "available": True,
        "state": str(state),
        "state_label": str(state).replace("_", " ").title(),
        "meaning": LC.STATE_MEANING[state],
        "basis": d["state_basis"],
        "first_observed_session": d["first_observed_session"],
        "last_observed_session": d["last_observed_session"],
        "sessions_observed": int(d["sessions_observed"]),
        "listing_date": d["listing_date"],
        "listing_date_basis": d["listing_date_basis"],
        "in_current_roster": bool(d["in_current_roster"]),
        "trade_for_trade_sessions": int(d["trade_for_trade_sessions"]),
        "delisted_on": None,
        "suspended_on": None,
        "date_note": ("NSE publishes no open delisting or suspension list, so no such "
                      "date is stated. The last observed session bounds it."),
    }


def point_in_time_view(symbol: str, as_of_date: str | None = None,
                       strict: bool = False) -> dict:
    """What was knowable about one instrument at a chosen instant.

    ``strict`` stands at the session close, before that session's own bhavcopy exists;
    otherwise the view stands after publication. The difference is the point of the
    control: it makes the knowledge boundary something the reader can see move.
    """
    sym = str(symbol or "").upper().strip()
    panel = live.cash_panel()
    rows = panel[panel["symbol"].str.upper() == sym]
    if rows.empty:
        return _unavailable("Point-in-time view",
                            "%s is not in the panel." % sym)

    target = pd.Timestamp(as_of_date) if as_of_date else rows["date"].max()
    asof = (pit.AsOf.at_session_close(target) if strict
            else pit.AsOf.after_publication(target))
    visible = pit.as_of_frame(rows, asof)
    pit.assert_no_leakage(visible, asof)

    hidden = len(rows[rows["date"] <= target]) - len(visible)
    return {
        "available": True,
        "symbol": sym,
        "as_of": asof.to_dict(),
        "strict": strict,
        "visible_sessions": int(len(visible)),
        "latest_visible_session": (str(pd.Timestamp(visible["date"].max()).date())
                                   if len(visible) else None),
        "latest_visible_close": (float(visible.sort_values("date")["close"].iloc[-1])
                                 if len(visible) else None),
        "withheld_by_knowledge_bound": int(max(0, hidden)),
        "explanation": (
            "Standing at the close of %s, that session's bhavcopy is not published yet, "
            "so its own row is not visible." % str(pd.Timestamp(target).date())
            if strict else
            "Standing after the bhavcopy for %s is published, that session is visible "
            "and no later one is." % str(pd.Timestamp(target).date())),
        "read_path": "research.data.pit.as_of_frame",
    }


def market_session() -> dict:
    """Session facts, each labelled fact or assumption, plus the holiday calendar."""
    d = sessions.to_dict()
    d["available"] = True
    d["note"] = ("Values marked PROJECT_ASSUMPTION are this repository's, not NSE's. "
                 "They are shown so that a reader can see which is which.")
    return d


def reference_status() -> dict:
    """The twelve-input delivery report, verified against disk."""
    p = paths.REFERENCE / "reference_manifest.json"
    if not p.exists():
        return _unavailable("Reference data", "No reference manifest.",
                            "Run python -m research.reference.acquire.")
    r = registry.status_report()
    r["available"] = True
    r["review_cycle"] = IM.review_cycle()
    return r


def index_summary() -> dict:
    """The divisor-reconciled index, and the divisor events behind it."""
    levels = index_levels()
    if levels is None or levels.empty:
        return _unavailable("Index", "The reconciled index has not been built.")
    ev_path = paths.PANEL / "index_divisor_events.parquet"
    events = pd.read_parquet(ev_path) if ev_path.exists() else pd.DataFrame()
    ca = events[events["reason"] == "CORPORATE_ACTION"] if len(events) else events
    return {
        "available": True,
        "sessions": int(len(levels)),
        "first_session": str(pd.Timestamp(levels["date"].min()).date()),
        "last_session": str(pd.Timestamp(levels["date"].max()).date()),
        "level": float(levels.sort_values("date")["level"].iloc[-1]),
        "divisor_events": int(len(events)),
        "corporate_action_events": int(len(ca)),
        "max_abs_daily_log_return": float(levels["logret_1d"].abs().max()),
        "recent_divisor_events": (
            ca.sort_values("date", ascending=False).head(5).to_dict("records")
            if len(ca) else []),
        "caveat": ("Built over the point-in-time liquidity-proxy universe. It is NOT "
                   "the NIFTY 50: NSE Indices' free-float factors and capping rules are "
                   "not published openly and are not reconstructed here."),
    }


def instrument_context(symbol: str, as_of_date: str | None = None) -> dict:
    """Everything the Week 1 foundation knows about one instrument."""
    sym = str(symbol or "").upper().strip()
    return {
        "week1_version": WEEK1_VERSION,
        "symbol": sym,
        "status": security_status(sym),
        "corporate_actions": corporate_action_context(sym),
        "price_band": price_band(sym),
        "point_in_time": point_in_time_view(sym, as_of_date),
    }


def foundation_summary() -> dict:
    """The Week 1 page's top-level block."""
    p = paths.REPO_ROOT / "outputs" / "week1" / "foundation_summary.json"
    stored = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return {
        "week1_version": WEEK1_VERSION,
        "available": bool(stored),
        "reference": reference_status(),
        "index": index_summary(),
        "session": market_session(),
        "quarantine": Q.summarise(),
        "corporate_actions": stored.get("corporate_actions", {}),
        "lifecycle": stored.get("lifecycle", {}),
    }
