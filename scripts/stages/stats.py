"""STATS module adapters (STATS-01 .. STATS-16).

Each function wraps canonical code. Read the manifest entry beside a function to see which
implementation it calls; nothing here reimplements a statistic.

Three of the sixteen are ``INFRASTRUCTURE_ONLY`` because the science genuinely does not
exist in the repository yet — verified by inspection, not assumed. Those return NOT YET
EXECUTED and write nothing.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from research.core import jsonio, paths
from scripts.stages import (
    OK,
    AnalysisResult,
    StageResult,
    insufficient,
    metric,
    require,
    series,
)

DATASET = paths.PANEL / "multimodal_dataset.parquet"
PER_ROW = paths.ARTIFACTS / "experiments" / "per_row_FULL.parquet"

#: How many instruments STATS-06 will correlate at once. Pairs grow quadratically, and an
#: unbounded request over the whole universe is minutes of work for a table nobody reads.
MAX_CORRELATED = 40


def _out(slug: str) -> Path:
    d = paths.REPO_ROOT / "outputs" / "stats" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


# ------------------------------------------------------------------- STATS-01 ----

def block_coverage(df: pd.DataFrame) -> pd.DataFrame:
    """Per-block feature presence and mean fill, over whatever rows are handed in.

    Shared by the regenerating adapter and the live analysis so the two cannot compute
    coverage differently. It takes a frame rather than reading one, which is the whole
    reason the same function can serve a full-panel regeneration and a user-selected
    slice.
    """
    from research.data import dataset as ds

    rows = []
    for block, cols in ds.MODALITY_BLOCKS.items():
        present = [c for c in cols if c in df.columns]
        rows.append({
            "block": block,
            "declared_features": len(cols),
            "present_in_dataset": len(present),
            "mean_non_null_fraction": float(df[present].notna().mean().mean())
            if present and len(df) else 0.0,
        })
    return pd.DataFrame(rows)


def integrity_profile(df: pd.DataFrame) -> dict:
    """Structural profile of a frame: counts, key uniqueness, splits, class balance."""
    from research.market import features as mf

    key = ["symbol", "date"]
    return {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "instruments": int(df["symbol"].nunique()),
        "date_range": [str(df["date"].min().date()), str(df["date"].max().date())]
        if len(df) else [None, None],
        "duplicate_keys": int(df.duplicated(subset=key).sum()),
        "split_sizes": {str(k): int(v) for k, v in df["split"].value_counts().items()}
        if "split" in df.columns else "NOT PRESENT",
        "positive_rate": float(df["is_episode"].mean())
        if "is_episode" in df.columns and len(df) else None,
        "all_null_columns": sorted(c for c in df.columns if df[c].isna().all()),
        "coverage_report_available": hasattr(mf, "coverage_report"),
    }


def data_integrity_profile(force: bool = False) -> StageResult:
    """Wraps research.market.features.coverage_report + the block definitions."""
    if (r := require([DATASET])):
        return r
    df = pd.read_parquet(DATASET)
    out = _out("01_data_integrity_profile")

    cov = block_coverage(df)
    cov.to_csv(out / "block_coverage.csv", index=False)
    profile = integrity_profile(df)
    jsonio.write(out / "profile.json", profile)
    return StageResult(OK, "%d rows x %d cols, %d instruments, %d duplicate keys"
                       % (profile["rows"], profile["columns"],
                          profile["instruments"], profile["duplicate_keys"]),
                       outputs=[str(out / "profile.json"),
                                str(out / "block_coverage.csv")],
                       detail=profile)


# ------------------------------------------------------------------- STATS-02 ----

def universe_survivorship(force: bool = False) -> StageResult:
    """Wraps research.data.universe (membership table already built)."""
    upath = paths.PANEL / "universe.parquet"
    if (r := require([upath])):
        return r
    out = _out("02_universe_survivorship")
    members = pd.read_parquet(upath)

    date_col = ("rebalance_date" if "rebalance_date" in members.columns
                else members.columns[0])
    per_rebalance = members.groupby(date_col)["symbol"].nunique()
    prev, entries, exits = None, [], []
    for _d, grp in members.groupby(date_col):
        cur = set(grp["symbol"])
        if prev is not None:
            entries.append(len(cur - prev))
            exits.append(len(prev - cur))
        prev = cur
    churn = pd.DataFrame({"entries": entries, "exits": exits})
    churn.to_csv(out / "churn.csv", index=False)

    summary = {
        "rebalances": int(members[date_col].nunique()),
        "distinct_members_ever": int(members["symbol"].nunique()),
        "members_per_rebalance_mean": float(per_rebalance.mean()),
        "mean_entries_per_rebalance": float(np.mean(entries)) if entries else None,
        "mean_exits_per_rebalance": float(np.mean(exits)) if exits else None,
        "is_index_membership": False,
        "caveat": "Point-in-time liquidity-proxy universe. Never the Nifty 50 (L-01).",
    }
    jsonio.write(out / "universe_summary.json", summary)
    return StageResult(OK, "%d rebalances, %d distinct ever, %.2f entries/rebalance"
                       % (summary["rebalances"], summary["distinct_members_ever"],
                          summary["mean_entries_per_rebalance"] or float("nan")),
                       outputs=[str(out / "universe_summary.json"),
                                str(out / "churn.csv")], detail=summary)


# ------------------------------------------------------------------- STATS-03 ----

def descriptive_distributions(force: bool = False) -> StageResult:
    """Wraps the block definitions; descriptive statistics via pandas."""
    if (r := require([DATASET])):
        return r
    from research.data import dataset as ds

    df = pd.read_parquet(DATASET)
    out = _out("03_descriptive_distributions")
    block_of = {c: b for b, cols in ds.MODALITY_BLOCKS.items() for c in cols}

    rows = []
    for c in ds.ALL_FEATURES:
        if c not in df.columns:
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        rows.append({
            "feature": c, "block": block_of.get(c, "?"),
            "non_null_fraction": float(s.notna().mean()),
            "n_distinct": int(s.nunique(dropna=True)),
            "mean": float(s.mean()), "std": float(s.std()),
            "min": float(s.min()), "p50": float(s.median()), "max": float(s.max()),
        })
    tbl = pd.DataFrame(rows)
    tbl.to_csv(out / "feature_summary.csv", index=False)

    # A feature with one distinct value cannot inform anything; one with a zero standard
    # deviation is the same condition seen from the other side. Both are surfaced rather
    # than left to be discovered as an unexplained zero importance later.
    degenerate = tbl[(tbl["n_distinct"] <= 1) | (tbl["std"].fillna(0) == 0)]
    degenerate.to_csv(out / "degenerate_features.csv", index=False)
    return StageResult(OK, "%d features profiled, %d degenerate"
                       % (len(tbl), len(degenerate)),
                       outputs=[str(out / "feature_summary.csv"),
                                str(out / "degenerate_features.csv")],
                       detail={"n_features": len(tbl), "n_degenerate": len(degenerate)})


# ------------------------------------------------------------------- STATS-04 ----

def market_microstructure(force: bool = False) -> StageResult:
    """Wraps research.market.features (feature lists + the NOT MEASURED register)."""
    if (r := require([DATASET])):
        return r
    from research.market import features as mf

    df = pd.read_parquet(DATASET)
    out = _out("04_market_microstructure")
    rows = []
    for name, cols in (("market", mf.MARKET_FEATURES),
                       ("microstructure_proxy", mf.MICROSTRUCTURE_PROXIES)):
        for c in cols:
            if c not in df.columns:
                rows.append({"group": name, "feature": c, "present": False})
                continue
            s = pd.to_numeric(df[c], errors="coerce")
            rows.append({"group": name, "feature": c, "present": True,
                         "non_null_fraction": float(s.notna().mean()),
                         "std": float(s.std())})
    pd.DataFrame(rows).to_csv(out / "market_coverage.csv", index=False)
    jsonio.write(out / "not_measured.json", {
        "not_measured": mf.MICROSTRUCTURE_NOT_MEASURED,
        "caveat": "Daily-bar proxies are not order-book microstructure (L-02).",
    })
    return StageResult(OK, "%d market + %d microstructure-proxy features; %d quantities "
                       "recorded NOT MEASURED"
                       % (len(mf.MARKET_FEATURES), len(mf.MICROSTRUCTURE_PROXIES),
                          len(mf.MICROSTRUCTURE_NOT_MEASURED)),
                       outputs=[str(out / "market_coverage.csv"),
                                str(out / "not_measured.json")])


# ------------------------------------------------------------------- STATS-05 ----

def regime_statistics(force: bool = False) -> StageResult:
    """Wraps the regime labels already assembled into the dataset."""
    if (r := require([DATASET])):
        return r
    df = pd.read_parquet(DATASET)
    if "regime_id" not in df.columns:
        return StageResult(4, "regime_id absent from the dataset")
    out = _out("05_regime_statistics")

    occ = (df.groupby("regime_id").size().rename("rows").reset_index())
    occ["share"] = occ["rows"] / occ["rows"].sum()
    if "is_episode" in df.columns:
        occ = occ.merge(df.groupby("regime_id")["is_episode"].mean()
                        .rename("positive_rate").reset_index(), on="regime_id")
    occ.to_csv(out / "regime_occupancy.csv", index=False)
    return StageResult(OK, "%d regimes, largest holds %.1f%% of rows"
                       % (len(occ), 100 * occ["share"].max()),
                       outputs=[str(out / "regime_occupancy.csv")])


# ------------------------------------------------------------------- STATS-06 ----

def dependence_propagation(force: bool = False) -> StageResult:
    """Wraps research.propagation.graph (feature register + assembled coverage)."""
    if (r := require([DATASET])):
        return r
    from research.propagation import graph as pg

    df = pd.read_parquet(DATASET)
    out = _out("06_dependence_propagation")
    present = [c for c in pg.PROPAGATION_FEATURES if c in df.columns]
    summary = {
        "propagation_features_declared": list(pg.PROPAGATION_FEATURES),
        "present_in_dataset": present,
        "mean_non_null_fraction": float(df[present].notna().mean().mean())
        if present else 0.0,
        "per_feature_mean": {c: float(pd.to_numeric(df[c], errors="coerce").mean())
                             for c in present},
        "caveat": "Statistical co-movement, not causal propagation (L-07).",
    }
    jsonio.write(out / "graph_summary.json", summary)
    return StageResult(OK, "%d propagation features present, mean coverage %.3f"
                       % (len(present), summary["mean_non_null_fraction"]),
                       outputs=[str(out / "graph_summary.json")], detail=summary)


# ------------------------------------------------------------------- STATS-07 ----

def tail_extreme_risk(force: bool = False) -> StageResult:
    """Wraps research.risk.gate.tail_metrics.

    ``tail_metrics`` expects a **net return series**: it compounds its input with
    ``cumprod(1 + r)`` to build an equity curve. An earlier version of this adapter passed
    the integrity-risk score instead, which is bounded in [0, 1] and strictly positive, so
    the equity curve diverged and the record came back with ``total_return = Infinity``.
    The forward return is therefore built here exactly as the canonical
    capital-consequence path builds it in ``scripts/generate_paper_artifacts.py``:
    next-session percentage change in close, per instrument.
    """
    cash = paths.PANEL / "cash_panel.parquet"
    if (r := require([PER_ROW, cash])):
        return r
    from research.risk import gate

    scored = pd.read_parquet(PER_ROW)
    out = _out("07_tail_extreme_risk")

    panel = pd.read_parquet(cash, columns=["symbol", "date", "close"])
    fwd = panel.sort_values(["symbol", "date"]).copy()
    fwd["fwd_ret"] = fwd.groupby("symbol")["close"].pct_change().shift(-1)
    merged = (scored.merge(fwd[["symbol", "date", "fwd_ret"]], on=["symbol", "date"],
                           how="left").dropna(subset=["fwd_ret"]))
    if len(merged) < 20:
        return StageResult(4, "only %d rows carry a forward return; tail_metrics needs "
                              "at least 20" % len(merged))

    net = merged["fwd_ret"].to_numpy(float)
    metrics = gate.tail_metrics(net[np.isfinite(net)])
    metrics["series"] = "next-session return of the scored instrument-days"
    metrics["n_scored_rows"] = int(len(scored))
    metrics["n_rows_with_forward_return"] = int(len(merged))
    metrics["note"] = ("Unconditional tail statistics of the realised return over the "
                       "scored rows. This is the input distribution the exposure gate "
                       "acts on, not the result of applying it, and no allocation or "
                       "position size is produced anywhere in this module.")

    # Corporate-action diagnostic. The close series is not adjusted for splits and
    # bonuses, so a 10:1 split reads as a -90% session. One such row is enough to
    # dominate a drawdown statistic, and reporting max_drawdown without saying so would
    # be reporting a corporate action as a market loss. The metric is left untouched and
    # the contamination is reported beside it: see KI-06.
    extreme = merged.loc[merged["fwd_ret"].abs() > 0.5, ["symbol", "date", "fwd_ret"]]
    clean = merged.loc[merged["fwd_ret"].abs() <= 0.5, "fwd_ret"]
    metrics["corporate_action_suspects"] = {
        "threshold_abs_return": 0.5,
        "n_rows": int(len(extreme)),
        "rows": [{"symbol": str(r.symbol), "date": str(pd.Timestamp(r.date).date()),
                  "fwd_ret": float(r.fwd_ret)} for r in extreme.itertuples(index=False)],
        "worst_day_excluding_suspects": float(clean.min()) if len(clean) else None,
        "caveat": ("Prices are unadjusted for splits and bonuses. Rows above the "
                   "threshold are almost certainly corporate actions rather than "
                   "returns, and max_drawdown and worst_day above are contaminated by "
                   "them. Tracked as KI-06; the metric is reported unmodified so it "
                   "stays comparable with the existing capital-consequence path, which "
                   "builds its return series the same way."),
    }
    jsonio.write(out / "tail_metrics.json", metrics)
    return StageResult(OK, "tail metrics over %d of %d scored rows (CVaR %.5f)"
                       % (len(merged), len(scored), metrics["cvar"]),
                       outputs=[str(out / "tail_metrics.json")], detail=metrics)


# ------------------------------------------------------------------- STATS-08 ----

def episode_event_statistics(force: bool = False) -> StageResult:
    """Wraps the injected-episode labels produced by research.detection.episodes."""
    epath = paths.PANEL / "episode_labels.parquet"
    if (r := require([epath])):
        return r
    lab = pd.read_parquet(epath)
    out = _out("08_episode_event_statistics")
    summary: dict = {"rows": int(len(lab)), "columns": sorted(lab.columns)}
    if "episode_id" in lab.columns:
        summary["episodes"] = int(lab["episode_id"].nunique())
    if "symbol" in lab.columns:
        summary["instruments_with_episodes"] = int(lab["symbol"].nunique())
    for c in ("intensity", "duration", "n_sessions"):
        if c in lab.columns:
            s = pd.to_numeric(lab[c], errors="coerce")
            summary[c] = {"mean": float(s.mean()), "min": float(s.min()),
                          "max": float(s.max())}
    summary["caveat"] = ("Episodes are synthetic, injected into real price data (L-04). "
                         "No result from them describes real-world manipulation.")

    # Additive: the count-based event detector, which consumes the Week 2 arrival
    # dispersion. The synthetic-episode summary above is unchanged; this is a second,
    # independent view of the same week built on real exchange trade counts. If Week 2
    # has not published its result the block reports that rather than falling back to a
    # Poisson band this repository has measured to be wrong.
    outputs = [str(out / "episode_summary.json")]
    try:
        from research.detection import count_events as ce

        detector = ce.CountEventDetector.from_week2()
        counts = pd.read_parquet(paths.PANEL / "cash_panel.parquet",
                                 columns=["symbol", "date", "trades"])
        uni = pd.read_parquet(paths.PANEL / "universe.parquet")
        members = set(uni[uni["rebalance_date"] == uni["rebalance_date"].max()]["symbol"])
        detected = detector.detect(counts[counts["symbol"].isin(members)])
        summary["count_events"] = ce.summary(detected, detector)
        jsonio.write(out / "count_event_summary.json", summary["count_events"])
        outputs.append(str(out / "count_event_summary.json"))
    except ce_missing_week2() as exc:            # noqa: F821 - resolved below
        summary["count_events"] = {
            "available": False,
            "why": str(exc),
            "remedy": "Run scripts/build_week2_foundation.py to publish the Week 2 "
                      "arrival-dispersion result.",
        }

    jsonio.write(out / "episode_summary.json", summary)
    return StageResult(OK, "%d label rows, %s episodes"
                       % (summary["rows"], summary.get("episodes", "?")),
                       outputs=outputs, detail=summary)


def ce_missing_week2():
    """The exception the count detector raises when Week 2 has not published.

    Resolved lazily so that importing this module does not require the Week 2 package to
    be importable, which keeps the existing STATS-08 path working on a checkout where the
    market foundation has not been built.
    """
    from research.detection.count_events import MissingWeek2Input
    return MissingWeek2Input


# ------------------------------------------------------------------- STATS-09 ----

def leakage_verification(force: bool = False) -> StageResult:
    """Wraps tests/leakage — the L1-L6 suite, run read-only."""
    out = _out("09_leakage_verification")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/leakage", "-q", "--no-header"],
        cwd=str(paths.REPO_ROOT), capture_output=True, text=True)
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    report = {"returncode": proc.returncode, "summary": tail,
              "suite": "tests/leakage (L1-L6)",
              "interpretation": "A non-zero return code invalidates every downstream "
                                "result, which is why this suite is blocking in CI."}
    jsonio.write(out / "leakage_report.json", report)
    return StageResult(OK if proc.returncode == 0 else 1,
                       tail or "pytest produced no summary",
                       outputs=[str(out / "leakage_report.json")], detail=report)


# ------------------------------------------------------------------- STATS-10 ----

def validation_verification(force: bool = False) -> StageResult:
    """Wraps research.evaluation.metrics.verification_report.

    The operating threshold is **read from the experiment bundle**, where it was selected
    on the training split. Recomputing it here from the evaluation scores would be
    threshold-provenance leakage (L6) and would quietly flatter every metric below.
    """
    if (r := require([PER_ROW])):
        return r
    from research.evaluation import metrics as mx

    bundles = sorted((paths.REPORTS).glob("*FULL*/metrics.json"))
    if not bundles:
        return StageResult(4, "no FULL experiment bundle under %s; the train-selected "
                              "threshold is unavailable and this module will not choose "
                              "one on the evaluation split" % paths.REPORTS)
    bundle = json.loads(bundles[0].read_text(encoding="utf-8"))
    threshold = bundle.get("detection", {}).get("threshold")
    if threshold is None:
        return StageResult(4, "the FULL bundle records no threshold")

    scored = pd.read_parquet(PER_ROW)
    out = _out("10_validation_verification")
    y = scored["is_episode"].to_numpy(int)
    p = scored["integrity_risk"].to_numpy(float)

    report = mx.verification_report(y, p, float(threshold))
    report["threshold_source"] = str(bundles[0].relative_to(paths.REPO_ROOT).as_posix())
    report["metrics_version"] = mx.METRICS_VERSION
    mx.confusion_matrix_frame(y, p, float(threshold)).to_csv(
        out / "confusion_matrix.csv")
    mx.per_class_report(y, p, float(threshold)).to_csv(
        out / "per_class.csv", index=False)
    jsonio.write(out / "verification_metrics.json", report)

    m = report["metrics"]
    return StageResult(OK, "n=%d thr=%.4f  TP=%d TN=%d FP=%d FN=%d  acc=%.4f "
                       "bal_acc=%.4f MCC=%.4f"
                       % (m["n"], m["threshold"], m["tp"], m["tn"], m["fp"], m["fn"],
                          m["accuracy"], m["balanced_accuracy"], m["mcc"]),
                       outputs=[str(out / "verification_metrics.json"),
                                str(out / "confusion_matrix.csv"),
                                str(out / "per_class.csv")],
                       detail=m)


# ------------------------------------------------------------------- STATS-11 ----

def calibration_uncertainty(force: bool = False) -> StageResult:
    """Wraps evaluation.metrics + information (reliability, ECE, selective risk)."""
    if (r := require([PER_ROW])):
        return r
    from research.evaluation import information as inf
    from research.evaluation import metrics as mx

    scored = pd.read_parquet(PER_ROW)
    out = _out("11_calibration_uncertainty")
    y = scored["is_episode"].to_numpy(int)
    p = scored["integrity_risk"].to_numpy(float)

    rel = mx.reliability_curve(y, p)
    rel.to_csv(out / "reliability.csv", index=False)
    payload = {
        "ece": mx.expected_calibration_error(y, p),
        "detection": mx.detection_metrics(y, p),
        "caveat": "The risk score is not a calibrated probability (L-10).",
    }
    if "uncertainty" in scored.columns:
        sel = inf.selective_risk(y, p, scored["uncertainty"].to_numpy(float))
        sel.to_csv(out / "selective_risk.csv", index=False)
        payload["selective_risk_rows"] = int(len(sel))
    jsonio.write(out / "calibration.json", payload)
    return StageResult(OK, "ECE %.4f over %d rows" % (payload["ece"], len(scored)),
                       outputs=[str(out / "reliability.csv"),
                                str(out / "calibration.json")])


# ------------------------------------------------------------------- STATS-12 ----

def error_analysis(force: bool = False) -> StageResult:
    """Wraps research.evaluation.metrics.classify_errors."""
    if (r := require([PER_ROW])):
        return r
    from research.evaluation import metrics as mx

    scored = pd.read_parquet(PER_ROW)
    out = _out("12_error_analysis")
    y = scored["is_episode"].to_numpy(int)
    p = scored["integrity_risk"].to_numpy(float)
    thr = mx.best_f1_threshold(y, p)
    tax = mx.classify_errors(scored, thr)
    tax.to_csv(out / "error_taxonomy.csv", index=False)
    return StageResult(OK, "error taxonomy at threshold %.3f (%d rows)" % (thr, len(tax)),
                       outputs=[str(out / "error_taxonomy.csv")],
                       detail={"threshold": float(thr)})


# ------------------------------------------------------------- STATS-13 / 14 ----

def _run_experiments(label: str) -> StageResult:
    """Both baseline comparison and the ablation study come from one runner.

    Kept as a single invocation deliberately: running it twice would fit the same arms
    twice and produce two artifact sets that could silently disagree.
    """
    proc = subprocess.run([sys.executable, "scripts/run_experiments.py"],
                          cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        return StageResult(1, "scripts/run_experiments.py exited %d" % proc.returncode)
    return StageResult(OK, "%s regenerated via scripts/run_experiments.py" % label,
                       outputs=[str(paths.ARTIFACTS / "experiments")])


def baseline_comparison(force: bool = False) -> StageResult:
    return _run_experiments("baseline comparison")


def ablation_study(force: bool = False) -> StageResult:
    return _run_experiments("ablation study")


# ------------------------------------------------------------------- STATS-15 ----

def robustness_generalization(force: bool = False) -> StageResult:
    """Wraps scripts/run_robustness_generalization.py.

    Runs the whole sweep rather than reading a cached artifact, for the same reason
    STATS-13/14 does: a module that reports numbers it did not produce cannot tell a stale
    artifact from a current one.
    """
    out = paths.REPO_ROOT / "outputs" / "stats" / "15_robustness_generalization"
    proc = subprocess.run(
        [sys.executable, "scripts/run_robustness_generalization.py", "--all"],
        cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        return StageResult(1, "scripts/run_robustness_generalization.py exited %d"
                           % proc.returncode)

    summary = json.loads((out / "run.json").read_text(encoding="utf-8"))
    worst = summary.get("worst_degradation") or {}
    period = summary.get("period_transfer") or {}
    instrument = summary.get("instrument_transfer") or {}
    return StageResult(
        OK,
        "%d robustness rows, %d generalization rows; worst degradation %s at %.2f "
        "(auprc %.4f); period transfer auprc %.4f, instrument transfer auprc %.4f; "
        "%d holdout rows untouched"
        % (summary.get("robustness_rows", 0), summary.get("generalization_rows", 0),
           worst.get("corruption", "-"), worst.get("severity", 0.0),
           worst.get("auprc", float("nan")),
           period.get("auprc_mean", float("nan")),
           instrument.get("auprc_mean", float("nan")),
           summary.get("n_rows_frozen_and_unused", 0)),
        outputs=[str(out / "robustness.csv"), str(out / "generalization.csv"),
                 str(out / "run.json")],
        detail=summary)


# ------------------------------------------------------------------- STATS-16 ----

def multiseed_significance(force: bool = False) -> StageResult:
    """Wraps scripts/run_multiseed.py."""
    out = paths.REPO_ROOT / "outputs" / "stats" / "16_multiseed_significance"
    proc = subprocess.run([sys.executable, "scripts/run_multiseed.py"],
                          cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        return StageResult(1, "scripts/run_multiseed.py exited %d" % proc.returncode)

    summary = json.loads((out / "significance.json").read_text(encoding="utf-8"))
    floor = summary.get("seed_noise_floor") or {}
    survives = summary.get("differences_surviving_correction") or []
    dissolves = summary.get("differences_within_seed_noise") or []
    return StageResult(
        OK,
        "%d arms x %d seeds (%d/%d fits OK); pooled seed sd %.5f, 95%% noise floor "
        "%.5f auprc; %d of %d arm differences survive Benjamini-Hochberg, %d dissolve "
        "into seed variance"
        % (summary.get("n_arms", 0), summary.get("n_seeds", 0),
           summary.get("n_fits_ok", 0), summary.get("n_fits", 0),
           floor.get("pooled_seed_sd", float("nan")),
           floor.get("noise_floor_95", float("nan")),
           len(survives), len(survives) + len(dissolves), len(dissolves)),
        outputs=[str(out / "seed_table.csv"), str(out / "significance.json"),
                 str(out / "seed_summary.csv"), str(out / "paired_tests.csv")],
        detail=summary)


# -- live analysis -------------------------------------------------------------------
#
# These run on request, over the slice the caller selected, and write nothing. They call
# the same functions the regenerating adapters above call; what differs is that a slice
# arrives as validated parameters and no artifact is touched.


def analyse_data_integrity(date_from: str | None = None, date_to: str | None = None,
                           instruments: list[str] | None = None,
                           split: str = "all") -> AnalysisResult:
    """STATS-01 live: profile the slice the caller selected.

    Same block-coverage and structural-profile functions the regenerating adapter uses,
    over a filtered frame. A caller asking about January 2022 for three instruments gets
    the coverage of those rows, computed now, and not the whole-panel figure with a
    filter applied to the label.
    """
    from scripts.stages import live

    df = live.slice_frame(live.panel(), date_from, date_to, instruments, split)
    if len(df) < live.MIN_ROWS:
        return insufficient(
            "the selected slice holds %d rows, below the %d needed for a coverage "
            "profile to mean anything" % (len(df), live.MIN_ROWS),
            "Widen the date range, or select more instruments.")

    profile = integrity_profile(df)
    cov = block_coverage(df).sort_values("mean_non_null_fraction", ascending=False)
    thin = cov[cov["mean_non_null_fraction"] < 0.9]

    metrics = [
        metric("rows", "Rows in this slice", profile["rows"], "int",
               "instrument-days matching your selection"),
        metric("instruments", "Instruments", profile["instruments"], "int",
               "distinct symbols in the slice"),
        metric("columns", "Columns", profile["columns"], "int",
               "features plus metadata"),
        metric("duplicate_keys", "Duplicate keys", profile["duplicate_keys"], "int",
               "symbol-date pairs appearing twice; zero is the only acceptable value"),
        metric("positive_rate", "Episode rate", profile["positive_rate"], "pct",
               "share of rows inside an injected episode (limitation L-04)"),
        metric("blocks_thin", "Blocks below 90% fill", int(len(thin)), "int",
               "modality blocks whose mean fill is under 0.9 on this slice"),
    ]
    observations = [
        "Coverage was computed on the %d rows you selected, not on the whole panel."
        % profile["rows"],
        "Key uniqueness holds: %d duplicate symbol-date pairs."
        % profile["duplicate_keys"],
    ]
    if len(thin):
        observations.append(
            "Thinnest block on this slice: %s at %.1f%% mean fill."
            % (thin.iloc[-1]["block"],
               100 * float(thin.iloc[-1]["mean_non_null_fraction"])))
    else:
        observations.append("Every modality block is at or above 90% mean fill here.")
    if profile["all_null_columns"]:
        observations.append(
            "%d column(s) are entirely empty on this slice: %s."
            % (len(profile["all_null_columns"]),
               ", ".join(profile["all_null_columns"][:6])))

    return AnalysisResult(
        dataset=live.describe_slice(
            df, "data/panel/multimodal_dataset.parquet",
            date_from=date_from, date_to=date_to, instruments=instruments,
            split=split),
        metrics=metrics,
        series=[
            series("block_coverage", "Modality block coverage on this slice",
                   list(cov.columns), cov.values.tolist(),
                   "mean_non_null_fraction is the average fill across the block's "
                   "features on the selected rows"),
            series("split_sizes", "Rows per split in this slice",
                   ["split", "rows"],
                   [[k, v] for k, v in (profile["split_sizes"] or {}).items()]
                   if isinstance(profile["split_sizes"], dict) else [],
                   "the frozen holdout is included in the count and is never scored"),
        ],
        observations=observations,
        uncertainty={
            "kind": "none",
            "reading": ("These are counts and fill rates over the rows you selected, "
                        "not estimates. They carry no sampling interval because nothing "
                        "was estimated."),
        },
        provenance={
            "canonical_called": [
                "scripts.stages.stats:integrity_profile",
                "scripts.stages.stats:block_coverage",
                "research.data.dataset:MODALITY_BLOCKS",
            ],
            "rows_considered": profile["rows"],
            "wrote_nothing": True,
        },
        message="%d rows across %d instruments profiled live"
                % (profile["rows"], profile["instruments"]),
    )


# ------------------------------------------------------------------- STATS-02 ----

def analyse_universe(date_from: str | None = None,
                     date_to: str | None = None) -> AnalysisResult:
    """STATS-02 live: membership and churn over the rebalances in the chosen window.

    Survivorship is a property of a window, not of a dataset, so asking about one window
    is the only way the question has an answer. A universe that looks stable over eleven
    years can be turbulent over one of them.
    """
    from scripts.stages import live

    members = live.universe()
    date_col = ("rebalance_date" if "rebalance_date" in members.columns
                else members.columns[0])
    sel = members
    if date_from:
        sel = sel[sel[date_col] >= pd.Timestamp(date_from)]
    if date_to:
        sel = sel[sel[date_col] <= pd.Timestamp(date_to)]
    rebalances = sorted(sel[date_col].unique())
    if len(rebalances) < 2:
        return insufficient(
            "the selected window contains %d rebalance date(s); churn needs at least two"
            % len(rebalances),
            "Widen the date range so it spans more than one rebalance.")

    rows, prev = [], None
    for d in rebalances:
        cur = set(sel.loc[sel[date_col] == d, "symbol"])
        rows.append({
            "rebalance_date": str(pd.Timestamp(d).date()),
            "members": len(cur),
            "entries": len(cur - prev) if prev is not None else None,
            "exits": len(prev - cur) if prev is not None else None,
        })
        prev = cur
    churn = pd.DataFrame(rows)
    entries = churn["entries"].dropna()
    exits = churn["exits"].dropna()
    ever = int(sel["symbol"].nunique())
    always = len(set.intersection(*[
        set(sel.loc[sel[date_col] == d, "symbol"]) for d in rebalances]))

    metrics = [
        metric("rebalances", "Rebalances in this window", len(rebalances), "int",
               "reconstitution dates covered by your selection"),
        metric("ever", "Instruments ever a member", ever, "int",
               "the union across those rebalances"),
        metric("always", "Members at every rebalance", always, "int",
               "the intersection; the difference from the union is the survivorship gap"),
        metric("members_mean", "Members per rebalance",
               float(churn["members"].mean()), "float2"),
        metric("entries_mean", "Entries per rebalance",
               float(entries.mean()) if len(entries) else 0.0, "float2"),
        metric("exits_mean", "Exits per rebalance",
               float(exits.mean()) if len(exits) else 0.0, "float2"),
    ]
    return AnalysisResult(
        dataset={"source": "data/panel/universe.parquet",
                 "rows": int(len(sel)),
                 "date_from": str(pd.Timestamp(rebalances[0]).date()),
                 "date_to": str(pd.Timestamp(rebalances[-1]).date()),
                 "selection": {"date_from": date_from, "date_to": date_to}},
        metrics=metrics,
        series=[series("churn", "Membership at each rebalance",
                       list(churn.columns), churn.values.tolist(),
                       "entries and exits are relative to the previous rebalance in "
                       "this window, so the first row has none")],
        observations=[
            "%d instruments appear at some point and %d appear at every rebalance; the "
            "gap between them is what a survivorship-free sample has to carry."
            % (ever, always),
            "Membership is reconstructed point in time: a row belongs to a rebalance "
            "because it qualified then, not because it qualifies now.",
            "This is a liquidity-proxy universe reconstructed by this project. It is not "
            "the Nifty 50 and does not reproduce index membership (L-01).",
        ],
        uncertainty={"kind": "none",
                     "reading": "Counts over the reconstructed membership table. "
                                "Nothing here is estimated."},
        provenance={"canonical_called": ["research.data.universe"],
                    "rebalances_considered": len(rebalances),
                    "wrote_nothing": True},
        message="%d rebalances, %d instruments ever a member" % (len(rebalances), ever),
    )


# ------------------------------------------------------------------- STATS-03 ----

def analyse_distributions(date_from: str | None = None, date_to: str | None = None,
                          instruments: list[str] | None = None,
                          block: str = "all", split: str = "all") -> AnalysisResult:
    """STATS-03 live: descriptive statistics of the features on the selected rows.

    Degenerate features are reported alongside, because a feature with one distinct value
    on the slice being looked at cannot inform anything computed from that slice, however
    informative it is elsewhere.
    """
    from research.data import dataset as ds
    from scripts.stages import live

    df = live.slice_frame(live.panel(), date_from, date_to, instruments, split)
    if len(df) < live.MIN_ROWS:
        return insufficient(
            "the selected slice holds %d rows, below the %d needed for a distribution "
            "to describe anything" % (len(df), live.MIN_ROWS),
            "Widen the date range, or select more instruments.")

    block_of = {c: b for b, cols in ds.MODALITY_BLOCKS.items() for c in cols}
    wanted = (list(ds.ALL_FEATURES) if block in ("", "all")
              else list(ds.MODALITY_BLOCKS.get(block, [])))
    rows = []
    for c in wanted:
        if c not in df.columns:
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        rows.append({"feature": c, "block": block_of.get(c, "?"),
                     "non_null_fraction": float(s.notna().mean()),
                     "n_distinct": int(s.nunique(dropna=True)),
                     "mean": float(s.mean()), "std": float(s.std()),
                     "min": float(s.min()), "p50": float(s.median()),
                     "max": float(s.max())})
    tbl = pd.DataFrame(rows)
    if tbl.empty:
        return insufficient(
            "no features of block %r are present in the panel" % block,
            "Choose a different block, or all.")
    degenerate = tbl[(tbl["n_distinct"] <= 1) | (tbl["std"].fillna(0) == 0)]

    metrics = [
        metric("rows", "Rows described", int(len(df)), "int"),
        metric("features", "Features described", int(len(tbl)), "int",
               "numeric features present on these rows"),
        metric("degenerate", "Degenerate here", int(len(degenerate)), "int",
               "one distinct value or zero variance on this slice"),
        metric("mean_fill", "Mean fill",
               float(tbl["non_null_fraction"].mean()), "pct",
               "average share of rows carrying a value"),
        metric("thinnest", "Thinnest feature fill",
               float(tbl["non_null_fraction"].min()), "pct"),
    ]
    observations = [
        "Described %d features over the %d rows you selected." % (len(tbl), len(df)),
    ]
    if len(degenerate):
        observations.append(
            "%d feature(s) are constant on this slice and cannot separate anything "
            "computed from it: %s."
            % (len(degenerate), ", ".join(degenerate["feature"].head(5))))
    else:
        observations.append("Every described feature varies on this slice.")

    top = tbl.sort_values("std", ascending=False).head(40)
    return AnalysisResult(
        dataset=live.describe_slice(df, "data/panel/multimodal_dataset.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments, block=block, split=split),
        metrics=metrics,
        series=[series("features", "Feature summary on this slice (widest first)",
                       list(top.columns), top.values.tolist(),
                       "ordered by standard deviation; at most 40 rows shown",
                       total_rows=int(len(tbl)))],
        observations=observations,
        uncertainty={"kind": "none",
                     "reading": "Sample moments of the selected rows. They describe "
                                "this slice and are not estimates of a population."},
        provenance={"canonical_called": ["research.data.dataset:MODALITY_BLOCKS",
                                         "research.data.dataset:ALL_FEATURES"],
                    "features_considered": int(len(tbl)), "wrote_nothing": True},
        message="%d features described over %d rows" % (len(tbl), len(df)),
    )


# ------------------------------------------------------------------- STATS-04 ----

def analyse_microstructure(date_from: str | None = None, date_to: str | None = None,
                           instruments: list[str] | None = None) -> AnalysisResult:
    """STATS-04 live: the market and microstructure-proxy blocks on the selected rows.

    The register of quantities recorded NOT MEASURED travels with the numbers. A proxy
    computed from daily bars is a proxy whether or not the reader remembers that, and the
    list of what daily bars cannot see is the boundary of everything below.
    """
    from research.market import features as mf
    from scripts.stages import live

    df = live.slice_frame(live.panel(), date_from, date_to, instruments)
    if len(df) < live.MIN_ROWS:
        return insufficient(
            "the selected slice holds %d rows, below the %d needed to describe the "
            "market blocks" % (len(df), live.MIN_ROWS),
            "Widen the date range, or select more instruments.")

    rows = []
    for name, cols in (("market", mf.MARKET_FEATURES),
                       ("microstructure_proxy", mf.MICROSTRUCTURE_PROXIES)):
        for c in cols:
            if c not in df.columns:
                rows.append({"group": name, "feature": c, "present": False,
                             "non_null_fraction": 0.0, "mean": None, "std": None})
                continue
            s = pd.to_numeric(df[c], errors="coerce")
            rows.append({"group": name, "feature": c, "present": True,
                         "non_null_fraction": float(s.notna().mean()),
                         "mean": float(s.mean()), "std": float(s.std())})
    tbl = pd.DataFrame(rows)
    present = tbl[tbl["present"]]

    metrics = [
        metric("rows", "Rows described", int(len(df)), "int"),
        metric("market_features", "Market features",
               int((tbl["group"] == "market").sum()), "int"),
        metric("proxy_features", "Microstructure proxies",
               int((tbl["group"] == "microstructure_proxy").sum()), "int"),
        metric("mean_fill", "Mean fill on this slice",
               float(present["non_null_fraction"].mean()) if len(present) else 0.0,
               "pct"),
        metric("not_measured", "Quantities recorded NOT MEASURED",
               len(mf.MICROSTRUCTURE_NOT_MEASURED), "int",
               "order-book quantities daily bars cannot express"),
    ]
    return AnalysisResult(
        dataset=live.describe_slice(df, "data/panel/multimodal_dataset.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments),
        metrics=metrics,
        series=[
            series("coverage", "Market and proxy features on this slice",
                   list(tbl.columns), tbl.values.tolist(),
                   "present is whether the column exists at all; fill is over the "
                   "selected rows"),
            series("not_measured", "Recorded NOT MEASURED", ["quantity"],
                   [[q] for q in mf.MICROSTRUCTURE_NOT_MEASURED],
                   "these are not missing values; they are quantities this data source "
                   "cannot express at all"),
        ],
        observations=[
            "Every quantity above is derived from daily bars. Daily-bar proxies are not "
            "order-book microstructure, and the register beside them lists what is out "
            "of reach rather than merely absent (L-02).",
            "Fill is measured on the %d rows you selected." % len(df),
        ],
        uncertainty={"kind": "none",
                     "reading": "Coverage and sample moments of the selected rows."},
        provenance={"canonical_called": ["research.market.features:MARKET_FEATURES",
                                         "research.market.features:MICROSTRUCTURE_PROXIES",
                                         "research.market.features:"
                                         "MICROSTRUCTURE_NOT_MEASURED"],
                    "wrote_nothing": True},
        message="%d market and proxy features over %d rows" % (len(tbl), len(df)),
    )


# ------------------------------------------------------------------- STATS-05 ----

def analyse_regimes(date_from: str | None = None, date_to: str | None = None,
                    instruments: list[str] | None = None,
                    split: str = "all") -> AnalysisResult:
    """STATS-05 live: how the selected rows distribute across regimes."""
    from scripts.stages import live

    df = live.slice_frame(live.panel(), date_from, date_to, instruments, split)
    if "regime_id" not in df.columns:
        return insufficient("the panel carries no regime_id column",
                            "Rebuild the dataset with the regime block enabled.")
    if len(df) < live.MIN_ROWS:
        return insufficient(
            "the selected slice holds %d rows, below the %d needed for an occupancy "
            "profile" % (len(df), live.MIN_ROWS),
            "Widen the date range, or select more instruments.")

    occ = df.groupby("regime_id").size().rename("rows").reset_index()
    occ["share"] = occ["rows"] / occ["rows"].sum()
    if "is_episode" in df.columns:
        occ = occ.merge(df.groupby("regime_id")["is_episode"].mean()
                        .rename("episode_rate").reset_index(), on="regime_id")
    occ = occ.sort_values("rows", ascending=False)
    largest = occ.iloc[0]

    metrics = [
        metric("rows", "Rows in this slice", int(len(df)), "int"),
        metric("regimes", "Regimes present", int(len(occ)), "int"),
        metric("largest_share", "Largest regime share", float(occ["share"].max()),
               "pct", "share of the slice held by regime %s" % largest["regime_id"]),
        metric("smallest_rows", "Smallest regime, rows", int(occ["rows"].min()), "int",
               "a regime with few rows supports little on its own"),
    ]
    observations = [
        "Regime %s holds %.1f%% of the %d rows you selected."
        % (largest["regime_id"], 100 * float(largest["share"]), len(df)),
    ]
    if "episode_rate" in occ.columns:
        hot = occ.sort_values("episode_rate", ascending=False).iloc[0]
        observations.append(
            "The highest episode rate on this slice is %.1f%% in regime %s. Episodes are "
            "injected by this project, so this describes where they were placed (L-04)."
            % (100 * float(hot["episode_rate"]), hot["regime_id"]))
    thin = occ[occ["rows"] < 30]
    if len(thin):
        observations.append(
            "%d regime(s) hold fewer than 30 rows here; anything conditioned on them "
            "rests on very little." % len(thin))

    return AnalysisResult(
        dataset=live.describe_slice(df, "data/panel/multimodal_dataset.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments, split=split),
        metrics=metrics,
        series=[series("occupancy", "Regime occupancy on this slice",
                       list(occ.columns), occ.values.tolist(),
                       "share sums to one over the selected rows")],
        observations=observations,
        uncertainty={"kind": "none",
                     "reading": "Counts and rates over the selected rows."},
        provenance={"canonical_called": ["research.regime"],
                    "wrote_nothing": True},
        message="%d regimes over %d rows" % (len(occ), len(df)),
    )


# ------------------------------------------------------------------- STATS-06 ----

def analyse_dependence(date_from: str | None = None, date_to: str | None = None,
                       instruments: list[str] | None = None,
                       top_n: int = 15) -> AnalysisResult:
    """STATS-06 live: co-movement across the selected instruments, and the propagation
    feature block that summarises it.

    Everything below is contemporaneous association. Nothing here identifies a direction,
    a mechanism or an origin, and the wording is chosen so that it cannot be read as if it
    did (L-07).
    """
    from research.propagation import graph as pg
    from scripts.stages import live

    # Association is measured on the cash panel rather than on the modelling panel:
    # returns are the quantity a reader means by "these moved together", and the
    # modelling panel holds only the scored sessions, which are far too sparse per
    # instrument to correlate.
    cash = live.slice_frame(live.cash_panel(), date_from, date_to, instruments)
    if len(cash) < 60:
        return insufficient(
            "the selected slice holds %d sessions, below the 60 needed to measure "
            "co-movement" % len(cash),
            "Widen the date range, or select more instruments.")
    panel = live.slice_frame(live.panel(), date_from, date_to, instruments)

    truncated = 0
    present = [c for c in pg.PROPAGATION_FEATURES if c in panel.columns]
    feat = pd.DataFrame({
        "feature": present,
        "non_null_fraction": [float(panel[c].notna().mean()) for c in present],
        "mean": [float(pd.to_numeric(panel[c], errors="coerce").mean())
                 for c in present],
        "std": [float(pd.to_numeric(panel[c], errors="coerce").std())
                for c in present],
    }) if len(panel) else pd.DataFrame(
        columns=["feature", "non_null_fraction", "mean", "std"])

    pairs = pd.DataFrame(columns=["instrument_a", "instrument_b", "correlation",
                                  "sessions"])
    if len(cash):
        wide = (cash.pivot_table(index="date", columns="symbol", values="close")
                .sort_index())
        rets = wide.pct_change().dropna(how="all")
        counts = rets.notna().sum()
        usable = counts[counts >= 30].index.tolist()
        # Every pair among n instruments is n(n-1)/2 correlations, so an unfiltered
        # request over the whole universe is tens of thousands of them and minutes of
        # waiting. The most-observed instruments are kept and the truncation is reported
        # in the observations below, because a silently shortened table reads as a
        # complete one.
        truncated = 0
        if len(usable) > MAX_CORRELATED:
            truncated = len(usable) - MAX_CORRELATED
            usable = counts[usable].sort_values(ascending=False).head(
                MAX_CORRELATED).index.tolist()
        if len(usable) >= 2:
            corr = rets[usable].corr(min_periods=30)
            rows = []
            for i, a in enumerate(usable):
                for b in usable[i + 1:]:
                    value = corr.loc[a, b]
                    if pd.notna(value):
                        rows.append({"instrument_a": a, "instrument_b": b,
                                     "correlation": float(value),
                                     "sessions": int(min(counts[a], counts[b]))})
            if rows:
                pairs = (pd.DataFrame(rows)
                         .reindex(pd.DataFrame(rows)["correlation"].abs()
                                  .sort_values(ascending=False).index))

    metrics = [
        metric("sessions", "Sessions in this slice", int(len(cash)), "int",
               "instrument-days of price history the correlations were measured on"),
        metric("propagation_features", "Propagation features present",
               len(present), "int",
               "of %d declared" % len(pg.PROPAGATION_FEATURES)),
        metric("mean_fill", "Mean fill",
               float(feat["non_null_fraction"].mean()) if len(feat) else 0.0, "pct"),
        metric("pairs", "Instrument pairs measured", int(len(pairs)), "int",
               "pairs with at least 30 overlapping sessions"),
        metric("median_abs_corr", "Median absolute correlation",
               float(pairs["correlation"].abs().median()) if len(pairs) else float("nan"),
               "float4", "contemporaneous return correlation across those pairs"),
    ]
    observations = [
        "Correlations were computed on the sessions you selected, over %d instrument "
        "pairs with enough overlap to measure." % len(pairs),
        "These are contemporaneous associations between return series. They do not "
        "identify which instrument moved first, and nothing here supports a statement "
        "about one instrument driving another (L-07).",
    ]
    if truncated:
        observations.append(
            "%d instrument(s) were left out: every pair among %d instruments is more "
            "correlations than this endpoint will compute, so the %d with the most "
            "observed sessions were kept. Name the instruments you want to be sure."
            % (truncated, truncated + MAX_CORRELATED, MAX_CORRELATED))
    if len(pairs):
        top = pairs.iloc[0]
        observations.append(
            "The strongest association on this slice is %s and %s at %.3f over %d "
            "sessions." % (top["instrument_a"], top["instrument_b"],
                           float(top["correlation"]), int(top["sessions"])))

    return AnalysisResult(
        dataset=live.describe_slice(cash, "data/panel/cash_panel.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments, top_n=top_n),
        metrics=metrics,
        series=[
            series("pairs", "Strongest associations on this slice",
                   ["instrument_a", "instrument_b", "correlation", "sessions"],
                   pairs.head(max(1, int(top_n))).values.tolist(),
                   "ordered by absolute correlation; association only",
                   total_rows=int(len(pairs))),
            series("propagation_block", "Propagation feature block on this slice",
                   list(feat.columns), feat.values.tolist(),
                   "declared propagation features and their fill on the %d scored "
                   "rows in this window" % len(panel)),
        ],
        observations=observations,
        uncertainty={
            "kind": "sample",
            "n_pairs": int(len(pairs)),
            "reading": ("Each correlation is a sample statistic over the overlapping "
                        "sessions shown beside it. Pairs with few sessions move a great "
                        "deal from one window to the next, which is why the session "
                        "count is reported per pair rather than once for the table."),
        },
        provenance={"canonical_called": ["research.propagation.graph:"
                                         "PROPAGATION_FEATURES"],
                    "instrument_pairs": int(len(pairs)), "wrote_nothing": True},
        message="%d instrument pairs measured over %d sessions"
                % (len(pairs), len(cash)),
    )


# ------------------------------------------------------------------- STATS-07 ----

def analyse_tail_risk(date_from: str | None = None, date_to: str | None = None,
                      instruments: list[str] | None = None,
                      alpha: float = 0.05) -> AnalysisResult:
    """STATS-07 live: tail statistics of the realised next-session return on the slice.

    The same construction the regenerating adapter uses — next-session percentage change
    in close, per instrument — so the live figure and the artifact figure are the same
    quantity measured over different rows. The corporate-action diagnostic travels with
    it, because an unadjusted 10:1 split reads as a -90% session and one such row is
    enough to dominate a drawdown.
    """
    from research.risk import gate
    from scripts.stages import live

    cash = live.slice_frame(live.cash_panel(), date_from, date_to, instruments)
    if len(cash) < 60:
        return insufficient(
            "the selected slice holds %d sessions; tail statistics need at least 60"
            % len(cash),
            "Widen the date range, or select more instruments.")

    fwd = cash.sort_values(["symbol", "date"]).copy()
    fwd["fwd_ret"] = fwd.groupby("symbol")["close"].pct_change().shift(-1)
    net = fwd["fwd_ret"].to_numpy(float)
    net = net[np.isfinite(net)]
    if len(net) < 20:
        return insufficient(
            "only %d rows carry a next-session return" % len(net),
            "Widen the date range so each instrument has consecutive sessions.")

    stats = gate.tail_metrics(net, alpha=float(alpha))
    suspects = fwd.loc[fwd["fwd_ret"].abs() > 0.5, ["symbol", "date", "fwd_ret"]]
    clean = net[np.abs(net) <= 0.5]

    metrics = [
        metric("n", "Returns measured", int(stats["n"]), "int",
               "instrument-sessions with a next-session return in this slice"),
        metric("var", "VaR at %.0f%%" % (100 * alpha), stats["var"], "pct",
               "the quantile of the realised return distribution"),
        metric("cvar", "CVaR at %.0f%%" % (100 * alpha), stats["cvar"], "pct",
               "mean return in the tail beyond that quantile"),
        metric("vol_annual", "Annualised volatility", stats["vol_annual"], "pct"),
        metric("worst_day", "Worst session", stats["worst_day"], "pct",
               "unadjusted for corporate actions; see the diagnostic below"),
        metric("max_drawdown", "Maximum drawdown", stats["max_drawdown"], "pct",
               "of the equal-weight compounded series over these rows"),
    ]
    observations = [
        "Measured over %d realised next-session returns in the slice you selected."
        % int(stats["n"]),
        "This is the distribution the exposure gate reads. It is not the result of "
        "applying one, and no position size, allocation or exposure is produced here.",
    ]
    if len(suspects):
        observations.append(
            "%d session(s) move more than 50%%, which is almost certainly a split or "
            "bonus rather than a return: prices here are unadjusted. Worst session "
            "excluding them is %.2f%% (KI-06)."
            % (len(suspects),
               100 * float(clean.min()) if len(clean) else float("nan")))
    else:
        observations.append(
            "No session in this slice moves more than 50%, so the drawdown figure is "
            "not visibly contaminated by an unadjusted corporate action.")

    table = pd.DataFrame([{"statistic": k, "value": v} for k, v in stats.items()])
    return AnalysisResult(
        dataset=live.describe_slice(cash, "data/panel/cash_panel.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments, alpha=alpha),
        metrics=metrics,
        series=[
            series("tail", "Tail statistics on this slice",
                   list(table.columns), table.values.tolist(),
                   "computed by research.risk.gate.tail_metrics"),
            series("suspects", "Sessions above the corporate-action threshold",
                   ["symbol", "date", "fwd_ret"],
                   [[str(r.symbol), str(pd.Timestamp(r.date).date()), float(r.fwd_ret)]
                    for r in suspects.head(25).itertuples(index=False)],
                   "absolute move greater than 50%; reported, not removed",
                   total_rows=int(len(suspects))),
        ],
        observations=observations,
        uncertainty={
            "kind": "sample",
            "n": int(stats["n"]),
            "reading": ("Tail statistics are the least stable thing in this project: "
                        "CVaR at 5%% is an average over roughly %d observations here, "
                        "and a different window can move it substantially. Read it as a "
                        "description of these rows, not as a forecast."
                        % max(1, int(0.05 * stats["n"]))),
        },
        provenance={"canonical_called": ["research.risk.gate:tail_metrics"],
                    "alpha": float(alpha), "wrote_nothing": True},
        message="tail statistics over %d realised returns" % int(stats["n"]),
    )


# ------------------------------------------------------------------- STATS-08 ----

def analyse_episodes(date_from: str | None = None, date_to: str | None = None,
                     instruments: list[str] | None = None) -> AnalysisResult:
    """STATS-08 live: the injected episodes overlapping the selected window."""
    from scripts.stages import live

    labels = pd.read_parquet(paths.PANEL / "episode_labels.parquet")
    # Synthetic episode ground truth, not market history: exempt by name in
    # live.NON_BITEMPORAL_FRAMES["episode_labels"].
    sel = live.slice_frame(labels, date_from, date_to, instruments,
                           require_point_in_time=False) \
        if "date" in labels.columns else labels
    if len(sel) < live.MIN_ROWS:
        return insufficient(
            "the selected window holds %d episode label rows, below the %d needed to "
            "summarise them" % (len(sel), live.MIN_ROWS),
            "Widen the date range, or select more instruments.")

    n_episodes = int(sel["episode_id"].nunique()) if "episode_id" in sel.columns else 0
    rows = []
    for col in ("intensity", "duration", "n_sessions", "state"):
        if col not in sel.columns:
            continue
        s = sel[col]
        if s.dtype == object:
            counts = s.value_counts()
            for k, v in counts.items():
                rows.append({"quantity": "%s=%s" % (col, k), "value": int(v),
                             "kind": "count"})
        else:
            s = pd.to_numeric(s, errors="coerce")
            rows.append({"quantity": "%s mean" % col, "value": float(s.mean()),
                         "kind": "mean"})
            rows.append({"quantity": "%s max" % col, "value": float(s.max()),
                         "kind": "max"})
    table = pd.DataFrame(rows)

    metrics = [
        metric("label_rows", "Label rows in this window", int(len(sel)), "int"),
        metric("episodes", "Episodes", n_episodes, "int",
               "distinct injected episodes overlapping the window"),
        metric("instruments", "Instruments affected",
               int(sel["symbol"].nunique()) if "symbol" in sel.columns else 0, "int"),
    ]
    if "intensity" in sel.columns:
        metrics.append(metric("intensity", "Mean intensity",
                              float(pd.to_numeric(sel["intensity"],
                                                  errors="coerce").mean()), "float4",
                              "the injected magnitude, a construction parameter"))

    return AnalysisResult(
        dataset=live.describe_slice(sel, "data/panel/episode_labels.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments),
        metrics=metrics,
        series=[series("episode_summary", "Episode label summary in this window",
                       list(table.columns), table.values.tolist(),
                       "counts for categorical columns, moments for numeric ones")]
        if len(table) else [],
        observations=[
            "%d episodes touch the window you selected, across %d instruments."
            % (n_episodes,
               int(sel["symbol"].nunique()) if "symbol" in sel.columns else 0),
            "These episodes were injected into real price series by this project. They "
            "are a construction with known parameters, and no count here describes "
            "real-world market manipulation (L-04).",
        ],
        uncertainty={"kind": "none",
                     "reading": "Counts over the injected label table. The labels are "
                                "exact by construction, which is what makes them "
                                "usable as ground truth and also what bounds them."},
        provenance={"canonical_called": ["research.detection.episodes"],
                    "episodes": n_episodes, "wrote_nothing": True},
        message="%d episodes over %d label rows" % (n_episodes, len(sel)),
    )


# ------------------------------------------------------------------- STATS-09 ----

def analyse_leakage() -> AnalysisResult:
    """STATS-09 live: run the L1-L6 leakage suite now and report what it found.

    No parameters, deliberately. The suite is the canonical definition of the property
    and there is nothing about it a caller should be able to vary: a leakage check whose
    scope the requester can narrow is not a leakage check. The command is a fixed argument
    list with no value from the request in it.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/leakage", "-q", "--no-header",
         "--tb=no"],
        cwd=str(paths.REPO_ROOT), capture_output=True, text=True)
    lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
    tail = lines[-1] if lines else "pytest produced no summary"
    passed = _count(tail, "passed")
    failed = _count(tail, "failed")

    metrics = [
        metric("passed", "Checks passed", passed, "int"),
        metric("failed", "Checks failed", failed, "int",
               "a single failure invalidates every downstream result"),
        metric("returncode", "Suite exit code", int(proc.returncode), "int",
               "zero is the only acceptable value"),
    ]
    ok = proc.returncode == 0
    observations = [
        "The suite ran during this request; this is not a stored report.",
        ("All %d checks pass, so no test in the suite found information from after a "
         "decision time reaching a feature computed before it." % passed) if ok else
        ("%d check(s) failed. Every result computed downstream of the affected feature "
         "is invalid until the failure is resolved." % failed),
        "Passing means the suite found nothing, which is not the same as proving that "
        "nothing exists to find (L-11).",
    ]
    return AnalysisResult(
        ok=True,
        dataset={"source": "tests/leakage", "rows": passed + failed,
                 "selection": {}},
        metrics=metrics,
        series=[series("output", "Suite output", ["line"],
                       [[ln] for ln in lines[-12:]],
                       "the last lines pytest printed")],
        observations=observations,
        uncertainty={"kind": "none",
                     "reading": "A test suite result is a pass or a fail, not an "
                                "estimate. What it bounds is which failure modes were "
                                "looked for."},
        provenance={"canonical_called": ["tests/leakage (L1-L6)"],
                    "returncode": int(proc.returncode), "wrote_nothing": True},
        message=tail,
    )


