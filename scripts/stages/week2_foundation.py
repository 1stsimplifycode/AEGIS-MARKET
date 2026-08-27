"""The Week 2 market and liquidity layer, as the product and research views consume it.

Every value here is read from the artifacts ``scripts/build_week2_foundation.py`` wrote,
which are the same artifacts the C1-C7 tests assert against. Nothing is recomputed with
different parameters for display, and nothing is hardcoded: a page cannot show a liquidity
number the research layer would not stand behind.

Anything unavailable comes back as ``available: False`` with a reason. A liquidity metric
that is simply absent from a response renders as a blank, and a blank reads as "nothing
unusual" -- which is a claim, and usually the wrong one.
"""
from __future__ import annotations

import functools
import json

import pandas as pd

from research.core import paths
from research.detection import count_events as CE
from research.market import liquidity as L
from research.reference import week2_inputs as W2

WEEK2_VERSION = "week2-foundation-v1"


def _unavailable(what: str, why: str) -> dict:
    return {"available": False, "what": what, "why": why,
            "remedy": "Run scripts/build_week2_foundation.py."}


@functools.lru_cache(maxsize=1)
def _read(name: str) -> pd.DataFrame | None:
    p = paths.REFERENCE / name
    return pd.read_parquet(p) if p.exists() else None


@functools.lru_cache(maxsize=1)
def realised_variance() -> pd.DataFrame | None:
    return _read("realised_variance.parquet")


@functools.lru_cache(maxsize=1)
def price_impact() -> pd.DataFrame | None:
    return _read("price_impact.parquet")


@functools.lru_cache(maxsize=1)
def arrival_fits() -> pd.DataFrame | None:
    return _read("arrival_fits.parquet")


@functools.lru_cache(maxsize=1)
def liquidity_state() -> pd.DataFrame | None:
    return _read("liquidity_state.parquet")


@functools.lru_cache(maxsize=1)
def foundation() -> dict:
    p = paths.REPO_ROOT / "outputs" / "week2" / "foundation_summary.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


# -- per instrument ---------------------------------------------------------------------

