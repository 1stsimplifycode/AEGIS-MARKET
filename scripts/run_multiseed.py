"""Execute the STATS-16 multi-seed and significance harness.

    python scripts/run_multiseed.py --seeds 10
    python scripts/run_multiseed.py --seeds 5 --jobs 4

Repeats every ablation arm across seeds, then applies the existing cluster bootstrap,
paired permutation, Benjamini-Hochberg correction and power analysis to the repeated
measurements. Writes to ``outputs/stats/16_multiseed_significance/``; nothing under
``research_artifacts/`` is touched.

The evaluation split is ``validation``. The frozen holdout is not used for seed variance
either: repeating a measurement on the holdout ten times is ten looks at the data it was
frozen to protect.
"""
from __future__ import annotations

import argparse
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
from research.evaluation import ablations as ab  # noqa: E402
from research.evaluation import multiseed as ms  # noqa: E402
from research.statistics import power as pw  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "stats" / "16_multiseed_significance"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="multimodal_dataset.parquet")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--jobs", type=int, default=0)
    ap.add_argument("--metric", default="auprc")
    ap.add_argument("--reference", default="FULL")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    seeds = list(ms.DEFAULT_SEEDS)[:args.seeds]
    arms = ab.all_arms()
    dataset_path = str(paths.PANEL / args.dataset)
    data = pd.read_parquet(dataset_path)
    progress.log("[stats-16] %d arms x %d seeds on %d validation rows"
                 % (len(arms), len(seeds),
                    int((data["split"] == "validation").sum())))

    table = ms.run_seeds_parallel(dataset_path, arms, seeds=seeds,
                                  n_jobs=args.jobs, log=progress.log)
    table.to_csv(OUT / "seed_table.csv", index=False)
    n_ok = int((table["status"] == "OK").sum())
    progress.log("  %d/%d fits succeeded" % (n_ok, len(table)))

    agg = ms.aggregate(table)
    agg.to_csv(OUT / "seed_summary.csv", index=False)
    focus = agg[agg["metric"] == args.metric].sort_values("mean", ascending=False)
    for _, r in focus.head(6).iterrows():
        progress.log("    %-24s %s %.4f +/- %.4f  [%.4f, %.4f]  range %.4f"
                     % (r["arm"], args.metric, r["mean"], r["sd"], r["min"], r["max"],
                        r["range"]))

    tests = ms.paired_seed_tests(table, reference=args.reference, metric=args.metric)
    tests.to_csv(OUT / "paired_tests.csv", index=False)
    floor = ms.seed_noise_floor(table, metric=args.metric)
    progress.log("  pooled seed sd %.5f; 95%% noise floor %.5f %s"
                 % (floor.get("pooled_seed_sd", float("nan")),
                    floor.get("noise_floor_95", float("nan")), args.metric))

    # Which single-run differences survive seed variance, and which do not.
    survives, dissolves = [], []
    if "mean_difference" in tests.columns:
        for _, r in tests[tests.get("status") == "OK"].iterrows():
            item = {"arm": r["arm"],
                    "mean_difference": float(r["mean_difference"]),
                    "p_value": float(r["p_value"]),
                    "adjusted_p": (None if pd.isna(r.get("adjusted_p"))
                                   else float(r.get("adjusted_p"))),
                    "abs_difference_vs_noise_floor":
                        float(abs(r["mean_difference"])
                              - floor.get("noise_floor_95", float("nan")))}
            (survives if bool(r.get("reject")) else dissolves).append(item)
    progress.log("  %d of %d arm differences survive BH correction at 0.05"
                 % (len(survives), len(survives) + len(dissolves)))

    # Within-run sampling variance for one seed, to contrast with the seed spread.
    within = pd.DataFrame()
    try:
        top = list(focus["arm"].head(4)) + [args.reference]
        _t, per_row = ms.run_seeds(data, [a for a in arms if a.name in set(top)],
                                   seeds=[seeds[0]], log=None)
        within = ms.within_run_intervals(per_row, sorted(set(top)), seeds[0])
        within.to_csv(OUT / "within_run_intervals.csv", index=False)
    except Exception as exc:  # noqa: BLE001
        progress.log("  within-run intervals skipped: %s: %s"
                     % (type(exc).__name__, exc))

    # Minimum detectable effect, from the machinery that already exists.
    mde = {}
    try:
        ref_rows = per_row.get((args.reference, seeds[0]))
        alt_name = next((a for a in focus["arm"] if a != args.reference), None)
        alt_rows = per_row.get((alt_name, seeds[0])) if alt_name else None
        if ref_rows is not None and alt_rows is not None:
            paired = ref_rows[["symbol", "episode_id", "is_episode"]].copy()
            paired["a"] = ref_rows["integrity_risk"].to_numpy()
            paired["b"] = alt_rows["integrity_risk"].to_numpy()
            paired["cluster"] = np.where(
                paired["episode_id"].astype(str) != "",
                paired["symbol"].astype(str) + "|"
                + paired["episode_id"].astype(str),
                paired["symbol"].astype(str))
            mde = pw.minimum_detectable_effect(paired, "cluster", "a", "b")
            mde["compared"] = "%s vs %s" % (args.reference, alt_name)
    except Exception as exc:  # noqa: BLE001
        mde = {"status": "NOT COMPUTED", "reason": "%s: %s" % (type(exc).__name__, exc)}

    summary = {
        "n_arms": len(arms), "n_seeds": len(seeds), "seeds": seeds,
        "metric": args.metric, "reference_arm": args.reference,
        "n_fits": int(len(table)), "n_fits_ok": n_ok,
        "seed_noise_floor": floor,
        "differences_surviving_correction": survives,
        "differences_within_seed_noise": dissolves,
        "within_run_intervals": within.to_dict(orient="records") if len(within) else [],
        "minimum_detectable_effect": mde,
        "interpretation": (
            "Every previously reported arm difference was a single run. A difference "
            "smaller than the seed noise floor above is not evidence that one arm is "
            "better; it is evidence that the pipeline is stochastic. Differences are "
            "reported both ways rather than filtered, so the ones that dissolve stay "
            "visible."),
        "holdout_policy": (
            "Validation only. Repeating a measurement on the frozen holdout across ten "
            "seeds would be ten looks at the data the freeze exists to protect."),
        "run_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "multiseed_version": ms.MULTISEED_VERSION,
        "environment": environment_snapshot(),
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "significance.json", summary)
    progress.log("done in %.0fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
