"""The single Week 4 upstream preparation entry point.

    python scripts/run_week4_preparation.py
    python scripts/run_week4_preparation.py --only image_chart_windows

Takes every registered source from raw media to a prepared, equalised tensor set and
writes data/prepared/week4/PREPARATION_MANIFEST.json. Historical V1/V2/V3 datasets under
data/models/ are not touched.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from research.preparation import orchestrator as O  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--video-limit-per-actor", type=int, default=None,
                    help="cap clips per actor (recorded in the manifest when used)")
    args = ap.parse_args()

    t0 = time.time()
    print("Week 4 -- single upstream preparation pass (seed %d)" % O.SEED)
    kw = {}
    if args.video_limit_per_actor is not None:
        kw["limit_per_actor"] = args.video_limit_per_actor
    manifest = O.run(log=print, only=args.only, **kw)

    print()
    print("  %-26s %-10s %-22s %s"
          % ("source", "modality", "train shape", "eq KS residual"))
    for e in manifest["sources"]:
        eq = e.get("equalisation", {})
        ks = eq.get("shortfall", {}).get("residual_ks_deviation")
        print("  %-26s %-10s %-22s %s"
              % (e["source_id"], e["modality"],
                 tuple(e["outputs"]["train"]["shape"]),
                 ("%.6f" % ks) if ks is not None else "n/a"))

    v = O.verify(manifest)
    print("\n  checksum verification: all_match=%s (%d arrays)"
          % (v["all_match"], len(v["checked"])))
    print("  parameter fingerprint: %s" % O.parameter_fingerprint(manifest))
    print("  elapsed %.1fs" % (time.time() - t0))
    return 0 if v["all_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
