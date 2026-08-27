"""Shared loading and slicing for the live analysis adapters.

Two jobs, both of which exist so the analysis adapters can stay thin:

**Caching.** A live analysis runs on request, and re-reading a 300,000-row parquet on
every keystroke would make the interface feel broken for reasons that have nothing to do
with the research. Frames are read once per process and reused. They are never mutated:
every slicing helper returns a copy, because an adapter that filtered in place would
poison the cache for the next request.

**One filter.** Every adapter that takes a date range and an instrument list applies it
the same way, so two modules asked for the same slice see the same rows. A slice that is
too small to analyse is refused here rather than producing a confident number over eleven
observations.
"""
from __future__ import annotations

import functools

import pandas as pd

from research.core import paths
from research.data import pit

#: Below this many rows a slice does not produce a small result, it produces a
#: meaningless one. Adapters refuse rather than return one.
MIN_ROWS = 30


@functools.lru_cache(maxsize=1)
def panel() -> pd.DataFrame:
    """The assembled multimodal modelling panel."""
    return pd.read_parquet(paths.PANEL / "multimodal_dataset.parquet")


@functools.lru_cache(maxsize=1)
def text_corpus() -> pd.DataFrame:
    """The aligned text corpus: one row per document."""
    return pd.read_parquet(paths.PANEL / "text_corpus.parquet")


@functools.lru_cache(maxsize=1)
def cash_panel() -> pd.DataFrame:
    """The NSE daily cash panel, for anything needing prices rather than features."""
    return pd.read_parquet(paths.PANEL / "cash_panel.parquet")


@functools.lru_cache(maxsize=1)
def universe() -> pd.DataFrame:
    """The point-in-time liquidity-proxy universe and its membership history."""
    return pd.read_parquet(paths.PANEL / "universe.parquet")


@functools.lru_cache(maxsize=48)
def per_row(arm: str) -> pd.DataFrame | None:
    """Per-row scores for one executed ablation arm, or None if that arm was not run."""
    p = paths.ARTIFACTS / "experiments" / ("per_row_%s.parquet" % arm)
    return pd.read_parquet(p) if p.exists() else None


@functools.lru_cache(maxsize=1)
def available_arms() -> tuple[str, ...]:
    d = paths.ARTIFACTS / "experiments"
    if not d.exists():
        return ()
    return tuple(sorted(p.stem.replace("per_row_", "")
                        for p in d.glob("per_row_*.parquet")))


@functools.lru_cache(maxsize=1)
def symbols() -> tuple[str, ...]:
    return tuple(sorted(panel()["symbol"].unique()))


@functools.lru_cache(maxsize=1)
def panel_dates() -> tuple[str, str]:
    d = panel()["date"]
    return str(d.min().date()), str(d.max().date())


@functools.lru_cache(maxsize=1)
def corpus_dates() -> tuple[str, str]:
    d = text_corpus()["date"]
    return str(d.min().date()), str(d.max().date())


def slice_frame(df: pd.DataFrame, date_from: str | None = None,
                date_to: str | None = None,
                instruments: list[str] | None = None,
                split: str | None = None,
                asof: pit.AsOf | None = None,
                require_point_in_time: bool = True) -> pd.DataFrame:
    """Apply the caller's selection point-in-time. The cached frame is never touched.

    The date range selects *which sessions the caller asked about*. It is not, and must
    not be, the leakage boundary: the bhavcopy for the last requested session is
    published after that session closes, so a range filter alone would expose rows the
    system could not have known. The knowledge bound is applied separately by
    :func:`research.data.pit.as_of_frame`, from ``asof``.

    ``asof`` defaults to the publication instant of ``date_to`` -- the honest reading of
    "give me everything through this session". Frames that carry no knowledge-time column
    are read with ``require_point_in_time=False``; :data:`NON_BITEMPORAL_FRAMES` records
    which those are and why.
    """
    out = df
    if date_from:
        out = out[out["date"] >= pd.Timestamp(date_from)]
    if date_to:
        out = out[out["date"] <= pd.Timestamp(date_to)]
    if instruments:
        wanted = {s.upper() for s in instruments}
        out = out[out["symbol"].str.upper().isin(wanted)]
    if split and split != "all" and "split" in out.columns:
        out = out[out["split"] == split]

    if require_point_in_time:
        cutoff = asof or (pit.AsOf.after_publication(date_to) if date_to
                          else pit.AsOf.latest())
        out = pit.as_of_frame(out, cutoff)
        pit.assert_no_leakage(out, cutoff)
    return out.copy()


#: Frames with no knowledge-time column, and the reason each is exempt. Anything not
#: named here is read point-in-time; the C2 test asserts this list does not grow
#: silently.
NON_BITEMPORAL_FRAMES = {
    "per_row_scores": ("Model scores for an already-executed experiment arm. Not "
                       "market history: they are outputs of a run whose inputs were "
                       "themselves read point-in-time."),
    "episode_labels": ("Synthetic episode ground truth generated with the panel, not "
                       "observed from the market (limitation L-04)."),
}


def as_of_for(date_to: str | None) -> pit.AsOf:
    """The knowledge cutoff implied by a request for sessions through ``date_to``."""
    return pit.AsOf.after_publication(date_to) if date_to else pit.AsOf.latest()


def describe_slice(df: pd.DataFrame, source: str, asof: pit.AsOf | None = None,
                   **selection) -> dict:
    """What the caller actually got, so a response can never imply a wider slice."""
    out = {
        "source": source,
        "rows": int(len(df)),
        "instruments": int(df["symbol"].nunique()) if "symbol" in df.columns else None,
        "date_from": str(df["date"].min().date()) if len(df) and "date" in df else None,
        "date_to": str(df["date"].max().date()) if len(df) and "date" in df else None,
        "selection": {k: v for k, v in selection.items() if v not in (None, "", [])},
    }
    if asof is not None:
        out["point_in_time"] = asof.to_dict()
    return out
