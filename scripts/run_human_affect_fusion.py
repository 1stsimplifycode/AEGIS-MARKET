"""Multimodal fusion, ablation, disagreement, robustness, fairness and trajectories.

    python scripts/run_human_affect_fusion.py --all

Runs on the RAVDESS clips that have **both** audio and video, so the audiovisual fusion is
over the same utterance by the same actor recorded simultaneously — not two recordings
paired by label. Everything is speaker-disjoint and every number here comes from a model
scored on actors it never saw.

Stages:

``fusion``       every modality subset, late fusion over calibrated posteriors
``disagreement`` cross-modal divergence, and whether it predicts fused error
``robustness``   real corruption of the actual waveforms and pixels, re-run end to end
``fairness``     performance across actor sex, emotional intensity and statement
``trajectory``   timestamped affect over each clip rather than one label per clip
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import os
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
from research.human_affect import (  # noqa: E402
    MediaKind,  # noqa: E402
    ingest,
    models,
    speech,
)
from research.human_affect import corpora as C  # noqa: E402
from research.human_affect import face as face_mod  # noqa: E402
from research.human_affect import fusion as fu  # noqa: E402
from scripts.run_human_affect_experiments import _aggregate_face  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "human_affect" / "experiments"
CACHE = paths.DATA / "affective" / "_cache"
SEED = 20260819


def _feature_cols(frame: pd.DataFrame, extra_exclude: set[str] | None = None
                  ) -> list[str]:
    exclude = {"path", "emotion", "emotion_id", "intensity", "statement",
               "statement_id", "repetition", "actor", "actor_sex", "valence",
               "arousal", "modality", "split", "clip_key", "n_frames"}
    exclude |= (extra_exclude or set())
    return [c for c in frame.columns
            if c not in exclude and pd.api.types.is_numeric_dtype(frame[c])]


def load_aligned() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Audio and face feature frames restricted to clips present in both, split jointly.

    The split is computed once over the intersection's actors and applied to both frames,
    so the audio model and the face model are trained and tested on exactly the same
    actors. Splitting them independently would let an actor be in audio-train and
    face-test, and the fused evaluation would then be partly contaminated.
    """
    audio = pd.read_parquet(CACHE / "ravdess_speech_features.parquet")
    face = C.drop_duplicate_video(
        pd.read_parquet(CACHE / "ravdess_face_features.parquet"))
    audio["clip_key"] = audio["path"].map(fu.clip_key)
    face["clip_key"] = face["path"].map(fu.clip_key)

    shared = sorted(set(audio["clip_key"]) & set(face["clip_key"]))
    audio = audio[audio["clip_key"].isin(shared)].copy()
    face = face[face["clip_key"].isin(shared)].copy()

    split = C.speaker_disjoint_split(
        audio.drop(columns=["split"], errors="ignore"), seed=SEED)
    C.assert_speaker_disjoint(split)
    mapping = dict(zip(split["clip_key"], split["split"]))
    audio["split"] = audio["clip_key"].map(mapping)
    face["split"] = face["clip_key"].map(mapping)
    audio = audio.sort_values("clip_key").reset_index(drop=True)
    face = face.sort_values("clip_key").reset_index(drop=True)

    # Posteriors are combined positionally, so a row offset between the two frames would
    # fuse one actor's voice with another actor's face and still produce a plausible
    # number. Nothing downstream could detect that, so it is checked here.
    if list(audio["clip_key"]) != list(face["clip_key"]):
        raise SystemExit("audio and face frames are not row-aligned on clip_key")
    if not (audio["emotion"].to_numpy() == face["emotion"].to_numpy()).all():
        raise SystemExit("aligned clips disagree on the emotion label")
    return audio, face


def text_arm(audio: pd.DataFrame) -> pd.DataFrame:
    """The RAVDESS lexical channel as a real, and really uninformative, modality.

    RAVDESS speaks two fixed sentences, so this arm cannot carry emotion -- that is the
    point of including it. A fusion scheme that cannot absorb a null modality without
    losing accuracy is fragile in a way an audio-plus-video table would never reveal.
    The model is fit for real rather than stubbed with a uniform vector, so what the
    ablation measures is a genuine trained channel that happens to be at chance.
    """
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline

    return make_pipeline(
        TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1),
        CalibratedClassifierCV(
            LogisticRegression(max_iter=1000, random_state=SEED), cv=3))


