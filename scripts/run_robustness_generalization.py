"""Execute the STATS-15 robustness and generalization harness.

    python scripts/run_robustness_generalization.py --all
    python scripts/run_robustness_generalization.py --stage period --stage instrument

Writes to ``outputs/stats/15_robustness_generalization/``. Nothing under
``research_artifacts/`` is touched, and the frozen holdout is never read: the harness
refuses to score a frame containing holdout rows.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import environment_snapshot, git_commit  # noqa: E402
from research.evaluation import robustness as rb  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "stats" / "15_robustness_generalization"
SEED = 20260818

STAGES = ("input", "missingness", "training_size", "period", "instrument")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--stage", action="append", choices=list(STAGES))
    ap.add_argument("--dataset", default="multimodal_dataset.parquet")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    stages = list(STAGES) if args.all else (args.stage or ["input"])

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    data = pd.read_parquet(paths.PANEL / args.dataset)
    work = rb.working_set(data)
    progress.log("[stats-15] %d rows in train+validation, %d held frozen and untouched"
                 % (len(work), int((data["split"] == "holdout").sum())))

    robustness_frames, generalization_frames = [], []
    summary: dict = {"seed": args.seed, "dataset": args.dataset,
                     "n_rows_used": int(len(work)),
                     "n_rows_frozen_and_unused": int(
                         (data["split"] == "holdout").sum())}

    if "input" in stages:
        progress.log("[input] degrading the evaluation signal; "
                     "the model is fitted once on clean data")
        f = rb.input_robustness(data, seed=args.seed, log=progress.log)
        robustness_frames.append(f)
    if "missingness" in stages:
        progress.log("[missingness] taking each modality offline")
        f = rb.missingness_robustness(data, seed=args.seed, log=progress.log)
        robustness_frames.append(f)
    if "training_size" in stages:
        progress.log("[training size] symbol-level learning curve")
        f = rb.training_size_curve(data, seed=args.seed, log=progress.log)
        robustness_frames.append(f)
    if "period" in stages:
        progress.log("[period] expanding-window transfer forward in time")
        generalization_frames.append(rb.period_transfer(data, seed=args.seed,
                                                        log=progress.log))
    if "instrument" in stages:
        progress.log("[instrument] transfer to disjoint tickers")
        generalization_frames.append(rb.instrument_transfer(data, seed=args.seed,
                                                            log=progress.log))

    if robustness_frames:
        table = pd.concat(robustness_frames, ignore_index=True)
        table.to_csv(OUT / "robustness.csv", index=False)
        summary["robustness_rows"] = int(len(table))
        worst = table[(table.get("corruption") != "none")
                      & table.get("degradation").notna()] \
            if "degradation" in table.columns else table.iloc[0:0]
        if len(worst):
            w = worst.loc[worst["degradation"].idxmax()]
            summary["worst_degradation"] = {
                "family": w.get("family"), "corruption": w.get("corruption"),
                "target": w.get("target"), "severity": float(w.get("severity", 0.0)),
                "auprc": float(w.get("auprc", float("nan"))),
                "degradation": float(w.get("degradation", float("nan")))}
            progress.log("  worst degradation: %s %s at %.2f -> auprc %.4f (%+.4f)"
                         % (w.get("corruption"), w.get("target"),
                            w.get("severity", 0.0), w.get("auprc", float("nan")),
                            -w.get("degradation", 0.0)))

    if generalization_frames:
        table = pd.concat(generalization_frames, ignore_index=True)
        table.to_csv(OUT / "generalization.csv", index=False)
        summary["generalization_rows"] = int(len(table))
        ok = table[table["status"] == "OK"] if "status" in table.columns else table
        for family, g in ok.groupby("family"):
            summary["%s_transfer" % family] = {
                "n_folds": int(len(g)),
                "auprc_mean": float(g["auprc"].mean()),
                "auprc_min": float(g["auprc"].min()),
                "auprc_max": float(g["auprc"].max()),
            }
            progress.log("  %s transfer: %d folds, auprc %.4f (%.4f - %.4f)"
                         % (family, len(g), g["auprc"].mean(), g["auprc"].min(),
                            g["auprc"].max()))

    summary["dataset_transfer"] = rb.dataset_transfer_status()
    summary["adversarial_robustness"] = (
        "NOT RUN. Every corruption here is random. An adversarial claim needs a threat "
        "model and an attacker who sees the detector, which is a different experiment.")
    summary["holdout_policy"] = (
        "The frozen holdout was neither read nor scored. assert_no_holdout() raises on "
        "any frame carrying holdout rows, and every fit in this run passed through it.")
    summary.update({"run_at": datetime.now(UTC).isoformat(),
                    "git_commit": git_commit(),
                    "robustness_version": rb.ROBUSTNESS_VERSION,
                    "environment": environment_snapshot(),
                    "elapsed_s": round(time.time() - t0, 1)})
    jsonio.write(OUT / "run.json", summary)
    progress.log("done in %.0fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
