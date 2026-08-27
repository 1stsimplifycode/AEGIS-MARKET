"""HUMAN_AFFECT module adapters (Stream B).

Thin wrappers over ``research/human_affect/``, following the same rule as every other
adapter in this package: they orchestrate, they never define a feature or a metric.

Execution reality: each module runs on **real human media** when a licence-verified
corpus is present locally, and falls back to a clearly-labelled **synthetic development
fixture** when it is not. Which one happened is recorded in every artifact under
``execution``, because a fixture exercises the code path but is not evidence about a
person and no research claim may rest on one.

These adapters are sampled on purpose: they are the interactive `run.bat` surface and
must finish in seconds. The full-corpus results come from
``scripts/run_human_affect_experiments.py`` and ``scripts/run_human_affect_fusion.py``,
and modules 07 and 08 report those.
"""
from __future__ import annotations

import json
from pathlib import Path

from research.core import jsonio, paths
from research.human_affect import MediaKind
from scripts.stages import BLOCKED, OK, StageResult

OUT_ROOT = paths.REPO_ROOT / "outputs" / "human_affect"


def _out(slug: str) -> Path:
    d = OUT_ROOT / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fixture_note(kind: MediaKind) -> str:
    if kind == MediaKind.SYNTHETIC_DEVELOPMENT_FIXTURE:
        return ("Executed against a SYNTHETIC DEVELOPMENT FIXTURE because no "
                "licence-verified human corpus is present. This demonstrates that the "
                "pipeline runs; it is not evidence about any person and no research "
                "claim may rest on it.")
    return ""


def _real_media(pattern: str, limit: int = 0) -> list[Path]:
    """Real RAVDESS media if it has been fetched, newest-stable order, else empty.

    Returns paths rather than a boolean so the caller states in its artifact exactly
    which files it ran on; "we used real data" is not checkable, a SHA-listed file set
    is.
    """
    from research.human_affect import corpora as C

    roots = [C.RAVDESS_ROOT / "audio_speech", C.RAVDESS_ROOT / "video_speech"]
    found: list[Path] = []
    for root in roots:
        if root.exists():
            found.extend(sorted(root.rglob(pattern)))
    return found[:limit] if limit else found


# ------------------------------------------------------------ HUMAN_AFFECT-01 ----

def dataset_registry(force: bool = False) -> StageResult:
    """Wraps research.human_affect.registry."""
    from research.human_affect import registry as reg

    out = _out("01_dataset_registry")
    summary = reg.summary()
    jsonio.write(out / "datasets.json", summary)

    verified = summary["n_licence_verified"]
    present = summary["n_present_locally"]
    msg = ("%d datasets registered, %d licence-verified, %d present locally"
           % (summary["n_datasets"], verified, present))
    if verified == 0:
        return StageResult(BLOCKED, msg + " — no dataset may be ingested until its "
                                          "licence is verified locally",
                           outputs=[str(out / "datasets.json")], detail=summary)
    return StageResult(OK, msg, outputs=[str(out / "datasets.json")], detail=summary)


# ------------------------------------------------------------ HUMAN_AFFECT-02 ----

