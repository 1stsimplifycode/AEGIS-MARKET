"""Paper tables, every one from an executed artifact (§17).

    python scripts/generate_paper_tables.py

Ten tables, each written as CSV and as Markdown. A table whose source artifact is
missing is recorded as NOT GENERATED with the command that would produce it, never
emitted empty: an empty table in a paper directory reads as a result of zero.

Error analysis is computed here rather than read, because no earlier stage produced a
per-class error table for the full multimodal arm.
"""
from __future__ import annotations

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
from research.core.manifest import git_commit  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "paper_tables"
R = paths.REPO_ROOT
WRITTEN: list[dict] = []
SKIPPED: list[dict] = []


def _json(*parts):
    p = R.joinpath(*parts)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _csv(*parts):
    p = R.joinpath(*parts)
    return pd.read_csv(p) if p.exists() else None


def emit(name: str, frame: pd.DataFrame, caption: str, source: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT / ("%s.csv" % name), index=False)
    md = ["# %s" % name.replace("_", " ").title(), "", caption, "",
          frame.to_markdown(index=False, floatfmt=".4f"), "",
          "Source: `%s`" % source, ""]
    (OUT / ("%s.md" % name)).write_text("\n".join(md), encoding="utf-8")
    WRITTEN.append({"table": name, "rows": int(len(frame)), "caption": caption,
                    "source": source})
    progress.log("      %-32s %d rows" % (name, len(frame)))


def skip(name: str, reason: str) -> None:
    SKIPPED.append({"table": name, "status": "NOT GENERATED", "reason": reason})
    progress.log("      %-32s NOT GENERATED: %s" % (name, reason))


# ---------------------------------------------------------------------- tables ----

def t_dataset_composition() -> None:
    rep = _json("outputs", "corpus", "corpus_report.json")
    if not rep:
        return skip("table01_dataset_composition", "run scripts/build_corpus.py --all")
    rows = []
    for a in rep.get("per_shard_analysis") or []:
        c, e = a.get("composition") or {}, a.get("effective_sample_size") or {}
        rows.append({
            "shard": a["shard"], "rows": a["rows"],
            "real": c.get("real_samples"), "synthetic": c.get("synthetic_samples"),
            "independent_units": e.get("n_independent_units"),
            "design_effect": e.get("design_effect"),
            "cross_split_clean": (a.get("cross_split") or {}).get("clean"),
        })
    comp = rep["composition"]
    rows.append({"shard": "TOTAL", "rows": comp["total_samples"],
                 "real": comp["real_samples"], "synthetic": comp["synthetic_samples"],
                 "independent_units": rep["effective_sample_size"][
                     "n_independent_units"],
                 "design_effect": rep["effective_sample_size"]["design_effect"],
                 "cross_split_clean": True})
    emit("table01_dataset_composition", pd.DataFrame(rows),
         "Corpus composition by shard. The design effect is rows per independent unit; "
         "statistical inference uses the unit count, not the row count.",
         "outputs/corpus/corpus_report.json")


def t_unimodal_and_multimodal() -> None:
    agg = _csv("outputs", "multimodal_multiseed", "full_seed_summary.csv")
    if agg is None:
        return skip("table02_unimodal_results",
                    "run scripts/run_multimodal_multiseed.py")
    cols = ["subset", "n", "n_folds", "n_seeds", "balanced_accuracy_mean",
            "balanced_accuracy_sd", "balanced_accuracy_min", "balanced_accuracy_max",
            "balanced_accuracy_ci_low", "balanced_accuracy_ci_high", "accuracy_mean",
            "macro_f1_mean", "cohen_kappa_mean", "ece_mean"]
    cols = [c for c in cols if c in agg.columns]
    uni = agg[~agg["subset"].str.contains(r"\+")][cols]
    multi = agg[agg["subset"].str.contains(r"\+")][cols]
    emit("table02_unimodal_results", uni,
         "Single-modality arms, 720 aligned RAVDESS performances, 12 actors, "
         "leave-one-actor-out, 5 seeds. Chance is 0.1250.",
         "outputs/multimodal_multiseed/full_seed_summary.csv")
    emit("table03_multimodal_results", multi,
         "Multi-modality arms on the same clips, actors, folds and seeds.",
         "outputs/multimodal_multiseed/full_seed_summary.csv")


