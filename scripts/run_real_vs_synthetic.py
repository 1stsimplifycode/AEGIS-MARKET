"""Does synthetic training data help, hurt, or do nothing? (§39)

    python scripts/run_real_vs_synthetic.py

Two arms, one evaluation set:

``REAL_ONLY``        fitted on the real training rows
``REAL_PLUS_SYNTH``  fitted on the real training rows plus copula-generated rows

**Both are scored on the same real evaluation rows.** Synthetic data never enters the
evaluation set, so whatever the difference turns out to be, it is a statement about
training and not an artefact of testing on the generator's own output.

The result is reported whichever way it falls. Synthetic augmentation is frequently
neutral or harmful on tabular data with an already-adequate training set, and a pipeline
that only reports the runs where it helped is not measuring anything.
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
from research.corpus import PROVENANCE_COLUMNS  # noqa: E402
from research.corpus import synthesis as SY  # noqa: E402
from research.evaluation import experiment as ex  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "corpus"
CORPUS = paths.DATA / "corpus"
SEEDS = (20260818, 20260819, 20260820)


def load_arms() -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Real panel rows, and the synthetic rows generated from their training half."""
    real = pd.read_parquet(paths.PANEL / "multimodal_dataset.parquet")
    synth_path = CORPUS / "synthetic_panel_features.parquet"
    if not synth_path.exists():
        raise SystemExit("run scripts/build_corpus.py first")

    synth = pd.read_parquet(synth_path)
    payload = [c for c in synth.columns if c not in PROVENANCE_COLUMNS]
    shared = [c for c in payload if c in real.columns]

    body = synth[shared].copy()
    # Synthetic rows are training rows only, and they are marked so every consumer can
    # see what they are without consulting a separate manifest.
    body["split"] = "train"
    body["is_synthetic"] = True
    for col in ("symbol", "episode_id", "state", "t_entry", "t_exit"):
        if col in real.columns and col not in body.columns:
            body[col] = "SYNTHETIC"
    if "date" in real.columns and "date" not in body.columns:
        body["date"] = real[real["split"] == "train"]["date"].max()
    # The label lives in the provenance column when it did not survive the generator's
    # feature cap. Taking it from there rather than defaulting to zero: a silently
    # all-negative synthetic arm would look like "synthetic data hurts" for the wrong
    # reason.
    if "is_episode" in body.columns:
        label = pd.to_numeric(body["is_episode"], errors="coerce")
    else:
        label = pd.to_numeric(synth["label"], errors="coerce")
    if label.isna().all():
        raise SystemExit("synthetic rows carry no usable episode label")
    body["is_episode"] = np.rint(label.fillna(0)).astype(int)

    real = real.copy()
    real["is_synthetic"] = False
    return real, body, shared


def score(frame: pd.DataFrame, arm: str, seed: int) -> dict:
    from research.data import dataset as ds

    spec = ex.ExperimentSpec(
        experiment_id="real_vs_synthetic",
        hypothesis="synthetic training rows change real-data generalization",
        arm=arm, modalities=list(ds.MODALITY_BLOCKS), seed=seed,
        eval_split="validation")
    res = ex.run(spec, frame, write=False)
    if res.status != "OK":
        return {"arm": arm, "seed": seed, "status": res.status,
                "reason": res.failure_reason}
    out = {"arm": arm, "seed": seed, "status": "OK"}
    out.update({k: v for k, v in res.detection.items()
                if isinstance(v, (int, float))})
    return out