def _count(summary: str, word: str) -> int:
    import re as _re
    m = _re.search(r"(\d+)\s+%s" % word, summary)
    return int(m.group(1)) if m else 0


# ------------------------------------------------------------------- STATS-10 ----

def _scored(arm: str, date_from: str | None, date_to: str | None,
            instruments: list[str] | None):
    """Per-row scores for one arm, filtered to the caller's slice."""
    from scripts.stages import live

    frame = live.per_row(arm)
    if frame is None:
        return None, ("no per-row scores exist for arm %s" % arm,
                      "Choose an arm that was executed, or run "
                      "`python scripts/run_experiments.py` at a terminal.")
    # Model scores from an executed arm, not market history: exempt by name in
    # live.NON_BITEMPORAL_FRAMES["per_row_scores"].
    sel = live.slice_frame(frame, date_from, date_to, instruments,
                           require_point_in_time=False)
    if len(sel) < live.MIN_ROWS:
        return None, ("the selected slice holds %d scored rows, below the %d needed for "
                      "a metric to mean anything" % (len(sel), live.MIN_ROWS),
                      "Widen the date range, or select fewer instruments to exclude.")
    if sel["is_episode"].nunique() < 2:
        return None, ("every row in this slice has the same label, so no ranking metric "
                      "is defined on it",
                      "Widen the window so it contains both episode and non-episode "
                      "rows.")
    return sel, None


