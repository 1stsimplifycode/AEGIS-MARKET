"""The product surface of the backend: market, instrument, search, attention.

Separate from :mod:`backend.service` because it answers a different kind of question.
`service` runs a research module and returns the module contract; this returns the read
models the product experience is built from, and never runs a module.

The rules it inherits are the ones that matter:

* **Nothing is scored on request.** Prices are read from the panel now; risk numbers come
  from a stored experiment run and are stamped with it. Each block carries its own
  provenance, so a page cannot present the second as if it were as current as the first.
* **No path, no secret, no absolute location** leaves this layer.
* **Every input is bounded** before it reaches a read model: a symbol is validated as a
  symbol, a limit is clamped, a window is clamped.

If the read models are unavailable — no panel on disk — these return a refusal with a
reason and a remedy rather than an empty shape the interface would render as zeroes.
"""
from __future__ import annotations

import time

from backend import BACKEND_VERSION, INVALID_INPUT, OK

#: Bounds on anything a caller can ask for.
MAX_LIMIT = 50
MAX_WINDOW = 750
MIN_WINDOW = 20
MAX_QUERY = 24


class ProductError(ValueError):
    """A product request that cannot be served, with what to do about it."""

    def __init__(self, code: str, reason: str, remedy: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason
        self.remedy = remedy


def _views():
    from scripts.stages import product_views

    return product_views


def _clean_symbol(raw: str) -> str:
    symbol = str(raw or "").strip().upper()
    if not symbol:
        raise ProductError(INVALID_INPUT, "no instrument symbol was given",
                           "Search for an instrument and open it from the results.")
    if len(symbol) > MAX_QUERY or not symbol.replace("&", "").replace("-", "").isalnum():
        raise ProductError(INVALID_INPUT, "%r is not a valid instrument symbol" % raw,
                           "Symbols are letters and digits, up to %d characters."
                           % MAX_QUERY)
    return symbol


def _clean_index(raw: str | None) -> str:
    """Resolve what a caller typed to a canonical index identifier.

    `NIFTY 50`, `NIFTY50` and `^NSEI` all mean the same benchmark and all reach the same
    entity. What they never reach is the liquidity proxy: that has its own identifier and
    its own type, and no alias points at it.
    """
    from research.data import nse_index as ix

    text = str(raw or ix.PRIMARY).strip().upper().replace(" ", "").replace("-", "")
    aliases = {
        "NIFTY": ix.PRIMARY, "NIFTY50": ix.PRIMARY, "^NSEI": ix.PRIMARY,
        "NSEI": ix.PRIMARY, "NIFTYFIFTY": ix.PRIMARY,
        "BANKNIFTY": "NIFTYBANK", "NIFTYBANK": "NIFTYBANK",
        "FINNIFTY": "NIFTYFINSERVICE", "NIFTYFINSERVICE": "NIFTYFINSERVICE",
        "MIDCPNIFTY": "NIFTYMIDCAP50", "NIFTYMIDCAP50": "NIFTYMIDCAP50",
        "NIFTYNXT50": "NIFTYNEXT50", "NIFTYNEXT50": "NIFTYNEXT50",
    }
    resolved = aliases.get(text)
    if resolved is None:
        raise ProductError(INVALID_INPUT, "%r is not an index this project ingests" % raw,
                           "Try NIFTY 50, NIFTY Bank or NIFTY Next 50.")
    return resolved


def _clean_date(raw) -> str | None:
    """A date, or nothing. Never a fragment that would silently widen a window."""
    import datetime as _dt

    if raw in (None, ""):
        return None
    try:
        return _dt.date.fromisoformat(str(raw)[:10]).isoformat()
    except ValueError as exc:
        raise ProductError(INVALID_INPUT, "%r is not a date" % raw,
                           "Use YYYY-MM-DD.") from exc


def _clamp(value, low: int, high: int, default: int) -> int:
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError):
        return default


def _envelope(payload: dict, started: float, **extra) -> dict:
    return {
        "backend_version": BACKEND_VERSION,
        "status": OK,
        "elapsed_s": round(time.perf_counter() - started, 3),
        **extra,
        **payload,
    }


def overview() -> dict:
    """The market's last session, the tracked sample, and the stored risk mix."""
    started = time.perf_counter()
    return _envelope(_views().market_overview(), started)


def instrument(symbol: str, window=None) -> dict:
    """One instrument: price history, stored signal, and what carried it."""
    started = time.perf_counter()
    sym = _clean_symbol(symbol)
    sessions = _clamp(window, MIN_WINDOW, MAX_WINDOW, _views().DEFAULT_WINDOW)
    payload = _views().instrument(sym, window=sessions)
    if not payload.get("found"):
        raise ProductError("UNKNOWN_INSTRUMENT",
                           payload.get("why", "no such instrument"),
                           "Search for an instrument and open it from the results.")
    return _envelope(payload, started)


def search(query: str, limit=None) -> dict:
    """Instrument lookup. An empty query returns the tracked sample."""
    started = time.perf_counter()
    q = str(query or "").strip()
    if len(q) > MAX_QUERY:
        raise ProductError(INVALID_INPUT,
                           "the search term is longer than %d characters" % MAX_QUERY,
                           "Search by instrument symbol.")
    n = _clamp(limit, 1, MAX_LIMIT, _views().SEARCH_LIMIT)
    return _envelope(_views().search(q, limit=n), started)


def index_overview(index_id: str | None = None) -> dict:
    """The benchmark card for the home page."""
    started = time.perf_counter()
    return _envelope(_views().index_overview(_clean_index(index_id)), started)


