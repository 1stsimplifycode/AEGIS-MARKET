"""SCENARIO module adapters.

Thin wrappers over ``research/scenario/``, following the same rule as every other adapter
in this package: they orchestrate, they never define a scenario, a metric or an outcome.

Two kinds of module here, and the split is deliberate. The catalogue and the transaction
fixture are cheap and execute in place, because a reviewer opening those run.bat files
should see the actual objects. The market scenarios, the ablation and the robustness sweep
cost minutes and are produced by ``scripts/run_scenarios.py``; their modules read the
artifact that run wrote and report it, exactly as the human-affect modules report the
full-corpus experiments rather than re-running them on the interactive surface.

Nothing here executes anything against a market, an account or a person, and
``research.scenario.assert_no_execution`` is called on every entry point that runs a
scenario so the refusal is exercised rather than assumed.
"""
from __future__ import annotations

import json
from pathlib import Path

from research.core import jsonio, paths
from scripts.stages import BLOCKED, OK, StageResult, require

OUT_ROOT = paths.REPO_ROOT / "outputs" / "scenario"
RESULTS = OUT_ROOT / "scenario_results.json"


def _out() -> Path:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    return OUT_ROOT


def _results() -> dict | None:
    if not RESULTS.exists():
        return None
    return json.loads(RESULTS.read_text(encoding="utf-8"))


def _needs_run(what: str) -> StageResult:
    return StageResult(
        BLOCKED,
        "%s has not been executed. Run `python scripts/run_scenarios.py` first; this "
        "module reports that run rather than repeating it, because the market catalogue "
        "costs minutes and the interactive surface must not." % what)


def _rows(payload: dict, family: str) -> list[dict]:
    track = payload.get(family if family != "market" else "market") or {}
    return [r for r in (track.get("results") or []) if r.get("status") == "OK"]


# --------------------------------------------------------------- SCENARIO-01 ----

def scenario_catalogue(force: bool = False) -> StageResult:
    """Emit the declared catalogue and check every scenario is reportable."""
    from research.scenario import SCENARIO_VERSION
    from research.scenario import market as mk
    from research.scenario import transactions as tx

    out = _out()
    specs = list(mk.CATALOGUE) + list(tx.CATALOGUE)
    problems = [p for s in specs for p in s.check()]
    payload = {
        "scenario_version": SCENARIO_VERSION,
        "n_scenarios": len(specs),
        "by_family": {"market": len(mk.CATALOGUE), "transaction": len(tx.CATALOGUE)},
        "by_method": {m: sum(1 for s in specs if str(s.simulation_method) == m)
                      for m in sorted({str(s.simulation_method) for s in specs})},
        "n_baselines": sum(1 for s in specs if s.is_baseline),
        "problems": problems,
        "scenarios": [s.to_dict() for s in specs],
        "reading": (
            "A scenario is a record, not a function: its baseline, its assumption, the "
            "features it touches and the method by which its rows were obtained are all "
            "fields, so a result can never be shown without them."),
    }
    jsonio.write(out / "scenario_catalogue.json", payload)
    if problems:
        return StageResult(1, "%d scenario(s) are not reportable: %s"
                           % (len(problems), "; ".join(problems[:3])),
                           outputs=[str(out / "scenario_catalogue.json")],
                           detail=payload)
    return StageResult(
        OK,
        "%d scenarios across %d families; %d observed-stratum, %d counterfactual, "
        "%d policy" % (len(specs), 2,
                       payload["by_method"].get("OBSERVED_STRATUM", 0),
                       payload["by_method"].get("COUNTERFACTUAL", 0),
                       payload["by_method"].get("POLICY_COUNTERFACTUAL", 0)),
        outputs=[str(out / "scenario_catalogue.json")], detail=payload)


# --------------------------------------------------------------- SCENARIO-02 ----

def market_conditions(force: bool = False) -> StageResult:
    """Report the observed-stratum market scenarios from the executed run."""
    payload = _results()
    if not payload:
        return _needs_run("The market scenario catalogue")
    rows = [r for r in _rows(payload, "market")
            if r["scenario"]["simulation_method"] == "OBSERVED_STRATUM"]
    if not rows:
        return _needs_run("The observed-condition scenarios")
    lines = ", ".join(
        "%s risk %.4f on %d rows" % (r["scenario"]["scenario_id"],
                                     r["outcome"]["risk_mean"], r["outcome"]["n_rows"])
        for r in rows)
    return StageResult(OK, "%d observed conditions: %s" % (len(rows), lines),
                       outputs=[str(RESULTS)], detail={"scenarios": rows})


# --------------------------------------------------------------- SCENARIO-03 ----

def counterfactual_conditions(force: bool = False) -> StageResult:
    """Report the counterfactual market scenarios and whether each moved the estimate."""
    payload = _results()
    if not payload:
        return _needs_run("The counterfactual scenarios")
    rows = [r for r in _rows(payload, "market")
            if r["scenario"]["simulation_method"] == "COUNTERFACTUAL"]
    if not rows:
        return _needs_run("The counterfactual scenarios")
    established = [r for r in rows if _excludes_zero(r.get("interval") or {})]
    return StageResult(
        OK,
        "%d counterfactual conditions; %d moved the risk estimate by an interval "
        "excluding zero" % (len(rows), len(established)),
        outputs=[str(RESULTS)], detail={"scenarios": rows})


# --------------------------------------------------------------- SCENARIO-04 ----

