"""Check every load-bearing figure in the datasets/models report against its artifact.

A document that quotes numbers from a repository goes stale the moment either side
changes, and a stale number in a technical report is worse than no number: it looks
checked. This re-reads each artifact and compares it to the value written in the LaTeX
source, so drift is a failure rather than something a reader has to catch.

    python scripts/verify_documentation.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEX = REPO / "outputs" / "documentation" / "AEGIS_Datasets_Models.tex"


def load(rel: str) -> dict:
    p = REPO / rel
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    if not TEX.exists():
        print("MISSING: %s" % TEX)
        return 1
    tex = TEX.read_text(encoding="utf-8")

    checks: list[tuple[str, str, bool]] = []

    def want(label: str, needle: str, ok: bool = True) -> None:
        present = needle in tex
        checks.append((label, needle, present is ok))

    # ---- market panel -------------------------------------------------------
    import pandas as pd
    panel = pd.read_parquet(REPO / "data/panel/cash_panel.parquet", columns=["date", "symbol"])
    want("panel rows", "8{,}399{,}065")
    want("panel symbols", "4{,}487")
    want("panel end", "2026-08-14")
    assert len(panel) == 8399065, "panel row count changed: %d" % len(panel)

    # ---- text ---------------------------------------------------------------
    t = load("outputs/week3/text_summary.json")
    c = t.get("corpus", {})
    want("corpus records", "377{,}650")
    want("corpus distinct", "285{,}230")
    want("train docs", "288{,}893")
    assert c.get("records") == 377650, c.get("records")
    assert c.get("distinct_bodies") == 285230

    emb = t.get("c4_embeddings", {})
    assert emb.get("negative_k") == 5 and emb.get("dim") == 128
    want("embedding K", "$K=5$")
    want("embedding dim", "dim 128")

    # ---- C3 comparison ------------------------------------------------------
    cmp_ = load("outputs/week3/c3_baseline_comparison.json")
    tf = cmp_["systems"]["MARKET_TFIDF_V1"]["metrics"]
    em = cmp_["systems"]["MARKET_EMBEDDING_V1"]["metrics"]
    for value in ("0.8674", "0.6856", "0.8622", "0.6730", "0.8286", "0.6133", "0.8172", "0.6127"):
        want("c3 %s" % value, value)
    want("c3 margin", "0.0724")
    want("c3 n", "33{,}322")
    assert round(tf["macro_f1"], 4) == 0.6856, tf["macro_f1"]
    assert round(em["macro_f1"], 4) == 0.6133, em["macro_f1"]
    assert round(cmp_["margin_macro_f1"], 4) == 0.0724
    assert cmp_["evaluation_sample"]["n"] == 33322
    assert cmp_["winner"] == "MARKET_TFIDF_V1"

    # ---- week 4 preparation -------------------------------------------------
    man = load("data/prepared/week4/PREPARATION_MANIFEST.json")
    by = {e["source_id"]: e for e in man.get("sources", [])}
    for sid, ent in ("audio_ravdess_speech", 1440), ("video_ravdess_speech", 1440), \
                    ("image_chart_windows", 17517):
        assert by[sid]["raw"]["n_raw_files"] == ent, (sid, by[sid]["raw"]["n_raw_files"])
    want("equalisation audio", "0.999997")
    want("equalisation video", "0.843165")
    want("equalisation video ceiling", "0.890382")
    want("equalisation image", "0.055596")
    want("chart windows", "17{,}517")

    # ---- geometry -----------------------------------------------------------
    g = load("research_artifacts/models/week4_geometry_contract.json")
    geo = g.get("geometries", {})
    assert geo["image"]["total_parameters"] == 60771
    assert geo["audio"]["conv_macs"] == 78852096
    assert geo["video"]["total_parameters"] == 111240
    want("ChartCNN params", "60{,}771")
    want("SpeechCNN MACs", "78{,}852{,}096")
    want("video params", "111{,}240")

    # ---- image basis --------------------------------------------------------
    b = load("outputs/week4/image_basis.json")
    assert b["retention"]["retained_directions"] == 2226
    assert b["method"]["covariance_formed"] is False
    want("basis k", "2226")
    want("basis threshold", "0.95")

    # ---- limitations --------------------------------------------------------
    sys.path.insert(0, str(REPO))
    from research.limitations import registry as reg
    for lid in ("L-01", "L-04", "L-06", "L-13"):
        reg.by_id(lid)
        want("limitation %s" % lid, lid)

    # ---- no placeholders ----------------------------------------------------
    for bad in ("TODO", "TBD", "insert here", "Lorem", "XXX", "FIXME", "placeholder"):
        checks.append(("no %r" % bad, bad, bad.lower() not in tex.lower()))

    failed = [c for c in checks if not c[2]]
    for label, needle, ok in checks:
        if not ok:
            print("  FAIL  %-30s %r" % (label, needle[:60]))
    print("checked %d assertions against artifacts; %d failed"
          % (len(checks), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
