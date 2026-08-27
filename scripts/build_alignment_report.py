"""Compute and record the temporal alignment between this project's evidence sources.

    python scripts/build_alignment_report.py

Writes ``outputs/alignment/evidence_alignment.json`` and ``evidence_alignment.csv``, and
draws ``figures/figALN01_windows.png`` — every source's coverage on one timeline, so the
gaps are visible rather than described.

The report is regenerated, never edited. Its verdicts come from the sessions each source
holds at the moment it runs, so ingesting a source that closes a gap changes the answer
without anything here changing. That is the point: the current ``NOT_ALIGNED`` between the
index and the model evidence is a measurement, not a decision.
"""
from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import environment_snapshot, git_commit  # noqa: E402
from research.data.alignment import ALIGNMENT_VERSION  # noqa: E402
from scripts.stages import product_views as pv  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "alignment"
FIGS = OUT / "figures"

STATUS_COLOUR = {
    "ALIGNED": "#009e73",
    "PARTIAL": "#e69f00",
    "NOT_ALIGNED": "#d55e00",
    "UNKNOWN": "#6b7683",
}


def figure_windows(sources: list[dict]) -> dict:
    """Every source's coverage on one timeline.

    A gap between two bars is the whole finding, and a bar chart of date ranges shows it
    in a way no table does: the eye lands on the empty space between them before it reads
    a single number.
    """
    usable = [s for s in sources if s["start"] and s["end"]]
    usable.sort(key=lambda s: s["start"])

    fig, ax = plt.subplots(figsize=(8.2, 0.62 * len(usable) + 1.6))
    for i, s in enumerate(usable):
        start = pd.Timestamp(s["start"])
        end = pd.Timestamp(s["end"])
        ax.barh(i, (end - start).days, left=start, height=0.55,
                color="#0072b2", alpha=0.75)
        ax.text(end, i, "  %d sessions" % s["sessions"], va="center", fontsize=8,
                color="#4a545f")

    ax.set_yticks(range(len(usable)))
    ax.set_yticklabels(["%s\n%s" % (s["label"], s["kind"]) for s in usable], fontsize=8)
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.grid(alpha=0.25, lw=0.5, axis="x")
    ax.set_title("Coverage of each evidence source")
    fig.tight_layout()

    FIGS.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(FIGS / ("figALN01_windows.%s" % ext), dpi=200, bbox_inches="tight")
    plt.close(fig)
    progress.log("      figALN01_windows")
    return {
        "figure": "figALN01_windows",
        "caption": (
            "Coverage of every evidence source this project holds. Where two bars do not "
            "share a horizontal span, no result can be about both: the NIFTY 50 series "
            "and the model evaluation are the pair in that position, sharing zero "
            "sessions."),
        "source_data": "outputs/alignment/evidence_alignment.json",
    }


def main() -> int:
    t0 = time.time()
    progress.log("[evidence alignment]")
    OUT.mkdir(parents=True, exist_ok=True)

    matrix = pv.alignment_matrix()
    pairs = matrix["pairs"]

    rows = []
    for r in pairs:
        rows.append({
            "source_a": r["source_a"]["source_id"],
            "source_a_kind": r["source_a"]["kind"],
            "source_a_start": r["index_start"],
            "source_a_end": r["index_end"],
            "source_a_sessions": r["source_a"]["sessions"],
            "source_b": r["source_b"]["source_id"],
            "source_b_kind": r["source_b"]["kind"],
            "source_b_start": r["evidence_start"],
            "source_b_end": r["evidence_end"],
            "source_b_sessions": r["source_b"]["sessions"],
            "overlap_start": r["overlap_start"],
            "overlap_end": r["overlap_end"],
            "overlap_sessions": r["overlap_sessions"],
            "coverage_ratio": round(r["coverage_ratio"], 6),
            "alignment_status": r["alignment_status"],
        })
    pd.DataFrame(rows).to_csv(OUT / "evidence_alignment.csv", index=False)

    figure = figure_windows(matrix["sources"])

    jsonio.write(OUT / "evidence_alignment.json", {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "environment": environment_snapshot(),
        "alignment_version": ALIGNMENT_VERSION,
        "limitation": "L-25",
        "matrix": matrix,
        "figures": [figure],
        "policy": (
            "Alignment is computed from the sessions each source holds, on every run. No "
            "status is stored, no date is shifted, and no series is extended to close a "
            "gap. A pair reading NOT_ALIGNED becomes ALIGNED when a source covering the "
            "other's sessions is ingested, with nothing here edited."),
    })

    for r in pairs:
        progress.log("      %-14s x %-14s %-12s overlap %5d  ratio %.3f"
                     % (r["source_a"]["source_id"], r["source_b"]["source_id"],
                        r["alignment_status"], r["overlap_sessions"],
                        r["coverage_ratio"]))
    counts = matrix["counts"]
    progress.log("%d pairs: %d aligned, %d partial, %d not aligned"
                 % (counts["pairs"], counts["aligned"], counts["partial"],
                    counts["not_aligned"]))
    progress.log("elapsed %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