def _posteriors(model, frame: pd.DataFrame, classes: list[str]) -> np.ndarray:
    """Posterior matrix in a fixed class order, so modalities can be combined."""
    proba = model.predict_proba(frame)
    index = {c: i for i, c in enumerate(model.classes)}
    return np.stack([proba[:, index[c]] if c in index else np.zeros(len(frame))
                     for c in classes], axis=1)


def _score(pred: np.ndarray, y: np.ndarray, proba: np.ndarray,
           classes: list[str]) -> dict:
    from sklearn.metrics import (
        accuracy_score,
        balanced_accuracy_score,
        cohen_kappa_score,
        f1_score,
    )
    return {
        "accuracy": float(accuracy_score(y, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "macro_f1": float(f1_score(y, pred, average="macro", zero_division=0)),
        "cohen_kappa": float(cohen_kappa_score(y, pred)),
        "calibration": models.calibration(proba, y, classes),
    }


# ----------------------------------------------------------------- fusion ----

def stage_fusion(audio: pd.DataFrame, face: pd.DataFrame) -> dict:
    """Every modality subset, scored on the same held-out actors."""
    a_cols = _feature_cols(audio, {"gate_passed"})
    f_cols = _feature_cols(face)

    a_tr, a_va, a_te = (audio[audio["split"] == s]
                        for s in ("train", "validation", "test"))
    f_tr, f_va, f_te = (face[face["split"] == s]
                        for s in ("train", "validation", "test"))
    progress.log("      aligned clips: %d (train %d / val %d / test %d), %d actors"
                 % (len(audio), len(a_tr), len(a_va), len(a_te),
                    audio["actor"].nunique()))

    audio_model = models.fit(a_tr, a_va, a_cols, seed=SEED)
    face_model = models.fit(f_tr, f_va, f_cols, seed=SEED)
    progress.log("      audio model %s | face model %s"
                 % (audio_model.config["selected_model"],
                    face_model.config["selected_model"]))

    classes = sorted(set(audio_model.classes) | set(face_model.classes))
    y_va = a_va["emotion"].to_numpy()
    y_te = a_te["emotion"].to_numpy()

    text_model = text_arm(audio)
    text_model.fit(a_tr["statement"].astype(str), a_tr["emotion"])
    t_index = {c: i for i, c in enumerate(text_model.classes_)}

    def text_post(frame: pd.DataFrame) -> np.ndarray:
        proba = text_model.predict_proba(frame["statement"].astype(str))
        return np.stack([proba[:, t_index[c]] if c in t_index
                         else np.zeros(len(frame)) for c in classes], axis=1)

    post_va = {"audio": _posteriors(audio_model, a_va, classes),
               "face": _posteriors(face_model, f_va, classes),
               "text": text_post(a_va)}
    post_te = {"audio": _posteriors(audio_model, a_te, classes),
               "face": _posteriors(face_model, f_te, classes),
               "text": text_post(a_te)}

    text_only_pred = np.array([classes[i] for i in post_te["text"].argmax(axis=1)])
    text_only = _score(text_only_pred, y_te, post_te["text"], classes)
    progress.log("      text arm (2 fixed sentences): balanced %.4f against chance %.4f"
                 % (text_only["balanced_accuracy"], 1.0 / len(classes)))

    weights = fu.fit_fusion_weights(post_va, y_va, classes)
    progress.log("      fusion weights from validation: %s"
                 % {k: round(v, 3) for k, v in weights.items()})

    # Every non-empty subset of the three modalities, so "fusion helps" is a measured
    # claim about this lattice rather than a comparison against one chosen baseline.
    subsets = {
        "audio_only": ["audio"],
        "face_only": ["face"],
        "text_only": ["text"],
        "audio_face": ["audio", "face"],
        "audio_text": ["audio", "text"],
        "face_text": ["face", "text"],
        "audio_face_text": ["audio", "face", "text"],
    }
    rows = []
    for name, mods in subsets.items():
        sub = {m: post_te[m] for m in mods}
        sub_w = {m: weights.get(m, 1.0) for m in mods}
        # Weights are fitted for the full ensemble, where a useless modality correctly
        # gets zero. Carried into a subset unchanged, an all-zero weighting turns the
        # geometric pool uniform and the arm scores the base rate of whichever class
        # sorts first -- which reads as "this modality is worthless" when what actually
        # happened is that it was switched off. Renormalise within the subset, and fall
        # back to equal weights when the subset has no weight left at all.
        total = sum(sub_w.values())
        if total <= 0:
            sub_w = dict.fromkeys(mods, 1.0)
        fused = fu.fuse(sub, sub_w)
        pred = np.array([classes[i] for i in fused.argmax(axis=1)])
        metrics = _score(pred, y_te, fused, classes)
        rows.append({"subset": name, "modalities": ",".join(mods), **{
            k: v for k, v in metrics.items() if k != "calibration"},
            "ece": metrics["calibration"]["ece"],
            "brier": metrics["calibration"]["brier_multiclass"]})
        progress.log("      %-12s accuracy %.4f  balanced %.4f  macro-F1 %.4f  ECE %.4f"
                     % (name, metrics["accuracy"], metrics["balanced_accuracy"],
                        metrics["macro_f1"], metrics["calibration"]["ece"]))

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "fusion_ablation.csv", index=False)

    best_uni = table[table["subset"].isin(
        ["audio_only", "face_only", "text_only"])]["balanced_accuracy"].max()
    fused_score = float(table[table["subset"] == "audio_face"]
                        ["balanced_accuracy"].iloc[0])
    delta = fused_score - float(best_uni)
    progress.log("      fusion minus best unimodal: %+.4f balanced accuracy" % delta)

    # Cross-modal disagreement on the same test clips.
    informative = {k: v for k, v in post_te.items() if k in ("audio", "face")}
    dis = fu.disagreement(informative, classes)
    fused = fu.fuse(post_te, weights)
    fused_pred = np.array([classes[i] for i in fused.argmax(axis=1)])
    dis_vs_acc = fu.disagreement_vs_accuracy(dis, fused_pred == y_te)
    dis.to_csv(OUT / "fusion_disagreement.csv", index=False)
    dis_vs_acc.to_csv(OUT / "fusion_disagreement_vs_accuracy.csv", index=False)
    progress.log("      modalities name the same emotion on %.1f%% of test clips"
                 % (100 * dis["argmax_agreement"].mean()))
    for _, r in dis_vs_acc.iterrows():
        if "accuracy" in r and pd.notna(r.get("accuracy")):
            progress.log("        JS %.3f-%.3f  n=%-4d fused accuracy %.4f"
                         % (r["js_low"], r["js_high"], r["n"], r["accuracy"]))

    # Per-clip fused predictions, used by the fairness and trajectory stages.
    preds = a_te[["clip_key", "actor", "actor_sex", "emotion", "intensity",
                  "statement_id"]].copy()
    preds["fused_pred"] = fused_pred
    preds["audio_pred"] = [classes[i] for i in post_te["audio"].argmax(axis=1)]
    preds["face_pred"] = [classes[i] for i in post_te["face"].argmax(axis=1)]
    preds["fused_confidence"] = fused.max(axis=1)
    preds["js_divergence"] = dis["mean_js_divergence"].to_numpy()
    preds["agreement"] = dis["argmax_agreement"].to_numpy()
    preds.to_csv(OUT / "fusion_test_predictions.csv", index=False)

    result = {
        "dataset": "RAVDESS audiovisual (audio and video of the same utterances)",
        "licence": C.licence_note(),
        "n_aligned_clips": int(len(audio)),
        "n_actors": int(audio["actor"].nunique()),
        "classes": classes,
        "fusion_method": "weighted geometric pooling of calibrated posteriors",
        "weights": weights,
        "ablation": rows,
        "text_arm": {
            **{k: v for k, v in text_only.items() if k != "calibration"},
            "n_distinct_sentences": int(audio["statement"].nunique()),
            "note": ("RAVDESS speaks two fixed sentences, so this channel cannot carry "
                     "emotion. It is included so the ablation shows what fusion does "
                     "with a modality that contributes nothing."),
        },
        "fusion_minus_best_unimodal_balanced_accuracy": float(delta),
        "agreement_rate": float(dis["argmax_agreement"].mean()),
        "disagreement_vs_accuracy": dis_vs_acc.to_dict(orient="records"),
        "audio_config": audio_model.config,
        "face_config": face_model.config,
    }
    jsonio.write(OUT / "fusion.json", result)
    return {"result": result, "audio_model": audio_model, "face_model": face_model,
            "classes": classes, "weights": weights,
            "post_te": post_te, "y_te": y_te,
            "a_te": a_te, "f_te": f_te, "preds": preds}


# ------------------------------------------------------------- robustness ----

def _corrupt_face_worker(task: tuple) -> dict:
    """Corrupt one clip's frames and re-extract facial features. Runs in a worker.

    The whole pipeline is re-run from the pixels, which is the expensive and the correct
    choice: perturbing the feature vector instead would be almost free and would answer a
    different question.
    """
    path, emotion, kind, severity, seed = task
    detector = getattr(_corrupt_face_worker, "_detector", None)
    if detector is None:
        try:
            import cv2
            cv2.setNumThreads(1)
        except Exception:
            pass
        detector = face_mod.get_detector()
        _corrupt_face_worker._detector = detector
    try:
        frames, times = ingest.sample_video_frames(path, fps=2.0, max_frames=10)
        corrupted = [fu.corrupt_frame(fr, kind, severity, seed=seed) for fr in frames]
        res = face_mod.analyse_frames(corrupted, times, MediaKind.HUMAN_VIDEO,
                                      detector=detector)
        feats = _aggregate_face(res.frames)
        feats["_emotion"] = emotion
        return feats
    except Exception as exc:  # noqa: BLE001
        return {"_emotion": emotion, "_error": "%s: %s" % (type(exc).__name__, exc)}


def stage_robustness(ctx: dict, audio: pd.DataFrame, face: pd.DataFrame,
                     n_clips: int = 60) -> dict:
    """Corrupt the real signals, re-extract features, re-run inference, measure the drop.

    Feature-space noise would be cheaper and would not answer the question. The pipeline
    is re-run from the waveform and the pixels, so the number reflects what a genuinely
    degraded recording would do.
    """
    audio_model, face_model = ctx["audio_model"], ctx["face_model"]
    a_te, f_te = ctx["a_te"], ctx["f_te"]
    rng = np.random.default_rng(SEED)

    sample_keys = list(a_te["clip_key"])
    if len(sample_keys) > n_clips:
        sample_keys = list(rng.choice(sample_keys, n_clips, replace=False))
    a_sub = a_te[a_te["clip_key"].isin(sample_keys)]
    f_sub = f_te[f_te["clip_key"].isin(sample_keys)]
    progress.log("      corrupting %d test clips per condition" % len(a_sub))

    from sklearn.metrics import balanced_accuracy_score
    a_cols = audio_model.feature_names
    f_cols = face_model.feature_names

    rows = []
    base_audio = balanced_accuracy_score(a_sub["emotion"],
                                         audio_model.predict(a_sub))
    base_face = balanced_accuracy_score(f_sub["emotion"], face_model.predict(f_sub))
    rows.append({"modality": "audio", "corruption": "none", "severity": 0.0,
                 "balanced_accuracy": float(base_audio), "degradation": 0.0,
                 "n": int(len(a_sub))})
    rows.append({"modality": "face", "corruption": "none", "severity": 0.0,
                 "balanced_accuracy": float(base_face), "degradation": 0.0,
                 "n": int(len(f_sub))})

    for kind in ("gaussian_noise", "dropout", "clipping", "lowpass"):
        for severity in (0.1, 0.25, 0.5):
            feats = []
            for rec in a_sub.itertuples(index=False):
                x, sr = ingest.load_audio(rec.path)
                y = fu.corrupt_audio(x, sr, kind, severity, seed=SEED)
                feats.append(speech.utterance_features(y, sr))
            frame = pd.DataFrame(feats)
            for c in a_cols:
                if c not in frame.columns:
                    frame[c] = np.nan
            score = balanced_accuracy_score(a_sub["emotion"],
                                            audio_model.predict(frame))
            rows.append({"modality": "audio", "corruption": kind,
                         "severity": severity, "balanced_accuracy": float(score),
                         "degradation": float(base_audio - score),
                         "n": int(len(a_sub))})
            progress.log("        audio %-16s sev %.2f  balanced %.4f  (%+.4f)"
                         % (kind, severity, score, score - base_audio))

    if face_mod.get_detector() is not None:
        conditions = [(kind, sev) for kind in ("blur", "darkness", "occlusion", "noise")
                      for sev in (0.1, 0.25, 0.5)]
        # Every (clip, condition) is independent, and each one re-decodes a 720p video and
        # runs a CNN detector over ten frames. Serially this is hours; fanned out it is
        # minutes.
        tasks = [(rec.path, rec.emotion, kind, sev, SEED)
                 for kind, sev in conditions
                 for rec in f_sub.itertuples(index=False)]
        workers = max(1, min(8, (os.cpu_count() or 2) - 1))
        progress.log("      %d face corruption runs across %d worker processes"
                     % (len(tasks), workers))
        with cf.ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_corrupt_face_worker, tasks, chunksize=4))

        per_clip = len(f_sub)
        for i, (kind, severity) in enumerate(conditions):
            chunk = results[i * per_clip:(i + 1) * per_clip]
            good = [r for r in chunk if "_error" not in r]
            if not good:
                progress.log("        face  %-16s sev %.2f  ALL FAILED"
                             % (kind, severity))
                continue
            kept = [r.pop("_emotion") for r in good]
            frame = pd.DataFrame(good)
            for c in f_cols:
                if c not in frame.columns:
                    frame[c] = np.nan
            score = balanced_accuracy_score(kept, face_model.predict(frame))
            detection = float(frame["face_detection_rate"].mean())
            rows.append({"modality": "face", "corruption": kind,
                         "severity": severity, "balanced_accuracy": float(score),
                         "degradation": float(base_face - score),
                         "face_detection_rate": detection, "n": int(len(good))})
            progress.log("        face  %-16s sev %.2f  balanced %.4f  (%+.4f)  "
                         "detection %.3f"
                         % (kind, severity, score, score - base_face, detection))

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "robustness.csv", index=False)
    result = {"rows": rows, "baseline_audio": float(base_audio),
              "baseline_face": float(base_face),
              "note": ("Corruption is applied to the waveform and the pixels and the "
                       "whole feature pipeline is re-run, so these are degradations of "
                       "the real signal rather than of a feature vector."),
              "adversarial": ("NOT RUN. These are random corruptions. Nothing here "
                              "licenses a claim about adversarial robustness, which is "
                              "a different property requiring an attacker model.")}
    jsonio.write(OUT / "robustness.json", result)
    return result


