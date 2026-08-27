"""Multimodal robustness: degradation, missing modalities and misalignment (§11).

    python scripts/run_multimodal_robustness.py

Conditions, all against the same clean baseline on the same held-out actors:

``clean``                  undegraded reference
``noise_<block>``          per-feature Gaussian noise scaled to each feature's own spread
``dropout_<block>``        a fraction of values go missing, as a partial feed outage does
``missing_<block>``        the modality is absent entirely
``misaligned``             face rows paired with the wrong audio rows, same actor

The misalignment condition is the one worth arguing for. Every fusion result in this
project rests on audio and video being the *same utterance recorded simultaneously*,
joined on clip identity. If pairing them wrongly barely changes the score, the fusion gain
was never about correspondence and the design is decorative. This measures that.

The model is fitted once on clean training folds; only the evaluation side is degraded.
Refitting on corrupted data would ask whether the learner adapts, which is a different and
easier question than what happens to a deployed model when its inputs go bad.
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
SEEDS = (0, 1, 2)
SEVERITIES = (0.1, 0.25, 0.5)


def degrade(block: pd.DataFrame, kind: str, severity: float, seed: int,
            actors: np.ndarray | None = None) -> pd.DataFrame:
    """Apply one named degradation to one feature block."""
    rng = np.random.default_rng(seed)
    # astype(float) rather than copy(): some feature columns are bool-backed, and writing
    # a float array back into a bool column raises rather than casting.
    out = block.astype(float)
    M = out.to_numpy(float)

    if kind == "noise":
        sd = np.nanstd(M, axis=0)
        sd = np.where(np.isfinite(sd) & (sd > 0), sd, 1.0)
        M = M + rng.normal(0.0, 1.0, M.shape) * sd * severity
    elif kind == "dropout":
        M = np.where(rng.random(M.shape) < severity, np.nan, M)
    elif kind == "missing":
        M = np.full_like(M, np.nan)
    elif kind == "misaligned":
        # Permute rows *within* each actor, so the actor is unchanged and only the
        # correspondence between this block and the others is destroyed. Permuting across
        # actors would confound misalignment with a speaker change.
        idx = np.arange(len(out))
        if actors is not None:
            for a in np.unique(actors):
                where = np.flatnonzero(actors == a)
                if where.size > 1:
                    perm = rng.permutation(where.size)
                    # Guarantee a real derangement rather than an accidental identity.
                    while np.any(perm == np.arange(where.size)) and where.size > 2:
                        perm = rng.permutation(where.size)
                    idx[where] = where[perm]
        M = M[idx]
    else:
        raise ValueError("unknown degradation %r" % kind)

    out.iloc[:, :] = M
    return out


def score(meta, blocks: dict, seed: int) -> dict:
    """Leave-one-actor-out on whatever blocks are handed in."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score

    y = meta["emotion"].to_numpy()
    actors = meta["actor"].to_numpy()
    X = pd.concat([blocks[b] for b in sorted(blocks)], axis=1).loc[meta.index]
    Xv = np.nan_to_num(X.to_numpy(float), nan=0.0, posinf=0.0, neginf=0.0)

    preds = np.empty(len(y), dtype=object)
    for a in np.unique(actors):
        test = actors == a
        train = ~test
        if len(np.unique(y[train])) < 2 or not test.any():
            continue
        clf = RandomForestClassifier(n_estimators=300, random_state=seed,
                                     min_samples_leaf=2, n_jobs=1)
        clf.fit(Xv[train], y[train])
        preds[test] = clf.predict(Xv[test])

    keep = preds != None  # noqa: E711 - object array
    yt, yp = y[keep], preds[keep].astype(str)
    return {
        "accuracy": float(accuracy_score(yt, yp)),
        "balanced_accuracy": float(balanced_accuracy_score(yt, yp)),
        "macro_f1": float(f1_score(yt, yp, average="macro", zero_division=0)),
        "n": int(keep.sum()),
    }