def _train_threshold() -> tuple[float | None, str]:
    """The threshold selected on the training split, from the experiment bundle."""
    bundles = sorted(paths.REPORTS.glob("*FULL*/metrics.json"))
    if not bundles:
        return None, ""
    bundle = json.loads(bundles[0].read_text(encoding="utf-8"))
    return (bundle.get("detection", {}).get("threshold"),
            str(bundles[0].relative_to(paths.REPO_ROOT).as_posix()))


def analyse_validation(arm: str = "FULL", threshold: float | None = None,
                       date_from: str | None = None, date_to: str | None = None,
                       instruments: list[str] | None = None) -> AnalysisResult:
    """STATS-10 live: the confusion matrix and its metrics at a threshold you choose.

    The default is the threshold selected on the training split, read from the experiment
    bundle. A caller may override it — that is the point of an interactive panel — and
    when they do, the response says plainly that the threshold was chosen by hand and that
    picking the one that flatters a metric on the evaluation split is not a selection
    procedure (L6). The number is still computed correctly; what changes is what it is
    evidence of.
    """
    from research.evaluation import metrics as mx

    sel, problem = _scored(arm, date_from, date_to, instruments)
    if sel is None:
        return insufficient(*problem)

    train_thr, source = _train_threshold()
    chosen_by_caller = threshold is not None
    thr = float(threshold) if chosen_by_caller else (
        float(train_thr) if train_thr is not None else mx.best_f1_threshold(
            sel["is_episode"].to_numpy(int), sel["integrity_risk"].to_numpy(float)))

    y = sel["is_episode"].to_numpy(int)
    p = sel["integrity_risk"].to_numpy(float)
    report = mx.verification_report(y, p, thr)
    m = report["metrics"]
    per_class = pd.DataFrame(report["per_class"])

    metrics = [
        metric("n", "Rows scored", int(m["n"]), "int"),
        metric("threshold", "Threshold applied", thr, "float4",
               "chosen by you" if chosen_by_caller
               else "selected on the training split, not here"),
        metric("balanced_accuracy", "Balanced accuracy", m["balanced_accuracy"],
               "float4", "accuracy corrected for the class imbalance"),
        metric("mcc", "Matthews correlation", m["mcc"], "float4",
               "a single number that degrades when any cell of the matrix does"),
        metric("tp", "True positives", m["tp"], "int"),
        metric("fp", "False positives", m["fp"], "int"),
        metric("fn", "False negatives", m["fn"], "int"),
        metric("tn", "True negatives", m["tn"], "int"),
    ]
    observations = [
        "Computed on the %d scored rows in your slice of arm %s." % (int(m["n"]), arm),
    ]
    if chosen_by_caller:
        observations.append(
            "You set this threshold. Choosing a threshold by looking at the evaluation "
            "metrics it produces is not a selection procedure, and a number obtained "
            "that way is a description of this slice rather than evidence about unseen "
            "data (L6). The training-selected threshold is %s."
            % ("%.4f" % train_thr if train_thr is not None else "unavailable"))
    else:
        observations.append(
            "The threshold came from %s, where it was selected on the training split. "
            "Recomputing it here would flatter every metric above."
            % (source or "the best-F1 rule, because no experiment bundle was found"))
    observations.append(
        "The episodes these labels describe are injected by this project, so this "
        "measures detection of a known construction (L-04).")

    return AnalysisResult(
        dataset={"source": "research_artifacts/experiments/per_row_%s.parquet" % arm,
                 "rows": int(len(sel)),
                 "date_from": str(sel["date"].min().date()),
                 "date_to": str(sel["date"].max().date()),
                 "instruments": int(sel["symbol"].nunique()),
                 "selection": {"arm": arm, "threshold": thr,
                               "date_from": date_from, "date_to": date_to}},
        metrics=metrics,
        series=[series("per_class", "Per-class report at this threshold",
                       list(per_class.columns), per_class.values.tolist(),
                       "precision, recall and support for each class")],
        observations=observations,
        uncertainty={
            "kind": "threshold",
            "threshold": thr,
            "threshold_selected_by": "caller" if chosen_by_caller else "training split",
            "reading": ("Every count above moves with the threshold, and the threshold "
                        "is a choice rather than a property of the model. Change it and "
                        "watch which cells trade against each other; that trade is the "
                        "actual result."),
        },
        provenance={"canonical_called": ["research.evaluation.metrics:"
                                         "verification_report",
                                         "research.evaluation.metrics:per_class_report"],
                    "arm": arm, "threshold_source": source or "best-F1 fallback",
                    "threshold_chosen_by_caller": chosen_by_caller,
                    "metrics_version": mx.METRICS_VERSION,
                    "wrote_nothing": True},
        message="%d rows at threshold %.4f (balanced accuracy %.4f)"
                % (int(m["n"]), thr, m["balanced_accuracy"]),
    )


