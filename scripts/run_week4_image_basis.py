"""Compute the Week 4 image basis by direct SVD of the prepared image matrix.

    python scripts/run_week4_image_basis.py

Reads the equalised image source through the Week 4 preparation manifest (so the basis is
tied by checksum to a registered prepared array), decomposes X directly, and writes the
basis plus its report. No covariance or Gram product is formed.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from research.image import basis as B  # noqa: E402
from research.preparation import orchestrator as O  # noqa: E402

SOURCE_ID = "image_chart_windows"


def main() -> int:
    t0 = time.time()
    print("Week 4 image basis -- direct SVD")
    manifest = O.load_manifest()
    entry = next(e for e in manifest["sources"] if e["source_id"] == SOURCE_ID)
    x, _ = O.load_prepared(SOURCE_ID, "train", manifest)
    print("  source %s  train %s  (registered, checksum verified)"
          % (SOURCE_ID, tuple(x.shape)))

    result = B.compute(x, source_id=SOURCE_ID,
                       source_sha256=entry["outputs"]["train"]["x_sha256"], log=print)
    factors = {"mean": result["_arrays"]["mean"],
               "components": result["_arrays"]["components"],
               "singular_values": result["_arrays"]["singular_values"]}
    # Verify against the SAME rows the decomposition saw, not the full array.
    check = B.verify_not_covariance_derived(x, factors, report_hint=result)
    result["covariance_check"] = check
    result["covariance_route_for_contrast"] = B.covariance_route_for_contrast(x[:2000])

    basis_path, report_path = B.save(result)

    r = result["retention"]
    print("\n  threshold %.2f (declared before the curve)" % r["threshold"])
    print("  retained %d of %d directions (%.1f%%)"
          % (r["retained_directions"], r["available_directions"],
             100 * r["fraction_of_directions_retained"]))
    print("  cumulative energy at k: %.6f" % r["cumulative_energy_at_k"])
    rec = result["reconstruction"]
    print("  reconstruction explained %.6f  relative residual %.6f"
          % (rec["explained"], rec["relative_residual"]))
    print("  energy identity matches cumulative: %s" % rec["matches_cumulative_energy"])
    print("  not covariance-derived: %s" % check["passes"])
    print("  contrast (covariance route) energy identity holds: %s"
          % result["covariance_route_for_contrast"]["energy_identity_holds"])
    print("\n  written: %s" % basis_path.relative_to(REPO_ROOT).as_posix())
    print("           %s" % report_path.relative_to(REPO_ROOT).as_posix())
    print("  elapsed %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