def index_detail(index_id: str | None = None, window=None) -> dict:
    """One index in full, with its coverage, provenance and unavailable fields."""
    started = time.perf_counter()
    sessions = _clamp(window, 20, 2000, 250)
    payload = _views().index_detail(_clean_index(index_id), window=sessions)
    if not payload.get("available"):
        raise ProductError("INDEX_UNAVAILABLE", payload.get("why", "no index data"),
                           payload.get("remedy",
                                       "Build the index panel from the NSE archive."))
    return _envelope(payload, started)


def index_series(index_id: str | None = None, date_from=None, date_to=None) -> dict:
    """The index series with every derived column, for an interactive chart.

    Level, daily change, volatility and drawdown all travel as columns. The interface
    chooses which to draw; it computes none of them, because a derived number without a
    pipeline behind it is a number with no provenance.
    """
    started = time.perf_counter()
    payload = _views().index_series(_clean_index(index_id),
                                    date_from=_clean_date(date_from),
                                    date_to=_clean_date(date_to))
    if not payload.get("available"):
        raise ProductError("INDEX_UNAVAILABLE", payload.get("why", "no index series"),
                           "Widen the date range, or build the index panel.")
    return _envelope(payload, started)


def index_context(index_id: str | None = None) -> dict:
    """What else this project observed over the index's sessions, at two levels."""
    started = time.perf_counter()
    payload = _views().index_context(_clean_index(index_id))
    if not payload.get("available"):
        raise ProductError("INDEX_UNAVAILABLE", payload.get("why", "no index data"),
                           "Build the index panel from the NSE archive.")
    return _envelope(payload, started)


#: Sources the alignment endpoints will resolve. A caller cannot ask about an arbitrary
#: string: an unknown source is a typo, and answering it with an empty window would look
#: like a real "no overlap" answer.
ALIGNMENT_SOURCES = ("NIFTY50", "NIFTYBANK", "NIFTYFINSERVICE", "NIFTYMIDCAP50",
                     "NIFTYNEXT50", "MODEL_EVIDENCE", "TEXT_CORPUS", "PANEL",
                     "LIQUIDITY_PROXY_TOP50")


def _clean_source(raw: str | None, fallback: str) -> str:
    name = str(raw or fallback).strip().upper().replace(" ", "_").replace("-", "_")
    if name not in ALIGNMENT_SOURCES:
        raise ProductError(INVALID_INPUT,
                           "%r is not a source this project tracks coverage for" % raw,
                           "Known sources: %s." % ", ".join(ALIGNMENT_SOURCES))
    return name


def alignment(source_a=None, source_b=None) -> dict:
    """How far two sources overlap in time, and what that permits."""
    started = time.perf_counter()
    a = _clean_source(source_a, "NIFTY50")
    b = _clean_source(source_b, "MODEL_EVIDENCE")
    return _envelope(_views().alignment(a, b), started)


def alignment_matrix() -> dict:
    """Every pair the interface presents together, with a computed status on each."""
    started = time.perf_counter()
    return _envelope(_views().alignment_matrix(), started)


def evidence_summary(index_id=None) -> dict:
    """What evidence exists for the sessions an index covers, ready to render.

    A product read model over the alignment layer, not a second implementation of it:
    every status here is one `research/data/alignment.py` computed for that specific pair.
    """
    started = time.perf_counter()
    return _envelope(_views().evidence_summary(_clean_index(index_id)), started)


def alignment_gate(source_a=None, source_b=None, what: str = "") -> dict:
    """Whether a combined result about two sources may be built at all.

    A gate rather than a hint. It answers before anything is computed, so a caller cannot
    produce a figure covering no shared sessions and discover afterwards that it meant
    nothing.
    """
    started = time.perf_counter()
    a = _clean_source(source_a, "NIFTY50")
    b = _clean_source(source_b, "MODEL_EVIDENCE")
    label = str(what or "a combined result").strip()[:160]
    return _envelope(_views().combined_analysis_permitted(a, b, label), started)


def indices() -> dict:
    """Every index whose level has been ingested."""
    started = time.perf_counter()
    return _envelope(_views().indices(), started)


def attention(limit=None) -> dict:
    """Scored instruments whose last stored assessment was not Normal."""
    started = time.perf_counter()
    n = _clamp(limit, 1, MAX_LIMIT, 8)
    return _envelope(_views().attention(limit=n), started)


def analysis_section(capability_id: str) -> dict | None:
    """The result behind one /analysis section, for callers that reached it.

    Called only after `capability.require_capability` has allowed it — the gate decides,
    this reads. Returning `None` means the capability is a section of the page rather than
    a dataset of its own, which is a different answer from "not allowed" and is reported
    as such by the caller.

    It runs the module the section is built from, through the same service every other
    module request goes through. That keeps one execution path: the live/replay labelling,
    the protected-artifact guard and the response contract all apply here exactly as they
    do everywhere else, rather than being re-implemented for one page.
    """
    from backend import service as svc

    module_for = {
        "contribution-analysis": "MULTIMODAL-14",
        "event-analysis": "STATS-08",
    }
    module_id = module_for.get(capability_id)
    if module_id is None:
        return None

    payload = svc.run_module(module_id, {})
    return {
        **payload,
        "capability": capability_id,
        "measurement": MEASUREMENT_NOTES.get(capability_id, ""),
    }


#: What each section's numbers mean, in one place, so the page and the API agree.
MEASUREMENT_NOTES = {
    "contribution-analysis": (
        "unique = AUPRC(full) - AUPRC(without that modality), from the leave-one-out "
        "ablation arms. Positive is the score lost by removing the modality; negative "
        "means the score was higher without it; a missing arm yields no value rather "
        "than a zero."
    ),
    "event-analysis": (
        "Counts, durations and intensities of the injected integrity-risk episodes that "
        "every detection result is measured against."
    ),
}
