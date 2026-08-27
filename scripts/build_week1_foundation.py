"""Build every Week 1 market-intelligence artifact from what is already on disk.

    python scripts/build_week1_foundation.py

Does not re-download anything and does not rebuild the cash panel. It consumes the
acquired reference data (``research.reference.acquire``) plus the existing panel and
emits the derived artifacts the Week 1 criteria are judged on:

    data/reference/corporate_actions.parquet             parsed + reconciled actions
    data/reference/corporate_action_adjustments.parquet  the corroborated price factors
    data/reference/security_lifecycle.parquet            per-security lifecycle state
    data/reference/c7_status.json                        the twelve-input status report
    data/panel/index_reconciled.parquet                  divisor-maintained index levels
    data/panel/index_divisor_events.parquet              every divisor reset, with cause
    outputs/week1/foundation_summary.json                what this run produced
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.core import paths  # noqa: E402
from research.data import quarantine as Q  # noqa: E402
from research.market import index_construction as ic  # noqa: E402
from research.reference import corporate_actions as CA  # noqa: E402
from research.reference import index_methodology as IM  # noqa: E402
from research.reference import lifecycle as LC  # noqa: E402
from research.reference import registry, sessions  # noqa: E402


def main() -> int:
    paths.ensure_dirs()
    out = paths.REPO_ROOT / "outputs" / "week1"
    out.mkdir(parents=True, exist_ok=True)
    summary: dict = {"built_at": datetime.now(UTC).isoformat()}

    print("reading cash panel ...")
    panel = pd.read_parquet(paths.PANEL / "cash_panel.parquet",
                            columns=["symbol", "date", "series", "close",
                                     "prev_close", "event_time", "knowledge_time"])
    universe = pd.read_parquet(paths.PANEL / "universe.parquet")
    print("  %d rows, %d symbols" % (len(panel), panel["symbol"].nunique()))

    print("corporate actions: parsing and reconciling against the bhavcopy ...")
    summary["corporate_actions"] = CA.build(panel)
    print("  %d corroborated price-affecting actions"
          % summary["corporate_actions"]["price_affecting_corroborated"])

    print("security lifecycle ...")
    summary["lifecycle"] = LC.build_and_save(panel, universe)
    print("  %s" % summary["lifecycle"]["state_counts"])

    print("index: building with and without divisor reconciliation ...")
    adj = pd.read_parquet(paths.REFERENCE / "corporate_action_adjustments.parquet")
    good = ic.build_index(panel, universe, adj, reconcile_divisor=True)
    bad = ic.build_index(panel, universe, adj, reconcile_divisor=False)
    good.levels.to_parquet(paths.PANEL / "index_reconciled.parquet", index=False)
    pd.DataFrame([e.to_dict() for e in good.events]).to_parquet(
        paths.PANEL / "index_divisor_events.parquet", index=False)
    summary["index"] = good.to_summary()
    summary["index"]["unreconciled_max_abs_daily_log_return"] = float(
        bad.levels["logret_1d"].abs().max())
    summary["index"]["unreconciled_sessions_over_25pct"] = int(
        (bad.levels["logret_1d"].abs() > 0.25).sum())
    summary["index"]["reconciled_sessions_over_25pct"] = int(
        (good.levels["logret_1d"].abs() > 0.25).sum())
    print("  reconciled max |r| %.4f vs unreconciled %.4f"
          % (summary["index"]["max_abs_daily_log_return"],
             summary["index"]["unreconciled_max_abs_daily_log_return"]))

    print("reference status ...")
    registry.save()
    summary["c7"] = {k: v for k, v in registry.status_report().items()
                     if k != "inputs"}
    summary["index_review_cycle"] = IM.review_cycle()
    summary["sessions"] = sessions.to_dict()
    summary["quarantine"] = Q.summarise()

    (out / "foundation_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print("\nsummary: %s" % (out / "foundation_summary.json"))
    print("C7 delivered %d/12, fully satisfying %d/12"
          % (summary["c7"]["delivered"], summary["c7"]["fully_satisfying"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
