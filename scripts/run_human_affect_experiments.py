"""Execute the Stream B human-affect experiments on RAVDESS.

    python scripts/run_human_affect_experiments.py --stage features
    python scripts/run_human_affect_experiments.py --stage speech
    python scripts/run_human_affect_experiments.py --all

Real human speech, real labels, speaker-disjoint splits, results written to
``outputs/human_affect/experiments/``. Nothing under ``research_artifacts/`` is touched.

Feature extraction is cached to parquet because it is the expensive step; every later
stage reads the cache, so the modelling work iterates in seconds.
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
    guards,
    ingest,
    models,
    speech,
)
from research.human_affect import corpora as C  # noqa: E402
from research.human_affect import face as face_mod  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "human_affect" / "experiments"
CACHE = paths.DATA / "affective" / "_cache"
SEED = 20260819

#: Feature families, used for group permutation importance. Shuffling the thirteen MFCC
#: means independently would break their correlation structure and overstate them.
FEATURE_GROUPS = {
    "prosody_f0": ["f0_median_hz", "f0_iqr_hz", "f0_range_hz", "f0_slope_hz_per_s"],
    "prosody_energy": ["energy_mean", "energy_std", "energy_dynamic_range_db"],
    "prosody_timing": ["duration_s", "voiced_fraction", "speech_rate_syllables_per_s",
                       "pause_count", "pause_fraction", "mean_pause_s",
                       "longest_pause_s"],
    "voice_quality": ["jitter_local", "shimmer_local", "hnr_db"],
    "spectral": ["spectral_centroid_hz", "spectral_bandwidth_hz",
                 "spectral_rolloff95_hz", "spectral_flux_mean", "zcr_mean"],
    "mfcc": ["mfcc%d_%s" % (i, s) for i in range(13) for s in ("mean", "std")],
    "mfcc_delta": ["dmfcc%d_%s" % (i, s) for i in range(13) for s in ("mean", "std")],
}


def feature_columns(frame: pd.DataFrame) -> list[str]:
    exclude = {"path", "emotion", "emotion_id", "intensity", "statement",
               "statement_id", "repetition", "actor", "actor_sex", "valence",
               "arousal", "modality", "split"}
    return [c for c in frame.columns
            if c not in exclude and pd.api.types.is_numeric_dtype(frame[c])]


# ------------------------------------------------------------------- features ----

def stage_features(force: bool = False) -> pd.DataFrame:
    """Extract utterance features for every RAVDESS speech clip, cached."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / "ravdess_speech_features.parquet"
    if cache_path.exists() and not force:
        frame = pd.read_parquet(cache_path)
        # The split is recomputed rather than read from the cache: features are expensive
        # and stable, split policy is cheap and has changed once already. Trusting a
        # cached split is how a stale partition survives a policy fix unnoticed.
        frame = C.speaker_disjoint_split(frame.drop(columns=["split"], errors="ignore"),
                                         seed=SEED)
        C.assert_speaker_disjoint(frame)
        progress.log("      cached features: %d clips x %d columns (split recomputed)"
                     % (len(frame), frame.shape[1]))
        return frame

    index = C.load_index(C.RAVDESS_ROOT / "audio_speech")
    if index.empty:
        raise SystemExit("no RAVDESS audio found; run scripts/fetch_affective_data.py "
                         "--dataset RAVDESS_SPEECH_AUDIO")
    index = C.speaker_disjoint_split(index, seed=SEED)
    C.assert_speaker_disjoint(index)

    rows, failures, t0 = [], [], time.time()
    for i, rec in enumerate(index.itertuples(index=False)):
        try:
            x, sr = ingest.load_audio(rec.path)
            # The gate runs on real data, not only on fixtures: this asserts that RAVDESS
            # speech is accepted as speech, which is the positive control for a guard
            # whose negative controls are all sonification.
            gate = guards.looks_like_speech(*speech.resample_to(x, sr))
            feats = speech.utterance_features(x, sr)
            feats.update({"path": rec.path, "gate_passed": bool(gate.passed)})
            rows.append(feats)
        except Exception as exc:
            failures.append({"path": rec.path, "error": "%s: %s"
                             % (type(exc).__name__, exc)})
        if i and i % 200 == 0:
            rate = (i + 1) / (time.time() - t0)
            progress.log("      %d/%d clips  %.1f/s  eta %.0fs"
                         % (i, len(index), rate, (len(index) - i) / rate))

    features = pd.DataFrame(rows)
    frame = index.merge(features, on="path", how="inner")
    frame.to_parquet(cache_path, index=False)
    progress.log("      extracted %d clips in %.0fs (%d failures)"
                 % (len(frame), time.time() - t0, len(failures)))
    if failures:
        jsonio.write(OUT / "feature_failures.json", failures)
    return frame


