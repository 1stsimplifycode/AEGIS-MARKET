"""Export the executed STATS-15 and STATS-16 results as an app bundle.

    python scripts/export_robustness_lab.py

Additive: writes ``public/data/robustness_lab.json``, a file that does not exist yet, and
never modifies one that does. The main exporter is a protected module because it rewrites
every existing bundle with a fresh timestamp; creating a new file carries none of that
risk.
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

RB = paths.REPO_ROOT / "outputs" / "stats" / "15_robustness_generalization"
MS = paths.REPO_ROOT / "outputs" / "stats" / "16_multiseed_significance"
BUNDLE = paths.REPO_ROOT / "public" / "data" / "robustness_lab.json"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    frame = pd.read_csv(path)
    return json.loads(frame.to_json(orient="records"))


def main() -> int:
    robustness = _json(RB / "run.json")
    significance = _json(MS / "significance.json")

    meta = {
        "robustness": {
            "run": robustness or {},
            "rows": _csv(RB / "robustness.csv"),
            "generalization": _csv(RB / "generalization.csv"),
            "executed": robustness is not None,
        },
        "multiseed": {
            "run": significance or {},
            "summary": _csv(MS / "seed_summary.csv"),
            "paired_tests": _csv(MS / "paired_tests.csv"),
            "within_run": _csv(MS / "within_run_intervals.csv"),
            "executed": significance is not None,
        },
        "holdout_policy": (
            "Neither module reads the frozen holdout. assert_no_holdout() raises on any "
            "frame carrying holdout rows, and every fit in STATS-15 passes through it; "
            "STATS-16 evaluates on validation because repeating a measurement on the "
            "holdout across ten seeds would be ten looks at the data the freeze exists "
            "to protect."),
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
