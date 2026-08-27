"""Fusion-strategy comparison on one corpus, one metric, one split (§8).

    python scripts/run_fusion_strategies.py

**First, a correction that the rest of this file depends on.** An earlier report of mine
put four numbers side by side -- speech 0.5458, face 0.3917, text 0.6182, fusion 0.5938 --
in a way that invites reading "fusion underperforms text". They are not comparable:

    text 0.6182   accuracy, GoEmotions, 7 Ekman classes, chance 0.1429
    fusion 0.5938 balanced accuracy, RAVDESS, 8 classes, chance 0.1250

Different corpora, different class counts, different metrics. **On RAVDESS -- the corpus
fusion is actually evaluated on -- the text channel scores exactly chance, 0.1250**,
because the corpus speaks two fixed sentences. Fusion at 0.5938 is above every unimodal
arm there, by a wide margin. There is no fusion-underperforms-text finding to explain; the
comparison itself was the error.

What *is* worth asking is which fusion rule is best, so this compares five of them on the
same clips, the same actors and the same metric:

``text_only``      the uninformative control
``early``          concatenate the feature blocks, fit one model
``late``           one model per modality, average the posteriors
``weighted``       validation-fitted weights, geometric pooling
``uncertainty``    weights from per-clip confidence rather than fitted globally

Every arm is leave-one-actor-out and speaker-disjoint. Seeds vary only the learner.
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
SEEDS = (0, 1, 2, 3, 4)
STRATEGIES = ("text_only", "early", "late", "weighted", "uncertainty")


def _posteriors(clf, X, classes):
    p = clf.predict_proba(X)
    index = {c: i for i, c in enumerate(clf.classes_)}
    return np.stack([p[:, index[c]] if c in index else np.zeros(len(X))
                     for c in classes], axis=1)


def evaluate(meta, blocks, strategy: str, seed: int) -> dict:
    """Leave-one-actor-out scores for one fusion rule at one seed."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import (
        accuracy_score,
        balanced_accuracy_score,
        cohen_kappa_score,
        f1_score,
    )

    y = meta["emotion"].to_numpy()
    actors = meta["actor"].to_numpy()
    classes = sorted(set(y))
    fused = np.zeros((len(y), len(classes)))

    use = ["TEXT"] if strategy == "text_only" else ["AUDIO", "FACE"]

    for actor in np.unique(actors):
        test = actors == actor
        train = ~test
        if len(np.unique(y[train])) < 2 or not test.any():
            continue

        if strategy == "early":
            X = pd.concat([blocks[b] for b in use], axis=1).loc[meta.index]
            Xv = np.nan_to_num(X.to_numpy(float), nan=0.0, posinf=0.0, neginf=0.0)
            clf = RandomForestClassifier(n_estimators=300, random_state=seed,
                                         min_samples_leaf=2, n_jobs=1)
            clf.fit(Xv[train], y[train])
            fused[test] = _posteriors(clf, Xv[test], classes)
            continue

        per_mod = {}
        for b in use:
            Xb = blocks[b].loc[meta.index]
            Xv = np.nan_to_num(Xb.to_numpy(float), nan=0.0, posinf=0.0, neginf=0.0)
            clf = RandomForestClassifier(n_estimators=300, random_state=seed,
                                         min_samples_leaf=2, n_jobs=1,
                                         oob_score=True, bootstrap=True)
            clf.fit(Xv[train], y[train])
            # Out-of-bag posteriors for the weight search, not in-bag ones. A forest's
            # posteriors on its own training rows are close to memorised, so a grid
            # fitted against them optimises a fiction: on the first run this drove the
            # weighted arm to a degenerate face-only solution scoring exactly what
            # face-alone scores, which is how the defect announced itself. OOB
            # predictions come only from trees that did not see the row.
            oob = getattr(clf, "oob_decision_function_", None)
            if oob is None or not np.isfinite(oob).all():
                oob = clf.predict_proba(Xv[train])
            index = {c: i for i, c in enumerate(clf.classes_)}
            oob_aligned = np.stack(
                [oob[:, index[c]] if c in index else np.zeros(oob.shape[0])
                 for c in classes], axis=1)
            per_mod[b] = (_posteriors(clf, Xv[test], classes), oob_aligned)

        if strategy in ("text_only", "late"):
            stack = np.stack([v[0] for v in per_mod.values()])
            fused[test] = stack.mean(axis=0)

        elif strategy == "weighted":
            # Weights fitted on the training folds by grid search, then applied to the
            # held-out actor. Fitting them on the test fold would be the leak this whole
            # protocol exists to avoid.
            best_w, best_score = None, -np.inf
            grid = np.linspace(0.0, 1.0, 11)
            for w in grid:
                weights = {b: (w if i == 0 else 1.0 - w)
                           for i, b in enumerate(per_mod)}
                logs = sum(weights[b] * np.log(np.clip(per_mod[b][1], 1e-9, 1.0))
                           for b in per_mod)
                pred = np.array([classes[i] for i in logs.argmax(axis=1)])
                score = balanced_accuracy_score(y[train], pred)
                if score > best_score:
                    best_score, best_w = score, weights
            logs = sum(best_w[b] * np.log(np.clip(per_mod[b][0], 1e-9, 1.0))
                       for b in per_mod)
            e = np.exp(logs - logs.max(axis=1, keepdims=True))
            fused[test] = e / e.sum(axis=1, keepdims=True)

        elif strategy == "uncertainty":
            # Per-clip weights from each modality's own confidence, so a modality that is
            # unsure about *this* clip is down-weighted for it rather than globally.
            logs = 0.0
            for b in per_mod:
                p = np.clip(per_mod[b][0], 1e-9, 1.0)
                conf = p.max(axis=1, keepdims=True)
                entropy = -(p * np.log(p)).sum(axis=1, keepdims=True)
                w = conf / (1.0 + entropy)
                logs = logs + w * np.log(p)
            e = np.exp(logs - logs.max(axis=1, keepdims=True))
            fused[test] = e / e.sum(axis=1, keepdims=True)

    pred = np.array([classes[i] for i in fused.argmax(axis=1)])
    onehot = np.zeros_like(fused)
    for i, c in enumerate(y):
        onehot[i, classes.index(c)] = 1.0
    conf = fused.max(axis=1)
    correct = (pred == y).astype(float)
    order = np.argsort(conf)
    bins = np.array_split(order, 10)
    ece = float(sum(abs(correct[b].mean() - conf[b].mean()) * len(b)
                    for b in bins if len(b)) / max(1, len(order)))

    return {
        "strategy": strategy, "seed": seed, "status": "OK", "n": int(len(y)),
        # aggregate() reports the fold and feature counts beside every mean, so a reader
        # never sees a spread without the sample size that produced it.
        "n_folds": int(len(np.unique(actors))),
        "n_features": int(sum(blocks[b].shape[1] for b in use)),
        "accuracy": float(accuracy_score(y, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, average="macro", zero_division=0)),
        "cohen_kappa": float(cohen_kappa_score(y, pred)),
        "brier": float(np.mean(np.sum((fused - onehot) ** 2, axis=1))),
        "ece": ece, "mean_confidence": float(conf.mean()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=5)
    args = ap.parse_args()

    from scripts.run_multimodal_multiseed import aggregate, load_blocks, noise_floor

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    meta, blocks = load_blocks("full")
    chance = 1.0 / meta["emotion"].nunique()
    seeds = list(SEEDS)[:args.seeds]
    progress.log("[fusion strategies] %d clips, %d actors, %d classes (chance %.4f)"
                 % (len(meta), meta["actor"].nunique(), meta["emotion"].nunique(),
                    chance))

    rows = []
    for strategy in STRATEGIES:
        for seed in seeds:
            rows.append(evaluate(meta, blocks, strategy, seed))
        got = rows[-len(seeds):]
        v = np.array([r["balanced_accuracy"] for r in got])
        e = np.array([r["ece"] for r in got])
        progress.log("      %-12s balanced %.4f +/- %.4f  ece %.4f  [%.4f, %.4f]"
                     % (strategy, v.mean(), v.std(ddof=1) if v.size > 1 else 0.0,
                        e.mean(), v.min(), v.max()))

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "fusion_strategy_runs.csv", index=False)
    agg = aggregate(table.rename(columns={"strategy": "subset"}))
    agg = agg.rename(columns={"subset": "strategy"})
    agg.to_csv(OUT / "fusion_strategy_summary.csv", index=False)
    floor = noise_floor(table.rename(columns={"strategy": "subset"}))

    ok = table[table["status"] == "OK"]
    means = ok.groupby("strategy")["balanced_accuracy"].mean()
    best = means.idxmax()
    ranked = means.sort_values(ascending=False)
    spread = float(ranked.iloc[0] - ranked[ranked.index != "text_only"].iloc[-1])

    report = {
        "corpus": "RAVDESS audiovisual, 8 classes",
        "n_clips": int(len(meta)), "n_actors": int(meta["actor"].nunique()),
        "chance": chance, "seeds": seeds,
        "protocol": "leave-one-actor-out, speaker-disjoint; fusion weights fitted on the "
                    "training folds only",
        "runs": rows,
        "summary": jsonio.sanitise(agg.to_dict(orient="records")),
        "seed_noise_floor": floor,
        "best_strategy": str(best),
        "ranking": {str(k): float(v) for k, v in ranked.items()},
        "spread_between_real_strategies": spread,
        "spread_exceeds_noise_floor": bool(
            spread > floor.get("noise_floor_95", np.inf)),
        "correction": (
            "An earlier report placed text 0.6182 beside fusion 0.5938 and invited the "
            "reading that fusion underperforms text. Those are different corpora and "
            "different metrics: 0.6182 is accuracy on GoEmotions over 7 classes, 0.5938 "
            "is balanced accuracy on RAVDESS over 8. On RAVDESS the text channel scores "
            "exactly chance (0.1250) because the corpus speaks two fixed sentences, and "
            "fusion is far above every unimodal arm. The comparison was the error, not "
            "the fusion."),
        "run_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "environment": environment_snapshot(),
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "fusion_strategies.json", report)
    progress.log("  best %s; spread between real strategies %.4f (floor %.4f) -> %s"
                 % (best, spread, floor.get("noise_floor_95", float("nan")),
                    "established" if report["spread_exceeds_noise_floor"]
                    else "NOT established"))
    progress.log("done in %.0fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
