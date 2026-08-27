"""Export the corpus, synthetic ablation, VLM and validation scorecard as an app bundle.

    python scripts/export_corpus_lab.py

Additive: writes ``public/data/corpus_lab.json``, a file that does not exist yet, and
never modifies one that does.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import git_commit  # noqa: E402

BUNDLE = paths.REPO_ROOT / "public" / "data" / "corpus_lab.json"
R = paths.REPO_ROOT


def _json(*parts):
    p = R.joinpath(*parts)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _csv(*parts) -> list[dict]:
    p = R.joinpath(*parts)
    if not p.exists():
        return []
    return json.loads(pd.read_csv(p).to_json(orient="records"))


def main() -> int:
    corpus = _json("outputs", "corpus", "corpus_report.json") or {}
    rvs = _json("outputs", "corpus", "real_vs_synthetic.json") or {}
    sweep = _json("outputs", "corpus", "synthetic_ratio_sweep.json") or {}
    validation = _json("outputs", "research_validation", "validation_summary.json") or {}
    vlm = _json("outputs", "vlm", "vlm_run.json") or {}
    vlm_abl = _json("outputs", "vlm", "vlm_ablation.json") or {}

    shards = []
    for a in (corpus.get("per_shard_analysis") or []):
        eff = a.get("effective_sample_size") or {}
        comp = a.get("composition") or {}
        shards.append({
            "shard": a.get("shard"), "rows": a.get("rows"),
            "units": eff.get("n_independent_units"),
            "design_effect": eff.get("design_effect"),
            "real": comp.get("real_samples"), "synthetic": comp.get("synthetic_samples"),
            "cross_split_clean": (a.get("cross_split") or {}).get("clean"),
            "duplicate_fraction": (a.get("exact_duplicates") or {}).get(
                "duplicate_fraction"),
        })

    meta = {
        "corpus": {
            "composition": corpus.get("composition"),
            "effective_sample_size": corpus.get("effective_sample_size"),
            "scale_target": corpus.get("scale_target"),
            "split_policy": corpus.get("split_policy"),
            "shards": shards,
        },
        "synthetic": {
            "summary": rvs.get("summary"),
            "verdict": rvs.get("verdict"),
            "fidelity": rvs.get("generator_fidelity"),
            "memorisation": rvs.get("generator_memorisation"),
            "runs": _csv("outputs", "corpus", "real_vs_synthetic.csv"),
            "ratio_sweep": sweep.get("rows") or [],
            "largest_harmless_share": sweep.get("largest_harmless_share"),
        },
        "vlm": {
            "executed": bool(vlm),
            "backends": vlm.get("backends"),
            "hardware_note": vlm.get("hardware_note"),
            "describe": vlm.get("describe"),
            "temporal": vlm.get("temporal"),
            "robustness": vlm.get("robustness"),
            "consistency": vlm.get("consistency"),
            "ablation": vlm_abl,
        },
        "validation": {
            "scorecard": validation.get("scorecard"),
            "summary": validation.get("summary"),
            "claim_gate": validation.get("claim_gate"),
        },
        "git_commit": git_commit(),
        "generated_at": datetime.now(UTC).isoformat(),
    }

    existing = sorted(p.name for p in BUNDLE.parent.glob("*.json"))
    jsonio.write(BUNDLE, {"generated_at": meta["generated_at"], "rows": [],
                          "meta": meta})
    progress.log("wrote %s (%.1f KB); %d existing bundles untouched"
                 % (BUNDLE.name, BUNDLE.stat().st_size / 1024,
                    len([e for e in existing if e != BUNDLE.name])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
