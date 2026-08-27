# Known issues

Issues are recorded here rather than fixed opportunistically, and each is labelled
**PRE-EXISTING** or **RESTRUCTURING REGRESSION** so the two can never be confused.

Nothing in this file has been silently changed in the code. Where a fix would alter a
number that the claim ledger or the documentation quotes, the issue stays open until the
artifact that would replace the number has actually been produced.

---

## KI-01 — `CLAIM-12` cites latency figures with no backing artifact

**Status:** OPEN · **Kind:** PRE-EXISTING · **Severity:** provenance violation

`research/claims/ledger.py`, `CLAIM-12` states:

> p50 latency 5.9-10.0 ms and p95 17.1-32.9 ms over 20 samples per route

No file under `research_artifacts/` contains those numbers. Verified by searching the
artifact tree for each value. They were measured ad-hoc during an earlier session and
typed into the ledger by hand.

**Why it matters.** Every other number in the ledger is traceable to a stored artifact.
This one is not, which makes it exactly the hardcoded metric the project's own provenance
rule forbids. It is also unreproducible: nobody can re-run it and compare.

**Why it is not fixed yet.** The honest replacement is a real deployment benchmark that
measures latency percentiles and writes an artifact. That harness is **STATS-adjacent new
scientific functionality**, deliberately excluded from the structural restructuring so the
two changes stay separable. Editing the claim text now — either to delete the numbers or
to soften them — would change a documented claim without evidence either way.

**Resolution path.** Build the deployment benchmark harness, have it write
`research_artifacts/deployment/latency.json`, then rewrite `CLAIM-12` to cite that
artifact. Until then the figures should be read as unverified.

---

## KI-02 — `CLAIM-12` page and route counts are stale

**Status:** OPEN · **Kind:** PRE-EXISTING · **Severity:** minor factual drift

`CLAIM-12` states "204 pages including 162 instrument routes and 17 limitation routes".
The current build produces **210 pages** and **22 limitation routes** (15 limitations plus
7 negative findings). The instrument count of 162 is still correct.

The drift is a consequence of work that legitimately added routes. It is grouped with
KI-01 because both live in the same claim and should be corrected in one edit, once KI-01
has an artifact to cite.

---

## KI-03 — Three empty package stubs

**Status:** OPEN · **Kind:** PRE-EXISTING · **Severity:** cosmetic

`research/affective/__init__.py`, `research/media/__init__.py` and
`research/microstructure/__init__.py` are all zero bytes. The functionality their names
suggest lives elsewhere and works:

| Stub | Where the implementation actually is |
|---|---|
| `research/affective/` | `research/text/affect.py`, `research/audio/pipeline.py` |
| `research/media/` | `scripts/make_media.py` |
| `research/microstructure/` | `research/market/features.py` (`MICROSTRUCTURE_PROXIES`) |

Deleting them is safe but is a code change with no functional benefit, so it is recorded
rather than done during a restructuring whose whole purpose is to avoid touching working
code.

---

## KI-04 — Empty scaffolding directories

**Status:** OPEN · **Kind:** PRE-EXISTING · **Severity:** cosmetic

`experiments/configs/`, `experiments/manifests/` and `experiments/runners/` at the
repository root contain no files. The real experiment bundles are in
`research_artifacts/experiment_reports/`. Likewise `research_artifacts/csv/`, `json/`,
`latex/` and `supplementary/` are created by `paths.ensure_dirs()` but never populated by
the current pipeline.

---

## KI-05 — Structural layer is validated by a script, not by pytest

**Status:** RESOLVED in the metrics commit · **Kind:** INTRODUCED BY THIS RESTRUCTURING
(deliberate) · **Severity:** low

`scripts/validate_structure.py` checks the 32-module structure, adapter importability,
canonical-path existence, dependency cycles and generated-file drift. It is not yet wired
into `pytest`, because adding tests in the structural commit would change the 542-test
baseline that this phase is required to preserve exactly.

**Resolved.** `tests/unit/test_module_structure.py` now covers manifest integrity, the
16+16 directory layout, `run.bat` presence, absence of absolute paths, adapter resolution,
canonical-path existence, the wrapper-status invariant, exit-code constants, protected
artifact refusal verified by byte comparison, and the provenance-record schema. It found a
real defect on its first run: the provenance logger emitted bare `Infinity`.

---

## KI-06 — Prices are unadjusted for corporate actions, contaminating drawdown statistics

**Status:** OPEN · **Kind:** PRE-EXISTING · **Severity:** affects a cited claim

`data/panel/cash_panel.parquet` carries raw closes with no adjustment for splits or
bonuses. A next-session percentage change therefore reads a 10:1 split as a -90% session.
Across the whole panel, 1 468 of 8 394 578 session returns exceed +/-50%, the largest being
a +9 933% "return" that is plainly a consolidation.

**Scope within the scored rows is narrow and exact:** of the 3 855 scored
instrument-days, exactly **one** is affected — `TATASTEEL` on 2022-07-27, `fwd_ret =
-0.8954`, the 10:1 split. One row is enough. It alone drives `max_drawdown = -0.974` and
`worst_day = -0.895` in STATS-07; excluding it, the worst session is -0.199.

**What it touches.** The existing capital-consequence path in
`scripts/generate_paper_artifacts.py` builds its forward return exactly the same way
(`groupby(symbol).close.pct_change().shift(-1)`), so the cited CVaR delta (+0.00508) and
maximum-drawdown delta (+0.02531) rest on the same contaminated series. The CVaR figure is
a 5% tail mean and is far less sensitive to a single point than the drawdown figure is.

**Why it is not fixed here.** Fixing it means either adjusting the price series or
filtering suspected corporate actions, and both change numbers the claim ledger already
quotes. That is a deliberate artifact refresh, not something to fold into a metrics commit.

