"""Regenerate every paper asset from the experiment artifacts.

    python scripts/generate_paper_artifacts.py

Reads only files produced by ``build_panel.py``, ``build_dataset.py`` and
``run_experiments.py``. Writes figures (png/pdf/svg), tables (csv/json/md/tex), captions,
statistics, the XAI benchmark, the capital-consequence study, and the assembled
``paper_package/``.

Figures whose input artifact is missing are recorded in the manifest as ``NOT GENERATED``
with the reason. Nothing is drawn from data that does not exist.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
import traceback
import warnings
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from research.claims import ledger as cl
from research.core import paths, progress
from research.core.manifest import ReproducibilityManifest, environment_snapshot
from research.data import dataset as ds
from research.detection import state as st
from research.evaluation import ablations as ab
from research.evaluation import metrics as mx
from research.limitations import registry as reg
from research.models.risk_model import AegisRiskModel
from research.multimodal.fusion import softmax
from research.propagation import graph as pg
from research.regime import detection as rd
from research.risk.gate import CostModel, GatePolicy, capital_consequence
from research.text import affect as ta
from research.visualization import figures as F
from research.visualization.registry import FigureRegistry, TableRegistry
from research.xai import benchmark as xb
from research.xai import methods as xm
from research.xai import sanity as xs

RUN_ID = "paper_%s" % datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
EXPERIMENT_ID = "aegis_main"
SCRIPT = "scripts/generate_paper_artifacts.py"

skipped: list[dict] = []


def skip(figure_id: str, reason: str) -> None:
    skipped.append({"artifact": figure_id, "status": "NOT GENERATED", "reason": reason})
    progress.log("  SKIP %-34s %s" % (figure_id, reason))


def guard(figure_id: str):
    """Decorator-ish helper: run a block, record a skip if it raises."""
    class _G:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            if exc is not None:
                skip(figure_id, "%s: %s" % (exc_type.__name__, exc))
                if "-v" in sys.argv:
                    traceback.print_exception(exc_type, exc, tb)
                return True
            return False
    return _G()


def main() -> int:
    t0 = time.time()
    paths.ensure_dirs()
    progress.log("paper artifact generation %s" % RUN_ID)

    figs = FigureRegistry(EXPERIMENT_ID, RUN_ID)
    tabs = TableRegistry(EXPERIMENT_ID, RUN_ID)

    exp_dir = paths.ARTIFACTS / "experiments"
    data_path = paths.PANEL / "multimodal_dataset.parquet"
    if not data_path.exists():
        raise SystemExit("dataset missing: run scripts/build_dataset.py first")
    data = pd.read_parquet(data_path)
    panel = pd.read_parquet(paths.PANEL / "cash_panel.parquet")
    universe = pd.read_parquet(paths.PANEL / "universe.parquet")

    ablation = (pd.read_csv(exp_dir / "ablation_results.csv")
                if (exp_dir / "ablation_results.csv").exists() else pd.DataFrame())
    baselines = (pd.read_csv(exp_dir / "baseline_results.csv")
                 if (exp_dir / "baseline_results.csv").exists() else pd.DataFrame())
    stats = (pd.read_csv(exp_dir / "ablation_statistics.csv")
             if (exp_dir / "ablation_statistics.csv").exists() else pd.DataFrame())

    train = data[data["split"] == "train"]
    evald = data[data["split"] == "validation"]
    y_tr = train["is_episode"].to_numpy(int)
    y_ev = evald["is_episode"].to_numpy(int)
    dataset_label = "NSE cash panel + injected synthetic episodes"

    # ---------------------------------------------------------------- schematics ----
    progress.log("[1] schematic figures")
    with guard("fig01_architecture"):
        figs.save(F.fig_architecture(), "fig01_architecture",
                  title="System architecture",
                  caption="AEGIS-Market architecture. Evidence enters a bitemporal store "
                          "that answers every query as of a stated knowledge cutoff; "
                          "modality extractors, market and regime features and the "
                          "propagation graph feed a fusion layer whose output is an "
                          "integrity-risk estimate with uncertainty and coverage. The "
                          "research exposure gate and the paper-artifact pipeline are "
                          "downstream consumers.",
                  placement="MAIN", dataset=dataset_label,
                  source_data="schematic; no data plotted", generation_script=SCRIPT)
    with guard("fig04_state_machine"):
        figs.save(F.fig_state_machine(), "fig04_state_machine",
                  title="Temporal integrity-risk state machine",
                  caption="States used to characterise an episode over time. Entry and "
                          "exit are governed by separate thresholds with persistence "
                          "requirements; states may be skipped and any elevated state "
                          "may return to NORMAL without reaching PEAK.",
                  placement="MAIN", dataset=dataset_label,
                  source_data="schematic; no data plotted", generation_script=SCRIPT)

    # ------------------------------------------------------------------- data ----
    progress.log("[2] data and universe figures")
    with guard("fig06_universe"):
        from research.data.universe import LiquidityProxyUniverse
        u = LiquidityProxyUniverse(panel, size=50)
        u._table = universe
        figs.save(F.fig_universe_coverage(universe, u.churn()), "fig06_universe",
                  title="Point-in-time research universe",
                  caption="Membership and churn of the point-in-time liquidity-proxy "
                          "universe (top 50 by trailing median traded value, rebalanced "
                          "monthly, estimated only from sessions preceding each "
                          "rebalance). Non-zero churn is direct evidence that the "
                          "universe is not a survivorship-biased snapshot. This is not "
                          "the Nifty 50: no licence-clear point-in-time constituent "
                          "history was available (limitation L-01).",
                  placement="MAIN", dataset="NSE cash bhavcopy 2005-2026",
                  source_data=str(paths.PANEL / "universe.parquet"),
                  generation_script=SCRIPT)

    with guard("fig07_regimes"):
        feat_cols = ["date", "symbol", "close", "prev_close", "turnover"]
        sub = panel[feat_cols].copy()
        sub["logret"] = np.log(sub["close"]) - np.log(sub["prev_close"])
        desc = rd.index_descriptors(sub)
        # Named `regime_labels`, not `reg`: `reg` is the module alias for the limitations
        # registry, and a local assignment here shadows it for the whole function -- the
        # second time this exact failure mode has bitten this script.
        regime_labels = data[["date", "regime_id"]].drop_duplicates().dropna()
        figs.save(F.fig_regimes(desc, regime_labels), "fig07_regimes",
                  title="Market regimes",
                  caption="Equal-weighted market descriptors coloured by the fitted "
                          "Gaussian-mixture regime. The mixture is fitted on the "
                          "training window only and applied forward; the number of "
                          "components is chosen by BIC subject to a pre-declared "
                          "admissibility rule on minimum occupancy and persistence.",
                  placement="MAIN", dataset=dataset_label,
                  source_data=str(data_path), generation_script=SCRIPT)

    # --------------------------------------------------------------- main model ----
    progress.log("[3] fitting the reference model for XAI and capital analysis")
    full_arm = [a for a in ab.all_arms() if a.name == "FULL"][0]
    model = AegisRiskModel(modalities=list(full_arm.modalities),
                           fusion_strategy=full_arm.fusion)
    model.fit(train, y_tr)
    pred_tr = model.predict(train)
    pred_ev = model.predict(evald)
    thr = mx.best_f1_threshold(y_tr, pred_tr["integrity_risk"])
    det_full = mx.detection_metrics(y_ev, pred_ev["integrity_risk"], threshold=thr)
    progress.log("    FULL auprc=%.4f auroc=%.4f thr=%.3f"
                 % (det_full["auprc"], det_full["auroc"], thr))

    scored = evald[["symbol", "date", "is_episode", "episode_id", "t_entry",
                    "t_exit", "state"]].copy()
    scored["integrity_risk"] = pred_ev["integrity_risk"]
    scored["uncertainty"] = pred_ev["uncertainty"]
    scored["coverage"] = pred_ev["coverage"]
    scored = st.apply_to_frame(scored, "integrity_risk")

    # ---------------------------------------------------------------- detection ----
    progress.log("[4] detection, calibration and temporal figures")
    with guard("fig13_precision_recall"):
        from sklearn.metrics import precision_recall_curve
        curves = {}
        pre, rec, _ = precision_recall_curve(y_ev, pred_ev["integrity_risk"])
        curves["AEGIS (full stack)"] = (rec, pre)
        for name in ("market_only", "text_only", "statistical_anomaly"):
            f = exp_dir / ("per_row_%s.parquet" % name.upper())
            if f.exists():
                d = pd.read_parquet(f)
                p, r, _ = precision_recall_curve(d["is_episode"], d["integrity_risk"])
                curves[name] = (r, p)
        figs.save(F.fig_pr_curves(curves, float(y_ev.mean())), "fig13_precision_recall",
                  title="Detection precision-recall",
                  caption="Precision-recall on the validation split for the full "
                          "evidence stack and comparison arms. The dotted line is the "
                          "no-skill baseline, equal to the positive rate (%.3f); AUPRC "
                          "must be read against it because it has no fixed chance level. "
                          "Positives are injected synthetic episodes (limitation L-04)."
                          % float(y_ev.mean()),
                  placement="MAIN", dataset=dataset_label,
                  source_data=str(data_path), generation_script=SCRIPT)

    with guard("fig14_calibration"):
        rel = {"AEGIS (full stack)":
               mx.reliability_curve(y_ev, pred_ev["integrity_risk"])}
        figs.save(F.fig_calibration(rel), "fig14_calibration",
                  title="Calibration",
                  caption="Reliability diagram with equal-mass bins. Expected "
                          "calibration error is %.4f; deviation above the diagonal "
                          "indicates under-confidence and below it over-confidence."
                          % det_full["ece"],
                  placement="MAIN", dataset=dataset_label,
                  source_data=str(data_path), generation_script=SCRIPT)

    temporal = {}
    with guard("fig15_lead_time"):
        pw = pd.DataFrame([{"symbol": w.symbol, "t_entry": w.t_entry,
                            "t_exit": w.t_exit, "censored": w.censored}
                           for w in st.windows_from_frame(scored)])
        tw = (scored[scored["is_episode"] == 1]
              .groupby(["symbol", "episode_id"])
              .agg(t_entry=("t_entry", "first"), t_exit=("t_exit", "first"))
              .reset_index())
        temporal = mx.temporal_metrics(tw, pw, scored["date"].drop_duplicates())
        per_window = temporal.pop("per_window")
        figs.save(F.fig_lead_time({"AEGIS (full stack)":
                                   per_window["lead_time"].to_numpy(float)}),
                  "fig15_lead_time", title="Detection lead time",
                  caption="Distribution of lead time in trading sessions between the "
                          "predicted and the true episode entry, over %d matched "
                          "windows. Positive values indicate detection before the "
                          "injected onset; median %.1f sessions."
                          % (int(temporal["n_matched"]),
                             float(temporal["median_lead_time"])
                             if np.isfinite(temporal["median_lead_time"])
                             else float("nan")),
                  placement="MAIN", dataset=dataset_label,
                  source_data=str(data_path), generation_script=SCRIPT)
        per_window.to_csv(paths.STATISTICS / "temporal_per_window.csv", index=False)

    with guard("fig05_risk_window"):
        eps = scored[scored["episode_id"].astype(str) != ""]
        if eps.empty:
            raise ValueError("no episodes in the evaluation split")
        best = eps.groupby("episode_id")["integrity_risk"].max().idxmax()
        sym = eps[eps["episode_id"] == best]["symbol"].iloc[0]
        g = scored[scored["symbol"] == sym].sort_values("date")
        ep_rows = g[g["episode_id"] == best]
        wins = st.extract_windows(g["date"], g["integrity_risk"].to_numpy(float), sym)
        w0 = wins[0] if wins else None
        figs.save(F.fig_risk_window(
            g["date"].to_numpy(), g["integrity_risk"].to_numpy(float),
            ep_rows["t_entry"].iloc[0], ep_rows["t_exit"].iloc[0],
            w0.t_entry if w0 else None, w0.t_exit if w0 else None,
            uncertainty=g["uncertainty"].to_numpy(float), symbol=sym),
            "fig05_risk_window", title="Risk window",
            caption="Integrity-risk trace for instrument %s around injected episode %s. "
                    "The shaded band is the injected risk window; the dashed and "
                    "dash-dotted lines are the entry and exit produced by the temporal "
                    "state machine, and the light band is the model's uncertainty. "
                    "Points are the sampled decision rows for this instrument rather "
                    "than every trading session, so segments between sparse background "
                    "rows are interpolated."
                    % (sym, best),
            placement="MAIN", dataset=dataset_label, source_data=str(data_path),
            generation_script=SCRIPT)

    with guard("figS_state_occupancy"):
        figs.save(F.fig_state_occupancy(scored["risk_state"]), "figS_state_occupancy",
                  title="Predicted state occupancy",
                  caption="Number of instrument-days assigned to each risk state on the "
                          "validation split (log scale).",
                  placement="SUPPLEMENTARY", dataset=dataset_label,
                  source_data=str(data_path), generation_script=SCRIPT)

    # ---------------------------------------------------------------- ablations ----
    progress.log("[5] ablation figures")
    if len(ablation):
        kinds = {"fig09_modality_ablation": ("modality", "Modality ablation"),
                 "figS_component_ablation": ("component", "Component ablation"),
                 "fig12_fusion_ablation": ("fusion", "Fusion-strategy comparison")}
        arm_kind = {a.name: a.kind for a in ab.all_arms()}
        ablation["kind"] = ablation["arm"].map(arm_kind)
        for fid, (kind, title) in kinds.items():
            with guard(fid):
                sel = ablation[(ablation["kind"] == kind)
                               | (ablation["arm"] == "FULL")]
                if sel.empty:
                    raise ValueError("no arms of kind %s" % kind)
                figs.save(F.fig_ablation(sel, "auprc", title, reference="FULL"),
                          fid, title=title,
                          caption="%s on the validation split. Bars are AUPRC with "
                                  "95%% percentile intervals from a cluster bootstrap "
                                  "that resamples whole episodes, so within-episode "
                                  "dependence is respected. The dashed line marks the "
                                  "full evidence stack." % title,
                          placement="MAIN" if kind != "component" else "SUPPLEMENTARY",
                          dataset=dataset_label,
                          source_data=str(exp_dir / "ablation_results.csv"),
                          generation_script=SCRIPT)

    with guard("fig27_modality_contribution"):
        contrib = pd.DataFrame({
            "modality": pred_ev["modality_names"],
            "contribution": pred_ev["modality_contribution"].mean(axis=0)})
        figs.save(F.fig_modality_contribution(contrib), "fig27_modality_contribution",
                  title="Modality contribution",
                  caption="Mean contribution of each modality to the fused integrity "
                          "risk, computed as the calibrated per-modality score times "
                          "its fusion weight. Contributions are exact: they sum to the "
                          "fused score by construction, not by approximation.",
                  placement="MAIN", dataset=dataset_label,
                  source_data=str(data_path), generation_script=SCRIPT)
        contrib.to_csv(paths.STATISTICS / "modality_contribution.csv", index=False)

    # ------------------------------------------------------- regime degeneracy ----
    progress.log("[6] regime degeneracy figure")
    with guard("fig12b_regime_degeneracy"):
        active = pred_ev["modality_names"]
        cov = np.column_stack([AegisRiskModel._coverage_col(evald, m) for m in active])
        regime = evald["regime_id"].fillna(0).to_numpy().astype(int)
        regime = np.clip(regime, 0, model.n_regimes - 1)
        f = model.fusion
        base = np.tile(f.logits_, (len(evald), 1))
        w_static = softmax(np.where(cov > 0, base, -np.inf), axis=1)
        w_inh = softmax(np.where(cov > 0,
                                 base + f.regime_scalar_[regime][:, None], -np.inf),
                        axis=1)
        w_corr = f.weights(cov, None, regime)
        figs.save(F.fig_degeneracy(regime, w_static, w_inh, w_corr, list(active)),
                  "fig12b_regime_degeneracy",
                  title="Regime-conditioned fusion: inherited vs corrected",
                  caption="Mean fusion weight per modality within each regime. The "
                          "inherited formulation is indistinguishable from static "
                          "attention because a regime term shared by all softmax "
                          "numerators cancels under normalisation (maximum absolute "
                          "weight difference %.2e); the corrected formulation uses a "
                          "modality-specific regime bias and a regime temperature and "
                          "does vary across regimes."
                          % float(np.max(np.abs(w_static - w_inh))),
                  placement="MAIN", dataset=dataset_label,
                  source_data=str(data_path), generation_script=SCRIPT)
        from research.multimodal.fusion import demonstrate_degeneracy
        deg = demonstrate_degeneracy(np.zeros_like(cov), cov, regime, f.logits_,
                                     f.regime_scalar_)
        (paths.STATISTICS / "regime_degeneracy.json").write_text(
            json.dumps(deg, indent=2), encoding="utf-8")

    # ------------------------------------------------------------------- XAI ----
    progress.log("[7] XAI: attributions, benchmark, sanity checks")
    xai_summary: dict = {}
    with guard("xai_block"):
        cols = [c for m in full_arm.modalities
                for c in ds.MODALITY_BLOCKS[m] if c in evald.columns]
        cols = [c for c in cols if evald[c].notna().any()]
        Xev = np.nan_to_num(evald[cols].to_numpy(float), nan=0.0)
        Xtr = np.nan_to_num(train[cols].to_numpy(float), nan=0.0)

        from sklearn.ensemble import HistGradientBoostingClassifier
        surrogate = HistGradientBoostingClassifier(max_iter=180, max_depth=4,
                                                   learning_rate=0.06,
                                                   random_state=20260818)
        surrogate.fit(Xtr, y_tr)
        predict_fn = lambda Z: surrogate.predict_proba(np.nan_to_num(Z, nan=0.0))[:, 1]
        agreement_note = (
            "attributions are computed on a single-model surrogate fitted to the same "
            "features, because KernelSHAP and LIME require one f(x) over a flat feature "
            "vector; the surrogate reaches AUPRC %.4f against the fused model's %.4f"
            % (mx.detection_metrics(y_ev, predict_fn(Xev))["auprc"], det_full["auprc"]))
        progress.log("    " + agreement_note)

        perm = xm.permutation_importance(predict_fn, Xev, y_ev, cols, n_repeats=3)
        imp = pd.DataFrame({"feature": perm.feature_names,
                            "importance": perm.values})
        with guard("fig22_global_importance"):
            figs.save(F.fig_global_importance(imp), "fig22_global_importance",
                      title="Global feature importance",
                      caption="Permutation importance measured as the drop in AUPRC "
                              "when a feature is shuffled (3 repeats). Computed on the "
                              "validation split. %s" % agreement_note,
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(data_path), generation_script=SCRIPT)
        imp.sort_values("importance", ascending=False).to_csv(
            paths.STATISTICS / "global_importance.csv", index=False)

        row = int(np.argmax(pred_ev["integrity_risk"]))
        bg = Xtr[np.random.default_rng(0).choice(len(Xtr), min(200, len(Xtr)),
                                                 replace=False)]
        attrs: dict[str, xm.Attribution] = {}
        for name, fn in (
            ("occlusion", lambda: xm.occlusion(predict_fn, Xev, row, cols, bg)),
            ("kernel_shap", lambda: xm.kernel_shap(predict_fn, Xev, row, cols, bg,
                                                   nsamples=150)),
            ("lime", lambda: xm.lime(predict_fn, Xev, row, cols, bg, n_samples=600)),
            ("counterfactual", lambda: xm.counterfactual(predict_fn, Xev, row, cols,
                                                         bg)),
        ):
            try:
                attrs[name] = fn()
                progress.log("    %-16s %.2fs" % (name, attrs[name].seconds))
            except Exception as exc:
                skip("xai_%s" % name, "%s: %s" % (type(exc).__name__, exc))

        for name, a in attrs.items():
            fid = "fig23_local_%s" % name
            with guard(fid):
                figs.save(F.fig_local_explanation(a, title="Local explanation (%s)"
                                                  % name),
                          fid, title="Local explanation: %s" % name,
                          caption="Attribution for the highest-risk instrument-day in "
                                  "the validation split, method %s. Positive values "
                                  "push the score up. %s" % (name, agreement_note),
                          placement="MAIN" if name == "kernel_shap"
                          else "SUPPLEMENTARY",
                          dataset=dataset_label, source_data=str(data_path),
                          generation_script=SCRIPT)

        # modality-level attribution by group occlusion
        with guard("fig27b_modality_occlusion"):
            groups = {}
            for m in full_arm.modalities:
                idx = [cols.index(c) for c in ds.MODALITY_BLOCKS[m] if c in cols]
                if idx:
                    groups[m] = idx
            ga = xm.occlusion(predict_fn, Xev, row, cols, bg, groups=groups)
            figs.save(F.fig_local_explanation(ga, k=len(groups),
                                              title="Modality attribution (occlusion)"),
                      "fig27b_modality_occlusion",
                      title="Modality-level attribution",
                      caption="Score change when each modality block is replaced in "
                              "full by its background median, for the highest-risk "
                              "instrument-day. This is the modality analogue of feature "
                              "occlusion and answers which evidence stream carried the "
                              "decision.",
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(data_path), generation_script=SCRIPT)

        # faithfulness / agreement / cost
        faith_rows = []
        for name, a in attrs.items():
            try:
                fr = xb.faithfulness(predict_fn, Xev[row], a, np.nanmedian(bg, axis=0))
                faith_rows.append(fr.__dict__)
            except Exception as exc:
                skip("faithfulness_%s" % name, str(exc))
        faith = pd.DataFrame(faith_rows)
        if len(faith):
            with guard("fig33_faithfulness"):
                figs.save(F.fig_faithfulness(faith), "fig33_faithfulness",
                          title="Explanation faithfulness",
                          caption="Deletion and insertion AUC per explanation method "
                                  "(deletion lower is better, insertion higher is "
                                  "better). Features are removed or restored in "
                                  "attribution order and replaced by the background "
                                  "median.",
                          placement="MAIN", dataset=dataset_label,
                          source_data=str(data_path), generation_script=SCRIPT)
            tabs.save(faith, "table18_explanation_faithfulness",
                      title="Explanation faithfulness",
                      caption="Faithfulness of each explanation method on the "
                              "highest-risk validation row.")

        if len(attrs) > 1:
            agr = xb.agreement(attrs)
            with guard("fig32_agreement"):
                figs.save(F.fig_agreement_heatmap(agr, list(attrs)), "fig32_agreement",
                          title="Cross-explainer agreement",
                          caption="Spearman rank correlation between the attribution "
                                  "vectors of each pair of methods. Agreement is "
                                  "descriptive: methods can share a bias, so high "
                                  "agreement is not evidence of correctness and "
                                  "disagreement is not proof of error.",
                          placement="MAIN", dataset=dataset_label,
                          source_data=str(data_path), generation_script=SCRIPT)
            tabs.save(agr, "table10_xai_agreement", title="Cross-explainer agreement",
                      caption="Pairwise Spearman correlation and top-10 Jaccard overlap "
                              "between explanation methods.")

        tabs.save(xb.cost_table(attrs), "table15_xai_cost",
                  title="Explanation computational cost",
                  caption="Wall-clock seconds per explanation on the evaluation "
                          "hardware recorded in the reproducibility manifest.")

        # sanity suite
        with guard("xai_sanity"):
            rand_fn = xs.randomised_model_predict(Xtr, y_tr)
            rand_attr = xm.occlusion(rand_fn, Xev, row, cols, bg)
            base_attr = attrs.get("occlusion")
            repeats = [xm.lime(predict_fn, Xev, row, cols, bg, n_samples=400, seed=s)
                       for s in (1, 2, 3)]
            suite = xs.run_suite(base_attr, rand_attr, None, repeats)
            suite.to_csv(paths.STATISTICS / "xai_sanity.csv", index=False)
            tabs.save(suite, "table17_xai_sanity",
                      title="XAI sanity checks",
                      caption="Model-randomisation and stability checks. A method whose "
                              "attributions survive model randomisation is describing "
                              "the data rather than the model and must not be presented "
                              "as insight into the model.")
            xai_summary["sanity_all_passed"] = bool(suite["passed"].all())
            progress.log("    sanity checks passed: %s"
                         % suite["passed"].all())

        xai_summary["note"] = agreement_note
        xai_summary["methods_run"] = list(attrs)
        xai_summary["not_applicable"] = xm.NOT_APPLICABLE

    # ------------------------------------------------------- text/image/audio XAI ----
    progress.log("[8] modality-specific explanation figures")
    with guard("fig23t_text_attribution"):
        doc = ("Regulators opened a probe into alleged manipulation after an unusual "
               "surge in turnover; the company strongly denies any irregularity, "
               "although the auditor issued a qualified opinion.")
        a = ta.extract(doc)
        toks = ta.tokenize(doc)
        vals = np.zeros(len(toks))
        for c in a.contributions:
            if c.dimension == "valence":
                vals[c.index] += c.value
        keep = [i for i, v in enumerate(vals) if abs(v) > 0]
        figs.save(F.fig_text_attribution([toks[i] for i in keep],
                                         [vals[i] for i in keep], "valence"),
                  "fig23t_text_attribution", title="Token attribution",
                  caption="Exact per-token contributions to document valence. Because "
                          "the text extractor is lexicon-based, these attributions are "
                          "the computation itself rather than an approximation of it.",
                  placement="SUPPLEMENTARY", dataset="illustrative document",
                  source_data="constructed example sentence", generation_script=SCRIPT)

    with guard("fig28_image_saliency"):
        from research.image import chartgen as cg
        from research.image import pipeline as ip
        sym = scored.sort_values("integrity_risk", ascending=False)["symbol"].iloc[0]
        sdf = panel[panel["symbol"] == sym].sort_values("date").reset_index(drop=True)
        i = len(sdf) - 1
        raster = cg.rasterize_window(sdf, i, 60)
        base_feat = ip.features_from_array(raster)
        grid = 8
        sal = np.zeros((grid, grid))
        h, w, _ = raster.shape
        # Named `row_edges`/`col_edges`, not `ys`/`xs`: `xs` is the module alias for
        # research.xai.sanity, and a local assignment here would shadow it for the whole
        # function, turning the sanity-suite call above into an UnboundLocalError.
        row_edges = np.linspace(0, h, grid + 1).astype(int)
        col_edges = np.linspace(0, w, grid + 1).astype(int)
        for r in range(grid):
            for c in range(grid):
                occ = raster.copy()
                occ[row_edges[r]:row_edges[r + 1],
                    col_edges[c]:col_edges[c + 1], :] = raster.mean(axis=(0, 1))
                f2 = ip.features_from_array(occ)
                sal[r, c] = np.linalg.norm(base_feat.embedding - f2.embedding)
        figs.save(F.fig_image_saliency(raster, sal), "fig28_image_saliency",
                  title="Image occlusion saliency",
                  caption="Occlusion saliency over the chart image for %s: each patch is "
                          "replaced by the image mean and the change in the image "
                          "embedding is recorded. Bright regions are those the image "
                          "descriptor depends on most." % sym,
                  placement="SUPPLEMENTARY", dataset=dataset_label,
                  source_data=str(paths.PANEL / "cash_panel.parquet"),
                  generation_script=SCRIPT)

    with guard("fig29_audio_attribution"):
        from research.audio import pipeline as apx
        from research.audio import sonify as son
        w = sdf.iloc[max(0, i - 59):i + 1]
        wave = son.sonify(w["close"].to_numpy(), w["volume"].to_numpy())
        af = apx.extract_from_array(wave, son.SR)
        n_seg = 10
        seg_len = len(wave) // n_seg
        imp = np.zeros(n_seg)
        base_arousal = af.affect["arousal"]
        for k in range(n_seg):
            w2 = wave.copy()
            w2[k * seg_len:(k + 1) * seg_len] = 0.0
            imp[k] = base_arousal - apx.extract_from_array(w2, son.SR).affect["arousal"]
        figs.save(F.fig_audio_attribution(af.frame_times, af.frame_energy, imp),
                  "fig29_audio_attribution", title="Audio temporal attribution",
                  caption="Energy envelope of the sonified series for %s with "
                          "per-segment "
                          "importance measured by silencing each tenth of the signal and "
                          "recording the change in acoustic arousal. The audio modality "
                          "here is a sonification of market data, not speech "
                          "(limitation L-06)." % sym,
                  placement="SUPPLEMENTARY", dataset=dataset_label,
                  source_data=str(paths.PANEL / "cash_panel.parquet"),
                  generation_script=SCRIPT)

    with guard("fig30_video_attribution"):
        from research.video import pipeline as vpx
        frames, times = [], []
        for k in range(8):
            j = max(60, i - (7 - k) * 5)
            frames.append(cg.rasterize_window(sdf, j, 60))
            times.append(float(k))
        v = vpx.extract_from_frames(frames, times)
        base_edge = float(np.mean([f["edge_energy"] for f in v.frame_affect]))
        imp = np.zeros(len(frames))
        for k in range(len(frames)):
            f2 = list(frames)
            f2[k] = np.full_like(frames[k], frames[k].mean())
            v2 = vpx.extract_from_frames(f2, times)
            imp[k] = base_edge - float(np.mean([f["edge_energy"]
                                                for f in v2.frame_affect]))
        figs.save(F.fig_video_attribution(np.array(times), v.temporal_saliency, imp),
                  "fig30_video_attribution", title="Video temporal attribution",
                  caption="Inter-frame change and per-frame importance for the "
                          "chart clip of %s, the latter measured by replacing each "
                          "frame with a flat field and recording the change in mean "
                          "visual edge energy." % sym,
                  placement="SUPPLEMENTARY", dataset=dataset_label,
                  source_data=str(paths.PANEL / "cash_panel.parquet"),
                  generation_script=SCRIPT)

    # ------------------------------------------------------------- propagation ----
    progress.log("[9] propagation graph")
    with guard("fig18_propagation"):
        last_date = scored["date"].max()
        sub = panel[panel["symbol"].isin(scored["symbol"].unique())].copy()
        sub["logret"] = np.log(sub["close"]) - np.log(sub["prev_close"])
        edges = pg.correlation_graph(sub, pd.Timestamp(last_date))
        risk = dict(zip(scored[scored["date"] == last_date]["symbol"],
                        scored[scored["date"] == last_date]["integrity_risk"]))
        fig = F.fig_propagation_graph(edges, risk, k=50)
        if fig is None:
            raise ValueError("empty propagation graph")
        figs.save(fig, "fig18_propagation", title="Propagation graph",
                  caption="Instrument graph on %s: an edge joins two instruments whose "
                          "trailing 126-session return correlation exceeds 0.25, "
                          "estimated strictly before the date shown. Node colour is the "
                          "integrity-risk estimate. Edges are statistical co-movement "
                          "only and imply no economic relationship (limitation L-07)."
                          % pd.Timestamp(last_date).date(),
                  placement="MAIN", dataset=dataset_label,
                  source_data=str(paths.PANEL / "cash_panel.parquet"),
                  generation_script=SCRIPT)
        edges.to_csv(paths.STATISTICS / "propagation_edges.csv", index=False)

    # ------------------------------------------------------ capital consequence ----
    progress.log("[10] capital consequence")
    cap: dict = {}
    with guard("capital_block"):
        fwd = panel[["symbol", "date", "close"]].sort_values(["symbol", "date"]).copy()
        fwd["fwd_ret"] = fwd.groupby("symbol")["close"].pct_change().shift(-1)
        merged = scored.merge(fwd[["symbol", "date", "fwd_ret"]],
                              on=["symbol", "date"], how="left")
        merged = merged.dropna(subset=["fwd_ret"])
        cap = capital_consequence(merged, "fwd_ret", GatePolicy(), CostModel())
        ctrl, trt = cap["control_series"], cap["treatment_series"]
        with guard("fig19_capital"):
            figs.save(F.fig_capital(ctrl, trt), "fig19_capital",
                      title="Capital consequence",
                      caption="Cumulative growth of one unit under a fixed equal-weight "
                              "research policy without (control) and with (treatment) "
                              "the integrity gate. Released capital is not redeployed. "
                              "This is a hypothetical research exposure policy applied "
                              "to historical data and is not investment advice, not a "
                              "strategy and not an achievable return.",
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(data_path), generation_script=SCRIPT)
        with guard("fig21_drawdown"):
            figs.save(F.fig_drawdown(ctrl, trt), "fig21_drawdown",
                      title="Drawdown comparison",
                      caption="Drawdown of the control and treatment series. Maximum "
                              "drawdown %.4f (control) versus %.4f (treatment)."
                              % (cap["control"]["max_drawdown"],
                                 cap["treatment"]["max_drawdown"]),
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(data_path), generation_script=SCRIPT)
        with guard("fig20_cvar"):
            figs.save(F.fig_cvar({"control": cap["control"],
                                  "treatment": cap["treatment"]}), "fig20_cvar",
                      title="Tail loss comparison",
                      caption="Daily 5%% conditional value at risk under the control and "
                              "gated policies (%d sessions)." % cap["control"]["n"],
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(data_path), generation_script=SCRIPT)
        with guard("figS_return_distribution"):
            figs.save(F.fig_return_distribution(ctrl["net"].to_numpy(),
                                                trt["net"].to_numpy()),
                      "figS_return_distribution", title="Return distributions",
                      caption="Daily net return distributions with the 5% quantile "
                              "marked for each arm.",
                      placement="SUPPLEMENTARY", dataset=dataset_label,
                      source_data=str(data_path), generation_script=SCRIPT)
        # A difference in CVaR is not a finding until it survives resampling. Blocks of
        # 21 sessions are resampled jointly for both arms, because daily returns are
        # autocorrelated and the two arms share the same days.
        rng = np.random.default_rng(20260818)
        rc = ctrl["net"].to_numpy(float)
        rt = trt["net"].to_numpy(float)
        block = 21
        n = min(len(rc), len(rt))
        cvar_d, mdd_d = [], []
        for _ in range(2000):
            starts = rng.integers(0, max(1, n - block), size=max(1, n // block))
            idx = np.concatenate([np.arange(st_, min(n, st_ + block))
                                  for st_ in starts])
            a, b = rc[idx], rt[idx]
            qa, qb = np.percentile(a, 5), np.percentile(b, 5)
            ta_, tb_ = a[a <= qa], b[b <= qb]
            if len(ta_) and len(tb_):
                cvar_d.append(float(tb_.mean() - ta_.mean()))
            ea, eb = np.cumprod(1 + a), np.cumprod(1 + b)
            mdd_d.append(float((eb / np.maximum.accumulate(eb) - 1).min()
                               - (ea / np.maximum.accumulate(ea) - 1).min()))

        def _summarise(v, name):
            v = np.asarray(v)
            lo, hi = np.percentile(v, [2.5, 97.5])
            p_two = 2.0 * min((v <= 0).mean(), (v >= 0).mean())
            return {"metric": name, "mean_delta": float(v.mean()),
                    "ci_low": float(lo), "ci_high": float(hi),
                    "p_value": float(min(1.0, max(p_two, 1.0 / (len(v) + 1)))),
                    "n_resamples": int(len(v)),
                    "test": "moving-block bootstrap (21-session blocks) on the paired "
                            "daily net-return series; positive delta means the gated arm "
                            "has the less negative tail"}

        cap_sig = [_summarise(cvar_d, "cvar_delta"),
                   _summarise(mdd_d, "max_drawdown_delta")]
        pd.DataFrame(cap_sig).to_csv(paths.STATISTICS / "capital_significance.csv",
                                     index=False)
        tabs.save(pd.DataFrame(cap_sig), "table12b_capital_significance",
                  title="Capital-consequence significance",
                  caption="Moving-block bootstrap on the paired daily net-return series. "
                          "A positive delta means the integrity-gated arm has the less "
                          "severe tail. Hypothetical research policy; not advice.")
        progress.log("    cvar delta %+.5f (95%% CI %+.5f..%+.5f, p=%.4f)"
                     % (cap_sig[0]["mean_delta"], cap_sig[0]["ci_low"],
                        cap_sig[0]["ci_high"], cap_sig[0]["p_value"]))
        progress.log("    mdd  delta %+.5f (95%% CI %+.5f..%+.5f, p=%.4f)"
                     % (cap_sig[1]["mean_delta"], cap_sig[1]["ci_low"],
                        cap_sig[1]["ci_high"], cap_sig[1]["p_value"]))

        cap_out = {k: v for k, v in cap.items()
                   if k not in ("control_series", "treatment_series")}
        cap_out["significance"] = cap_sig
        (paths.STATISTICS / "capital_consequence.json").write_text(
            json.dumps(cap_out, indent=2, default=str), encoding="utf-8")

    # ----------------------------------------------------- uncertainty/coverage ----
    progress.log("[11] uncertainty, coverage and robustness")
    with guard("fig35_uncertainty"):
        d = evald.copy()
        d["_p"] = pred_ev["integrity_risk"]
        d["_u"] = pred_ev["uncertainty"]
        qs = np.quantile(d["_u"], np.linspace(0, 1, 6))
        rows = []
        for lo, hi in zip(qs[:-1], qs[1:]):
            sel = d[(d["_u"] >= lo) & (d["_u"] <= hi)]
            if len(sel) < 30 or sel["is_episode"].nunique() < 2:
                continue
            rows.append({"uncertainty_mid": float((lo + hi) / 2),
                         "auprc": mx.detection_metrics(
                             sel["is_episode"].to_numpy(int),
                             sel["_p"].to_numpy())["auprc"],
                         "n": int(len(sel))})
        ub = pd.DataFrame(rows)
        if ub.empty:
            raise ValueError("no usable uncertainty bins")
        figs.save(F.fig_uncertainty_vs_performance(ub), "fig35_uncertainty",
                  title="Uncertainty vs performance",
                  caption="AUPRC within uncertainty quintiles. A downward trend is the "
                          "expected behaviour: the model should be less accurate exactly "
                          "where it reports being less certain.",
                  placement="MAIN", dataset=dataset_label, source_data=str(data_path),
                  generation_script=SCRIPT)
        ub.to_csv(paths.STATISTICS / "uncertainty_bins.csv", index=False)

    with guard("fig36_coverage"):
        d = evald.copy()
        d["_p"] = pred_ev["integrity_risk"]
        d["_u"] = pred_ev["uncertainty"]
        rows = []
        for frac in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4):
            k = int(len(d) * frac)
            sel = d.nsmallest(k, "_u")
            if sel["is_episode"].nunique() < 2:
                continue
            rows.append({"coverage": frac,
                         "auprc": mx.detection_metrics(
                             sel["is_episode"].to_numpy(int),
                             sel["_p"].to_numpy())["auprc"], "n": k})
        cb = pd.DataFrame(rows)
        figs.save(F.fig_coverage_vs_reliability(cb), "fig36_coverage",
                  title="Coverage vs reliability",
                  caption="Selective-prediction curve: AUPRC on the most-certain "
                          "fraction of rows. Rising accuracy as coverage falls means "
                          "the uncertainty estimate is usable for abstention.",
                  placement="MAIN", dataset=dataset_label, source_data=str(data_path),
                  generation_script=SCRIPT)
        cb.to_csv(paths.STATISTICS / "coverage_bins.csv", index=False)

    with guard("fig34_missing_modality"):
        rng = np.random.default_rng(3)
        rows = []
        for m in ("text", "image", "audio", "video", "market"):
            key = {"microstructure": "cov_micro"}.get(m, "cov_%s" % m)
            if key not in evald.columns:
                continue
            for rate in (0.0, 0.25, 0.5, 0.75, 1.0):
                d = evald.copy()
                mask = rng.random(len(d)) < rate
                d.loc[mask, key] = 0.0
                for c in ds.MODALITY_BLOCKS[m]:
                    if c in d.columns:
                        d.loc[mask, c] = np.nan
                p = model.predict(d)["integrity_risk"]
                rows.append({"dropped": m, "drop_rate": rate,
                             "auprc": mx.detection_metrics(y_ev, p)["auprc"]})
        mm = pd.DataFrame(rows)
        figs.save(F.fig_missing_modality(mm), "fig34_missing_modality",
                  title="Missing-modality robustness",
                  caption="AUPRC when a modality is withheld at inference time from a "
                          "growing fraction of rows. The model was trained with the "
                          "full stack; degradation measures how gracefully the fusion "
                          "layer handles absence rather than imputing it.",
                  placement="MAIN", dataset=dataset_label, source_data=str(data_path),
                  generation_script=SCRIPT)
        mm.to_csv(paths.STATISTICS / "missing_modality.csv", index=False)

    # ---------------------------------------------------------- error taxonomy ----
    progress.log("[12] error analysis")
    with guard("fig38_errors"):
        d = evald.copy()
        d["integrity_risk"] = pred_ev["integrity_risk"]
        d["uncertainty"] = pred_ev["uncertainty"]
        err = mx.classify_errors(d, thr)
        counts = (err["error_class"].value_counts().rename_axis("error_class")
                  .reset_index(name="count"))
        figs.save(F.fig_error_taxonomy(counts), "fig38_errors",
                  title="Error taxonomy",
                  caption="Distribution of outcome classes on the validation split at "
                          "the training-selected operating threshold %.3f. Data "
                          "problems are diagnosed before model problems: a row with no "
                          "evidence is a coverage failure, not a model failure." % thr,
                  placement="MAIN", dataset=dataset_label, source_data=str(data_path),
                  generation_script=SCRIPT)
        tabs.save(counts, "table14_error_analysis", title="Error analysis",
                  caption="Counts per error class at the operating threshold.")

    # ------------------------------------------------------------------ tables ----
    progress.log("[13] tables")
    with guard("table01_dataset"):
        rows = [
            {"quantity": "trading sessions (panel)", "value": panel["date"].nunique()},
            {"quantity": "instruments (panel)", "value": panel["symbol"].nunique()},
            {"quantity": "panel rows", "value": len(panel)},
            {"quantity": "panel first session", "value": str(panel["date"].min().date())},
            {"quantity": "panel last session", "value": str(panel["date"].max().date())},
            {"quantity": "research universe size", "value": 50},
            {"quantity": "distinct universe members ever",
             "value": universe["symbol"].nunique()},
            {"quantity": "dataset rows", "value": len(data)},
            {"quantity": "dataset features", "value": len(ds.ALL_FEATURES)},
            {"quantity": "episode rows", "value": int(data["is_episode"].sum())},
            {"quantity": "positive rate",
             "value": round(float(data["is_episode"].mean()), 4)},
            {"quantity": "train rows", "value": int((data["split"] == "train").sum())},
            {"quantity": "validation rows",
             "value": int((data["split"] == "validation").sum())},
            {"quantity": "holdout rows (untouched)",
             "value": int((data["split"] == "holdout").sum())},
        ]
        tabs.save(pd.DataFrame(rows), "table01_dataset_statistics",
                  title="Dataset statistics",
                  caption="Composition of the real NSE panel and the assembled "
                          "multimodal dataset. The holdout split has not been evaluated.")

    with guard("table02_provenance"):
        prov = pd.DataFrame([
            {"source": "NSE daily cash bhavcopy", "modality": "market",
             "licence": "NSE public archive; see docs/DATA_LICENSING.md",
             "coverage": "2005-01-03 .. 2026-08-14", "status": "USED"},
            {"source": "AEGIS-rendered chart images", "modality": "image",
             "licence": "repository licence (original work)",
             "coverage": "derived from the panel", "status": "USED"},
            {"source": "Market sonification", "modality": "audio",
             "licence": "repository licence (original work)",
             "coverage": "derived from the panel", "status": "USED (limitation L-06)"},
            {"source": "AEGIS-rendered chart clips", "modality": "video",
             "licence": "repository licence (original work)",
             "coverage": "derived from the panel", "status": "USED"},
            {"source": "Synthetic episode text corpus", "modality": "text",
             "licence": "repository licence (original work)",
             "coverage": "aligned to the panel", "status": "USED (limitation L-04)"},
            {"source": "Third-party broadcast video", "modality": "video",
             "licence": "all rights reserved", "coverage": "n/a",
             "status": "REFERENCE ONLY - not ingested"},
            {"source": "Historical Nifty-50 membership", "modality": "universe",
             "licence": "no licence-clear source located", "coverage": "n/a",
             "status": "NOT OBTAINED (limitation L-01)"},
            {"source": "NSE order-book depth", "modality": "microstructure",
             "licence": "not published openly", "coverage": "n/a",
             "status": "NOT MEASURED (limitation L-02)"},
        ])
        tabs.save(prov, "table02_provenance", title="Data-source provenance",
                  caption="Every data source, its licence, and whether it was used, "
                          "referenced only, or not obtained.")

    with guard("table03_models"):
        tabs.save(model.summary(), "table03_model_configuration",
                  title="Model configuration",
                  caption="Per-modality learner status, training rows, feature count and "
                          "fusion logit for the full evidence stack.")

    if len(baselines):
        with guard("table04_baselines"):
            tabs.save(baselines, "table04_baseline_comparison",
                      title="Baseline comparison",
                      caption="Baselines evaluated on the same validation split with the "
                              "same metric definitions.")
    if len(ablation):
        with guard("table05_ablation"):
            keep = [c for c in ("arm", "status", "auprc", "auroc", "precision", "recall",
                                "f1", "brier", "ece", "ci_low", "ci_high")
                    if c in ablation.columns]
            tabs.save(ablation[keep].sort_values("auprc", ascending=False),
                      "table05_ablation", title="Ablation results",
                      caption="All ablation arms with bootstrap intervals. Failed arms "
                              "are listed with their status rather than omitted.")
    if len(stats):
        with guard("table05b_statistics"):
            tabs.save(stats, "table05b_ablation_statistics",
                      title="Ablation significance",
                      caption="Paired cluster-bootstrap differences against the full "
                              "stack, with Benjamini-Hochberg adjusted p-values at a "
                              "5% false-discovery rate.")

    with guard("table11_temporal"):
        if temporal:
            tt = pd.DataFrame([{"metric": k, "value": v}
                               for k, v in temporal.items()
                               if isinstance(v, (int, float))])
            tabs.save(tt, "table11_temporal_metrics", title="Temporal metrics",
                      caption="Window-matching results: detection rate, lead time, onset "
                              "and resolution error, and temporal IoU.")

    with guard("table12_capital"):
        if cap:
            rows = []
            for arm in ("control", "treatment"):
                for k, v in cap[arm].items():
                    rows.append({"arm": arm, "metric": k, "value": v})
            tabs.save(pd.DataFrame(rows), "table12_capital_consequence",
                      title="Capital consequence",
                      caption="Tail and drawdown statistics for the ungated control and "
                              "integrity-gated treatment arms of a hypothetical research "
                              "exposure policy. Not investment advice.")

    with guard("table16_operational"):
        import platform
        op = pd.DataFrame([
            {"quantity": "python", "value": sys.version.split()[0]},
            {"quantity": "platform", "value": platform.platform()},
            {"quantity": "dataset rows", "value": len(data)},
            {"quantity": "features", "value": len(ds.ALL_FEATURES)},
            {"quantity": "artifact generation seconds",
             "value": round(time.time() - t0, 1)},
        ])
        tabs.save(op, "table16_operational", title="Computational cost",
                  caption="Environment and wall-clock cost of regenerating the paper "
                          "assets.")

    # --------------------------------------------- research-angle figures ----
    progress.log("[13b] research-angle figures (limitations turned into measurements)")
    ang_dir = paths.ARTIFACTS / "research_angles"
    ang_path = ang_dir / "research_angles.json"
    if ang_path.exists():
        ang = json.loads(ang_path.read_text(encoding="utf-8"))["results"]

        with guard("figINFO_modality_matrix"):
            m = pd.read_csv(ang_dir / "modality_information_matrix.csv")
            figs.save(F.fig_modality_information(m), "figINFO_modality_matrix",
                      title="Modality information decomposition",
                      caption="Per-modality AUPRC contribution split into the part that "
                              "is unique (lost when the modality is removed) and the "
                              "part that is redundant with other modalities. Image, "
                              "audio and video are rendered or sonified from the market "
                              "series, so their near-zero unique contribution is "
                              "expected by construction and serves as a negative "
                              "control. This is an operational decomposition in AUPRC, "
                              "not a formal partial information decomposition.",
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(ang_dir / "modality_information_matrix.csv"),
                      generation_script=SCRIPT)

        with guard("figN03_lead_time_frontier"):
            fr = pd.read_csv(ang_dir / "exp_n03_lead_time_frontier.csv")
            figs.save(F.fig_lead_time_frontier(fr), "figN03_lead_time_frontier",
                      title="Detection timing versus precision frontier",
                      caption="Window precision against median lead time as the state "
                              "machine entry threshold is swept from 0.20 to 0.90, "
                              "labelled at each point. No operating point reaches "
                              "positive lead time, so the lateness reported elsewhere is "
                              "a property of when the evidence arrives rather than of "
                              "how conservatively the detector is tuned.",
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(ang_dir / "exp_n03_lead_time_frontier.csv"),
                      generation_script=SCRIPT)

        with guard("figN03_modality_lead_lag"):
            curves = json.loads((ang_dir / "exp_n03_lead_lag_curves.json")
                                .read_text(encoding="utf-8"))
            figs.save(F.fig_modality_lead_lag(curves), "figN03_modality_lead_lag",
                      title="Modality lead and lag",
                      caption="Mean cross-correlation between each modality score and "
                              "the episode indicator, computed per instrument and "
                              "averaged across instruments. Positive lag means the "
                              "modality moves before the episode indicator. Text is "
                              "coincident, market lags, and only the microstructure "
                              "proxies peak at a positive lag, weakly.",
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(ang_dir / "exp_n03_lead_lag_curves.json"),
                      generation_script=SCRIPT)

        with guard("figL10_calibration_by_uncertainty"):
            bu = pd.read_csv(ang_dir / "exp_l10_calibration_by_uncertainty.csv")
            figs.save(F.fig_calibration_by_uncertainty(bu),
                      "figL10_calibration_by_uncertainty",
                      title="Calibration against reported uncertainty",
                      caption="Expected calibration error and Brier score within "
                              "equal-mass uncertainty quintiles of 771 rows each. Error "
                              "rises with the uncertainty the model itself reports, "
                              "which is the behaviour an uncertainty estimate should "
                              "show. The corresponding analysis against coverage is NOT "
                              "MEASURABLE on this dataset: coverage takes only two "
                              "well-populated values.",
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(ang_dir
                                      / "exp_l10_calibration_by_uncertainty.csv"),
                      generation_script=SCRIPT)

        with guard("figN04_selective_risk"):
            sr = pd.DataFrame(ang["EXP-N04-1"]["table"])
            figs.save(F.fig_selective_risk(sr), "figN04_selective_risk",
                      title="Selective risk versus coverage",
                      caption="Error rate on the most-certain fraction of rows for the "
                              "static and uncertainty-weighted fusion arms. The "
                              "uncertainty-weighted arm is lower at every coverage level "
                              "despite showing no AUPRC advantage, which is why it is "
                              "reported as PARTIAL rather than NOT SUPPORTED. Each arm "
                              "ranks rows by its own uncertainty, so the comparison "
                              "flatters an arm whose uncertainty is merely "
                              "self-consistent.",
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(ang_dir / "exp_n04_selective_risk.csv"),
                      generation_script=SCRIPT)

        with guard("figL12_power_curve"):
            pc = pd.read_csv(ang_dir / "exp_l12_power_curves.csv")
            figs.save(F.fig_power_curve(pc), "figL12_power_curve",
                      title="Minimum detectable effect versus sample size",
                      caption="Bootstrap interval half-width against the number of "
                              "resampled episode clusters, on log axes. The half-width "
                              "at the full cluster count is the minimum detectable "
                              "effect: for the microstructure comparison it is 0.000185 "
                              "against an observed difference of 0.000176, so that "
                              "non-significant result is uninformative rather than "
                              "evidence that the contribution is zero.",
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(ang_dir / "exp_l12_power_curves.csv"),
                      generation_script=SCRIPT)

        with guard("figN01_lime_stability"):
            ls = pd.read_csv(ang_dir / "exp_n01_lime_stability.csv")
            figs.save(F.fig_lime_stability(ls), "figN01_lime_stability",
                      title="Explanation stability against cost",
                      caption="LIME sign consistency across three seeds as the "
                              "perturbation count grows, with runtime on the right axis. "
                              "The pre-declared 0.80 threshold is crossed at 6400 "
                              "perturbations, still below the runtime of occlusion. "
                              "Stability is not agreement: the rank correlation against "
                              "occlusion stays near zero throughout.",
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(ang_dir / "exp_n01_lime_stability.csv"),
                      generation_script=SCRIPT)

        with guard("table19_research_angles"):
            rows = []
            for e in reg.ALL_ENTRIES:
                for rq in e.research_questions:
                    for ex in rq.experiments:
                        rows.append({
                            "limitation": e.id, "category": e.category.value,
                            "research_question": rq.id, "experiment": ex.id,
                            "status": ex.status.value,
                            "runnable_now": not ex.required_data,
                            "required_data": "; ".join(ex.required_data) or "none",
                        })
            tabs.save(pd.DataFrame(rows), "table19_research_angles",
                      title="Limitations, research questions and experiment status",
                      caption="Every limitation mapped to the research question it "
                              "creates and the experiment that would resolve it. "
                              "Specifications blocked by external data are marked as "
                              "such and carry no result.")

        with guard("table20_claim_ledger"):
            tabs.save(pd.DataFrame([{
                "id": c.id, "status": c.status.value, "scope": c.scope.value,
                "claim": c.claim, "limitations": ", ".join(c.limitations) or "none",
            } for c in cl.CLAIMS]), "table20_claim_ledger",
                title="Research claim ledger",
                caption="Every substantive claim with its status, validity scope and the "
                        "limitations that bound it. No claim is stated at out-of-sample "
                        "scope, because the holdout is frozen and unevaluated.")

        with guard("claim_guard"):
            violations = cl.self_check()
            if violations:
                raise RuntimeError("claim ledger violates its own guard: %s"
                                   % violations[:3])
            cl.write(paths.MANIFESTS / "claim_ledger.json")
            reg.write(paths.MANIFESTS / "limitations_registry.json")
            progress.log("    claim guard clean; ledger and registry written")
    else:
        skip("research_angle_figures",
             "research_angles.json absent: run scripts/run_research_angles.py")

    # --------------------------------------------------- position lifecycle ----
    progress.log("[lifecycle] position-lifecycle figures and tables")
    lc_dir = paths.ARTIFACTS / "lifecycle"
    lc_path = lc_dir / "lifecycle.json"
    if lc_path.exists():
        lc = json.loads(lc_path.read_text(encoding="utf-8"))
        lc_res = lc.get("results", {})

        with guard("fig_lifecycle_phases"):
            figs.save(F.fig_lifecycle_phases(), "figLC1_lifecycle_phases",
                      title="Position lifecycle as an observational segmentation",
                      caption="The analysis window is segmented into ENTRY, HOLDING and "
                              "RESOLUTION by position, and each session carries one of "
                              "six observed states. The terminal node is RESOLUTION, not "
                              "an instruction: no entry price, exit price, target or "
                              "position size exists anywhere in this framework. Phases "
                              "are analytical and no real holding period is observed "
                              "(L-15).",
                      placement="MAIN", dataset=dataset_label,
                      source_data="research/lifecycle/states.py",
                      generation_script=SCRIPT)

        with guard("fig_lifecycle_trajectory"):
            traj = pd.read_parquet(lc_dir / "lifecycle_trajectories.parquet")
            counts = traj.groupby("symbol").size().sort_values(ascending=False)
            # The instrument with the most sessions, chosen mechanically so the figure
            # is not a hand-picked illustration.
            pick = counts.index[0]
            g = traj[traj["symbol"] == pick].sort_values("date").reset_index(drop=True)
            cps = [i for i, v in enumerate(g["is_change_point"]) if bool(v)]
            figs.save(F.fig_lifecycle_trajectory(
                g["date"].tolist(), g["integrity_risk"].to_numpy(float),
                g["phase"].tolist(), cps, symbol=str(pick)),
                "figLC2_lifecycle_trajectory",
                title="Risk profile across the analysis window",
                caption="Integrity risk for %s, the cohort instrument with the most "
                        "out-of-sample sessions, selected by count rather than by "
                        "appearance. Shading marks the phase, dashed lines mark detected "
                        "change points, dotted lines mark the band edges. The series is "
                        "a model estimate on validation and holdout rows only."
                        % pick,
                placement="MAIN", dataset=dataset_label,
                source_data=str(lc_dir / "lifecycle_trajectories.parquet"),
                generation_script=SCRIPT)

        with guard("fig_lifecycle_transitions"):
            mat = pd.read_csv(lc_dir / "transition_matrix.csv", index_col=0)
            tr = lc_res.get("transitions", {})
            figs.save(F.fig_lifecycle_transitions(mat), "figLC3_transitions",
                      title="Risk-band transitions",
                      caption="Band-to-band movements across %d instrument-sessions: %d "
                              "transitions, %s. Bands exist only so a movement can be "
                              "named; the underlying risk estimate stays continuous."
                              % (lc.get("n_rows", 0), tr.get("n_transitions", 0),
                                 ", ".join("%d %s" % (v, k.lower().replace("_", "-"))
                                           for k, v in
                                           tr.get("by_direction", {}).items())),
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(lc_dir / "transition_matrix.csv"),
                      generation_script=SCRIPT)

        with guard("fig_stage_importance"):
            exp = lc_res.get("EXP-LC-1", {})
            stab = {s["stage"]: s for s in exp.get("within_stage_stability", [])}
            n_stable = sum(1 for s in stab.values() if s.get("top1_stable"))
            figs.save(F.fig_stage_importance(exp.get("per_stage", {}), stab),
                      "figLC4_stage_importance",
                      title="Block importance by lifecycle stage",
                      caption="Permutation importance per feature block, one model per "
                              "stage on a common forward-material-change target. Only "
                              "%d of %d stages produced a ranking that reproduces on "
                              "disjoint halves of the evaluation instruments; the "
                              "others are hatched and must not be read as findings "
                              "(N-06). Fundamental and valuation blocks are absent from "
                              "the dataset entirely (L-13, L-14)."
                              % (n_stable, len(stab)),
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(lc_path), generation_script=SCRIPT)

        with guard("fig_signal_order"):
            order = pd.read_csv(lc_dir / "signal_order.csv")
            figs.save(F.fig_signal_order(order), "figLC5_signal_order",
                      title="Which signal shifts first",
                      caption="Median offset, in sessions, between each block's own "
                              "change point and the change point of the fused risk "
                              "estimate. Negative means the block moved first. Blocks "
                              "contributing fewer than ten instruments are excluded "
                              "rather than plotted with a wide interval. This is "
                              "ordering among the model's own inputs and is not a "
                              "causal statement.",
                      placement="MAIN", dataset=dataset_label,
                      source_data=str(lc_dir / "signal_order.csv"),
                      generation_script=SCRIPT)

        with guard("fig_conflict_stratified"):
            strat = lc_res.get("conflict", {}).get("risk_stratified", {})
            strata = pd.DataFrame(strat.get("strata", []))
            figs.save(F.fig_conflict_stratified(
                strata, float(strat["unconditional"]["difference"]),
                strat.get("pooled_within_stratum_difference")),
                "figLC6_conflict_stratified",
                title="Conflict effect before and after holding risk fixed",
                caption="Difference in the forward material-change rate between rows "
                        "with and without modality conflict. The unconditional "
                        "difference collapses once the risk decile is held fixed, "
                        "because conflict is defined against the same 0.5 threshold "
                        "that separates the MODERATE and ELEVATED bands and therefore "
                        "occurs almost only at high risk (N-07).",
                placement="MAIN", dataset=dataset_label,
                source_data=str(lc_dir / "conflict_risk_stratified.csv"),
                generation_script=SCRIPT)

        with guard("table21_stage_informativeness"):
            exp = lc_res.get("EXP-LC-1", {})
            stab = {s["stage"]: s for s in exp.get("within_stage_stability", [])}
            rows = []
            for m in exp.get("stage_meta", []):
                s = stab.get(m["stage"], {})
                rows.append({
                    "stage": m["stage"], "n_fit": m.get("n_train"),
                    "n_eval": m.get("n_eval"),
                    "n_instruments_eval": m.get("n_instruments_eval"),
                    "base_rate": m.get("positive_rate"), "auprc": m.get("auprc"),
                    "lift_over_base": m.get("lift_over_base"),
                    "split_half_spearman":
                        s.get("within_stage_split_half_spearman"),
                    "top_block": s.get("top_block_full"),
                    "reproducible": s.get("top1_stable"),
                    "status": m.get("status"),
                })
            tabs.save(pd.DataFrame(rows), "table21_stage_informativeness",
                      title="Stage-differential signal informativeness (EXP-LC-1)",
                      caption="Per-stage detection performance and ranking "
                              "reproducibility. The split-half column is the noise "
                              "floor: it is the same importance vector estimated twice "
                              "on disjoint halves of the evaluation instruments, so a "
                              "cross-stage correlation is only interpretable relative "
                              "to it. Only the holding phase clears the bar.")

        with guard("table22_lifecycle_transitions"):
            tr = lc_res.get("transitions", {})
            mat = pd.read_csv(lc_dir / "transition_matrix.csv", index_col=0)
            rows = [{"from_band": idx, **{str(c): int(mat.loc[idx, c])
                                          for c in mat.columns}}
                    for idx in mat.index]
            tabs.save(pd.DataFrame(rows), "table22_lifecycle_transitions",
                      title="Risk-band transition matrix",
                      caption="Counts of band-to-band movements over the lifecycle "
                              "cohort. Mean absolute risk change at a transition is "
                              "%.3f."
                              % (tr.get("mean_abs_delta_risk") or float("nan")))
    else:
        skip("lifecycle_figures",
             "lifecycle.json absent: run scripts/run_lifecycle.py")

    # ------------------------------------------------------------- manifests ----
    progress.log("[14] manifests and paper package")
    figs.write_manifest()
    tabs.write_manifest()

    (paths.MANIFESTS / "not_generated.json").write_text(
        json.dumps(skipped, indent=2), encoding="utf-8")

    ReproducibilityManifest(
        experiment_id=EXPERIMENT_ID, run_id=RUN_ID, seed=20260818,
        config={"dataset": str(data_path), "threshold": float(thr),
                "arm": "FULL", "fusion": full_arm.fusion},
        dataset_version=ds.DATASET_VERSION,
        model_versions={"risk_model": model.version},
        xai_versions={"methods": xm.XAI_VERSION, "benchmark": xb.BENCHMARK_VERSION,
                      "sanity": xs.SANITY_VERSION},
        notes=["synthetic-episode evaluation (L-04)",
               "audio modality is sonification (L-06)",
               "holdout split not evaluated in this run"],
    ).write(paths.MANIFESTS / ("reproducibility_%s.json" % RUN_ID))

    summary = {
        "run_id": RUN_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "figures": figs.summary(),
        "tables": len(tabs.records),
        "not_generated": len(skipped),
        "detection_full_stack": det_full,
        "temporal": {k: v for k, v in temporal.items()
                     if isinstance(v, (int, float))},
        "xai": xai_summary,
        "capital": {k: v for k, v in (cap or {}).items()
                    if k in ("control", "treatment", "delta",
                             "opportunity_cost_total_return", "mean_cap")},
        "environment": environment_snapshot(),
    }
    (paths.STATISTICS / "paper_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")

    _assemble_package(figs, tabs)
    progress.log("done in %.1fs | figures %s | tables %d | not generated %d"
                 % (time.time() - t0, figs.summary(), len(tabs.records), len(skipped)))
    print(json.dumps(summary["figures"], indent=2))
    return 0


def _assemble_package(figs: FigureRegistry, tabs: TableRegistry) -> None:
    pkg = paths.REPO_ROOT / "paper_package"
    if pkg.exists():
        shutil.rmtree(pkg)
    for sub in ("figures", "tables", "captions", "supplementary", "statistics",
                "experiment_manifests", "dataset_manifest", "model_manifest",
                "xai_manifest", "reproducibility", "latex"):
        (pkg / sub).mkdir(parents=True, exist_ok=True)

    for rec in figs.records:
        dest = pkg / ("supplementary" if rec.placement == "SUPPLEMENTARY" else "figures")
        for _fmt, p in rec.output_paths.items():
            if Path(p).exists():
                shutil.copy2(p, dest / Path(p).name)
    for rec in tabs.records:
        for _fmt, p in rec.output_paths.items():
            if Path(p).exists():
                shutil.copy2(p, pkg / "tables" / Path(p).name)
    for p in paths.CAPTIONS.glob("*"):
        shutil.copy2(p, pkg / "captions" / p.name)
    for p in paths.STATISTICS.glob("*"):
        shutil.copy2(p, pkg / "statistics" / p.name)
    for p in paths.MANIFESTS.glob("*.json"):
        shutil.copy2(p, pkg / "reproducibility" / p.name)
    for p in paths.CAPTIONS.glob("*.tex"):
        shutil.copy2(p, pkg / "latex" / p.name)
    for p in paths.TABLES.glob("*.tex"):
        shutil.copy2(p, pkg / "latex" / p.name)

    n_main = sum(1 for r in figs.records if r.placement == "MAIN")
    n_supp = sum(1 for r in figs.records if r.placement == "SUPPLEMENTARY")
    readme = [
        "# AEGIS-Market paper package",
        "",
        "Generated by `scripts/generate_paper_artifacts.py`. Every file here is "
        "reproducible from the dataset, the experiment configuration and the git commit "
        "recorded in `reproducibility/`.",
        "",
        "## Contents", "",
        "- `figures/` %d main-paper figures (png, pdf, svg)" % n_main,
        "- `supplementary/` %d supplementary figures" % n_supp,
        "- `tables/` %d tables in csv, json, markdown and LaTeX" % len(tabs.records),
        "- `captions/` per-figure captions and metadata",
        "- `statistics/` statistical outputs backing every claim",
        "- `reproducibility/` manifests: commit, seeds, versions, hashes",
        "- `latex/` ready-to-include LaTeX snippets",
        "",
        "## Standing caveats",
        "",
        "1. Episode labels are **synthetic**, injected into real NSE price data. "
        "No claim "
        "is made about detecting real-world market manipulation.",
        "2. The universe is a **point-in-time liquidity proxy**, not the Nifty 50.",
        "3. The audio modality is a **sonification** of market data, not speech.",
        "4. True microstructure (order-book depth, OFI, VPIN) is **NOT MEASURED**.",
        "5. The exposure policy is a **research instrument**, not investment advice.",
        "6. The final holdout split has **not** been evaluated.",
        "",
        "See `docs/LIMITATIONS.md` for the full register.",
    ]
    (pkg / "README.md").write_text("\n".join(readme), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
