"""Run the Trustworthy AI evaluation and the affective-computing audit.

    python scripts/run_trust.py

Writes to ``outputs/trust/`` only. It reads existing research artifacts and never
regenerates one, so it is safe to run at any time and needs no --force.

Deliberately not a seventeenth STATS module: the approved 16 + 16 mapping is unchanged.
This is an evaluation layer over what the modules already produced, invoked directly and
by ``run_all_research.bat``.
"""
from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from research.affective import audit as aff  # noqa: E402
from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import environment_snapshot, git_commit  # noqa: E402
from research.trust import privacy as pv  # noqa: E402
from research.trust import scorecard as sc  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "trust"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    progress.log("[1/3] privacy audit")
    audit = pv.audit()
    jsonio.write(OUT / "privacy_audit.json",
                 {**audit.to_dict(), "data_inventory": pv.data_inventory()})
    progress.log("      %d files scanned, %d findings, status %s"
                 % (audit.files_scanned, len(audit.findings), audit.status))
    for k, v in audit.checks.items():
        progress.log("      %-34s %s" % (k, v))

    progress.log("[2/3] trustworthy AI scorecard")
    card = sc.build()
    jsonio.write(OUT / "scorecard.json", card)
    for name, c in card["principles"].items():
        progress.log("      %-16s %-22s %d evidence item(s), %d limitation(s)"
                     % (name, c["status"], len(c["evidence"]), len(c["limitations"])))
    progress.log("      status counts: %s" % card["status_counts"])
    progress.log("      composite score: %s (deliberately absent)"
                 % card["composite_score"])

    progress.log("[3/3] affective computing audit")
    # The separation audit is the evidence that Stream A cannot leak into Stream B.
    from scripts.stages.human_affect import stream_separation_audit
    sep_result = stream_separation_audit()
    sep = {"status": sep_result.status, "message": sep_result.message,
           "detail": sep_result.detail}
    progress.log("      stream separation: %s" % sep_result.message)
    checklist = aff.checklist()
    payload = {**checklist.to_dict(),
               "research_questions": aff.research_questions(),
               "capabilities": [c.to_dict() for c in aff.capabilities()],
               "stream_separation": sep}
    jsonio.write(OUT / "affective_audit.json", payload)
    for status, n in sorted(checklist.by_status().items()):
        progress.log("      %-16s %d" % (status, n))
    progress.log("      capabilities (capability/implementation/dataset/validation):")
    for c in aff.capabilities():
        progress.log("        %-34s %-10s %-14s %-9s %s"
                     % (c.name, c.capability, c.implementation, c.dataset,
                        c.validation))
    progress.log("      verdict: %s" % checklist.verdict)

    # Additive export: writes a bundle that does not exist yet and never touches one that
    # does. The main exporter is a protected module because it rewrites every existing
    # bundle with a fresh timestamp; creating a new file carries none of that risk.
    bundle = paths.REPO_ROOT / "public" / "data" / "trust.json"
    existing = sorted(p.name for p in bundle.parent.glob("*.json"))
    jsonio.write(bundle, {
        "generated_at": datetime.now(UTC).isoformat(),
        "rows": [],
        "meta": {
            "scorecard": card,
            "privacy": {**audit.to_dict(), "data_inventory": pv.data_inventory()},
            "affective": payload,
        },
    })
    progress.log("      wrote public/data/trust.json (new bundle; %d existing bundles "
                 "untouched)" % len(existing))

    jsonio.write(OUT / "run.json", {
        "run_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "environment": environment_snapshot(),
        "elapsed_s": round(time.time() - t0, 2),
        "outputs": ["privacy_audit.json", "scorecard.json", "affective_audit.json"],
        "note": "Reads existing artifacts; regenerates nothing.",
    })
    progress.log("done in %.1fs -> %s" % (time.time() - t0, OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
