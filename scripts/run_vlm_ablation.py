"""Does the VLM see anything the specialised facial model does not? (§30, RQ-V1/V3)

    python scripts/run_vlm_ablation.py

Every modality subset over the frames the VLM actually processed:

    FACE, VLM, AUDIO, TEXT and every combination of them.

**Leave-one-actor-out cross-validation.** The VLM subset is 80 clips from four held-out
actors, which is too small to carve a further train/test split from without leaving a
handful of clips per class. Rotating one actor out at a time uses every clip while keeping
each fold speaker-disjoint, and the fold count is reported beside every number so the
sample size is never in doubt.

The VLM representation is deliberately shallow: which observable regions the description
mentioned, how long it was, how much unsupported language it contained, and the model's
own mean token log-probability. A deeper text encoder would blur the question -- what is
tested is whether the *visual observations* carry signal, not whether a language model can
be trained on captions.
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

OUT = paths.REPO_ROOT / "outputs" / "vlm"
CACHE = paths.DATA / "affective" / "_cache"
SEED = 20260819


def vlm_features(desc: pd.DataFrame, backend: str) -> pd.DataFrame:
    """Structured features from the VLM descriptions of one backend."""
    g = desc[desc["model"] == backend].copy()
    if g.empty:
        return pd.DataFrame()
    region_cols = [c for c in g.columns if c.startswith("region_")]
    out = pd.DataFrame({"clip_key": g["segment_id"].to_numpy()})
    for c in region_cols:
        out["vlm_%s" % c] = g[c].astype(float).to_numpy()
    text = g["text"].astype(str)
    out["vlm_n_regions"] = g["n_regions_described"].astype(float).to_numpy()
    out["vlm_n_words"] = text.str.split().str.len().to_numpy()
    out["vlm_n_chars"] = text.str.len().to_numpy()
    out["vlm_ungrounded"] = g["n_ungrounded_terms"].astype(float).to_numpy()
    out["vlm_logprob"] = g["mean_token_logprob"].astype(float).to_numpy()

    # A small bag of the words a description of a face actually varies on. Fixed and
    # declared rather than fitted, so the feature set cannot quietly absorb the label.
    vocab = ("closed", "open", "smiling", "smile", "raised", "furrowed", "wide",
             "narrow", "tilted", "straight", "forward", "down", "up", "left", "right",
             "neutral", "slightly", "teeth", "looking", "away")
    low = text.str.lower()
    for w in vocab:
        out["vlm_w_%s" % w] = low.str.count(r"\b%s\b" % w).astype(float).to_numpy()
    return out


def assemble(desc: pd.DataFrame, backend: str) -> tuple[pd.DataFrame, dict]:
    """Join VLM, face, audio and text features on clip identity."""
    face = C.drop_duplicate_video(
        pd.read_parquet(CACHE / "ravdess_face_features.parquet"))
    audio = pd.read_parquet(CACHE / "ravdess_speech_features.parquet")
    face["clip_key"] = face["path"].map(fu.clip_key)
    audio["clip_key"] = audio["path"].map(fu.clip_key)

    v = vlm_features(desc, backend)
    if v.empty:
        raise SystemExit("no VLM descriptions for backend %r" % backend)

    keys = sorted(set(v["clip_key"]) & set(face["clip_key"]) & set(audio["clip_key"]))
    v = v[v["clip_key"].isin(keys)].drop_duplicates("clip_key").set_index("clip_key")
    f = face[face["clip_key"].isin(keys)].drop_duplicates(
        "clip_key").set_index("clip_key")
    a = audio[audio["clip_key"].isin(keys)].drop_duplicates("clip_key").set_index(
        "clip_key")
    v, f, a = v.loc[keys], f.loc[keys], a.loc[keys]

    exclude = {"emotion", "emotion_id", "intensity", "statement", "statement_id",
               "repetition", "actor", "actor_sex", "valence", "arousal", "modality",
               "split", "n_frames", "path", "clip_key"}

    def numeric(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
        cols = [c for c in frame.columns
                if c not in exclude and pd.api.types.is_numeric_dtype(frame[c])]
        sub = frame[cols].copy()
        sub.columns = ["%s_%s" % (prefix, c) for c in cols]
        return sub

    blocks = {
        "FACE": numeric(f, "face"),
        "VLM": v,
        "AUDIO": numeric(a, "aud"),
        # RAVDESS speaks two fixed sentences; the text channel is included because it
        # carries nothing, which is what makes it a useful control in this lattice.
        "TEXT": pd.get_dummies(a["statement_id"].astype(int),
                               prefix="txt").astype(float),
    }
    meta = pd.DataFrame({
        "emotion": f["emotion"].to_numpy(),
        "actor": f["actor"].to_numpy(),
    }, index=keys)
    return meta, blocks


def evaluate(meta: pd.DataFrame, blocks: dict, subset: tuple) -> dict:
    """Leave-one-actor-out accuracy for one modality subset."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score

    X = pd.concat([blocks[b] for b in subset], axis=1)
    X = X.loc[meta.index]
    Xv = np.nan_to_num(X.to_numpy(float), nan=0.0, posinf=0.0, neginf=0.0)
    y = meta["emotion"].to_numpy()
    actors = meta["actor"].to_numpy()

    preds = np.empty(len(y), dtype=object)
    for actor in np.unique(actors):
        test = actors == actor
        train = ~test
        if len(np.unique(y[train])) < 2 or test.sum() == 0:
            continue
        clf = RandomForestClassifier(n_estimators=300, random_state=SEED,
                                     min_samples_leaf=2, n_jobs=1)
        clf.fit(Xv[train], y[train])
        preds[test] = clf.predict(Xv[test])

    keep = preds != None  # noqa: E711 - object array, `is not None` is not elementwise
    if keep.sum() == 0:
        return {"subset": "+".join(subset), "status": "NO USABLE FOLD"}
    yt, yp = y[keep], preds[keep].astype(str)
    return {
        "subset": "+".join(subset),
        "status": "OK",
        "n": int(keep.sum()),
        "n_features": int(Xv.shape[1]),
        "n_folds": int(len(np.unique(actors))),
        "accuracy": float(accuracy_score(yt, yp)),
        "balanced_accuracy": float(balanced_accuracy_score(yt, yp)),
        "macro_f1": float(f1_score(yt, yp, average="macro", zero_division=0)),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backend", default="smolvlm-256m")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    desc_path = OUT / "vlm_descriptions.csv"
    if not desc_path.exists():
        raise SystemExit("run scripts/run_vlm_experiments.py --stage describe first")
    desc = pd.read_csv(desc_path)

    meta, blocks = assemble(desc, args.backend)
    chance = 1.0 / meta["emotion"].nunique()
    progress.log("[vlm ablation] %d clips, %d actors, %d classes (chance %.4f)"
                 % (len(meta), meta["actor"].nunique(), meta["emotion"].nunique(),
                    chance))
    for name, block in blocks.items():
        progress.log("      %-6s %d features" % (name, block.shape[1]))

    names = ["FACE", "VLM", "AUDIO", "TEXT"]
    rows = []
    for k in range(1, len(names) + 1):
        for subset in combinations(names, k):
            r = evaluate(meta, blocks, subset)
            rows.append(r)
            if r.get("status") == "OK":
                progress.log("      %-22s acc %.4f  balanced %.4f  macro-F1 %.4f  "
                             "(%d features)"
                             % (r["subset"], r["accuracy"], r["balanced_accuracy"],
                                r["macro_f1"], r["n_features"]))

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "vlm_ablation.csv", index=False)
    ok = table[table["status"] == "OK"]

    def bal(name: str) -> float:
        row = ok[ok["subset"] == name]
        return float(row["balanced_accuracy"].iloc[0]) if len(row) else float("nan")

    face_only, vlm_only, face_vlm = bal("FACE"), bal("VLM"), bal("FACE+VLM")
    full_no_vlm = bal("FACE+AUDIO+TEXT")
    full = bal("FACE+VLM+AUDIO+TEXT")

    vlm_adds_to_face = face_vlm - face_only
    vlm_adds_to_full = full - full_no_vlm
    verdict = ("VLM adds information beyond the specialised facial model"
               if vlm_adds_to_face > 0.02 else
               "VLM does not add information beyond the specialised facial model"
               if vlm_adds_to_face < -0.02 else
               "no difference beyond what this sample can resolve")

    progress.log("  VLM on top of FACE: %+.4f balanced accuracy" % vlm_adds_to_face)
    progress.log("  VLM on top of FACE+AUDIO+TEXT: %+.4f" % vlm_adds_to_full)
    progress.log("  verdict: %s" % verdict)

    report = {
        "backend": args.backend,
        "n_clips": int(len(meta)),
        "n_actors": int(meta["actor"].nunique()),
        "n_classes": int(meta["emotion"].nunique()),
        "chance": chance,
        "protocol": ("leave-one-actor-out cross-validation over the VLM-evaluated "
                     "subset; every fold is speaker-disjoint"),
        "block_sizes": {k: int(v.shape[1]) for k, v in blocks.items()},
        "ablation": rows,
        "face_only_balanced_accuracy": face_only,
        "vlm_only_balanced_accuracy": vlm_only,
        "face_plus_vlm_balanced_accuracy": face_vlm,
        "vlm_delta_over_face": vlm_adds_to_face,
        "vlm_delta_over_all_other_modalities": vlm_adds_to_full,
        "verdict": verdict,
        "limitations": (
            "The subset is %d clips from %d actors, so a difference smaller than a few "
            "points is not resolvable here. The VLM representation is a shallow record "
            "of which regions were described rather than a learned text encoder, which "
            "is the intended test: whether the visual observations carry signal, not "
            "whether a language model can be trained on captions."
            % (len(meta), meta["actor"].nunique())),
        "run_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "environment": environment_snapshot(),
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "vlm_ablation.json", report)
    progress.log("done in %.1fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
