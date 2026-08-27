"""Build the NSE index panel and its data-quality report.

    python scripts/build_index_panel.py

Reads the derivatives bhavcopy archive in place, extracts every published index level it
carries, derives the series a level implies, and writes:

    data/panel/index_panel.parquet
    outputs/data_quality/nifty50_data_quality_report.json
    outputs/data_quality/nifty50_data_quality.csv

The raw archive is never copied into the repository: NSE publishes these files publicly
but does not licence redistribution, so this is an ingestion adapter and the parquet it
writes is a derived series with the restriction recorded on it.

The quality report is not decoration. An index panel assembled from six thousand daily
files can be wrong in ways that are invisible in a chart — a repeated session, a gap
nobody noticed, a level that moved twelve percent because a file was malformed — and each
of those is checked here by name.
"""
from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import environment_snapshot, git_commit  # noqa: E402
from research.data import nse_index as ix  # noqa: E402

OUT_PANEL = paths.PANEL / "index_panel.parquet"
OUT_QUALITY = paths.REPO_ROOT / "outputs" / "data_quality"

#: A session-over-session move larger than this is flagged for a human to look at. Indices
#: do move this much — 2020 had several — so it is a flag, never a filter.
JUMP_THRESHOLD = 0.10


def quality(frame: pd.DataFrame, index_id: str) -> dict:
    """Everything that could be wrong with one index's series, checked by name."""
    g = frame[frame["index_id"] == index_id].sort_values("date")
    close = pd.to_numeric(g["close"], errors="coerce")
    dates = pd.to_datetime(g["date"])

    duplicates = g[dates.duplicated(keep=False)]
    expected = pd.bdate_range(dates.min(), dates.max()) if len(dates) else []
    observed = set(dates.dt.normalize())
    missing = [str(d.date()) for d in expected if d not in observed]

    returns = close.pct_change()
    jumps = g.loc[returns.abs() > JUMP_THRESHOLD, ["date", "close"]].copy()
    jumps["return_pct"] = returns[returns.abs() > JUMP_THRESHOLD]

    return {
        "index_id": index_id,
        "sessions": int(len(g)),
        "first_session": str(dates.min().date()) if len(dates) else None,
        "last_session": str(dates.max().date()) if len(dates) else None,
        "duplicate_sessions": int(len(duplicates)),
        "duplicate_dates": sorted({str(d.date()) for d in duplicates["date"]}),
        "missing_business_days": len(missing),
        # Exchange holidays are business days with no session, so this count is expected
        # to be non-zero. It is reported rather than silenced because a sudden change in
        # it is the signal that something went wrong upstream.
        "missing_business_days_note": (
            "Business days with no session. NSE observes roughly a dozen trading "
            "holidays a year, so a non-zero count is normal; a jump in it is not."),
        "missing_dates_sample": missing[:20],
        "null_closes": int(close.isna().sum()),
        "non_positive_closes": int((close <= 0).sum()),
        "large_moves": int(len(jumps)),
        "large_move_threshold": JUMP_THRESHOLD,
        "large_move_rows": [
            {"date": str(pd.Timestamp(r.date).date()),
             "close": float(r.close),
             "return_pct": float(r.return_pct)}
            for r in jumps.itertuples(index=False)
        ],
        "min_close": float(close.min()) if len(close) else None,
        "max_close": float(close.max()) if len(close) else None,
        "distinct_source_files": int(g["source_file"].nunique()),
        "timezone_note": (
            "Dates are the exchange's trading date as printed in the bhavcopy, with no "
            "timezone conversion applied. A session is a date, not an instant."),
    }


def main() -> int:
    t0 = time.time()
    progress.log("[index panel]")
    OUT_QUALITY.mkdir(parents=True, exist_ok=True)
    paths.PANEL.mkdir(parents=True, exist_ok=True)

    try:
        frame = ix.ingest(log=progress.log)
    except ix.IndexDataUnavailable as exc:
        progress.log("FAILED: %s" % exc)
        return 4

    frame.to_parquet(OUT_PANEL, index=False)
    progress.log("      wrote %s (%d rows)"
                 % (OUT_PANEL.relative_to(paths.REPO_ROOT).as_posix(), len(frame)))

    reports = {i: quality(frame, i) for i in sorted(frame["index_id"].unique())}
    primary = reports.get(ix.PRIMARY, {})

    rows = []
    for index_id, r in reports.items():
        rows.append({
            "index_id": index_id,
            "display_name": ix.INDEX_REGISTRY[index_id].display_name,
            "sessions": r["sessions"],
            "first_session": r["first_session"],
            "last_session": r["last_session"],
            "duplicate_sessions": r["duplicate_sessions"],
            "missing_business_days": r["missing_business_days"],
            "null_closes": r["null_closes"],
            "non_positive_closes": r["non_positive_closes"],
            "large_moves": r["large_moves"],
            "min_close": r["min_close"],
            "max_close": r["max_close"],
        })
    pd.DataFrame(rows).to_csv(OUT_QUALITY / "nifty50_data_quality.csv", index=False)

    jsonio.write(OUT_QUALITY / "nifty50_data_quality_report.json", {
        "index_version": ix.INDEX_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "environment": environment_snapshot(),
        "primary_index": ix.PRIMARY,
        "coverage": ix.coverage(frame, ix.PRIMARY),
        "registry": {i: s.to_dict() for i, s in ix.INDEX_REGISTRY.items()},
        "per_index": reports,
        "checks_performed": [
            "duplicate sessions", "missing business days", "null closes",
            "non-positive closes", "unexpected session-over-session moves",
            "single unambiguous level per session per index",
            "trading-date normalisation without timezone conversion",
        ],
        "reconstruction_policy": (
            "No index level is computed by this project. Where the source carries no "
            "level, the series is absent rather than reconstructed from futures prices "
            "or from constituent closes."),
    })

    if primary:
        progress.log("      %s: %d sessions, %s to %s, %d duplicates, %d nulls, "
                     "%d large moves"
                     % (ix.PRIMARY, primary["sessions"], primary["first_session"],
                        primary["last_session"], primary["duplicate_sessions"],
                        primary["null_closes"], primary["large_moves"]))
    last = frame[frame["index_id"] == ix.PRIMARY].sort_values("date").iloc[-1]
    progress.log("      %s close %.2f on %s"
                 % (ix.PRIMARY, float(last["close"]),
                    str(pd.Timestamp(last["date"]).date())))
    progress.log("elapsed %.1fs" % (time.time() - t0))
    return 0 if not np.isnan(float(last["close"])) else 1


if __name__ == "__main__":
    raise SystemExit(main())