# ------------------------------------------------------------------- STATS-11 ----

def analyse_calibration(arm: str = "FULL", bins: int = 10,
                        date_from: str | None = None, date_to: str | None = None,
                        instruments: list[str] | None = None) -> AnalysisResult:
    """STATS-11 live: the reliability curve at a binning you choose.

    The bin count is exposed because expected calibration error depends on it, and a
    single ECE quoted without its binning is a number whose scale nobody can check. Move
    the slider and the figure moves; that sensitivity is the finding.
    """
    from research.evaluation import metrics as mx

    sel, problem = _scored(arm, date_from, date_to, instruments)
    if sel is None:
        return insufficient(*problem)

    y = sel["is_episode"].to_numpy(int)
    p = sel["integrity_risk"].to_numpy(float)
    n_bins = max(2, min(int(bins), 50))
    rel = mx.reliability_curve(y, p, n_bins=n_bins)
    ece = mx.expected_calibration_error(y, p, n_bins=n_bins)
    detection = mx.detection_metrics(y, p)

    metrics = [
        metric("n", "Rows scored", int(len(sel)), "int"),
        metric("bins", "Bins", n_bins, "int",
               "the ECE beside this is defined only with respect to this binning"),
        metric("ece", "Expected calibration error", ece, "float4",
               "mean gap between predicted score and observed rate, weighted by bin"),
        metric("auprc", "AUPRC", detection["auprc"], "float4",
               "ranking quality, which calibration does not affect"),
        metric("positive_rate", "Episode rate in this slice",
               detection["positive_rate"], "pct"),
    ]
    worst = rel.iloc[(rel.get("gap", (rel.iloc[:, 1] - rel.iloc[:, 2]).abs())
                      .abs()).idxmax()] if len(rel) else None

    observations = [
        "Reliability computed over %d scored rows at %d bins." % (len(sel), n_bins),
        "The integrity-risk score is a ranking, not a calibrated probability: a score of "
        "0.7 does not mean seven episodes in ten (L-10). The curve below shows how far "
        "from that the score actually is.",
    ]
    if worst is not None:
        observations.append(
            "The widest gap between score and observed rate on this slice is in bin %s."
            % str(worst.iloc[0]))

    return AnalysisResult(
        dataset={"source": "research_artifacts/experiments/per_row_%s.parquet" % arm,
                 "rows": int(len(sel)),
                 "date_from": str(sel["date"].min().date()),
                 "date_to": str(sel["date"].max().date()),
                 "selection": {"arm": arm, "bins": n_bins,
                               "date_from": date_from, "date_to": date_to}},
        metrics=metrics,
        series=[series("reliability", "Reliability curve at %d bins" % n_bins,
                       list(rel.columns), rel.values.tolist(),
                       "one row per bin: mean predicted score against observed rate")],
        observations=observations,
        uncertainty={
            "kind": "binning",
            "bins": n_bins,
            "reading": ("Expected calibration error is a function of the binning as much "
                        "as of the model. Fewer bins hide miscalibration inside them; "
                        "more bins put very few rows in each and the curve becomes "
                        "noise. Both failure modes are reachable from the control above, "
                        "which is why the bin count is reported with the number."),
        },
        provenance={"canonical_called": ["research.evaluation.metrics:reliability_curve",
                                         "research.evaluation.metrics:"
                                         "expected_calibration_error"],
                    "arm": arm, "bins": n_bins, "wrote_nothing": True},
        message="ECE %.4f at %d bins over %d rows" % (ece, n_bins, len(sel)),
    )