def score_degraded(meta, clean_blocks: dict, seed: int, target: str | None,
                   kind: str, severity: float) -> dict:
    """Fit on clean training folds, evaluate with the target block degraded.

    The degradation is applied to the whole block before splitting, then only the
    evaluation rows are taken from the degraded copy: training rows keep their clean
    values. That is what "the model is unchanged, the feed is not" means.
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score

    y = meta["emotion"].to_numpy()
    actors = meta["actor"].to_numpy()

    clean_X = pd.concat([clean_blocks[b] for b in sorted(clean_blocks)],
                        axis=1).loc[meta.index]
    dirty = dict(clean_blocks)
    if target is not None:
        dirty[target] = degrade(clean_blocks[target], kind, severity, seed, actors)
    dirty_X = pd.concat([dirty[b] for b in sorted(dirty)], axis=1).loc[meta.index]

    Xc = np.nan_to_num(clean_X.to_numpy(float), nan=0.0, posinf=0.0, neginf=0.0)
    Xd = np.nan_to_num(dirty_X.to_numpy(float), nan=0.0, posinf=0.0, neginf=0.0)

    preds = np.empty(len(y), dtype=object)
    for a in np.unique(actors):
        test = actors == a
        train = ~test
        if len(np.unique(y[train])) < 2 or not test.any():
            continue
        clf = RandomForestClassifier(n_estimators=300, random_state=seed,
                                     min_samples_leaf=2, n_jobs=1)
        clf.fit(Xc[train], y[train])
        preds[test] = clf.predict(Xd[test])

    keep = preds != None  # noqa: E711
    yt, yp = y[keep], preds[keep].astype(str)
    return {
        "accuracy": float(accuracy_score(yt, yp)),
        "balanced_accuracy": float(balanced_accuracy_score(yt, yp)),
        "macro_f1": float(f1_score(yt, yp, average="macro", zero_division=0)),
        "n": int(keep.sum()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=3)
    args = ap.parse_args()

    from scripts.run_multimodal_multiseed import load_blocks

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    meta, blocks = load_blocks("full")
    seeds = list(SEEDS)[:args.seeds]
    progress.log("[multimodal robustness] %d clips, %d actors, %d seeds"
                 % (len(meta), meta["actor"].nunique(), len(seeds)))

    rows = []
    for seed in seeds:
        base = score_degraded(meta, blocks, seed, None, "noise", 0.0)
        rows.append({"condition": "clean", "target": "-", "kind": "none",
                     "severity": 0.0, "seed": seed, **base})

    clean_mean = float(np.mean([r["balanced_accuracy"] for r in rows]))
    progress.log("      clean baseline balanced %.4f" % clean_mean)

    for target in ("AUDIO", "FACE", "TEXT"):
        for kind, sevs in (("noise", SEVERITIES), ("dropout", SEVERITIES),
                           ("missing", (1.0,))):
            for sev in sevs:
                for seed in seeds:
                    r = score_degraded(meta, blocks, seed, target, kind, sev)
                    rows.append({"condition": "%s_%s" % (kind, target.lower()),
                                 "target": target, "kind": kind, "severity": sev,
                                 "seed": seed, **r})
                got = rows[-len(seeds):]
                v = float(np.mean([g["balanced_accuracy"] for g in got]))
                progress.log("      %-18s sev %.2f  balanced %.4f  (%+.4f)"
                             % ("%s_%s" % (kind, target.lower()), sev, v,
                                v - clean_mean))

    for target in ("FACE", "AUDIO"):
        for seed in seeds:
            r = score_degraded(meta, blocks, seed, target, "misaligned", 1.0)
            rows.append({"condition": "misaligned_%s" % target.lower(),
                         "target": target, "kind": "misaligned", "severity": 1.0,
                         "seed": seed, **r})
        got = rows[-len(seeds):]
        v = float(np.mean([g["balanced_accuracy"] for g in got]))
        progress.log("      %-18s          balanced %.4f  (%+.4f)"
                     % ("misaligned_%s" % target.lower(), v, v - clean_mean))

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "multimodal_robustness_runs.csv", index=False)

    agg = table.groupby(["condition", "target", "kind", "severity"]).agg(
        balanced_accuracy_mean=("balanced_accuracy", "mean"),
        balanced_accuracy_sd=("balanced_accuracy", "std"),
        accuracy_mean=("accuracy", "mean"),
        macro_f1_mean=("macro_f1", "mean"),
        n=("n", "first"), n_seeds=("seed", "count")).reset_index()
    agg["degradation"] = clean_mean - agg["balanced_accuracy_mean"]
    agg["relative_degradation"] = agg["degradation"] / max(1e-9, clean_mean)
    agg = agg.sort_values("degradation", ascending=False)
    agg.to_csv(OUT / "multimodal_robustness.csv", index=False)

    worst = agg.iloc[0]
    mis = agg[agg["kind"] == "misaligned"]
    report = {
        "n_clips": int(len(meta)), "n_actors": int(meta["actor"].nunique()),
        "seeds": seeds, "clean_balanced_accuracy": clean_mean,
        "conditions": jsonio.sanitise(agg.to_dict(orient="records")),
        "worst_condition": {
            "condition": str(worst["condition"]),
            "balanced_accuracy": float(worst["balanced_accuracy_mean"]),
            "degradation": float(worst["degradation"]),
            "relative_degradation": float(worst["relative_degradation"])},
        "misalignment": {
            "rows": jsonio.sanitise(mis.to_dict(orient="records")),
            "interpretation": (
                "Audio and video are joined on clip identity because they are the same "
                "utterance recorded simultaneously. Permuting one block within each "
                "actor keeps the speaker and the label distribution and destroys only "
                "the correspondence. A large drop means the fusion gain genuinely comes "
                "from the pairing; a small one would mean it never did."),
        },
        "protocol": ("fitted once on clean training folds, evaluated on degraded rows; "
                     "leave-one-actor-out and speaker-disjoint throughout"),
        "adversarial": ("NOT RUN. Every degradation here is random or structural. An "
                        "adversarial claim needs an attacker model."),
        "run_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "environment": environment_snapshot(),
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "multimodal_robustness.json", report)
    progress.log("  worst: %s balanced %.4f (%+.4f, %.1f%% relative)"
                 % (worst["condition"], worst["balanced_accuracy_mean"],
                    -worst["degradation"], 100 * worst["relative_degradation"]))
    progress.log("done in %.0fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
