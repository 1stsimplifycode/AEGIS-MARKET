"""Build the Week 2 market, liquidity and statistical foundation.

    python scripts/build_week2_foundation.py --acquire     # fetch intraday, then build
    python scripts/build_week2_foundation.py               # build from what is on disk

Vertical slices, in dependency order. Each stage writes a real artifact and the summary
records what was measured rather than what was intended:

    data/reference/intraday_bars.parquet          real intraday NSE OHLCV (redistributor)
    data/reference/realised_variance.parquet      RV at the selected sampling frequency
    data/reference/rv_frequency_selection.json    every candidate, and why one won
    data/reference/price_impact.parquet           per-security lambda WITH its std error
    data/reference/arrival_fits.parquet           per-security Poisson / NB fits
    data/reference/week2_overdispersion.json      the result Week 8 consumes
    data/reference/liquidity_state.parquet        the state vector, gate and attribution
    data/reference/week2_thresholds.json          conformal thresholds and their budget
    outputs/week2/foundation_summary.json         everything above, in one place

Nothing here fabricates data. If the intraday bars are absent the realised-variance and
price-impact stages are skipped and reported as skipped, and the stages that depend only
on the daily panel still run.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.core import paths  # noqa: E402
from research.detection import count_events as CE  # noqa: E402
from research.market import arrival as A  # noqa: E402
from research.market import liquidity as L  # noqa: E402
from research.market import price_impact as PI  # noqa: E402
from research.market import realised_variance as RV  # noqa: E402
from research.market import thresholds as TH  # noqa: E402
from research.reference import intraday as I  # noqa: E402
from research.reference import price_bands as PB  # noqa: E402
from research.reference import read_manifest, write_manifest  # noqa: E402

#: Daily window for the arrival model. Long enough for the dispersion test to have power.
ARRIVAL_FROM = "2024-01-01"


def universe_symbols() -> list[str]:
    uni = pd.read_parquet(paths.PANEL / "universe.parquet")
    last = uni["rebalance_date"].max()
    return uni[uni["rebalance_date"] == last].sort_values("rank")["symbol"].tolist()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--acquire", action="store_true",
                    help="fetch intraday bars before building")
    ap.add_argument("--arrival-from", default=ARRIVAL_FROM)
    args = ap.parse_args()

    paths.ensure_dirs()
    out = paths.REPO_ROOT / "outputs" / "week2"
    out.mkdir(parents=True, exist_ok=True)
    summary: dict = {"built_at": datetime.now(UTC).isoformat()}

    symbols = universe_symbols()
    print("universe: %d symbols" % len(symbols))

    # -- intraday -------------------------------------------------------------------
    if args.acquire:
        print("acquiring intraday bars ...")
        bars, source = I.acquire(symbols, intervals=("1m", "2m", "5m"))
        sources = [s for s in read_manifest() if s.input_id != "intraday_bars"]
        sources.append(source)
        write_manifest(sources)
        print("  %d bars, %s" % (len(bars), source.availability))

    try:
        bars = I.load()
    except I.IntradayUnavailable as exc:
        bars = pd.DataFrame()
        summary["intraday"] = {"available": False, "why": str(exc)}
        print("intraday bars unavailable: %s" % exc)

    rv_table = pd.DataFrame()
    estimates = pd.DataFrame()

    if not bars.empty:
        summary["intraday"] = {
            "available": True, "bars": int(len(bars)),
            "symbols": int(bars["symbol"].nunique()),
            "per_interval": {
                iv: {"bars": int((bars["interval"] == iv).sum()),
                     "sessions": int(bars.loc[bars["interval"] == iv,
                                              "session"].nunique())}
                for iv in sorted(bars["interval"].unique())},
            "basis": "THIRD_PARTY_REDISTRIBUTOR (not an NSE publication)",
        }

        # -- C1 realised variance ---------------------------------------------------
        print("C1: selecting the sampling frequency ...")
        finest = bars[bars["interval"] == "1m"]
        selection = RV.select_frequency(finest if not finest.empty else bars)
        (paths.REFERENCE / "rv_frequency_selection.json").write_text(
            json.dumps(selection.to_dict(), indent=2), encoding="utf-8")
        print("  selected %s minutes (target %s)"
              % (selection.selected_minutes, selection.target))

        if selection.selected_minutes:
            chosen = "%dm" % selection.selected_minutes
            at_freq = bars[bars["interval"] == chosen]
            # Fall back to aggregating the finest bars only if the vendor does not serve
            # the selected granularity directly; never to a different frequency.
            source_bars = at_freq if not at_freq.empty else finest
            rv_table = RV.session_realised_variance(source_bars,
                                                    selection.selected_minutes)
            rv_table.to_parquet(paths.REFERENCE / "realised_variance.parquet",
                                index=False)
            summary["c1_realised_variance"] = RV.summary(selection, rv_table)
            print("  %d session-level RV rows" % len(rv_table))
        else:
            summary["c1_realised_variance"] = {
                "selected_sampling_minutes": None,
                "why": "no candidate frequency met the pre-declared precision target",
                "precision_target": selection.target,
                "evaluations": selection.evaluations,
            }

        # -- C2 price impact --------------------------------------------------------
        print("C2: fitting price impact ...")
        minutes = selection.selected_minutes or 5
        pi_bars = bars[bars["interval"] == "%dm" % minutes]
        if pi_bars.empty:
            pi_bars = bars[bars["interval"] == "5m"]
        estimates = PI.fit_all(pi_bars)
        if not estimates.empty:
            PI.validate(estimates)
            estimates.to_parquet(paths.REFERENCE / "price_impact.parquet", index=False)
            summary["c2_price_impact"] = PI.summary(estimates, minutes)
            print("  %d estimates, all with standard errors" % len(estimates))

    # -- C5 arrival -----------------------------------------------------------------
    print("C5: fitting trade-arrival models ...")
    panel = pd.read_parquet(paths.PANEL / "cash_panel.parquet",
                            columns=["symbol", "date", "close", "turnover", "trades"])
    fits = A.fit_all(panel, symbols=symbols, date_from=args.arrival_from)
    fits.to_parquet(paths.REFERENCE / "arrival_fits.parquet", index=False)
    agg = A.aggregate_overdispersion(fits)
    summary["c5_arrival"] = A.summary(fits, agg)

    published = CE.save_week2_overdispersion(agg)
    summary["c5_arrival"]["published_for_week8"] = str(
        published.relative_to(paths.REPO_ROOT).as_posix())
    print("  Fano %.1f, sd inflation %.1f -> published to %s"
          % (agg.fano_factor, agg.sd_inflation(), published.name))

    # -- Amihud, from the daily panel over the same window --------------------------
    print("C3: Amihud over the arrival window ...")
    p = panel[panel["date"] >= pd.Timestamp(args.arrival_from)].copy()
    p = p[p["symbol"].isin(set(symbols))].sort_values(["symbol", "date"])
    p["ret_1d"] = p.groupby("symbol", sort=False)["close"].pct_change()
    p["illiq"] = p["ret_1d"].abs() / p["turnover"].replace(0, pd.NA)
    amihud = p.groupby("symbol")["illiq"].mean().astype(float)
    summary["c3_amihud"] = {
        "formula": "mean over the window of |r_t| / turnover_t",
        "window_sessions": 21,
        "cross_section_window": "%s .. %s" % (args.arrival_from,
                                              str(p["date"].max().date())),
        "fields": ["close -> ret_1d", "turnover (TOTTRDVAL / TtlTrfVal)"],
        "securities": int(amihud.notna().sum()),
        "median": float(amihud.median()),
        "basis": "DERIVED_FROM_EXCHANGE_DATA",
    }

    # -- C3 cross-check --------------------------------------------------------------
    cross = None
    if not estimates.empty:
        lam = estimates.set_index("symbol")["lambda"]
        cross = L.cross_check_rankings(amihud, lam)
        summary["c3_cross_check"] = cross.to_dict()
        print("  Spearman rho %.3f (p=%.4g, n=%d)"
              % (cross.spearman_rho, cross.spearman_p_value, cross.n))
    else:
        summary["c3_cross_check"] = {
            "available": False,
            "why": "no price-impact estimates; the cross-check needs both rankings"}

    # -- C6 liquidity state vector ---------------------------------------------------
    # One row per (symbol, session), not per symbol. The criterion asks for a vector
    # produced for observations, and a 50-row cross-section is also far too small to
    # calibrate a 1%-false-alarm threshold against -- the gate refuses it, correctly.
    print("C6: assembling the liquidity state vector ...")
    p = p.sort_values(["symbol", "date"])
    p["amihud_21"] = p.groupby("symbol", sort=False)["illiq"].transform(
        lambda s: s.rolling(21, min_periods=10).mean())
    daily = p[["symbol", "date", "amihud_21"]].rename(columns={"date": "session"})

    if not rv_table.empty:
        comp = rv_table[["symbol", "session", "realised_variance"]].copy()
        comp["session"] = pd.to_datetime(comp["session"])
        daily["session"] = pd.to_datetime(daily["session"])
        comp = comp.merge(daily, on=["symbol", "session"], how="left")
    else:
        comp = daily.copy()
    comp = comp.rename(columns={"amihud_21": "amihud"})

    # Security-level characteristics broadcast across that security's sessions: lambda
    # and the Fano factor are properties of the name, not of the day.
    comp["arrival_fano"] = comp["symbol"].map(
        fits.set_index("symbol")["fano_factor"])
    if not estimates.empty:
        comp["price_impact_lambda"] = comp["symbol"].map(
            estimates.set_index("symbol")["lambda"])

    state = L.build_state_vector(comp)
    gate = L.fit_stress_gate(state)
    state = gate.evaluate(state)
    state.to_parquet(paths.REFERENCE / "liquidity_state.parquet", index=False)
    summary["c6_liquidity_state"] = L.summary(state, gate, cross)
    print("  %d (symbol, session) states, gate fired on %d"
          % (len(state), int(state["stress_gate_fired"].sum())))

    # -- C4 thresholds on the Week 2 features ----------------------------------------
    print("C4: fitting distribution-free thresholds ...")
    feature_directions = {c: d for c, d in L.COMPONENTS.items() if c in state.columns}
    per_session = rv_table if not rv_table.empty else pd.DataFrame()
    detector = None
    if not per_session.empty:
        detector = TH.fit_detector(per_session, {"realised_variance": "upper"})
        summary["c4_thresholds"] = detector.to_dict()
        flagged = detector.detect(per_session)
        summary["c4_thresholds"]["applied_to"] = {
            "rows": int(len(flagged)),
            "anomalies": int(flagged["anomaly_any"].sum()),
            "realised_rate": float(flagged["anomaly_any"].mean()),
        }
        print("  budget alpha=%.3f -> %d anomalies in %d rows"
              % (detector.budget["alpha"], int(flagged["anomaly_any"].sum()),
                 len(flagged)))
    else:
        summary["c4_thresholds"] = {
            "available": False,
            "why": "no per-session feature series to calibrate on"}
    summary["c4_thresholds"]["stress_gate_threshold"] = gate.threshold.to_dict()
    summary["c4_thresholds"]["features_in_state_vector"] = list(feature_directions)

    # -- circuit-band history: an exchange fact the Week 2 layer actually consumes ----
    try:
        hits = PB.load()
        flags = PB.band_hit_flags(hits, symbols)
        summary["circuit_band_history"] = PB.summary(hits)
        summary["c6_liquidity_state"]["band_hit_validation"] = (
            L.validate_against_band_hits(state, flags))
        v = summary["c6_liquidity_state"]["band_hit_validation"]
        if v.get("available") and v.get("gate_fired"):
            print("  band-hit check: %.1f%% when stressed vs %.1f%% base"
                  % (v["band_hit_rate_when_gate_fired"] * 100,
                     v["band_hit_base_rate"] * 100))
    except PB.PriceBandsUnavailable as exc:
        summary["circuit_band_history"] = {"available": False, "why": str(exc)}

    (paths.REFERENCE / "week2_thresholds.json").write_text(
        json.dumps(summary["c4_thresholds"], indent=2, default=str), encoding="utf-8")

    # -- Week 8 consumption proof ----------------------------------------------------
    print("Week 8: running the count-event detector on the published result ...")
    week8 = CE.CountEventDetector.from_week2()
    detected = week8.detect(panel[panel["symbol"].isin(set(symbols))])
    summary["week8_integration"] = CE.summary(detected, week8)
    print("  %s" % summary["week8_integration"]["interpretation"])

    (out / "foundation_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print("\nsummary: %s" % (out / "foundation_summary.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
