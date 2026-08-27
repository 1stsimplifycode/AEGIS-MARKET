"""Modality attribution, calibration and representation analysis (§9, §10, §15).

    python scripts/run_multimodal_xai_fairness.py

**Attribution** is group permutation importance over whole modality blocks. Each block is
shuffled as a unit on the evaluation fold and the drop is measured, so correlated features
inside a block are not destroyed piecemeal. This is a faithfulness-evaluated attribution:
it is defined by an intervention on the model's own inputs and it measures what the model
actually loses.

A VLM's prose description is **not** in that category and is never called an explanation
here. It is a *model-generated visual rationale*: readable, possibly useful, and never
verified to correspond to anything the classifier used.

**Calibration** is consolidated across every arm into one table under a single
definition of ECE, so the numbers are comparable.

**Representation** is deliberately not called demographic fairness. RAVDESS publishes
actor sex and nothing else about the people, so the groups analysed are the ones the
corpus documents -- sex, emotional intensity, spoken statement -- plus two condition
groups the pipeline measures for itself: face-detection quality and voiced fraction.
Every group is reported with its sample size and a Wilson interval, and a gap whose
intervals overlap is reported as unestablished.
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

OUT = paths.REPO_ROOT / "outputs" / "human_affect" / "experiments"
CACHE = paths.DATA / "affective" / "_cache"
SEEDS = (0, 1, 2)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (float(centre - half), float(centre + half))


def fit_predict(meta, blocks, seed: int, permute: str | None = None):
    """Leave-one-actor-out predictions, optionally with one block shuffled at test."""
    from sklearn.ensemble import RandomForestClassifier

    y = meta["emotion"].to_numpy()
    actors = meta["actor"].to_numpy()
    classes = sorted(set(y))
    order = sorted(blocks)

    rng = np.random.default_rng(seed)
    use = dict(blocks)
    if permute is not None:
        # float, not copy(): bool-backed columns reject a float write-back.
        shuffled = blocks[permute].astype(float)
        # Shuffle within actor: permuting across actors would also change the speaker,
        # confounding "this block matters" with "this speaker matters".
        idx = np.arange(len(shuffled))
        for a in np.unique(actors):
            where = np.flatnonzero(actors == a)
            idx[where] = rng.permutation(where)
        shuffled.iloc[:, :] = shuffled.to_numpy()[idx]
        use[permute] = shuffled

    Xc = np.nan_to_num(pd.concat([blocks[b] for b in order], axis=1)
                       .loc[meta.index].to_numpy(float), nan=0.0,
                       posinf=0.0, neginf=0.0)
    Xp = np.nan_to_num(pd.concat([use[b] for b in order], axis=1)
                       .loc[meta.index].to_numpy(float), nan=0.0,
                       posinf=0.0, neginf=0.0)

    preds = np.empty(len(y), dtype=object)
    proba = np.zeros((len(y), len(classes)))
    for a in np.unique(actors):
        test = actors == a
        train = ~test
        if len(np.unique(y[train])) < 2 or not test.any():
            continue
        clf = RandomForestClassifier(n_estimators=300, random_state=seed,
                                     min_samples_leaf=2, n_jobs=1)
        clf.fit(Xc[train], y[train])
        preds[test] = clf.predict(Xp[test])
        p = clf.predict_proba(Xp[test])
        index = {c: i for i, c in enumerate(clf.classes_)}
        for j, c in enumerate(classes):
            if c in index:
                proba[test, j] = p[:, index[c]]
    return preds.astype(str), proba, classes


def ece_of(proba: np.ndarray, correct: np.ndarray, n_bins: int = 10) -> float:
    conf = proba.max(axis=1)
    order = np.argsort(conf)
    bins = np.array_split(order, n_bins)
    return float(sum(abs(correct[b].mean() - conf[b].mean()) * len(b)
                     for b in bins if len(b)) / max(1, len(order)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=3)
    args = ap.parse_args()

    from sklearn.metrics import balanced_accuracy_score

    from scripts.run_multimodal_multiseed import load_blocks

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    seeds = list(SEEDS)[:args.seeds]

    # The VLM tier so the attribution can include the VLM block alongside the others.
    meta, blocks = load_blocks("vlm")
    progress.log("[xai] %d clips, %d actors, blocks %s"
                 % (len(meta), meta["actor"].nunique(), sorted(blocks)))

    y = meta["emotion"].to_numpy()
    base_scores, base_proba = [], None
    for seed in seeds:
        preds, proba, _classes = fit_predict(meta, blocks, seed)
        base_scores.append(balanced_accuracy_score(y, preds))
        if base_proba is None:
            base_proba = proba
    base = float(np.mean(base_scores))
    progress.log("      full-model balanced accuracy %.4f" % base)

    attribution = []
    for block in sorted(blocks):
        drops = []
        for seed in seeds:
            preds, _p, _c = fit_predict(meta, blocks, seed, permute=block)
            drops.append(base - balanced_accuracy_score(y, preds))
        attribution.append({
            "block": block, "n_features": int(blocks[block].shape[1]),
            "importance_mean": float(np.mean(drops)),
            "importance_sd": float(np.std(drops, ddof=1)) if len(drops) > 1 else 0.0,
            "n_seeds": len(seeds),
        })
        progress.log("      %-6s importance %+.4f +/- %.4f"
                     % (block, np.mean(drops),
                        np.std(drops, ddof=1) if len(drops) > 1 else 0.0))
    attribution.sort(key=lambda r: -r["importance_mean"])
    pd.DataFrame(attribution).to_csv(OUT / "modality_attribution.csv", index=False)

    # ---- calibration across arms -------------------------------------------------
    progress.log("[calibration] consolidating every arm under one ECE definition")
    cal_rows = []
    for name, subset in (("TEXT", ["TEXT"]), ("AUDIO", ["AUDIO"]), ("FACE", ["FACE"]),
                         ("VLM", ["VLM"]),
                         ("AUDIO+FACE", ["AUDIO", "FACE"]),
                         ("FULL", sorted(blocks))):
        if any(b not in blocks for b in subset):
            continue
        sub = {b: blocks[b] for b in subset}
        eces, briers, accs, confs = [], [], [], []
        for seed in seeds:
            preds, proba, classes = fit_predict(meta, sub, seed)
            correct = (preds == y).astype(float)
            onehot = np.zeros_like(proba)
            for i, c in enumerate(y):
                onehot[i, classes.index(c)] = 1.0
            eces.append(ece_of(proba, correct))
            briers.append(float(np.mean(np.sum((proba - onehot) ** 2, axis=1))))
            accs.append(float(correct.mean()))
            confs.append(float(proba.max(axis=1).mean()))
        cal_rows.append({
            "arm": name, "n": int(len(y)), "n_seeds": len(seeds),
            "accuracy": float(np.mean(accs)),
            "mean_confidence": float(np.mean(confs)),
            "confidence_minus_accuracy": float(np.mean(confs) - np.mean(accs)),
            "ece": float(np.mean(eces)), "ece_sd": float(np.std(eces, ddof=1))
            if len(eces) > 1 else 0.0,
            "brier": float(np.mean(briers)),
        })
        progress.log("      %-11s acc %.4f  conf %.4f  ece %.4f  brier %.4f"
                     % (name, np.mean(accs), np.mean(confs), np.mean(eces),
                        np.mean(briers)))

    cal = pd.DataFrame(cal_rows).sort_values("ece")
    cal.to_csv(OUT / "calibration_summary.csv", index=False)
    best_cal = cal.iloc[0]["arm"]
    over = cal.loc[cal["confidence_minus_accuracy"].idxmax()]
    under = cal.loc[cal["confidence_minus_accuracy"].idxmin()]

    # ---- representation ------------------------------------------------------------
    progress.log("[representation] groups the corpus actually documents")
    face = pd.read_parquet(CACHE / "ravdess_face_features.parquet")
    audio = pd.read_parquet(CACHE / "ravdess_speech_features.parquet")
    from research.human_affect import corpora as C
    from research.human_affect import fusion as fu
    face = C.drop_duplicate_video(face)
    face["clip_key"] = face["path"].map(fu.clip_key)
    audio["clip_key"] = audio["path"].map(fu.clip_key)
    f = face.drop_duplicates("clip_key").set_index("clip_key").reindex(meta.index)
    a = audio.drop_duplicates("clip_key").set_index("clip_key").reindex(meta.index)

    preds, _p, _c = fit_predict(meta, blocks, seeds[0])
    correct = (preds == y).astype(int)

    groups = pd.DataFrame({
        "actor_sex": f["actor_sex"].to_numpy(),
        "intensity": f["intensity"].to_numpy(),
        "statement": f["statement_id"].astype(str).to_numpy(),
        "face_detection_quality": pd.qcut(
            f["face_detection_rate"].astype(float), 2,
            labels=["lower", "higher"], duplicates="drop").astype(str).to_numpy()
        if f["face_detection_rate"].nunique() > 1 else "constant",
        "voiced_fraction": pd.qcut(
            a["voiced_fraction"].astype(float), 2, labels=["lower", "higher"],
            duplicates="drop").astype(str).to_numpy()
        if "voiced_fraction" in a.columns and a["voiced_fraction"].nunique() > 1
        else "constant",
    }, index=meta.index)

    rows = []
    for col in groups.columns:
        for value, idx in groups.groupby(col).groups.items():
            sel = groups.index.isin(idx)
            n = int(sel.sum())
            k = int(correct[sel].sum())
            lo, hi = wilson(k, n)
            rows.append({"group": col, "value": str(value), "n": n,
                         "accuracy": float(k / n) if n else float("nan"),
                         "ci_low": lo, "ci_high": hi,
                         "status": "OK" if n >= 20 else "INSUFFICIENT DATA"})
    rep = pd.DataFrame(rows)
    rep.to_csv(OUT / "representation_analysis.csv", index=False)

    gaps = []
    for col, g in rep[rep["status"] == "OK"].groupby("group"):
        if len(g) < 2:
            continue
        hi = g.loc[g["accuracy"].idxmax()]
        lo = g.loc[g["accuracy"].idxmin()]
        overlap = not (lo["ci_high"] < hi["ci_low"])
        gaps.append({"group": col, "best": hi["value"], "worst": lo["value"],
                     "n_best": int(hi["n"]), "n_worst": int(lo["n"]),
                     "gap": float(hi["accuracy"] - lo["accuracy"]),
                     "intervals_overlap": bool(overlap),
                     "reading": ("unestablished at this sample size" if overlap
                                 else "supported at this sample size")})
        progress.log("      %-22s best %-8s worst %-8s gap %+.4f  %s"
                     % (col, hi["value"], lo["value"],
                        hi["accuracy"] - lo["accuracy"],
                        "overlap" if overlap else "disjoint"))

    report = {
        "n_clips": int(len(meta)), "n_actors": int(meta["actor"].nunique()),
        "seeds": seeds,
        "attribution": {
            "method": ("group permutation importance; each modality block shuffled as a "
                       "unit within actor on the evaluation fold"),
            "faithfulness": ("defined by an intervention on the model's own inputs, so "
                             "it measures what the model loses rather than what a "
                             "surrogate believes"),
            "full_model_balanced_accuracy": base,
            "blocks": attribution,
        },
        "calibration": {
            "rows": jsonio.sanitise(cal.to_dict(orient="records")),
            "best_calibrated": str(best_cal),
            "most_overconfident": {"arm": str(over["arm"]),
                                   "confidence_minus_accuracy": float(
                                       over["confidence_minus_accuracy"])},
            "most_underconfident": {"arm": str(under["arm"]),
                                    "confidence_minus_accuracy": float(
                                        under["confidence_minus_accuracy"])},
            "definition": "equal-mass-bin ECE on the predicted-class confidence, 10 bins",
        },
        "representation": {
            "rows": jsonio.sanitise(rep.to_dict(orient="records")),
            "gaps": gaps,
            "note": ("Not demographic fairness. RAVDESS publishes actor sex and nothing "
                     "else about the people, so no other person-level attribute is "
                     "analysed and none is inferred. The remaining groups are recording "
                     "conditions the pipeline measures for itself."),
        },
        "vlm_rationale_status": (
            "A VLM description is a model-generated visual rationale, not a faithful "
            "explanation. No faithfulness evaluation of it exists, so it is never "
            "reported as an explanation of the classifier."),
        "run_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "environment": environment_snapshot(),
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "xai_fairness.json", report)
    progress.log("  best calibrated %s; most overconfident %s (%+.4f)"
                 % (best_cal, over["arm"], over["confidence_minus_accuracy"]))
    progress.log("done in %.0fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
