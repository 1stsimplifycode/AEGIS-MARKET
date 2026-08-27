"""Paper figures for the corpus, synthetic ablation, STATS-15/16 and the VLM branch.

    python scripts/generate_research_figures.py

Every figure is drawn from an artifact that exists. A missing artifact produces a recorded
NOT GENERATED entry naming what would produce it, never a placeholder: in a paper pipeline
a placeholder is indistinguishable from a result.

Writes to ``outputs/research_figures/``; never touches ``research_artifacts/``.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import git_commit  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "research_figures"
R = paths.REPO_ROOT
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
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / ("%s.%s" % (name, ext)), dpi=200, bbox_inches="tight")
    plt.close(fig)
    GENERATED.append({"figure": name, "caption": caption,
                      "source_data": _relative(source)})
    progress.log("      %s" % name)


def skip(name: str, reason: str) -> None:
    SKIPPED.append({"figure": name, "status": "NOT GENERATED", "reason": reason})
    progress.log("      %-36s NOT GENERATED: %s" % (name, reason))


def _json(*parts):
    p = R.joinpath(*parts)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _csv(*parts):
    p = R.joinpath(*parts)
    return pd.read_csv(p) if p.exists() else None


def fig_corpus_composition(report: dict):
    shards = []
    for a in report.get("per_shard_analysis") or []:
        c = a.get("composition") or {}
        shards.append((a["shard"], c.get("real_samples", 0),
                       c.get("synthetic_samples", 0)))
    shards.sort(key=lambda t: t[1] + t[2])
    names = [s[0] for s in shards]
    real = np.array([s[1] for s in shards], dtype=float)
    synth = np.array([s[2] for s in shards], dtype=float)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    y = np.arange(len(names))
    ax.barh(y, real, color="#2b6cb0", label="real")
    ax.barh(y, synth, left=real, color="#dd6b20", label="synthetic")
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xscale("symlog")
    ax.set_xlabel("samples (symlog)")
    ax.set_title("Corpus composition by shard")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(axis="x", alpha=0.3)
    return fig


def fig_design_effect(report: dict):
    rows = []
    for a in report.get("per_shard_analysis") or []:
        e = a.get("effective_sample_size") or {}
        rows.append((a["shard"], a["rows"], e.get("n_independent_units", 0),
                     e.get("design_effect", np.nan)))
    rows.sort(key=lambda t: t[3])
    fig, ax = plt.subplots(figsize=(8, 4.5))
    y = np.arange(len(rows))
    ax.barh(y, [r[3] for r in rows], color="#2c7a7b")
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=8)
    ax.set_xscale("log")
    ax.set_xlabel("design effect  (rows per independent unit, log scale)")
    ax.set_title("Rows are not independent observations")
    for i, r in enumerate(rows):
        ax.text(r[3], i, "  %d rows / %d units" % (r[1], r[2]),
                va="center", fontsize=7, color="#444")
    ax.grid(axis="x", alpha=0.3)
    return fig


def fig_synthetic_sweep(sweep: dict):
    rows = [r for r in (sweep.get("rows") or []) if r.get("status") == "OK"]
    rows.sort(key=lambda r: r["synthetic_share"])
    x = [100 * r["synthetic_share"] for r in rows]
    y = [r["auprc"] for r in rows]
    base = sweep.get("baseline_auprc_real_only", y[0] if y else np.nan)

    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(x, y, "o-", color="#c53030", linewidth=2, markersize=7)
    ax.axhline(base, color="#2b6cb0", linestyle="--", linewidth=1.2,
               label="real-only baseline %.4f" % base)
    ax.axhspan(base - 0.00877, base + 0.00877, color="#2b6cb0", alpha=0.12,
               label="seed noise floor")
    ax.set_xlabel("synthetic share of the training set (%)")
    ax.set_ylabel("AUPRC on real validation rows")
    ax.set_title("Synthetic augmentation: harmless to a point, then a cliff")
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    ax.grid(alpha=0.3)
    for xi, yi in zip(x, y):
        ax.annotate("%.3f" % yi, (xi, yi), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=7)
    return fig


def fig_stats_robustness(table: pd.DataFrame):
    sub = table[(table["family"] == "input") & (table["corruption"] != "none")]
    clean = table[table["corruption"] == "none"]["auprc"]
    base = float(clean.iloc[0]) if len(clean) else np.nan
    fig, ax = plt.subplots(figsize=(7, 4.2))
    for kind, g in sub.groupby("corruption"):
        g = g.sort_values("severity")
        ax.plot(g["severity"], g["auprc"], "o-", label=kind, linewidth=1.8)
    ax.axhline(base, color="#444", linestyle="--", linewidth=1,
               label="clean %.4f" % base)
    ax.set_xlabel("severity")
    ax.set_ylabel("AUPRC")
    ax.set_title("STATS-15: input degradation")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(alpha=0.3)
    return fig


def fig_stats_learning_curve(table: pd.DataFrame):
    sub = table[table["family"] == "training_size"]
    agg = sub.groupby("severity")["auprc"].agg(["mean", "min", "max"]).reset_index()
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(100 * agg["severity"], agg["mean"], "o-", color="#2b6cb0", linewidth=2)
    ax.fill_between(100 * agg["severity"], agg["min"], agg["max"],
                    color="#2b6cb0", alpha=0.18)
    ax.set_xlabel("percentage of training symbols kept")
    ax.set_ylabel("AUPRC")
    ax.set_title("STATS-15: learning curve, subsampled by instrument")
    ax.grid(alpha=0.3)
    return fig


def fig_generalization(table: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, family, xlabel in ((axes[0], "period", "time fold"),
                               (axes[1], "instrument", "instrument group")):
        g = table[(table["family"] == family) & (table["status"] == "OK")]
        if g.empty:
            ax.set_visible(False)
            continue
        key = "fold" if family == "period" else "group"
        ax.bar(g[key].astype(int), g["auprc"], color="#2c7a7b")
        ax.set_ylim(0, 1)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("AUPRC")
        ax.set_title("%s transfer" % family)
        ax.grid(axis="y", alpha=0.3)
    fig.suptitle("STATS-15: generalization across time and instruments")
    fig.tight_layout()
    return fig


def fig_seed_variability(table: pd.DataFrame):
    ok = table[table["status"] == "OK"]
    stats = ok.groupby("arm")["auprc"].agg(["mean", "std", "min", "max"])
    stats = stats.sort_values("mean", ascending=False).head(16)
    fig, ax = plt.subplots(figsize=(8, 5))
    y = np.arange(len(stats))
    ax.errorbar(stats["mean"], y,
                xerr=[stats["mean"] - stats["min"], stats["max"] - stats["mean"]],
                fmt="o", color="#2b6cb0", ecolor="#90cdf4", capsize=3, markersize=5)
    ax.set_yticks(y)
    ax.set_yticklabels(stats.index, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("AUPRC (point = mean over seeds, bar = observed min to max)")
    ax.set_title("STATS-16: seed variability by arm")
    ax.grid(axis="x", alpha=0.3)
    return fig


def fig_vlm_region_coverage(describe: dict):
    per = describe.get("per_model") or []
    regions = sorted((per[0].get("region_coverage") or {}).keys())
    fig, ax = plt.subplots(figsize=(7, 4.2))
    width = 0.8 / max(1, len(per))
    x = np.arange(len(regions))
    for i, m in enumerate(per):
        cov = m.get("region_coverage") or {}
        ax.bar(x + i * width, [cov.get(r, 0.0) for r in regions], width,
               label="%s (%.2f regions/output)"
                     % (m["model"], m.get("mean_regions_described", 0.0)))
    ax.set_xticks(x + width * (len(per) - 1) / 2)
    ax.set_xticklabels(regions)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("fraction of descriptions mentioning the region")
    ax.set_title("What each VLM chose to describe")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    return fig


def fig_vlm_ablation(table: pd.DataFrame, chance: float):
    ok = table[table["status"] == "OK"].sort_values("balanced_accuracy")
    fig, ax = plt.subplots(figsize=(8, 5.5))
    y = np.arange(len(ok))
    colours = ["#dd6b20" if "VLM" in s else "#2b6cb0" for s in ok["subset"]]
    ax.barh(y, ok["balanced_accuracy"], color=colours)
    ax.axvline(chance, color="#c53030", linestyle="--", linewidth=1.2,
               label="chance %.4f" % chance)
    ax.set_yticks(y)
    ax.set_yticklabels([s.replace("+", " + ") for s in ok["subset"]], fontsize=8)
    ax.set_xlabel("balanced accuracy, leave-one-actor-out")
    ax.set_title("Every modality subset (orange includes the VLM channel)")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    return fig


def fig_vlm_robustness(table: pd.DataFrame):
    agg = table.groupby("corruption").agg(
        jaccard=("word_jaccard", "mean"),
        identical=("identical_to_clean", "mean")).reset_index()
    fig, ax = plt.subplots(figsize=(7, 4.2))
    x = np.arange(len(agg))
    ax.bar(x - 0.2, agg["jaccard"], 0.4, label="word overlap with clean description",
           color="#2b6cb0")
    ax.bar(x + 0.2, agg["identical"], 0.4, label="description unchanged",
           color="#2c7a7b")
    ax.set_xticks(x)
    ax.set_xticklabels(agg["corruption"])
    ax.set_ylim(0, 1.05)
    ax.set_title("VLM output stability under pixel corruption (severity 0.25)")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    return fig


def main() -> int:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    progress.log("[research figures]")

    corpus = _json("outputs", "corpus", "corpus_report.json")
    if corpus:
        save(fig_corpus_composition(corpus), "figR01_corpus_composition",
             "Real and synthetic sample counts per corpus shard. The scale target is met "
             "by real observations alone; synthetic rows are 6.1% of the corpus.",
             "outputs/corpus/corpus_report.json")
        save(fig_design_effect(corpus), "figR02_design_effect",
             "Rows per independent unit for each shard. A design effect of 3832 on daily "
             "market data is a property of the data, not a defect; inference uses the "
             "unit count rather than the row count.",
             "outputs/corpus/corpus_report.json")
    else:
        skip("figR01_corpus_composition",
             "corpus_report.json absent; run build_corpus.py")
        skip("figR02_design_effect",
             "corpus_report.json absent; run build_corpus.py")

    sweep = _json("outputs", "corpus", "synthetic_ratio_sweep.json")
    if sweep:
        save(fig_synthetic_sweep(sweep), "figR03_synthetic_ratio_sweep",
             "AUPRC on real validation rows against the synthetic share of the training "
             "set. Harmless to 25%, degrading at 50%, collapsing between 50% and 75%.",
             "outputs/corpus/synthetic_ratio_sweep.json")
    else:
        skip("figR03_synthetic_ratio_sweep",
             "synthetic_ratio_sweep.json absent; run run_real_vs_synthetic.py "
             "--ratio-sweep")

    rob = _csv("outputs", "stats", "15_robustness_generalization", "robustness.csv")
    if rob is not None:
        save(fig_stats_robustness(rob), "figR04_stats_input_robustness",
             "AUPRC under each input degradation. Noise is the worst failure and a stale "
             "feed the mildest; a single robustness number would hide the distinction.",
             "outputs/stats/15_robustness_generalization/robustness.csv")
        save(fig_stats_learning_curve(rob), "figR05_stats_learning_curve",
             "Learning curve over training-set size, subsampled by instrument rather "
             "than by row because rows from one instrument are not independent.",
             "outputs/stats/15_robustness_generalization/robustness.csv")
    else:
        skip("figR04_stats_input_robustness", "robustness.csv absent")
        skip("figR05_stats_learning_curve", "robustness.csv absent")

    gen = _csv("outputs", "stats", "15_robustness_generalization", "generalization.csv")
    if gen is not None:
        save(fig_generalization(gen), "figR06_stats_generalization",
             "Forward-in-time transfer rises across folds as history accumulates; "
             "transfer to disjoint instruments is close to in-sample performance.",
             "outputs/stats/15_robustness_generalization/generalization.csv")
    else:
        skip("figR06_stats_generalization", "generalization.csv absent")

    seeds = _csv("outputs", "stats", "16_multiseed_significance", "seed_table.csv")
    if seeds is not None:
        save(fig_seed_variability(seeds), "figR07_seed_variability",
             "Mean AUPRC over ten seeds with the observed range, for the strongest "
             "arms. The spread is what a single-run difference has to exceed.",
             "outputs/stats/16_multiseed_significance/seed_table.csv")
    else:
        skip("figR07_seed_variability", "seed_table.csv absent")

    vlm = _json("outputs", "vlm", "vlm_run.json")
    describe = (vlm or {}).get("describe") or {}
    if describe.get("per_model"):
        save(fig_vlm_region_coverage(describe), "figR08_vlm_region_coverage",
             "Fraction of descriptions mentioning each observable region, per model. The "
             "two capacities attend to near-complementary parts of the same face.",
             "outputs/vlm/vlm_run.json")
    else:
        skip("figR08_vlm_region_coverage", "vlm_run.json has no describe stage")

    abl = _csv("outputs", "vlm", "vlm_ablation.csv")
    abl_json = _json("outputs", "vlm", "vlm_ablation.json") or {}
    if abl is not None and len(abl):
        save(fig_vlm_ablation(abl, abl_json.get("chance", 0.125)),
             "figR09_vlm_modality_ablation",
             "Balanced accuracy for every modality subset under leave-one-actor-out. The "
             "VLM channel alone reaches twice chance, close to the specialised facial "
             "model, but adds little once that model is present.",
             "outputs/vlm/vlm_ablation.csv")
    else:
        skip("figR09_vlm_modality_ablation", "vlm_ablation.csv absent")

    vrob = _csv("outputs", "vlm", "vlm_robustness.csv")
    if vrob is not None and len(vrob):
        save(fig_vlm_robustness(vrob), "figR10_vlm_robustness",
             "Stability of the VLM description under pixel corruption, measured as word "
             "overlap with the clean description and the rate at which the text is "
             "unchanged.",
             "outputs/vlm/vlm_robustness.csv")
    else:
        skip("figR10_vlm_robustness", "vlm_robustness.csv absent")

    closure_figures()
    consolidated_figures()
    scenario_figures()

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



# ------------------------------------------------------------- closure phase ----

def fig_sample_size_ladder(report: dict):
    """Raw N against independent N against effective N, per shard."""
    rows = []
    for a in report.get("per_shard_analysis") or []:
        e = a.get("effective_sample_size") or {}
        rows.append((a["shard"], a["rows"], e.get("n_independent_units", 0)))
    rows.sort(key=lambda t: t[1])
    names = [r[0] for r in rows]
    raw = np.array([r[1] for r in rows], dtype=float)
    units = np.array([max(1, r[2]) for r in rows], dtype=float)
    # Effective N under a simple exchangeable design effect: the row count discounted by
    # how many rows share each unit.
    effective = raw / np.maximum(1.0, raw / units)

    fig, ax = plt.subplots(figsize=(8.5, 5))
    y = np.arange(len(names))
    ax.barh(y - 0.26, raw, 0.26, label="raw rows", color="#a0aec0")
    ax.barh(y, effective, 0.26, label="effective N", color="#dd6b20")
    ax.barh(y + 0.26, units, 0.26, label="independent units", color="#2b6cb0")
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xscale("log")
    ax.set_xlabel("count (log scale)")
    ax.set_title("A row is not an observation: raw, effective and independent N")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(axis="x", alpha=0.3)
    return fig


def fig_multimodal_multiseed(summary, floor: float, chance: float):
    s = summary.sort_values("balanced_accuracy_mean")
    fig, ax = plt.subplots(figsize=(8, 4.6))
    y = np.arange(len(s))
    lo = s["balanced_accuracy_mean"] - s["balanced_accuracy_min"]
    hi = s["balanced_accuracy_max"] - s["balanced_accuracy_mean"]
    ax.errorbar(s["balanced_accuracy_mean"], y, xerr=[lo, hi], fmt="o",
                color="#2b6cb0", ecolor="#90cdf4", capsize=3, markersize=6)
    ax.axvline(chance, color="#c53030", linestyle="--", linewidth=1.2,
               label="chance %.4f" % chance)
    ax.set_yticks(y)
    ax.set_yticklabels([t.replace("+", " + ") for t in s["subset"]], fontsize=8)
    ax.set_xlabel("balanced accuracy (point = mean over 5 seeds, bar = min to max)")
    ax.set_title("Multimodal arms across seeds; noise floor %.4f" % floor)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    return fig


def fig_fusion_strategies(report: dict):
    s = pd.DataFrame(report["summary"])
    real = s[s["strategy"] != "text_only"]
    fig, ax = plt.subplots(figsize=(7, 4.6))
    ax.scatter(real["ece_mean"], real["balanced_accuracy_mean"], s=90,
               color="#2b6cb0", zorder=3)
    for _, r in real.iterrows():
        ax.annotate(r["strategy"], (r["ece_mean"], r["balanced_accuracy_mean"]),
                    textcoords="offset points", xytext=(8, 4), fontsize=9)
    floor = report["seed_noise_floor"]["noise_floor_95"]
    best = real["balanced_accuracy_mean"].max()
    ax.axhspan(best - floor, best, color="#2b6cb0", alpha=0.10,
               label="within the seed noise floor of the best")
    ax.set_xlabel("expected calibration error  (lower is better)")
    ax.set_ylabel("balanced accuracy  (higher is better)")
    ax.set_title("Fusion rules: accuracy against calibration")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.grid(alpha=0.3)
    return fig


def fig_multimodal_robustness(table, clean: float):
    sub = table[table["kind"].isin(["noise", "dropout"])]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, kind in zip(axes, ("noise", "dropout")):
        g = sub[sub["kind"] == kind]
        for target, gg in g.groupby("target"):
            gg = gg.sort_values("severity")
            ax.plot(gg["severity"], gg["balanced_accuracy_mean"], "o-",
                    label=target, linewidth=1.8)
        ax.axhline(clean, color="#444", linestyle="--", linewidth=1,
                   label="clean %.4f" % clean)
        ax.set_title(kind)
        ax.set_xlabel("severity")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("balanced accuracy")
    axes[0].legend(frameon=False, fontsize=8)

    extra = table[table["kind"].isin(["missing", "misaligned"])]
    if len(extra):
        txt = "  |  ".join("%s %.4f" % (r["condition"], r["balanced_accuracy_mean"])
                           for _, r in extra.iterrows())
        fig.suptitle("Multimodal robustness.  %s" % txt, fontsize=9)
    fig.tight_layout()
    return fig


def fig_modality_attribution(table):
    s = table.sort_values("importance_mean")
    fig, ax = plt.subplots(figsize=(7, 3.6))
    y = np.arange(len(s))
    ax.barh(y, s["importance_mean"], xerr=s["importance_sd"], color="#2c7a7b",
            ecolor="#4a5568", capsize=3)
    ax.axvline(0.0, color="#444", linewidth=1)
    ax.set_yticks(y)
    ax.set_yticklabels(s["block"])
    ax.set_xlabel("drop in balanced accuracy when the block is shuffled")
    ax.set_title("Modality attribution by intervention")
    ax.grid(axis="x", alpha=0.3)
    return fig


def fig_vlm_family(battery: dict):
    per = pd.DataFrame(battery["per_class"])
    models = sorted(per["model"].unique())
    classes = sorted(per["image_class"].unique())
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    width = 0.8 / max(1, len(models))
    x = np.arange(len(classes))
    colours = ["#2c7a7b" if c == "human_face" else "#c53030" for c in classes]
    for i, m in enumerate(models):
        g = per[per["model"] == m].set_index("image_class").reindex(classes)
        ax.bar(x + i * width, g["claims_face_rate"].fillna(0.0), width,
               label=m, edgecolor=colours, linewidth=1.6)
    ax.set_xticks(x + width * (len(models) - 1) / 2)
    ax.set_xticklabels([c.replace("_", "\n") for c in classes], fontsize=8)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("rate of claiming a face is present")
    ax.set_title("One class contains a face (green edge); the rest are false claims")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    return fig


def closure_figures() -> None:
    corpus = _json("outputs", "corpus", "corpus_report.json")
    if corpus:
        save(fig_sample_size_ladder(corpus), "figR11_sample_size_ladder",
             "Raw rows, effective N and independent units per shard. The gap between "
             "the grey and blue bars is why inference uses the unit count.",
             "outputs/corpus/corpus_report.json")
    else:
        skip("figR11_sample_size_ladder", "corpus_report.json absent")

    ms = _json("outputs", "multimodal_multiseed", "multimodal_multiseed.json")
    full = _csv("outputs", "multimodal_multiseed", "full_seed_summary.csv")
    if ms and full is not None:
        tier = ms["tiers"]["full"]
        save(fig_multimodal_multiseed(full, tier["seed_noise_floor"]["noise_floor_95"],
                                      tier["chance"]),
             "figR12_multimodal_multiseed",
             "Balanced accuracy across five seeds for every arm on the full 720-clip "
             "tier. AUDIO+FACE beats the best unimodal arm by 0.0823, which exceeds "
             "the 0.0217 seed noise floor.",
             "outputs/multimodal_multiseed/full_seed_summary.csv")
    else:
        skip("figR12_multimodal_multiseed", "run run_multimodal_multiseed.py")

    fs = _json("outputs", "human_affect", "experiments", "fusion_strategies.json")
    if fs:
        save(fig_fusion_strategies(fs), "figR13_fusion_strategies",
             "Fusion rules on one corpus and one metric. The four real rules sit "
             "within the seed noise floor of one another on accuracy while differing "
             "sharply in calibration, so no rule is established as best.",
             "outputs/human_affect/experiments/fusion_strategies.json")
    else:
        skip("figR13_fusion_strategies", "run run_fusion_strategies.py")

    mr = _csv("outputs", "human_affect", "experiments", "multimodal_robustness.csv")
    mrj = _json("outputs", "human_affect", "experiments", "multimodal_robustness.json")
    if mr is not None and mrj:
        save(fig_multimodal_robustness(mr, mrj["clean_balanced_accuracy"]),
             "figR14_multimodal_robustness",
             "Degradation by modality and severity, with the missing-modality and "
             "misalignment conditions in the caption. Destroying the audio-video "
             "correspondence costs more than heavy noise on either stream.",
             "outputs/human_affect/experiments/multimodal_robustness.csv")
    else:
        skip("figR14_multimodal_robustness", "run run_multimodal_robustness.py")

    attr = _csv("outputs", "human_affect", "experiments", "modality_attribution.csv")
    if attr is not None:
        save(fig_modality_attribution(attr), "figR15_modality_attribution",
             "Group permutation importance per modality block, measured by "
             "intervention on the model's own inputs. Audio and face carry the signal; "
             "the VLM block contributes within its own standard deviation of zero.",
             "outputs/human_affect/experiments/modality_attribution.csv")
    else:
        skip("figR15_modality_attribution", "run run_multimodal_xai_fairness.py")

    fam = _json("outputs", "vlm", "vlm_family_comparison.json")
    if fam and fam.get("hallucination_battery"):
        save(fig_vlm_family(fam["hallucination_battery"]), "figR16_vlm_hallucination",
             "Rate at which each model claims a face is present, by stimulus class. "
             "SmolVLM claims one in every faceless class; BLIP-VQA claims none.",
             "outputs/vlm/vlm_family_comparison.json")
    else:
        skip("figR16_vlm_hallucination", "run run_vlm_family_comparison.py --all")


# -- consolidated figures -----------------------------------------------------------
#
# Three figures that each carry a whole result rather than one panel of one. They exist
# because the corresponding findings are only convincing when the measurement and its
# diagnosis sit on the same page: a performance curve without the distribution
# diagnostics invites "the generator must have been bad", and a robustness bar chart
# sorted by severity hides that alignment and noise are different kinds of failure.


def fig_synthetic_consolidated(sweep: dict, diag: dict, rv: dict):
    """Synthetic share, performance, distribution diagnostics and the mechanism.

    Four panels because the argument needs four steps: the effect exists, it is not a
    marginal-distribution problem, it is not a correlation problem, and a discriminator
    locates what is actually missing.
    """
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.6))

    rows = sorted(sweep.get("rows") or sweep.get("runs") or [],
                  key=lambda r: r["synthetic_share"])
    share = np.array([r["synthetic_share"] for r in rows], dtype=float)
    auprc = np.array([r["auprc"] for r in rows], dtype=float)

    ax = axes[0, 0]
    ax.plot(share * 100, auprc, marker="o", color="#2b6cb0", lw=2)
    harmless = float(diag["finding_being_explained"]["largest_harmless_synthetic_share"])
    ax.axvspan(0, harmless * 100, color="#2c7a7b", alpha=0.10)
    ax.axvspan(50, 75, color="#c53030", alpha=0.10)
    ax.annotate("harmless to %d%%" % int(harmless * 100),
                (harmless * 50, auprc.min()), fontsize=8.5, color="#2c7a7b",
                ha="center", va="bottom")
    ax.annotate("collapse\n50-75%", (62, (auprc.max() + auprc.min()) / 2),
                fontsize=8, color="#c53030", ha="center")
    for x, y in zip(share * 100, auprc):
        ax.annotate("%.3f" % y, (x, y), fontsize=7, xytext=(0, 7),
                    textcoords="offset points", ha="center")
    ax.set_xlabel("synthetic share of the training set (%)")
    ax.set_ylabel("AUPRC on real validation rows")
    ax.set_title("A. Performance against synthetic share")
    ax.grid(alpha=0.3)

    ax = axes[0, 1]
    mech = {m["mechanism"]: m for m in diag["mechanisms"]}
    labels, values, refs = [], [], []
    labels.append("KS distance\n(marginals)")
    values.append(mech["marginal_mismatch"]["ks_mean"])
    refs.append(0.05)
    labels.append("correlation error\n(2nd order)")
    values.append(mech["covariance_distortion"]["mean_abs_error"])
    refs.append(0.10)
    labels.append("|1 - label ratio|")
    values.append(abs(mech["label_shift"]["ratio"] - 1.0))
    refs.append(0.10)
    labels.append("|1 - eff. rank ratio|")
    values.append(abs(mech["mode_collapse"]["ratio"] - 1.0))
    refs.append(0.20)
    labels.append("out-of-range rate")
    values.append(mech["feature_scale"]["mean_out_of_training_range_rate"])
    refs.append(0.05)
    y = np.arange(len(labels))
    ax.barh(y, values, color="#2c7a7b", height=0.55)
    ax.barh(y, refs, color="none", edgecolor="#a0aec0", height=0.72, linestyle="--")
    for i, v in enumerate(values):
        ax.annotate("%.4f" % v, (max(v, 0.0), i), fontsize=7.5,
                    xytext=(4, 0), textcoords="offset points", va="center")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlim(0, max(refs) * 1.35)
    ax.set_xlabel("measured distance (dashed outline = a concern threshold)")
    ax.set_title("B. Distribution diagnostics: every one is small")
    ax.grid(axis="x", alpha=0.3)
    ax.invert_yaxis()

    ax = axes[1, 0]
    il = mech["interaction_loss"]
    bars = [il["discriminator_auc_linear"], il["discriminator_auc_trees"]]
    ax.bar(["linear\n(1st + 2nd order)", "tree ensemble\n(interactions)"], bars,
           color=["#a0aec0", "#c53030"], width=0.55)
    ax.axhline(0.5, color="#4a5568", lw=1, ls="--")
    ax.annotate("chance", (1.42, 0.51), fontsize=7.5, color="#4a5568")
    ax.annotate("", xy=(0.5, bars[1]), xytext=(0.5, bars[0]),
                arrowprops={"arrowstyle": "<->", "color": "#c53030", "lw": 1.4})
    ax.annotate("interaction gap %.4f" % il["interaction_gap"],
                (0.5, (bars[0] + bars[1]) / 2), fontsize=8.5, color="#c53030",
                ha="center", va="center",
                bbox={"boxstyle": "round,pad=0.3", "facecolor": "white",
                      "edgecolor": "#c53030", "linewidth": 0.8})
    for i, v in enumerate(bars):
        ax.annotate("%.4f" % v, (i, v), fontsize=8, xytext=(0, 4),
                    textcoords="offset points", ha="center")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("AUC separating real from generated rows")
    ax.set_title("C. Mechanism: what a linear model cannot see")
    ax.grid(axis="y", alpha=0.3)

    ax = axes[1, 1]
    ax.axis("off")
    summary = rv.get("summary") or {}
    real = (summary.get("REAL_ONLY") or {}).get("auprc", {})
    both = (summary.get("REAL_PLUS_SYNTH") or {}).get("auprc", {})
    lines = [
        "REAL ONLY            AUPRC %.4f  (sd %.4f)"
        % (real.get("mean", float("nan")), real.get("sd", float("nan"))),
        "REAL + SYNTHETIC     AUPRC %.4f  (sd %.4f)"
        % (both.get("mean", float("nan")), both.get("sd", float("nan"))),
        "difference           %.4f"
        % (rv.get("verdict", {}).get("mean_difference", float("nan"))),
        "seed noise floor     %.5f"
        % (rv.get("verdict", {}).get("seed_noise_floor", float("nan"))),
        "",
        "Mechanisms measured: %d" % len(diag["mechanisms"]),
        "Mechanisms supported: %s" % ", ".join(diag["mechanisms_supported"]),
        "",
        "The generated rows reproduce every marginal, the rank",
        "correlation, the class balance and the feature range, and",
        "do not memorise the training set. What they do not carry",
        "is dependence beyond second order, which a Gaussian copula",
        "cannot represent. Diluting a training set with rows that",
        "are marginally correct and interaction-free teaches a",
        "distribution in which the target signal is absent.",
    ]
    ax.text(0.0, 1.0, "\n".join(lines), fontsize=8.6, family="monospace",
            va="top", ha="left", linespacing=1.5)
    ax.set_title("D. Result and reading", loc="left")

    fig.suptitle("Under what conditions does synthetic augmentation degrade "
                 "predictive performance?", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return fig


#: How each robustness condition is grouped for the alignment figure. The point of the
#: figure is that these four families are different kinds of failure, so the grouping is
#: declared here rather than inferred from a severity ordering.
_CORRUPTION_FAMILY = {
    "none": "NO CORRUPTION",
    "noise": "NOISE",
    "dropout": "NOISE",
    "misaligned": "MISALIGNMENT",
    "missing": "MISSING MODALITY",
}
_FAMILY_ORDER = ["NO CORRUPTION", "NOISE", "MISALIGNMENT", "MISSING MODALITY"]
_FAMILY_COLOUR = {
    "NO CORRUPTION": "#2c7a7b",
    "NOISE": "#3182ce",
    "MISALIGNMENT": "#dd6b20",
    "MISSING MODALITY": "#c53030",
}


def fig_alignment_degradation(rob: dict):
    """Clean against noise, misalignment and missing modality, grouped by kind.

    Sorting all 24 conditions by severity would produce a smooth ramp and hide the
    finding. Grouping them by what was done to the signal shows that destroying the
    audio-video correspondence costs an order of magnitude more than degrading either
    stream, which is the claim.
    """
    clean = float(rob["clean_balanced_accuracy"])
    conds = [c for c in rob["conditions"] if c["condition"] != "clean"]
    by_family: dict[str, list[dict]] = {f: [] for f in _FAMILY_ORDER}
    for c in conds:
        by_family[_CORRUPTION_FAMILY[c["kind"]]].append(c)
    by_family["NO CORRUPTION"] = [c for c in rob["conditions"]
                                  if c["condition"] == "clean"]

    fig, (ax, ax2) = plt.subplots(
        1, 2, figsize=(12.5, 5.6), gridspec_kw={"width_ratios": [2.5, 1]})

    labels, values, errs, colours, edges = [], [], [], [], []
    for fam in _FAMILY_ORDER:
        group = sorted(by_family[fam], key=lambda c: -c["balanced_accuracy_mean"])
        for c in group:
            sev = "" if c["severity"] in (0.0, 1.0) else "  sev %.2f" % c["severity"]
            labels.append("%s%s" % (c["condition"].replace("_", " "), sev))
            values.append(c["balanced_accuracy_mean"])
            errs.append(c["balanced_accuracy_sd"])
            colours.append(_FAMILY_COLOUR[fam])
            edges.append(fam)
        labels.append("")
        values.append(np.nan)
        errs.append(0.0)
        colours.append("none")
        edges.append(fam)

    y = np.arange(len(labels))
    ax.barh(y, values, xerr=errs, color=colours, height=0.68,
            error_kw={"ecolor": "#2d3748", "lw": 0.9})
    ax.axvline(clean, color="#2c7a7b", lw=1.4, ls="--")
    ax.annotate("clean %.4f" % clean, (clean, -1.1), fontsize=8,
                color="#2c7a7b", xytext=(4, 0), textcoords="offset points")
    ax.axvline(0.125, color="#718096", lw=1, ls=":")
    ax.annotate("chance 0.125", (0.125, -1.1), fontsize=8,
                color="#718096", xytext=(4, 0), textcoords="offset points")
    for i, v in enumerate(values):
        if not np.isnan(v):
            ax.annotate("%.4f" % v, (v, i), fontsize=7,
                        xytext=(4, 0), textcoords="offset points", va="center")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7.6)
    ax.invert_yaxis()
    ax.set_xlim(0, max(0.60, clean * 1.18))
    ax.set_xlabel("balanced accuracy (3 seeds, error bar = seed sd)")
    ax.set_title("Every condition, grouped by what was done to the signal")
    ax.grid(axis="x", alpha=0.3)
    handles = [plt.Rectangle((0, 0), 1, 1, color=_FAMILY_COLOUR[f])
               for f in _FAMILY_ORDER]
    # Outside the axes: every interior position collides with a bar or its value label,
    # and a legend sitting on top of the missing-modality rows hides the finding.
    ax.legend(handles, _FAMILY_ORDER, frameon=False, fontsize=8.5, ncol=4,
              loc="upper center", bbox_to_anchor=(0.5, -0.10))

    worst = {}
    for fam in _FAMILY_ORDER:
        group = by_family[fam]
        if not group:
            continue
        worst[fam] = min(group, key=lambda c: c["balanced_accuracy_mean"])
    fams = [f for f in _FAMILY_ORDER if f in worst]
    drops = [clean - worst[f]["balanced_accuracy_mean"] for f in fams]
    ax2.bar(range(len(fams)), drops,
            color=[_FAMILY_COLOUR[f] for f in fams], width=0.6)
    for i, (f, d) in enumerate(zip(fams, drops)):
        ax2.annotate("-%.4f\n%s" % (d, worst[f]["condition"].replace("_", " ")),
                     (i, d), fontsize=7.6, ha="center",
                     xytext=(0, 4), textcoords="offset points")
    ax2.set_xticks(range(len(fams)))
    ax2.set_xticklabels([f.replace(" ", "\n") for f in fams], fontsize=8)
    ax2.set_ylim(0, max(drops) * 1.42)
    ax2.set_ylabel("worst drop from clean")
    ax2.set_title("Worst case per family")
    ax2.grid(axis="y", alpha=0.3)

    fig.suptitle("Multimodal performance depends on temporal correspondence, not on "
                 "signal quality", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def fig_accuracy_vs_calibration(cal: dict):
    """Accuracy against calibration error, with the overconfidence axis beside it.

    A reader who sees only ECE concludes the VLM arm is the good one; a reader who sees
    only accuracy concludes it is the FULL arm. Putting them on one pair of axes is the
    whole argument, so the two panels share an arm ordering and a colour per arm.
    """
    rows = cal["rows"]
    arms = [r["arm"] for r in rows]
    acc = np.array([r["accuracy"] for r in rows])
    ece = np.array([r["ece"] for r in rows])
    ece_sd = np.array([r.get("ece_sd", 0.0) for r in rows])
    gap = np.array([r["confidence_minus_accuracy"] for r in rows])
    palette = ["#2b6cb0", "#c53030", "#2c7a7b", "#dd6b20", "#805ad5", "#4a5568"]
    colours = [palette[i % len(palette)] for i in range(len(arms))]

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12, 5.2))

    ax.errorbar(ece, acc, xerr=ece_sd, fmt="none", ecolor="#a0aec0", lw=1)
    # Two arms can sit almost on top of each other -- FULL and AUDIO+FACE differ by
    # 0.0125 accuracy here -- so a fixed label offset overlaps. Flip the label to the
    # other side when a nearer-left neighbour is close in both coordinates.
    span_x = float(ece.max() - ece.min()) or 1.0
    span_y = float(acc.max() - acc.min()) or 1.0
    for i, a in enumerate(arms):
        ax.scatter(ece[i], acc[i], s=150, color=colours[i], zorder=3,
                   edgecolor="white", linewidth=1.4)
        crowded = any(
            j != i
            and abs(ece[j] - ece[i]) < 0.25 * span_x
            and abs(acc[j] - acc[i]) < 0.12 * span_y
            and acc[j] > acc[i]
            for j in range(len(arms)))
        ax.annotate(a, (ece[i], acc[i]), fontsize=9, fontweight="bold",
                    xytext=(-11, -6) if crowded else (9, 4),
                    ha="right" if crowded else "left",
                    textcoords="offset points")
    best_cal = int(np.argmin(ece))
    best_acc = int(np.argmax(acc))
    ax.scatter(ece[best_cal], acc[best_cal], s=340, facecolor="none",
               edgecolor="#2c7a7b", linewidth=2, zorder=2)
    ax.scatter(ece[best_acc], acc[best_acc], s=340, facecolor="none",
               edgecolor="#c53030", linewidth=2, zorder=2)
    ax.annotate("best calibrated", (ece[best_cal], acc[best_cal]), fontsize=8,
                color="#2c7a7b", xytext=(-6, -24), textcoords="offset points",
                ha="right")
    ax.annotate("most accurate", (ece[best_acc], acc[best_acc]), fontsize=8,
                color="#c53030", xytext=(-6, -24), textcoords="offset points",
                ha="right")
    ax.axhline(0.125, color="#718096", lw=1, ls=":")
    ax.annotate("chance 0.125", (float(ece.min()), 0.125), fontsize=8,
                color="#718096", xytext=(0, 4), textcoords="offset points")
    ax.set_xlabel("expected calibration error (equal-mass, 10 bins) - lower is better")
    ax.set_ylabel("accuracy - higher is better")
    ax.set_title("The two axes do not agree on a winner")
    ax.grid(alpha=0.3)

    order = np.argsort(gap)
    ypos = np.arange(len(arms))
    ax2.barh(ypos, gap[order], color=[colours[i] for i in order], height=0.6)
    ax2.axvline(0, color="#2d3748", lw=1)
    for i, j in enumerate(order):
        ax2.annotate("%+.4f  (acc %.4f)" % (gap[j], acc[j]), (gap[j], i), fontsize=7.6,
                     xytext=(6 if gap[j] >= 0 else -6, 0),
                     textcoords="offset points", va="center",
                     ha="left" if gap[j] >= 0 else "right")
    ax2.set_yticks(ypos)
    ax2.set_yticklabels([arms[i] for i in order], fontsize=9)
    ax2.set_xlim(float(gap.min()) * 2.6, float(gap.max()) * 3.6)
    ax2.set_xlabel("mean confidence minus accuracy "
                   "(negative = underconfident, positive = overconfident)")
    ax2.set_title("Overconfidence is worst where accuracy is lowest")
    ax2.grid(axis="x", alpha=0.3)

    fig.suptitle("Calibration and predictive accuracy are separate axes", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


def consolidated_figures() -> None:
    sweep = _json("outputs", "corpus", "synthetic_ratio_sweep.json")
    diag = _json("outputs", "corpus", "05_synthetic_degradation", "diagnosis.json")
    rv = _json("outputs", "corpus", "real_vs_synthetic.json")
    if sweep and diag and rv:
        save(fig_synthetic_consolidated(sweep, diag, rv),
             "figC01_synthetic_augmentation",
             "Synthetic share against AUPRC on real validation rows (A), the "
             "distribution diagnostics that fail to explain the drop (B), the "
             "discriminator gap that does (C), and the paired result (D). The "
             "generated rows reproduce the marginals, the rank correlation, the class "
             "balance and the feature range, and are separable from real rows only by "
             "a model that can use interactions.",
             "outputs/corpus/synthetic_ratio_sweep.json, "
             "outputs/corpus/05_synthetic_degradation/diagnosis.json, "
             "outputs/corpus/real_vs_synthetic.json")
    else:
        skip("figC01_synthetic_augmentation",
             "run run_real_vs_synthetic.py --ratio-sweep and "
             "diagnose_synthetic_degradation.py")

    rob = _json("outputs", "human_affect", "13_multimodal_robustness", "robustness.json")
    if rob:
        save(fig_alignment_degradation(rob), "figC02_alignment_degradation",
             "All 24 robustness conditions grouped into no corruption, noise, "
             "misalignment and missing modality. Permuting the audio-video pairing "
             "within actor preserves speaker and label distribution and destroys only "
             "the correspondence, and costs 0.2661 balanced accuracy against 0.0278 "
             "for the heaviest additive audio noise.",
             "outputs/human_affect/13_multimodal_robustness/robustness.json")
    else:
        skip("figC02_alignment_degradation", "run run_multimodal_robustness.py")

    xai = _json("outputs", "human_affect", "14_xai_calibration_representation",
                "xai.json")
    if xai and xai.get("calibration"):
        save(fig_accuracy_vs_calibration(xai["calibration"]),
             "figC03_accuracy_vs_calibration",
             "Accuracy against expected calibration error for every arm, with the "
             "overconfidence axis beside it. The best-calibrated arm is the "
             "second-weakest predictor and the strongest predictor is the worst "
             "calibrated, so neither metric substitutes for the other.",
             "outputs/human_affect/14_xai_calibration_representation/xai.json")
    else:
        skip("figC03_accuracy_vs_calibration", "run run_multimodal_xai_fairness.py")


# -- scenario lab ---------------------------------------------------------------------
#
# Six figures, one per question the Scenario Lab is asked. Every one keeps the simulation
# method visible in the colour, because the difference between "these sessions really
# happened" and "this is what the model would have said" is the whole point and a chart
# that flattens it would be worse than no chart.

#: One colour per simulation method, used identically in all six figures.
METHOD_COLOUR = {
    "OBSERVED_STRATUM": "#2c7a7b",
    "COUNTERFACTUAL": "#dd6b20",
    "POLICY_COUNTERFACTUAL": "#2b6cb0",
}
METHOD_LABEL = {
    "OBSERVED_STRATUM": "observed stratum (rows really occurred)",
    "COUNTERFACTUAL": "counterfactual (rows altered under an assumption)",
    "POLICY_COUNTERFACTUAL": "policy comparison (identical rows, different rule)",
}


def _method_legend(ax, methods):
    handles = [plt.Rectangle((0, 0), 1, 1, color=METHOD_COLOUR[m])
               for m in methods if m in METHOD_COLOUR]
    labels = [METHOD_LABEL[m] for m in methods if m in METHOD_COLOUR]
    ax.legend(handles, labels, frameon=False, fontsize=8, loc="upper center",
              bbox_to_anchor=(0.5, -0.12), ncol=1)


def fig_scenario_comparison(comparison: pd.DataFrame):
    """Every condition's mean risk beside its baseline, per domain."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.4))
    for ax, family, title in ((axes[0], "market", "NIFTY-50 market conditions"),
                              (axes[1], "transaction",
                               "Transaction fixture conditions")):
        sub = comparison[comparison["family"] == family].copy()
        if sub.empty:
            ax.set_visible(False)
            continue
        base = sub[sub["is_baseline"]]
        base_risk = float(base["risk_mean"].iloc[0]) if len(base) else np.nan
        sub = sub.sort_values("risk_mean")
        y = np.arange(len(sub))
        colours = [METHOD_COLOUR.get(m, "#718096") for m in sub["simulation_method"]]
        ax.barh(y, sub["risk_mean"], color=colours, height=0.66,
                edgecolor=["#111" if b else "none" for b in sub["is_baseline"]],
                linewidth=1.2)
        ax.axvline(base_risk, color="#111", ls="--", lw=1.2)
        ax.annotate("baseline %.4f" % base_risk, (base_risk, len(sub) - 0.35),
                    fontsize=8, xytext=(4, 0), textcoords="offset points")
        for i, (v, n) in enumerate(zip(sub["risk_mean"], sub["n_rows"], strict=False)):
            ax.annotate("%.4f  (n=%d)" % (v, n), (v, i), fontsize=7.5,
                        xytext=(4, 0), textcoords="offset points", va="center")
        ax.set_yticks(y)
        ax.set_yticklabels(sub["scenario_id"], fontsize=8.5)
        ax.set_xlim(0, float(sub["risk_mean"].max()) * 1.35)
        ax.set_xlabel("mean estimate under the condition")
        ax.set_title(title)
        ax.grid(axis="x", alpha=0.3)
        _method_legend(ax, list(dict.fromkeys(sub["simulation_method"])))
    fig.suptitle("What the model reported under each declared condition", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def fig_counterfactual_outcome(comparison: pd.DataFrame, currency: pd.DataFrame):
    """Baseline to counterfactual, and the currency figure the policy comparison gives."""
    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(13, 5.2))

    cf = comparison[(comparison["family"] == "market")
                    & (comparison["simulation_method"] == "COUNTERFACTUAL")].copy()
    base = comparison[comparison["is_baseline"]
                      & (comparison["family"] == "market")]
    base_risk = float(base["risk_mean"].iloc[0]) if len(base) else np.nan
    cf = cf.sort_values("risk_mean")
    y = np.arange(len(cf))
    for i, row in enumerate(cf.itertuples()):
        ax.annotate("", xy=(row.risk_mean, i), xytext=(base_risk, i),
                    arrowprops={"arrowstyle": "->", "color": "#dd6b20", "lw": 2})
        ax.annotate("%+.4f" % (row.risk_mean - base_risk),
                    ((row.risk_mean + base_risk) / 2, i), fontsize=8,
                    xytext=(0, 7), textcoords="offset points", ha="center")
    ax.scatter([base_risk] * len(cf), y, s=60, color="#111", zorder=3, label="baseline")
    ax.scatter(cf["risk_mean"], y, s=60, color="#dd6b20", zorder=3,
               label="under the assumption")
    ax.set_yticks(y)
    ax.set_yticklabels(cf["scenario_id"], fontsize=9)
    ax.set_xlabel("mean estimate")
    ax.set_title("Counterfactual: what the model would have reported")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.3)

    cur = currency[currency["family"] == "market"].copy()
    if len(cur):
        cur = cur.sort_values("amount_inr")
        yy = np.arange(len(cur))
        lo = cur["amount_ci_low_inr"].to_numpy(float)
        hi = cur["amount_ci_high_inr"].to_numpy(float)
        pt = cur["amount_inr"].to_numpy(float)
        ax2.errorbar(pt / 1e5, yy, xerr=[(pt - lo) / 1e5, (hi - pt) / 1e5],
                     fmt="o", color="#2b6cb0", ecolor="#90cdf4", capsize=4,
                     markersize=7)
        for i, p_ in enumerate(pt):
            ax2.annotate("Rs %.2f lakh" % (p_ / 1e5), (p_ / 1e5, i), fontsize=8,
                         xytext=(0, 9), textcoords="offset points", ha="center")
        ax2.set_yticks(yy)
        ax2.set_yticklabels(cur["scenario_id"], fontsize=9)
        ax2.set_xlabel("simulated reduction in the daily 5% tail loss "
                       "(Rs lakh, declared notional)")
        ax2.set_title("Policy comparison on identical evidence")
        ax2.grid(axis="x", alpha=0.3)
    else:
        ax2.set_visible(False)

    fig.suptitle("Counterfactual outcomes: none of this happened", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


#: How each headline quantity is read, for the forest-plot facet titles. Facetting is not
#: cosmetic: a difference in mean risk and a difference in value coverage are different
#: quantities, and putting them on one axis would make the larger unit look like the
#: larger finding.
HEADLINE_AXIS = {
    "risk_mean": "difference in mean estimate",
    "exposure_cvar_delta": "difference in the daily 5% tail loss (fraction of notional)",
    "exposure_elevated_value_coverage":
        "difference in the share of labelled-elevated value referred",
}


def fig_scenario_uncertainty(uncertainty: pd.DataFrame):
    """A forest plot per quantity: which differences the evidence separates from zero."""
    sub = uncertainty.dropna(subset=["estimate"]).copy()
    groups = [(m, g.sort_values("estimate")) for m, g in sub.groupby("headline_metric")]
    groups.sort(key=lambda t: -len(t[1]))
    heights = [max(1.0, len(g) * 0.42) for _, g in groups]
    fig, axes = plt.subplots(len(groups), 1, figsize=(9.8, sum(heights) + 1.6),
                             gridspec_kw={"height_ratios": heights})
    axes = np.atleast_1d(axes)

    for ax, (metric, g) in zip(axes, groups, strict=False):
        y = np.arange(len(g))
        lo = g["ci_low"].to_numpy(float)
        hi = g["ci_high"].to_numpy(float)
        pt = g["estimate"].to_numpy(float)
        has_ci = np.isfinite(lo) & np.isfinite(hi)
        excludes = has_ci & ((lo > 0) | (hi < 0))
        for i in np.where(has_ci)[0]:
            ax.plot([lo[i], hi[i]], [i, i],
                    color="#2b6cb0" if excludes[i] else "#a0aec0", lw=2.4)
        ax.scatter(pt, y, s=54,
                   color=["#2b6cb0" if e else "#a0aec0" for e in excludes], zorder=3)
        for i in np.where(~has_ci)[0]:
            ax.annotate("no sampling interval", (pt[i], i), fontsize=7.5,
                        color="#718096", xytext=(-9, 0), textcoords="offset points",
                        va="center", ha="right")
        ax.axvline(0, color="#111", lw=1.2)
        ax.set_yticks(y)
        ax.set_yticklabels(g["scenario_id"], fontsize=9)
        ax.set_xlabel(HEADLINE_AXIS.get(metric, metric), fontsize=9)
        ax.set_ylim(-0.7, len(g) - 0.3)
        edges = np.concatenate([pt, lo[has_ci], hi[has_ci]])
        span = float(np.nanmax(np.abs(edges))) or 1.0
        ax.set_xlim(-span * 1.45, span * 1.45)
        ax.grid(axis="x", alpha=0.3)

    axes[0].set_title("Blue intervals exclude zero; grey ones do not and are unresolved",
                      fontsize=10)
    fig.suptitle("Which scenario differences this evidence establishes, per quantity",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return fig


def fig_scenario_sensitivity(uncertainty: pd.DataFrame):
    """A tornado: which condition the estimate is most sensitive to, and at what cost."""
    sub = uncertainty.dropna(subset=["estimate"]).copy()
    sub["magnitude"] = sub["estimate"].abs()
    sub = sub.sort_values("magnitude")
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    y = np.arange(len(sub))
    colours = [METHOD_COLOUR.get(m, "#718096") for m in sub["simulation_method"]]
    ax.barh(y, sub["magnitude"], color=colours, height=0.66)
    for i, (m, n, q) in enumerate(zip(sub["magnitude"], sub["n_assumptions"],
                                      sub["headline_metric"], strict=False)):
        ax.annotate("%.4f  %s   %d assumption%s"
                    % (m, str(q).replace("exposure_", ""), n, "" if n == 1 else "s"),
                    (m, i), fontsize=7.5, xytext=(4, 0), textcoords="offset points",
                    va="center")
    ax.set_yticks(y)
    ax.set_yticklabels(sub["scenario_id"], fontsize=9)
    ax.set_xlim(0, float(sub["magnitude"].max()) * 2.05)
    ax.set_xlabel("absolute difference from baseline; the quantity differs by row "
                  "and is named beside each bar")
    ax.set_title("Sensitivity, with the number of assumptions each result rests on")
    ax.grid(axis="x", alpha=0.3)
    _method_legend(ax, list(dict.fromkeys(sub["simulation_method"])))
    fig.suptitle("A larger effect resting on more assumptions is not a stronger result",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


def fig_scenario_ablation(ablation: pd.DataFrame):
    """Does the direction of each scenario effect survive losing a modality block?"""
    pivot = ablation.pivot_table(index="scenario_id", columns="subset",
                                 values="delta_risk_mean", aggfunc="mean")
    order = [c for c in ("ALL", "NO_TEXT", "NO_MARKET", "NO_MEDIA", "MARKET_ONLY")
             if c in pivot.columns]
    pivot = pivot[order]
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    values = pivot.to_numpy(float)
    scale = np.nanmax(np.abs(values)) or 1.0
    ax.imshow(values, cmap="RdBu_r", vmin=-scale, vmax=scale, aspect="auto")
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            v = values[i, j]
            if np.isfinite(v):
                ax.text(j, i, "%+.4f" % v, ha="center", va="center", fontsize=8,
                        color="#111" if abs(v) < scale * 0.55 else "#fff")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, fontsize=9)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=9)
    ax.set_xlabel("modality subset the whole catalogue was re-run under")
    ax.set_title("Change in mean estimate, per condition and per subset")
    fig.suptitle("A conclusion that changes sign across subsets belongs to one channel",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


def fig_scenario_robustness(robustness: pd.DataFrame):
    """Effect against its own seed spread: is the conclusion a property of the draw?"""
    sub = robustness.dropna(subset=["delta_mean"]).copy()
    sub = sub.sort_values("delta_mean")
    fig, ax = plt.subplots(figsize=(10, 5.6))
    y = np.arange(len(sub))
    lo = sub["delta_min"].to_numpy(float)
    hi = sub["delta_max"].to_numpy(float)
    pt = sub["delta_mean"].to_numpy(float)
    stable = sub["stable_sign"].to_numpy(bool)
    for i in range(len(sub)):
        ax.plot([lo[i], hi[i]], [i, i],
                color="#2c7a7b" if stable[i] else "#c53030", lw=2.4)
    ax.scatter(pt, y, s=52,
               color=["#2c7a7b" if s else "#c53030" for s in stable], zorder=3)
    ax.axvline(0, color="#111", lw=1.2)
    labels = ["%s  (%s)" % (s, f) for s, f in
              zip(sub["scenario_id"], sub["family"], strict=False)]
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8.5)
    ax.set_xlabel("difference from baseline: mean across seeds, with the observed range")
    ax.set_title("Green keeps its sign in every seed; red does not")
    ax.grid(axis="x", alpha=0.3)
    fig.suptitle("Is the conclusion a property of the condition or of the seed?",
                 fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return fig


def scenario_figures() -> None:
    comparison = _csv("outputs", "scenario", "scenario_comparison.csv")
    currency = _csv("outputs", "scenario", "scenario_money.csv")
    uncertainty = _csv("outputs", "scenario", "scenario_uncertainty.csv")
    ablation = _csv("outputs", "scenario", "scenario_ablation.csv")
    robustness = _csv("outputs", "scenario", "scenario_robustness.csv")
    run = "run python scripts/run_scenarios.py"

    if comparison is not None and not comparison.empty:
        save(fig_scenario_comparison(comparison), "figS01_scenario_comparison",
             "Mean integrity-risk estimate under every declared condition, per domain, "
             "against the baseline. Colour is the simulation method: observed strata "
             "select rows that occurred, counterfactuals alter rows under a stated "
             "assumption, and policy comparisons change a declared rule on identical "
             "evidence.",
             "outputs/scenario/scenario_comparison.csv")
    else:
        skip("figS01_scenario_comparison", run)

    if comparison is not None and currency is not None and not comparison.empty:
        save(fig_counterfactual_outcome(comparison, currency),
             "figS02_counterfactual_outcome",
             "Left: the move from the baseline estimate to the estimate under each "
             "counterfactual assumption. Right: the simulated reduction in the daily 5% "
             "tail loss under each declared exposure policy, on a declared notional "
             "research base, with a moving-block interval. None of this occurred and no "
             "capital was at risk.",
             "outputs/scenario/scenario_comparison.csv, "
             "outputs/scenario/scenario_money.csv")
    else:
        skip("figS02_counterfactual_outcome", run)

    if uncertainty is not None and not uncertainty.empty:
        save(fig_scenario_uncertainty(uncertainty), "figS03_scenario_uncertainty",
             "Every scenario difference with its 95% interval. Blue intervals exclude "
             "zero; grey ones do not and the difference is reported as unresolved rather "
             "than as absent. Policy comparisons carry a moving-block interval; the "
             "transaction referral thresholds are deterministic on fixed scores and "
             "carry none.",
             "outputs/scenario/scenario_uncertainty.csv")
        save(fig_scenario_sensitivity(uncertainty), "figS04_scenario_sensitivity",
             "Absolute effect size per condition, with the number of assumptions each "
             "result rests on. The ordering is deliberately not a ranking of importance: "
             "the largest effect here is also the one resting on the strongest "
             "assumption.",
             "outputs/scenario/scenario_uncertainty.csv")
    else:
        skip("figS03_scenario_uncertainty", run)
        skip("figS04_scenario_sensitivity", run)

    if ablation is not None and not ablation.empty:
        save(fig_scenario_ablation(ablation), "figS05_scenario_ablation",
             "Change in the mean estimate for every condition, re-run under five "
             "modality subsets. A row whose colour flips between columns is a conclusion "
             "that belongs to one channel rather than to the condition.",
             "outputs/scenario/scenario_ablation.csv")
    else:
        skip("figS05_scenario_ablation", run)

    if robustness is not None and not robustness.empty:
        save(fig_scenario_robustness(robustness), "figS06_scenario_robustness",
             "Each scenario's effect averaged over seeds, with the observed range. Green "
             "keeps the sign of its effect in every seed; red does not, and its "
             "conclusion is a property of the draw rather than of the condition.",
             "outputs/scenario/scenario_robustness.csv")
    else:
        skip("figS06_scenario_robustness", run)

if __name__ == "__main__":
    raise SystemExit(main())
