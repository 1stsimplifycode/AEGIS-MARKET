"""Source-by-source equalisation report, computed from the prepared arrays.

    python scripts/run_week4_equalisation_report.py

Reads each registered Week 4 prepared array through load_prepared (so every figure is
tied to a checksum in the preparation manifest), measures the output distribution, and
compares it against BOTH the continuous target and the entropy a monotone map can
actually attain on that source.

Why the second comparison exists: the chart-window source is binary by construction, and
judging it only against flatness would report a property of the data as a failure of the
method. The attainable ceiling makes the distinction measurable.

Writes:
    outputs/week4/equalisation_report.json
    outputs/week4/EQUALISATION.md
"""
from __future__ import annotations

import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from research.preparation import equalisation as EQ  # noqa: E402
from research.preparation import orchestrator as O  # noqa: E402

JSON_PATH = REPO_ROOT / "outputs" / "week4" / "equalisation_report.json"
MD_PATH = REPO_ROOT / "outputs" / "week4" / "EQUALISATION.md"


def main() -> int:
    man = O.load_manifest()
    rows = []
    print("Week 4 equalisation report")
    for e in man["sources"]:
        sid = e["source_id"]
        x, _ = O.load_prepared(sid, "train", man)
        # A monotone map is a bijection on distinct values, so the equalised output's
        # atom masses ARE the source's atom masses. The ceiling is computable here.
        _, counts = np.unique(x, return_counts=True)
        masses = counts / float(counts.sum())
        measured = EQ.flatness(x)
        ceiling = EQ.entropy_ceiling(masses)
        achieved = measured["normalised_entropy"]
        stored = e["equalisation"]

        row = {
            "source_id": sid,
            "modality": e["modality"],
            "designation": e["designation"],
            "prepared_array": e["outputs"]["train"]["path"],
            "prepared_array_sha256": e["outputs"]["train"]["file_sha256"],
            "target": EQ.TARGET,
            "method": EQ.METHOD,
            "source_dtype": stored["source_dtype"],
            "n_distinct_source_values": int(len(masses)),
            "largest_atom_mass": float(masses.max()),
            "distribution_before": stored["distribution_before"],
            "distribution_after_recomputed": measured,
            "distribution_after_as_stored": stored["distribution_after"],
            "recomputation_agrees_with_manifest": bool(
                abs(achieved - stored["distribution_after"]["normalised_entropy"]) < 1e-9),
            "shortfall_vs_continuous_target": {
                "ks_deviation": measured["ks_deviation"],
                "total_variation": measured["total_variation"],
                "chi_square_per_bin": measured["chi_square_per_bin"],
                "entropy_gap_from_flat": 1.0 - achieved,
            },
            "attainable_ceiling": {
                "max_attainable_normalised_entropy": ceiling,
                "achieved_normalised_entropy": achieved,
                "achieved_fraction_of_attainable": achieved / ceiling if ceiling else None,
                "bound_1_atom_entropy": "H(atom masses) / log K",
                "bound_2_largest_atom": (
                    "one atom of mass p_max lands wholly in one bin, so some bin holds "
                    ">= p_max; the ceiling takes the tighter of the two bounds"),
                "is_degenerate": bool(len(masses) < EQ.N_BINS),
            },
            "improvement": {
                "ks": stored["distribution_before"]["ks_deviation"] - measured["ks_deviation"],
                "total_variation": (stored["distribution_before"]["total_variation"]
                                    - measured["total_variation"]),
                "normalised_entropy": (achieved
                                       - stored["distribution_before"]["normalised_entropy"]),
            },
        }
        rows.append(row)
        print("  %-26s distinct=%-9d after=%.6f ceiling=%.6f frac=%.4f"
              % (sid, len(masses), achieved, ceiling,
                 achieved / ceiling if ceiling else float("nan")))

    report = {
        "equalisation_report_version": "week4-equalisation-report-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "generated_by": "scripts/run_week4_equalisation_report.py",
        "measured_from": "the prepared arrays themselves, via "
                         "orchestrator.load_prepared (checksum-verified)",
        "target": EQ.TARGET,
        "method": EQ.METHOD,
        "n_bins": EQ.N_BINS,
        "sources": rows,
        "how_to_read_this": (
            "Two comparisons are reported per source. The first is distance from the "
            "continuous Uniform(0,1) target. The second is distance from what a monotone "
            "map can attain given the source's own atom masses. A binary source scores "
            "badly on the first and perfectly on the second, and both facts are true."),
        "software": {"python": platform.python_version(), "numpy": np.__version__},
    }
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")

    md = ["# Week 4 source equalisation", "",
          "Target: **%s**, %d bins. Method: **%s**, %s."
          % (EQ.TARGET["distribution"], EQ.N_BINS, EQ.METHOD["name"],
             EQ.METHOD["fitted_on"]), "",
          "| source | dtype | distinct | KS before | KS after | entropy before | "
          "entropy after | attainable | % of attainable |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        b = r["distribution_before"]
        a = r["distribution_after_recomputed"]
        c = r["attainable_ceiling"]
        md.append("| `%s` | %s | %d | %.6f | %.6f | %.6f | %.6f | %.6f | %.2f%% |"
                  % (r["source_id"], r["source_dtype"], r["n_distinct_source_values"],
                     b["ks_deviation"], a["ks_deviation"], b["normalised_entropy"],
                     a["normalised_entropy"], c["max_attainable_normalised_entropy"],
                     100 * c["achieved_fraction_of_attainable"]))
    md += ["", "## Reading the residual", "", report["how_to_read_this"], ""]
    for r in rows:
        c = r["attainable_ceiling"]
        md.append("- **%s**: %d distinct values, largest atom mass %.4f. %s"
                  % (r["source_id"], r["n_distinct_source_values"],
                     r["largest_atom_mass"],
                     "Degenerate for equalisation: fewer distinct values than bins."
                     if c["is_degenerate"] else
                     "Enough distinct values to bin, but uneven atom masses cap the "
                     "attainable flatness below 1."))
    MD_PATH.write_text("\n".join(md), encoding="utf-8")

    print("\n  written: %s" % JSON_PATH.relative_to(REPO_ROOT).as_posix())
    print("           %s" % MD_PATH.relative_to(REPO_ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