# ------------------------------------------------------------------- STATS-12 ----

def analyse_errors(arm: str = "FULL", threshold: float | None = None,
                   segment_by: str = "error_class",
                   date_from: str | None = None, date_to: str | None = None,
                   instruments: list[str] | None = None) -> AnalysisResult:
    """STATS-12 live: where the scoring goes wrong on the selected rows, and how.

    The taxonomy separates data problems from model problems, in that order: a row with
    no evidence under it is not a model failure, and counting it as one would send the
    reader looking in the wrong place.
    """
    from research.evaluation import metrics as mx

    sel, problem = _scored(arm, date_from, date_to, instruments)
    if sel is None:
        return insufficient(*problem)

    train_thr, source = _train_threshold()
    chosen_by_caller = threshold is not None
    thr = float(threshold) if chosen_by_caller else (
        float(train_thr) if train_thr is not None
        else mx.best_f1_threshold(sel["is_episode"].to_numpy(int),
                                  sel["integrity_risk"].to_numpy(float)))

    tax = mx.classify_errors(sel, thr)
    counts = (tax["error_class"].value_counts()
              .rename_axis("error_class").reset_index(name="rows"))
    counts["share"] = counts["rows"] / counts["rows"].sum()

    if segment_by in tax.columns and segment_by != "error_class":
        cross = (tax.groupby([segment_by, "error_class"]).size()
                 .rename("rows").reset_index())
    else:
        cross = counts.copy()

    wrong = tax[tax["error_class"] != "CORRECT"]
    metrics = [
        metric("n", "Rows examined", int(len(tax)), "int"),
        metric("threshold", "Threshold applied", thr, "float4",
               "chosen by you" if chosen_by_caller else "selected on the training split"),
        metric("wrong", "Rows not classified correctly", int(len(wrong)), "int"),
        metric("error_rate", "Error rate",
               float(len(wrong) / max(1, len(tax))), "pct"),
        metric("classes", "Distinct failure modes",
               int(counts[counts["error_class"] != "CORRECT"].shape[0]), "int"),
    ]
    observations = [
        "%d of %d rows in this slice are not classified correctly at threshold %.4f."
        % (len(wrong), len(tax), thr),
    ]
    if len(wrong):
        worst = (wrong["error_class"].value_counts().idxmax())
        observations.append(
            "The most common failure mode here is %s. The taxonomy diagnoses data "
            "problems before model problems, so a row counted as MISSING_MODALITY or "
            "DATA_QUALITY is one where the evidence was absent, not one where the model "
            "reasoned badly." % worst)
    if not chosen_by_caller and source:
        observations.append("The threshold came from %s." % source)

    return AnalysisResult(
        dataset={"source": "research_artifacts/experiments/per_row_%s.parquet" % arm,
                 "rows": int(len(sel)),
                 "date_from": str(sel["date"].min().date()),
                 "date_to": str(sel["date"].max().date()),
                 "selection": {"arm": arm, "threshold": thr, "segment_by": segment_by,
                               "date_from": date_from, "date_to": date_to}},
        metrics=metrics,
        series=[
            series("taxonomy", "Failure modes on this slice",
                   list(counts.columns), counts.values.tolist(),
                   "one row per class, including CORRECT"),
            series("segmented", "Failure modes by %s" % segment_by,
                   list(cross.columns), cross.head(60).values.tolist(),
                   "at most 60 rows shown", total_rows=int(len(cross))),
        ],
        observations=observations,
        uncertainty={
            "kind": "threshold",
            "threshold": thr,
            "reading": ("Which rows are wrong depends entirely on the threshold. The "
                        "counts above are the composition of the errors at this one, not "
                        "a property of the model at every threshold."),
        },
        provenance={"canonical_called": ["research.evaluation.metrics:classify_errors"],
                    "arm": arm, "threshold_chosen_by_caller": chosen_by_caller,
                    "wrote_nothing": True},
        message="%d of %d rows misclassified at %.4f" % (len(wrong), len(tax), thr),
    )


