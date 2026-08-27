"""Assemble the AEGIS-Market multimodal research dataset.

    python scripts/build_dataset.py --start 2015-01-01 --episodes 140

Pipeline: real panel -> PIT universe -> synthetic episodes injected into the raw bars ->
market features -> regimes (fitted on the training window only) -> text corpus ->
multimodal assembly.

Splits are temporal and frozen here, before any model is fitted:

    train       ..            2021-12-31
    validation  2022-01-01 .. 2023-12-31
    holdout     2024-01-01 ..              (touched once, at the end)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from research.core import paths, progress
from research.core.manifest import ReproducibilityManifest, file_hash
from research.data import dataset as ds
from research.detection import episodes as ep
from research.market import features as mf
from research.regime import detection as rd

TRAIN_END = pd.Timestamp("2021-12-31")
VAL_END = pd.Timestamp("2023-12-31")


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def assign_split(d: pd.Timestamp) -> str:
    if d <= TRAIN_END:
        return "train"
    if d <= VAL_END:
        return "validation"
    return "holdout"


def main() -> int:
    ap_ = argparse.ArgumentParser()
    ap_.add_argument("--start", type=_d, default=date(2015, 1, 1))
    ap_.add_argument("--end", type=_d, default=date(2026, 8, 14))
    ap_.add_argument("--episodes", type=int, default=140)
    ap_.add_argument("--background-rows", type=int, default=5000)
    ap_.add_argument("--seed", type=int, default=20260818)
    ap_.add_argument("--out", default="multimodal_dataset.parquet")
    ap_.add_argument("--resume", action="store_true",
                     help="reuse the assembly checkpoint if present")
    args = ap_.parse_args()

    paths.ensure_dirs()
    t0 = time.time()

    progress.reset()
    progress.log("[1/7] loading panel and universe")
    panel = pd.read_parquet(paths.PANEL / "cash_panel.parquet")
    uni = pd.read_parquet(paths.PANEL / "universe.parquet")
    panel = panel[(panel["date"] >= pd.Timestamp(args.start))
                  & (panel["date"] <= pd.Timestamp(args.end))]
    symbols = sorted(uni[uni["rebalance_date"] >= pd.Timestamp(args.start)]
                     ["symbol"].unique().tolist())
    panel = panel[panel["symbol"].isin(symbols)].reset_index(drop=True)
    print("      panel %d rows, %d symbols, %s .. %s"
          % (len(panel), panel["symbol"].nunique(), panel["date"].min().date(),
             panel["date"].max().date()))

    progress.log("[2/7] generating and injecting synthetic episodes")
    cfg = ep.GeneratorConfig(n_episodes=args.episodes, seed=args.seed)
    eps = ep.generate(panel, symbols, cfg)
    injected, labels = ep.inject(panel, eps, cfg)
    print("      %d episodes, %d labelled instrument-days, %d censored"
          % (len(eps), len(labels), sum(e.censored for e in eps)))

    progress.log("[3/7] market features on the injected panel")
    feat = mf.compute_features(injected)
    print("      %d rows x %d cols" % feat.shape)

    progress.log("[4/7] regimes (fitted on the training window only)")
    desc = rd.index_descriptors(feat)
    train_desc = desc[desc.index <= TRAIN_END]
    order = rd.select_order(train_desc)
    print(order.to_string(index=False))
    best_k, k_justification = rd.select_k(order)
    print("      selected k = %d -- %s" % (best_k, k_justification))
    model = rd.RegimeModel(best_k, args.seed).fit(train_desc)
    proba = model.predict_proba(desc)
    regimes = pd.DataFrame({"date": desc.index, "regime_id": model.predict(desc)})
    for k in range(ds.MAX_REGIMES):
        regimes["regime_p%d" % k] = proba[:, k] if k < proba.shape[1] else np.nan
    stability = rd.bootstrap_stability(train_desc, best_k, n_boot=40, seed=args.seed)
    shuffle = rd.shuffle_null(train_desc, best_k, n_perm=60, seed=args.seed)
    print("      stability ARI mean %.3f | shuffle-null p=%.4f (obs %.3f vs null %.3f)"
          % (stability["ari_mean"], shuffle["p_value"],
             shuffle["observed_persistence"], shuffle["null_mean"]))

    progress.log("[5/7] text corpus")
    docs = ep.generate_text_corpus(feat[["symbol", "date"]], eps, cfg)
    print("      %d documents (%s)"
          % (len(docs), docs["doc_kind"].value_counts().to_dict()))

    progress.log("[6/7] multimodal assembly (image + audio + video per row)")
    bc = ds.BuildConfig(background_rows=args.background_rows, seed=args.seed,
                        enable_propagation=False)
    checkpoint = paths.PANEL / ("_assembly_checkpoint_%s.parquet" % args.seed)
    if args.resume and checkpoint.exists():
        progress.log("      resuming from %s" % checkpoint.name)
        data = pd.read_parquet(checkpoint)
    else:
        data = ds.build(feat, labels, docs, regimes, bc)
        data.to_parquet(checkpoint, index=False)
        progress.log("      checkpoint written: %s" % checkpoint.name)

    progress.log("      attaching propagation block")
    data = ds.attach_propagation(data, feat)
    data["split"] = data["date"].map(assign_split)
    print("      %d rows x %d cols in %.1fs" % (data.shape[0], data.shape[1],
                                                time.time() - t0))
    print(data.groupby(["split", "is_episode"]).size().to_string())

    progress.log("[7/7] writing")
    out = paths.PANEL / args.out
    data.to_parquet(out, index=False)
    labels.to_parquet(paths.PANEL / "episode_labels.parquet", index=False)
    docs.to_parquet(paths.PANEL / "text_corpus.parquet", index=False)

    man = ReproducibilityManifest(
        experiment_id="dataset_build", run_id="ds_%s" % args.seed, seed=args.seed,
        config={"start": str(args.start), "end": str(args.end),
                "episodes": args.episodes, "background_rows": args.background_rows,
                "generator": dict(cfg.__dict__.items()),
                "regime_k": best_k, "train_end": str(TRAIN_END.date()),
                "val_end": str(VAL_END.date())},
        dataset_version=ds.DATASET_VERSION, dataset_hash=file_hash(out),
        feature_version=mf.FEATURE_VERSION,
        model_versions={"regime": rd.REGIME_VERSION,
                        "text_affect": "text-affect-v1",
                        "image": "image-v1", "audio": "audio-v1", "video": "video-v1",
                        "generator": ep.GENERATOR_VERSION},
        notes=["regimes fitted on train window only",
               "audio modality is sonification, not speech (limitation L-06)",
               "episode labels are synthetic (limitation L-04)"],
    )
    man.write(paths.MANIFESTS / "dataset_build.json")

    stats = {
        "built_at": datetime.now(UTC).isoformat(),
        "rows": int(len(data)), "columns": int(data.shape[1]),
        "episodes": len(eps),
        "episode_rows": int(data["is_episode"].sum()),
        "positive_rate": float(data["is_episode"].mean()),
        "split_counts": data["split"].value_counts().to_dict(),
        "state_counts": data["state"].value_counts().to_dict(),
        "regime_order_selection": order.to_dict(orient="records"),
        "regime_selected_k": best_k,
        "regime_k_justification": k_justification,
        "regime_stability": stability,
        "regime_shuffle_null": shuffle,
        "doc_kinds": docs["doc_kind"].value_counts().to_dict(),
        "coverage": {c: float(data[c].mean()) for c in ds.COVERAGE_FLAGS
                     if c in data.columns},
        "dataset_sha256": file_hash(out),
        "elapsed_s": round(time.time() - t0, 1),
    }
    (paths.MANIFESTS / "dataset_stats.json").write_text(
        json.dumps(stats, indent=2, default=str), encoding="utf-8")
    print("\nwrote %s (%.1f MB) in %.1fs"
          % (out, out.stat().st_size / 1e6, time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