# --------------------------------------------------------------------- speech ----

def stage_speech(frame: pd.DataFrame) -> dict:
    """Train and evaluate the speech-emotion model, speaker-independent."""
    OUT.mkdir(parents=True, exist_ok=True)
    cols = feature_columns(frame)
    train = frame[frame["split"] == "train"]
    val = frame[frame["split"] == "validation"]
    test = frame[frame["split"] == "test"]

    progress.log("      train %d / validation %d / test %d clips  (%d features)"
                 % (len(train), len(val), len(test), len(cols)))

    model = models.fit(train, val, cols, seed=SEED)
    progress.log("      selected %s (validation balanced accuracy %.4f)"
                 % (model.config["selected_model"],
                    model.config["validation_balanced_accuracy"]))
    for row in model.config["sweep"]:
        progress.log("        %-24s %.4f"
                     % (row["model"], row["validation_balanced_accuracy"]))

    result = {
        "dataset": "RAVDESS speech (audio)",
        "licence": C.licence_note(),
        "protocol": ("speaker-disjoint split; model family chosen on the validation "
                     "actors; the test actors are scored once"),
        "config": model.config,
        "validation": models.evaluate(model, val),
        "test": models.evaluate(model, test),
        "majority_baseline_test": models.majority_baseline(train, test),
        "feature_columns": cols,
    }

    test_metrics = result["test"]
    progress.log("      TEST  accuracy %.4f  balanced %.4f  macro-F1 %.4f  kappa %.4f"
                 % (test_metrics["accuracy"], test_metrics["balanced_accuracy"],
                    test_metrics["macro_f1"], test_metrics["cohen_kappa"]))
    progress.log("      TEST  chance %.4f, majority baseline balanced %.4f"
                 % (test_metrics["chance_accuracy"],
                    result["majority_baseline_test"]["balanced_accuracy"]))
    progress.log("      TEST  valence MAE %.4f R2 %.4f | arousal MAE %.4f R2 %.4f"
                 % (test_metrics["valence_mae"], test_metrics["valence_r2"],
                    test_metrics["arousal_mae"], test_metrics["arousal_r2"]))
    progress.log("      TEST  ECE %.4f  Brier %.4f"
                 % (test_metrics["calibration"]["ece"],
                    test_metrics["calibration"]["brier_multiclass"]))

    imp = models.permutation_importance(model, test, groups=FEATURE_GROUPS, seed=SEED)
    result["permutation_importance"] = imp
    progress.log("      feature-group importance on test:")
    for row in imp["groups"]:
        progress.log("        %-16s %+.4f" % (row["group"], row["importance"]))

    # Positive control for the speech gate: RAVDESS is real speech and must pass.
    if "gate_passed" in frame.columns:
        rate = float(frame["gate_passed"].mean())
        result["speech_gate_pass_rate_on_real_speech"] = rate
        progress.log("      speech content gate accepts %.1f%% of real RAVDESS clips"
                     % (100 * rate))

    jsonio.write(OUT / "speech_emotion.json", result)
    pd.DataFrame(test_metrics["per_class"]).to_csv(OUT / "speech_per_class.csv",
                                                   index=False)
    pd.DataFrame(test_metrics["confusion_matrix"], index=test_metrics["classes"],
                 columns=test_metrics["classes"]).to_csv(OUT / "speech_confusion.csv")
    pd.DataFrame(imp["groups"]).to_csv(OUT / "speech_group_importance.csv", index=False)
    pd.DataFrame(test_metrics["calibration"]["bins"]).to_csv(
        OUT / "speech_calibration.csv", index=False)

    # Per-clip predictions, which every later stage (fairness, robustness, fusion) reads.
    preds = test[["path", "actor", "actor_sex", "emotion", "intensity", "statement_id",
                  "valence", "arousal"]].copy()
    proba = model.predict_proba(test)
    preds["predicted"] = model.predict(test)
    dims = model.predict_dimensional(test)
    preds["valence_pred"] = dims["valence"]
    preds["arousal_pred"] = dims["arousal"]
    unc = model.uncertainty(test)
    for k, v in unc.items():
        preds[k] = v
    for i, c in enumerate(model.classes):
        preds["p_%s" % c] = proba[:, i]
    preds.to_csv(OUT / "speech_test_predictions.csv", index=False)
    return result


