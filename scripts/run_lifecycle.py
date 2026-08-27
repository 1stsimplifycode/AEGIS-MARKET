"""Execute the position-lifecycle analyses (domain requirement).

    python scripts/run_lifecycle.py

Runs what the available data supports:

* lifecycle state trajectories, phases and risk-band transitions
* change-point detection on the risk trajectory
* signal-ordering around change points -- which block shifts first
* the stage-differential experiment: do the informative signals differ between ENTRY,
  HOLDING and RESOLUTION?
* signal agreement, conflict and dominance, and their association with forward change
* EXP-L15-1: whether the stage result survives redefining the phases

Two design decisions worth stating up front, because both are load-bearing:

**The scored frame is rebuilt here, and the holdout stays frozen.**
``per_row_FULL.parquet`` is the validation split scored for detection, which is not the
same thing as a trajectory. This refits on train and rescores every validation row, so
each instrument carries one continuous out-of-sample series. Training rows are never
scored: an in-sample stretch at the start of every trajectory would put the quietest part
of the risk series exactly where ENTRY is defined.

Extending into the holdout would raise the cohort from 35 instruments to 53. It is not
done. The holdout is a one-shot resource reserved for the final detection evaluation
(L-11), and the stage question is unresolvable at either cohort size, so spending it here
would buy nothing and cost the only clean split left.

**The stage comparison splits by instrument, not by time.** Phase is defined by position
within an instrument's window, so a temporal split would place ENTRY rows almost entirely
on one side and RESOLUTION rows on the other -- the split and the stage would be the same
variable, and any stage difference would be unattributable. Splitting the cohort into two
disjoint halves of instruments keeps all three phases present on both sides.

What it does not run, and does not simulate: anything requiring fundamentals or
valuation. Those blocks do not exist in this dataset (L-13, L-14) and their experiments
stay BLOCKED with no number attached.
"""
from __future__ import annotations

import sys
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from research.core import jsonio, paths, progress
from research.core.manifest import environment_snapshot
from research.data import dataset as ds
from research.lifecycle import changepoints as cp
from research.lifecycle import stages as st
from research.lifecycle import states as ls
from research.models.risk_model import AegisRiskModel

OUT = paths.ARTIFACTS / "lifecycle"

SEED = 20260818

#: Splits scored here. The holdout is deliberately absent: it is reserved for the final
#: detection evaluation (L-11) and has not been looked at. Including it would grow the
#: cohort from 35 instruments to 53 without changing any conclusion below.
SCORED_SPLITS = ["validation"]
#: Minimum out-of-sample sessions for an instrument to enter the lifecycle cohort.
#: Below roughly this many observations, binary segmentation has fewer points than its
#: own minimum segment size on both sides and would return either nothing or noise.
MIN_SESSIONS = 30

BLOCK_SCORE_COLS = {
    "market": "score_market", "microstructure": "score_microstructure",
    "regime": "score_regime", "propagation": "score_propagation",
    "text": "score_text", "image": "score_image", "audio": "score_audio",
    "video": "score_video",
}


