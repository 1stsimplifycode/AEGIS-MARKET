"""Run the VLM visual branch on real human video and measure what it adds.

    python scripts/run_vlm_experiments.py --stage describe --backend smolvlm-256m
    python scripts/run_vlm_experiments.py --all

Every inference is cached on the image content, so a re-run costs nothing and a run
interrupted halfway resumes where it stopped.

**The evaluated subset is not the corpus.** A single frame costs about a minute on this
CPU, so the VLM sees a stratified sample of frames rather than the whole corpus. The
sample is drawn deterministically across emotions and actors, its size is reported beside
every result, and no output is ever generated for a frame the model did not actually see.
"""
from __future__ import annotations

import argparse
import json
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
from research.human_affect import corpora as C  # noqa: E402
from research.human_affect import fusion as fu  # noqa: E402
from research.human_affect import ingest  # noqa: E402
from research.vlm import PROMPT_VERSION, PROMPTS  # noqa: E402
from research.vlm import models as M  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "vlm"
SEED = 20260819

#: Frames per stage. Chosen against a measured ~60 s/frame budget on this hardware and
#: stated rather than hidden: these are the numbers the results rest on.
N_DESCRIBE_CLIPS = 80
N_TEMPORAL_CLIPS = 10
N_TEMPORAL_FRAMES = 3
N_ROBUST_FRAMES = 12
N_PARAPHRASE_FRAMES = 20


def peak_frame(path: str) -> tuple[np.ndarray, float, int]:
    """The middle frame of a clip: RAVDESS performances peak near the centre."""
    frames, times = ingest.sample_video_frames(path, fps=2.0, max_frames=8)
    if not frames:
        raise RuntimeError("no frames decoded from %s" % path)
    i = len(frames) // 2
    return frames[i], float(times[i]), i