def stream_separation_audit(force: bool = False) -> StageResult:
    """Execute the Stream A / Stream B gates and record that they fired.

    The most important module here: it proves the separation holds rather than asserting
    it. Every case is checked against real signals produced by this repository's own
    sonifier, not against a mock.
    """
    import numpy as np

    from research.audio import sonify as so
    from research.human_affect import MediaKindError, face, guards, ingest, speech

    out = _out("02_stream_separation_audit")
    checks: list[dict] = []

    def record(name: str, expectation: str, fn) -> None:
        try:
            fn()
            checks.append({"check": name, "expectation": expectation,
                           "result": "NOT REFUSED", "passed": False})
        except MediaKindError as exc:
            checks.append({"check": name, "expectation": expectation,
                           "result": "REFUSED", "passed": True,
                           "message": str(exc)[:220]})

    close = 100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 240))
    volume = np.abs(np.random.default_rng(2).normal(1e6, 2e5, 240))
    son = np.asarray(so.sonify(close, volume), dtype=float)

    record("sonification_declared_into_speech_pipeline",
           "structural gate refuses a declared market_sonification",
           lambda: speech.analyse(son, so.SR, MediaKind.MARKET_SONIFICATION))
    record("sonification_mislabelled_as_human_speech",
           "content gate refuses a tone-like signal even when mislabelled",
           lambda: speech.analyse(son, so.SR, MediaKind.HUMAN_SPEECH))
    record("chart_image_into_face_pipeline",
           "structural gate refuses a declared market_chart_image",
           lambda: face.analyse_frames([ingest.synthetic_frame_fixture()], [0.0],
                                       MediaKind.MARKET_CHART_IMAGE))
    record("chart_video_into_face_pipeline",
           "structural gate refuses a declared market_chart_video",
           lambda: face.analyse_frames([ingest.synthetic_frame_fixture()], [0.0],
                                       MediaKind.MARKET_CHART_VIDEO))
    for purpose in ("deception detection from the interview",
                    "candidate ranking for hiring",
                    "diagnose an anxiety disorder",
                    "identify the speaker"):
        record("forbidden_inference::%s" % purpose,
               "prohibited inference refused",
               lambda p=purpose: guards.assert_no_forbidden_inference(p))

    # A legitimate path must still work, or the gate would be a blanket refusal.
    x, sr = ingest.synthetic_speech_fixture()
    try:
        speech.analyse(x, sr, MediaKind.SYNTHETIC_DEVELOPMENT_FIXTURE)
        checks.append({"check": "labelled_fixture_accepted",
                       "expectation": "a labelled development fixture is processed",
                       "result": "ACCEPTED", "passed": True})
    except Exception as exc:
        checks.append({"check": "labelled_fixture_accepted",
                       "expectation": "a labelled development fixture is processed",
                       "result": "REFUSED", "passed": False,
                       "message": str(exc)[:220]})

    failed = [c for c in checks if not c["passed"]]
    payload = {"checks": checks, "n_checks": len(checks), "n_failed": len(failed),
               "face_content_layer": guards.content_layer_for_faces_available()[1],
               "statement": ("Stream A (market-derived) and Stream B (human media) are "
                             "separated by a structural gate on declared provenance and "
                             "a content gate where one is available. Both were executed "
                             "against this repository's own sonifier output.")}
    jsonio.write(out / "stream_separation.json", payload)

    if failed:
        return StageResult(1, "%d of %d separation checks did not hold: %s"
                           % (len(failed), len(checks),
                              ", ".join(c["check"] for c in failed)),
                           outputs=[str(out / "stream_separation.json")], detail=payload)
    return StageResult(OK, "all %d stream-separation checks held" % len(checks),
                       outputs=[str(out / "stream_separation.json")], detail=payload)


# ------------------------------------------------------------ HUMAN_AFFECT-03 ----

def audio_ingestion(force: bool = False) -> StageResult:
    """Ingest human speech into timestamped segments of derived features."""
    import soundfile as sf

    from research.human_affect import ingest
    from research.human_affect import registry as reg

    out = _out("03_audio_ingestion")
    usable = [d for d in reg.apply_manifest()
              if d.licence_verified and d.present_locally
              and d.modality in ("audio", "audiovisual")]

    if not usable:
        # Execute against a labelled fixture so the path is exercised and the blocker is
        # visible, rather than writing nothing and leaving the reader to guess.
        x, sr = ingest.synthetic_speech_fixture(seconds=32.0)
        tmp = out / "_fixture.wav"
        sf.write(str(tmp), x, sr)
        record, segments = ingest.ingest_audio(
            tmp, MediaKind.SYNTHETIC_DEVELOPMENT_FIXTURE)
        tmp.unlink(missing_ok=True)
        payload = {
            "record": record.to_dict(),
            "n_segments": len(segments),
            "segments": [s.to_dict() for s in segments],
            "provenance": ingest.provenance_summary([record]),
            "execution": "SYNTHETIC DEVELOPMENT FIXTURE",
            "note": _fixture_note(MediaKind.SYNTHETIC_DEVELOPMENT_FIXTURE),
        }
        jsonio.write(out / "ingestion.json", payload)
        return StageResult(
            BLOCKED,
            "no licence-verified human audio corpus is present; the pipeline ran on a "
            "labelled fixture producing %d segments. Register and verify a dataset "
            "(see HUMAN_AFFECT-01) to run it on real speech." % len(segments),
            outputs=[str(out / "ingestion.json")], detail=payload)

    records, all_segments = [], []
    for d in usable:
        for path in sorted(Path(d.local_path).rglob("*.wav")):
            record, segments = ingest.ingest_audio(
                path, MediaKind.HUMAN_SPEECH, dataset_id=d.dataset_id,
                licence_verified=True)
            records.append(record)
            all_segments.extend(segments)
    payload = {"n_records": len(records), "n_segments": len(all_segments),
               "provenance": ingest.provenance_summary(records),
               "execution": "REAL HUMAN SPEECH"}
    jsonio.write(out / "ingestion.json", payload)
    return StageResult(OK, "%d files, %d segments" % (len(records), len(all_segments)),
                       outputs=[str(out / "ingestion.json")], detail=payload)