# ------------------------------------------------------------------- STATS-14 ----

def analyse_ablation(arms: list[str] | None = None, reference: str = "FULL",
                     date_from: str | None = None,
                     date_to: str | None = None) -> AnalysisResult:
    """STATS-14 live: recompute each arm's detection metrics on the selected rows.

    The arms were fitted once, by the experiment runner, and their per-row scores are
    stored. What is recomputed here is the *metric* over the rows you chose — which is the
    honest interactive version of an ablation, because refitting on request would let a
    reader arrive at an arm ranking chosen after seeing the evaluation data.

    A difference smaller than the seed noise floor is not a finding. The floor is measured
    in STATS-16 and is not assumed here, so the gaps below are reported as gaps.
    """
    from research.evaluation import metrics as mx
    from scripts.stages import live

    available = live.available_arms()
    wanted = [a for a in (arms or ["FULL", "NO_TEXT", "NO_MARKET", "TEXT_ONLY"])
              if a in available]
    if reference not in wanted and reference in available:
        wanted = [reference, *wanted]
    if len(wanted) < 2:
        return insufficient(
            "fewer than two of the requested arms have per-row scores on disk",
            "Choose arms from the executed set: %s." % ", ".join(available[:12]))

    rows, skipped = [], []
    for arm in wanted:
        sel, problem = _scored(arm, date_from, date_to, None)
        if sel is None:
            skipped.append((arm, problem[0]))
            continue
        d = mx.detection_metrics(sel["is_episode"].to_numpy(int),
                                 sel["integrity_risk"].to_numpy(float))
        rows.append({"arm": arm, "n": int(d["n"]), "auprc": d["auprc"],
                     "auroc": d["auroc"], "brier": d["brier"],
                     "auprc_lift": d["auprc_lift"]})
    if len(rows) < 2:
        return insufficient(
            "only %d arm(s) could be scored on this slice" % len(rows),
            "Widen the date range so each arm has enough scored rows.")

    table = pd.DataFrame(rows).sort_values("auprc", ascending=False)
    ref_row = table[table["arm"] == reference]
    base = float(ref_row["auprc"].iloc[0]) if len(ref_row) else float(
        table["auprc"].max())
    table["delta_vs_reference"] = table["auprc"] - base
    best, worst = table.iloc[0], table.iloc[-1]

    metrics = [
        metric("arms", "Arms compared", int(len(table)), "int"),
        metric("reference_auprc", "%s AUPRC" % reference, base, "float4"),
        metric("best_auprc", "Best AUPRC here", float(best["auprc"]), "float4",
               "arm %s" % best["arm"]),
        metric("spread", "Spread across arms",
               float(table["auprc"].max() - table["auprc"].min()), "float4",
               "largest minus smallest AUPRC on this slice"),
        metric("rows", "Rows per arm", int(table["n"].iloc[0]), "int"),
    ]
    observations = [
        "Metrics were recomputed on the %d rows in your window; the arms themselves were "
        "fitted once by the experiment runner and are not refitted here."
        % int(table["n"].iloc[0]),
        "%s leads on this slice and %s trails, a gap of %.4f AUPRC."
        % (best["arm"], worst["arm"],
           float(best["auprc"] - worst["auprc"])),
        "Whether a gap this size is a finding depends on the seed noise floor, which is "
        "measured separately in STATS-16. A gap smaller than the floor is not evidence "
        "that one arm is better.",
    ]
    if skipped:
        observations.append(
            "%d arm(s) could not be scored on this slice: %s."
            % (len(skipped), "; ".join("%s (%s)" % (a, r) for a, r in skipped[:3])))

    return AnalysisResult(
        dataset={"source": "research_artifacts/experiments/per_row_*.parquet",
                 "rows": int(table["n"].sum()),
                 "selection": {"arms": wanted, "reference": reference,
                               "date_from": date_from, "date_to": date_to}},
        metrics=metrics,
        series=[series("arms", "Detection metrics per arm on this slice",
                       list(table.columns), table.values.tolist(),
                       "delta_vs_reference is AUPRC minus the reference arm's AUPRC")],
        observations=observations,
        uncertainty={
            "kind": "no_interval",
            "reading": ("These are point estimates on one slice with no confidence "
                        "interval attached. Two arms whose AUPRC differs in the third "
                        "decimal should be treated as unresolved until the seed noise "
                        "floor in STATS-16 says otherwise."),
        },
        provenance={"canonical_called": ["research.evaluation.metrics:"
                                         "detection_metrics"],
                    "arms": wanted, "reference": reference,
                    "refitted": False, "wrote_nothing": True},
        message="%d arms compared over %d rows each"
                % (len(table), int(table["n"].iloc[0])),
    )


