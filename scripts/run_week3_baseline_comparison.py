"""Run the Week 3 C3 experiment: TF-IDF baseline vs the trained learned representation.

    python scripts/run_week3_baseline_comparison.py

Writes:
    outputs/week3/c3_baseline_comparison.json   metrics, hashes, task definition, winner
    outputs/week3/c3_predictions.npz            the predictions every metric derives from

The split boundaries are the ones fixed by scripts/build_week3_text.py and are not
recomputed or altered here. Nothing in this script is conditioned on which system wins.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from research.text import baseline_comparison as BC  # noqa: E402


def main() -> int:
    t0 = time.time()
    print("Week 3 C3 -- frequency baseline vs learned representation")
    print("  task: %s" % BC.TASK["task_id"])
    artifact = BC.run(log=print)

    print()
    print("  evaluation: %d documents, %d classes, sessions %s .. %s"
          % (artifact["evaluation_sample"]["n"], len(artifact["classes"]),
             artifact["splits"]["evaluation_first"],
             artifact["splits"]["evaluation_last"]))
    print()
    print("  %-24s %8s %8s %8s %8s" % ("system", "acc", "macroF1", "wtdF1", "balAcc"))
    for name, s in artifact["systems"].items():
        m = s["metrics"]
        print("  %-24s %8.4f %8.4f %8.4f %8.4f"
              % (name, m["accuracy"], m["macro_f1"], m["weighted_f1"],
                 m["balanced_accuracy"]))
    print()
    print("  winner: %s  (macro F1 margin %.4f)"
          % (artifact["winner"], artifact["margin_macro_f1"]))
    print("  elapsed %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