# ----------------------------------------------------------------------- face ----


def _aggregate_face(frames: list) -> dict[str, float]:
    """Per-clip summary of the per-frame expression geometry.

    Four statistics per feature rather than a mean: an expression is a trajectory, and
    the standard deviation, range and frame-to-frame volatility are where the dynamics
    live. A mean alone discards exactly what separates a held expression from a changing
    one.
    """
    out: dict[str, float] = {}
    ok = [f for f in frames if f.status == "OK"]
    out["face_detection_rate"] = float(len(ok) / max(1, len(frames)))
    out["n_frames"] = float(len(frames))
    if not ok:
        return out
    for name in face_mod.FACE_FEATURE_NAMES:
        series = np.array([f.features.get(name, np.nan) for f in ok], dtype=float)
        finite = series[np.isfinite(series)]
        if finite.size == 0:
            continue
        out["%s_mean" % name] = float(finite.mean())
        out["%s_std" % name] = float(finite.std())
        out["%s_range" % name] = float(finite.max() - finite.min())
        out["%s_volatility" % name] = (float(np.mean(np.abs(np.diff(finite))))
                                       if finite.size > 1 else 0.0)
    quality = np.array([f.quality.get("score", np.nan) for f in ok], dtype=float)
    out["frame_quality_mean"] = float(np.nanmean(quality))
    return out


def _face_worker(path: str) -> dict | None:
    """Extract one clip's facial features. Runs in a worker process.

    Top-level and self-contained because Windows spawns rather than forks, so the worker
    re-imports this module; the detector is built once per process and cached on the
    function, since constructing YuNet per clip would cost more than the detection.
    """
    detector = getattr(_face_worker, "_detector", None)
    if detector is None:
        # One thread per worker: seven processes each spawning eight OpenCV threads on an
        # eight-core machine is fifty-six threads contending, which is slower than one
        # each, not faster.
        try:
            import cv2
            cv2.setNumThreads(1)
        except Exception:
            pass
        detector = face_mod.get_detector()
        _face_worker._detector = detector
    try:
        frames, times = ingest.sample_video_frames(path, fps=4.0, max_frames=32)
        result = face_mod.analyse_frames(frames, times, MediaKind.HUMAN_VIDEO,
                                         detector=detector)
        feats = _aggregate_face(result.frames)
        feats["path"] = path
        return feats
    except Exception as exc:  # noqa: BLE001 - one bad clip must not kill the sweep
        return {"path": path, "_error": "%s: %s" % (type(exc).__name__, exc)}


