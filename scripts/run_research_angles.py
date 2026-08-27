"""Execute the experiment specifications that need no external data.

    python scripts/run_research_angles.py

The limitations registry marks seven specifications as runnable now. Those are
obligations, not ideas: a research angle whose data is already on disk and which has not
been run is just an unexecuted experiment. This script runs them and writes results into
the registry's result slots.

Everything blocked by external data stays blocked and is reported as such. Nothing here
fabricates a result for an experiment it cannot run.
"""
from __future__ import annotations

import sys
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from research.core import jsonio, paths, progress
from research.core.manifest import environment_snapshot
from research.data import dataset as ds
from research.evaluation import information as info
from research.evaluation import temporal_analysis as ta
from research.limitations import registry as reg
from research.statistics import power as pw
from research.xai import methods as xm
from research.xai import sanity as xs

OUT = paths.ARTIFACTS / "research_angles"
EXP_DIR = paths.ARTIFACTS / "experiments"

MODALITIES = ["text", "image", "audio", "video", "market", "microstructure",
              "regime", "propagation"]

#: (modality -> (only-arm, without-arm)) for the information decomposition.
MODALITY_ARMS = {
    "text": ("TEXT_ONLY", "NO_TEXT"),
    "image": ("IMAGE_ONLY", "NO_IMAGE"),
    "audio": ("AUDIO_ONLY", "NO_AUDIO"),
    "video": ("VIDEO_ONLY", "NO_VIDEO"),
    "market": ("MARKET_ONLY", "NO_MARKET"),
    "microstructure": ("MARKET_MICRO", "NO_MICROSTRUCTURE"),
    "propagation": (None, "NO_PROPAGATION"),
    "regime": (None, "NO_REGIME"),
}

results: dict[str, dict] = {}


def _load_arms() -> dict[str, pd.DataFrame]:
    arms = {}
    for p in sorted(EXP_DIR.glob("per_row_*.parquet")):
        arms[p.stem.replace("per_row_", "")] = pd.read_parquet(p)
    return arms


def _cluster(df: pd.DataFrame) -> pd.Series:
    return np.where(df["episode_id"].astype(str) != "",
                    df["episode_id"].astype(str),
                    "sym_" + df["symbol"].astype(str))


# -- EXP-N03-1: lead-time / precision frontier and modality lead-lag --------------------

def exp_n03(arms: dict[str, pd.DataFrame]) -> dict:
    full = arms["FULL"]
    frontier = ta.lead_time_frontier(full)
    frontier.to_csv(OUT / "exp_n03_lead_time_frontier.csv", index=False)

    lead_lag = ta.modality_lead_lag(full, MODALITIES)
    curves = {r["modality"]: {"lags": r.get("_curve_lags"),
                              "values": r.get("_curve_values")}
              for _, r in lead_lag.iterrows() if r.get("status") == "OK"}
    jsonio.write(OUT / "exp_n03_lead_lag_curves.json", curves, indent=1)
    lead_lag.drop(columns=[c for c in lead_lag.columns if c.startswith("_")]) \
        .to_csv(OUT / "exp_n03_modality_lead_lag.csv", index=False)

    lifecycle = ta.onset_peak_resolution_scores(full)
    jsonio.write(OUT / "exp_n03_lifecycle.json", lifecycle)

    ok = frontier[frontier.get("status") == "OK"] if "status" in frontier else frontier
    positive = ok[ok["median_lead_time"] > 0] if len(ok) else ok
    best_positive = None
    if len(positive):
        row = positive.sort_values("window_precision", ascending=False).iloc[0]
        best_positive = {"entry_threshold": float(row["entry_threshold"]),
                         "median_lead_time": float(row["median_lead_time"]),
                         "window_precision": float(row["window_precision"]),
                         "detection_rate": float(row["detection_rate"])}
    return {
        "experiment": "EXP-N03-1",
        "status": "MEASURED",
        "n_thresholds": int(len(ok)),
        "any_positive_lead_operating_point": best_positive is not None,
        "best_positive_lead_point": best_positive,
        "frontier_range": {
            "median_lead_time_min": float(ok["median_lead_time"].min()) if len(ok)
            else None,
            "median_lead_time_max": float(ok["median_lead_time"].max()) if len(ok)
            else None,
            "window_precision_min": float(ok["window_precision"].min()) if len(ok)
            else None,
            "window_precision_max": float(ok["window_precision"].max()) if len(ok)
            else None,
        },
        "modality_lead_lag": lead_lag.drop(
            columns=[c for c in lead_lag.columns if c.startswith("_")]
        ).to_dict(orient="records"),
        "lifecycle": lifecycle,
    }