def stratified_clips(n: int, seed: int = SEED) -> pd.DataFrame:
    """Deterministic sample balanced across emotion, drawn from held-out actors.

    Held-out actors on purpose: the VLM is being compared against a facial model that was
    fitted on the training actors, so the comparison has to happen where neither has an
    advantage from having seen the person.
    """
    index = C.load_index(C.RAVDESS_ROOT / "video_speech", pattern="*.mp4")
    if index.empty:
        raise SystemExit("no RAVDESS video present")
    index = C.speaker_disjoint_split(index, seed=20260819)
    pool = index[index["split"].isin(["validation", "test"])]
    if pool.empty:
        pool = index

    rng = np.random.default_rng(seed)
    per_emotion = max(1, n // pool["emotion"].nunique())
    picks = []
    for _emo, g in pool.groupby("emotion"):
        take = min(per_emotion, len(g))
        picks.append(g.iloc[rng.choice(len(g), size=take, replace=False)])
    out = pd.concat(picks, ignore_index=True)
    return out.sort_values(["emotion", "actor"]).reset_index(drop=True)


def _observation_row(obs, rec) -> dict:
    d = obs.to_dict()
    regions = d.pop("observed_regions", {})
    d.update({"region_%s" % k: bool(v) for k, v in regions.items()})
    d["n_regions_described"] = int(sum(bool(v) for v in regions.values()))
    d["ungrounded_terms"] = ",".join(d.get("ungrounded_terms") or [])
    d["emotion"] = getattr(rec, "emotion", "")
    d["actor"] = getattr(rec, "actor", -1)
    d["intensity"] = getattr(rec, "intensity", "")
    d["split"] = getattr(rec, "split", "")
    return d


# ---------------------------------------------------------------------- describe ----

def stage_describe(backends: list[str], n_clips: int, log=progress.log) -> dict:
    """One peak frame per clip, described by every backend."""
    clips = stratified_clips(n_clips)
    log("      %d clips across %d emotions, %d held-out actors"
        % (len(clips), clips["emotion"].nunique(), clips["actor"].nunique()))

    rows, t0 = [], time.time()
    for bi, backend in enumerate(backends):
        runner = M.VLMRunner(backend)
        for i, rec in enumerate(clips.itertuples(index=False)):
            try:
                frame, ts, fi = peak_frame(rec.path)
            except Exception as exc:
                log("        FAILED decode %s: %s" % (Path(rec.path).name, exc))
                continue
            obs = runner.describe(
                frame, PROMPTS["expression_features"], "expression_features",
                segment_id=fu.clip_key(rec.path), source_id=rec.path,
                timestamp_s=ts, frame_index=fi)
            rows.append(_observation_row(obs, rec))
            if (i + 1) % 10 == 0:
                done = bi * len(clips) + i + 1
                total = len(backends) * len(clips)
                rate = done / max(1e-9, time.time() - t0)
                log("        %s %d/%d  (%d cached)  eta %.0fs"
                    % (backend, i + 1, len(clips), runner.n_cache_hits,
                       (total - done) / max(1e-9, rate)))
        log("      %s: %d inferences, %d cache hits"
            % (backend, runner.n_inferences, runner.n_cache_hits))

    frame = pd.DataFrame(rows)
    # Merge with whatever other backends already wrote. Each backend runs as its own
    # process so they can proceed in parallel, and a plain overwrite would leave the file
    # holding only the last one to finish -- taking the cross-model comparison with it.
    path = OUT / "vlm_descriptions.csv"
    if path.exists():
        previous = pd.read_csv(path)
        previous = previous[~previous["model"].isin(set(frame["model"]))]
        frame = pd.concat([previous, frame], ignore_index=True)
    frame.to_csv(path, index=False)
    return summarise_descriptions(frame)


def summarise_descriptions(frame: pd.DataFrame) -> dict:
    """Coverage of observable regions, ungrounded language, and cross-model agreement."""
    out: dict = {"n_observations": int(len(frame)),
                 "n_clips": int(frame["segment_id"].nunique()),
                 "models": sorted(frame["model"].unique())}
    per_model = []
    region_cols = [c for c in frame.columns if c.startswith("region_")]
    for model, g in frame.groupby("model"):
        per_model.append({
            "model": model,
            "n": int(len(g)),
            "mean_regions_described": float(g["n_regions_described"].mean()),
            "region_coverage": {c.replace("region_", ""): float(g[c].mean())
                                for c in region_cols},
            "ungrounded_term_rate": float((g["n_ungrounded_terms"] > 0).mean()),
            "mean_ungrounded_terms": float(g["n_ungrounded_terms"].mean()),
            "mean_words": float(g["text"].astype(str).str.split().str.len().mean()),
            "mean_token_logprob": float(g["mean_token_logprob"].mean()),
            "mean_seconds_per_frame": float(g["elapsed_s"].replace(0.0, np.nan).mean()),
        })
    out["per_model"] = per_model

    # Cross-model agreement on which regions were described, clip by clip.
    models = out["models"]
    if len(models) >= 2:
        a = frame[frame["model"] == models[0]].set_index("segment_id")
        b = frame[frame["model"] == models[1]].set_index("segment_id")
        shared = sorted(set(a.index) & set(b.index))
        if shared:
            agree = np.mean([
                np.mean([bool(a.loc[s, c]) == bool(b.loc[s, c]) for c in region_cols])
                for s in shared])
            jac = []
            for s in shared:
                wa = set(str(a.loc[s, "text"]).lower().split())
                wb = set(str(b.loc[s, "text"]).lower().split())
                jac.append(len(wa & wb) / max(1, len(wa | wb)))
            out["cross_model"] = {
                "models": models[:2],
                "n_shared_clips": len(shared),
                "region_agreement": float(agree),
                "mean_word_jaccard": float(np.mean(jac)),
                "note": ("Both models are SmolVLM at different capacities, so this "
                         "measures whether size changes what is reported. It does "
                         "not test whether another architecture would see something "
                         "else; no second architecture ran on this hardware."),
            }
    return out


# ---------------------------------------------------------------------- temporal ----

def stage_temporal(backend: str, log=progress.log) -> dict:
    """Several timestamped frames per clip: change is observed, not assumed."""
    clips = stratified_clips(N_TEMPORAL_CLIPS * 2).head(N_TEMPORAL_CLIPS)
    runner = M.VLMRunner(backend)
    rows = []
    for rec in clips.itertuples(index=False):
        frames, times = ingest.sample_video_frames(rec.path, fps=2.0, max_frames=8)
        if len(frames) < N_TEMPORAL_FRAMES:
            continue
        picks = np.linspace(0, len(frames) - 1, N_TEMPORAL_FRAMES).astype(int)
        for fi in picks:
            obs = runner.describe(
                frames[fi], PROMPTS["expression_features"], "expression_features",
                segment_id=fu.clip_key(rec.path), source_id=rec.path,
                timestamp_s=float(times[fi]), frame_index=int(fi))
            rows.append(_observation_row(obs, rec))
        log("        %s %d frames" % (fu.clip_key(rec.path), len(picks)))

    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "vlm_temporal.csv", index=False)

    # Does the description change across a clip, or is it constant?
    changed, jac = [], []
    for _seg, g in frame.groupby("segment_id"):
        texts = list(g.sort_values("frame_index")["text"].astype(str))
        changed.append(len(set(texts)) > 1)
        for i in range(len(texts) - 1):
            wa, wb = set(texts[i].lower().split()), set(texts[i + 1].lower().split())
            jac.append(len(wa & wb) / max(1, len(wa | wb)))
    return {
        "n_clips": int(frame["segment_id"].nunique()) if len(frame) else 0,
        "frames_per_clip": N_TEMPORAL_FRAMES,
        "n_observations": int(len(frame)),
        "clips_with_any_change": float(np.mean(changed)) if changed else float("nan"),
        "mean_adjacent_frame_jaccard": float(np.mean(jac)) if jac else float("nan"),
        "interpretation": (
            "A model that returns the same sentence for every frame of a clip is "
            "not reading the expression; it is reading the scene. The fraction of "
            "clips whose description changes at all is the check for that."),
    }