**What was done instead.** STATS-07 reports the contaminated metric unmodified — so it
stays comparable with the existing path — and publishes a `corporate_action_suspects`
block beside it naming the offending rows and giving the worst day with them excluded. The
number is not silently wrong; it is labelled.

**Resolution path.** Obtain an adjustment factor series, or filter sessions whose absolute
return exceeds a declared threshold and record how many were removed, then refresh the
capital-consequence artifacts and the claim in one deliberate pass.

---

## KI-07 — the cited ablation table still contains the unimplemented FUSION_EARLY arm

**Severity.** Medium. It affects one row of a published table, and that row supported a
comparison no experiment had actually run.

**What was wrong.** `fusion_strategy="early"` was accepted as a valid strategy, but
`Fusion.weights` mapped it onto the same all-zero logits as `late`, and nothing anywhere
concatenated the feature blocks. The FUSION_EARLY arm therefore *was* FUSION_LATE under a
different name.

**How it surfaced.** Not by inspection. In a single run the two arms produced adjacent
table rows agreeing to four decimal places, which reads as "early and late fusion perform
comparably" — a plausible and publishable-sounding result. STATS-16 refits every arm across
ten seeds, and the two columns came back **identical to machine precision on all ten**. Two
genuinely different algorithms do not do that. The same check found two other identical
groups, both of which are correct: `FULL` equals `FUSION_REGIME_CORRECTED` and
`NO_UNCERTAINTY` equals `FUSION_STATIC` because each pair is the same configuration under
two names, and `FUSION_REGIME_INHERITED` equals `FUSION_STATIC` because that degeneracy is
the predicted result of section 57.

**What was fixed.** `AegisRiskModel._fit_early` now fits a single learner over the union of
every modality's columns, with a row counted as covered when any modality covers it. Early
fusion consequently sees interactions *between* modalities that per-modality learners
cannot, and gives up per-modality attribution — which is the trade that makes the
comparison worth running. Measured on validation: early 0.9318 AUPRC against late 0.9477,
with per-row scores differing by up to 0.725. Late fusion wins here, and that is now a
measurement rather than an artefact of the two arms being the same code.

**What is still stale.** The ablation artifacts under `research_artifacts/` were generated
before the fix and still carry the old FUSION_EARLY row. They are protected artifacts, so
they were deliberately not regenerated in this pass; STATS-13 and STATS-14 refuse to
rewrite them without `--force`. Any paper text drawing an early-versus-late conclusion from
the cited table is drawing it from the defect.

**Resolution path.** Regenerate the ablation artifacts in a deliberate pass
(`--force`), then update the claim ledger row and any paper text that compares early with
late fusion. The corrected numbers are already available in
`outputs/stats/16_multiseed_significance/seed_table.csv`.

---

## KI-08 -- Florence-2 cannot run under transformers 5.15, so the VLM comparison is
single-architecture

**Severity.** Low for correctness, medium for interpretation. It does not make any reported
number wrong; it bounds what the cross-model comparison can be read to mean.

**What happened.** Florence-2-base was chosen as a third vision-language backend
specifically because it is architecturally different from SmolVLM -- a DaViT vision tower
with a BART text decoder against SmolVLM's SigLIP-plus-Llama arrangement. The weights
downloaded and the processor loads. Generation fails:

    AttributeError: 'Florence2LanguageConfig' object has no attribute 'forced_bos_token_id'

Its bundled remote code reads an attribute that the transformers 5.x config objects no
longer carry.

**Why it was not worked around.** The available fixes are pinning transformers to a 4.x
release or monkey-patching the vendored remote code at load time. The first breaks
SmolVLM, which needs 5.x and is the backend the results actually rest on; the second means
research results depending on a patch applied to a third party's downloaded source at
runtime. Neither is worth a third data point.

**What it costs.** The two backends that do run, SmolVLM-256M and SmolVLM-500M, share an
architecture family. The cross-model agreement figure -- region agreement 0.5425, word
overlap 0.2678 -- therefore measures whether **capacity** changes what is reported. It does
not establish what a different architecture would see, and RQ-V4 is answered only in that
narrower sense. The limitation is stated in `docs/VLM.md` and in the module notes rather
than left for a reader to infer from the model names.

**Resolution path.** A transformers release that restores compatibility, or a third
CPU-viable backend from another family. Nothing else in the branch needs to change: the
runner takes any backend registered in `research/vlm/models.py`.

---

## KI-09 -- fusion weights were fitted on in-bag posteriors

**Severity.** High while it lasted. It produced a wrong ordering of fusion rules and would
have supported the claim that weighted fusion is much worse than simple averaging.

**What was wrong.** The weighted-fusion arm grid-searched its modality weights against each
per-modality forest's predictions on its own training rows. A random forest's in-bag
predictions are close to memorised, so the search was optimising a fiction.

**How it surfaced.** The arm reported balanced accuracy 0.3885 and ECE 0.0700 -- *exactly*
face-alone's numbers, to four decimal places. Two arms matching that precisely is not a
coincidence, and the grid had in fact collapsed to putting all weight on the face modality
despite audio being the stronger single channel.

**What was fixed.** Weights are now fitted on **out-of-bag** posteriors, which come only
from trees that did not see the row. The weighted arm moves from 0.3885 to 0.5292, and the
four real fusion rules land within the seed noise floor of one another -- so the corrected
finding is that no rule is established as best, not that any particular one wins.

**Why it matters beyond this arm.** Any hyperparameter fitted against a model's predictions
on its own training data has the same defect. The out-of-bag route is available for bagged
ensembles; for other learners an inner split is required.

---

## Resolved

None yet. Issues move to this section with the commit that fixes them and the artifact
that proves it.