# -- EXP-L10-1: calibration under coverage and disagreement ----------------------------

def exp_l10(arms: dict[str, pd.DataFrame]) -> dict:
    full = arms["FULL"].copy()
    by_cov = info.calibration_by_bucket(full, "coverage")
    by_unc = info.calibration_by_bucket(full, "uncertainty")
    by_cov.to_csv(OUT / "exp_l10_calibration_by_coverage.csv", index=False)
    by_unc.to_csv(OUT / "exp_l10_calibration_by_uncertainty.csv", index=False)

    def _trend(d: pd.DataFrame) -> float | None:
        """Slope of ECE against the bucket midpoint, or None when unmeasurable.

        Returning None matters: `coverage` takes only five distinct values in this
        dataset, so a fitted slope there would describe the binning rather than the
        data."""
        ok = d[d["status"] == "OK"] if "status" in d.columns else d
        ok = ok.dropna(subset=["ece"])
        if len(ok) < 3:
            return None
        x = ((ok["bucket_low"] + ok["bucket_high"]) / 2).to_numpy(float)
        if len(np.unique(x)) < 3:
            return None
        return float(np.polyfit(x, ok["ece"].to_numpy(float), 1)[0])

    return {
        "experiment": "EXP-L10-1",
        "status": "MEASURED",
        "ece_slope_vs_coverage": _trend(by_cov),
        "coverage_measurable": _trend(by_cov) is not None,
        "coverage_note": (
            "Coverage takes only five distinct values on this dataset (median 1.0), so "
            "the ECE-versus-coverage relationship is NOT MEASURABLE here. It becomes "
            "measurable once modalities are genuinely absent for a meaningful share of "
            "rows."),
        "ece_slope_vs_uncertainty": _trend(by_unc),
        "by_coverage": by_cov.to_dict(orient="records"),
        "by_uncertainty": by_unc.to_dict(orient="records"),
        "interpretation_rule": (
            "A positive slope against uncertainty means calibration degrades exactly "
            "where the model says it is unsure, which is the expected and desirable "
            "pattern. A flat slope against coverage means the uncertainty estimate is "
            "already absorbing missingness."),
    }


# -- EXP-N04-1: selective risk for uncertainty-weighted fusion -------------------------

def exp_n04(arms: dict[str, pd.DataFrame]) -> dict:
    a = arms.get("FUSION_STATIC")
    b = arms.get("FUSION_UNCERTAINTY")
    if a is None or b is None:
        return {"experiment": "EXP-N04-1", "status": "BLOCKED",
                "reason": "required arms missing"}
    sa = info.selective_risk(a["is_episode"].to_numpy(int),
                             a["integrity_risk"].to_numpy(float),
                             a["uncertainty"].to_numpy(float))
    sb = info.selective_risk(b["is_episode"].to_numpy(int),
                             b["integrity_risk"].to_numpy(float),
                             b["uncertainty"].to_numpy(float))
    sa["arm"] = "FUSION_STATIC"
    sb["arm"] = "FUSION_UNCERTAINTY"
    both = pd.concat([sa, sb], ignore_index=True)
    both.to_csv(OUT / "exp_n04_selective_risk.csv", index=False)

    merged = sa.merge(sb, on="coverage", suffixes=("_static", "_unc"))
    merged["risk_delta"] = (merged["selective_risk_unc"]
                            - merged["selective_risk_static"])
    wins = int((merged["risk_delta"] < 0).sum())
    return {
        "experiment": "EXP-N04-1",
        "status": "MEASURED",
        "coverage_levels": int(len(merged)),
        "levels_where_uncertainty_arm_better": wins,
        "mean_risk_delta": float(merged["risk_delta"].mean()),
        "dominates": bool(wins == len(merged)),
        "table": merged[["coverage", "selective_risk_static", "selective_risk_unc",
                         "risk_delta"]].to_dict(orient="records"),
        "note": ("Selective risk uses each arm's own uncertainty to rank rows, so an arm "
                 "whose uncertainty is merely self-consistent can look good here. Read "
                 "alongside the ECE comparison, not instead of it."),
    }


# -- EXP-L12-1: power curve and minimum detectable effect ------------------------------