# ---------------------------------------------------------------- fairness ----

def stage_fairness(ctx: dict) -> dict:
    """Performance across the legitimate metadata RAVDESS actually provides.

    Actor sex, emotional intensity and spoken statement are recorded in the corpus. No
    demographic attribute is invented: RAVDESS publishes actor sex and nothing else about
    the people, so that is the only person-level grouping used.
    """
    from sklearn.metrics import accuracy_score, balanced_accuracy_score

    preds = ctx["preds"]
    rows = []
    for group_col in ("actor_sex", "intensity", "statement_id"):
        for value, g in preds.groupby(group_col):
            if len(g) < 20:
                rows.append({"group": group_col, "value": str(value), "n": int(len(g)),
                             "status": "INSUFFICIENT DATA"})
                continue
            acc = float(accuracy_score(g["emotion"], g["fused_pred"]))
            bal = float(balanced_accuracy_score(g["emotion"], g["fused_pred"]))
            # Wilson interval on accuracy: the sample is small and a bare point estimate
            # would invite a comparison the data cannot support.
            n = len(g)
            z = 1.96
            denom = 1 + z ** 2 / n
            centre = (acc + z ** 2 / (2 * n)) / denom
            half = z * np.sqrt(acc * (1 - acc) / n + z ** 2 / (4 * n ** 2)) / denom
            rows.append({"group": group_col, "value": str(value), "n": int(n),
                         "accuracy": acc, "balanced_accuracy": bal,
                         "ci_low": float(centre - half), "ci_high": float(centre + half),
                         "mean_confidence": float(g["fused_confidence"].mean()),
                         "agreement_rate": float(g["agreement"].mean()),
                         "status": "OK"})

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "fairness.csv", index=False)

    gaps = []
    for group_col in ("actor_sex", "intensity", "statement_id"):
        sel = table[(table["group"] == group_col) & (table["status"] == "OK")]
        if len(sel) < 2:
            continue
        hi = sel.loc[sel["accuracy"].idxmax()]
        lo = sel.loc[sel["accuracy"].idxmin()]
        overlap = not (lo["ci_high"] < hi["ci_low"])
        gaps.append({
            "group": group_col, "best": str(hi["value"]), "worst": str(lo["value"]),
            "gap": float(hi["accuracy"] - lo["accuracy"]),
            "confidence_intervals_overlap": bool(overlap),
            "reading": ("the intervals overlap, so this sample does not establish a "
                        "difference" if overlap else
                        "the intervals do not overlap, so a difference is supported at "
                        "this sample size"),
        })
        progress.log("      %-12s best %-8s worst %-8s gap %+.4f  %s"
                     % (group_col, hi["value"], lo["value"],
                        hi["accuracy"] - lo["accuracy"],
                        "CIs overlap" if overlap else "CIs disjoint"))

    result = {"rows": rows, "gaps": gaps,
              "note": ("Groups are the metadata RAVDESS publishes: actor sex, emotional "
                       "intensity and spoken statement. No demographic attribute is "
                       "invented, and a gap whose confidence intervals overlap is "
                       "reported as unestablished rather than as unfairness.")}
    jsonio.write(OUT / "fairness.json", result)
    return result


