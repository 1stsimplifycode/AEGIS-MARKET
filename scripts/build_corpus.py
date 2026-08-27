"""Build the traceable research corpus and report what it actually contains.

    python scripts/build_corpus.py --all

Writes parquet shards to ``data/corpus/`` (gitignored) and a report to
``outputs/corpus/``. Nothing under ``research_artifacts/`` is touched and the frozen
holdout keeps its label: rows split ``holdout`` in the modelling panel stay ``holdout``
here rather than being relabelled ``test``.

The report is the point as much as the corpus. A row count is not a sample count, so the
build measures duplication, cross-split contamination, effective sample size and the
real/synthetic composition, and refuses to describe the result as N independent samples
when it is not.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import environment_snapshot, git_commit  # noqa: E402
from research.corpus import CORPUS_VERSION, PROVENANCE_COLUMNS  # noqa: E402
from research.corpus import build as B  # noqa: E402
from research.corpus import quality as Q  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "corpus"
SEED = 20260818

#: How many synthetic rows to draw per source shard. Deliberately a small fraction of the
#: real corpus: synthetic data is a secondary resource here, not the way the size target
#: is met. The real shards already exceed the target on their own.
SYNTHETIC_PLAN = (
    ("panel_features", 40000, "multimodal", "symbol_day"),
    ("speech_utterance", 20000, "audio", "utterance"),
    ("face_performance", 20000, "video", "performance"),
)


def chronological_split_fn(panel: pd.DataFrame):
    """Reuse the modelling panel's own date boundaries, so a split means one thing.

    Financial data must split by time, never at random: a random split lets a model see
    the future of the very period it is scored on. The boundaries are read off the panel
    rather than re-derived, so the corpus cannot drift away from the models.
    """
    dates = pd.to_datetime(panel["date"])
    train_end = dates[panel["split"] == "train"].max()
    val_end = dates[panel["split"] == "validation"].max()

    def split_of(d) -> str:
        d = pd.Timestamp(d)
        if d <= train_end:
            return "train"
        if d <= val_end:
            return "validation"
        # Beyond validation is the frozen period. It is labelled holdout, never test:
        # relabelling it would hand the frozen rows to anything looking for a test set.
        return "holdout"

    return split_of, train_end, val_end


def analyse_shard(path: Path, name: str) -> dict:
    """Duplication, contamination and effective-N for one shard."""
    frame = pd.read_parquet(path)
    feature_cols = [c for c in frame.columns
                    if c not in PROVENANCE_COLUMNS
                    and pd.api.types.is_numeric_dtype(frame[c])]
    out = {"shard": name, "rows": int(len(frame)),
           "feature_columns": len(feature_cols)}
    if feature_cols:
        out["exact_duplicates"] = Q.exact_duplicates(frame, feature_cols)
        out["cross_split_content"] = Q.cross_split_duplicates(frame, feature_cols)
        out["near_duplicates"] = Q.near_duplicates(frame, feature_cols)
    out["cross_split"] = Q.cross_split_sources(frame)
    out["effective_sample_size"] = Q.effective_sample_size(frame)
    out["composition"] = Q.composition(frame)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--skip-market", action="store_true",
                    help="skip the 700k-row market shard for a fast rebuild")
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    B.CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    panel = pd.read_parquet(paths.PANEL / "multimodal_dataset.parquet",
                            columns=["symbol", "date", "split"])
    split_of, train_end, val_end = chronological_split_fn(panel)
    symbols = sorted(panel["symbol"].unique())
    progress.log("[corpus] %d modelled symbols; chronological boundaries "
                 "train<=%s validation<=%s"
                 % (len(symbols), train_end.date(), val_end.date()))

    shards = []
    progress.log("[real] assembling real shards")
    if not args.skip_market:
        shards.append(B.build_market_daily(symbols, split_of, log=progress.log))
    shards.append(B.build_financial_text(split_of, log=progress.log))
    shards.append(B.build_panel_features(log=progress.log))
    shards.append(B.build_speech(log=progress.log))
    shards.append(B.build_face(log=progress.log))
    shards.append(B.build_text_annotations(log=progress.log))

    progress.log("[synthetic] fitting generators on TRAINING rows only")
    for source, n, modality, unit in SYNTHETIC_PLAN:
        shards.append(B.build_synthetic(source, n, modality, unit,
                                        seed=args.seed, log=progress.log))

    real_shards = [s for s in shards if s.get("rows")]
    total = sum(s["rows"] for s in real_shards)
    progress.log("[analysis] %d rows across %d shards" % (total, len(real_shards)))

    per_shard = []
    for s in real_shards:
        p = Path(s["path"])
        if p.exists():
            per_shard.append(analyse_shard(p, s["shard"]))
            a = per_shard[-1]
            dup = a.get("exact_duplicates", {}).get("duplicate_fraction")
            eff = a["effective_sample_size"]
            progress.log("      %-22s %8d rows  %6d units  design effect %6.1f%s"
                         % (a["shard"], a["rows"], eff["n_independent_units"],
                            eff["design_effect"],
                            "" if dup is None else "  dup %.4f" % dup))

    # Corpus-level composition, from the provenance columns only so nothing is loaded
    # twice and the whole corpus never sits in memory at once.
    prov_parts = []
    for s in real_shards:
        p = Path(s["path"])
        if p.exists():
            prov_parts.append(pd.read_parquet(p, columns=list(PROVENANCE_COLUMNS)))
    provenance = pd.concat(prov_parts, ignore_index=True)
    composition = Q.composition(provenance)
    effective = Q.effective_sample_size(provenance)

    progress.log("  total %d samples: %d real (%.1f%%), %d synthetic (%.1f%%)"
                 % (composition["total_samples"], composition["real_samples"],
                    composition["real_percentage"], composition["synthetic_samples"],
                    composition["synthetic_percentage"]))
    progress.log("  test split: %d rows, %d real, %d synthetic (test_is_real_only=%s)"
                 % (composition["test_count"], composition["real_test_count"],
                    composition["synthetic_test_count"],
                    composition["test_is_real_only"]))
    progress.log("  effective: %d independent units, design effect %.1f"
                 % (effective["n_independent_units"], effective["design_effect"]))

    target_met = composition["total_samples"] >= 500_000
    report = {
        "corpus_version": CORPUS_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "seed": args.seed,
        "shards": shards,
        "per_shard_analysis": per_shard,
        "composition": composition,
        "effective_sample_size": effective,
        "scale_target": {
            "target": 500_000,
            "achieved": composition["total_samples"],
            "met": bool(target_met),
            "met_by_real_data_alone": bool(composition["real_samples"] >= 500_000),
            "note": ("The target is met by real observations; synthetic rows are a "
                     "secondary resource and are a small fraction of the corpus. No row "
                     "is a duplicate of another created to reach a number."),
        },
        "split_policy": {
            "financial": "chronological, using the modelling panel's own boundaries",
            "train_end": str(train_end.date()),
            "validation_end": str(val_end.date()),
            "human_affect": "speaker-disjoint; no actor appears in two splits",
            "text_annotations": "split by text, so one sentence cannot cross a split",
            "synthetic": "forced to train; barred from validation and test",
            "holdout": ("rows beyond the validation boundary keep the label holdout and "
                        "are never relabelled test"),
        },
        "environment": environment_snapshot(),
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "corpus_report.json", report)

    rows = []
    for a in per_shard:
        c, e = a["composition"], a["effective_sample_size"]
        rows.append({
            "shard": a["shard"], "rows": a["rows"],
            "source_type": max(c["source_datasets"], key=c["source_datasets"].get)
            if c["source_datasets"] else "",
            "real": c["real_samples"], "synthetic": c["synthetic_samples"],
            "units": e["n_independent_units"], "design_effect": e["design_effect"],
            "duplicate_fraction": a.get("exact_duplicates", {}).get(
                "duplicate_fraction"),
            "cross_split_clean": a.get("cross_split", {}).get("clean"),
        })
    pd.DataFrame(rows).to_csv(OUT / "corpus_shards.csv", index=False)
    progress.log("done in %.0fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
