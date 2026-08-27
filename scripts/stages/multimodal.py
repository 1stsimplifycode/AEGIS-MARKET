"""MULTIMODAL module adapters (MULTIMODAL-01 .. MULTIMODAL-16).

Each function wraps canonical code. Nothing here defines a feature, a model or a metric.

Modality-specific honesty rules are enforced by the surrounding project and restated in
the manifest: sonification is not speech, market-derived renderings are not independent
visual evidence, and no third-party broadcast media is downloaded or redistributed.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from research.core import jsonio, paths
from scripts.stages import (
    OK,
    AnalysisResult,
    StageResult,
    insufficient,
    metric,
    require,
    series,
)

DATASET = paths.PANEL / "multimodal_dataset.parquet"
CASH = paths.PANEL / "cash_panel.parquet"
CORPUS = paths.PANEL / "text_corpus.parquet"


def _out(slug: str) -> Path:
    d = paths.REPO_ROOT / "outputs" / "multimodal" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _block_summary(block: str, slug: str, filename: str) -> StageResult:
    """Shared reporter for the four feature-block modules.

    One helper rather than four near-identical copies: the blocks differ only in
    which column list they read, and duplicating the body would let them drift.
    """
    if (r := require([DATASET])):
        return r
    from research.data import dataset as ds

    df = pd.read_parquet(DATASET)
    out = _out(slug)
    cols = ds.MODALITY_BLOCKS[block]
    rows = []
    for c in cols:
        if c not in df.columns:
            rows.append({"feature": c, "present": False})
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        rows.append({"feature": c, "present": True,
                     "non_null_fraction": float(s.notna().mean()),
                     "n_distinct": int(s.nunique(dropna=True)),
                     "mean": float(s.mean()), "std": float(s.std())})
    tbl = pd.DataFrame(rows)
    tbl.to_csv(out / filename, index=False)
    present = int(tbl.get("present", pd.Series(dtype=bool)).sum())
    return StageResult(OK, "%s block: %d/%d features present"
                       % (block, present, len(cols)),
                       outputs=[str(out / filename)])


def _one_symbol(value) -> str:
    """One instrument, however the caller expressed it.

    The declared kind is ``symbols``, which validates and normalises a list, so a
    single-instrument control arrives as a one-element list. Reaching for ``str()`` on it
    produces the literal ``['RELIANCE']``, which then matches nothing — a failure that
    reads to the user as "this instrument has no data".
    """
    if isinstance(value, (list, tuple)):
        return str(value[0]).upper() if value else ""
    return str(value or "").upper()


# -------------------------------------------------------------- MULTIMODAL-01 ----

def text_corpus_ingestion(force: bool = False) -> StageResult:
    """Wraps episodes.generate_text_corpus via scripts/build_dataset.py."""
    proc = subprocess.run([sys.executable, "scripts/build_dataset.py"],
                          cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        return StageResult(1, "scripts/build_dataset.py exited %d" % proc.returncode)
    return StageResult(OK, "text corpus regenerated", outputs=[str(CORPUS)])


# -------------------------------------------------------------- MULTIMODAL-02 ----

def text_affect_extraction(force: bool = False) -> StageResult:
    """Wraps research.text.affect over the existing corpus (read-only)."""
    if (r := require([CORPUS])):
        return r
    from research.text import affect as ta

    corpus = pd.read_parquet(CORPUS)
    out = _out("02_text_affect_extraction")
    sample = corpus if len(corpus) <= 4000 else corpus.sample(4000, random_state=20260818)
    rows = []
    for r_ in sample.itertuples(index=False):
        cred = float(getattr(r_, "source_credibility", 1.0))
        a = ta.extract(r_.text, source_credibility=cred)
        rows.append(a.scores)
    scores = pd.DataFrame(rows)
    summary = (scores.describe().T.reset_index()
               .rename(columns={"index": "dimension"}))
    summary.to_csv(out / "affect_distribution.csv", index=False)
    return StageResult(OK, "%d dimensions over %d documents"
                       % (len(ta.TEXT_AFFECT_DIMENSIONS), len(sample)),
                       outputs=[str(out / "affect_distribution.csv")],
                       detail={"n_documents_sampled": int(len(sample))})


# -------------------------------------------------------------- MULTIMODAL-03 ----

def text_feature_block(force: bool = False) -> StageResult:
    return _block_summary("text", "03_text_feature_block", "text_block_summary.csv")


# -------------------------------------------------------------- MULTIMODAL-04 ----

def image_asset_generation(force: bool = False) -> StageResult:
    """Wraps scripts/make_media.py (image stage)."""
    proc = subprocess.run([sys.executable, "scripts/make_media.py"],
                          cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        return StageResult(1, "scripts/make_media.py exited %d" % proc.returncode)
    return StageResult(OK, "market-derived image assets regenerated",
                       outputs=[str(paths.MEDIA / "images")])


# -------------------------------------------------------------- MULTIMODAL-05 ----

def image_feature_block(force: bool = False) -> StageResult:
    return _block_summary("image", "05_image_feature_block", "image_block_summary.csv")


# -------------------------------------------------------------- MULTIMODAL-06 ----

def audio_sonification(force: bool = False) -> StageResult:
    """Wraps scripts/make_media.py (audio stage)."""
    proc = subprocess.run([sys.executable, "scripts/make_media.py"],
                          cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        return StageResult(1, "scripts/make_media.py exited %d" % proc.returncode)
    return StageResult(OK, "sonified audio regenerated (sonification, not speech)",
                       outputs=[str(paths.MEDIA / "audio")])


# -------------------------------------------------------------- MULTIMODAL-07 ----

def audio_prosody_affect(force: bool = False) -> StageResult:
    return _block_summary("audio", "07_audio_prosody_affect", "audio_block_summary.csv")


# -------------------------------------------------------------- MULTIMODAL-08 ----

def video_generation(force: bool = False) -> StageResult:
    """Wraps scripts/make_media.py (video stage)."""
    proc = subprocess.run([sys.executable, "scripts/make_media.py"],
                          cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        return StageResult(1, "scripts/make_media.py exited %d" % proc.returncode)
    return StageResult(OK, "market-derived video regenerated",
                       outputs=[str(paths.MEDIA / "video")])


# -------------------------------------------------------------- MULTIMODAL-09 ----

def video_feature_block(force: bool = False) -> StageResult:
    return _block_summary("video", "09_video_feature_block", "video_block_summary.csv")


# -------------------------------------------------------------- MULTIMODAL-10 ----

def media_licensing_provenance(force: bool = False) -> StageResult:
    """Wraps research.core.licensing (registry + checker)."""
    from research.core import licensing as lic

    out = _out("10_media_licensing_provenance")
    refs = paths.MEDIA / "references"
    report: dict = {
        "reference_files": (sorted(p.name for p in refs.glob("*"))
                            if refs.exists() else []),
        "checker_available": hasattr(lic, "MediaLicenseChecker"),
        "statuses_declared": [s.value for s in lic.LicenseStatus],
        "policy": ("Public accessibility is not permission to redistribute. Where "
                   "redistribution is not permitted, reference metadata is stored "
                   "instead of media. Nothing with UNKNOWN status may reach a "
                   "publication artifact."),
    }
    for name in ("DATASETS", "MODELS", "REGISTRY"):
        if hasattr(lic, name):
            report["registry_%s" % name.lower()] = str(getattr(lic, name))[:400]
    jsonio.write(out / "licence_report.json", report)
    return StageResult(OK, "%d reference records; licence checker present"
                       % len(report["reference_files"]),
                       outputs=[str(out / "licence_report.json")], detail=report)


# -------------------------------------------------------------- MULTIMODAL-11 ----

def crossmodal_alignment(force: bool = False) -> StageResult:
    """Wraps research.evaluation.temporal_analysis.asynchrony_sensitivity."""
    if (r := require([DATASET])):
        return r
    from research.data import dataset as ds
    from research.evaluation import temporal_analysis as ta
    from research.models.risk_model import AegisRiskModel

    df = pd.read_parquet(DATASET)
    train = df[df["split"] == "train"]
    out = _out("11_crossmodal_alignment")
    model = AegisRiskModel(modalities=list(ds.MODALITY_BLOCKS),
                           fusion_strategy="regime_corrected", seed=20260818)
    model.fit(train, train["is_episode"].to_numpy(int))
    evald = df[df["split"] == "validation"]
    frames = []
    for modality in ("text", "image", "audio", "video"):
        # The block's own columns are what gets shifted; passing them explicitly is the
        # canonical signature rather than something this adapter decides.
        block_columns = [c for c in ds.MODALITY_BLOCKS[modality] if c in df.columns]
        res = ta.asynchrony_sensitivity(evald, model, modality, block_columns)
        frames.append(res)
    tbl = pd.concat(frames, ignore_index=True)
    tbl.to_csv(out / "asynchrony.csv", index=False)
    return StageResult(OK, "asynchrony over %d modality-offset rows" % len(tbl),
                       outputs=[str(out / "asynchrony.csv")])


# -------------------------------------------------------------- MULTIMODAL-12 ----

def multimodal_dataset_assembly(force: bool = False) -> StageResult:
    """Wraps scripts/build_dataset.py."""
    proc = subprocess.run([sys.executable, "scripts/build_dataset.py"],
                          cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        return StageResult(1, "scripts/build_dataset.py exited %d" % proc.returncode)
    return StageResult(OK, "multimodal dataset reassembled", outputs=[str(DATASET)])


# -------------------------------------------------------------- MULTIMODAL-13 ----

def fusion_strategies(force: bool = False) -> StageResult:
    """Wraps research.multimodal.fusion.demonstrate_degeneracy (analytic, no data).

    The inputs are constructed exactly as ``tests/property/test_regime_degeneracy.py``
    constructs them, including the deliberately large regime terms: if the cancellation
    were only approximate, a large term would expose it. Reusing the test's construction
    rather than inventing a gentler one is the point.
    """
    import numpy as np

    from research.multimodal import fusion as fu

    out = _out("13_fusion_strategies")
    rng = np.random.default_rng(20260818)
    n, n_mod, n_regimes = 500, 8, 4
    logits = rng.normal(0, 1.5, n_mod)
    regime = rng.integers(0, n_regimes, n)
    regime_scalar = rng.normal(0, 25.0, n_regimes)
    coverage = (rng.random((n, n_mod)) > 0.2).astype(float)
    coverage[coverage.sum(axis=1) == 0, 0] = 1.0

    proof = fu.demonstrate_degeneracy(np.zeros((n, n_mod)), coverage, regime,
                                      logits, regime_scalar)
    payload = {
        "strategies": sorted(getattr(fu, "STRATEGIES", ()) or ()),
        "degeneracy": proof,
        "construction": {"n_rows": n, "n_modalities": n_mod, "n_regimes": n_regimes,
                         "regime_term_sd": 25.0, "seed": 20260818},
        "statement": ("Under the inherited formulation softmax(s_m + g(r)), the regime "
                      "term factors out of numerator and denominator, so the fused "
                      "weights are algebraically identical to static attention."),
    }
    jsonio.write(out / "degeneracy.json", payload)
    return StageResult(OK, "max abs weight difference %.3e over %d rows"
                       % (proof["max_abs_weight_difference"], proof["n_rows"]),
                       outputs=[str(out / "degeneracy.json")], detail=payload)


# -------------------------------------------------------------- MULTIMODAL-14 ----

def modality_information(force: bool = False) -> StageResult:
    """Wraps research.evaluation.information.decomposition over existing arm artifacts."""
    exp_dir = paths.ARTIFACTS / "experiments"
    if (r := require([exp_dir])):
        return r
    from research.evaluation import information as inf

    per_arm = {p.stem.replace("per_row_", ""): pd.read_parquet(p)
               for p in sorted(exp_dir.glob("per_row_*.parquet"))}
    if "FULL" not in per_arm:
        return StageResult(4, "per_row_FULL.parquet absent; run STATS-13 first")
    from scripts.run_research_angles import MODALITY_ARMS

    out = _out("14_modality_information")
    # The mapping is the point of the call. Without it `decomposition` iterates an empty
    # dict and writes a header-only file, which is what this module did until the paper
    # consolidation found the declared output was two bytes long. The mapping is imported
    # from the canonical caller rather than restated, so the two cannot diverge.
    usable = {m: (only, without) for m, (only, without) in MODALITY_ARMS.items()
              if only in per_arm and without in per_arm}
    tbl = inf.decomposition(per_arm, "FULL", usable)
    tbl.to_csv(out / "decomposition.csv", index=False)
    return StageResult(
        OK,
        "decomposition over %d arms covering %d modalities with both a stand-alone and "
        "a leave-one-out arm" % (len(per_arm), len(usable)),
        outputs=[str(out / "decomposition.csv")],
        detail={"n_arms": len(per_arm), "n_modalities": len(usable),
                "modalities": sorted(usable)})


# -------------------------------------------------------------- MULTIMODAL-15 ----

def modality_missingness(force: bool = False) -> StageResult:
    """Wraps the leave-one-out arms already produced by the ablation runner."""
    exp_dir = paths.ARTIFACTS / "experiments"
    results = exp_dir / "ablation_results.csv"
    if (r := require([results])):
        return r
    out = _out("15_modality_missingness_asynchrony")
    tbl = pd.read_csv(results)
    col = "arm" if "arm" in tbl.columns else tbl.columns[0]
    withheld = tbl[tbl[col].astype(str).str.startswith("NO_")]
    withheld.to_csv(out / "missingness.csv", index=False)
    return StageResult(OK, "%d leave-one-out arms" % len(withheld),
                       outputs=[str(out / "missingness.csv")],
                       detail={"n_arms": int(len(withheld))})


# -------------------------------------------------------------- MULTIMODAL-16 ----

def multimodal_xai(force: bool = False) -> StageResult:
    """Wraps the XAI stage of scripts/generate_paper_artifacts.py."""
    proc = subprocess.run([sys.executable, "scripts/generate_paper_artifacts.py"],
                          cwd=str(paths.REPO_ROOT))
    if proc.returncode != 0:
        return StageResult(1, "scripts/generate_paper_artifacts.py exited %d"
                           % proc.returncode)
    return StageResult(OK, "XAI attributions, benchmark and sanity suite regenerated",
                       outputs=[str(paths.ARTIFACTS / "statistics")])


# -- live analysis -------------------------------------------------------------------


def analyse_text_corpus(date_from: str | None = None, date_to: str | None = None,
                        instruments: list[str] | None = None,
                        doc_kind: str = "all",
                        sample_size: int = 400) -> AnalysisResult:
    """MULTIMODAL-01 live: ingest the caller's slice and extract affect from it.

    Runs :func:`research.text.affect.extract` over a sample of the real corpus, now. The
    lexicon match rate is reported beside the scores because a dimension scored from one
    matched token in eight is a different object from one scored from twenty, and a mean
    that hides the match rate invites the first to be read as the second.
    """
    from research.text import affect as ta
    from scripts.stages import live

    corpus = live.text_corpus()
    df = live.slice_frame(corpus, date_from, date_to, instruments)
    if doc_kind and doc_kind != "all":
        df = df[df["doc_kind"] == doc_kind]
    if len(df) < live.MIN_ROWS:
        return insufficient(
            "the selected slice holds %d documents, below the %d needed for an affect "
            "distribution to mean anything" % (len(df), live.MIN_ROWS),
            "Widen the date range, choose more instruments, or select all document "
            "kinds.")

    # A deterministic sample: the same selection returns the same documents, so a
    # reader who reruns the request sees the same numbers.
    sample = df.sample(n=min(sample_size, len(df)), random_state=20260818) \
        if len(df) > sample_size else df

    extracted = [ta.extract(str(t), source_credibility=float(c))
                 for t, c in zip(sample["text"], sample["source_credibility"],
                                 strict=False)]
    scored = pd.DataFrame([e.scores for e in extracted])
    matched = np.array([e.n_matched for e in extracted], dtype=float)
    tokens = np.array([e.n_tokens for e in extracted], dtype=float)
    match_rate = float(np.divide(matched, np.maximum(tokens, 1)).mean())
    polarization = float(ta.polarization(extracted))

    dims = [d for d in ta.TEXT_AFFECT_DIMENSIONS if d in scored.columns]
    summary = pd.DataFrame({
        "dimension": dims,
        "mean": [float(scored[d].mean()) for d in dims],
        "sd": [float(scored[d].std(ddof=1)) if len(scored) > 1 else 0.0 for d in dims],
        "nonzero_share": [float((scored[d] != 0).mean()) for d in dims],
    }).sort_values("mean", ascending=False)

    kinds = (df["doc_kind"].value_counts()
             .rename_axis("doc_kind").reset_index(name="documents"))
    strongest = summary.iloc[0]

    metrics = [
        metric("documents", "Documents in this slice", int(len(df)), "int",
               "aligned text items matching your selection"),
        metric("sampled", "Documents scored", int(len(sample)), "int",
               "extracted live by the canonical lexicon extractor"),
        metric("instruments", "Instruments", int(df["symbol"].nunique()), "int",
               "distinct symbols carrying text in the slice"),
        metric("match_rate", "Lexicon match rate", match_rate, "pct",
               "share of tokens the affect lexicon recognised; a low rate means the "
               "scores rest on few words"),
        metric("polarization", "Polarization", polarization, "float4",
               "disagreement in valence across the sampled documents"),
        metric("mean_credibility", "Mean source credibility",
               float(sample["source_credibility"].mean()), "float4",
               "a corpus attribute, not a judgement about any publisher"),
    ]

    observations = [
        "%d documents matched your selection; %d were scored live by the canonical "
        "extractor." % (len(df), len(sample)),
        "The strongest dimension on this slice is %s at %.4f."
        % (strongest["dimension"], float(strongest["mean"])),
        "The lexicon recognised %.1f%% of tokens, so these scores rest on that "
        "fraction of the text." % (100 * match_rate),
    ]
    episode_docs = int((df["doc_kind"].astype(str).str.startswith("episode")).sum())
    if episode_docs:
        observations.append(
            "%d of these documents were generated as episode narration (limitation "
            "L-04); the rest are background." % episode_docs)

    return AnalysisResult(
        dataset=live.describe_slice(
            df, "data/panel/text_corpus.parquet",
            date_from=date_from, date_to=date_to, instruments=instruments,
            doc_kind=doc_kind, sample_size=sample_size),
        metrics=metrics,
        series=[
            series("affect_dimensions", "Affect dimensions on this slice",
                   list(summary.columns), summary.values.tolist(),
                   "extracted live; nonzero_share is how many documents scored the "
                   "dimension at all"),
            series("doc_kinds", "Document kinds in this slice",
                   list(kinds.columns), kinds.values.tolist(),
                   "background documents are filler; episode documents are generated "
                   "narration aligned to an injected episode"),
        ],
        observations=observations,
        uncertainty={
            "kind": "sampling",
            "n_sampled": int(len(sample)),
            "n_available": int(len(df)),
            "reading": ("Means are over %d sampled documents drawn deterministically "
                        "from the %d that matched, so re-running this request returns "
                        "the same documents. The sample standard deviation is reported "
                        "per dimension in the table."
                        % (len(sample), len(df))),
        },
        provenance={
            "canonical_called": [
                "research.text.affect:extract",
                "research.text.affect:polarization",
            ],
            "extractor_version": extracted[0].extractor_version,
            "lexicon_version": extracted[0].lexicon_version,
            "sample_seed": 20260818,
            "documents_scored": int(len(sample)),
            "wrote_nothing": True,
        },
        message="%d documents scored live across %d instruments"
                % (len(sample), df["symbol"].nunique()),
    )


# ------------------------------------------------------------ block summaries ----

def block_feature_table(df: pd.DataFrame, block: str) -> pd.DataFrame:
    """Per-feature presence and moments for one modality block, over the rows given.

    The frame-taking twin of :func:`_block_summary`. Four modules (text, image, audio and
    video blocks) report the same thing about different column lists, and the live and
    regenerating paths must not compute it two different ways.
    """
    from research.data import dataset as ds

    rows = []
    for c in ds.MODALITY_BLOCKS.get(block, []):
        if c not in df.columns:
            rows.append({"feature": c, "present": False, "non_null_fraction": 0.0,
                         "n_distinct": 0, "mean": None, "std": None})
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        rows.append({"feature": c, "present": True,
                     "non_null_fraction": float(s.notna().mean()),
                     "n_distinct": int(s.nunique(dropna=True)),
                     "mean": float(s.mean()), "std": float(s.std())})
    return pd.DataFrame(rows)


def _analyse_block(block: str, note: str, date_from: str | None, date_to: str | None,
                   instruments: list[str] | None, split: str) -> AnalysisResult:
    """Shared live analysis for the four feature-block modules."""
    from scripts.stages import live

    df = live.slice_frame(live.panel(), date_from, date_to, instruments, split)
    if len(df) < live.MIN_ROWS:
        return insufficient(
            "the selected slice holds %d rows, below the %d needed to describe the %s "
            "block" % (len(df), live.MIN_ROWS, block),
            "Widen the date range, or select more instruments.")

    tbl = block_feature_table(df, block)
    if tbl.empty:
        return insufficient("the %s block declares no features" % block,
                            "This is a defect in the block definition, not in your "
                            "selection.")
    present = tbl[tbl["present"]]
    degenerate = present[(present["n_distinct"] <= 1)
                         | (present["std"].fillna(0) == 0)]

    metrics = [
        metric("rows", "Rows in this slice", int(len(df)), "int"),
        metric("declared", "Features declared", int(len(tbl)), "int"),
        metric("present", "Present in the panel", int(len(present)), "int"),
        metric("mean_fill", "Mean fill on these rows",
               float(present["non_null_fraction"].mean()) if len(present) else 0.0,
               "pct"),
        metric("thinnest", "Thinnest feature",
               float(present["non_null_fraction"].min()) if len(present) else 0.0,
               "pct", "the least populated feature of the block on this slice"),
        metric("degenerate", "Constant here", int(len(degenerate)), "int",
               "features with one distinct value on these rows"),
    ]
    observations = [
        "The %s block carries %d of %d declared features, filled on average %.1f%% of "
        "the %d rows you selected."
        % (block, len(present), len(tbl),
           100 * float(present["non_null_fraction"].mean()) if len(present) else 0.0,
           len(df)),
        note,
    ]
    if len(degenerate):
        observations.append(
            "%d feature(s) are constant on this slice: %s. They cannot separate anything "
            "computed from these rows." % (len(degenerate),
                                           ", ".join(degenerate["feature"].head(4))))

    return AnalysisResult(
        dataset=live.describe_slice(df, "data/panel/multimodal_dataset.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments, block=block, split=split),
        metrics=metrics,
        series=[series("features", "%s block features on this slice" % block.title(),
                       list(tbl.columns), tbl.values.tolist(),
                       "present is whether the column exists; fill is over the "
                       "selected rows")],
        observations=observations,
        uncertainty={"kind": "none",
                     "reading": "Coverage and sample moments of the selected rows. "
                                "Nothing here is estimated."},
        provenance={"canonical_called": ["research.data.dataset:MODALITY_BLOCKS",
                                         "scripts.stages.multimodal:"
                                         "block_feature_table"],
                    "block": block, "wrote_nothing": True},
        message="%d of %d %s features present over %d rows"
                % (len(present), len(tbl), block, len(df)),
    )


# -------------------------------------------------------------- MULTIMODAL-02 ----

def analyse_text_affect(date_from: str | None = None, date_to: str | None = None,
                        instruments: list[str] | None = None,
                        dimension: str = "narrative_intensity",
                        group_by: str = "doc_kind",
                        sample_size: int = 600,
                        supplied_text: str = "") -> AnalysisResult:
    """MULTIMODAL-02 live: the affect distribution, and how one dimension varies.

    Where MULTIMODAL-01 asks what documents exist, this asks what the extractor makes of
    them. One dimension is put in the foreground because a table of fifteen means is a
    table nobody reads; the rest stay available beneath it.

    Given ``supplied_text``, the same extractor runs over that instead of over the corpus.
    It is the honest way to let someone check what the lexicon actually does: paste a
    paragraph, see how much of it matched, and read that rate beside the scores.
    """
    import numpy as np

    from research.text import affect as ta
    from scripts.stages import live

    if (supplied_text or "").strip():
        return _analyse_supplied_text(supplied_text)

    corpus = live.text_corpus()
    df = live.slice_frame(corpus, date_from, date_to, instruments)
    if len(df) < live.MIN_ROWS:
        return insufficient(
            "the selected slice holds %d documents, below the %d needed for an affect "
            "distribution" % (len(df), live.MIN_ROWS),
            "Widen the date range, or choose more instruments.")

    sample = (df.sample(n=min(int(sample_size), len(df)), random_state=20260818)
              if len(df) > sample_size else df)
    extracted = [ta.extract(str(t), source_credibility=float(c))
                 for t, c in zip(sample["text"], sample["source_credibility"],
                                 strict=False)]
    scored = pd.DataFrame([e.scores for e in extracted])
    scored.index = sample.index

    dims = [d for d in ta.TEXT_AFFECT_DIMENSIONS if d in scored.columns]
    if dimension not in dims:
        dimension = dims[0]

    summary = pd.DataFrame({
        "dimension": dims,
        "mean": [float(scored[d].mean()) for d in dims],
        "sd": [float(scored[d].std(ddof=1)) if len(scored) > 1 else 0.0 for d in dims],
        "p90": [float(scored[d].quantile(0.9)) for d in dims],
        "nonzero_share": [float((scored[d] != 0).mean()) for d in dims],
    }).sort_values("mean", ascending=False)

    key = group_by if group_by in sample.columns else "doc_kind"
    joined = sample[[key]].join(scored[[dimension]])
    grouped = (joined.groupby(key)[dimension]
               .agg(["count", "mean", "std"]).reset_index()
               .rename(columns={"count": "documents", "mean": "%s_mean" % dimension,
                                "std": "%s_sd" % dimension})
               .sort_values("%s_mean" % dimension, ascending=False))

    matched = np.array([e.n_matched for e in extracted], dtype=float)
    tokens = np.array([e.n_tokens for e in extracted], dtype=float)
    match_rate = float(np.divide(matched, np.maximum(tokens, 1)).mean())
    polarization = float(ta.polarization(extracted))

    metrics = [
        metric("scored", "Documents scored", int(len(sample)), "int"),
        metric("dimensions", "Dimensions extracted", len(dims), "int"),
        metric("focus_mean", "%s, mean" % dimension.replace("_", " "),
               float(scored[dimension].mean()), "float4"),
        metric("focus_sd", "%s, spread" % dimension.replace("_", " "),
               float(scored[dimension].std(ddof=1)) if len(scored) > 1 else 0.0,
               "float4"),
        metric("match_rate", "Lexicon match rate", match_rate, "pct",
               "share of tokens the lexicon recognised"),
        metric("polarization", "Polarization", polarization, "float4",
               "disagreement in valence across the scored documents"),
    ]
    top_group = grouped.iloc[0] if len(grouped) else None
    observations = [
        "Extraction ran during this request over %d of the %d documents matching your "
        "selection." % (len(sample), len(df)),
    ]
    if top_group is not None:
        observations.append(
            "%s scores highest for %s at %.4f, over %d documents."
            % (str(top_group[key]), dimension.replace("_", " "),
               float(top_group["%s_mean" % dimension]), int(top_group["documents"])))
    observations.append(
        "These dimensions are lexicon matches over generated text, not measurements of "
        "anyone's state. The corpus is written by this project (L-04), and a dimension "
        "named for an emotion is a word-count under that name.")

    return AnalysisResult(
        dataset=live.describe_slice(df, "data/panel/text_corpus.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments, dimension=dimension,
                                    group_by=key, sample_size=sample_size),
        metrics=metrics,
        series=[
            series("dimensions", "Affect dimensions on this slice",
                   list(summary.columns), summary.values.tolist(),
                   "nonzero_share is how many documents scored the dimension at all"),
            series("grouped", "%s by %s" % (dimension.replace("_", " "), key),
                   list(grouped.columns), grouped.values.tolist(),
                   "means over the sampled documents in each group"),
        ],
        observations=observations,
        uncertainty={
            "kind": "sampling",
            "n_sampled": int(len(sample)),
            "n_available": int(len(df)),
            "reading": ("Means over %d documents drawn with a fixed seed from the %d "
                        "that matched, so the same selection returns the same "
                        "documents. A group with few documents in the table below has "
                        "a mean that moves a great deal; the count is shown beside it."
                        % (len(sample), len(df))),
        },
        provenance={"canonical_called": ["research.text.affect:extract",
                                         "research.text.affect:polarization"],
                    "extractor_version": extracted[0].extractor_version,
                    "lexicon_version": extracted[0].lexicon_version,
                    "sample_seed": 20260818, "wrote_nothing": True},
        message="%d documents scored across %d dimensions" % (len(sample), len(dims)),
    )


# -------------------------------------------------------------- MULTIMODAL-03 ----

def _analyse_supplied_text(text: str) -> AnalysisResult:
    """Score one document the caller provided, with the same extractor.

    Two things this must not be allowed to become, and the wording is chosen to prevent
    both. It is not a reading of whoever wrote the text: the dimensions are counts of
    lexicon matches, and a high "fear" score means fear-listed words were present, not
    that anyone was afraid. And it is not a general-purpose sentiment service: the lexicon
    was built for financial commentary, so the match rate on anything else will be low and
    is reported first for exactly that reason.
    """
    from research.text import affect as ta

    body = str(text).strip()
    if len(body.split()) < 5:
        return insufficient(
            "the supplied text holds %d word(s); a lexicon match rate over that many "
            "means nothing" % len(body.split()),
            "Supply a paragraph rather than a phrase.")

    result = ta.extract(body, source_credibility=1.0)
    matched = float(result.n_matched)
    tokens = float(max(1, result.n_tokens))
    match_rate = matched / tokens

    # The declared dimensions only. `scores` also carries the source-credibility weight
    # that was passed in, and reporting an input back as the strongest "dimension" would
    # be reporting the caller's own argument as a finding.
    table = (pd.DataFrame([{"dimension": d, "score": float(result.scores[d])}
                           for d in ta.TEXT_AFFECT_DIMENSIONS
                           if d in result.scores])
             .sort_values("score", ascending=False))
    top = table.iloc[0]

    metrics = [
        metric("words", "Words in the document", len(body.split()), "int"),
        metric("tokens", "Tokens the extractor saw", int(tokens), "int"),
        metric("matched", "Tokens the lexicon recognised", int(matched), "int"),
        metric("match_rate", "Lexicon match rate", match_rate, "pct",
               "the share of the document these scores actually rest on"),
        metric("top_dimension", "Strongest dimension", str(top["dimension"]), "text"),
        metric("top_score", "Its score", float(top["score"]), "float4"),
    ]
    observations = [
        "Scored during this request. The document was read into memory and not stored; "
        "nothing was written anywhere.",
        "The lexicon recognised %.1f%% of the tokens. Every score below rests on that "
        "fraction of the text and on nothing else." % (100 * match_rate),
        "These dimensions count words from a list built for financial commentary. A high "
        "score on a dimension named for an emotion means words on that list appeared; it "
        "is not a statement about the author, their state, or their intent.",
    ]
    if match_rate < 0.05:
        observations.append(
            "At this match rate the scores are close to meaningless: almost nothing in "
            "this document is in the lexicon. That is the expected result for text "
            "outside the financial domain the lexicon was built for.")

    return AnalysisResult(
        dataset={"source": "supplied by the caller",
                 "rows": 1,
                 "selection": {"characters": len(body), "stored": False}},
        metrics=metrics,
        series=[series("dimensions", "Every dimension on this document",
                       list(table.columns), table.values.tolist(),
                       "one row per declared dimension, highest first")],
        observations=observations,
        uncertainty={
            "kind": "single_document",
            "match_rate": match_rate,
            "reading": ("One document, scored by lexicon match. There is no interval "
                        "here because nothing was estimated from a sample, and no "
                        "reliability either: a single document's score moves entirely "
                        "with which listed words happen to appear in it."),
        },
        provenance={"canonical_called": ["research.text.affect:extract"],
                    "extractor_version": result.extractor_version,
                    "lexicon_version": result.lexicon_version,
                    "supplied_by_caller": True,
                    "stored_anywhere": False,
                    "wrote_nothing": True},
        message="%d words scored, %.1f%% of tokens matched"
                % (len(body.split()), 100 * match_rate),
    )


def analyse_text_block(date_from: str | None = None, date_to: str | None = None,
                       instruments: list[str] | None = None,
                       split: str = "all") -> AnalysisResult:
    """MULTIMODAL-03 live: the text feature block on the selected rows."""
    return _analyse_block(
        "text",
        "Text features summarise the documents available on or before each session, so a "
        "row's text block never contains a document published after it.",
        date_from, date_to, instruments, split)


# -------------------------------------------------------------- MULTIMODAL-04 ----

def analyse_image_render(symbol: str = "RELIANCE", as_of: str | None = None,
                         lookback: int = 60) -> AnalysisResult:
    """MULTIMODAL-04 live: render a chart from the market window and read it back.

    The whole modality in one request: the price window is rasterised by the canonical
    chart generator and the resulting pixels are passed to the canonical image pipeline,
    which extracts the same visual-affect dimensions the panel's image block carries.

    What this cannot be is independent evidence. The image is a rendering of the market
    series; anything the extractor finds in it was put there by the renderer.
    """
    from research.image import chartgen, pipeline
    from scripts.stages import live

    cash = live.cash_panel()
    sym = _one_symbol(symbol)
    hist = cash[cash["symbol"].str.upper() == sym].sort_values("date")
    if as_of:
        hist = hist[hist["date"] <= pd.Timestamp(as_of)]
    if len(hist) < int(lookback) + 1:
        return insufficient(
            "%s has %d sessions on or before that date; the %d-session window needs more"
            % (sym, len(hist), int(lookback)),
            "Choose a later date, a longer history, or a shorter lookback.")

    window = hist.tail(int(lookback))
    raster = chartgen.rasterize_window(hist.reset_index(drop=True),
                                       upto_index=len(hist) - 1,
                                       lookback=int(lookback))
    rgb = raster if raster.ndim == 3 else np.dstack([raster] * 3)
    affect = pipeline.visual_affect(rgb)

    table = pd.DataFrame([{"dimension": k, "value": float(v)}
                          for k, v in affect.items()]).sort_values(
                              "value", ascending=False)
    first, last = float(window["close"].iloc[0]), float(window["close"].iloc[-1])

    metrics = [
        metric("sessions", "Sessions rendered", int(len(window)), "int"),
        metric("window_from", "Window opens",
               str(window["date"].iloc[0].date()), "text"),
        metric("window_to", "Window closes",
               str(window["date"].iloc[-1].date()), "text"),
        metric("window_change", "Change across the window",
               (last - first) / first if first else float("nan"), "pct",
               "a property of the prices, not of the rendering"),
        metric("pixels", "Raster size", "%d x %d" % (rgb.shape[0], rgb.shape[1]),
               "text"),
        metric("dimensions", "Visual dimensions extracted", len(affect), "int"),
    ]
    strongest = table.iloc[0]
    return AnalysisResult(
        dataset={"source": "data/panel/cash_panel.parquet",
                 "rows": int(len(window)),
                 "date_from": str(window["date"].iloc[0].date()),
                 "date_to": str(window["date"].iloc[-1].date()),
                 "selection": {"symbol": sym, "as_of": as_of,
                               "lookback": int(lookback)}},
        metrics=metrics,
        series=[series("visual_affect", "Visual dimensions of the rendered chart",
                       list(table.columns), table.values.tolist(),
                       "extracted from the raster this request produced")],
        observations=[
            "A %d-session chart for %s was rasterised and read back during this request."
            % (len(window), sym),
            "The strongest dimension on this rendering is %s at %.4f."
            % (strongest["dimension"], float(strongest["value"])),
            "This image was drawn from the price series by this project. It is a second "
            "view of the same numbers and carries no information the market data did not "
            "already contain; it is never independent visual evidence (L-05).",
        ],
        uncertainty={
            "kind": "deterministic",
            "reading": ("The renderer and the extractor are both deterministic, so "
                        "this request returns the same numbers every time for the "
                        "same window. What varies is the window, and the dimensions "
                        "move with the shape of the prices in it."),
        },
        provenance={"canonical_called": ["research.image.chartgen:rasterize_window",
                                         "research.image.pipeline:visual_affect"],
                    "chart_version": chartgen.CHART_VERSION,
                    "extractor_version": pipeline.EXTRACTOR_VERSION,
                    "symbol": sym, "wrote_nothing": True},
        message="%s rendered over %d sessions and read back" % (sym, len(window)),
    )


# -------------------------------------------------------------- MULTIMODAL-05 ----

def analyse_image_block(date_from: str | None = None, date_to: str | None = None,
                        instruments: list[str] | None = None,
                        split: str = "all") -> AnalysisResult:
    """MULTIMODAL-05 live: the image feature block on the selected rows."""
    return _analyse_block(
        "image",
        "Every image feature is computed from a chart this project rendered from the "
        "market series, so the block is a transformation of market data rather than a "
        "separate observation of the world (L-05).",
        date_from, date_to, instruments, split)


# -------------------------------------------------------------- MULTIMODAL-06 ----

def analyse_sonification(symbol: str = "RELIANCE", as_of: str | None = None,
                         lookback: int = 60) -> AnalysisResult:
    """MULTIMODAL-06 live: sonify a market window and extract its acoustic features.

    The canonical sonifier turns a price and volume window into a waveform; the canonical
    audio pipeline then extracts from that waveform the features the panel's audio block
    carries. Both run during this request.

    The waveform contains no speech. Nothing here is a voice, and the features named for
    prosody describe an oscillator driven by prices.
    """
    from research.audio import pipeline as ap
    from research.audio import sonify as sn
    from scripts.stages import live

    cash = live.cash_panel()
    sym = _one_symbol(symbol)
    hist = cash[cash["symbol"].str.upper() == sym].sort_values("date")
    if as_of:
        hist = hist[hist["date"] <= pd.Timestamp(as_of)]
    if len(hist) < int(lookback):
        return insufficient(
            "%s has %d sessions on or before that date; the %d-session window needs more"
            % (sym, len(hist), int(lookback)),
            "Choose a later date or a shorter lookback.")

    window = hist.tail(int(lookback))
    close = window["close"].to_numpy(float)
    volume = (window["volume"].to_numpy(float) if "volume" in window.columns else None)
    wave = sn.sonify(close, volume)
    sr = sn.SR
    feats = ap.extract_from_array(wave, sr, name="%s sonification" % sym)
    values = (feats.features if hasattr(feats, "features")
              else feats.to_dict() if hasattr(feats, "to_dict") else dict(feats))
    values = {k: v for k, v in values.items() if isinstance(v, (int, float))}
    affect = ap.audio_affect(values)

    table = pd.DataFrame([{"feature": k, "value": float(v)}
                          for k, v in values.items() if isinstance(v, (int, float))])
    affect_table = pd.DataFrame([{"dimension": k, "value": float(v)}
                                 for k, v in affect.items()])

    metrics = [
        metric("sessions", "Sessions sonified", int(len(window)), "int"),
        metric("samples", "Waveform samples", int(len(wave)), "int"),
        metric("sample_rate", "Sample rate", int(sr), "int"),
        metric("duration", "Duration", float(len(wave) / max(1, sr)), "float2",
               "seconds of audio generated for this window"),
        metric("features", "Acoustic features extracted", int(len(table)), "int"),
    ]
    return AnalysisResult(
        dataset={"source": "data/panel/cash_panel.parquet",
                 "rows": int(len(window)),
                 "date_from": str(window["date"].iloc[0].date()),
                 "date_to": str(window["date"].iloc[-1].date()),
                 "selection": {"symbol": sym, "as_of": as_of,
                               "lookback": int(lookback)}},
        metrics=metrics,
        series=[
            series("acoustic", "Acoustic features of this sonification",
                   list(table.columns), table.values.tolist(),
                   "extracted from the waveform this request generated"),
            series("audio_affect", "Affect proxies derived from those features",
                   list(affect_table.columns), affect_table.values.tolist(),
                   "derived quantities, not measurements of a speaker"),
        ],
        observations=[
            "A %d-session window for %s was sonified and analysed during this request."
            % (len(window), sym),
            "The waveform is generated from prices and volumes. It contains no speech, "
            "no voice and no recording of any person, so nothing extracted from it "
            "describes how anyone sounded (L-06).",
            "Features named for pitch and prosody describe an oscillator whose frequency "
            "the price series controls.",
        ],
        uncertainty={
            "kind": "deterministic",
            "reading": ("The sonifier and the extractor are deterministic: the same "
                        "window yields the same waveform and the same features every "
                        "time. Changing the window changes them."),
        },
        provenance={"canonical_called": ["research.audio.sonify:sonify",
                                         "research.audio.pipeline:extract_from_array",
                                         "research.audio.pipeline:audio_affect"],
                    "symbol": sym, "sample_rate": int(sr), "wrote_nothing": True},
        message="%d sessions sonified into %.1fs of audio"
                % (len(window), len(wave) / max(1, sr)),
    )


# -------------------------------------------------------------- MULTIMODAL-07 ----

def analyse_audio_block(date_from: str | None = None, date_to: str | None = None,
                        instruments: list[str] | None = None,
                        split: str = "all") -> AnalysisResult:
    """MULTIMODAL-07 live: the audio feature block on the selected rows."""
    return _analyse_block(
        "audio",
        "These features are computed from sonified market data, not from recorded "
        "speech. A dimension named for prosody describes a generated waveform (L-06).",
        date_from, date_to, instruments, split)


# -------------------------------------------------------------- MULTIMODAL-09 ----

def analyse_video_block(date_from: str | None = None, date_to: str | None = None,
                        instruments: list[str] | None = None,
                        split: str = "all") -> AnalysisResult:
    """MULTIMODAL-09 live: the video feature block on the selected rows."""
    return _analyse_block(
        "video",
        "Video features come from clips this project rendered from the market series. No "
        "broadcast footage is downloaded, stored or analysed anywhere in this system.",
        date_from, date_to, instruments, split)


# -------------------------------------------------------------- MULTIMODAL-10 ----

def analyse_media_licence(source_url: str = "", publisher: str = "",
                          licence_name: str = "") -> AnalysisResult:
    """MULTIMODAL-10 live: classify a media reference against the licence rules.

    The checker runs offline against domain rules and whatever the caller declares. It
    never fetches the URL: this module answers "may this be redistributed", and asking the
    host would neither answer that question nor be appropriate from a research service.

    The rules are deliberately conservative. Anything not explicitly known is UNKNOWN, and
    UNKNOWN media never reaches a publication artifact.
    """
    from research.core import licensing as lic

    url = str(source_url or "").strip()
    if not url:
        return insufficient(
            "no media reference was supplied",
            "Enter the source URL of the reference you want classified.")
    if not url.lower().startswith(("http://", "https://")):
        return insufficient(
            "a media reference must be an http or https URL",
            "Enter the full address, beginning with https://.")

    checker = lic.MediaLicenseChecker()
    verdict = checker.check(url, publisher=publisher or None,
                            licence_name=licence_name or None)
    status_name = verdict.status.value
    reason = getattr(verdict, "evidence", "") or ""
    # Ask the record, not a membership test against the enum: the statuses that may be
    # redistributed are the checker's business and restating them here would let the two
    # disagree the first time the vocabulary changes.
    redistributable = bool(verdict.may_redistribute())

    rules = pd.DataFrame(
        [{"category": "open", "hosts": ", ".join(checker.OPEN_HOSTS)},
         {"category": "embed only", "hosts": ", ".join(checker.EMBED_ONLY_HOSTS)},
         {"category": "restricted", "hosts": ", ".join(checker.RESTRICTED_HOSTS)}])

    metrics = [
        metric("status", "Licence status", status_name, "text",
               "the classification these rules assign"),
        metric("redistributable", "May be redistributed",
               "yes" if redistributable else "no", "text",
               "whether the media itself may travel with an artifact"),
        metric("statuses", "Statuses in the vocabulary",
               len(list(lic.LicenseStatus)), "int"),
    ]
    observations = [
        "Classified during this request from the address you entered. The URL was not "
        "fetched: nothing about it was requested from its host.",
        reason or "The classification follows from the host and what you declared.",
        "Public accessibility is not permission to redistribute. Where redistribution is "
        "not permitted, this project stores reference metadata instead of media.",
    ]
    if not redistributable:
        observations.append(
            "Because this reference is not classified as redistributable, the media "
            "itself would not be copied into any artifact; only the reference would be "
            "recorded.")

    return AnalysisResult(
        dataset={"source": "research/core/licensing.py",
                 "rows": 1,
                 "selection": {"source_url": url, "publisher": publisher,
                               "licence_name": licence_name}},
        metrics=metrics,
        series=[
            series("rules", "The host rules this verdict came from",
                   list(rules.columns), rules.values.tolist(),
                   "anything outside these lists defaults to UNKNOWN, never to "
                   "permissive"),
            series("vocabulary", "Statuses the checker can assign", ["status"],
                   [[s.value] for s in lic.LicenseStatus], ""),
        ],
        observations=observations,
        uncertainty={
            "kind": "rule_based",
            "reading": ("This is a rule lookup, not a legal determination. A "
                        "conservative UNKNOWN is the expected answer for most "
                        "addresses, and it means the rules do not cover the host "
                        "rather than that redistribution is forbidden."),
        },
        provenance={"canonical_called": ["research.core.licensing:MediaLicenseChecker",
                                         "research.core.licensing:LicenseStatus"],
                    "fetched_the_url": False, "wrote_nothing": True},
        message="%s classified as %s" % (url[:60], status_name),
    )


# -------------------------------------------------------------- MULTIMODAL-11 ----

def analyse_alignment(modality: str = "text", max_offset: int = 10,
                      seed: int = 20260818) -> AnalysisResult:
    """MULTIMODAL-11 live: delay one modality and measure what it costs.

    The model is fitted on the training split during this request and then scored with one
    modality's features shifted forward in time. Forward is the only realistic direction:
    media arrives later than market data, never earlier.
    """
    from research.data import dataset as ds
    from research.evaluation import temporal_analysis as ta
    from research.models.risk_model import AegisRiskModel
    from scripts.stages import live

    if modality not in ds.MODALITY_BLOCKS:
        return insufficient(
            "%r is not a declared modality block" % modality,
            "Choose one of: %s." % ", ".join(ds.MODALITY_BLOCKS))

    df = live.panel()
    train = df[df["split"] == "train"]
    evald = df[df["split"] == "validation"]
    if len(train) < 100 or len(evald) < 50:
        return insufficient(
            "the panel does not hold enough train and validation rows to fit and score",
            "Rebuild the dataset before running this module.")

    block_columns = [c for c in ds.MODALITY_BLOCKS[modality] if c in df.columns]
    if not block_columns:
        return insufficient(
            "the %s block has no columns in the panel" % modality,
            "Choose a modality the panel actually carries.")

    offsets = tuple(o for o in (0, 1, 3, 5, 10, 20) if o <= int(max_offset))
    model = AegisRiskModel(modalities=list(ds.MODALITY_BLOCKS),
                           fusion_strategy="regime_corrected", seed=int(seed))
    model.fit(train, train["is_episode"].to_numpy(int))
    table = ta.asynchrony_sensitivity(evald, model, modality, block_columns,
                                      offsets=offsets)

    ok = table[table["status"] == "OK"]
    base = float(ok.loc[ok["offset_sessions"] == 0, "auprc"].iloc[0]) if len(
        ok[ok["offset_sessions"] == 0]) else float("nan")
    worst = ok.sort_values("auprc").iloc[0] if len(ok) else None

    metrics = [
        metric("modality", "Modality delayed", modality, "text"),
        metric("columns", "Columns shifted", len(block_columns), "int"),
        metric("base_auprc", "AUPRC with no delay", base, "float4"),
        metric("worst_auprc", "AUPRC at the largest delay tested",
               float(worst["auprc"]) if worst is not None else float("nan"), "float4"),
        metric("loss", "Loss across the range",
               base - float(worst["auprc"]) if worst is not None else float("nan"),
               "float4"),
        metric("eval_rows", "Evaluation rows", int(len(evald)), "int"),
    ]
    observations = [
        "The model was fitted on the training split during this request, then scored "
        "with the %s block shifted forward by each offset." % modality,
    ]
    if worst is not None:
        observations.append(
            "A delay of %d session(s) costs %.4f AUPRC on this evaluation split."
            % (int(worst["offset_sessions"]), base - float(worst["auprc"])))
    observations.append(
        "Shifting forward simulates evidence arriving later than the system assumes. "
        "Shifting backward would simulate evidence arriving before it existed, which is "
        "the leakage the pipeline is built to prevent, so it is not offered here.")

    return AnalysisResult(
        dataset={"source": "data/panel/multimodal_dataset.parquet",
                 "rows": int(len(evald)),
                 "selection": {"modality": modality, "max_offset": int(max_offset),
                               "seed": int(seed)}},
        metrics=metrics,
        series=[series("offsets", "Detection quality against delay",
                       list(table.columns), table.values.tolist(),
                       "one row per offset, in sessions")],
        observations=observations,
        uncertainty={
            "kind": "single_seed",
            "seed": int(seed),
            "reading": ("One fit at one seed. Differences between adjacent offsets that "
                        "are smaller than the seed noise floor measured in STATS-16 "
                        "should not be read as a trend."),
        },
        provenance={"canonical_called": ["research.evaluation.temporal_analysis:"
                                         "asynchrony_sensitivity",
                                         "research.models.risk_model:AegisRiskModel"],
                    "modality": modality, "offsets": list(offsets),
                    "fitted_now": True, "wrote_nothing": True},
        message="%s delayed up to %d sessions" % (modality, int(max_offset)),
    )


# -------------------------------------------------------------- MULTIMODAL-12 ----

def analyse_assembly(date_from: str | None = None, date_to: str | None = None,
                     instruments: list[str] | None = None,
                     split: str = "all") -> AnalysisResult:
    """MULTIMODAL-12 live: how completely the modality blocks joined on these rows.

    Assembly is a join, and a join is judged by what it left behind. The figure that
    matters is not how many rows exist but how many carry every block at once, because a
    result computed on rows with three blocks and reported as multimodal is a different
    claim from one computed on rows with seven.
    """
    from research.data import dataset as ds
    from scripts.stages import live

    df = live.slice_frame(live.panel(), date_from, date_to, instruments, split)
    if len(df) < live.MIN_ROWS:
        return insufficient(
            "the selected slice holds %d rows, below the %d needed to describe the join"
            % (len(df), live.MIN_ROWS),
            "Widen the date range, or select more instruments.")

    rows, present_mask = [], None
    for block, cols in ds.MODALITY_BLOCKS.items():
        cols = [c for c in cols if c in df.columns]
        if not cols:
            rows.append({"block": block, "features": 0, "rows_with_any": 0,
                         "row_share": 0.0, "mean_fill": 0.0})
            continue
        any_present = df[cols].notna().any(axis=1)
        rows.append({"block": block, "features": len(cols),
                     "rows_with_any": int(any_present.sum()),
                     "row_share": float(any_present.mean()),
                     "mean_fill": float(df[cols].notna().mean().mean())})
        present_mask = any_present if present_mask is None else (
            present_mask & any_present)
    table = pd.DataFrame(rows).sort_values("row_share", ascending=False)
    complete = int(present_mask.sum()) if present_mask is not None else 0

    metrics = [
        metric("rows", "Rows in this slice", int(len(df)), "int"),
        metric("blocks", "Blocks joined", int(len(table)), "int"),
        metric("complete", "Rows carrying every block", complete, "int"),
        metric("complete_share", "Share complete",
               float(complete / max(1, len(df))), "pct",
               "rows where every modality block has at least one value"),
        metric("thinnest_block", "Thinnest block",
               str(table.iloc[-1]["block"]), "text",
               "the block present on the fewest rows here"),
    ]
    observations = [
        "%d of %d rows in your slice carry at least one value from every block."
        % (complete, len(df)),
        "A result computed on this slice is multimodal to the extent shown above and no "
        "further: rows missing a block were still scored, with that block absent.",
        "The key is one row per instrument-day and the join is by that key, so no "
        "document, image or clip can attach to a session earlier than the one it belongs "
        "to.",
    ]

    return AnalysisResult(
        dataset=live.describe_slice(df, "data/panel/multimodal_dataset.parquet",
                                    date_from=date_from, date_to=date_to,
                                    instruments=instruments, split=split),
        metrics=metrics,
        series=[series("blocks", "Block presence on this slice",
                       list(table.columns), table.values.tolist(),
                       "row_share is the fraction of rows with any value in the block; "
                       "mean_fill averages over the block's features")],
        observations=observations,
        uncertainty={"kind": "none",
                     "reading": "Counts over the assembled panel. What they bound is how "
                                "much of the multimodal claim these rows can carry."},
        provenance={"canonical_called": ["research.data.dataset:MODALITY_BLOCKS"],
                    "rows_complete": complete, "wrote_nothing": True},
        message="%d of %d rows carry every block" % (complete, len(df)),
    )


# -------------------------------------------------------------- MULTIMODAL-13 ----

def analyse_degeneracy(n_rows: int = 500, n_modalities: int = 8, n_regimes: int = 4,
                       regime_term_sd: float = 25.0,
                       seed: int = 20260818) -> AnalysisResult:
    """MULTIMODAL-13 live: run the degeneracy proof at parameters you choose.

    The claim is algebraic: under the inherited formulation ``softmax(s_m + g(r))`` the
    regime term is constant across modalities, so it cancels between numerator and
    denominator and the fused weights are identical to static attention. An algebraic
    identity should survive any parameterisation, so the controls exist to be pushed. Turn
    the regime term up to a hundred and the difference stays at machine precision; that is
    what makes it a proof rather than an observation.
    """
    import numpy as np

    from research.multimodal import fusion as fu

    n = max(50, min(int(n_rows), 5000))
    n_mod = max(2, min(int(n_modalities), 32))
    n_reg = max(2, min(int(n_regimes), 16))
    rng = np.random.default_rng(int(seed))
    logits = rng.normal(0, 1.5, n_mod)
    regime = rng.integers(0, n_reg, n)
    regime_scalar = rng.normal(0, float(regime_term_sd), n_reg)
    coverage = (rng.random((n, n_mod)) > 0.2).astype(float)
    coverage[coverage.sum(axis=1) == 0, 0] = 1.0

    proof = fu.demonstrate_degeneracy(np.zeros((n, n_mod)), coverage, regime,
                                      logits, regime_scalar)
    diff = float(proof["max_abs_weight_difference"])
    table = pd.DataFrame([{"quantity": k, "value": v} for k, v in proof.items()])

    metrics = [
        metric("max_diff", "Largest weight difference", diff, "sci",
               "between regime-inherited fusion and static attention"),
        metric("rows", "Rows constructed", n, "int"),
        metric("modalities", "Modalities", n_mod, "int"),
        metric("regimes", "Regimes", n_reg, "int"),
        metric("regime_sd", "Regime term spread", float(regime_term_sd), "float2",
               "how large the term that is supposed to matter was made"),
    ]
    machine_precision = diff < 1e-9
    observations = [
        "Constructed and checked during this request at the parameters you set.",
        ("The largest difference between the two fusions is %.3e, which is machine "
         "precision: with a regime term of spread %.1f, the regime-inherited weights are "
         "the static weights." % (diff, regime_term_sd)) if machine_precision else
        ("The largest difference is %.3e, above machine precision. At these parameters "
         "the two fusions are not identical." % diff),
        "This is why the project uses the regime-corrected formulation instead. The "
        "inherited one does not fail to work; it works as static attention while "
        "appearing to condition on regime.",
    ]
    return AnalysisResult(
        dataset={"source": "constructed in memory for this request",
                 "rows": n,
                 "selection": {"n_rows": n, "n_modalities": n_mod,
                               "n_regimes": n_reg,
                               "regime_term_sd": float(regime_term_sd),
                               "seed": int(seed)}},
        metrics=metrics,
        series=[series("proof", "What the proof reports",
                       list(table.columns), table.values.tolist(),
                       "the record returned by demonstrate_degeneracy")],
        observations=observations,
        uncertainty={
            "kind": "analytic",
            "reading": ("Nothing is estimated here and no data is read. The result is "
                        "an algebraic identity, checked numerically at the parameters "
                        "above; the residual is floating-point error, not uncertainty "
                        "about the claim."),
        },
        provenance={"canonical_called": ["research.multimodal.fusion:"
                                         "demonstrate_degeneracy"],
                    "seed": int(seed), "reads_no_data": True, "wrote_nothing": True},
        message="largest weight difference %.3e over %d rows" % (diff, n),
    )


# -------------------------------------------------------------- MULTIMODAL-14 ----

def analyse_decomposition(modalities: list[str] | None = None,
                          date_from: str | None = None,
                          date_to: str | None = None) -> AnalysisResult:
    """MULTIMODAL-14 live: unique, shared and synergistic contribution per modality.

    Each modality needs two arms to be decomposed: one where it is the only evidence and
    one where it is the only evidence withheld. A modality with only the second is
    reported as NaN rather than guessed at, which is why the table below can be shorter
    than the modality list.
    """
    from research.evaluation import information as inf
    from scripts.run_research_angles import MODALITY_ARMS
    from scripts.stages import live

    available = set(live.available_arms())
    if "FULL" not in available:
        return insufficient(
            "the FULL arm has no per-row scores on disk",
            "Run `python scripts/run_module.py --module STATS-14` at a terminal.")

    wanted = [m for m in (modalities or list(MODALITY_ARMS))
              if m in MODALITY_ARMS]
    usable = {}
    for m in wanted:
        only, without = MODALITY_ARMS[m]
        if only in available and without in available:
            usable[m] = (only, without)
    if not usable:
        return insufficient(
            "none of the selected modalities has both a stand-alone and a "
            "leave-one-out arm on disk",
            "Choose from: %s." % ", ".join(sorted(
                m for m, (a, b) in MODALITY_ARMS.items()
                if a in available and b in available)))

    needed = {"FULL", *[a for pair in usable.values() for a in pair]}
    per_arm = {}
    for arm in sorted(needed):
        frame = live.per_row(arm)
        if frame is None:
            continue
        # Per-arm model scores: exempt by name in live.NON_BITEMPORAL_FRAMES.
        per_arm[arm] = live.slice_frame(frame, date_from, date_to, None,
                                        require_point_in_time=False)
    if any(len(f) < live.MIN_ROWS for f in per_arm.values()):
        return insufficient(
            "the selected window leaves fewer than %d scored rows in at least one arm"
            % live.MIN_ROWS,
            "Widen the date range.")

    table = inf.decomposition(per_arm, "FULL", usable)
    ranked = table.sort_values("unique", ascending=False) if "unique" in table.columns \
        else table
    top = ranked.iloc[0] if len(ranked) else None

    metrics = [
        metric("modalities", "Modalities decomposed", int(len(table)), "int"),
        metric("arms", "Arms read", len(per_arm), "int"),
        metric("rows", "Scored rows per arm",
               int(len(per_arm["FULL"])), "int"),
    ]
    if top is not None and "unique" in ranked.columns:
        metrics.append(metric("top_unique", "Largest unique contribution",
                              float(top["unique"]), "float4",
                              "modality %s" % top.iloc[0]))
    observations = [
        "Recomputed during this request from the stored per-row scores of %d arms; "
        "nothing was refitted." % len(per_arm),
    ]
    if top is not None and "unique" in ranked.columns:
        observations.append(
            "%s carries the largest unique contribution on these rows at %.4f AUPRC: "
            "that is what is lost when it alone is withheld."
            % (str(top.iloc[0]), float(top["unique"])))
    observations.append(
        "Unique, shared and synergistic are arithmetic on arm AUPRCs, not an information-"
        "theoretic decomposition. A modality with a small unique contribution may still "
        "be carrying evidence that another modality also carries.")

    return AnalysisResult(
        dataset={"source": "research_artifacts/experiments/per_row_*.parquet",
                 "rows": int(len(per_arm["FULL"])),
                 "selection": {"modalities": sorted(usable),
                               "date_from": date_from, "date_to": date_to}},
        metrics=metrics,
        series=[series("decomposition", "Contribution per modality on this slice",
                       list(table.columns), table.values.tolist(),
                       "NaN means one of the two arms that modality needs was not run")],
        observations=observations,
        uncertainty={
            "kind": "no_interval",
            "reading": ("Point differences between arm AUPRCs with no interval attached. "
                        "A contribution smaller than the seed noise floor from STATS-16 "
                        "is not distinguishable from reseeding the same arm."),
        },
        provenance={"canonical_called": ["research.evaluation.information:decomposition",
                                         "scripts.run_research_angles:MODALITY_ARMS"],
                    "modalities": sorted(usable), "refitted": False,
                    "wrote_nothing": True},
        message="%d modalities decomposed over %d arms" % (len(table), len(per_arm)),
    )


# -------------------------------------------------------------- MULTIMODAL-15 ----

def analyse_missingness(modality: str = "text", fraction: float = 0.5,
                        seed: int = 20260818) -> AnalysisResult:
    """MULTIMODAL-15 live: take one modality offline for part of the evaluation rows.

    The blackout blanks the block's columns *and* its coverage flag. Blanking the columns
    alone leaves the fusion layer reading a coverage flag that still says the modality is
    present, so the modality keeps voting with nothing behind it and the result comes out
    too optimistic. That asymmetry is exactly how an induced-missingness experiment
    flatters itself.
    """
    from research.evaluation import robustness as rb
    from scripts.stages import live

    data = live.panel()
    work = rb.working_set(data)
    train = work[work["split"] == "train"]
    evald = work[work["split"] == "validation"]
    if not rb.modality_columns(work, modality):
        return insufficient(
            "the %s block has no columns in the panel" % modality,
            "Choose a modality block the panel carries.")

    frac = max(0.0, min(float(fraction), 1.0))
    clean = rb.fit_and_score(train, evald, list(rb.ds.MODALITY_BLOCKS), int(seed),
                             "clean", "every modality present")
    if clean.status != "OK":
        return insufficient(
            "the reference fit did not complete: %s" % clean.reason,
            "This is a condition of the data, not of your selection.")

    dark = rb.blackout_modality(evald, modality, frac, int(seed))
    hit = rb.fit_and_score(train, dark, list(rb.ds.MODALITY_BLOCKS), int(seed),
                           "%s_dark_%.2f" % (modality, frac),
                           "one modality offline for part of the evaluation rows")
    if hit.status != "OK":
        return insufficient(
            "the blackout fit did not complete: %s" % hit.reason,
            "Try a smaller fraction.")

    base = float(clean.metrics.get("auprc", float("nan")))
    after = float(hit.metrics.get("auprc", float("nan")))
    table = pd.DataFrame([
        {"condition": "all modalities present", **dict(clean.metrics)},
        {"condition": "%s offline on %.0f%% of rows" % (modality, 100 * frac),
         **dict(hit.metrics)},
    ])

    metrics = [
        metric("base_auprc", "AUPRC with every modality", base, "float4"),
        metric("dark_auprc", "AUPRC with %s offline" % modality, after, "float4"),
        metric("loss", "Loss in AUPRC", base - after, "float4"),
        metric("fraction", "Rows affected", frac, "pct"),
        metric("columns", "Columns taken offline",
               len(rb.modality_columns(work, modality)), "int"),
        metric("eval_rows", "Evaluation rows", int(len(evald)), "int"),
    ]
    observations = [
        "Run now: %s taken offline for %.0f%% of the evaluation rows, coverage flag "
        "included, with the model fitted once on complete data."
        % (modality, 100 * frac),
        "AUPRC moves from %.4f to %.4f, a loss of %.4f." % (base, after, base - after),
        "A small loss here means the remaining modalities carry evidence this one also "
        "carries. It does not mean the modality is uninformative, and it is not a reason "
        "to remove it.",
        "The frozen holdout was not read.",
    ]
    return AnalysisResult(
        dataset={"source": "data/panel/multimodal_dataset.parquet",
                 "rows": int(len(evald)),
                 "selection": {"modality": modality, "fraction": frac,
                               "seed": int(seed)}},
        metrics=metrics,
        series=[series("conditions", "Present against offline",
                       list(table.columns), table.values.tolist(),
                       "both rows produced by the canonical fit-and-score path")],
        observations=observations,
        uncertainty={
            "kind": "single_seed",
            "seed": int(seed),
            "reading": ("One blackout draw at one seed. Which rows lost the modality is "
                        "random, and a different seed moves the result by roughly the "
                        "noise floor measured in STATS-16."),
        },
        provenance={"canonical_called": ["research.evaluation.robustness:"
                                         "blackout_modality",
                                         "research.evaluation.robustness:fit_and_score"],
                    "modality": modality, "fraction": frac, "seed": int(seed),
                    "coverage_flag_cleared": True, "holdout_read": False,
                    "wrote_nothing": True},
        message="%s offline on %.0f%% of rows costs %.4f AUPRC"
                % (modality, 100 * frac, base - after),
    )