# ------------------------------------------------------------ HUMAN_AFFECT-04 ----

def speech_affect_pipeline(force: bool = False) -> StageResult:
    """Prosodic and spectral descriptors plus a dimensional affective representation."""
    from research.human_affect import ingest, speech

    out = _out("04_speech_affect_pipeline")
    real = _real_media("*.wav", limit=1)
    if real:
        x, sr = ingest.load_audio(str(real[0]))
        kind = MediaKind.HUMAN_SPEECH
    else:
        x, sr = ingest.synthetic_speech_fixture(seconds=6.0)
        kind = MediaKind.SYNTHETIC_DEVELOPMENT_FIXTURE
    result = speech.analyse(x, sr, kind)

    categorical_status = ""
    try:
        speech.classify_emotion(result.features)
    except NotImplementedError as exc:
        categorical_status = str(exc)

    payload = {
        "feature_names": speech.SPEECH_FEATURE_NAMES,
        "affect_dimensions": speech.AFFECT_DIMENSIONS,
        "result": result.to_dict(),
        "categorical_emotion": {
            "status": "TRAINED SEPARATELY" if real else "BLOCKED ON DATA",
            "detail": categorical_status,
            "trained_model": ("speech.classify_emotion stays unimplemented on purpose: a "
                              "single descriptor vector has no speaker-disjoint context, "
                              "so the trained model lives in "
                              "scripts/run_human_affect_experiments.py where the split "
                              "can be enforced.")},
        "source_file": real[0].name if real else None,
        "execution": ("REAL HUMAN SPEECH" if real
                      else "SYNTHETIC DEVELOPMENT FIXTURE"),
        "note": _fixture_note(kind),
    }
    jsonio.write(out / "speech_affect.json", payload)
    if not real:
        return StageResult(
            BLOCKED,
            "pipeline executes (%d descriptors, %d affect dimensions) but only on a "
            "labelled fixture; fetch a corpus to run it on real speech"
            % (len(speech.SPEECH_FEATURE_NAMES), len(speech.AFFECT_DIMENSIONS)),
            outputs=[str(out / "speech_affect.json")], detail=payload)
    return StageResult(
        OK,
        "%d descriptors and %d affect dimensions from real human speech (%s)"
        % (len(speech.SPEECH_FEATURE_NAMES), len(speech.AFFECT_DIMENSIONS),
           real[0].name),
        outputs=[str(out / "speech_affect.json")], detail=payload)


# ------------------------------------------------------------ HUMAN_AFFECT-05 ----

def video_ingestion(force: bool = False) -> StageResult:
    """Frame sampling and per-frame quality assessment for human video."""
    from research.human_affect import face, ingest
    from research.human_affect import registry as reg

    out = _out("05_video_ingestion")
    usable = [d for d in reg.apply_manifest()
              if d.licence_verified and d.present_locally
              and d.modality in ("video", "audiovisual")]

    real = _real_media("*.mp4", limit=1)
    if real:
        frames, times = ingest.sample_video_frames(str(real[0]), fps=2.0, max_frames=6)
        kind = MediaKind.HUMAN_VIDEO
    else:
        frames = [ingest.synthetic_frame_fixture() for _ in range(6)]
        times = [i * 0.5 for i in range(6)]
        kind = MediaKind.SYNTHETIC_DEVELOPMENT_FIXTURE
    result = face.analyse_frames(frames, times, kind)
    payload = {
        "n_frames_sampled": len(frames),
        "source_file": real[0].name if real else None,
        "frame_quality": [f.quality for f in result.frames],
        "detector": result.detector,
        "status": result.status,
        "notes": result.notes,
        "execution": "REAL HUMAN VIDEO" if real else "SYNTHETIC DEVELOPMENT FIXTURE",
        "licence_verified_video_datasets": [d.dataset_id for d in usable],
    }
    jsonio.write(out / "video_ingestion.json", payload)
    if not real:
        return StageResult(
            BLOCKED,
            "frame sampling and quality assessment execute on %d fixture frames; no "
            "human video corpus is present locally" % len(frames),
            outputs=[str(out / "video_ingestion.json")], detail=payload)
    return StageResult(
        OK,
        "sampled %d frames from real human video (%s); mean quality %.3f"
        % (len(frames), real[0].name,
           sum(f.quality.get("score", 0.0) for f in result.frames)
           / max(1, len(result.frames))),
        outputs=[str(out / "video_ingestion.json")], detail=payload)


