"""Export the executed Stream B experiments as an app bundle.

    python scripts/export_affective_lab.py

Additive: writes ``public/data/affective_lab.json``, a file that does not exist yet, and
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

from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import git_commit  # noqa: E402

EXP = paths.REPO_ROOT / "outputs" / "human_affect" / "experiments"
FIGS = paths.REPO_ROOT / "outputs" / "human_affect" / "figures"
DATA_ROOT = paths.DATA / "affective"
BUNDLE = paths.REPO_ROOT / "public" / "data" / "affective_lab.json"


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def dataset_rows() -> list[dict]:
    """What was actually acquired, read from the download manifests."""
    rows = []
    for manifest_path in sorted(DATA_ROOT.glob("*.manifest.json")):
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        rows.append({
            "dataset_id": m.get("dataset_id"),
            "title": m.get("title"),
            "modality": ("audiovisual" if "VIDEO" in (m.get("dataset_id") or "")
                         else "text" if "GOEMOTION" in (m.get("dataset_id") or "")
                         else "audio"),
            "licence": m.get("licence_id"),
            "licence_verified": m.get("licence_verified"),
            "licence_source": m.get("licence_source"),
            "n_items": m.get("n_media_files") or len(m.get("files") or []),
            "retrieved_at": m.get("retrieved_at"),
            "redistributed": m.get("redistributed", False),
            "role": m.get("note"),
        })
    return rows


def main() -> int:
    speech = _read(EXP / "speech_emotion.json")
    text = _read(EXP / "text_affect.json")
    face = _read(EXP / "face_emotion.json")
    fusion = _read(EXP / "fusion.json")
    robustness = _read(EXP / "robustness.json")
    fairness = _read(EXP / "fairness.json")
    figures = _read(FIGS / "figures.json")
    run = _read(EXP / "run.json")

    meta = {
        "datasets": dataset_rows(),
        "speech": speech or {},
        "text": text or {},
        "face": face or {},
        "fusion": fusion or {},
        "robustness": robustness or {},
        "fairness": fairness or {},
        "figures": (figures or {}).get("figures", []),
        "figures_not_generated": (figures or {}).get("not_generated", []),
        "run": {k: v for k, v in (run or {}).items()
                if k in {"run_at", "git_commit", "elapsed_s", "seed", "split_summary",
                         "n_clips"}},
        "git_commit": git_commit(),
        "generated_at": datetime.now(UTC).isoformat(),
        "stream": "STREAM_B_HUMAN_MEDIA",
        "separation_note": (
            "These experiments use real human media only. The market-derived Stream A "
            "pipeline is untouched, and the gates that keep the two apart are executed "
            "by HUMAN_AFFECT-02."),
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
