"""Write outputs/week3/CLOSURE.json from actual runs and artifacts.

    python scripts/persist_week3_closure.py
    python scripts/persist_week3_closure.py --full-suite-passed 3160

The test suites are executed by this script; their counts are parsed from the actual
pytest output. The full suite takes ~16 minutes, so it may be supplied from a run made
elsewhere -- in which case it is recorded with that provenance rather than as a fresh
measurement.
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from research.week3 import closure as C  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full-suite-passed", type=int, default=None)
    ap.add_argument("--full-suite-skipped", type=int, default=0)
    ap.add_argument("--full-suite-failed", type=int, default=0)
    ap.add_argument("--full-suite-ran-at", default=None)
    ap.add_argument("--skip-tests", action="store_true")
    args = ap.parse_args()

    full = None
    if args.full_suite_passed is not None:
        full = {
            "label": "full pytest suite",
            "command": "-m pytest tests/ -q",
            "passed": args.full_suite_passed,
            "skipped": args.full_suite_skipped,
            "failed": args.full_suite_failed,
            "exit_code": 0 if args.full_suite_failed == 0 else 1,
            "ran_at": args.full_suite_ran_at or datetime.now(UTC).isoformat(),
            "measured_by": "supplied to scripts/persist_week3_closure.py from a "
                           "separate full-suite run; not executed inside this script",
        }

    print("Persisting Week 3 closure")
    if not args.skip_tests:
        print("  running tests/week3 ...")
        print("  running tests/week1 + tests/week2 ...")
    record = C.build(full_suite=full, run_tests=not args.skip_tests)
    path = C.save(record)

    for s in record["verification"]:
        print("  %-38s passed=%s skipped=%s failed=%s exit=%s"
              % (s["label"], s["passed"], s["skipped"], s["failed"], s["exit_code"]))
    rep = record["c3_reproduction"]
    print("  C3 winner (recomputed): %s  margin=%.4f  agrees_with_artifact=%s"
          % (rep["winner"], rep["margin_macro_f1"],
             rep["recomputed_agrees_with_artifact"]))

    result = C.verify(record)
    print("\n  consistency checks:")
    for k, v in result["checks"].items():
        print("    %-42s %s" % (k, v))
    print("\n  OK: %s" % result["ok"])
    print("  written: %s" % path.relative_to(REPO_ROOT).as_posix())
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
