"""Export the product read models to `public/data/market.json`.

The product experience needs prices, and prices live in an 8.4-million-row parquet the
deployed application cannot open. This writes the snapshot the pages fall back to when no
analysis backend is reachable — the same read models `backend/product.py` serves, frozen
at the moment of export and stamped with the session they describe.

It is a snapshot, not a substitute. The pages that use it say which session it covers, so
"the market" on a static deployment is always a dated observation rather than an implied
"now". When a backend *is* reachable the pages prefer it, and the two agree because they
are the same functions.

    python scripts/export_product.py
"""
from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import git_commit  # noqa: E402
from scripts.stages import product_views as pv  # noqa: E402

OUT = paths.REPO_ROOT / "public" / "data"

#: Sessions of price history kept per instrument. Enough for a shape, small enough that
#: the bundle stays in the low megabytes: a static deployment downloads all of it.
SNAPSHOT_WINDOW = 90

#: Instruments the snapshot covers beyond the scored sample, by traded value. Someone
#: searching for an instrument outside the evaluation sample should still see its price.
EXTRA_INSTRUMENTS = 120


def main() -> int:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    progress.log("[product export]")

    overview = pv.market_overview()
    attention = pv.attention(limit=pv.SEARCH_LIMIT)
    directory = pv.search("", limit=pv.SEARCH_LIMIT)
    indices = pv.indices()
    index_ids = [r["instrument_id"] for r in indices.get("rows", [])]
    index_detail = {i: pv.index_detail(i, window=500) for i in index_ids}
    index_series = {i: pv.index_series(i) for i in index_ids}
    index_context = {i: pv.index_context(i) for i in index_ids}
    alignment = pv.alignment_matrix()
    evidence = {i: pv.evidence_summary(i) for i in index_ids}
    progress.log("      alignment: %d pairs, %d not aligned"
                 % (alignment["counts"]["pairs"], alignment["counts"]["not_aligned"]))
    progress.log("      %d indices, primary %s"
                 % (len(index_detail), indices.get("primary")))

    scored = pv.scored()
    symbols: list[str] = []
    if not scored.empty:
        symbols = sorted(scored["symbol"].astype(str).str.upper().unique())
    for row in pv.search("", limit=EXTRA_INSTRUMENTS)["results"]:
        if row["symbol"] not in symbols:
            symbols.append(row["symbol"])

    instruments: dict[str, dict] = {}
    for symbol in symbols:
        payload = pv.instrument(symbol, window=SNAPSHOT_WINDOW)
        if payload.get("found"):
            instruments[symbol] = payload
    progress.log("      %d instruments snapshotted over %d sessions"
                 % (len(instruments), SNAPSHOT_WINDOW))

    jsonio.write_public(OUT / "market.json", {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "meta": {
            "last_session": overview["market"]["last_session"],
            "n_instruments": len(instruments),
            "snapshot_window": SNAPSHOT_WINDOW,
            "overview": overview,
            "attention": attention,
            "directory": directory,
            "indices": indices,
            "index_detail": index_detail,
            "index_series": index_series,
            "index_context": index_context,
            "alignment": alignment,
            "evidence": evidence,
            "note": ("A snapshot of the read models the analysis backend serves, frozen "
                     "at export. Pages prefer the backend when one is reachable and say "
                     "which of the two they used."),
        },
        "rows": [instruments[s] for s in sorted(instruments)],
    }, log=progress.log)

    progress.log("wrote market.json for session %s" % overview["market"]["last_session"])
    progress.log("elapsed %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