def t_vlm_comparison() -> None:
    fam = _json("outputs", "vlm", "vlm_family_comparison.json")
    run = _json("outputs", "vlm", "vlm_run.json")
    if not fam:
        return skip("table04_vlm_comparison",
                    "run scripts/run_vlm_family_comparison.py --all")
    rows = []
    per_model = ((run or {}).get("describe") or {}).get("per_model") or []
    by_model = {m["model"]: m for m in per_model}
    cost = {r["model"]: r for r in (fam.get("cost") or {}).get("rows", [])}
    battery = {r["model"]: r for r in
               (fam.get("hallucination_battery") or {}).get("per_model", [])}
    vqa = fam.get("vqa_describe") or {}

    for model in sorted(set(list(by_model) + list(battery) + list(cost))):
        m = by_model.get(model, {})
        b = battery.get(model, {})
        c = cost.get(model, {})
        rows.append({
            "model": model,
            "family": b.get("family") or c.get("family") or "SmolVLM",
            "params": c.get("params", ""),
            "licence": c.get("licence", ""),
            "seconds_per_image": (c.get("seconds_per_image")
                                  or b.get("mean_seconds_per_image")
                                  or m.get("mean_seconds_per_frame")),
            "rss_after_load_mb": c.get("rss_after_load_mb"),
            "false_face_claim_rate": b.get("false_face_claim_rate"),
            "true_face_claim_rate": b.get("true_face_claim_rate"),
            "ungrounded_term_rate": m.get("ungrounded_term_rate", 0.0),
            "mean_regions_described": m.get("mean_regions_described"),
        })
    if vqa:
        for r in rows:
            if r["model"] == "blip-vqa-base":
                r["mean_regions_described"] = None
                r["ungrounded_term_rate"] = (
                    vqa.get("ungrounded_terms_total", 0) / max(1, vqa.get("n_clips", 1)))
    emit("table04_vlm_comparison", pd.DataFrame(rows),
         "VLM-A (SmolVLM, free-form) against VLM-B (BLIP-VQA, question answering). "
         "False-face rate is on 15 stimuli containing no human face. Region counts are "
         "not comparable across families: a VQA model is asked about each region.",
         "outputs/vlm/vlm_family_comparison.json")


def t_ablation() -> None:
    agg = _csv("outputs", "multimodal_multiseed", "vlm_seed_summary.csv")
    if agg is None:
        return skip("table05_ablation", "run scripts/run_multimodal_multiseed.py")
    cols = [c for c in ["subset", "n", "n_folds", "n_seeds",
                        "balanced_accuracy_mean", "balanced_accuracy_sd",
                        "balanced_accuracy_ci_low", "balanced_accuracy_ci_high",
                        "macro_f1_mean"] if c in agg.columns]
    emit("table05_ablation", agg[cols],
         "All 15 subsets of TEXT, AUDIO, FACE and VLM on the 80 clips the VLM "
         "processed, 4 held-out actors, leave-one-actor-out, 5 seeds. The seed noise "
         "floor on this tier is 0.0745 balanced accuracy; no difference smaller than "
         "that is established.",
         "outputs/multimodal_multiseed/vlm_seed_summary.csv")


def t_multiseed() -> None:
    stats = _csv("outputs", "stats", "16_multiseed_significance", "seed_summary.csv")
    if stats is None:
        return skip("table06_multiseed", "run scripts/run_multiseed.py")
    sub = stats[stats["metric"] == "auprc"].sort_values("mean", ascending=False)
    cols = [c for c in ["arm", "n_seeds", "mean", "sd", "min", "max", "range",
                        "ci_low", "ci_high"] if c in sub.columns]
    emit("table06_multiseed", sub[cols].head(20),
         "STATS track: AUPRC across 10 seeds per ablation arm. Pooled seed sd 0.00316; "
         "95% noise floor 0.00877.",
         "outputs/stats/16_multiseed_significance/seed_summary.csv")