def stage_face_features(force: bool = False) -> pd.DataFrame:
    """Extract facial expression features for every available RAVDESS video clip."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / "ravdess_face_features.parquet"
    if cache_path.exists() and not force:
        frame = C.drop_duplicate_video(pd.read_parquet(cache_path))
        frame = C.speaker_disjoint_split(frame.drop(columns=["split"], errors="ignore"),
                                         seed=SEED)
        C.assert_speaker_disjoint(frame)
        progress.log("      cached face features: %d clips x %d columns "
                     "(split recomputed)" % (len(frame), frame.shape[1]))
        return frame

    index = C.load_index(C.RAVDESS_ROOT / "video_speech", pattern="*.mp4")
    if index.empty:
        raise SystemExit("no RAVDESS video found; run scripts/fetch_affective_data.py "
                         "--dataset RAVDESS_SPEECH_VIDEO")
    index = C.speaker_disjoint_split(index, seed=SEED)

    progress.log("      detector backends: %s"
                 % (face_mod.available_backends() or "NONE"))
    paths_todo = list(index["path"])
    workers = max(1, min(8, (os.cpu_count() or 2) - 1))
    progress.log("      %d clips across %d worker processes"
                 % (len(paths_todo), workers))
    rows, failures, t0 = [], [], time.time()
    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        for i, feats in enumerate(pool.map(_face_worker, paths_todo, chunksize=4), 1):
            if feats is None:
                continue
            if "_error" in feats:
                failures.append(feats)
                continue
            rows.append(feats)
            if i % 120 == 0:
                rate = i / (time.time() - t0)
                progress.log("      %d/%d clips  %.1f/s  eta %.0fs"
                             % (i, len(paths_todo), rate,
                                (len(paths_todo) - i) / rate))
    for f in failures[:10]:
        progress.log("      FAILED %s: %s"
                     % (Path(f["path"]).name, f["_error"]))
    if failures:
        progress.log("      %d clips failed extraction" % len(failures))

    features = pd.DataFrame(rows)
    frame = index.merge(features, on="path", how="inner")
    frame.to_parquet(cache_path, index=False)
    progress.log("      extracted %d clips in %.0fs; mean detection rate %.3f"
                 % (len(frame), time.time() - t0,
                    float(frame["face_detection_rate"].mean())))
    return frame


def stage_face(frame: pd.DataFrame) -> dict:
    """Train and evaluate the facial-expression emotion model, speaker-independent."""
    OUT.mkdir(parents=True, exist_ok=True)
    cols = [c for c in feature_columns(frame) if c != "n_frames"]
    train = frame[frame["split"] == "train"]
    val = frame[frame["split"] == "validation"]
    test = frame[frame["split"] == "test"]
    progress.log("      train %d / validation %d / test %d clips  (%d features)"
                 % (len(train), len(val), len(test), len(cols)))
    if min(len(train), len(val), len(test)) < 20:
        return {"status": "INSUFFICIENT DATA",
                "detail": "a split has under 20 clips; download more RAVDESS actors",
                "n_train": int(len(train)), "n_val": int(len(val)),
                "n_test": int(len(test))}

    model = models.fit(train, val, cols, seed=SEED)
    progress.log("      selected %s (validation balanced accuracy %.4f)"
                 % (model.config["selected_model"],
                    model.config["validation_balanced_accuracy"]))

    result = {
        "dataset": "RAVDESS speech (video, facial expression)",
        "licence": C.licence_note(),
        "detector": "opencv_yunet (MIT) with 5-landmark expression geometry",
        "config": model.config,
        "validation": models.evaluate(model, val),
        "test": models.evaluate(model, test),
        "majority_baseline_test": models.majority_baseline(train, test),
        "mean_face_detection_rate": float(frame["face_detection_rate"].mean()),
        "feature_columns": cols,
    }
    t = result["test"]
    progress.log("      TEST  accuracy %.4f  balanced %.4f  macro-F1 %.4f  kappa %.4f"
                 % (t["accuracy"], t["balanced_accuracy"], t["macro_f1"],
                    t["cohen_kappa"]))
    progress.log("      TEST  valence R2 %.4f | arousal R2 %.4f | ECE %.4f"
                 % (t["valence_r2"], t["arousal_r2"], t["calibration"]["ece"]))

    imp = models.permutation_importance(model, test, seed=SEED)
    result["permutation_importance"] = imp
    progress.log("      top facial features on test:")
    for row in imp["features"][:6]:
        progress.log("        %-36s %+.4f" % (row["feature"], row["importance"]))

    jsonio.write(OUT / "face_emotion.json", result)
    pd.DataFrame(t["confusion_matrix"], index=t["classes"],
                 columns=t["classes"]).to_csv(OUT / "face_confusion.csv")
    pd.DataFrame(t["per_class"]).to_csv(OUT / "face_per_class.csv", index=False)
    pd.DataFrame(imp["features"]).to_csv(OUT / "face_importance.csv", index=False)

    preds = test[["path", "actor", "actor_sex", "emotion", "intensity", "statement_id",
                  "valence", "arousal"]].copy()
    preds["predicted"] = model.predict(test)
    dims = model.predict_dimensional(test)
    preds["valence_pred"], preds["arousal_pred"] = dims["valence"], dims["arousal"]
    for k, v in model.uncertainty(test).items():
        preds[k] = v
    proba = model.predict_proba(test)
    for i, c in enumerate(model.classes):
        preds["p_%s" % c] = proba[:, i]
    preds.to_csv(OUT / "face_test_predictions.csv", index=False)
    return result


# ----------------------------------------------------------------------- text ----

def stage_text() -> dict:
    """Train and evaluate linguistic affect on GoEmotions, with label quality."""
    from research.human_affect import text_affect as T

    OUT.mkdir(parents=True, exist_ok=True)
    long = T.load_goemotions()
    agg = T.aggregate_with_agreement(long)
    frame = T.split_by_hash(agg, seed=SEED)
    train = frame[frame["split"] == "train"]
    val = frame[frame["split"] == "validation"]
    test = frame[frame["split"] == "test"]
    progress.log("      %d examples from %d rater rows; train %d / val %d / test %d"
                 % (len(frame), len(long), len(train), len(val), len(test)))

    model, val_score = T.fit_text_model(train, val, seed=SEED)
    progress.log("      validation balanced accuracy %.4f" % val_score)

    test_metrics = T.evaluate_text(model, test)
    progress.log("      TEST  accuracy %.4f  balanced %.4f  macro-F1 %.4f  (chance %.4f)"
                 % (test_metrics["accuracy"], test_metrics["balanced_accuracy"],
                    test_metrics["macro_f1"], test_metrics["chance_accuracy"]))
    progress.log("      TEST  ECE %.4f  Brier %.4f"
                 % (test_metrics["calibration"]["ece"],
                    test_metrics["calibration"]["brier_multiclass"]))

    quality = T.label_quality(model, test)
    progress.log("      label quality (accuracy by annotator agreement):")
    for band in quality["bands"]:
        if band.get("status") == "OK":
            progress.log("        %-16s n=%-6d agreement %.2f  accuracy %.4f"
                         % (band["band"], band["n"], band["mean_agreement"],
                            band["accuracy"]))
    progress.log("      accuracy spread across agreement bands: %.4f"
                 % quality["accuracy_spread_across_agreement_bands"])

    # Token attributions on a handful of test examples, one per predicted class.
    examples = []
    for cls in test_metrics["classes"]:
        sel = test[test["label"] == cls].head(1)
        if sel.empty:
            continue
        text = sel["text"].iloc[0]
        examples.append({"label": cls, "text": text[:200],
                         "attributions": T.token_attributions(model, text)})

    # How much information the RAVDESS lexical channel can carry: measured, not assumed.
    speech_index = C.load_index(C.RAVDESS_ROOT / "audio_speech")
    ravdess_text = T.ravdess_text_information(speech_index)
    progress.log("      RAVDESS text channel: best possible balanced accuracy %.4f "
                 "against chance %.4f"
                 % (ravdess_text["best_possible_text_only_balanced_accuracy"],
                    ravdess_text["chance"]))

    result = {
        "dataset": "GoEmotions (Apache-2.0), Ekman grouping",
        "n_examples": int(len(frame)),
        "n_rater_rows": int(len(long)),
        "mean_agreement": float(agg["agreement"].mean()),
        "unanimous_fraction": float(agg["unanimous"].mean()),
        "validation_balanced_accuracy": val_score,
        "test": test_metrics,
        "label_quality": quality,
        "token_attribution_examples": examples,
        "ravdess_text_channel": ravdess_text,
    }
    jsonio.write(OUT / "text_affect.json", result)
    pd.DataFrame(test_metrics["confusion_matrix"], index=test_metrics["classes"],
                 columns=test_metrics["classes"]).to_csv(OUT / "text_confusion.csv")
    pd.DataFrame(quality["bands"]).to_csv(OUT / "text_label_quality.csv", index=False)
    pd.DataFrame(test_metrics["calibration"]["bins"]).to_csv(
        OUT / "text_calibration.csv", index=False)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", choices=["features", "speech", "text", "face"],
                action="append")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--force-features", action="store_true",
                    help="re-extract the speech feature cache")
    ap.add_argument("--force-face-features", action="store_true",
                    help="re-extract only the face feature cache; the speech cache is "
                         "the cheap one and rarely needs redoing alongside it")
    args = ap.parse_args()
    stages = (["features", "speech", "text", "face"] if args.all
              else (args.stage or ["features"]))

    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    summary: dict = {"stages": stages, "seed": SEED}

    progress.log("[features] RAVDESS speech feature extraction")
    frame = stage_features(force=args.force_features)
    summary["n_clips"] = int(len(frame))
    summary["split_summary"] = C.split_summary(frame).to_dict(orient="records")

    if "speech" in stages:
        progress.log("[speech] speaker-independent emotion model")
        summary["speech"] = stage_speech(frame)

    if "text" in stages:
        progress.log("[text] linguistic affect on GoEmotions")
        summary["text"] = stage_text()

    if "face" in stages:
        progress.log("[face] facial expression from real human video")
        face_frame = stage_face_features(
            force=args.force_features or args.force_face_features)
        summary["face"] = stage_face(face_frame)

    summary.update({
        "run_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "environment": environment_snapshot(),
        "elapsed_s": round(time.time() - t0, 1),
        "media_kind": str(MediaKind.HUMAN_SPEECH),
        "note": "Real human speech from RAVDESS. No market-derived signal is present in "
                "any of these experiments.",
    })
    jsonio.write(OUT / "run.json", summary)
    progress.log("done in %.0fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


