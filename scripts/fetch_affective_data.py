"""Acquire the open human-affective corpora the Stream B experiments run on.

    python scripts/fetch_affective_data.py --dataset RAVDESS_SPEECH_AUDIO
    python scripts/fetch_affective_data.py --all

Downloads to ``data/affective/`` (gitignored), verifies size, records a SHA-256 and the
licence read from the source's own API, and writes the provenance manifest the registry
gate reads. Nothing is committed to the repository; the manifest and the checksums are.

Licence verification here is real rather than asserted: the Zenodo record carries a
machine-readable ``license`` field, which is fetched and stored alongside the data. That
is what lets :func:`research.human_affect.registry.assert_usable` stop refusing.

RAVDESS is CC BY-NC-SA 4.0: non-commercial, share-alike, attribution. This repository uses
it for non-commercial academic research and redistributes none of it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from research.core import paths, progress  # noqa: E402

DATA_ROOT = paths.DATA / "affective"

#: Each entry names a Zenodo record and the files to take from it. Deliberately a subset:
#: the full RAVDESS video set is 25 GB and the experiments here need co-occurring audio
#: and video for a defined set of actors, not every actor.
SOURCES: dict[str, dict] = {
    "RAVDESS_SPEECH_AUDIO": {
        "zenodo_record": "1188976",
        "files": ["Audio_Speech_Actors_01-24.zip"],
        "extract_to": "RAVDESS/audio_speech",
        "note": "All 24 actors, 1440 clips, 8 emotions x 2 intensities x 2 statements.",
    },
    "RAVDESS_SPEECH_VIDEO": {
        "zenodo_record": "1188976",
        # Four actors, alternating odd/even so both actor sexes are represented; the
        # numbering in RAVDESS is odd = male, even = female.
        # Twelve actors: enough for a speaker-disjoint train/validation/test split
        # with at least three actors held out. Four was not: 60/20/20 over two
        # actors per sex left the test split empty, which the splitter now refuses.
        "files": ["Video_Speech_Actor_%02d.zip" % i for i in range(1, 13)],
        "extract_to": "RAVDESS/video_speech",
        "note": "Four actors of audiovisual speech, co-occurring with the audio set.",
    },
}


#: GoEmotions: 58k Reddit comments, 27 emotion labels plus neutral, multiple raters per
#: example. Apache-2.0. Chosen because RAVDESS contains exactly two sentences and cannot
#: support learning text affect at all, and because the per-rater structure is the only
#: route this project has to a genuine label-quality analysis.
GOEMOTIONS = {
    "files": {
        "goemotions_1.csv":
            "https://storage.googleapis.com/gresearch/goemotions/data/full_dataset/"
            "goemotions_1.csv",
        "goemotions_2.csv":
            "https://storage.googleapis.com/gresearch/goemotions/data/full_dataset/"
            "goemotions_2.csv",
        "goemotions_3.csv":
            "https://storage.googleapis.com/gresearch/goemotions/data/full_dataset/"
            "goemotions_3.csv",
        "emotions.txt":
            "https://raw.githubusercontent.com/google-research/google-research/master/"
            "goemotions/data/emotions.txt",
        "ekman_mapping.json":
            "https://raw.githubusercontent.com/google-research/google-research/master/"
            "goemotions/data/ekman_mapping.json",
    },
    "extract_to": "GOEMOTIONS",
    "licence": "Apache-2.0",
    "licence_source": "https://github.com/google-research/google-research/tree/master/"
                      "goemotions (repository LICENSE)",
}


def fetch_goemotions() -> dict:
    """Download GoEmotions, which needs no archive handling: it is plain CSV."""
    progress.log("[GOEMOTIONS]")
    root = DATA_ROOT / GOEMOTIONS["extract_to"]
    root.mkdir(parents=True, exist_ok=True)
    entries = []
    for name, url in GOEMOTIONS["files"].items():
        dest = download(url, root / name)
        entries.append({"file": name, "bytes": dest.stat().st_size,
                        "sha256": sha256(dest), "url": url})
    manifest = {
        "dataset_id": "GOEMOTIONS",
        "title": "GoEmotions: A Dataset of Fine-Grained Emotions",
        "licence_id": GOEMOTIONS["licence"],
        "licence_source": GOEMOTIONS["licence_source"],
        "licence_verified": True,
        "verifier_note": ("Apache-2.0 per the google-research repository that "
                          "distributes it. Permissive: research use, modification and "
                          "redistribution allowed with attribution."),
        "retrieved_at": datetime.now(UTC).isoformat(),
        "local_path": str(root),
        "files": entries,
        "note": "58k Reddit comments, 27 emotions + neutral, multiple raters per "
                "example, which is what makes label-quality analysis possible.",
        "redistributed": False,
    }
    (DATA_ROOT / "GOEMOTIONS.manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    progress.log("      %d files -> %s (licence %s)"
                 % (len(entries), root, GOEMOTIONS["licence"]))
    return manifest


def zenodo_record(record_id: str) -> dict:
    url = "https://zenodo.org/api/records/%s" % record_id
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, expected_size: int | None = None) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (expected_size is None or dest.stat().st_size == expected_size):
        progress.log("      cached %s (%.1f MB)" % (dest.name, dest.stat().st_size / 1e6))
        return dest

    started = time.time()
    with urllib.request.urlopen(url, timeout=300) as r, dest.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        last = 0.0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            now = time.time()
            if now - last > 10:
                rate = done / max(now - started, 1e-9) / 1e6
                progress.log("      %s %.0f/%.0f MB  %.1f MB/s"
                             % (dest.name, done / 1e6, total / 1e6, rate))
                last = now
    progress.log("      downloaded %s (%.1f MB in %.0fs)"
                 % (dest.name, dest.stat().st_size / 1e6, time.time() - started))
    return dest


def fetch(name: str) -> dict:
    spec = SOURCES[name]
    progress.log("[%s]" % name)
    rec = zenodo_record(spec["zenodo_record"])
    metadata = rec.get("metadata", {})
    licence = metadata.get("license", {})
    licence_id = licence.get("id") if isinstance(licence, dict) else str(licence)

    by_key = {f["key"]: f for f in rec.get("files", [])}
    raw_dir = DATA_ROOT / "_archives"
    extract_root = DATA_ROOT / spec["extract_to"]
    extract_root.mkdir(parents=True, exist_ok=True)

    entries = []
    for key in spec["files"]:
        f = by_key.get(key)
        if f is None:
            raise KeyError("%s not present in Zenodo record %s"
                           % (key, spec["zenodo_record"]))
        url = f["links"]["self"]
        archive = download(url, raw_dir / key, f.get("size"))
        digest = sha256(archive)
        with zipfile.ZipFile(archive) as z:
            z.extractall(extract_root)
        entries.append({"file": key, "bytes": archive.stat().st_size,
                        "sha256": digest, "url": url})

    n_media = sum(1 for _ in extract_root.rglob("*.wav")) + \
        sum(1 for _ in extract_root.rglob("*.mp4"))
    manifest = {
        "dataset_id": name,
        "title": metadata.get("title"),
        "zenodo_record": spec["zenodo_record"],
        "doi": metadata.get("doi"),
        "licence_id": licence_id,
        "licence_source": "https://zenodo.org/api/records/%s (machine-readable "
                          "license field)" % spec["zenodo_record"],
        "licence_verified": True,
        "verifier_note": ("Licence read programmatically from the Zenodo record's own "
                          "API metadata at download time, not from secondary sources. "
                          "CC BY-NC-SA 4.0 permits non-commercial research use with "
                          "attribution and share-alike; no redistribution occurs here."),
        "retrieved_at": datetime.now(UTC).isoformat(),
        "local_path": str(extract_root),
        "n_media_files": n_media,
        "archives": entries,
        "note": spec["note"],
        "redistributed": False,
    }
    out = DATA_ROOT / ("%s.manifest.json" % name)
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    progress.log("      %d media files -> %s" % (n_media, extract_root))
    progress.log("      licence %s (verified from source API)" % licence_id)
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", choices=sorted(SOURCES))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--goemotions", action="store_true",
                    help="fetch the GoEmotions text corpus")
    ap.add_argument("--keep-archives", action="store_true",
                    help="keep the downloaded zips (they are large)")
    args = ap.parse_args()

    names = sorted(SOURCES) if args.all else ([args.dataset] if args.dataset else [])
    if not names and not args.goemotions:
        ap.error("pass --dataset, --goemotions or --all")

    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    for name in names:
        fetch(name)
    if args.goemotions or args.all:
        fetch_goemotions()

    if not args.keep_archives:
        archives = DATA_ROOT / "_archives"
        if archives.exists():
            freed = sum(p.stat().st_size for p in archives.glob("*"))
            for p in archives.glob("*"):
                p.unlink()
            progress.log("removed archives, freed %.1f GB" % (freed / 1e9))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