# ------------------------------------------------------------------- STATS-15 ----

def analyse_robustness(corruption: str = "gaussian", severity: float = 0.10,
                       modality: str = "all", seed: int = 20260818) -> AnalysisResult:
    """STATS-15 live: one perturbation condition, fitted clean and scored degraded.

    The model is fitted once on clean data and the *evaluation* inputs are degraded. That
    asymmetry is the point: refitting on corrupted data measures whether the learner can
    adapt to a new noise regime, which is an easier and different question from what
    happens to a deployed model when its feed degrades.

    The frozen holdout is never read; the canonical harness refuses a frame containing it.
    """
    from research.evaluation import robustness as rb
    from scripts.stages import live

    if corruption not in ("gaussian", "dropout", "stale", "outliers"):
        return insufficient(
            "%r is not one of the implemented failure modes" % corruption,
            "Choose gaussian, dropout, stale or outliers.")

    data = live.panel()
    work = rb.working_set(data)
    train = work[work["split"] == "train"]
    evald = work[work["split"] == "validation"]
    cols = (rb.feature_columns(work) if modality in ("", "all")
            else rb.modality_columns(work, modality))
    if not cols:
        return insufficient(
            "no feature columns for modality %r are present" % modality,
            "Choose all, or a modality block the panel actually carries.")

    clean = rb.fit_and_score(train, evald, list(rb.ds.MODALITY_BLOCKS), int(seed),
                             "clean", "undegraded reference")
    if clean.status != "OK":
        return insufficient(
            "the clean reference fit did not complete: %s" % clean.reason,
            "This is a condition of the data, not of your selection.")

    degraded_frame = rb.perturb(evald, cols, corruption, float(severity), int(seed))
    degraded = rb.fit_and_score(train, degraded_frame, list(rb.ds.MODALITY_BLOCKS),
                                int(seed), "%s@%.2f" % (corruption, severity),
                                "evaluation inputs degraded")
    if degraded.status != "OK":
        return insufficient(
            "the degraded fit did not complete: %s" % degraded.reason,
            "Try a lower severity.")

    base = float(clean.metrics.get("auprc", float("nan")))
    hit = float(degraded.metrics.get("auprc", float("nan")))
    table = pd.DataFrame([
        {"condition": "clean", **dict(clean.metrics)},
        {"condition": "%s@%.2f" % (corruption, severity),
         **dict(degraded.metrics)},
    ])

    metrics = [
        metric("clean_auprc", "AUPRC, clean inputs", base, "float4"),
        metric("degraded_auprc", "AUPRC, degraded inputs", hit, "float4"),
        metric("degradation", "Loss in AUPRC", base - hit, "float4",
               "clean minus degraded; positive means the corruption hurt"),
        metric("relative", "Share of AUPRC lost",
               (base - hit) / base if base else float("nan"), "pct"),
        metric("columns", "Columns degraded", len(cols), "int"),
        metric("eval_rows", "Evaluation rows", int(len(evald)), "int"),
    ]
    observations = [
        "One condition, run now: %s at severity %.2f applied to %d %s columns of the "
        "evaluation inputs." % (corruption, severity, len(cols),
                                "feature" if modality in ("", "all") else modality),
        "AUPRC moves from %.4f to %.4f, a loss of %.4f." % (base, hit, base - hit),
        "The model was fitted once on clean data and never saw the degradation, which is "
        "the situation a deployed model is in when a feed degrades.",
        "The frozen holdout was not read: this ran on train and validation only.",
    ]
    return AnalysisResult(
        dataset={"source": "data/panel/multimodal_dataset.parquet",
                 "rows": int(len(work)),
                 "selection": {"corruption": corruption, "severity": float(severity),
                               "modality": modality, "seed": int(seed)}},
        metrics=metrics,
        series=[series("conditions", "Clean against degraded",
                       list(table.columns), table.values.tolist(),
                       "both rows produced by the same fit-and-score path the "
                       "regenerating harness uses")],
        observations=observations,
        uncertainty={
            "kind": "single_seed",
            "seed": int(seed),
            "reading": ("One condition at one seed. Part of the difference above is "
                        "seed variance rather than the corruption: the noise floor "
                        "measured in STATS-16 is the scale against which a loss this "
                        "size should be read."),
        },
        provenance={"canonical_called": ["research.evaluation.robustness:perturb",
                                         "research.evaluation.robustness:fit_and_score",
                                         "research.evaluation.robustness:working_set"],
                    "corruption": corruption, "severity": float(severity),
                    "seed": int(seed), "refitted_on_clean_only": True,
                    "holdout_read": False, "wrote_nothing": True},
        message="%s@%.2f costs %.4f AUPRC" % (corruption, severity, base - hit),
    )


