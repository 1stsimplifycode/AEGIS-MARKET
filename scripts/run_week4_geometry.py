"""Build the Week 4 convolution sizing analysis and freeze the geometry contract.

    python scripts/run_week4_geometry.py
    python scripts/run_week4_geometry.py --verify   # check live models against the freeze

Writes:
    research_artifacts/models/week4_geometry_contract.json
    outputs/week4/conv_sizing.json
    outputs/week4/CONV_SIZING.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from research.models import geometry as G  # noqa: E402

SIZING_JSON = REPO_ROOT / "outputs" / "week4" / "conv_sizing.json"
SIZING_MD = REPO_ROOT / "outputs" / "week4" / "CONV_SIZING.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()

    if args.verify:
        result = G.verify_contract()
        for kind, r in result["per_geometry"].items():
            print("  %-7s %s" % (kind, "MATCHES" if r["matches"] else "CHANGED"))
        print("  all_match: %s" % result["all_match"])
        return 0 if result["all_match"] else 1

    print("Week 4 convolution sizing (derived from instantiated models)")
    tables = G.all_sizing_tables()
    for kind, t in tables.items():
        print("  %-7s %-20s conv=%d params=%-9s MACs=%-14s FLOPs=%s"
              % (kind, t["model"], t["conv_layers"],
                 format(t["total_parameters"], ","), format(t["conv_macs"], ","),
                 format(t["conv_flops"], ",")))

    SIZING_JSON.parent.mkdir(parents=True, exist_ok=True)
    SIZING_JSON.write_text(json.dumps(tables, indent=2), encoding="utf-8")
    SIZING_MD.write_text(G.markdown_table(tables), encoding="utf-8")

    contract = G.build_contract()
    path = G.save_contract(contract)
    print("\n  contract fingerprint: %s" % contract["contract_fingerprint"])
    for week, kinds in contract["downstream_consumers"].items():
        checks = [G.assert_geometry(k, week)["ok"] for k in kinds]
        print("  %-7s tied to %s -> %s" % (week, kinds, all(checks)))
    print("  written: %s" % path.relative_to(REPO_ROOT).as_posix())
    print("           %s" % SIZING_JSON.relative_to(REPO_ROOT).as_posix())
    print("           %s" % SIZING_MD.relative_to(REPO_ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