def exp_l12(arms: dict[str, pd.DataFrame]) -> dict:
    full = arms["FULL"]
    out: dict = {"experiment": "EXP-L12-1", "status": "MEASURED", "comparisons": []}
    targets = [("NO_MICROSTRUCTURE", "not significant at 5% FDR"),
               ("NO_PROPAGATION", "significant but negligible"),
               ("NO_AFFECTIVE", "significant and large")]
    curves = []
    for arm_name, label in targets:
        other = arms.get(arm_name)
        if other is None:
            continue
        merged = full[["symbol", "date", "is_episode", "episode_id",
                       "integrity_risk"]].merge(
            other[["symbol", "date", "integrity_risk"]], on=["symbol", "date"],
            suffixes=("_full", "_arm"))
        merged["cluster"] = _cluster(merged)
        curve = pw.power_curve(merged, "cluster", "integrity_risk_full",
                               "integrity_risk_arm", b=250)
        curve["comparison"] = "FULL vs %s" % arm_name
        curves.append(curve)
        mde = pw.minimum_detectable_effect(merged, "cluster", "integrity_risk_full",
                                           "integrity_risk_arm", b=400)
        need = pw.required_clusters_for_effect(curve, target_effect=0.002)
        out["comparisons"].append({
            "arm": arm_name, "prior_label": label,
            "minimum_detectable_effect": mde.get("minimum_detectable_effect"),
            "observed_difference": mde.get("observed_difference"),
            "informative": mde.get("informative"),
            "scaling_exponent": need.get("scaling_exponent"),
            "clusters_needed_for_0.002": need.get("required_clusters"),
            "multiple_of_current": need.get("multiple_of_current"),
        })
    if curves:
        pd.concat(curves, ignore_index=True).to_csv(
            OUT / "exp_l12_power_curves.csv", index=False)
    return out


# -- EXP-L04-2: which episode properties drive detection -------------------------------

def exp_l04(arms: dict[str, pd.DataFrame]) -> dict:
    full = arms["FULL"]
    labels_path = paths.PANEL / "episode_labels.parquet"
    if not labels_path.exists():
        return {"experiment": "EXP-L04-2", "status": "BLOCKED",
                "reason": "episode_labels.parquet absent"}
    labels = pd.read_parquet(labels_path)
    ep = full[full["episode_id"].astype(str) != ""]
    if ep.empty:
        return {"experiment": "EXP-L04-2", "status": "NOT MEASURED",
                "reason": "no episode rows in the evaluation split"}

    props = (labels.groupby("episode_id")
             .agg(peak_intensity=("peak_intensity", "first"),
                  censored=("censored", "first"),
                  duration=("date", "count"))
             .reset_index())
    per_ep = (ep.groupby("episode_id")
              .agg(max_score=("integrity_risk", "max"),
                   mean_score=("integrity_risk", "mean"),
                   n_rows=("integrity_risk", "size"))
              .reset_index())
    d = per_ep.merge(props, on="episode_id", how="inner")
    if len(d) < 8:
        return {"experiment": "EXP-L04-2", "status": "INSUFFICIENT",
                "n_episodes": int(len(d))}

    from scipy.stats import spearmanr
    d["detected"] = (d["max_score"] >= 0.55).astype(int)
    d.to_csv(OUT / "exp_l04_episode_properties.csv", index=False)

    q = d["peak_intensity"].quantile([0.25, 0.75])
    low = d[d["peak_intensity"] <= q.iloc[0]]
    high = d[d["peak_intensity"] >= q.iloc[1]]
    return {
        "experiment": "EXP-L04-2",
        "status": "MEASURED",
        "n_episodes": int(len(d)),
        "spearman_intensity_vs_max_score": float(
            spearmanr(d["peak_intensity"], d["max_score"]).statistic),
        "spearman_duration_vs_max_score": float(
            spearmanr(d["duration"], d["max_score"]).statistic),
        "detection_rate_low_intensity_quartile": float(low["detected"].mean())
        if len(low) else None,
        "detection_rate_high_intensity_quartile": float(high["detected"].mean())
        if len(high) else None,
        "intensity_floor_note": (
            "Peak intensity is a generator parameter, so a positive correlation is "
            "partly definitional. The informative quantity is the detection rate in the "
            "lowest quartile: it bounds the magnitude of event this architecture could "
            "see at all."),
    }


# -- EXP-N02-1: regime gap versus episodes per regime ----------------------------------