# ------------------------------------------------------------------- STATS-16 ----

def analyse_seed_noise(arms: list[str] | None = None,
                       alpha: float = 0.05) -> AnalysisResult:
    """STATS-16 live: the seed noise floor over the arms you select.

    Re-derived from the stored seed table rather than refitted, because refitting sixteen
    arms across five seeds on request would take minutes and produce the same numbers. The
    computation that matters — pooling the within-arm seed variance into a floor, and
    testing arm differences against it with a multiplicity correction — runs now, on the
    arms you chose.

    The floor is the point. A difference between two arms that is smaller than it is not a
    small effect; it is not distinguishable from rerunning the same arm with a different
    seed.
    """
    from research.statistics import tests as st

    path = (paths.REPO_ROOT / "outputs" / "stats" / "16_multiseed_significance"
            / "seed_table.csv")
    if not path.exists():
        return insufficient(
            "the multi-seed table has not been produced",
            "Run `python scripts/run_module.py --module STATS-16` at a terminal.")

    table = pd.read_csv(path)
    table = table[table["status"] == "OK"]
    available = sorted(table["arm"].unique())
    wanted = [a for a in (arms or available) if a in available]
    if len(wanted) < 2:
        return insufficient(
            "fewer than two of the selected arms have completed seed fits",
            "Choose at least two of: %s." % ", ".join(available[:12]))

    sel = table[table["arm"].isin(wanted)]
    # An arm with one completed seed has no standard deviation, and asking numpy for one
    # produces a warning and a NaN. Reporting it as blank is the honest rendering: the
    # spread was not measured, rather than measured as zero.
    grouped = sel.groupby("arm")["auprc"]
    per_arm = pd.DataFrame({
        "arm": grouped.count().index,
        "seeds": grouped.count().to_numpy(int),
        "auprc_mean": grouped.mean().to_numpy(float),
        "auprc_sd": [float(g.std(ddof=1)) if len(g) > 1 else float("nan")
                     for _, g in sel.groupby("arm")["auprc"]],
    }).sort_values("auprc_mean", ascending=False)
    # Only arms with at least two completed seeds contribute a within-arm variance; an
    # arm with one is not a low-variance arm, it is an unmeasured one.
    counts = sel.groupby("arm")["auprc"].count()
    within = (sel[sel["arm"].isin(counts[counts >= 2].index)]
              .groupby("arm")["auprc"].std(ddof=1).dropna())
    pooled_sd = float(np.sqrt((within ** 2).mean())) if len(within) else float("nan")
    floor = float(1.96 * pooled_sd * np.sqrt(2)) if np.isfinite(pooled_sd) else float(
        "nan")

    # Every pair, tested against the floor and then corrected for the number of tests.
    pairs = []
    arms_sorted = per_arm["arm"].tolist()
    for i, a in enumerate(arms_sorted):
        for b in arms_sorted[i + 1:]:
            xa = sel.loc[sel["arm"] == a, "auprc"].to_numpy(float)
            xb = sel.loc[sel["arm"] == b, "auprc"].to_numpy(float)
            n = min(len(xa), len(xb))
            if n < 2:
                continue
            diff = xa[:n] - xb[:n]
            result = st.paired_permutation(diff, n_perm=2000, seed=20260818)
            pairs.append({"arm_a": a, "arm_b": b,
                          "difference": float(diff.mean()),
                          "exceeds_noise_floor": bool(abs(diff.mean()) > floor),
                          "p_value": (float(result.p_value)
                                      if result.p_value is not None else float("nan")),
                          "pairs_tested": int(result.n)})
    pair_table = pd.DataFrame(pairs)
    survives = resolved = 0
    if len(pair_table):
        bh = st.benjamini_hochberg(pair_table["p_value"].tolist(), alpha=float(alpha))
        pair_table["adjusted_p"] = bh["adjusted_p"].to_numpy()
        pair_table["survives_correction"] = bh["reject"].to_numpy()
        # Both conditions, deliberately. Surviving the correction says the difference is
        # unlikely to be zero; exceeding the floor says it is larger than what reseeding
        # the same arm produces. A difference can pass the first and fail the second, and
        # such a pair is reliably small rather than reliably meaningful.
        pair_table["resolved"] = (pair_table["survives_correction"]
                                  & pair_table["exceeds_noise_floor"])
        survives = int(pair_table["survives_correction"].sum())
        resolved = int(pair_table["resolved"].sum())

    metrics = [
        metric("arms", "Arms compared", len(wanted), "int"),
        metric("seeds", "Seeds per arm", int(per_arm["seeds"].min()), "int"),
        metric("pooled_sd", "Pooled seed standard deviation", pooled_sd, "float5",
               "within-arm AUPRC variation across seeds"),
        metric("floor", "95% seed noise floor", floor, "float5",
               "an AUPRC gap smaller than this is not distinguishable from reseeding"),
        metric("pairs", "Pairs tested", int(len(pair_table)), "int"),
        metric("survives", "Pairs surviving correction", survives, "int",
               "after Benjamini-Hochberg at alpha %.2f" % alpha),
        metric("resolved", "Pairs resolved", resolved, "int",
               "both larger than the noise floor and surviving the correction"),
    ]
    within_floor = (int((~pair_table["exceeds_noise_floor"]).sum())
                    if len(pair_table) else 0)
    observations = [
        "The noise floor on these arms is %.5f AUPRC. Rerunning the same arm with a "
        "different seed moves it by about that much." % floor,
        "%d of %d arm pairs differ by less than the floor and are unresolved: not close, "
        "not equal, simply not separable by this evidence."
        % (within_floor, len(pair_table)),
        "%d pair(s) survive multiplicity correction at alpha %.2f, and %d of those are "
        "also larger than the floor. Only the second count is a resolved difference: a "
        "gap can be reliably non-zero and still be no larger than reseeding."
        % (survives, alpha, resolved),
    ]
    return AnalysisResult(
        dataset={"source": "outputs/stats/16_multiseed_significance/seed_table.csv",
                 "rows": int(len(sel)),
                 "selection": {"arms": wanted, "alpha": float(alpha)}},
        metrics=metrics,
        series=[
            series("per_arm", "AUPRC across seeds, per arm",
                   list(per_arm.columns), per_arm.values.tolist(),
                   "mean and standard deviation over the seeds that completed"),
            series("pairs", "Pairwise differences against the floor",
                   list(pair_table.columns), pair_table.values.tolist(),
                   "a difference below the floor is unresolved regardless of its "
                   "p-value") if len(pair_table) else
            series("pairs", "Pairwise differences", ["note"],
                   [["not enough seeds per arm to test any pair"]], ""),
        ],
        observations=observations,
        uncertainty={
            "kind": "seed_variance",
            "pooled_sd": pooled_sd,
            "noise_floor_95": floor,
            "reading": ("This module measures the uncertainty every other comparison in "
                        "the project should be read against. The floor is derived from "
                        "the seeds that were actually run; more seeds would tighten it, "
                        "and it is not an estimate of variance from any other source."),
        },
        provenance={"canonical_called": ["research.statistics.tests:paired_permutation",
                                         "research.statistics.tests:benjamini_hochberg"],
                    "arms": wanted, "refitted": False, "wrote_nothing": True},
        message="noise floor %.5f AUPRC over %d arms" % (floor, len(wanted)),
    )
