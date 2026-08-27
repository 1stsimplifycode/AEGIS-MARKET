"""VLM-A against VLM-B across two architecture families, plus a hallucination battery.

    python scripts/run_vlm_family_comparison.py --all

**VLM-A** SmolVLM (SigLIP tower + Llama decoder), free-form description.
**VLM-B** BLIP-VQA (ViT-B/16 + BERT encoder-decoder, VQA head), question answering.

These are genuinely different families, which is what the earlier SmolVLM-256M against
SmolVLM-500M comparison was not. What they are *not* is interchangeable: one writes prose
and the other answers questions, so only some axes compare. The ones that do are latency,
memory, grounding accuracy, stability under corruption, unsupported inference, and the
contribution each makes to the ablation. Region coverage does not compare -- a VQA
model is asked about each region, so its coverage measures the question list rather than
the model -- and the report says so rather than putting the two in one column.

The hallucination battery (§6) is the sharp end. Six image classes, only one of which
contains a human face, and the question is what each model claims about the other five.
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
from research.human_affect import fusion as fu  # noqa: E402
from research.vlm import NEGATIVE_ANSWERS, PROMPTS  # noqa: E402,F401
from research.vlm import models as M  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "vlm"
SEED = 20260819

#: Image classes for the battery. Exactly one contains a human face; every claim of a face
#: in the other five is a false positive, and every facial-region description in them is
#: language the pixels do not support.
CONTAINS_FACE = {"human_face": True, "market_chart": False, "research_figure": False,
                 "text_only": False, "empty_background": False, "noise": False}


def battery_images(n_per_class: int = 3, seed: int = SEED) -> list[dict]:
    """Build the stimulus set. Everything is generated or drawn from this repository."""
    from PIL import Image, ImageDraw

    from research.image import chartgen
    from scripts.run_vlm_experiments import peak_frame, stratified_clips

    rng = np.random.default_rng(seed)
    items: list[dict] = []

    clips = stratified_clips(n_per_class * 4).head(n_per_class)
    for rec in clips.itertuples(index=False):
        frame, _ts, _fi = peak_frame(rec.path)
        items.append({"image": frame, "image_class": "human_face",
                      "name": fu.clip_key(rec.path)})

    # Real price series from the modelling panel, rendered by this repository's own
    # chart generator -- the same images the Stream A pipeline consumes.
    panel = pd.read_parquet(paths.PANEL / "multimodal_dataset.parquet",
                            columns=["symbol", "date"])
    cash = pd.read_parquet(paths.PANEL / "cash_panel.parquet",
                           columns=["symbol", "date", "open", "high", "low", "close"])
    symbols = [s for s in panel["symbol"].unique()[:40]
               if (cash["symbol"] == s).sum() > 200][:n_per_class]
    for sym in symbols:
        g = cash[cash["symbol"] == sym].sort_values("date").tail(120)
        arr = chartgen.rasterize(g["close"].to_numpy(float),
                                 g["high"].to_numpy(float),
                                 g["low"].to_numpy(float))
        arr = np.asarray(arr)
        if arr.ndim == 2:
            arr = np.dstack([arr] * 3)
        if arr.dtype != np.uint8:
            arr = (255 * np.clip(arr, 0, 1)).astype(np.uint8)
        items.append({"image": arr, "image_class": "market_chart", "name": str(sym)})

    figs = sorted((paths.REPO_ROOT / "outputs" / "research_figures").glob("*.png"))
    for p in figs[:n_per_class]:
        items.append({"image": np.array(Image.open(p).convert("RGB")),
                      "image_class": "research_figure", "name": p.name})

    for i in range(n_per_class):
        img = Image.new("RGB", (512, 512), (250, 250, 248))
        d = ImageDraw.Draw(img)
        for j, line in enumerate([
                "QUARTERLY DISCLOSURE", "", "Revenue recognition policy",
                "unchanged from the prior period.", "",
                "Segment reporting follows the", "operating-review structure.",
                "", "Note %d of the annual filing." % (i + 1)]):
            d.text((28, 40 + j * 34), line, fill=(30, 30, 30))
        items.append({"image": np.array(img), "image_class": "text_only",
                      "name": "filing_text_%d" % i})

    for i in range(n_per_class):
        shade = 235 - 40 * i
        items.append({"image": np.full((512, 512, 3), shade, dtype=np.uint8),
                      "image_class": "empty_background", "name": "flat_%d" % i})

    for i in range(n_per_class):
        items.append({"image": rng.integers(0, 256, (512, 512, 3), dtype=np.uint8),
                      "image_class": "noise", "name": "noise_%d" % i})
    return items


def claims_face(obs) -> bool:
    """Did the output assert facial content?"""
    answers = getattr(obs, "answers", None)
    if answers:
        return str(answers.get("grounding", "")).strip().lower() \
            not in NEGATIVE_ANSWERS
    return any(obs.observed_regions.get(k) for k in ("mouth", "eyes", "eyebrows"))


def describes_regions(obs) -> int:
    return int(sum(bool(v) for v in obs.observed_regions.values()))


def stage_battery(backends: list[str], n_per_class: int, log=progress.log) -> dict:
    """Every backend over every stimulus class."""
    items = battery_images(n_per_class)
    counts = pd.Series([i["image_class"] for i in items]).value_counts().to_dict()
    log("      %d stimuli: %s" % (len(items), counts))

    rows = []
    for backend in backends:
        runner = M.build_runner(backend)
        for it in items:
            obs = runner.describe(it["image"], PROMPTS["expression_features"],
                                  "expression_features",
                                  segment_id="battery:%s" % it["name"],
                                  source_id=it["image_class"])
            rows.append({
                "model": backend, "family": _family(backend),
                "image_class": it["image_class"], "name": it["name"],
                "contains_face": CONTAINS_FACE[it["image_class"]],
                "claims_face": claims_face(obs),
                "n_regions": describes_regions(obs),
                "n_ungrounded": obs.n_ungrounded_terms,
                "elapsed_s": obs.elapsed_s,
                "text": obs.text,
            })
        log("      %s: %d inferences, %d cached"
            % (backend, runner.n_inferences, runner.n_cache_hits))

    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "vlm_hallucination_battery.csv", index=False)

    per = []
    for (model, cls), g in frame.groupby(["model", "image_class"]):
        per.append({
            "model": model, "image_class": cls, "n": int(len(g)),
            "contains_face": bool(g["contains_face"].iloc[0]),
            "claims_face_rate": float(g["claims_face"].mean()),
            "mean_regions_described": float(g["n_regions"].mean()),
            "mean_ungrounded_terms": float(g["n_ungrounded"].mean()),
        })

    summary = {"n_stimuli": int(len(items)), "classes": counts, "per_class": per}
    for model, g in frame.groupby("model"):
        no_face = g[~g["contains_face"]]
        face = g[g["contains_face"]]
        summary.setdefault("per_model", []).append({
            "model": model, "family": _family(model),
            "false_face_claim_rate": float(no_face["claims_face"].mean()),
            "true_face_claim_rate": float(face["claims_face"].mean()),
            "mean_regions_on_faceless_images": float(no_face["n_regions"].mean()),
            "ungrounded_terms_total": int(g["n_ungrounded"].sum()),
            "mean_seconds_per_image": float(g["elapsed_s"].replace(0.0, np.nan).mean()),
        })
        progress.log("      %-14s false-face %.3f on %d faceless stimuli | "
                     "true-face %.3f | %.1f s/image"
                     % (model, no_face["claims_face"].mean(), len(no_face),
                        face["claims_face"].mean(),
                        g["elapsed_s"].replace(0.0, np.nan).mean()))
    return summary


def _family(backend: str) -> str:
    if backend in M.VQA_BACKENDS:
        return M.VQA_BACKENDS[backend]["family"]
    return M.BACKENDS[backend]["family"]


def stage_describe_vqa(n_clips: int, log=progress.log) -> dict:
    """Run the VQA family over the same clips the free-form family described."""
    from scripts.run_vlm_experiments import peak_frame, stratified_clips

    clips = stratified_clips(n_clips)
    runner = M.build_runner("blip-vqa-base")
    rows = []
    t0 = time.time()
    for i, rec in enumerate(clips.itertuples(index=False)):
        frame, ts, fi = peak_frame(rec.path)
        obs = runner.describe(frame, segment_id=fu.clip_key(rec.path),
                              source_id=rec.path, timestamp_s=ts, frame_index=fi)
        answers = getattr(obs, "answers", {})
        rows.append({
            "segment_id": obs.segment_id, "model": obs.model,
            "model_version": obs.model_version, "text": obs.text,
            "emotion": rec.emotion, "actor": rec.actor, "intensity": rec.intensity,
            "elapsed_s": obs.elapsed_s, "n_ungrounded_terms": obs.n_ungrounded_terms,
            "n_regions_described": describes_regions(obs),
            **{("answer_%s" % k): v for k, v in answers.items()},
            **{("region_%s" % k): bool(v) for k, v in obs.observed_regions.items()},
        })
        if (i + 1) % 20 == 0:
            log("        %d/%d  %.1f s/clip"
                % (i + 1, len(clips), (time.time() - t0) / (i + 1)))

    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "vqa_descriptions.csv", index=False)
    grounded = frame["answer_grounding"].astype(str).str.lower()
    return {
        "backend": "blip-vqa-base", "n_clips": int(len(frame)),
        "grounding_yes_rate_on_real_faces": float(
            (~grounded.isin(NEGATIVE_ANSWERS)).mean()),
        "mean_seconds_per_clip": float(frame["elapsed_s"].replace(0.0, np.nan).mean()),
        "ungrounded_terms_total": int(frame["n_ungrounded_terms"].sum()),
        "answer_distributions": {
            k: frame["answer_%s" % k].astype(str).str.lower().value_counts()
            .head(6).to_dict()
            for k in ("mouth", "eyes", "head", "eyebrows")},
    }


def stage_cross_family(log=progress.log) -> dict:
    """Where the two families agree on the same clips, on the axes that compare."""
    free_path, vqa_path = OUT / "vlm_descriptions.csv", OUT / "vqa_descriptions.csv"
    if not (free_path.exists() and vqa_path.exists()):
        return {"status": "BOTH FAMILIES NOT YET RUN"}

    free = pd.read_csv(free_path)
    vqa = pd.read_csv(vqa_path)
    out = {"note": ("Region coverage is not compared across families: a VQA model is "
                    "asked about each region, so its coverage reflects the question list "
                    "rather than what it chose to look at.")}

    rows = []
    for model, g in free.groupby("model"):
        a = g.set_index("segment_id")
        b = vqa.set_index("segment_id")
        shared = sorted(set(a.index) & set(b.index))
        if not shared:
            continue
        jac = []
        for s in shared:
            wa = set(str(a.loc[s, "text"]).lower().split())
            wb = set(str(b.loc[s, "text"]).lower().split())
            jac.append(len(wa & wb) / max(1, len(wa | wb)))
        # Does the free-form model mention an open mouth where VQA says open?
        agree_mouth = []
        for s in shared:
            ta = str(a.loc[s, "text"]).lower()
            vb = str(b.loc[s, "answer_mouth"]).lower()
            if vb in ("open", "closed"):
                said_open = "open" in ta and "mouth" in ta
                agree_mouth.append(said_open == (vb == "open"))
        rows.append({
            "free_form_model": model, "vqa_model": "blip-vqa-base",
            "n_shared_clips": len(shared),
            "mean_word_jaccard": float(np.mean(jac)),
            "mouth_state_agreement": (float(np.mean(agree_mouth))
                                      if agree_mouth else float("nan")),
            "n_mouth_comparable": len(agree_mouth),
        })
    out["pairs"] = rows
    for r in rows:
        log("      %s vs %s: word jaccard %.4f, mouth-state agreement %.4f (n=%d)"
            % (r["free_form_model"], r["vqa_model"], r["mean_word_jaccard"],
               r["mouth_state_agreement"], r["n_mouth_comparable"]))
    return out


def stage_cost(backends: list[str], log=progress.log) -> dict:
    """Latency and resident memory per backend, measured rather than quoted."""
    import os

    from scripts.run_vlm_experiments import peak_frame, stratified_clips

    try:
        import psutil
        proc = psutil.Process(os.getpid())
    except Exception:
        proc = None

    rec = next(stratified_clips(8).head(1).itertuples(index=False))
    frame, _ts, _fi = peak_frame(rec.path)

    rows = []
    for backend in backends:
        before = proc.memory_info().rss / 1e6 if proc else float("nan")
        runner = M.build_runner(backend, use_cache=False)
        runner.load()
        after_load = proc.memory_info().rss / 1e6 if proc else float("nan")
        t0 = time.time()
        runner.describe(frame, PROMPTS["expression_features"], "expression_features")
        elapsed = time.time() - t0
        rows.append({
            "model": backend, "family": _family(backend),
            "params": (M.VQA_BACKENDS.get(backend) or M.BACKENDS.get(backend))["params"],
            "licence": (M.VQA_BACKENDS.get(backend)
                        or M.BACKENDS.get(backend))["licence"],
            "seconds_per_image": round(elapsed, 2),
            "rss_after_load_mb": round(after_load, 1),
            "rss_delta_mb": round(after_load - before, 1),
        })
        log("      %-14s %6.2f s/image, +%.0f MB resident"
            % (backend, elapsed, after_load - before))
        del runner
    return {"rows": rows, "device": "cpu", "note": (
        "Measured on this machine, single process. RSS delta is the increase after "
        "loading the model, not a VRAM figure: there is no CUDA device here.")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--stage", action="append",
                    choices=["vqa", "battery", "cross", "cost"])
    ap.add_argument("--clips", type=int, default=80)
    ap.add_argument("--per-class", type=int, default=3)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    stages = (["vqa", "battery", "cross", "cost"] if args.all
              else (args.stage or ["vqa"]))
    free = M.available_backends()
    vqa = M.available_vqa_backends()
    if not vqa:
        raise SystemExit("no VQA backend present")

    t0 = time.time()
    summary: dict = {
        "families": {"VLM_A": {"backends": free, "family": "SmolVLM",
                               "mode": "free-form description"},
                     "VLM_B": {"backends": vqa, "family": "BLIP",
                               "mode": "visual question answering"}},
        "stages": stages,
    }
    progress.log("[vlm families] A=%s  B=%s" % (free, vqa))

    if "vqa" in stages:
        progress.log("[vqa] BLIP over the same clips SmolVLM described")
        summary["vqa_describe"] = stage_describe_vqa(args.clips)
    if "battery" in stages:
        progress.log("[battery] six stimulus classes, one contains a face")
        summary["hallucination_battery"] = stage_battery(
            free[:1] + vqa, args.per_class)
    if "cross" in stages:
        progress.log("[cross] agreement between families")
        summary["cross_family"] = stage_cross_family()
    if "cost" in stages:
        progress.log("[cost] latency and memory")
        summary["cost"] = stage_cost(free + vqa)

    summary.update({"run_at": datetime.now(UTC).isoformat(),
                    "git_commit": git_commit(),
                    "environment": environment_snapshot(),
                    "elapsed_s": round(time.time() - t0, 1)})
    jsonio.write(OUT / "vlm_family_comparison.json", summary)
    progress.log("done in %.0fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