# -------------------------------------------------------------- trajectory ----

def stage_trajectory(ctx: dict, n_clips: int = 12) -> dict:
    """Timestamped affect over each clip, rather than one label per recording.

    The requirement that a recording is not collapsed to a single number. Audio is scored
    in overlapping windows and video frame by frame, and both are written on a common
    time axis so a reader can see when the signal moved.
    """
    a_te, f_te = ctx["a_te"], ctx["f_te"]
    audio_model = ctx["audio_model"]
    detector = face_mod.get_detector()
    keys = list(a_te["clip_key"])[:n_clips]

    rows = []
    for key in keys:
        arec = a_te[a_te["clip_key"] == key].iloc[0]
        frec = f_te[f_te["clip_key"] == key]
        x, sr = ingest.load_audio(arec.path)
        window, hop = 1.0, 0.5
        n = max(1, int((len(x) / sr - window) / hop) + 1)
        for i in range(n):
            start = i * hop
            seg = x[int(start * sr):int((start + window) * sr)]
            if len(seg) < sr // 2:
                continue
            feats = pd.DataFrame([speech.utterance_features(seg, sr)])
            for c in audio_model.feature_names:
                if c not in feats.columns:
                    feats[c] = np.nan
            dims = audio_model.predict_dimensional(feats)
            unc = audio_model.uncertainty(feats)
            rows.append({"clip_key": key, "true_emotion": arec.emotion,
                         "modality": "audio", "t_start_s": float(start),
                         "t_end_s": float(start + window),
                         "valence": float(dims["valence"][0]),
                         "arousal": float(dims["arousal"][0]),
                         "predicted": audio_model.predict(feats)[0],
                         "entropy": float(unc["entropy"][0])})

        if not frec.empty:
            frames, times = ingest.sample_video_frames(frec.iloc[0].path, fps=4.0,
                                                       max_frames=32)
            res = face_mod.analyse_frames(frames, times, MediaKind.HUMAN_VIDEO,
                                          detector=detector)
            for f in res.frames:
                if f.status != "OK":
                    continue
                rows.append({"clip_key": key, "true_emotion": arec.emotion,
                             "modality": "face", "t_start_s": float(f.timestamp_s),
                             "t_end_s": float(f.timestamp_s + 0.25),
                             "mouth_width_ratio":
                                 f.features.get("mouth_width_ratio"),
                             "mouth_openness_ratio":
                                 f.features.get("mouth_openness_ratio"),
                             "quality": f.quality.get("score")})

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "affect_trajectories.csv", index=False)
    progress.log("      %d timestamped rows across %d clips" % (len(table), len(keys)))
    return {"n_rows": int(len(table)), "n_clips": len(keys),
            "path": str(OUT / "affect_trajectories.csv")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--stage", action="append",
                    choices=["fusion", "robustness", "fairness", "trajectory"])
    args = ap.parse_args()
    stages = (["fusion", "robustness", "fairness", "trajectory"] if args.all
              else (args.stage or ["fusion"]))

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    progress.log("[align] audio and video for the same utterances")
    audio, face = load_aligned()

    progress.log("[fusion] modality ablation and disagreement")
    ctx = stage_fusion(audio, face)
    summary = {"fusion": ctx["result"]}

    if "robustness" in stages:
        progress.log("[robustness] corrupting real signals")
        summary["robustness"] = stage_robustness(ctx, audio, face)
    if "fairness" in stages:
        progress.log("[fairness] subgroup performance with confidence intervals")
        summary["fairness"] = stage_fairness(ctx)
    if "trajectory" in stages:
        progress.log("[trajectory] timestamped affect")
        summary["trajectory"] = stage_trajectory(ctx)

    summary.update({"run_at": datetime.now(UTC).isoformat(), "seed": SEED,
                    "git_commit": git_commit(),
                    "environment": environment_snapshot(),
                    "elapsed_s": round(time.time() - t0, 1)})
    jsonio.write(OUT / "fusion_run.json", summary)
    progress.log("done in %.0fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