def exp_n02(arms: dict[str, pd.DataFrame]) -> dict:
    a = arms.get("FUSION_STATIC")
    b = arms.get("FUSION_REGIME_CORRECTED")
    if a is None or b is None:
        return {"experiment": "EXP-N02-1", "status": "BLOCKED",
                "reason": "required arms missing"}
    merged = a[["symbol", "date", "is_episode", "episode_id", "integrity_risk"]].merge(
        b[["symbol", "date", "integrity_risk"]], on=["symbol", "date"],
        suffixes=("_static", "_regime"))
    merged["cluster"] = _cluster(merged)
    curve = pw.power_curve(merged, "cluster", "integrity_risk_regime",
                           "integrity_risk_static",
                           fractions=(0.3, 0.5, 0.7, 0.85, 1.0), b=250)
    curve.to_csv(OUT / "exp_n02_regime_gap_vs_sample.csv", index=False)
    ok = curve[curve.get("status") == "OK"] if "status" in curve.columns else curve

    trend = None
    if len(ok) >= 3:
        trend = float(np.polyfit(ok["n_clusters"].to_numpy(float),
                                 ok["mean_difference"].to_numpy(float), 1)[0])

    # Episodes available per regime, which is the quantity the variance-inflation
    # explanation depends on.
    per_regime = None
    dpath = paths.PANEL / "multimodal_dataset.parquet"
    if dpath.exists():
        dd = pd.read_parquet(dpath, columns=["regime_id", "episode_id", "split"])
        val = dd[dd["split"] == "validation"]
        per_regime = (val[val["episode_id"].astype(str) != ""]
                      .groupby("regime_id")["episode_id"].nunique().to_dict())
        per_regime = {str(int(k)): int(v) for k, v in per_regime.items()}

    return {
        "experiment": "EXP-N02-1",
        "status": "MEASURED",
        "gap_trend_per_cluster": trend,
        "gap_shrinks_with_sample": (trend is not None and trend > 0),
        "episodes_per_regime_validation": per_regime,
        "curve": ok.to_dict(orient="records"),
        "interpretation_rule": (
            "A gap that closes as clusters increase supports variance inflation from "
            "per-regime parameters. A flat gap points instead to redundancy between the "
            "regime block and the market block."),
    }


# -- EXP-N01-1: LIME stability versus perturbation count -------------------------------

def exp_n01() -> dict:
    dpath = paths.PANEL / "multimodal_dataset.parquet"
    if not dpath.exists():
        return {"experiment": "EXP-N01-1", "status": "BLOCKED",
                "reason": "dataset absent"}
    data = pd.read_parquet(dpath)
    train = data[data["split"] == "train"]
    evald = data[data["split"] == "validation"]
    cols = [c for m in MODALITIES for c in ds.MODALITY_BLOCKS[m]
            if c in data.columns]
    cols = [c for c in cols if data[c].notna().any()]
    Xtr = np.nan_to_num(train[cols].to_numpy(float), nan=0.0)
    Xev = np.nan_to_num(evald[cols].to_numpy(float), nan=0.0)
    y_tr = train["is_episode"].to_numpy(int)

    from sklearn.ensemble import HistGradientBoostingClassifier
    m = HistGradientBoostingClassifier(max_iter=180, max_depth=4, learning_rate=0.06,
                                       random_state=20260818)
    m.fit(Xtr, y_tr)
    predict = lambda Z: m.predict_proba(np.nan_to_num(Z, nan=0.0))[:, 1]  # noqa: E731
    row = int(np.argmax(predict(Xev)))
    bg = Xtr[np.random.default_rng(0).choice(len(Xtr), min(200, len(Xtr)),
                                             replace=False)]
    ref = xm.occlusion(predict, Xev, row, cols, bg)

    rows = []
    for n_samples in (400, 800, 1600, 3200, 6400):
        t0 = time.perf_counter()
        runs = [xm.lime(predict, Xev, row, cols, bg, n_samples=n_samples, seed=s)
                for s in (1, 2, 3)]
        elapsed = (time.perf_counter() - t0) / 3.0
        sc = xs.sign_consistency(runs)
        from scipy.stats import spearmanr
        rho = float(spearmanr(runs[0].values, ref.values).statistic)
        rows.append({"n_perturbations": n_samples,
                     "sign_consistency": float(sc.statistic),
                     "passes_threshold": bool(sc.passed),
                     "spearman_vs_occlusion": rho,
                     "seconds_per_run": float(elapsed)})
        progress.log("    LIME n=%5d  sign_consistency=%.3f  rho_vs_occlusion=%+.3f  "
                     "%.2fs" % (n_samples, sc.statistic, rho, elapsed))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "exp_n01_lime_stability.csv", index=False)
    crossing = df[df["passes_threshold"]]
    return {
        "experiment": "EXP-N01-1",
        "status": "MEASURED",
        "occlusion_seconds": float(ref.seconds),
        "crosses_threshold_at": int(crossing["n_perturbations"].min())
        if len(crossing) else None,
        "cost_at_crossing_seconds": float(
            crossing.sort_values("n_perturbations").iloc[0]["seconds_per_run"])
        if len(crossing) else None,
        "cheaper_than_occlusion_at_crossing": bool(
            len(crossing) and crossing.sort_values("n_perturbations")
            .iloc[0]["seconds_per_run"] < ref.seconds),
        "table": rows,
    }