def t_calibration() -> None:
    cal = _csv("outputs", "human_affect", "experiments", "calibration_summary.csv")
    if cal is None:
        return skip("table07_calibration",
                    "run scripts/run_multimodal_xai_fairness.py")
    emit("table07_calibration", cal,
         "Calibration by arm under one definition of ECE (equal-mass bins, 10 bins). "
         "confidence_minus_accuracy above zero is overconfidence.",
         "outputs/human_affect/experiments/calibration_summary.csv")


def t_robustness() -> None:
    mm = _csv("outputs", "human_affect", "experiments", "multimodal_robustness.csv")
    if mm is None:
        return skip("table08_robustness", "run scripts/run_multimodal_robustness.py")
    cols = [c for c in ["condition", "target", "kind", "severity",
                        "balanced_accuracy_mean", "balanced_accuracy_sd",
                        "degradation", "relative_degradation", "n", "n_seeds"]
            if c in mm.columns]
    emit("table08_robustness", mm[cols],
         "Multimodal robustness. The model is fitted once on clean training folds and "
         "evaluated on degraded rows. Random and structural degradation only; "
         "adversarial robustness is NOT RUN.",
         "outputs/human_affect/experiments/multimodal_robustness.csv")


def t_synthetic() -> None:
    sweep = _json("outputs", "corpus", "synthetic_ratio_sweep.json")
    diag = _json("outputs", "corpus", "synthetic_degradation_diagnosis.json")
    if not sweep:
        return skip("table09_synthetic_augmentation",
                    "run scripts/run_real_vs_synthetic.py --ratio-sweep")
    rows = [{"synthetic_share": r["synthetic_share"], "n_synthetic": r["n_synthetic"],
             "n_train_total": r["n_train_total"], "auprc": r.get("auprc"),
             "auroc": r.get("auroc"),
             "delta_vs_real_only": r.get("auprc", np.nan)
             - sweep["baseline_auprc_real_only"]}
            for r in sweep["rows"] if r.get("status") == "OK"]
    emit("table09_synthetic_augmentation", pd.DataFrame(rows),
         "Synthetic share of the training set against AUPRC on real validation rows. "
         "Real training rows are held fixed; only generated rows are added.",
         "outputs/corpus/synthetic_ratio_sweep.json")

    if diag:
        mech = pd.DataFrame([
            {"mechanism": m["mechanism"],
             "supported": m["supported"], "reading": m["reading"]}
            for m in diag["mechanisms"]])
        emit("table09b_synthetic_mechanisms", mech,
             "Candidate mechanisms for the degradation, each measured. Only interaction "
             "loss is supported: a tree ensemble separates real from generated at AUC "
             "0.9639 while a linear model reaches 0.4952, which is chance.",
             "outputs/corpus/synthetic_degradation_diagnosis.json")


