"""Multi-seed evaluation of the MULTIMODAL arms (§1, §3).

    python scripts/run_multimodal_multiseed.py --tier full
    python scripts/run_multimodal_multiseed.py --tier vlm

Two tiers, because the VLM channel exists for only part of the corpus and pretending
otherwise would silently shrink every other arm to match it.

``full``  720 aligned RAVDESS performances, 12 actors. Arms over TEXT, AUDIO and FACE.
``vlm``    80 clips, 4 held-out actors, the frames a VLM actually processed. All 15
           subsets of TEXT, AUDIO, FACE and VLM.

Both tiers are speaker-disjoint and both are evaluated by leave-one-actor-out
cross-validation, so every clip is used and no fold ever scores a person it trained on.
Seeds vary the stochastic part of the pipeline -- the forest's bootstrap and feature
sampling -- which is what a seed study is for. The data, the folds and the features are
identical across seeds, so the spread reported is seed variance and nothing else.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import environment_snapshot, git_commit  # noqa: E402
from research.human_affect import corpora as C  # noqa: E402
from research.human_affect import fusion as fu  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "multimodal_multiseed"
CACHE = paths.DATA / "affective" / "_cache"
VLM_DESC = paths.REPO_ROOT / "outputs" / "vlm" / "vlm_descriptions.csv"

SEEDS = (0, 1, 2, 3, 4)


def _numeric(frame: pd.DataFrame, prefix: str, exclude: set) -> pd.DataFrame:
    cols = [c for c in frame.columns
            if c not in exclude and pd.api.types.is_numeric_dtype(frame[c])]
    sub = frame[cols].copy()
    sub.columns = ["%s_%s" % (prefix, c) for c in cols]
    return sub


EXCLUDE = {"emotion", "emotion_id", "intensity", "statement", "statement_id",
           "repetition", "actor", "actor_sex", "valence", "arousal", "modality",
           "split", "n_frames", "path", "clip_key", "src_modality"}


def load_blocks(tier: str, backend: str = "smolvlm-256m"):
    """Feature blocks joined on clip identity, plus the label/actor metadata."""
    face = C.drop_duplicate_video(
        pd.read_parquet(CACHE / "ravdess_face_features.parquet"))
    audio = pd.read_parquet(CACHE / "ravdess_speech_features.parquet")
    face["clip_key"] = face["path"].map(fu.clip_key)
    audio["clip_key"] = audio["path"].map(fu.clip_key)

    keys = set(face["clip_key"]) & set(audio["clip_key"])
    vlm = None
    if tier == "vlm":
        if not VLM_DESC.exists():
            raise SystemExit("VLM descriptions absent; run run_vlm_experiments.py")
        from scripts.run_vlm_ablation import vlm_features
        vlm = vlm_features(pd.read_csv(VLM_DESC), backend)
        keys &= set(vlm["clip_key"])
    keys = sorted(keys)

    def align(frame: pd.DataFrame) -> pd.DataFrame:
        return frame[frame["clip_key"].isin(keys)].drop_duplicates(
            "clip_key").set_index("clip_key").loc[keys]

    f, a = align(face), align(audio)
    blocks = {
        "FACE": _numeric(f, "face", EXCLUDE),
        "AUDIO": _numeric(a, "aud", EXCLUDE),
        # Two fixed sentences: the lexical channel is a control that carries nothing.
        "TEXT": pd.get_dummies(a["statement_id"].astype(int),
                               prefix="txt").astype(float),
    }
    if vlm is not None:
        blocks["VLM"] = align(vlm)
    meta = pd.DataFrame({"emotion": f["emotion"].to_numpy(),
                         "actor": f["actor"].to_numpy()}, index=keys)
    return meta, blocks


def evaluate(meta: pd.DataFrame, blocks: dict, subset: tuple, seed: int) -> dict:
    """Leave-one-actor-out scores for one subset at one seed."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import (
        accuracy_score,
        balanced_accuracy_score,
        cohen_kappa_score,
        f1_score,
    )

    X = pd.concat([blocks[b] for b in subset], axis=1).loc[meta.index]
    Xv = np.nan_to_num(X.to_numpy(float), nan=0.0, posinf=0.0, neginf=0.0)
    y = meta["emotion"].to_numpy()
    actors = meta["actor"].to_numpy()
    classes = sorted(set(y))

    preds = np.empty(len(y), dtype=object)
    proba = np.zeros((len(y), len(classes)))
    for actor in np.unique(actors):
        test = actors == actor
        train = ~test
        if len(np.unique(y[train])) < 2 or not test.any():
            continue
        clf = RandomForestClassifier(n_estimators=300, random_state=seed,
                                     min_samples_leaf=2, n_jobs=1)
        clf.fit(Xv[train], y[train])
        preds[test] = clf.predict(Xv[test])
        p = clf.predict_proba(Xv[test])
        index = {c: i for i, c in enumerate(clf.classes_)}
        for j, c in enumerate(classes):
            if c in index:
                proba[test, j] = p[:, index[c]]

    keep = preds != None  # noqa: E711 - object array; `is not None` is not elementwise
    if not keep.any():
        return {"subset": "+".join(subset), "seed": seed, "status": "NO USABLE FOLD"}

    yt = y[keep]
    yp = preds[keep].astype(str)
    pk = proba[keep]
    onehot = np.zeros_like(pk)
    for i, c in enumerate(yt):
        onehot[i, classes.index(c)] = 1.0

    # Equal-mass-bin ECE on the predicted-class confidence.
    conf = pk.max(axis=1)
    correct = (yp == yt).astype(float)
    order = np.argsort(conf)
    bins = np.array_split(order, min(10, max(1, len(order) // 5)))
    ece = float(sum(abs(correct[b].mean() - conf[b].mean()) * len(b)
                    for b in bins if len(b)) / max(1, len(order)))

    return {
        "subset": "+".join(subset), "seed": seed, "status": "OK",
        "n": int(keep.sum()), "n_features": int(Xv.shape[1]),
        "n_folds": int(len(np.unique(actors))),
        "accuracy": float(accuracy_score(yt, yp)),
        "balanced_accuracy": float(balanced_accuracy_score(yt, yp)),
        "macro_f1": float(f1_score(yt, yp, average="macro", zero_division=0)),
        "cohen_kappa": float(cohen_kappa_score(yt, yp)),
        "brier": float(np.mean(np.sum((pk - onehot) ** 2, axis=1))),
        "ece": ece,
        "mean_confidence": float(conf.mean()),
    }


def aggregate(table: pd.DataFrame, metrics=("balanced_accuracy", "accuracy",
                                            "macro_f1", "cohen_kappa", "ece",
                                            "brier")) -> pd.DataFrame:
    """Mean, sd, min, max and a 95% interval on the mean over seeds."""
    ok = table[table["status"] == "OK"]
    rows = []
    for subset, g in ok.groupby("subset"):
        row = {"subset": subset, "n_seeds": int(len(g)),
               "n": int(g["n"].iloc[0]), "n_folds": int(g["n_folds"].iloc[0]),
               "n_features": int(g["n_features"].iloc[0])}
        for m in metrics:
            if m not in g.columns:
                continue
            v = pd.to_numeric(g[m], errors="coerce").dropna().to_numpy(float)
            if v.size == 0:
                continue
            sd = float(v.std(ddof=1)) if v.size > 1 else float("nan")
            se = sd / np.sqrt(v.size) if v.size > 1 else float("nan")
            row.update({
                "%s_mean" % m: float(v.mean()), "%s_sd" % m: sd,
                "%s_min" % m: float(v.min()), "%s_max" % m: float(v.max()),
                "%s_ci_low" % m: float(v.mean() - 1.96 * se) if v.size > 1 else np.nan,
                "%s_ci_high" % m: float(v.mean() + 1.96 * se) if v.size > 1 else np.nan,
            })
        rows.append(row)
    return pd.DataFrame(rows).sort_values("balanced_accuracy_mean", ascending=False)


def noise_floor(table: pd.DataFrame, metric: str = "balanced_accuracy") -> dict:
    """Pooled within-arm seed standard deviation: the resolution of this experiment."""
    ok = table[table["status"] == "OK"]
    sds = []
    for _subset, g in ok.groupby("subset"):
        v = pd.to_numeric(g[metric], errors="coerce").dropna().to_numpy(float)
        if v.size > 1:
            sds.append(v.std(ddof=1))
    if not sds:
        return {"status": "INSUFFICIENT DATA"}
    pooled = float(np.sqrt(np.mean(np.square(sds))))
    return {
        "metric": metric, "pooled_seed_sd": pooled,
        "noise_floor_95": float(1.96 * pooled * np.sqrt(2)),
        "interpretation": (
            "A difference between two arms smaller than the 95%% floor (%.4f %s) is "
            "inside what re-seeding alone produces and is not established by this "
            "experiment." % (float(1.96 * pooled * np.sqrt(2)), metric)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tier", choices=["full", "vlm", "both"], default="both")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--backend", default="smolvlm-256m")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    seeds = list(SEEDS)[:args.seeds]
    tiers = ["full", "vlm"] if args.tier == "both" else [args.tier]
    summary: dict = {"seeds": seeds, "tiers": {}}

    for tier in tiers:
        meta, blocks = load_blocks(tier, backend=args.backend)
        names = ["TEXT", "AUDIO", "FACE"] + (["VLM"] if "VLM" in blocks else [])
        chance = 1.0 / meta["emotion"].nunique()
        progress.log("[%s] %d clips, %d actors, %d classes (chance %.4f), %d seeds"
                     % (tier, len(meta), meta["actor"].nunique(),
                        meta["emotion"].nunique(), chance, len(seeds)))
        for n, b in blocks.items():
            progress.log("      %-6s %d features" % (n, b.shape[1]))

        rows = []
        subsets = [s for k in range(1, len(names) + 1)
                   for s in combinations(names, k)]
        for subset in subsets:
            for seed in seeds:
                rows.append(evaluate(meta, blocks, subset, seed))
            got = [r for r in rows[-len(seeds):] if r["status"] == "OK"]
            if got:
                v = np.array([r["balanced_accuracy"] for r in got])
                progress.log("      %-24s balanced %.4f +/- %.4f  [%.4f, %.4f]"
                             % ("+".join(subset), v.mean(),
                                v.std(ddof=1) if v.size > 1 else 0.0,
                                v.min(), v.max()))

        table = pd.DataFrame(rows)
        table.to_csv(OUT / ("%s_seed_runs.csv" % tier), index=False)
        agg = aggregate(table)
        agg.to_csv(OUT / ("%s_seed_summary.csv" % tier), index=False)
        floor = noise_floor(table)
        progress.log("  [%s] pooled seed sd %.5f, 95%% noise floor %.5f"
                     % (tier, floor.get("pooled_seed_sd", float("nan")),
                        floor.get("noise_floor_95", float("nan"))))

        best = agg.iloc[0]
        unimodal = agg[~agg["subset"].str.contains(r"\+")]
        best_uni = unimodal.iloc[0] if len(unimodal) else None
        gain = (float(best["balanced_accuracy_mean"])
                - float(best_uni["balanced_accuracy_mean"])) if best_uni is not None \
            else float("nan")
        established = bool(gain > floor.get("noise_floor_95", np.inf))
        progress.log("  [%s] best %s %.4f; best unimodal %s %.4f; gain %+.4f -> %s"
                     % (tier, best["subset"], best["balanced_accuracy_mean"],
                        best_uni["subset"] if best_uni is not None else "-",
                        float(best_uni["balanced_accuracy_mean"])
                        if best_uni is not None else float("nan"),
                        gain, "established" if established else "NOT established"))

        summary["tiers"][tier] = {
            "n_clips": int(len(meta)), "n_actors": int(meta["actor"].nunique()),
            "n_classes": int(meta["emotion"].nunique()), "chance": chance,
            "blocks": {k: int(v.shape[1]) for k, v in blocks.items()},
            "n_subsets": len(subsets),
            "summary": jsonio.sanitise(agg.to_dict(orient="records")),
            "seed_noise_floor": floor,
            "best_subset": str(best["subset"]),
            "best_balanced_accuracy": float(best["balanced_accuracy_mean"]),
            "best_unimodal": (str(best_uni["subset"]) if best_uni is not None else None),
            "multimodal_gain_over_best_unimodal": gain,
            "gain_exceeds_seed_noise_floor": established,
            "protocol": ("leave-one-actor-out cross-validation, speaker-disjoint; seeds "
                         "vary only the forest's bootstrap and feature sampling, so the "
                         "reported spread is seed variance alone"),
        }

    summary.update({"run_at": datetime.now(UTC).isoformat(),
                    "git_commit": git_commit(),
                    "environment": environment_snapshot(),
                    "elapsed_s": round(time.time() - t0, 1)})
    jsonio.write(OUT / "multimodal_multiseed.json", summary)
    progress.log("done in %.0fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