def score_out_of_sample(data: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Fit on train, score the validation split as one continuous trajectory."""
    train = data[data["split"] == "train"]
    oos = (data[data["split"].isin(SCORED_SPLITS)]
           .sort_values(["symbol", "date"]).reset_index(drop=True))
    model = AegisRiskModel(modalities=list(ds.MODALITY_BLOCKS),
                           fusion_strategy="regime_corrected", seed=SEED)
    model.fit(train, train["is_episode"].to_numpy(int))
    pred = model.predict(oos)

    keep = [c for c in ["symbol", "date", "split", "is_episode", "episode_id"]
            if c in oos.columns]
    scored = oos[keep].copy()
    scored["integrity_risk"] = pred["integrity_risk"]
    scored["uncertainty"] = pred["uncertainty"]
    scored["coverage"] = pred["coverage"]
    for i, m in enumerate(pred["modality_names"]):
        scored["score_%s" % m] = pred["modality_scores"][:, i]
        scored["contrib_%s" % m] = pred["modality_contribution"][:, i]

    meta = {
        "n_train_rows": int(len(train)),
        "n_scored_rows": int(len(scored)),
        "scored_splits": list(SCORED_SPLITS),
        "holdout_used": "holdout" in SCORED_SPLITS,
        "holdout_note": "The holdout split is frozen (L-11) and was not scored.",
        "date_range": [str(pd.Timestamp(scored["date"].min()).date()),
                       str(pd.Timestamp(scored["date"].max()).date())],
        "in_sample_rows_scored": 0,
    }
    return scored, meta


def build_cohort(scored: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Restrict to instruments with enough sessions to carry a trajectory."""
    n = scored.groupby("symbol").size()
    keep = set(n[n >= MIN_SESSIONS].index)
    cohort = scored[scored["symbol"].isin(keep)].copy()
    meta = {
        "min_sessions": MIN_SESSIONS,
        "n_instruments_available": int(scored["symbol"].nunique()),
        "n_instruments_in_cohort": int(len(keep)),
        "n_instruments_excluded": int(scored["symbol"].nunique() - len(keep)),
        "n_rows_in_cohort": int(len(cohort)),
        "median_sessions_in_cohort": float(n[n >= MIN_SESSIONS].median())
        if keep else float("nan"),
        "selection_note": (
            "Instruments are excluded for having too few out-of-sample sessions, which "
            "correlates with listing date and with liquidity. The cohort is therefore "
            "not a random sample of the universe, and no lifecycle result generalises "
            "to the excluded names."),
    }
    return cohort, meta


def instrument_split(cohort: pd.DataFrame, seed: int = SEED
                     ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split the cohort into two disjoint halves of instruments.

    By instrument rather than by date: see the module docstring. Deterministic given the
    seed, so the stage tables regenerate identically.
    """
    syms = np.array(sorted(cohort["symbol"].unique()))
    rng = np.random.default_rng(seed)
    rng.shuffle(syms)
    cut = len(syms) // 2
    fit_syms, eval_syms = set(syms[:cut]), set(syms[cut:])
    return (cohort[cohort["symbol"].isin(fit_syms)],
            cohort[cohort["symbol"].isin(eval_syms)])


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    results: dict = {}

    dpath = paths.PANEL / "multimodal_dataset.parquet"
    if not dpath.exists():
        raise SystemExit(
            "multimodal_dataset.parquet missing: run scripts/build_dataset.py")
    data = pd.read_parquet(dpath)

    progress.log("[1/7] scoring %s from a train-fitted model (holdout stays frozen)"
                 % "+".join(SCORED_SPLITS))
    scored, score_meta = score_out_of_sample(data)
    progress.log("      %d rows scored, %s to %s"
                 % (score_meta["n_scored_rows"], score_meta["date_range"][0],
                    score_meta["date_range"][1]))

    cohort, cohort_meta = build_cohort(scored)
    progress.log("      cohort: %d of %d instruments with >=%d sessions (%d rows)"
                 % (cohort_meta["n_instruments_in_cohort"],
                    cohort_meta["n_instruments_available"], MIN_SESSIONS,
                    cohort_meta["n_rows_in_cohort"]))
    if cohort.empty:
        raise SystemExit("no instrument has enough sessions for a lifecycle trajectory")

    progress.log("[2/7] change points on the risk trajectory")
    cps = cp.detect_per_instrument(cohort)
    n_with = sum(1 for v in cps.values() if v)
    n_points = sum(len(v) for v in cps.values())
    progress.log("      %d of %d instruments have at least one change point (%d total)"
                 % (n_with, len(cps), n_points))

    progress.log("[3/7] lifecycle trajectories, phases and states")
    mod_cols = [c for c in BLOCK_SCORE_COLS.values() if c in cohort.columns]
    traj = ls.build_trajectories(cohort, mod_cols, change_points=cps)
    traj = st.material_transition_target(traj, horizon=10, min_delta=0.15)
    traj.to_parquet(OUT / "lifecycle_trajectories.parquet", index=False)
    state_counts = {str(k): int(v)
                    for k, v in traj["lifecycle_state"].value_counts().items()}
    phase_counts = {str(k): int(v) for k, v in traj["phase"].value_counts().items()}
    progress.log("      states: %s" % state_counts)
    progress.log("      phases: %s" % phase_counts)
    progress.log("      material change within 10 sessions: %.3f"
                 % traj["material_change_ahead"].mean())

    progress.log("[4/7] risk-band transitions")
    transitions = ls.extract_transitions(traj, mod_cols)
    ttab = ls.transition_table(transitions)
    if len(ttab):
        ttab.to_csv(OUT / "transitions.csv", index=False)
    tmat = ls.transition_matrix(traj)
    tmat.to_csv(OUT / "transition_matrix.csv")
    results["transitions"] = {
        "analysis": "risk_band_transitions",
        "status": "MEASURED" if len(ttab) else "NO TRANSITIONS OBSERVED",
        "n_transitions": int(len(ttab)),
        "by_direction": ({str(k): int(v)
                          for k, v in ttab["direction"].value_counts().items()}
                         if len(ttab) else {}),
        "by_phase": ({str(k): int(v) for k, v in ttab["phase"].value_counts().items()}
                     if len(ttab) else {}),
        "mean_abs_delta_risk": float(ttab["delta_risk"].abs().mean())
        if len(ttab) else None,
        "matrix": {str(k): {str(k2): int(v2) for k2, v2 in v.items()}
                   for k, v in tmat.to_dict().items()},
    }
    progress.log("      %d band transitions: %s"
                 % (len(ttab), results["transitions"]["by_direction"]))

    progress.log("[5/7] signal ordering around change points")
    order = cp.signal_change_order(cohort, BLOCK_SCORE_COLS)
    summary = cp.summarise_order(order)
    if len(summary):
        summary.to_csv(OUT / "signal_order.csv", index=False)
        for _, r in summary.iterrows():
            progress.log("      %-15s n=%-4d median offset %+6.1f  %s"
                         % (r["block"], r["n_instruments"], r["median_offset"],
                            r["reading"]))
    results["signal_order"] = {
        "analysis": "signal_change_ordering",
        "status": "MEASURED" if len(summary) else "INSUFFICIENT DATA",
        "rows": summary.to_dict(orient="records") if len(summary) else [],
        "caveat": ("Ordering among the model's own inputs. It does not establish that "
                   "one signal causes another, and fundamentals are absent entirely "
                   "(L-13)."),
    }

    progress.log("[6/7] EXP-LC-1: stage-differential signal informativeness")
    feat_cols = [c for c in data.columns
                 if c not in traj.columns or c in ("symbol", "date")]
    merged = traj.merge(data[feat_cols], on=["symbol", "date"], how="left")
    fit_half, eval_half = instrument_split(merged)
    progress.log("      instrument split: %d fit / %d eval instruments"
                 % (fit_half["symbol"].nunique(), eval_half["symbol"].nunique()))
    stage = st.stage_informativeness(fit_half, eval_half)
    stage["split_design"] = "disjoint instruments, seed %d" % SEED
    results["EXP-LC-1"] = {"experiment": "EXP-LC-1", **stage}
    for m in stage.get("stage_meta", []):
        progress.log("      %-11s n_fit=%-5d n_eval=%-5d pos=%-6s auprc=%-7s %s"
                     % (m["stage"], m.get("n_train", 0), m.get("n_eval", 0),
                        ("%.3f" % m["positive_rate"])
                        if m.get("positive_rate") == m.get("positive_rate") else "n/a",
                        ("%.4f" % m["auprc"])
                        if m.get("auprc") == m.get("auprc") else "n/a", m["status"]))
    for s in stage.get("within_stage_stability", []):
        progress.log("      %-11s split-half rho %+.3f  top block %s vs %s  "
                     "stable=%s  positive in both: %s"
                     % (s["stage"], s["within_stage_split_half_spearman"],
                        s.get("top_block_half_a", "?"), s.get("top_block_half_b", "?"),
                        s.get("top1_stable"),
                        ",".join(s.get("blocks_positive_in_both_halves", [])) or "none"))
    for a in stage.get("cross_stage_agreement", []):
        progress.log("      %s vs %s: spearman %+.3f, top-3 overlap %d/3, "
                     "top block %s vs %s"
                     % (a["stage_a"], a["stage_b"], a["spearman"], a["top3_overlap"],
                        a["top_block_a"], a["top_block_b"]))
        progress.log("           -> %s" % a["reading"])
    for k, v in stage.get("per_stage", {}).items():
        pd.DataFrame(v).to_csv(OUT / ("stage_importance_%s.csv" % k.lower()),
                               index=False)

    progress.log("[7/7] signal conflict and its association with forward change")
    conf = st.signal_conflict(traj, mod_cols)
    cvo = st.conflict_vs_outcome(conf)
    if len(cvo):
        cvo.to_csv(OUT / "conflict_vs_outcome.csv", index=False)
        for _, r in cvo.iterrows():
            if r.get("status") == "OK":
                progress.log("      conflict %.2f-%.2f  n=%-5d  change rate %.3f"
                             % (r["conflict_low"], r["conflict_high"], r["n"],
                                r["material_change_rate"]))
    strat = st.conflict_vs_outcome_stratified(conf)
    pd.DataFrame(strat.get("strata", [])).to_csv(
        OUT / "conflict_risk_stratified.csv", index=False)
    progress.log("      unconditional difference %+.3f; %s"
                 % (strat["unconditional"]["difference"], strat["conclusion"]))
    dom = (conf["dominant_signal"].value_counts(normalize=True).to_dict()
           if "dominant_signal" in conf.columns
           and conf["dominant_signal"].notna().any() else {})
    results["conflict"] = {
        "analysis": "signal_conflict", "status": "MEASURED",
        "mean_agreement": float(conf["signal_agreement"].mean()),
        "mean_conflict": float(conf["signal_conflict"].mean()),
        "dominance_share": {str(k): float(v) for k, v in dom.items()},
        "buckets": cvo.to_dict(orient="records") if len(cvo) else [],
        "risk_stratified": strat,
        "caveat": ("Conflict is defined against the same 0.5 threshold that separates "
                   "the MODERATE and ELEVATED bands, so conflicting rows sit at high "
                   "risk by construction. Only the risk-stratified figure is "
                   "interpretable; the unconditional contrast is a restatement of the "
                   "risk level."),
    }

    # EXP-L15-1: does the stage result survive redefining the phase?
    progress.log("      EXP-L15-1: re-running with change-point-relative phases")
    alt = merged.copy()
    parts = []
    for sym, g in alt.sort_values(["symbol", "date"]).groupby("symbol", sort=False):
        n = len(g)
        pts = cps.get(sym, [])
        if pts:
            first = pts[0]
            ph = [ls.Phase.HOLDING.value] * n
            for i in range(n):
                if i < max(0, first - 10):
                    ph[i] = ls.Phase.ENTRY.value
                elif i > min(n - 1, first + 10):
                    ph[i] = ls.Phase.RESOLUTION.value
        else:
            ph = ls.assign_phase(n)
        parts.append(pd.Series(ph, index=g.index))
    alt["phase"] = pd.concat(parts).sort_index()
    alt_fit, alt_eval = instrument_split(alt)
    alt_stage = st.stage_informativeness(alt_fit, alt_eval)
    for k, v in alt_stage.get("per_stage", {}).items():
        pd.DataFrame(v).to_csv(
            OUT / ("stage_importance_changepoint_%s.csv" % k.lower()), index=False)

    from scipy.stats import spearmanr
    comparisons = []
    shared = sorted(set(stage.get("per_stage", {}))
                    & set(alt_stage.get("per_stage", {})))
    for s in shared:
        a = pd.DataFrame(stage["per_stage"][s]).set_index("block")["importance"]
        b = pd.DataFrame(alt_stage["per_stage"][s]).set_index("block")["importance"]
        common = a.index.intersection(b.index)
        if len(common) < 3:
            continue
        rho = spearmanr(a[common], b[common]).statistic
        comparisons.append({"stage": s, "n_blocks": int(len(common)),
                            "spearman_between_definitions":
                            float(rho) if rho == rho else None})
        progress.log("      %-11s window-position vs change-point phases: rho %+.3f"
                     % (s, rho))
    results["EXP-L15-1"] = {
        "experiment": "EXP-L15-1",
        "status": "MEASURED" if comparisons else "INSUFFICIENT DATA",
        "comparisons": comparisons,
        "alt_stage_meta": alt_stage.get("stage_meta", []),
        "interpretation_rule": (
            "A high correlation means the stage-differential finding is a property of "
            "the lifecycle stage rather than of how the stage was defined. A low one "
            "means it should not be reported as a stage effect at all."),
    }

    payload = {
        "run_at": datetime.now(UTC).isoformat(),
        "lifecycle_version": ls.LIFECYCLE_VERSION,
        "changepoint_version": cp.CHANGEPOINT_VERSION,
        "stages_version": st.STAGES_VERSION,
        "seed": SEED,
        "scoring": score_meta,
        "cohort": cohort_meta,
        "n_rows": int(len(traj)),
        "state_counts": state_counts,
        "phase_counts": phase_counts,
        "material_change_base_rate": float(traj["material_change_ahead"].mean()),
        "instruments_with_change_points": n_with,
        "n_change_points": n_points,
        "results": results,
        "not_available": {
            "fundamentals": "L-13: revenue growth, net debt, interest coverage, "
                            "earnings and cash flow are absent from this dataset",
            "valuation": "L-14: P/E, P/B, EV/EBITDA and FCF yield need accounting "
                         "quantities that are absent",
            "observed_positions": "L-15: no real holding period is observed; phases are "
                                  "analytical",
        },
        "environment": environment_snapshot(),
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "lifecycle.json", payload)
    progress.log("done in %.1fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