# -------------------------------------------------------------------- robustness ----

def stage_robustness(backend: str, log=progress.log) -> dict:
    """Corrupt the pixels and measure whether the description survives."""
    clips = stratified_clips(N_ROBUST_FRAMES * 2).head(N_ROBUST_FRAMES)
    runner = M.VLMRunner(backend)
    rows = []
    for rec in clips.itertuples(index=False):
        frame, ts, fi = peak_frame(rec.path)
        base = runner.describe(frame, PROMPTS["expression_features"],
                               "expression_features",
                               segment_id=fu.clip_key(rec.path), source_id=rec.path,
                               timestamp_s=ts, frame_index=fi)
        for kind in ("blur", "darkness", "occlusion", "noise"):
            corrupted = fu.corrupt_frame(frame, kind, 0.25, seed=SEED)
            obs = runner.describe(corrupted, PROMPTS["expression_features"],
                                  "expression_features",
                                  segment_id=fu.clip_key(rec.path),
                                  source_id=rec.path, timestamp_s=ts, frame_index=fi)
            wa = set(base.text.lower().split())
            wb = set(obs.text.lower().split())
            rows.append({
                "segment_id": fu.clip_key(rec.path), "corruption": kind,
                "severity": 0.25,
                "identical_to_clean": bool(obs.text.strip() == base.text.strip()),
                "word_jaccard": len(wa & wb) / max(1, len(wa | wb)),
                "n_regions_clean": sum(bool(v)
                                   for v in base.observed_regions.values()),
                "n_regions_corrupted": sum(bool(v)
                                           for v in obs.observed_regions.values()),
                "ungrounded_clean": base.n_ungrounded_terms,
                "ungrounded_corrupted": obs.n_ungrounded_terms,
                "text_clean": base.text, "text_corrupted": obs.text,
            })
        log("        %s done" % fu.clip_key(rec.path))

    frame_out = pd.DataFrame(rows)
    frame_out.to_csv(OUT / "vlm_robustness.csv", index=False)
    per_kind = []
    for kind, g in frame_out.groupby("corruption"):
        per_kind.append({
            "corruption": kind, "n": int(len(g)),
            "identical_rate": float(g["identical_to_clean"].mean()),
            "mean_word_jaccard": float(g["word_jaccard"].mean()),
            "mean_region_delta": float((g["n_regions_corrupted"]
                                        - g["n_regions_clean"]).mean()),
            "ungrounded_increase": float((g["ungrounded_corrupted"]
                                          - g["ungrounded_clean"]).mean()),
        })
    return {
        "backend": backend, "n_frames": int(frame_out["segment_id"].nunique()),
        "severity": 0.25, "per_corruption": per_kind,
        "adversarial": ("NOT RUN. These are random corruptions of the pixels. An "
                        "adversarial claim needs an attacker who can see the model."),
    }


# ------------------------------------------------------------ consistency / control ----

def stage_consistency(backend: str, log=progress.log) -> dict:
    """Paraphrase sensitivity, and the negative control that matters most.

    The control: a rendered market chart contains no face. A model that describes eyes and
    a mouth in it is producing text unconstrained by the image, and any facial reading it
    gives elsewhere has to be discounted accordingly.
    """
    clips = stratified_clips(N_PARAPHRASE_FRAMES * 2).head(N_PARAPHRASE_FRAMES)
    runner = M.VLMRunner(backend)

    rows = []
    for rec in clips.itertuples(index=False):
        frame, ts, fi = peak_frame(rec.path)
        a = runner.describe(frame, PROMPTS["expression_features"],
                            "expression_features", segment_id=fu.clip_key(rec.path),
                            source_id=rec.path, timestamp_s=ts, frame_index=fi)
        b = runner.describe(frame, PROMPTS["expression_paraphrase"],
                            "expression_paraphrase", segment_id=fu.clip_key(rec.path),
                            source_id=rec.path, timestamp_s=ts, frame_index=fi)
        wa, wb = set(a.text.lower().split()), set(b.text.lower().split())
        ra = {k for k, v in a.observed_regions.items() if v}
        rb = {k for k, v in b.observed_regions.items() if v}
        rows.append({
            "segment_id": fu.clip_key(rec.path),
            "word_jaccard": len(wa & wb) / max(1, len(wa | wb)),
            "region_jaccard": len(ra & rb) / max(1, len(ra | rb)),
            "identical": bool(a.text.strip() == b.text.strip()),
        })
    paraphrase = pd.DataFrame(rows)
    paraphrase.to_csv(OUT / "vlm_paraphrase.csv", index=False)

    control = negative_control(runner, log=log)
    return {
        "backend": backend,
        "paraphrase": {
            "n": int(len(paraphrase)),
            "mean_word_jaccard": float(paraphrase["word_jaccard"].mean()),
            "mean_region_jaccard": float(paraphrase["region_jaccard"].mean()),
            "identical_rate": float(paraphrase["identical"].mean()),
            "note": ("Two wordings of the same observational request. Low overlap means "
                     "the output is driven by the phrasing as much as by the image."),
        },
        "negative_control": control,
    }


