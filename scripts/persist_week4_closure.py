"""Write outputs/week4/CLOSURE.json from actual runs and artifacts.

    python scripts/persist_week4_closure.py --full-suite-passed 3300

Records a BLOCKED verdict as faithfully as Week 3 recorded a PASS. Suite counts are parsed
from pytest runs this script performs; a full-suite figure measured elsewhere may be
supplied and is recorded with that provenance.
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from research.week4 import closure as C  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full-suite-passed", type=int, default=None)
    ap.add_argument("--full-suite-skipped", type=int, default=0)
    ap.add_argument("--full-suite-failed", type=int, default=0)
    ap.add_argument("--full-suite-seconds", type=float, default=None)
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
            "seconds": args.full_suite_seconds,
            "exit_code": 0 if args.full_suite_failed == 0 else 1,
            "ran_at": args.full_suite_ran_at or datetime.now(UTC).isoformat(),
            "measured_by": "supplied from a separate full-suite run; not executed "
                           "inside this script",
        }

    print("Persisting Week 4 closure")
    if not args.skip_tests:
        print("  running tests/week4, week1+week2, week3 ...")
    record = C.build(full_suite=full, run_tests=not args.skip_tests)
    path = C.save(record)

    a = record["auditor"]
    print("\n  verdict : %s   blocking: %s" % (a["verdict"], a["blocking"]))
    for c in C.CRITERIA:
        print("    %-4s %s" % (c, a["criteria"][c]))
    print("\n  closed  : %s" % record["closed"])
    for s in record["verification"]:
        print("  %-40s passed=%-6s skipped=%-4s failed=%s"
              % (s["label"], s["passed"], s["skipped"], s["failed"]))

    result = C.verify(record)
    print("\n  consistency checks:")
    for k, v in result["checks"].items():
        print("    %-44s %s" % (k, v))
    print("\n  OK: %s" % result["ok"])
    print("  written: %s" % path.relative_to(REPO_ROOT).as_posix())
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