def t_error_analysis() -> None:
    """Per-class error and the most-confused pairs for the full multimodal arm."""
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import confusion_matrix

        from scripts.run_multimodal_multiseed import load_blocks
    except Exception as exc:
        return skip("table10_error_analysis", "imports failed: %s" % exc)

    try:
        meta, blocks = load_blocks("full")
    except SystemExit as exc:
        return skip("table10_error_analysis", str(exc))

    y = meta["emotion"].to_numpy()
    actors = meta["actor"].to_numpy()
    X = pd.concat([blocks[b] for b in sorted(blocks)], axis=1).loc[meta.index]
    Xv = np.nan_to_num(X.to_numpy(float), nan=0.0, posinf=0.0, neginf=0.0)
    classes = sorted(set(y))

    preds = np.empty(len(y), dtype=object)
    conf = np.zeros(len(y))
    for a in np.unique(actors):
        test = actors == a
        train = ~test
        clf = RandomForestClassifier(n_estimators=300, random_state=0,
                                     min_samples_leaf=2, n_jobs=1)
        clf.fit(Xv[train], y[train])
        preds[test] = clf.predict(Xv[test])
        conf[test] = clf.predict_proba(Xv[test]).max(axis=1)
    preds = preds.astype(str)

    cm = confusion_matrix(y, preds, labels=classes)
    rows = []
    for i, c in enumerate(classes):
        support = int(cm[i].sum())
        correct = int(cm[i, i])
        off = [(classes[j], int(cm[i, j])) for j in range(len(classes)) if j != i]
        worst = max(off, key=lambda t: t[1]) if off else ("-", 0)
        rows.append({
            "true_class": c, "support": support,
            "recall": correct / max(1, support),
            "most_confused_with": worst[0],
            "confusions_into_that_class": worst[1],
            "mean_confidence": float(conf[y == c].mean()),
        })
    frame = pd.DataFrame(rows).sort_values("recall")
    emit("table10_error_analysis", frame,
         "Per-class recall for the full multimodal arm, with the class each is most "
         "often confused into. Leave-one-actor-out, seed 0.",
         "computed in scripts/generate_paper_tables.py from the cached feature blocks")

    # High-confidence failures: the errors that would mislead a reader of the output.
    correct = (preds == y)
    dec = pd.qcut(conf, 5, labels=["q1", "q2", "q3", "q4", "q5"], duplicates="drop")
    band = pd.DataFrame({"confidence_band": dec.astype(str), "correct": correct,
                         "confidence": conf})
    agg = band.groupby("confidence_band").agg(
        n=("correct", "size"), accuracy=("correct", "mean"),
        mean_confidence=("confidence", "mean")).reset_index()
    agg["confidence_minus_accuracy"] = agg["mean_confidence"] - agg["accuracy"]
    emit("table10b_confidence_bands", agg,
         "Accuracy within confidence quintiles. A positive "
         "confidence-minus-accuracy in the top band is where a reader is most likely to "
         "be misled, because those are the confident errors.",
         "computed in scripts/generate_paper_tables.py")