def negative_control(runner, log=progress.log) -> dict:
    """Describe rendered market charts, which contain no human face."""
    charts = sorted((paths.REPO_ROOT / "outputs" / "human_affect"
                     / "02_stream_separation_audit").glob("*.png"))
    if not charts:
        charts = sorted((paths.REPO_ROOT / "outputs").rglob("fig*.png"))[:6]
    charts = charts[:6]
    if not charts:
        return {"status": "NO CONTROL IMAGES AVAILABLE"}

    from PIL import Image
    rows = []
    for p in charts:
        arr = np.array(Image.open(p).convert("RGB"))
        obs = runner.describe(arr, PROMPTS["expression_features"],
                              "expression_features", segment_id="control:%s" % p.name,
                              source_id=str(p))
        described_face = any(obs.observed_regions.get(k)
                             for k in ("mouth", "eyes", "eyebrows"))
        rows.append({"image": p.name,
                     "describes_face_regions": bool(described_face),
                     "text": obs.text})
        log("        control %s -> face regions described: %s"
            % (p.name, described_face))
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "vlm_negative_control.csv", index=False)
    return {
        "n_images": int(len(frame)),
        "face_region_hallucination_rate": float(frame["describes_face_regions"].mean()),
        "interpretation": (
            "Rendered market charts contain no face. A non-zero rate here is the "
            "model producing facial language unconstrained by the image, and it "
            "bounds how far any facial reading elsewhere can be trusted."),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--stage", action="append",
                    choices=["describe", "temporal", "robustness", "consistency"])
    ap.add_argument("--backend", action="append")
    ap.add_argument("--clips", type=int, default=N_DESCRIBE_CLIPS)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    available = M.available_backends()
    if not available:
        raise SystemExit("no VLM weights present; run the model fetch first")
    backends = args.backend or available
    stages = (["describe", "temporal", "robustness", "consistency"] if args.all
              else (args.stage or ["describe"]))

    t0 = time.time()
    progress.log("[vlm] backends %s | stages %s" % (backends, stages))
    summary: dict = {"backends": backends, "available_backends": available,
                     "stages": stages, "prompt_version": PROMPT_VERSION,
                     "hardware_note": (
                         "CPU-only Intel i7-8665U, no CUDA device. Model choice is "
                         "bound by that: one frame through a 3B-class VLM is minutes "
                         "here, so the study uses on-device models and a stratified "
                         "frame sample rather than the whole corpus.")}

    if "describe" in stages:
        progress.log("[describe] peak frame per clip, every backend")
        summary["describe"] = stage_describe(backends, args.clips)
    if "temporal" in stages:
        progress.log("[temporal] several frames per clip")
        summary["temporal"] = stage_temporal(backends[0])
    if "robustness" in stages:
        progress.log("[robustness] corrupted pixels")
        summary["robustness"] = stage_robustness(backends[0])
    if "consistency" in stages:
        progress.log("[consistency] paraphrase and negative control")
        summary["consistency"] = stage_consistency(backends[0])

    summary.update({"run_at": datetime.now(UTC).isoformat(),
                    "git_commit": git_commit(),
                    "environment": environment_snapshot(),
                    "elapsed_s": round(time.time() - t0, 1)})

    # Stages run as separate processes so they can proceed in parallel; each writes the
    # same summary file. Merging rather than overwriting keeps the earlier stages'
    # results, which a plain write would silently discard.
    run_path = OUT / "vlm_run.json"
    if run_path.exists():
        try:
            previous = json.loads(run_path.read_text(encoding="utf-8"))
            merged = {k: v for k, v in previous.items() if k not in summary}
            merged.update(summary)
            merged["stages"] = sorted(set(previous.get("stages") or [])
                                      | set(summary.get("stages") or []))
            merged["backends"] = sorted(set(previous.get("backends") or [])
                                        | set(summary.get("backends") or []))
            summary = merged
        except Exception:
            pass
    jsonio.write(run_path, summary)
    progress.log("done in %.0fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
