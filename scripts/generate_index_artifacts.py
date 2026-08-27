"""Research artifacts and figures for the NIFTY 50 index series.

    python scripts/generate_index_artifacts.py

Writes to ``outputs/index/``:

    index_statistics.json        the series described, with its coverage and provenance
    nifty50_returns.csv          per-session level, return, volatility and drawdown
    figures/figIDX01_level.png       the historical level
    figures/figIDX02_volatility.png  rolling annualised volatility
    figures/figIDX03_drawdown.png    drawdown from the running maximum
    figures/figIDX04_returns.png     the distribution of daily returns
    figures/figIDX05_evidence.png    market evidence volume over the same window
    figures/figures.json             captions and source data for each

Every figure is drawn from ``data/panel/index_panel.parquet``, which is built from NSE's
published report. Nothing here fits a model or produces a forecast: these describe what a
published benchmark did over the sessions the source covers.

The last figure is the one worth reading carefully. It places this project's evidence
volume beside the index window and shows where the *assessed* window sits — which, as it
happens, is nowhere near it. That gap is a real property of the data and is drawn rather
than described.
"""
from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import environment_snapshot, git_commit  # noqa: E402
from research.data import nse_index as ix  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "index"
FIGS = OUT / "figures"
PANEL = paths.PANEL / "index_panel.parquet"

GENERATED: list[dict] = []

#: The palette the rest of the paper figures use: distinguishable without colour.
LINE = "#0072b2"
WARN = "#d55e00"
MUTED = "#6b7683"


def _relative(path: Path) -> str:
    return path.relative_to(paths.REPO_ROOT).as_posix()


def save(fig, name: str, caption: str, source: Path) -> None:
    FIGS.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(FIGS / ("%s.%s" % (name, ext)), dpi=200, bbox_inches="tight")
    plt.close(fig)
    GENERATED.append({"figure": name, "caption": caption,
                      "source_data": _relative(source)})
    progress.log("      %s" % name)


def figure_level(g: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.plot(g["date"], g["close"], color=LINE, lw=1.3)
    ax.set_ylabel("Index level")
    ax.set_title("NIFTY 50 closing level")
    ax.grid(alpha=0.25, lw=0.5)
    save(fig, "figIDX01_level",
         "NIFTY 50 closing level over the %d sessions the source covers (%s to %s). "
         "Levels are read from NSE's daily derivatives report; no level is computed by "
         "this project."
         % (len(g), str(g["date"].min().date()), str(g["date"].max().date())), PANEL)


def figure_volatility(g: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 3.0))
    ax.plot(g["date"], 100 * g["volatility_20d"], color=WARN, lw=1.2)
    ax.set_ylabel("Annualised volatility (%)")
    ax.set_title("NIFTY 50 rolling 20-session volatility")
    ax.grid(alpha=0.25, lw=0.5)
    save(fig, "figIDX02_volatility",
         "Standard deviation of daily log returns over a trailing 20 sessions, "
         "annualised by the square root of 252. The first 19 sessions carry no value "
         "and are absent rather than zero.", PANEL)


def figure_drawdown(g: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 3.0))
    ax.fill_between(g["date"], 100 * g["drawdown"], 0, color=WARN, alpha=0.25)
    ax.plot(g["date"], 100 * g["drawdown"], color=WARN, lw=1.0)
    ax.set_ylabel("Drawdown (%)")
    ax.set_title("NIFTY 50 drawdown from the running maximum")
    ax.grid(alpha=0.25, lw=0.5)
    worst = g.loc[g["drawdown"].idxmin()]
    save(fig, "figIDX03_drawdown",
         "Level relative to its highest point so far *within this series*. The "
         "deepest drawdown observed is %.2f%% on %s. This is not an all-time "
         "drawdown: the series begins on %s."
         % (100 * float(worst["drawdown"]), str(worst["date"].date()),
            str(g["date"].min().date())), PANEL)


def figure_returns(g: pd.DataFrame) -> None:
    r = 100 * g["return_pct"].dropna()
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    ax.hist(r, bins=45, color=LINE, alpha=0.8)
    ax.axvline(0, color=MUTED, lw=0.8)
    ax.set_xlabel("Daily change (%)")
    ax.set_ylabel("Sessions")
    ax.set_title("NIFTY 50 daily change distribution")
    ax.grid(alpha=0.25, lw=0.5, axis="y")
    save(fig, "figIDX04_returns",
         "Distribution of session-over-session change across %d sessions. Mean %.3f%%, "
         "standard deviation %.3f%%, minimum %.2f%%, maximum %.2f%%."
         % (len(r), r.mean(), r.std(ddof=1), r.min(), r.max()), PANEL)