def ratio_sweep(real: pd.DataFrame, synth: pd.DataFrame, n_real_train: int,
                t0: float) -> int:
    """Vary the synthetic share of the training set, holding the real rows fixed.

    The headline comparison mixes two things: whether synthetic rows carry usable
    structure, and whether they swamp the real ones. At the default sizes the synthetic
    rows outnumber the real ones four to one, so a large drop there cannot distinguish
    "this generator is not good enough" from "any 81% dilution would do this". Sweeping
    the ratio separates them.
    """
    rng = np.random.default_rng(20260818)
    rows = []
    for share in (0.0, 0.10, 0.25, 0.50, 0.75, 0.81):
        if share == 0.0:
            frame, n_syn = real, 0
        else:
            # share = n_syn / (n_real + n_syn)
            n_syn = int(round(share * n_real_train / max(1e-9, 1.0 - share)))
            n_syn = min(n_syn, len(synth))
            idx = rng.choice(len(synth), size=n_syn, replace=False)
            frame = pd.concat([real, synth.iloc[idx]], ignore_index=True)
        r = score(frame, "SYNTH_SHARE_%.2f" % share, 20260818)
        r["synthetic_share"] = float(share)
        r["n_synthetic"] = int(n_syn)
        r["n_train_total"] = int(n_real_train + n_syn)
        rows.append(r)
        progress.log("      share %.2f  (%6d synthetic)  auprc %.4f  auroc %.4f"
                     % (share, n_syn, r.get("auprc", float("nan")),
                        r.get("auroc", float("nan"))))

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "synthetic_ratio_sweep.csv", index=False)
    ok = table[table["status"] == "OK"]
    baseline = float(ok[ok["synthetic_share"] == 0.0]["auprc"].iloc[0])
    harmless = ok[(ok["auprc"] >= baseline - 0.00877)
                  & (ok["synthetic_share"] > 0)]
    report = {
        "baseline_auprc_real_only": baseline,
        "rows": rows,
        "largest_harmless_share": (float(harmless["synthetic_share"].max())
                                   if len(harmless) else 0.0),
        "interpretation": (
            "Real training rows are held fixed and synthetic rows are added on top, so "
            "every arm has the same real data and differs only in how much generated "
            "data sits beside it. The largest share whose AUPRC stays within the seed "
            "noise floor of the real-only baseline is the point past which this "
            "generator does more harm than good."),
        "run_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "synthetic_ratio_sweep.json", report)
    progress.log("  largest harmless synthetic share: %.2f"
                 % report["largest_harmless_share"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--ratio-sweep", action="store_true",
                    help="sweep the synthetic share of the training set")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    real, synth, shared = load_arms()
    n_real_train = int((real["split"] == "train").sum())
    progress.log("[real vs synthetic] %d real train rows, %d synthetic rows, "
                 "%d shared feature columns"
                 % (n_real_train, len(synth), len(shared)))

    combined = pd.concat([real, synth], ignore_index=True)
    progress.log("      combined training rows: %d (%.0f%% synthetic)"
                 % (int((combined["split"] == "train").sum()),
                    100.0 * len(synth) / max(1, n_real_train + len(synth))))

    # Evaluation is real by construction: synthetic rows are all labelled train.
    ev_synth = int(((combined["split"] != "train")
                    & combined["is_synthetic"].fillna(False)).sum())
    if ev_synth:
        raise SystemExit("%d synthetic rows reached an evaluation split" % ev_synth)

    if args.ratio_sweep:
        return ratio_sweep(real, synth, n_real_train, t0)

    rows = []
    for seed in list(SEEDS)[:args.seeds]:
        for arm, frame in (("REAL_ONLY", real), ("REAL_PLUS_SYNTH", combined)):
            r = score(frame, arm, seed)
            rows.append(r)
            progress.log("      seed %d  %-16s auprc %.4f  auroc %.4f"
                         % (seed, arm, r.get("auprc", float("nan")),
                            r.get("auroc", float("nan"))))

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "real_vs_synthetic.csv", index=False)

    ok = table[table["status"] == "OK"]
    summary = {}
    for arm, g in ok.groupby("arm"):
        summary[arm] = {m: {"mean": float(g[m].mean()),
                            "sd": float(g[m].std(ddof=1)) if len(g) > 1 else float("nan")}
                        for m in ("auprc", "auroc", "f1", "brier", "ece")
                        if m in g.columns}

    verdict = {"status": "INSUFFICIENT DATA"}
    if {"REAL_ONLY", "REAL_PLUS_SYNTH"} <= set(ok["arm"]):
        a = ok[ok["arm"] == "REAL_ONLY"].set_index("seed")["auprc"]
        b = ok[ok["arm"] == "REAL_PLUS_SYNTH"].set_index("seed")["auprc"]
        common = sorted(set(a.index) & set(b.index))
        diff = (b.loc[common] - a.loc[common]).to_numpy(float)
        # The seed noise floor STATS-16 measured on this same pipeline.
        floor = 0.00877
        helps = bool(diff.mean() > floor)
        hurts = bool(diff.mean() < -floor)
        verdict = {
            "metric": "auprc",
            "n_paired_seeds": len(common),
            "mean_difference": float(diff.mean()),
            "seed_noise_floor": floor,
            "synthetic_helps": helps,
            "synthetic_hurts": hurts,
            "reading": ("adding synthetic training rows improves real-data AUPRC beyond "
                        "the seed noise floor" if helps else
                        "adding synthetic training rows degrades real-data AUPRC beyond "
                        "the seed noise floor" if hurts else
                        "the difference is inside the seed noise floor, so this "
                        "experiment does not establish an effect either way"),
        }
        progress.log("  synthetic minus real-only: %+.4f auprc (noise floor %.5f) -> %s"
                     % (diff.mean(), floor,
                        "helps" if helps else "hurts" if hurts else "not established"))

    # Fidelity and memorisation of the generator that produced the arm.
    real_train = real[real["split"] == "train"]
    fidelity = SY.fidelity(real_train, synth, shared[:40])
    memo = SY.memorisation(real_train, synth, shared[:40])
    progress.log("  generator: mean KS %.4f, correlation error %.4f, "
                 "memorisation ratio %.3f (%d exact copies)"
                 % (fidelity["ks_statistic_mean"],
                    fidelity["correlation_abs_error_mean"],
                    memo.get("distance_ratio", float("nan")),
                    memo.get("n_exact_copies", -1)))

    report = {
        "n_real_train": n_real_train,
        "n_synthetic": int(len(synth)),
        "shared_feature_columns": len(shared),
        "per_run": rows,
        "summary": summary,
        "verdict": verdict,
        "generator_fidelity": fidelity,
        "generator_memorisation": memo,
        "evaluation_policy": (
            "Both arms are scored on the same real validation rows. Synthetic rows are "
            "forced to the training split by the corpus builder and the runner refuses "
            "to proceed if any reaches an evaluation split."),
        "run_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "environment": environment_snapshot(),
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "real_vs_synthetic.json", report)
    progress.log("done in %.0fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
