"""Build the Week 4 finance inputs: capture conditions, results calendar, clip rule,
retention/takedown, and the audio-visual source record.

    python scripts/run_week4_finance_inputs.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from research.media import av_sources as AV  # noqa: E402
from research.media import capture_conditions as CC  # noqa: E402
from research.media import clip_selection as CS  # noqa: E402
from research.media import retention as RET  # noqa: E402
from research.reference import results_calendar as RC  # noqa: E402


def main() -> int:
    t0 = time.time()
    print("Week 4 finance inputs")

    print("\n[C5.A] audio-visual source record ...")
    av = AV.build(log=print)
    print("  ingested sources: %d   referenced-only: %d"
          % (av["counts"]["ingested"], av["counts"]["referenced_only"]))
    print("  finance AV obtained: %s" % av["finance_av_status"]["obtained"])

    print("\n[C5.B] capture conditions ...")
    cc = CC.build(log=print)
    for s in cc["sources"]:
        p = s["probed"]
        bits = []
        for k in ("width_values", "frame_rate_values", "sample_rate_values",
                  "channel_values", "resolution"):
            if k in p:
                bits.append("%s=%s" % (k.replace("_values", ""), p[k]))
        print("  %-24s %s" % (s["source_id"], "; ".join(bits) or "rendered"))

    print("\n[C5.C] results calendar ...")
    _, rc = RC.build(log=print)
    print("  rows %d, issuers %d, sessions %d, %s .. %s"
          % (rc["rows"], rc["issuers"], rc["sessions"],
             rc["first_session"], rc["last_session"]))
    print("  publication-timestamp coverage %.4f" % rc["publication_timestamp_coverage"])

    print("\n[C5.D] clip-selection rule ...")
    cs = CS.build(log=print)
    print("  selected %d of %d candidates across %d issuers"
          % (cs["n_selected"], cs["candidates"], cs["issuers_selected"]))
    print("  rejections: %s" % cs["rejected_counts"])
    print("  clips actually acquired: %d (%s)"
          % (cs["media_availability"]["clips_actually_acquired"],
             cs["media_availability"]["blocked_by"]))

    print("\n[C5.E] retention and takedown ...")
    ret = RET.build(log=print)
    print("  sources with established terms: %d; without: %d"
          % (ret["sources_with_established_terms"],
             ret["sources_without_established_terms"]))
    print("  takedown mechanism implemented: %s"
          % ret["takedown_mechanism"]["implemented"])

    print("\n  elapsed %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
