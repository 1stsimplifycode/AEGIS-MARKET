"""Execute the Scenario Lab and write its artifacts.

    python scripts/run_scenarios.py                # everything
    python scripts/run_scenarios.py --market       # NIFTY-50 catalogue only
    python scripts/run_scenarios.py --transactions # transaction fixture only
    python scripts/run_scenarios.py --quick        # one seed, fewer resamples

Adds no model and no dataset. The market track runs on the same NSE panel, the same
fitted model family and the same exposure policy the headline results use; the
transaction track runs on a declared synthetic fixture and says so on every row it emits.

Five artifacts, one for each question the Scenario Lab is asked:

    scenario_comparison.csv   what happened under each condition
    scenario_uncertainty.csv  how sure we are of each difference
    scenario_ablation.csv     whether the conclusion survives losing a modality
    scenario_robustness.csv   whether it survives re-seeding and re-generating
    scenario_money.csv        the currency figures, with their notional and their caveat

A scenario that fails is recorded as FAILED with its reason. Nothing is substituted.
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
from research.risk.gate import CostModel, GatePolicy, apply_gate, backtest  # noqa: E402
from research.scenario import (  # noqa: E402
    SCENARIO_VERSION,
    SimulationMethod,
    market,
    money,
)
from research.scenario import engine as eng  # noqa: E402
from research.scenario import transactions as txn  # noqa: E402
from research.scenario.spec import ScenarioResult  # noqa: E402
from research.statistics.tests import cvar, moving_block_paired_delta  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "scenario"


# ------------------------------------------------------------------------- data ----

def load_market() -> tuple[pd.DataFrame, pd.DataFrame]:
    data = pd.read_parquet(paths.PANEL / "multimodal_dataset.parquet")
    # The frozen holdout is neither read nor scored anywhere in the Scenario Lab.
    data = data[data["split"] != "holdout"].copy()
    panel = pd.read_parquet(paths.PANEL / "cash_panel.parquet",
                            columns=["symbol", "date", "close"])
    fwd = panel.sort_values(["symbol", "date"]).copy()
    fwd["fwd_ret"] = fwd.groupby("symbol")["close"].pct_change().shift(-1)
    return data, fwd[["symbol", "date", "fwd_ret"]].dropna()


# ---------------------------------------------------------------------- currency ----

def currency_for_policy(engine: eng.ScenarioEngine, spec, b: int) -> dict | None:
    """The rupee figure for one policy scenario, with a moving-block interval.

    Re-runs the exposure comparison on the first seed to recover the two daily series,
    then bootstraps the CVaR difference over 21-session blocks. The figure is expressed
    on the declared notional and carries its caveat in the same record, because a rupee
    number separated from its caveat is the thing a reader will quote.

    The baseline scenario is included with the *default* policy, so the comparison table
    has a reference row. Without it a reader has two tightened policies and nothing to
    read them against.
    """
    if spec.is_baseline:
        policy = GatePolicy()
    elif spec.simulation_method is SimulationMethod.POLICY_COUNTERFACTUAL:
        policy = GatePolicy(**spec.parameters["policy"])
    else:
        return None
    fit = engine.fitted(engine.seeds[0])
    scored = eng.score(fit, engine.evaluation_frame())
    merged = scored.merge(engine.forward, on=["symbol", "date"], how="left")
    merged = merged.dropna(subset=["fwd_ret"])
    gated = apply_gate(merged, policy)
    ctrl = backtest(gated, "w_base", "fwd_ret", CostModel())["net"].to_numpy(float)
    trt = backtest(gated, "w_gated", "fwd_ret", CostModel())["net"].to_numpy(float)
    test = moving_block_paired_delta(ctrl, trt, cvar, block=21, b=b,
                                     seed=spec.random_seed)
    est = money.CurrencyEstimate(
        quantity="daily 5% tail loss",
        fraction=test.statistic,
        fraction_ci_low=test.ci_low,
        fraction_ci_high=test.ci_high,
    )
    return {
        "scenario_id": spec.scenario_id,
        "scenario_name": spec.name,
        "family": spec.family,
        **est.to_dict(),
        "p_value": test.p_value,
        "interval_method": test.test_description,
        "n_sessions": test.n,
        "policy": {"full_allowance_below": policy.full_allowance_below,
                   "zero_allowance_above": policy.zero_allowance_above,
                   "floor": policy.floor,
                   "uncertainty_penalty": policy.uncertainty_penalty},
        "is_baseline_policy": spec.is_baseline,
        # The moving-block bootstrap works on one daily series, so the currency figure is
        # computed on one model seed while the comparison table reports the mean across
        # all of them. Recording which seed is what stops the two being read as a
        # disagreement.
        "model_seed": engine.seeds[0],
        "n_model_seeds_in_comparison": len(engine.seeds),
        "assumptions": list(spec.assumptions),
    }


def transaction_currency(result: ScenarioResult) -> dict | None:
    """The rupee figure for one transaction scenario.

    Weaker than the market one on purpose. It is an accounting fact of the simulation —
    how much labelled-elevated value falls above a declared referral threshold — and not
    a reduction, because the fixture contains no review outcome and inventing an
    effectiveness rate is exactly how a simulation becomes a recovery claim.
    """
    if result.outcome is None or not result.outcome.exposure:
        return None
    e = result.outcome.exposure
    return {
        "scenario_id": result.spec.scenario_id,
        "scenario_name": result.spec.name,
        "family": result.spec.family,
        "quantity": "labelled-elevated transaction value above the referral threshold",
        "amount_inr": e["elevated_value_referred_inr"],
        "elevated_value_total_inr": e["elevated_value_inr"],
        "coverage": e["elevated_value_coverage"],
        "review_load_cases": e["review_load"],
        "review_threshold": e["review_threshold"],
        "amount_ci_low_inr": None,
        "amount_ci_high_inr": None,
        "is_observed": False,
        "caveat": txn.FIXTURE_CAVEAT,
        "reading": ("Value covered by review in simulation, on a declared synthetic "
                    "fixture. Not a reduction, not a recovery, and not a measurement of "
                    "any payments system."),
    }


# ------------------------------------------------------------------------- tracks ----

def run_market(seeds: tuple[int, ...], b: int) -> dict:
    progress.log("[market scenarios] %d scenarios x %d seeds"
                 % (len(market.CATALOGUE), len(seeds)))
    data, fwd = load_market()
    engine = eng.ScenarioEngine(data, forward=fwd, seeds=seeds)
    results = engine.run_catalogue(market.CATALOGUE)
    for r in results:
        progress.log("      %-14s %s  n=%d" % (r.spec.scenario_id, r.status,
                                               r.outcome.n_rows if r.outcome else 0))
    currency = [c for c in (currency_for_policy(engine, s, b)
                            for s in market.CATALOGUE) if c]
    by_id = {c["scenario_id"]: c for c in currency}
    for r in results:
        c = by_id.get(r.spec.scenario_id)
        if c and not r.spec.is_baseline:
            r.interval = {
                "method": "moving_block_paired",
                "point": c["fraction"],
                "ci_low": c["fraction_ci_low"], "ci_high": c["fraction_ci_high"],
                "p_value": c["p_value"], "level": 0.95, "n": c["n_sessions"],
                "description": c["interval_method"],
                "note": "the same interval the currency figure is quoted with, so the "
                        "two tables cannot report different uncertainty for one number",
            }
    return {"results": results, "currency": currency, "engine": engine}


def run_transactions(seeds: tuple[int, ...]) -> dict:
    progress.log("[transaction scenarios] declared synthetic fixture")
    fx = txn.fixture(seed=seeds[0])
    engine = txn.TransactionScenarioEngine(fx.frame)
    results = engine.run_catalogue(txn.CATALOGUE)
    for r in results:
        progress.log("      %-14s %s  n=%d" % (r.spec.scenario_id, r.status,
                                               r.outcome.n_rows if r.outcome else 0))
    currency = [c for c in (transaction_currency(r) for r in results) if c]
    return {"results": results, "currency": currency, "fixture": fx}


def run_ablation(seeds: tuple[int, ...]) -> pd.DataFrame:
    """Does each scenario conclusion survive losing a modality block? (RQ-S4)

    One seed per subset: the question is whether the *sign and rough size* of the
    scenario effect persist, and the seed spread needed to answer that is reported by the
    robustness run rather than repeated inside every subset.
    """
    progress.log("[scenario ablation] %d modality subsets" % len(market.ABLATION_SUBSETS))
    data, fwd = load_market()
    rows = []
    for subset, mods in market.ABLATION_SUBSETS.items():
        engine = eng.ScenarioEngine(data, forward=fwd, seeds=(seeds[0],),
                                    modalities=mods)
        results = engine.run_catalogue(market.CATALOGUE)
        base = results[0]
        for r in results:
            if r.status != "OK" or r.spec.is_baseline:
                continue
            # A scenario that shocks a block this subset removed has no effect by
            # construction. Counting that as a sign flip would report a mechanical zero
            # as a fragile conclusion, which is the opposite of what it is.
            touched = set(r.spec.affected_features)
            removed = set(market.ABLATION_SUBSETS["ALL"]) - set(mods)
            rows.append({
                "subset": subset,
                "n_modalities": len(mods),
                "mechanically_zero": bool(touched & removed),
                "scenario_id": r.spec.scenario_id,
                "scenario_name": r.spec.name,
                "simulation_method": str(r.spec.simulation_method),
                "baseline_risk_mean": base.outcome.risk_mean if base.outcome else np.nan,
                "scenario_risk_mean": r.outcome.risk_mean if r.outcome else np.nan,
                "delta_risk_mean": r.delta_vs_baseline.get("risk_mean", np.nan),
                "delta_uncertainty_mean":
                    r.delta_vs_baseline.get("uncertainty_mean", np.nan),
                "delta_cvar": r.delta_vs_baseline.get("exposure_cvar_delta", np.nan),
                "ci_low": r.interval.get("ci_low"),
                "ci_high": r.interval.get("ci_high"),
            })
        progress.log("      %-12s done" % subset)
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    # Does the direction of the effect survive removing the block?
    full = frame[frame["subset"] == "ALL"].set_index("scenario_id")["delta_risk_mean"]
    frame["sign_matches_full_stack"] = [
        bool(np.sign(d) == np.sign(full.get(s, np.nan)))
        if np.isfinite(d) and np.isfinite(full.get(s, np.nan)) else False
        for s, d in zip(frame["scenario_id"], frame["delta_risk_mean"], strict=False)
    ]
    # The question the ablation actually asks: among the cells where the scenario could
    # still have an effect, does it point the same way?
    frame["informative_cell"] = ~frame["mechanically_zero"]
    frame["direction_survives"] = (frame["sign_matches_full_stack"]
                                   | frame["mechanically_zero"])
    return frame


def run_robustness(seeds: tuple[int, ...]) -> pd.DataFrame:
    """Is a scenario conclusion a property of the condition or of the seed? (RQ-S5)

    Two sources of variation, kept separate because they answer different questions: the
    model's own seed on the market track, and the fixture generator's seed on the
    transaction track. A conclusion that moves more across either than across scenarios
    has not been established.
    """
    progress.log("[scenario robustness] per-seed spread")
    rows = []

    data, fwd = load_market()
    for seed in seeds:
        engine = eng.ScenarioEngine(data, forward=fwd, seeds=(seed,))
        results = engine.run_catalogue(market.CATALOGUE)
        for r in results:
            if r.status != "OK" or r.spec.is_baseline:
                continue
            rows.append({
                "family": "market", "source_of_variation": "model seed", "seed": seed,
                "scenario_id": r.spec.scenario_id,
                "delta_risk_mean": r.delta_vs_baseline.get("risk_mean", np.nan),
                "delta_cvar": r.delta_vs_baseline.get("exposure_cvar_delta", np.nan),
            })
        progress.log("      market seed %d done" % seed)

    for seed in seeds:
        fx = txn.fixture(seed=seed)
        engine = txn.TransactionScenarioEngine(fx.frame)
        results = engine.run_catalogue(txn.CATALOGUE)
        for r in results:
            if r.status != "OK" or r.spec.is_baseline:
                continue
            e = r.outcome.exposure if r.outcome else {}
            rows.append({
                "family": "transaction", "source_of_variation": "fixture seed",
                "seed": seed, "scenario_id": r.spec.scenario_id,
                "delta_risk_mean": r.delta_vs_baseline.get("risk_mean", np.nan),
                "delta_value_coverage":
                    r.delta_vs_baseline.get("exposure_elevated_value_coverage", np.nan),
                "value_coverage": e.get("elevated_value_coverage", np.nan),
            })
        progress.log("      transaction fixture seed %d done" % seed)

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    spread = (frame.groupby(["family", "scenario_id"])["delta_risk_mean"]
              .agg(["mean", "std", "min", "max", "count"]).reset_index()
              .rename(columns={"mean": "delta_mean", "std": "delta_sd",
                               "min": "delta_min", "max": "delta_max",
                               "count": "n_seeds"}))
    spread["stable_sign"] = np.sign(spread["delta_min"]) == np.sign(spread["delta_max"])
    spread["exceeds_seed_spread"] = (
        spread["delta_mean"].abs() > 1.96 * spread["delta_sd"].fillna(0.0))
    return spread


# ------------------------------------------------------------------------- output ----

def uncertainty_table(results: list[ScenarioResult]) -> pd.DataFrame:
    rows = []
    for r in results:
        if r.spec.is_baseline or r.status != "OK":
            continue
        rows.append({
            "scenario_id": r.spec.scenario_id,
            "family": r.spec.family,
            "simulation_method": str(r.spec.simulation_method),
            "headline_metric": r.seed_spread.get("metric"),
            "estimate": r.delta_vs_baseline.get(
                r.seed_spread.get("metric", "risk_mean"), np.nan),
            "ci_low": r.interval.get("ci_low"),
            "ci_high": r.interval.get("ci_high"),
            "p_value": r.interval.get("p_value"),
            "interval_method": r.interval.get("method"),
            "seed_sd": r.seed_spread.get("sd"),
            "exceeds_seed_noise": r.seed_spread.get("exceeds_noise_floor"),
            "n_assumptions": len(r.spec.assumptions),
            "assumptions": " | ".join(r.spec.assumptions),
        })
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", action="store_true")
    ap.add_argument("--transactions", action="store_true")
    ap.add_argument("--quick", action="store_true",
                    help="one seed and fewer bootstrap resamples")
    args = ap.parse_args()
    do_market = args.market or not (args.market or args.transactions)
    do_txn = args.transactions or not (args.market or args.transactions)

    seeds = (eng.DEFAULT_SEEDS[0],) if args.quick else eng.DEFAULT_SEEDS
    b = 300 if args.quick else 2000

    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    progress.log("[scenario lab] seeds=%s" % (seeds,))

    all_results: list[ScenarioResult] = []
    currency: list[dict] = []
    payload: dict = {
        "scenario_version": SCENARIO_VERSION,
        "run_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "environment": environment_snapshot(),
        "seeds": list(seeds),
        "bootstrap_resamples": b,
        "notional": {"inr": money.NOTIONAL_RESEARCH_BASE_INR,
                     "label": money.NOTIONAL_LABEL,
                     "caveat": money.CURRENCY_CAVEAT},
    }

    if do_market:
        m = run_market(seeds, b)
        all_results += m["results"]
        currency += m["currency"]
        payload["market"] = {
            "catalogue_size": len(market.CATALOGUE),
            "results": [r.to_dict() for r in m["results"]],
        }

    if do_txn:
        t = run_transactions(seeds)
        all_results += t["results"]
        currency += t["currency"]
        payload["transaction"] = {
            "catalogue_size": len(txn.CATALOGUE),
            "corpus_search": txn.search_summary(),
            "fixture": t["fixture"].to_dict(),
            "results": [r.to_dict() for r in t["results"]],
        }

    comparison = eng.comparison_table(all_results)
    comparison.to_csv(OUT / "scenario_comparison.csv", index=False)
    uncertainty_table(all_results).to_csv(OUT / "scenario_uncertainty.csv", index=False)
    pd.DataFrame(currency).to_csv(OUT / "scenario_money.csv", index=False)

    if do_market and not args.quick:
        run_ablation(seeds).to_csv(OUT / "scenario_ablation.csv", index=False)
        run_robustness(seeds).to_csv(OUT / "scenario_robustness.csv", index=False)

    problems = [p for r in all_results for p in r.check()]
    payload["currency"] = currency
    payload["n_scenarios"] = len(all_results)
    payload["n_failed"] = sum(1 for r in all_results if r.status != "OK")
    payload["problems"] = problems
    payload["elapsed_s"] = round(time.time() - t0, 1)
    jsonio.write(OUT / "scenario_results.json", payload)

    for p in problems:
        progress.log("  PROBLEM %s" % p)
    progress.log("%d scenarios, %d failed, %d problems, %.1fs"
                 % (len(all_results), payload["n_failed"], len(problems),
                    payload["elapsed_s"]))
    return 1 if problems or payload["n_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