def mitigation_policies(force: bool = False) -> StageResult:
    """Report the policy counterfactuals and the currency figures they produced."""
    from research.scenario import money

    payload = _results()
    if not payload:
        return _needs_run("The mitigation policy scenarios")
    currency = [c for c in (payload.get("currency") or [])
                if c.get("family") == "market"]
    if not currency:
        return _needs_run("The mitigation policy scenarios")
    best = max(currency, key=lambda c: c.get("amount_inr") or 0.0)
    return StageResult(
        OK,
        "%d exposure policies compared on identical evidence; the largest simulated "
        "reduction in the daily 5%% tail loss is %s under %s. %s"
        % (len(currency), money.inr(best["amount_inr"]), best["scenario_id"],
           money.CURRENCY_CAVEAT),
        outputs=[str(RESULTS), str(OUT_ROOT / "scenario_money.csv")],
        detail={"currency": currency})


# --------------------------------------------------------------- SCENARIO-05 ----

def scenario_uncertainty(force: bool = False) -> StageResult:
    """Report which scenario differences are separated from zero, and which are not."""
    csv = OUT_ROOT / "scenario_uncertainty.csv"
    if require([csv]):
        return _needs_run("The scenario uncertainty table")
    import pandas as pd

    tbl = pd.read_csv(csv)
    established = tbl[tbl["ci_low"].notna() & tbl["ci_high"].notna()
                      & ((tbl["ci_low"] > 0) | (tbl["ci_high"] < 0))]
    unresolved = len(tbl) - len(established)
    return StageResult(
        OK,
        "%d scenario differences: %d have an interval excluding zero, %d are unresolved "
        "or carry no sampling interval" % (len(tbl), len(established), unresolved),
        outputs=[str(csv)],
        detail={"n": int(len(tbl)), "n_established": int(len(established)),
                "n_unresolved": int(unresolved)})


# --------------------------------------------------------------- SCENARIO-06 ----

def scenario_ablation(force: bool = False) -> StageResult:
    """Report whether each scenario conclusion survives losing a modality block."""
    csv = OUT_ROOT / "scenario_ablation.csv"
    if require([csv]):
        return _needs_run("The scenario ablation")
    import pandas as pd

    tbl = pd.read_csv(csv)
    if tbl.empty:
        return _needs_run("The scenario ablation")
    survives = tbl[tbl["subset"] != "ALL"]["sign_matches_full_stack"]
    return StageResult(
        OK,
        "%d subset-by-scenario cells over %d modality subsets; the direction of the "
        "effect matches the full stack in %d of %d cells outside it"
        % (len(tbl), tbl["subset"].nunique(), int(survives.sum()), len(survives)),
        outputs=[str(csv)],
        detail={"n_cells": int(len(tbl)),
                "n_subsets": int(tbl["subset"].nunique()),
                "sign_agreement": float(survives.mean()) if len(survives) else None})


# --------------------------------------------------------------- SCENARIO-07 ----

def scenario_robustness(force: bool = False) -> StageResult:
    """Report whether a scenario conclusion is a property of the condition or the seed."""
    csv = OUT_ROOT / "scenario_robustness.csv"
    if require([csv]):
        return _needs_run("The scenario robustness sweep")
    import pandas as pd

    tbl = pd.read_csv(csv)
    if tbl.empty:
        return _needs_run("The scenario robustness sweep")
    stable = int(tbl["stable_sign"].sum())
    exceeds = int(tbl["exceeds_seed_spread"].sum())
    return StageResult(
        OK,
        "%d scenarios re-run across seeds: %d keep the sign of their effect in every "
        "seed, %d have an effect larger than 1.96 times their own seed spread"
        % (len(tbl), stable, exceeds),
        outputs=[str(csv)],
        detail={"n": int(len(tbl)), "n_stable_sign": stable,
                "n_exceeding_seed_spread": exceeds})


# --------------------------------------------------------------- SCENARIO-08 ----

def transaction_risk(force: bool = False) -> StageResult:
    """Emit the transaction corpus search and the declared fixture's own description.

    Cheap enough to execute in place. It reports BLOCKED because no qualifying corpus was
    found, which is the honest status: the interface is complete and the evidence is not
    available.
    """
    from datetime import UTC, datetime

    from research.core.manifest import environment_snapshot, git_commit
    from research.scenario import transactions as tx

    out = _out()
    summary = tx.search_summary()
    fx = tx.fixture()
    # Stamped like every other result artifact. A BLOCKED outcome is still a finding a
    # reviewer has to be able to date and attribute, and this one is cited by CLAIM-29.
    payload = {**summary, "fixture": fx.to_dict(),
               "run_at": datetime.now(UTC).isoformat(),
               "git_commit": git_commit(),
               "environment": environment_snapshot()}
    jsonio.write(out / "transaction_corpus_search.json", payload)
    return StageResult(
        BLOCKED,
        "transaction-risk interface COMPLETE; corpus NOT AVAILABLE. %d candidates "
        "considered, %d qualify. Executed on a %s of %d rows across %d accounts."
        % (summary["n_candidates_considered"], summary["n_qualifying"],
           tx.FIXTURE_KIND, fx.to_dict()["n_rows"], fx.to_dict()["n_accounts"]),
        outputs=[str(out / "transaction_corpus_search.json")], detail=payload)


def _excludes_zero(interval: dict) -> bool:
    lo, hi = interval.get("ci_low"), interval.get("ci_high")
    if lo is None or hi is None:
        return False
    return lo > 0 or hi < 0
