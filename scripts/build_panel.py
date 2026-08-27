"""Build the AEGIS-Market cash-equity panel and the point-in-time research universe.

    python scripts/build_panel.py --start 2005-01-01 --end 2026-08-14

Writes ``data/panel/cash_panel.parquet`` and ``data/panel/universe.parquet`` plus a
coverage report. Nothing downstream reads the raw archive.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from research.core import paths
from research.core.manifest import environment_snapshot, file_hash
from research.data.nse_bhavcopy import build_panel
from research.data.quarantine import Quarantine
from research.data.universe import LiquidityProxyUniverse


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=_d, default=date(2005, 1, 1))
    ap.add_argument("--end", type=_d, default=date(2026, 8, 14))
    ap.add_argument("--universe-size", type=int, default=50)
    args = ap.parse_args()

    paths.ensure_dirs()
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    with Quarantine(run_id=run_id, source="nse_bhavcopy_cm") as quarantine:
        panel = build_panel(args.start, args.end, quarantine=quarantine)
    q_summary = quarantine.summary()
    print("\nquarantined %d records -> %s"
          % (q_summary["quarantined"], q_summary["path"] or "(nothing rejected)"))
    for reason, n in sorted(q_summary["by_reason"].items()):
        print("  %-26s %d" % (reason, n))

    out = paths.PANEL / "cash_panel.parquet"
    panel.to_parquet(out, index=False)
    print("\npanel written: %s (%.1f MB)" % (out, out.stat().st_size / 1e6))

    print("rows                 %d" % len(panel))
    print("symbols              %d" % panel["symbol"].nunique())
    print("sessions             %d" % panel["date"].nunique())
    print("date range           %s .. %s" % (panel["date"].min().date(),
                                             panel["date"].max().date()))
    trades_cov = panel["trades"].notna().mean()
    print("trades column cover  %.4f" % trades_cov)

    uni = LiquidityProxyUniverse(panel, size=args.universe_size)
    table = uni.build()
    upath = paths.PANEL / "universe.parquet"
    table.to_parquet(upath, index=False)
    stats = uni.turnover_stats()
    churn = uni.churn()
    print("\nuniverse written: %s" % upath)
    for k, v in stats.items():
        print("  %-24s %s" % (k, v))
    print("  %-24s %.2f" % ("mean entries/rebalance", churn["entries"].mean()))
    print("  %-24s %.2f" % ("mean exits/rebalance", churn["exits"].mean()))

    report = {
        "built_at": datetime.utcnow().isoformat() + "Z",
        "window": {"start": str(args.start), "end": str(args.end)},
        "panel": {
            "path": str(out),
            "sha256": file_hash(out),
            "rows": int(len(panel)),
            "symbols": int(panel["symbol"].nunique()),
            "sessions": int(panel["date"].nunique()),
            "first_session": str(panel["date"].min().date()),
            "last_session": str(panel["date"].max().date()),
            "trades_column_coverage": float(trades_cov),
            "series_retained": sorted(panel["series"].unique().tolist()),
        },
        "universe": {"path": str(upath), "sha256": file_hash(upath), **stats,
                     "mean_entries_per_rebalance": float(churn["entries"].mean()),
                     "mean_exits_per_rebalance": float(churn["exits"].mean())},
        "quarantine": q_summary,
        "environment": environment_snapshot(),
    }
    rp = paths.MANIFESTS / "panel_build.json"
    rp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("\nmanifest: %s" % rp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