# ------------------------------------------------------------ HUMAN_AFFECT-06 ----

def face_expression_pipeline(force: bool = False) -> StageResult:
    """Face detection, expression descriptors and temporal dynamics."""
    from research.human_affect import face, ingest

    out = _out("06_face_expression_pipeline")
    real = _real_media("*.mp4", limit=1)
    if real:
        frames, times = ingest.sample_video_frames(str(real[0]), fps=4.0, max_frames=8)
        kind = MediaKind.HUMAN_VIDEO
    else:
        frames = [ingest.synthetic_frame_fixture() for _ in range(8)]
        times = [i * 0.5 for i in range(8)]
        kind = MediaKind.SYNTHETIC_DEVELOPMENT_FIXTURE
    result = face.analyse_frames(frames, times, kind)

    backends = face.available_backends()
    payload = {
        "feature_names": face.FACE_FEATURE_NAMES,
        "available_backends": backends,
        "detector": result.detector,
        "status": result.status,
        "temporal": result.temporal,
        "frames": [f.to_dict() for f in result.frames],
        "gates": result.gates,
        "notes": result.notes,
        "source_file": real[0].name if real else None,
        "execution": "REAL HUMAN VIDEO" if real else "SYNTHETIC DEVELOPMENT FIXTURE",
        "capability_note": (
            "Expression features are five-landmark geometry normalised by inter-ocular "
            "distance, so they do not vary with how far the person sits from the camera. "
            "No identity representation is computed anywhere in this module. No "
            "heuristic detector fallback exists deliberately: one would return boxes on "
            "a chart as readily as on a face."),
    }
    jsonio.write(out / "face_expression.json", payload)

    if not backends:
        return StageResult(
            BLOCKED,
            "detection blocked: no backend installed (%s). Quality assessment, "
            "descriptors and temporal aggregation all ran."
            % ", ".join(n for n, _ in face.BACKENDS),
            outputs=[str(out / "face_expression.json")], detail=payload)
    return StageResult(OK, "detector %s over %d frames; %s"
                       % (result.detector, len(frames), result.status),
                       outputs=[str(out / "face_expression.json")], detail=payload)


# ------------------------------------------------------------ HUMAN_AFFECT-07 ----

def multimodal_fusion(force: bool = False) -> StageResult:
    """Report the executed audiovisual fusion ablation over every modality subset."""
    out = _out("07_multimodal_fusion")
    src = OUT_ROOT / "experiments" / "fusion.json"
    if not src.exists():
        return StageResult(
            BLOCKED,
            "fusion has not been executed; run scripts/run_human_affect_fusion.py --all",
            outputs=[])

    result = json.loads(src.read_text(encoding="utf-8"))
    rows = result.get("ablation") or []
    payload = {
        "n_aligned_clips": result.get("n_aligned_clips"),
        "n_actors": result.get("n_actors"),
        "classes": result.get("classes"),
        "fusion_method": result.get("fusion_method"),
        "weights": result.get("weights"),
        "ablation": rows,
        "fusion_minus_best_unimodal_balanced_accuracy":
            result.get("fusion_minus_best_unimodal_balanced_accuracy"),
        "agreement_rate": result.get("agreement_rate"),
        "text_arm": result.get("text_arm"),
        "execution": "REAL HUMAN AUDIOVISUAL MEDIA",
        "source": str(src),
        "note": ("Audio and video are joined on clip identity, so the two modalities are "
                 "the same utterance by the same actor recorded simultaneously rather "
                 "than two recordings paired by label. Splits are speaker-disjoint."),
    }
    jsonio.write(out / "multimodal_fusion.json", payload)
    return StageResult(
        OK,
        "%d modality subsets over %d aligned clips; fusion against best unimodal %+.4f "
        "balanced accuracy"
        % (len(rows), result.get("n_aligned_clips") or 0,
           result.get("fusion_minus_best_unimodal_balanced_accuracy") or 0.0),
        outputs=[str(out / "multimodal_fusion.json")], detail=payload)