# -- modality information decomposition (research-angle section 28) --------------------

def modality_matrix(arms: dict[str, pd.DataFrame]) -> dict:
    cov = {}
    dpath = paths.PANEL / "multimodal_dataset.parquet"
    if dpath.exists():
        flags = list(ds.COVERAGE_FLAGS)
        d = pd.read_parquet(dpath, columns=flags + ["split"])
        d = d[d["split"] == "validation"]
        for flag in flags:
            mod = flag.replace("cov_", "").replace("micro", "microstructure")
            cov[mod] = float(d[flag].mean())
    usable = {m: (a, b) for m, (a, b) in MODALITY_ARMS.items()
              if b in arms and (a is None or a in arms)}
    matrix = info.decomposition(arms, "FULL",
                                {m: (a, b) for m, (a, b) in usable.items()
                                 if a is not None},
                                coverage=cov)
    # Blocks that have no stand-alone arm still have a measurable unique contribution.
    extra = []
    for m, (a, b) in usable.items():
        if a is not None:
            continue
        without = arms[b]
        auprc_full = info._auprc(arms["FULL"]["is_episode"].to_numpy(int),
                                 arms["FULL"]["integrity_risk"].to_numpy(float))
        auprc_wo = info._auprc(without["is_episode"].to_numpy(int),
                               without["integrity_risk"].to_numpy(float))
        extra.append({"modality": m, "total_auprc": np.nan,
                      "unique": auprc_full - auprc_wo, "redundant": np.nan,
                      "redundant_raw": np.nan, "conflict_rate": np.nan,
                      "missing_rate": 1.0 - cov.get(m, np.nan),
                      "auprc_full": auprc_full, "auprc_without": auprc_wo})
    if extra:
        matrix = pd.concat([matrix, pd.DataFrame(extra)], ignore_index=True)
    matrix = matrix.sort_values("unique", ascending=False).reset_index(drop=True)
    matrix.to_csv(OUT / "modality_information_matrix.csv", index=False)
    return {"analysis": "modality_information_decomposition", "status": "MEASURED",
            "rows": matrix.to_dict(orient="records"),
            "caveat": ("Operational decomposition in AUPRC, not a formal partial "
                       "information decomposition. Image, video and audio are rendered "
                       "or sonified from the market series (L-09, L-06), so their low "
                       "uniqueness is expected by construction.")}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    progress.log("running research angles that need no external data")
    arms = _load_arms()
    progress.log("  loaded %d per-arm score frames" % len(arms))
    if "FULL" not in arms:
        raise SystemExit("per_row_FULL.parquet missing: run scripts/run_experiments.py")

    steps = [
        ("modality_information", lambda: modality_matrix(arms)),
        ("EXP-N03-1 lead-time frontier", lambda: exp_n03(arms)),
        ("EXP-L10-1 calibration buckets", lambda: exp_l10(arms)),
        ("EXP-N04-1 selective risk", lambda: exp_n04(arms)),
        ("EXP-L12-1 power analysis", lambda: exp_l12(arms)),
        ("EXP-L04-2 episode properties", lambda: exp_l04(arms)),
        ("EXP-N02-1 regime gap vs sample", lambda: exp_n02(arms)),
        ("EXP-N01-1 LIME stability", exp_n01),
    ]
    for name, fn in steps:
        progress.log("  %s" % name)
        try:
            r = fn()
            results[r.get("experiment", r.get("analysis", name))] = r
        except Exception as exc:
            progress.log("    FAILED: %s: %s" % (type(exc).__name__, exc))
            results[name] = {"status": "FAILED",
                             "error": "%s: %s" % (type(exc).__name__, exc)}

    payload = {
        "run_at": datetime.now(UTC).isoformat(),
        "registry_version": reg.REGISTRY_VERSION,
        "runnable_specs": [e.id for e in reg.runnable_now()],
        "blocked_specs": [{"id": e.id, "required_data": e.required_data}
                          for e in reg.blocked()],
        "results": results,
        "environment": environment_snapshot(),
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "research_angles.json", payload)
    reg.write(paths.MANIFESTS / "limitations_registry.json")
    progress.log("done in %.1fs -> %s" % (time.time() - t0, OUT))

    for k, v in results.items():
        print("%-34s %s" % (k, v.get("status")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