def t_dataset_provenance() -> None:
    """One provenance row per source, across both streams and both outcomes.

    A provenance table that lists only what was used is a marketing document. The rows
    that carry the most information are the ones with a status of NOT OBTAINED, because
    they are the reason particular claims are absent.
    """
    rep = _json("outputs", "corpus", "corpus_report.json")
    if not rep:
        return skip("table11_dataset_provenance", "run scripts/build_corpus.py --all")
    counts = (rep.get("composition") or {}).get("source_datasets") or {}

    rows: list[dict] = []

    # Stream A sources, read from the executed artifact rather than restated here.
    stream_a = _csv("research_artifacts", "tables", "table02_provenance.csv")
    if stream_a is not None:
        for r in stream_a.to_dict("records"):
            rows.append({
                "source": r["source"], "stream": "A (market)",
                "modality": r["modality"], "licence": r["licence"],
                "rows_in_corpus": counts.get(_SOURCE_KEY.get(r["source"], ""), 0),
                "status": r["status"],
            })

    # Stream B sources, read from the affective dataset registry the pipeline wrote.
    reg = _json("outputs", "human_affect", "01_dataset_registry", "datasets.json")
    used = {"RAVDESS": "RAVDESS", "GOEMOTIONS": "GOEMOTIONS"}
    for d in (reg or {}).get("datasets") or []:
        did = d["dataset_id"].upper()
        n = counts.get(used.get(did, ""), 0)
        rows.append({
            "source": d["name"], "stream": "B (human media)",
            "modality": d["modality"], "licence": d["licence_claimed"],
            "rows_in_corpus": n,
            "status": "USED" if n else "REGISTERED, NOT INGESTED",
        })

    ta = _json("outputs", "human_affect", "experiments", "text_affect.json")
    if ta and counts.get("GOEMOTIONS"):
        rows.append({
            "source": ta.get("dataset", "GoEmotions"), "stream": "B (human media)",
            "modality": "text", "licence": "Apache-2.0",
            "rows_in_corpus": counts["GOEMOTIONS"], "status": "USED",
        })

    # Generated shards. Named as generated everywhere they appear.
    for key, modality in (("SYNTHETIC_FROM_PANEL_FEATURES", "panel features"),
                          ("SYNTHETIC_FROM_SPEECH_UTTERANCE", "speech descriptors"),
                          ("SYNTHETIC_FROM_FACE_PERFORMANCE", "face descriptors")):
        if key in counts:
            rows.append({
                "source": key, "stream": "corpus",
                "modality": modality,
                "licence": "repository licence (generated by this project)",
                "rows_in_corpus": counts[key],
                "status": "TRAINING SPLIT ONLY (limitation N-09)",
            })

    # Candidates assessed for financial-domain transfer and rejected. These rows are the
    # evidence behind L-16 and CLAIM-23.
    tr = _json("outputs", "human_affect", "16_financial_domain_transfer",
               "transfer.json")
    for c in (tr or {}).get("candidates") or []:
        rows.append({
            "source": c["dataset_id"], "stream": "B (candidate)",
            "modality": c["modality"], "licence": c["licence"],
            "rows_in_corpus": 0,
            "status": "NOT OBTAINED (limitation L-16): %s"
                      % c["disqualifying_reason"].split(";")[0],
        })

    # Anything the corpus counts but the loop above did not name would be a source with
    # rows and no provenance, which is the failure this table exists to prevent.
    named = {_SOURCE_KEY.get(r["source"], r["source"]) for r in rows}
    named |= {"RAVDESS", "GOEMOTIONS"}
    for key, n in sorted(counts.items()):
        if key in named:
            continue
        extra = _EXTRA_SOURCE.get(key, ("unspecified",
                                        "declared in docs/DATA_LICENSING.md"))
        rows.append({
            "source": key, "stream": "corpus",
            "modality": extra[0], "licence": extra[1],
            "rows_in_corpus": n, "status": "USED",
        })

    frame = pd.DataFrame(rows).sort_values(
        ["stream", "rows_in_corpus"], ascending=[True, False])
    emit("table11_dataset_provenance", frame,
         "Every data source considered, its licence, how many corpus rows it "
         "contributed, and whether it was used, registered, generated or rejected. The "
         "five rejected financial candidates are the evidence for limitation L-16.",
         "outputs/corpus/corpus_report.json, "
         "outputs/human_affect/01_dataset_registry/datasets.json, "
         "outputs/human_affect/16_financial_domain_transfer/transfer.json, "
         "research_artifacts/tables/table02_provenance.csv")


#: corpus_report source keys for the Stream A rows, so the join is explicit rather than
#: guessed from a string match that would silently produce zeros.
_SOURCE_KEY = {
    "NSE daily cash bhavcopy": "NSE_CASH_PANEL",
    "Synthetic episode text corpus": "AEGIS_TEXT_CORPUS",
}

#: Corpus keys with no registry entry of their own, because they are assembled here from
#: sources already listed above rather than acquired.
_EXTRA_SOURCE = {
    "AEGIS_MULTIMODAL_PANEL": (
        "market+text+image+audio+video",
        "repository licence (assembled from the sources above)"),
}


def t_fusion_comparison() -> None:
    """Fusion rules side by side, with the noise floor that decides the comparison."""
    fs = _json("outputs", "human_affect", "12_fusion_strategies",
               "fusion_strategies.json")
    if not fs:
        return skip("table12_fusion_comparison",
                    "run python scripts/run_fusion_strategies.py")
    floor = (fs.get("seed_noise_floor") or {}).get("noise_floor_95")
    best = max((s["balanced_accuracy_mean"] for s in fs["summary"]), default=0.0)
    rows = []
    for s in sorted(fs["summary"], key=lambda x: -x["balanced_accuracy_mean"]):
        gap = best - s["balanced_accuracy_mean"]
        rows.append({
            "strategy": s["strategy"],
            "balanced_accuracy": s["balanced_accuracy_mean"],
            "sd": s["balanced_accuracy_sd"],
            "ci_low": s["balanced_accuracy_ci_low"],
            "ci_high": s["balanced_accuracy_ci_high"],
            "ece": s["ece_mean"],
            "brier": s["brier_mean"],
            "gap_to_leader": gap,
            "gap_exceeds_noise_floor": bool(floor is not None and gap > floor),
        })
    frame = pd.DataFrame(rows)
    emit("table12_fusion_comparison", frame,
         "Fusion rules on one corpus, five seeds, leave-one-actor-out. The 95%% seed "
         "noise floor is %.4f balanced accuracy: the spread between the four real rules "
         "is %.4f, so no accuracy ordering among them is established. They separate on "
         "calibration, which is a different axis."
         % (floor or float("nan"),
            fs.get("spread_between_real_strategies") or float("nan")),
         "outputs/human_affect/12_fusion_strategies/fusion_strategies.json")