# ------------------------------------------------------------ HUMAN_AFFECT-08 ----

def robustness_and_fairness(force: bool = False) -> StageResult:
    """Report the executed corruption robustness and subgroup performance analysis."""
    out = _out("08_robustness_fairness")
    exp = OUT_ROOT / "experiments"
    rob_path, fair_path = exp / "robustness.json", exp / "fairness.json"
    if not (rob_path.exists() and fair_path.exists()):
        return StageResult(
            BLOCKED,
            "robustness and fairness have not been executed; run "
            "scripts/run_human_affect_fusion.py --all",
            outputs=[])

    rob = json.loads(rob_path.read_text(encoding="utf-8"))
    fair = json.loads(fair_path.read_text(encoding="utf-8"))
    rows = rob.get("rows") or []
    worst = max((r for r in rows if r.get("corruption") != "none"),
                key=lambda r: r.get("degradation") or 0.0, default={})
    payload = {
        "robustness": rob,
        "fairness": fair,
        "worst_degradation": worst,
        "execution": "REAL HUMAN AUDIOVISUAL MEDIA",
        "note": ("Corruption is applied to the waveform and the pixels and the whole "
                 "feature pipeline is re-run, so a degradation here is a degradation of "
                 "the real signal rather than of a feature vector. Random corruption "
                 "only; adversarial robustness is a different property and is NOT RUN."),
    }
    jsonio.write(out / "robustness_fairness.json", payload)
    unestablished = sum(1 for g in (fair.get("gaps") or [])
                        if g.get("confidence_intervals_overlap"))
    return StageResult(
        OK,
        "%d corruption conditions (worst %s sev %.2f, %+.4f balanced accuracy); %d of %d "
        "subgroup gaps unestablished at this sample size"
        % (len([r for r in rows if r.get("corruption") != "none"]),
           worst.get("corruption", "-"), worst.get("severity", 0.0),
           -(worst.get("degradation") or 0.0), unestablished,
           len(fair.get("gaps") or [])),
        outputs=[str(out / "robustness_fairness.json")], detail=payload)


# ------------------------------------------------------------ HUMAN_AFFECT-09 ----

def vlm_visual_observation(force: bool = False) -> StageResult:
    """Report the executed vision-language observations of real human video."""
    from research.vlm import models as vlm_models

    out = _out("09_vlm_visual_observation")
    src = paths.REPO_ROOT / "outputs" / "vlm" / "vlm_run.json"
    backends = vlm_models.available_backends()
    if not src.exists():
        return StageResult(
            BLOCKED,
            "vision-language observation has not been executed; run "
            "scripts/run_vlm_experiments.py --all (backends present: %s)"
            % (", ".join(backends) or "none"),
            outputs=[])

    result = json.loads(src.read_text(encoding="utf-8"))
    describe = result.get("describe") or {}
    payload = {
        "backends_available": backends,
        "backends_run": result.get("backends"),
        "hardware_note": result.get("hardware_note"),
        "prompt_version": result.get("prompt_version"),
        "describe": describe,
        "temporal": result.get("temporal"),
        "robustness": result.get("robustness"),
        "consistency": result.get("consistency"),
        "execution": "REAL HUMAN VIDEO",
        "source": str(src),
        "safety_note": (
            "Prompts ask only for observable evidence. A guard refuses any prompt that "
            "asks a vision model to infer deception, identity, employment suitability, "
            "clinical state or an investment action, and it fires before the model is "
            "loaded. No identity representation is computed anywhere."),
    }
    jsonio.write(out / "vlm_visual.json", payload)

    per_model = describe.get("per_model") or []
    best = max(per_model, key=lambda m: m.get("mean_regions_described", 0.0),
               default={})
    return StageResult(
        OK,
        "%d observations over %d clips from %d model(s); %.2f observable regions per "
        "description, ungrounded-language rate %.3f"
        % (describe.get("n_observations", 0), describe.get("n_clips", 0),
           len(per_model), best.get("mean_regions_described", 0.0),
           best.get("ungrounded_term_rate", float("nan"))),
        outputs=[str(out / "vlm_visual.json")], detail=payload)


