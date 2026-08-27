# Data licensing registry

Every dataset the system touches, with licence, coverage and restrictions. Sources that
could not be obtained are listed as not obtained rather than substituted.

## Used

| Dataset | Source | Licence / basis | Date accessed | Coverage | Restrictions | Version / hash |
|---|---|---|---|---|---|---|
| NSE daily cash bhavcopy | NSE public archive, read via a local mirror created by a prior project | Public exchange archive, retained for research use; not redistributed by this repository | 2026-08-18 | 2005-01-03 to 2026-08-14, 5,337 sessions, 8,399,065 rows, 4,487 symbols | Not redistributed. The archive is read from an external, read-only path (`AEGIS_NSE_ARCHIVE`) and never copied into the repository. | sha256 recorded in `research_artifacts/manifests/panel_build.json` |
| AEGIS chart images | Rendered by `research/image/chartgen.py` from the panel | Repository licence (original work) | generated | derived | none | content hash per file |
| AEGIS chart clips | Rendered by `scripts/make_media.py` | Repository licence (original work) | generated | derived | none | content hash per file |
| Market sonification | `research/audio/sonify.py` | Repository licence (original work) | generated | derived | Must be labelled as sonification, not speech (L-06) | deterministic from input |
| Synthetic episode corpus | `research/detection/episodes.py` | Repository licence (original work) | generated | aligned to panel | Must be labelled synthetic wherever metrics appear (L-04) | seed 20260818 |
| AFAL v1 lexicon | This repository | Repository licence (original work) | 2026-08-18 | 142 valence terms, 48 uncertainty, 24 urgency, 31 hype, 23 confidence, 35 skepticism, 15 contradiction, 26 negation, 19 intensifier, 89 emotion | Must not be cited as Loughran-McDonald, Harvard GI or VADER | `afal-v1` |

## Referenced only — never ingested

| Source | Basis | What is stored |
|---|---|---|
| CNBC, Bloomberg, Reuters, WSJ, FT video and articles | All rights reserved | URL, publisher, title, timestamps, licence verdict. No media bytes. |
| YouTube and Vimeo | Platform terms permit embedding, not redistribution | URL, channel, title, embed permission flag. No download. |
| Wikimedia Commons, Internet Archive, Zenodo | Open material, but per-item licence unverified | Reference record only. Upgrading to ingestion requires an explicit declaration plus evidence. |

The `MediaLicenseChecker` defaults every unrecognised host to `UNKNOWN`, and `UNKNOWN`
material is excluded from every redistributable artifact. A declaration of an ingestible
status without accompanying evidence raises `LicenseViolation` rather than being accepted.

## Not obtained

| Dataset | Why | Consequence |
|---|---|---|
| Point-in-time Nifty-50 constituents | No licence-clear source located | L-01: universe is a liquidity proxy, never called the Nifty 50 |
| NSE Level-2 order book history | Not published openly | L-02: OFI, VPIN, depth are `NOT MEASURED` |
| Labelled NSE market-integrity incidents | No open corpus | L-04: evaluation uses injected synthetic episodes |
| NSE sector / index-weight mapping | No licence-clear source located | L-07: propagation graph is purely statistical |
| Licence-clear financial speech audio | None located | L-06: audio modality uses sonification |
| SPIVA India reports | Access-restricted | Not used; no claim depends on it |

## Access ethics

No access control was circumvented. No paywall was bypassed. No robots directive was
ignored. No scraper runs as part of any pipeline in this repository: the market data comes
from a local archive, and every media source is either generated here or referenced by URL.