def t_statistical_significance() -> None:
    """Every comparison the study rests on, with the test that decided it.

    Two different decision rules appear here and mixing them up would be the easy error:
    the STATS track uses a paired cluster bootstrap with a Benjamini-Hochberg adjusted
    p-value, and the multimodal track uses a pooled-seed noise floor. The rule column says
    which one applies to each row.
    """
    rows: list[dict] = []

    ab = _csv("research_artifacts", "experiments", "ablation_statistics.csv")
    if ab is not None:
        top = ab.reindex(ab["delta_auprc"].abs().sort_values(ascending=False).index)
        for r in top.head(8).to_dict("records"):
            rows.append({
                "comparison": "%s (%s)" % (r["arm"], r["comparison"]),
                "track": "STATS", "metric": "AUPRC",
                "effect": r["delta_auprc"],
                "uncertainty": "95%% CI %.4f to %.4f" % (r["ci_low"], r["ci_high"]),
                "p_adjusted": "%.4f" % r["adjusted_p"],
                "decision_rule": "paired cluster bootstrap, BH-adjusted at 5%",
                "established": bool(r["significant_fdr_5pct"]),
            })

    ms = _json("outputs", "human_affect", "11_multimodal_multiseed", "multiseed.json")
    for tier, tv in ((ms or {}).get("tiers") or {}).items():
        floor = (tv.get("seed_noise_floor") or {}).get("noise_floor_95")
        rows.append({
            "comparison": "%s over %s (%s tier)"
                          % (tv.get("best_subset"), tv.get("best_unimodal"), tier),
            "track": "MULTIMODAL", "metric": "balanced accuracy",
            "effect": tv.get("multimodal_gain_over_best_unimodal"),
            "uncertainty": "pooled-seed sd %.4f"
                           % ((tv.get("seed_noise_floor") or {}).get("pooled_seed_sd")
                              or 0.0),
            "p_adjusted": "-",
            "decision_rule": "pooled-seed 95%% noise floor %.4f" % (floor or 0.0),
            "established": bool(tv.get("gain_exceeds_seed_noise_floor")),
        })

    fs = _json("outputs", "human_affect", "12_fusion_strategies",
               "fusion_strategies.json")
    if fs:
        floor = (fs.get("seed_noise_floor") or {}).get("noise_floor_95")
        rows.append({
            "comparison": "spread between the four fusion rules",
            "track": "MULTIMODAL", "metric": "balanced accuracy",
            "effect": fs.get("spread_between_real_strategies"),
            "uncertainty": "pooled-seed sd %.4f"
                           % ((fs.get("seed_noise_floor") or {}).get("pooled_seed_sd")
                              or 0.0),
            "p_adjusted": "-",
            "decision_rule": "pooled-seed 95%% noise floor %.4f" % (floor or 0.0),
            "established": bool(fs.get("spread_exceeds_noise_floor")),
        })

    rv = _json("outputs", "corpus", "real_vs_synthetic.json")
    if rv:
        v = rv.get("verdict") or {}
        rows.append({
            "comparison": "REAL + SYNTHETIC over REAL ONLY",
            "track": "CORPUS", "metric": "AUPRC",
            "effect": v.get("mean_difference"),
            "uncertainty": "seed noise floor %.5f" % (v.get("seed_noise_floor") or 0),
            "p_adjusted": "-",
            "decision_rule": "paired over %s seeds against a %.5f seed noise floor"
                             % (v.get("n_paired_seeds"), v.get("seed_noise_floor") or 0),
            "established": bool(v.get("synthetic_hurts")),
        })

    rb = _json("outputs", "human_affect", "13_multimodal_robustness", "robustness.json")
    if rb:
        clean = rb.get("clean_balanced_accuracy")
        by = {c["condition"]: c for c in rb.get("conditions") or []}
        for cond in ("missing_audio", "misaligned_audio", "misaligned_face"):
            c = by.get(cond)
            if not c:
                continue
            rows.append({
                "comparison": "%s against clean" % cond,
                "track": "MULTIMODAL", "metric": "balanced accuracy",
                "effect": -float(c["degradation"]),
                "uncertainty": "seed sd %.4f" % c["balanced_accuracy_sd"],
                "p_adjusted": "-",
                "decision_rule": "3 seeds, sd %.4f; degradation exceeds 3 sd"
                                 % c["balanced_accuracy_sd"],
                "established": bool(c["degradation"] > 3 * c["balanced_accuracy_sd"]),
            })
        rows.append({
            "comparison": "clean reference",
            "track": "MULTIMODAL", "metric": "balanced accuracy",
            "effect": clean, "uncertainty": "-", "p_adjusted": "-",
            "decision_rule": "reference level, not a comparison",
            "established": True,
        })

    if not rows:
        return skip("table13_statistical_significance", "no statistical artifact found")
    frame = pd.DataFrame(rows)
    emit("table13_statistical_significance", frame,
         "Every comparison the study's conclusions rest on, with the rule that decided "
         "it. Two rules are in use and are named per row: a BH-adjusted paired cluster "
         "bootstrap on the STATS track, and a pooled-seed noise floor on the multimodal "
         "and corpus tracks. `established` false means the data does not separate the "
         "arms, never that the arms are equal.",
         "research_artifacts/experiments/ablation_statistics.csv, "
         "outputs/human_affect/11_multimodal_multiseed/multiseed.json, "
         "outputs/human_affect/12_fusion_strategies/fusion_strategies.json, "
         "outputs/corpus/real_vs_synthetic.json, "
         "outputs/human_affect/13_multimodal_robustness/robustness.json")