# ------------------------------------------------------------ HUMAN_AFFECT-10 ----

def vlm_ablation(force: bool = False) -> StageResult:
    """Does the vision-language channel add beyond specialised facial geometry?"""
    out = _out("10_vlm_ablation")
    src = paths.REPO_ROOT / "outputs" / "vlm" / "vlm_ablation.json"
    if not src.exists():
        return StageResult(
            BLOCKED,
            "vision-language ablation has not been executed; run "
            "scripts/run_vlm_ablation.py", outputs=[])

    result = json.loads(src.read_text(encoding="utf-8"))
    jsonio.write(out / "vlm_ablation.json", result)
    return StageResult(
        OK,
        "%d subsets over %d clips and %d actors; VLM on top of the facial model %+.4f "
        "balanced accuracy (%s)"
        % (len(result.get("ablation") or []), result.get("n_clips", 0),
           result.get("n_actors", 0), result.get("vlm_delta_over_face", float("nan")),
           result.get("verdict", "")),
        outputs=[str(out / "vlm_ablation.json")], detail=result)


# ------------------------------------------------------------ HUMAN_AFFECT-11 ----

def _report(slug: str, src: Path, name: str, missing: str):
    """Copy an executed artifact into the module folder, or report it BLOCKED."""
    out = _out(slug)
    if not src.exists():
        return None, StageResult(BLOCKED, missing, outputs=[])
    payload = json.loads(src.read_text(encoding="utf-8"))
    jsonio.write(out / name, payload)
    return payload, None


def multimodal_multiseed(force: bool = False) -> StageResult:
    """Report the executed multi-seed sweep over every modality arm."""
    src = (paths.REPO_ROOT / "outputs" / "multimodal_multiseed"
           / "multimodal_multiseed.json")
    payload, blocked = _report("11_multimodal_multiseed", src, "multiseed.json",
                               "multi-seed sweep not executed; run "
                               "scripts/run_multimodal_multiseed.py --tier both")
    if blocked:
        return blocked
    tiers = payload.get("tiers") or {}
    bits = []
    for name, t in tiers.items():
        bits.append("%s: %d clips/%d actors, best %s %.4f, gain %+.4f over %s (%s)"
                    % (name, t["n_clips"], t["n_actors"], t["best_subset"],
                       t["best_balanced_accuracy"],
                       t["multimodal_gain_over_best_unimodal"], t["best_unimodal"],
                       "established" if t["gain_exceeds_seed_noise_floor"]
                       else "not established"))
    return StageResult(
        OK, "%d seeds; %s" % (len(payload.get("seeds") or []), "; ".join(bits)),
        outputs=[str(_out("11_multimodal_multiseed") / "multiseed.json")],
        detail=payload)


# ------------------------------------------------------------ HUMAN_AFFECT-12 ----

def fusion_strategies(force: bool = False) -> StageResult:
    """Report the fusion-rule comparison."""
    src = (paths.REPO_ROOT / "outputs" / "human_affect" / "experiments"
           / "fusion_strategies.json")
    payload, blocked = _report("12_fusion_strategies", src, "fusion_strategies.json",
                               "fusion-rule comparison not executed; run "
                               "scripts/run_fusion_strategies.py")
    if blocked:
        return blocked
    ranking = payload.get("ranking") or {}
    return StageResult(
        OK,
        "best %s; spread between real rules %.4f against a seed noise floor of %.4f, so "
        "%s"
        % (payload.get("best_strategy"),
           payload.get("spread_between_real_strategies", float("nan")),
           (payload.get("seed_noise_floor") or {}).get("noise_floor_95", float("nan")),
           "a best rule is established" if payload.get("spread_exceeds_noise_floor")
           else "no rule is established as best"),
        outputs=[str(_out("12_fusion_strategies") / "fusion_strategies.json")],
        detail={"ranking": ranking, **payload})


# ------------------------------------------------------------ HUMAN_AFFECT-13 ----

