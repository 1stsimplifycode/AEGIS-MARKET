"""Add bitemporal stamps to the existing text corpus without regenerating it.

    python scripts/stamp_text_corpus.py

``data/panel/text_corpus.parquet`` is a protected artifact: regenerating it would draw
new documents from the RNG and change every downstream text feature. The timestamps are a
pure function of ``date``, so they can be added to the file as it stands. This script
proves that is what happened -- it hashes the text, doc_kind and credibility columns
before and after and refuses to write if either moved.

Idempotent: running it on an already-stamped corpus is a no-op.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.core import paths  # noqa: E402
from research.detection.episodes import stamp_bitemporal  # noqa: E402

PRESERVED = ("symbol", "date", "text", "doc_kind", "source_credibility")
STAMPS = ("publication_time", "knowledge_time", "event_time")


def _fingerprint(frame: pd.DataFrame) -> str:
    h = hashlib.sha256()
    for col in PRESERVED:
        h.update(col.encode())
        h.update(pd.util.hash_pandas_object(frame[col], index=False).values.tobytes())
    return h.hexdigest()


def main() -> int:
    path = paths.PANEL / "text_corpus.parquet"
    if not path.exists():
        print("no corpus at %s" % path)
        return 1
    corpus = pd.read_parquet(path)
    before = _fingerprint(corpus)
    print("corpus: %d rows, columns %s" % (len(corpus), list(corpus.columns)))

    if all(c in corpus.columns for c in STAMPS):
        print("already stamped; nothing to do")
        return 0

    stamped = stamp_bitemporal(corpus)
    after = _fingerprint(stamped)
    if before != after:
        print("REFUSING TO WRITE: the preserved columns changed (%s -> %s)"
              % (before[:16], after[:16]))
        return 2
    if len(stamped) != len(corpus):
        print("REFUSING TO WRITE: row count changed")
        return 2

    stamped.to_parquet(path, index=False)
    print("content fingerprint unchanged: %s" % before[:32])
    print("added %s" % ", ".join(STAMPS))
    print("written: %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