# -- scenario lab ---------------------------------------------------------------------

def t_scenario_comparison() -> None:
    """Every condition beside its baseline, with the method that produced its rows."""
    frame = _csv("outputs", "scenario", "scenario_comparison.csv")
    if frame is None:
        return skip("table14_scenario_comparison",
                    "run python scripts/run_scenarios.py")
    keep = ["scenario_id", "name", "family", "simulation_method", "is_baseline",
            "n_rows", "risk_mean", "uncertainty_mean", "elevated_rate",
            "delta_risk_mean", "ci_low", "ci_high"]
    out = frame[[c for c in keep if c in frame.columns]].copy()
    emit("table14_scenario_comparison", out,
         "Every declared condition with the mean estimate it produced. The simulation "
         "method is the load-bearing column: an observed stratum selects rows that "
         "occurred, a counterfactual alters rows under a stated assumption and did not "
         "happen, and a policy comparison changes a declared rule on identical evidence. "
         "The baseline row is the reference the rest are differences from.",
         "outputs/scenario/scenario_comparison.csv")


def t_scenario_uncertainty() -> None:
    """Each difference with its interval, its test and the assumptions it rests on."""
    frame = _csv("outputs", "scenario", "scenario_uncertainty.csv")
    if frame is None:
        return skip("table15_scenario_uncertainty",
                    "run python scripts/run_scenarios.py")
    out = frame.copy()
    has = out["ci_low"].notna() & out["ci_high"].notna()
    out["reading"] = [
        "no sampling interval" if not h
        else ("established" if (lo > 0 or hi < 0) else "unresolved")
        for h, lo, hi in zip(has, out["ci_low"].fillna(0), out["ci_high"].fillna(0),
                             strict=False)
    ]
    keep = ["scenario_id", "family", "headline_metric", "estimate", "ci_low", "ci_high",
            "p_value", "reading", "interval_method", "n_assumptions"]
    emit("table15_scenario_uncertainty", out[[c for c in keep if c in out.columns]],
         "Scenario differences with their intervals. The headline quantity differs by "
         "row and is named: a difference in mean estimate, a difference in the daily "
         "tail loss, and a difference in the share of labelled-elevated value referred "
         "are three different things and are not comparable across rows. `unresolved` "
         "means the interval covers zero, never that the effect is absent.",
         "outputs/scenario/scenario_uncertainty.csv")


