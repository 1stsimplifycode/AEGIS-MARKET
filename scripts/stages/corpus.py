"""CORPUS module adapters.

Thin wrappers over ``research/corpus/`` and ``research/validation/``, following the same
rule as every other adapter package: they orchestrate, they never define a metric.

CORPUS-01 and CORPUS-03 are expensive (a full corpus rebuild, and six model fits), so they
report the executed artifacts rather than re-running on every invocation. Each names the
command that regenerates its inputs, and each reports BLOCKED with that command when the
artifact is absent -- an adapter that silently produced a report from nothing would be
indistinguishable from one that ran.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from research.core import jsonio, paths
from scripts.stages import BLOCKED, OK, StageResult

OUT_ROOT = paths.REPO_ROOT / "outputs" / "corpus"
CORPUS_DIR = paths.DATA / "corpus"


def _out(slug: str) -> Path:
    d = OUT_ROOT / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


# ------------------------------------------------------------------- CORPUS-01 ----

def corpus_build(force: bool = False) -> StageResult:
    """Report the assembled corpus, or rebuild it when ``--force`` is given."""
    report_path = OUT_ROOT / "corpus_report.json"
    if force or not report_path.exists():
        proc = subprocess.run([sys.executable, "scripts/build_corpus.py", "--all"],
                              cwd=str(paths.REPO_ROOT))
        if proc.returncode != 0:
            return StageResult(1, "scripts/build_corpus.py exited %d" % proc.returncode)

    report = _read(report_path)
    if report is None:
        return StageResult(
            BLOCKED,
            "corpus not assembled; run python scripts/build_corpus.py --all", outputs=[])

    comp = report.get("composition") or {}
    target = report.get("scale_target") or {}
    return StageResult(
        OK,
        "%d samples: %d real (%.1f%%), %d synthetic; %d distinct source ids across %d "
        "datasets; scale target %s%s"
        % (comp.get("total_samples", 0), comp.get("real_samples", 0),
           comp.get("real_percentage", 0.0), comp.get("synthetic_samples", 0),
           comp.get("unique_source_ids", 0), comp.get("unique_sources", 0),
           "met" if target.get("met") else "NOT met",
           " by real data alone" if target.get("met_by_real_data_alone") else ""),
        outputs=[str(report_path), str(OUT_ROOT / "corpus_shards.csv")],
        detail=report)


# ------------------------------------------------------------------- CORPUS-02 ----

def corpus_quality(force: bool = False) -> StageResult:
    """Duplication, cross-split contamination and effective sample size per shard."""
    report = _read(OUT_ROOT / "corpus_report.json")
    if report is None:
        return StageResult(
            BLOCKED,
            "corpus not assembled; run python scripts/build_corpus.py --all", outputs=[])

    out = _out("02_corpus_quality")
    per_shard = report.get("per_shard_analysis") or []
    eff = report.get("effective_sample_size") or {}

    contaminated = [a["shard"] for a in per_shard
                    if not (a.get("cross_split") or {}).get("clean", True)]
    worst_dupe = max(
        (a for a in per_shard if a.get("exact_duplicates")),
        key=lambda a: a["exact_duplicates"]["duplicate_fraction"], default=None)

    payload = {
        "per_shard": per_shard,
        "corpus_effective_sample_size": eff,
        "shards_with_cross_split_contamination": contaminated,
        "worst_duplicate_shard": (
            {"shard": worst_dupe["shard"],
             **worst_dupe["exact_duplicates"]} if worst_dupe else None),
        "note": ("A shard whose payload columns are coarse summaries -- a word count and "
                 "a character count, say -- will show a high duplicate fraction without "
                 "any duplicated source material, because two different sentences of the "
                 "same length are identical in those two numbers. The figure is reported "
                 "per shard for that reason rather than as one corpus-wide rate."),
        # Derived from corpus_report.json, so the stamp is that report's rather than a
        # fresh one: this module reshapes numbers it did not compute, and claiming a
        # separate provenance would overstate what it did.
        "derived_from": "outputs/corpus/corpus_report.json",
        "generated_at": report.get("generated_at"),
        "git_commit": report.get("git_commit"),
        "environment": report.get("environment"),
    }
    jsonio.write(out / "quality.json", payload)

    rows = [{"shard": a["shard"], "rows": a["rows"],
             "units": (a.get("effective_sample_size") or {}).get(
                 "n_independent_units"),
             "design_effect": (a.get("effective_sample_size") or {}).get(
                 "design_effect"),
             "duplicate_fraction": (a.get("exact_duplicates") or {}).get(
                 "duplicate_fraction"),
             "cross_split_clean": (a.get("cross_split") or {}).get("clean")}
            for a in per_shard]
    pd.DataFrame(rows).to_csv(out / "quality.csv", index=False)

    return StageResult(
        OK if not contaminated else BLOCKED,
        ("%d shards analysed; %d independent units behind %d rows (design effect %.1f); "
         "cross-split contamination in %s"
         % (len(per_shard), eff.get("n_independent_units", 0), eff.get("n_rows", 0),
            eff.get("design_effect", float("nan")),
            "no shard" if not contaminated else ", ".join(contaminated))),
        outputs=[str(out / "quality.json"), str(out / "quality.csv")],
        detail=payload)


# ------------------------------------------------------------------- CORPUS-03 ----

def real_vs_synthetic(force: bool = False) -> StageResult:
    """Report whether synthetic training rows helped or harmed real-data performance."""
    path = OUT_ROOT / "real_vs_synthetic.json"
    if force or not path.exists():
        proc = subprocess.run([sys.executable, "scripts/run_real_vs_synthetic.py"],
                              cwd=str(paths.REPO_ROOT))
        if proc.returncode != 0:
            return StageResult(1, "scripts/run_real_vs_synthetic.py exited %d"
                               % proc.returncode)

    report = _read(path)
    if report is None:
        return StageResult(
            BLOCKED,
            "not executed; run python scripts/run_real_vs_synthetic.py", outputs=[])

    verdict = report.get("verdict") or {}
    memo = report.get("generator_memorisation") or {}
    sweep = _read(OUT_ROOT / "synthetic_ratio_sweep.json") or {}
    outputs = [str(path), str(OUT_ROOT / "real_vs_synthetic.csv")]
    if sweep:
        outputs.append(str(OUT_ROOT / "synthetic_ratio_sweep.json"))

    return StageResult(
        OK,
        "%d synthetic rows against %d real training rows: %+.4f AUPRC on real evaluation "
        "data (%s); generator memorisation ratio %.3f with %d exact copies%s"
        % (report.get("n_synthetic", 0), report.get("n_real_train", 0),
           verdict.get("mean_difference", float("nan")),
           verdict.get("reading", "not established"),
           memo.get("distance_ratio", float("nan")),
           memo.get("n_exact_copies", -1),
           ("; largest harmless synthetic share %.2f"
            % sweep.get("largest_harmless_share", 0.0)) if sweep else ""),
        outputs=outputs, detail=report)


# ------------------------------------------------------------------- CORPUS-04 ----

def research_validation(force: bool = False) -> StageResult:
    """Regenerate the fifteen-dimension scorecard and the claim gate."""
    out = paths.REPO_ROOT / "outputs" / "research_validation"
    proc = subprocess.run(
        [sys.executable, "scripts/generate_research_validation.py"],
        cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        return StageResult(1, "scripts/generate_research_validation.py exited %d"
                           % proc.returncode)

    report = _read(out / "validation_summary.json")
    if report is None:
        return StageResult(BLOCKED, "validation summary was not written", outputs=[])

    counts = (report.get("summary") or {}).get("counts") or {}
    claims = report.get("claim_gate") or []
    supported = sum(1 for c in claims if c.get("verdict") == "SUPPORTED")
    return StageResult(
        OK,
        "%d/%d cells SUPPORTED (%d partial, %d not run, %d blocked); %d of %d headline "
        "claims supported, the rest qualified or not supported"
        % (counts.get("SUPPORTED", 0), (report.get("summary") or {}).get("n_cells", 0),
           counts.get("PARTIAL", 0), counts.get("NOT RUN", 0),
           counts.get("BLOCKED", 0), supported, len(claims)),
        outputs=[str(out / "validation_summary.json"),
                 str(out / "research_validation_report.md"),
                 str(out / "scorecard.csv")],
        detail=report)


# ------------------------------------------------------------------- CORPUS-05 ----

def synthetic_degradation(force: bool = False) -> StageResult:
    """Report which mechanism explains the synthetic-augmentation collapse."""
    src = OUT_ROOT / "synthetic_degradation_diagnosis.json"
    if not src.exists():
        return StageResult(
            BLOCKED,
            "diagnosis not executed; run scripts/diagnose_synthetic_degradation.py",
            outputs=[])
    payload = json.loads(src.read_text(encoding="utf-8"))
    out = _out("05_synthetic_degradation")
    jsonio.write(out / "diagnosis.json", payload)
    supported = payload.get("mechanisms_supported") or []
    ruled_out = [m["mechanism"] for m in payload.get("mechanisms", [])
                 if not m["supported"]]
    return StageResult(
        OK,
        "%d mechanisms tested: %s supported, %d ruled out (%s). Claim '%s' is %s"
        % (len(payload.get("mechanisms", [])), ", ".join(supported) or "none",
           len(ruled_out), ", ".join(ruled_out),
           payload.get("research_claim", "")[:60],
           "supported" if payload.get("claim_is_supported") else "not supported"),
        outputs=[str(out / "diagnosis.json")], detail=payload)


# ------------------------------------------------------------------- CORPUS-06 ----

def paper_artifacts(force: bool = False) -> StageResult:
    """Regenerate every paper table and figure from executed artifacts."""
    for script in ("scripts/generate_paper_tables.py",
                   "scripts/generate_research_figures.py"):
        proc = subprocess.run([sys.executable, script], cwd=str(paths.REPO_ROOT))
        if proc.returncode != 0:
            return StageResult(1, "%s exited %d" % (script, proc.returncode))

    tables = _read(paths.REPO_ROOT / "outputs" / "paper_tables" / "tables.json") or {}
    figs = _read(paths.REPO_ROOT / "outputs" / "research_figures"
                 / "figures.json") or {}
    ha_figs = _read(paths.REPO_ROOT / "outputs" / "human_affect" / "figures"
                    / "figures.json") or {}
    total_figs = figs.get("n_generated", 0) + ha_figs.get("n_generated", 0)
    not_generated = (figs.get("n_not_generated", 0)
                     + ha_figs.get("n_not_generated", 0)
                     + tables.get("n_not_generated", 0))
    return StageResult(
        OK,
        "%d tables and %d figures generated; %d recorded NOT GENERATED"
        % (tables.get("n_written", 0), total_figs, not_generated),
        outputs=[str(paths.REPO_ROOT / "outputs" / "paper_tables" / "tables.json"),
                 str(paths.REPO_ROOT / "outputs" / "research_figures"
                     / "figures.json")],
        detail={"tables": tables, "research_figures": figs,
                "affective_figures": ha_figs})