def figure_evidence(g: pd.DataFrame) -> None:
    """Where the index window sits relative to what this project actually assessed."""
    from scripts.stages import live

    lo, hi = g["date"].min(), g["date"].max()
    corpus = live.text_corpus()
    docs = corpus[(corpus["date"] >= lo) & (corpus["date"] <= hi)]
    monthly = (docs.set_index("date").resample("ME").size()
               if len(docs) else pd.Series(dtype=int))

    scored_path = paths.ARTIFACTS / "experiments" / "per_row_FULL.parquet"
    scored = pd.read_parquet(scored_path) if scored_path.exists() else pd.DataFrame()

    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(8, 4.4), sharex=True,
        gridspec_kw={"height_ratios": [2, 1]})
    top.plot(g["date"], g["close"], color=LINE, lw=1.2)
    top.set_ylabel("NIFTY 50")
    top.grid(alpha=0.25, lw=0.5)
    top.set_title("Index window against this project's evidence and assessments")

    if len(monthly):
        bottom.bar(monthly.index, monthly.to_numpy(), width=20, color=MUTED, alpha=0.7)
    bottom.set_ylabel("Documents / month")
    bottom.grid(alpha=0.25, lw=0.5, axis="y")

    overlap = 0
    if len(scored):
        s_lo, s_hi = scored["date"].min(), scored["date"].max()
        overlap = int(((scored["date"] >= lo) & (scored["date"] <= hi)).sum())
        for ax in (top, bottom):
            ax.axvspan(s_lo, s_hi, color=WARN, alpha=0.12)
        top.text(0.02, 0.06,
                 "assessed sessions %s to %s — %s the index window"
                 % (str(s_lo.date()), str(s_hi.date()),
                    "overlapping" if overlap else "outside"),
                 transform=top.transAxes, fontsize=8, color=WARN)

    save(fig, "figIDX05_evidence",
         "The index series with the volume of aligned financial text beneath it, and "
         "the model's evaluation window shaded. %d of the assessed rows fall inside "
         "the index window: the assessed period and the index period %s. Evidence "
         "shown here is market context; none of it is attributed to the index, whose "
         "membership is not in the data."
         % (overlap, "overlap" if overlap else "do not overlap"), PANEL)


def statistics(g: pd.DataFrame) -> dict:
    r = g["return_pct"].dropna()
    worst = g.loc[g["drawdown"].idxmin()]
    return {
        "instrument_id": ix.PRIMARY,
        "instrument_type": "INDEX",
        "display_name": ix.INDEX_REGISTRY[ix.PRIMARY].display_name,
        "sessions": int(len(g)),
        "first_session": str(g["date"].min().date()),
        "last_session": str(g["date"].max().date()),
        "level": {
            "first": float(g["close"].iloc[0]),
            "last": float(g["close"].iloc[-1]),
            "min": float(g["close"].min()),
            "max": float(g["close"].max()),
            "total_change_pct": float(g["close"].iloc[-1] / g["close"].iloc[0] - 1.0),
        },
        "daily_change": {
            "n": int(len(r)),
            "mean": float(r.mean()),
            "sd": float(r.std(ddof=1)),
            "min": float(r.min()),
            "max": float(r.max()),
            "positive_sessions": int((r > 0).sum()),
            "negative_sessions": int((r < 0).sum()),
            "skew": float(r.skew()),
            "excess_kurtosis": float(r.kurtosis()),
        },
        "volatility": {
            "annualised_full_sample": float(np.log1p(r).std(ddof=1) * np.sqrt(252)),
            "rolling_20d_last": float(g["volatility_20d"].iloc[-1]),
            "rolling_20d_max": float(g["volatility_20d"].max()),
            "method": "sample sd of daily log returns, annualised by sqrt(252)",
        },
        "drawdown": {
            "worst": float(worst["drawdown"]),
            "worst_session": str(worst["date"].date()),
            "current": float(g["drawdown"].iloc[-1]),
            "method": "close over running maximum within this series, minus one",
            "caveat": "Measured within the ingested window, not all time.",
        },
        "coverage": ix.coverage(pd.read_parquet(PANEL), ix.PRIMARY),
        "not_computed_here": (
            "No index level is produced by this project. Every level is the one NSE "
            "published for the session."),
    }


def main() -> int:
    t0 = time.time()
    progress.log("[index artifacts]")
    if not PANEL.exists():
        progress.log("FAILED: %s is absent; run scripts/build_index_panel.py"
                     % _relative(PANEL))
        return 4

    OUT.mkdir(parents=True, exist_ok=True)
    panel = pd.read_parquet(PANEL)
    g = panel[panel["index_id"] == ix.PRIMARY].sort_values("date").reset_index(drop=True)
    if g.empty:
        progress.log("FAILED: no %s rows in the index panel" % ix.PRIMARY)
        return 4

    columns = ["date", "close", "prev_close", "change", "return_pct", "log_return",
               "volatility_20d", "drawdown", "high_52w", "low_52w"]
    g[columns].to_csv(OUT / "nifty50_returns.csv", index=False)
    progress.log("      wrote nifty50_returns.csv (%d rows)" % len(g))

    figure_level(g)
    figure_volatility(g)
    figure_drawdown(g)
    figure_returns(g)
    figure_evidence(g)

    stats = statistics(g)
    jsonio.write(OUT / "index_statistics.json", {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "environment": environment_snapshot(),
        "index_version": ix.INDEX_VERSION,
        "statistics": stats,
    })
    jsonio.write(FIGS / "figures.json", {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "figures": GENERATED,
    })

    progress.log("      %s: %d sessions, total change %+.2f%%, worst drawdown %.2f%%"
                 % (ix.PRIMARY, stats["sessions"],
                    100 * stats["level"]["total_change_pct"],
                    100 * stats["drawdown"]["worst"]))
    progress.log("wrote %d figures" % len(GENERATED))
    progress.log("elapsed %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