def multimodal_robustness(force: bool = False) -> StageResult:
    """Report degradation, missing-modality and misalignment conditions."""
    src = (paths.REPO_ROOT / "outputs" / "human_affect" / "experiments"
           / "multimodal_robustness.json")
    payload, blocked = _report("13_multimodal_robustness", src, "robustness.json",
                               "multimodal robustness not executed; run "
                               "scripts/run_multimodal_robustness.py")
    if blocked:
        return blocked
    worst = payload.get("worst_condition") or {}
    mis = (payload.get("misalignment") or {}).get("rows") or []
    mis_txt = ", ".join("%s %.4f" % (r["condition"], r["balanced_accuracy_mean"])
                        for r in mis)
    return StageResult(
        OK,
        "clean %.4f; worst %s at %.4f (%.1f%% relative); misalignment: %s"
        % (payload.get("clean_balanced_accuracy", float("nan")),
           worst.get("condition"), worst.get("balanced_accuracy", float("nan")),
           100 * worst.get("relative_degradation", 0.0), mis_txt or "not run"),
        outputs=[str(_out("13_multimodal_robustness") / "robustness.json")],
        detail=payload)


# ------------------------------------------------------------ HUMAN_AFFECT-14 ----

def xai_calibration_representation(force: bool = False) -> StageResult:
    """Report modality attribution, calibration and the group analysis."""
    src = (paths.REPO_ROOT / "outputs" / "human_affect" / "experiments"
           / "xai_fairness.json")
    payload, blocked = _report("14_xai_calibration_representation", src, "xai.json",
                               "attribution and calibration not executed; run "
                               "scripts/run_multimodal_xai_fairness.py")
    if blocked:
        return blocked
    attr = (payload.get("attribution") or {}).get("blocks") or []
    top = attr[0] if attr else {}
    cal = payload.get("calibration") or {}
    gaps = (payload.get("representation") or {}).get("gaps") or []
    unestablished = sum(1 for g in gaps if g.get("intervals_overlap"))
    return StageResult(
        OK,
        "top block %s %+.4f; best calibrated %s; %d of %d group gaps unestablished at "
        "this sample size"
        % (top.get("block"), top.get("importance_mean", float("nan")),
           cal.get("best_calibrated"), unestablished, len(gaps)),
        outputs=[str(_out("14_xai_calibration_representation") / "xai.json")],
        detail=payload)


# ------------------------------------------------------------ HUMAN_AFFECT-15 ----

def vlm_family_comparison(force: bool = False) -> StageResult:
    """Report the two-family vision-language comparison and hallucination battery."""
    src = paths.REPO_ROOT / "outputs" / "vlm" / "vlm_family_comparison.json"
    payload, blocked = _report("15_vlm_family_comparison", src,
                               "family_comparison.json",
                               "family comparison not executed; run "
                               "scripts/run_vlm_family_comparison.py --all")
    if blocked:
        return blocked
    per = (payload.get("hallucination_battery") or {}).get("per_model") or []
    bits = ", ".join("%s false-face %.3f" % (m["model"], m["false_face_claim_rate"])
                     for m in per)
    return StageResult(
        OK,
        "%d stimuli across 6 classes; %s"
        % ((payload.get("hallucination_battery") or {}).get("n_stimuli", 0),
           bits or "battery not run"),
        outputs=[str(_out("15_vlm_family_comparison") / "family_comparison.json")],
        detail=payload)


# ------------------------------------------------------------ HUMAN_AFFECT-16 ----

def financial_domain_transfer(force: bool = False) -> StageResult:
    """Record the transfer interface and the state of the corpus search."""
    from datetime import UTC, datetime

    from research.core.manifest import environment_snapshot, git_commit
    from research.human_affect import transfer as T

    out = _out("16_financial_domain_transfer")
    summary = T.search_summary()
    result = T.run_transfer(None, None).to_dict()
    # Stamped like every other result artifact. A BLOCKED outcome is still a finding a
    # reviewer has to be able to date and attribute, and this one is cited by CLAIM-23.
    payload = {**summary, "transfer_result": result,
               "note": ("Nothing here fabricates a dataset and no general-domain corpus "
                        "is relabelled financial. The interface is complete and the "
                        "experiment runs unchanged once a qualifying corpus exists."),
               "run_at": datetime.now(UTC).isoformat(),
               "git_commit": git_commit(),
               "environment": environment_snapshot()}
    jsonio.write(out / "transfer.json", payload)
    return StageResult(
        BLOCKED,
        "general-domain validation COMPLETE; financial-domain validation NOT AVAILABLE. "
        "%d candidate corpora considered, %d qualify. %s"
        % (summary["n_candidates_considered"], summary["n_qualifying"],
           result["blocker"]),
        outputs=[str(out / "transfer.json")], detail=payload)
