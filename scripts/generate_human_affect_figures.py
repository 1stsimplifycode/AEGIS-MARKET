"""Generate the Stream B paper figures from the executed experiments.

    python scripts/generate_human_affect_figures.py

Every figure is drawn from an artifact the experiment runners actually wrote. A missing
artifact produces a recorded NOT GENERATED entry with the reason, never a placeholder:
in a paper pipeline a placeholder is indistinguishable from a result.

Writes to ``outputs/human_affect/figures/`` and never touches ``research_artifacts/``.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import git_commit  # noqa: E402
from research.human_affect import figures as F  # noqa: E402

EXP = paths.REPO_ROOT / "outputs" / "human_affect" / "experiments"
OUT = paths.REPO_ROOT / "outputs" / "human_affect" / "figures"

GENERATED: list[dict] = []
SKIPPED: list[dict] = []


def _relative(source: str) -> str:
    """A source path as the repository sees it.

    Recording an absolute path here would put the generating machine's directory layout
    into `figures.json`, and from there into `public/data/`, which is served to every
    reader. It also makes the record useless to anyone else: a path under someone's home
    directory is not a citation.
    """
    text = str(source).replace("\\", "/")
    root = paths.REPO_ROOT.as_posix()
    return text[len(root) + 1:] if text.startswith(root + "/") else text


def save(fig, name: str, caption: str, source: str) -> None:
    import matplotlib.pyplot as plt
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / ("%s.%s" % (name, ext)), dpi=200, bbox_inches="tight")
    plt.close(fig)
    GENERATED.append({"figure": name, "caption": caption,
                      "source_data": _relative(source)})
    progress.log("      %s" % name)


def skip(name: str, reason: str) -> None:
    SKIPPED.append({"figure": name, "status": "NOT GENERATED", "reason": reason})
    progress.log("      %-34s NOT GENERATED: %s" % (name, reason))


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def main() -> int:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    progress.log("[human-affect figures]")

    # -- speech ---------------------------------------------------------------
    speech = _read_json(EXP / "speech_emotion.json")
    if speech:
        cm = pd.read_csv(EXP / "speech_confusion.csv", index_col=0)
        save(F.fig_confusion(cm, "Speech emotion, held-out actors",
                             speech["test"]["accuracy"]),
             "figHA01_speech_confusion",
             "Row-normalised confusion matrix for speaker-independent speech emotion "
             "recognition on RAVDESS. Accuracy %.4f against a chance rate of %.4f."
             % (speech["test"]["accuracy"], speech["test"]["chance_accuracy"]),
             str(EXP / "speech_confusion.csv"))

        save(F.fig_calibration(pd.read_csv(EXP / "speech_calibration.csv"),
                               "Speech model calibration",
                               speech["test"]["calibration"]["ece"]),
             "figHA02_speech_calibration",
             "Reliability diagram for the speech model on held-out actors; expected "
             "calibration error %.4f." % speech["test"]["calibration"]["ece"],
             str(EXP / "speech_calibration.csv"))

        save(F.fig_group_importance(pd.read_csv(EXP / "speech_group_importance.csv"),
                                    "Acoustic feature families"),
             "figHA03_speech_feature_importance",
             "Permutation importance by acoustic feature family, each family shuffled "
             "as a unit so within-family correlation is not destroyed.",
             str(EXP / "speech_group_importance.csv"))

        preds = pd.read_csv(EXP / "speech_test_predictions.csv")
        save(F.fig_valence_arousal(preds, "Speech: predicted circumplex position"),
             "figHA04_speech_valence_arousal",
             "Predicted valence and arousal from acoustics, coloured by true emotion. "
             "Targets are derived from the categorical labels through a declared "
             "circumplex mapping, not from continuous human ratings.",
             str(EXP / "speech_test_predictions.csv"))
    else:
        for n in ("figHA01_speech_confusion", "figHA02_speech_calibration",
                  "figHA03_speech_feature_importance",
                  "figHA04_speech_valence_arousal"):
            skip(n, "speech_emotion.json absent; run run_human_affect_experiments.py")

    # -- text -----------------------------------------------------------------
    text = _read_json(EXP / "text_affect.json")
    if text:
        cm = pd.read_csv(EXP / "text_confusion.csv", index_col=0)
        save(F.fig_confusion(cm, "Text emotion (GoEmotions)",
                             text["test"]["accuracy"]),
             "figHA05_text_confusion",
             "Confusion matrix for linguistic affect on GoEmotions, Ekman grouping. "
             "Accuracy %.4f against chance %.4f."
             % (text["test"]["accuracy"], text["test"]["chance_accuracy"]),
             str(EXP / "text_confusion.csv"))

        save(F.fig_label_quality(pd.read_csv(EXP / "text_label_quality.csv")),
             "figHA06_text_label_quality",
             "Model accuracy within bands of annotator agreement. Accuracy rises from "
             "%.3f on examples the raters split over to %.3f on unanimous ones, so a "
             "large part of the apparent error is label noise rather than model failure."
             % (min(b["accuracy"] for b in text["label_quality"]["bands"]
                    if b.get("status") == "OK"),
                max(b["accuracy"] for b in text["label_quality"]["bands"]
                    if b.get("status") == "OK")),
             str(EXP / "text_label_quality.csv"))

        save(F.fig_calibration(pd.read_csv(EXP / "text_calibration.csv"),
                               "Text model calibration",
                               text["test"]["calibration"]["ece"]),
             "figHA07_text_calibration",
             "Reliability diagram for the text model; expected calibration error %.4f."
             % text["test"]["calibration"]["ece"],
             str(EXP / "text_calibration.csv"))

        examples = text.get("token_attribution_examples") or []
        if examples:
            save(F.fig_text_token_attribution(examples[0]),
                 "figHA08_text_token_attribution",
                 "Token contributions for one prediction, read directly from the linear "
                 "coefficients. Exact for this model rather than a surrogate "
                 "approximation of it.",
                 str(EXP / "text_affect.json"))
        else:
            skip("figHA08_text_token_attribution", "no attribution examples recorded")
    else:
        for n in ("figHA05_text_confusion", "figHA06_text_label_quality",
                  "figHA07_text_calibration", "figHA08_text_token_attribution"):
            skip(n, "text_affect.json absent")

    # -- face -----------------------------------------------------------------
    face = _read_json(EXP / "face_emotion.json")
    if face and face.get("status") != "INSUFFICIENT DATA":
        cm = pd.read_csv(EXP / "face_confusion.csv", index_col=0)
        save(F.fig_confusion(cm, "Facial expression, held-out actors",
                             face["test"]["accuracy"]),
             "figHA09_face_confusion",
             "Confusion matrix for facial-expression emotion recognition from real human "
             "video, YuNet detection with five-landmark geometry. Accuracy %.4f."
             % face["test"]["accuracy"],
             str(EXP / "face_confusion.csv"))
        save(F.fig_group_importance(pd.read_csv(EXP / "face_importance.csv"),
                                    "Facial expression features"),
             "figHA10_face_feature_importance",
             "Permutation importance of the facial geometry and appearance features.",
             str(EXP / "face_importance.csv"))
    else:
        for n in ("figHA09_face_confusion", "figHA10_face_feature_importance"):
            skip(n, "face_emotion.json absent or insufficient data")

    # -- fusion ---------------------------------------------------------------
    fusion = _read_json(EXP / "fusion.json")
    if fusion:
        table = pd.read_csv(EXP / "fusion_ablation.csv")
        chance = 1.0 / len(fusion["classes"])
        save(F.fig_modality_ablation(table, chance),
             "figHA11_modality_ablation",
             "Balanced accuracy for each modality subset on held-out actors. Fusion "
             "changes balanced accuracy by %+.4f against the best single modality."
             % fusion["fusion_minus_best_unimodal_balanced_accuracy"],
             str(EXP / "fusion_ablation.csv"))

        dva = pd.read_csv(EXP / "fusion_disagreement_vs_accuracy.csv")
        save(F.fig_disagreement(dva, fusion["agreement_rate"]),
             "figHA12_cross_modal_disagreement",
             "Fused accuracy against the Jensen-Shannon divergence between the audio and "
             "facial posteriors. The modalities name the same emotion on %.1f%% of test "
             "clips." % (100 * fusion["agreement_rate"]),
             str(EXP / "fusion_disagreement_vs_accuracy.csv"))
    else:
        for n in ("figHA11_modality_ablation", "figHA12_cross_modal_disagreement"):
            skip(n, "fusion.json absent; run run_human_affect_fusion.py")

    # -- robustness -----------------------------------------------------------
    if (EXP / "robustness.csv").exists():
        table = pd.read_csv(EXP / "robustness.csv")
        for modality in ("audio", "face"):
            if (table["modality"] == modality).any():
                save(F.fig_robustness(table, modality),
                     "figHA13_robustness_%s" % modality,
                     "Balanced accuracy under real %s corruption applied to the signal "
                     "itself, with the whole feature pipeline re-run. These are random "
                     "corruptions and say nothing about adversarial robustness."
                     % modality,
                     str(EXP / "robustness.csv"))
            else:
                skip("figHA13_robustness_%s" % modality, "no rows for this modality")
    else:
        skip("figHA13_robustness_audio", "robustness.csv absent")
        skip("figHA13_robustness_face", "robustness.csv absent")

    # -- fairness -------------------------------------------------------------
    if (EXP / "fairness.csv").exists():
        table = pd.read_csv(EXP / "fairness.csv")
        for group in ("actor_sex", "intensity"):
            if ((table["group"] == group) & (table["status"] == "OK")).any():
                save(F.fig_fairness(table, group),
                     "figHA14_fairness_%s" % group,
                     "Accuracy by %s with 95%% Wilson intervals. Overlapping intervals "
                     "mean the sample does not establish a difference."
                     % group.replace("_", " "),
                     str(EXP / "fairness.csv"))
            else:
                skip("figHA14_fairness_%s" % group, "no usable rows for this group")
    else:
        skip("figHA14_fairness_actor_sex", "fairness.csv absent")
        skip("figHA14_fairness_intensity", "fairness.csv absent")

    # -- trajectories ---------------------------------------------------------
    if (EXP / "affect_trajectories.csv").exists():
        traj = pd.read_csv(EXP / "affect_trajectories.csv")
        keys = list(dict.fromkeys(traj["clip_key"]))[:2]
        for i, key in enumerate(keys, start=1):
            save(F.fig_trajectory(traj, key),
                 "figHA15_affect_trajectory_%d" % i,
                 "Timestamped affect within one clip: dimensional affect from audio "
                 "windows and mouth geometry from video frames on a common time axis. "
                 "The recording is not collapsed to a single label.",
                 str(EXP / "affect_trajectories.csv"))
        if not keys:
            skip("figHA15_affect_trajectory_1", "no trajectory rows")
    else:
        skip("figHA15_affect_trajectory_1", "affect_trajectories.csv absent")

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "n_generated": len(GENERATED),
        "n_not_generated": len(SKIPPED),
        "figures": GENERATED,
        "not_generated": SKIPPED,
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "figures.json", manifest)
    progress.log("generated %d figures, %d not generated"
                 % (len(GENERATED), len(SKIPPED)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