def instrument_liquidity(symbol: str) -> dict:
    """Every Week 2 estimator for one security, each with its uncertainty and basis."""
    sym = str(symbol or "").upper().strip()
    out: dict = {"week2_version": WEEK2_VERSION, "symbol": sym}

    rv = realised_variance()
    if rv is None or rv[rv["symbol"] == sym].empty:
        out["realised_variance"] = _unavailable(
            "Realised variance",
            "No intraday bars for %s. The vendor window covers the recent period and "
            "the current universe only." % sym)
    else:
        g = rv[rv["symbol"] == sym].sort_values("session")
        last = g.iloc[-1]
        out["realised_variance"] = {
            "available": True,
            "estimator": "RV = sum of squared intraday log returns",
            "sampling_minutes": int(last["sampling_minutes"]),
            "latest_session": str(pd.Timestamp(last["session"]).date()),
            "realised_variance": float(last["realised_variance"]),
            "annualised_volatility": float(last["realised_volatility_annualised"]),
            "n_returns": int(last["n_returns"]),
            "relative_standard_error": float(last["rv_relative_standard_error"]),
            "sessions": int(len(g)),
            "basis": "THIRD_PARTY_REDISTRIBUTOR (not an NSE publication)",
        }

    pi = price_impact()
    if pi is None or pi[pi["symbol"] == sym].empty:
        out["price_impact"] = _unavailable(
            "Price impact", "No intraday bars for %s to regress on." % sym)
    else:
        r = pi[pi["symbol"] == sym].iloc[0]
        out["price_impact"] = {
            "available": True,
            "specification": "r_i = alpha + lambda * signed_volume_i + e_i",
            "lambda": float(r["lambda"]),
            "standard_error": float(r["lambda_standard_error"]),
            "t_stat": float(r["lambda_t_stat"]),
            "ci_low": float(r["lambda_ci_low"]),
            "ci_high": float(r["lambda_ci_high"]),
            "n_obs": int(r["n_obs"]),
            "r_squared": float(r["r_squared"]),
            "significant": bool(abs(float(r["lambda_t_stat"])) > 1.96),
            "sign_carried_forward_share": float(r["sign_carried_forward_share"]),
            "signing_basis": r["signing_basis"],
            "caveat": ("Trade direction is inferred by the tick test, not published by "
                       "NSE. The coefficient is attenuated toward zero as a result."),
        }

    ar = arrival_fits()
    if ar is None or ar[ar["symbol"] == sym].empty:
        out["arrival"] = _unavailable("Trade arrival", "No arrival fit for %s." % sym)
    else:
        r = ar[ar["symbol"] == sym].iloc[0]
        out["arrival"] = {
            "available": True,
            "mean_daily_trades": float(r["mean_daily_trades"]),
            "poisson_lambda": float(r["poisson_lambda"]),
            "poisson_lambda_standard_error": float(
                r["poisson_lambda_standard_error"]),
            "fano_factor": float(r["fano_factor"]),
            "nb_dispersion_k": float(r["nb_dispersion_k"]),
            "dispersion_p_value": float(r["dispersion_p_value"]),
            "overdispersed": bool(r["overdispersed"]),
            "model_selected": r["model_selected"],
            "interpretation": r["interpretation"],
            "n_sessions": int(r["n_sessions"]),
            "basis": "DERIVED_FROM_EXCHANGE_DATA (bhavcopy trade counts)",
        }

    st = liquidity_state()
    if st is None or st[st["symbol"] == sym].empty:
        out["liquidity_state"] = _unavailable(
            "Liquidity state", "No state vector rows for %s." % sym)
    else:
        g = st[st["symbol"] == sym].sort_values("session")
        last = g.iloc[-1]
        components = [c for c in L.COMPONENTS if c in st.columns]
        attribution = {c: float(last.get("attribution_%s" % c, 0.0))
                       for c in components}
        out["liquidity_state"] = {
            "available": True,
            "vector": "L = [%s]" % ", ".join(components),
            "latest_session": str(pd.Timestamp(last["session"]).date()),
            "components": {c: {
                "value": (float(last[c]) if pd.notna(last.get(c)) else None),
                "robust_z": (float(last["z_%s" % c])
                             if pd.notna(last.get("z_%s" % c)) else None),
                "label": L.COMPONENT_LABELS.get(c, c),
            } for c in components},
            "stress_score": float(last["stress_score"]),
            "stress_gate_fired": bool(last["stress_gate_fired"]),
            "attribution": attribution,
            "primary_driver": str(last.get("primary_driver", "")),
            "sessions_stressed": int(g["stress_gate_fired"].sum()),
            "sessions": int(len(g)),
            "attribution_rule": (
                "contribution_j = z_j / sum over components with z_k > 0, computed from "
                "this row's own z-scores"),
        }
    return out


# -- week level -------------------------------------------------------------------------

def frequency_selection() -> dict:
    p = paths.REFERENCE / "rv_frequency_selection.json"
    if not p.exists():
        return _unavailable("Sampling-frequency selection", "Not built.")
    d = json.loads(p.read_text(encoding="utf-8"))
    d["available"] = True
    return d


def cross_check() -> dict:
    f = foundation().get("c3_cross_check")
    if not f:
        return _unavailable("Amihud vs price impact", "Not built.")
    out = dict(f)
    out["available"] = True
    return out


def week8_dependency() -> dict:
    """Proof, at request time, that Week 8 consumes the Week 2 result."""
    try:
        detector = CE.CountEventDetector.from_week2()
    except CE.MissingWeek2Input as exc:
        return _unavailable("Week 8 dependency", str(exc))
    d = detector.to_dict()
    d["available"] = True
    d["summary"] = foundation().get("week8_integration", {})
    return d


def finance_inputs() -> dict:
    r = W2.report()
    r["available"] = True
    return r


def summary() -> dict:
    f = foundation()
    st = liquidity_state()
    return {
        "week2_version": WEEK2_VERSION,
        "available": bool(f),
        "intraday": f.get("intraday", {}),
        "realised_variance": f.get("c1_realised_variance", {}),
        "price_impact": f.get("c2_price_impact", {}),
        "cross_check": f.get("c3_cross_check", {}),
        "thresholds": f.get("c4_thresholds", {}),
        "arrival": f.get("c5_arrival", {}),
        "liquidity_state": f.get("c6_liquidity_state", {}),
        "week8_integration": f.get("week8_integration", {}),
        "finance_inputs": finance_inputs(),
        "stressed_now": (int(st["stress_gate_fired"].sum()) if st is not None else 0),
    }
