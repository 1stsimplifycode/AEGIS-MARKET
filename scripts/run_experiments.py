"""Run baselines and every ablation arm, with statistics.

    python scripts/run_experiments.py --dataset multimodal_dataset.parquet

Writes one artifact bundle per arm under ``research_artifacts/experiment_reports/`` and a
consolidated results table. Nothing is hand-entered: the tables the paper uses are read
back from these files.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from research.core import paths, progress
from research.core.manifest import environment_snapshot
from research.evaluation import ablations as ab
from research.evaluation import experiment as ex
from research.evaluation import metrics as mx
from research.models import baselines as bl
from research.statistics import tests as stx


def auprc_of(df: pd.DataFrame, col: str = "integrity_risk") -> float:
    from sklearn.metrics import average_precision_score
    y = df["is_episode"].to_numpy(int)
    if len(np.unique(y)) < 2:
        return float("nan")
    return float(average_precision_score(y, df[col].to_numpy(float)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="multimodal_dataset.parquet")
    ap.add_argument("--eval-split", default="validation")
    ap.add_argument("--seed", type=int, default=20260818)
    ap.add_argument("--bootstrap", type=int, default=600)
    args = ap.parse_args()

    paths.ensure_dirs()
    progress.log("loading %s" % args.dataset)
    data = pd.read_parquet(paths.PANEL / args.dataset)
    progress.log("dataset %d rows, splits %s"
                 % (len(data), data["split"].value_counts().to_dict()))

    train = data[data["split"] == "train"]
    evald = data[data["split"] == args.eval_split]
    y_tr = train["is_episode"].to_numpy(int)
    y_ev = evald["is_episode"].to_numpy(int)
    progress.log("train %d (%.3f positive) | eval %d (%.3f positive)"
                 % (len(train), y_tr.mean(), len(evald), y_ev.mean()))

    # -- baselines --------------------------------------------------------------------
    progress.log("running baselines")
    base_rows = []
    base_scores: dict[str, np.ndarray] = {}
    for name, res in bl.run_all(train, evald, y_tr, args.seed).items():
        if res.status != "OK":
            base_rows.append({"model": name, "status": res.status, "note": res.note})
            progress.log("  %-22s %s" % (name, res.status))
            continue
        m = mx.detection_metrics(y_ev, res.eval_score)
        base_scores[name] = res.eval_score
        base_rows.append({"model": name, "status": "OK", **m})
        progress.log("  %-22s auprc=%.4f auroc=%.4f" % (name, m["auprc"], m["auroc"]))
    baselines_df = pd.DataFrame(base_rows)

    # -- ablation arms ----------------------------------------------------------------
    arms = ab.all_arms()
    progress.log("running %d ablation arms" % len(arms))
    results: list[ex.ExperimentResult] = []
    per_row_scores: dict[str, pd.DataFrame] = {}
    t0 = time.time()
    for i, arm in enumerate(arms, 1):
        spec = ex.ExperimentSpec(
            experiment_id="ablation", hypothesis=arm.hypothesis or
            "arm %s vs FULL" % arm.name,
            arm=arm.name, modalities=list(arm.modalities),
            fusion_strategy=arm.fusion, dataset_path=args.dataset,
            eval_split=args.eval_split, seed=args.seed,
            baseline="FULL", notes=[arm.note] if arm.note else [])
        d = ab.apply_arm(data, arm)
        r = ex.run(spec, d)
        results.append(r)
        if r.status == "OK":
            per_row_scores[arm.name] = r.per_row
            progress.log("  [%2d/%d] %-26s auprc=%.4f auroc=%.4f f1=%.3f"
                         % (i, len(arms), arm.name, r.detection.get("auprc", np.nan),
                            r.detection.get("auroc", np.nan),
                            r.detection.get("f1", np.nan)))
        else:
            progress.log("  [%2d/%d] %-26s FAILED: %s"
                         % (i, len(arms), arm.name, r.failure_reason))
    progress.log("arms done in %.1fs" % (time.time() - t0))

    table = ex.results_table(results)

    # -- statistics -------------------------------------------------------------------
    progress.log("bootstrap intervals and paired tests vs FULL")
    stat_rows = []
    ci_rows = []
    ref = per_row_scores.get("FULL")
    for arm in arms:
        pr = per_row_scores.get(arm.name)
        if pr is None:
            continue
        # Cluster on episode where present, otherwise on symbol: rows inside one episode
        # are not independent draws.
        pr = pr.copy()
        pr["cluster"] = np.where(pr["episode_id"].astype(str) != "",
                                 pr["episode_id"].astype(str),
                                 "sym_" + pr["symbol"].astype(str))
        ci = stx.cluster_bootstrap_ci(pr, auprc_of, "cluster", b=args.bootstrap,
                                      seed=args.seed)
        ci_rows.append({"arm": arm.name, "auprc": ci.statistic,
                        "ci_low": ci.ci_low, "ci_high": ci.ci_high,
                        "n": ci.n, "test": ci.name})
        if ref is not None and arm.name != "FULL":
            merged = pr[["symbol", "date", "is_episode", "episode_id",
                         "integrity_risk"]].merge(
                ref[["symbol", "date", "integrity_risk"]],
                on=["symbol", "date"], suffixes=("_arm", "_full"))
            merged["cluster"] = np.where(merged["episode_id"].astype(str) != "",
                                         merged["episode_id"].astype(str),
                                         "sym_" + merged["symbol"].astype(str))
            t = stx.paired_bootstrap_difference(
                merged, lambda d: auprc_of(d, "integrity_risk_full"),
                lambda d: auprc_of(d, "integrity_risk_arm"),
                "cluster", b=args.bootstrap, seed=args.seed)
            stat_rows.append({"arm": arm.name, "comparison": "FULL - arm",
                              "delta_auprc": t.statistic, "p_value": t.p_value,
                              "ci_low": t.ci_low, "ci_high": t.ci_high,
                              "test": t.name, "description": t.test_description})
    stats_df = pd.DataFrame(stat_rows)
    if len(stats_df):
        bh = stx.benjamini_hochberg(stats_df["p_value"].tolist())
        stats_df["adjusted_p"] = bh["adjusted_p"].to_numpy()
        stats_df["significant_fdr_5pct"] = bh["reject"].to_numpy()
    ci_df = pd.DataFrame(ci_rows)

    merged_table = table.merge(ci_df[["arm", "ci_low", "ci_high"]], on="arm",
                               how="left")

    # -- persist ----------------------------------------------------------------------
    out = paths.ARTIFACTS / "experiments"
    out.mkdir(parents=True, exist_ok=True)
    merged_table.to_csv(out / "ablation_results.csv", index=False)
    baselines_df.to_csv(out / "baseline_results.csv", index=False)
    stats_df.to_csv(out / "ablation_statistics.csv", index=False)
    ci_df.to_csv(out / "ablation_confidence_intervals.csv", index=False)
    ab.arm_table().to_csv(out / "arm_definitions.csv", index=False)
    for name, pr in per_row_scores.items():
        pr.to_parquet(out / ("per_row_%s.parquet" % name), index=False)

    summary = {
        "run_at": datetime.now(UTC).isoformat(),
        "dataset": args.dataset,
        "eval_split": args.eval_split,
        "n_train": int(len(train)), "n_eval": int(len(evald)),
        "positive_rate_eval": float(y_ev.mean()),
        "n_arms": len(arms),
        "n_arms_ok": int((table["status"] == "OK").sum()),
        "n_arms_failed": int((table["status"] != "OK").sum()),
        "bootstrap_resamples": args.bootstrap,
        "environment": environment_snapshot(),
    }
    (out / "run_summary.json").write_text(json.dumps(summary, indent=2, default=str),
                                          encoding="utf-8")
    progress.log("wrote %s" % out)
    print(merged_table.sort_values("auprc", ascending=False)
          [["arm", "status", "auprc", "auroc", "f1", "ece", "ci_low", "ci_high"]]
          .to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