def t_scenario_money() -> None:
    """Currency figures, each with its notional, its interval and its caveat."""
    frame = _csv("outputs", "scenario", "scenario_money.csv")
    if frame is None:
        return skip("table16_scenario_money", "run python scripts/run_scenarios.py")
    keep = ["scenario_id", "family", "quantity", "amount_inr", "amount_ci_low_inr",
            "amount_ci_high_inr", "notional_inr", "coverage", "review_load_cases",
            "is_observed"]
    out = frame[[c for c in keep if c in frame.columns]].copy()
    emit("table16_scenario_money", out,
         "Every currency figure this project produces. All of them are simulated: a "
         "modelled difference in a tail statistic multiplied by a declared notional "
         "research base, or an accounting fact about a declared referral threshold on a "
         "synthetic fixture. `is_observed` is false on every row, because no "
         "intervention was performed and nothing was recovered.",
         "outputs/scenario/scenario_money.csv")


def t_transaction_provenance() -> None:
    """The five candidate transaction corpora and why each was set aside."""
    payload = _json("outputs", "scenario", "transaction_corpus_search.json")
    if not payload:
        return skip("table17_transaction_provenance",
                    "run python scripts/run_module.py --module SCENARIO-08")
    rows = []
    for c in payload.get("candidates", []):
        rows.append({
            "dataset_id": c["dataset_id"],
            "description": c["description"],
            "transaction_level": c["transaction_level"],
            "human_labels": c["human_labels"],
            "interpretable_features": c["interpretable_features"],
            "entity_id": c["entity_id"],
            "licence": c["licence"],
            "licence_machine_verifiable": c["licence_machine_verifiable"],
            "qualifies": c["qualifies"],
            "disqualifying_reason": c["disqualifying_reason"],
        })
    fixture = payload.get("fixture") or {}
    rows.append({
        "dataset_id": "AEGIS declared fixture",
        "description": "Synthetic development fixture generated by this project",
        "transaction_level": True, "human_labels": False,
        "interpretable_features": True, "entity_id": True,
        "licence": "repository licence (generated by this project)",
        "licence_machine_verifiable": True, "qualifies": False,
        "disqualifying_reason": (
            "labels are a declared function of the generated features (%d rows, %d "
            "accounts); it exercises the pipeline and is not evidence"
            % (fixture.get("n_rows", 0), fixture.get("n_accounts", 0))),
    })
    emit("table17_transaction_provenance", pd.DataFrame(rows),
         "Every transaction corpus considered, against the six requirements. None "
         "qualifies, so the transaction track executes on the declared fixture in the "
         "final row. The nearest miss is ULB Credit Card Fraud: licence-clear and "
         "label-clear, but its features are unnamed principal components, so no scenario "
         "assumption can be stated about any of them.",
         "outputs/scenario/transaction_corpus_search.json")


def main() -> int:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    progress.log("[paper tables]")
    t_dataset_composition()
    t_unimodal_and_multimodal()
    t_vlm_comparison()
    t_ablation()
    t_multiseed()
    t_calibration()
    t_robustness()
    t_synthetic()
    t_error_analysis()
    t_dataset_provenance()
    t_fusion_comparison()
    t_statistical_significance()
    t_scenario_comparison()
    t_scenario_uncertainty()
    t_scenario_money()
    t_transaction_provenance()

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "n_written": len(WRITTEN), "n_not_generated": len(SKIPPED),
        "tables": WRITTEN, "not_generated": SKIPPED,
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "tables.json", manifest)
    progress.log("wrote %d tables, %d not generated"
                 % (len(WRITTEN), len(SKIPPED)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
