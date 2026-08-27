# Trustworthy AI evaluation

Five principles treated as measurable engineering properties, each with evidence,
limitations and open questions. Not a marketing label, and deliberately not a score.

Regenerate with `python scripts/run_trust.py`. It reads existing artifacts, writes to
`outputs/trust/` and adds one new bundle at `public/data/trust.json`; it regenerates
nothing and needs no `--force`.

---

## Scorecard

| Principle | Status | Why |
|---|---|---|
| Explainability | **FAILED SANITY CHECK** | The suite runs and one pre-declared threshold is crossed the wrong way. |
| Fairness | **NOT MEASURED** | The groupings exist; the analysis has not been run. |
| Robustness | **PARTIAL** | Missing-modality is measured. Noise, corruption and adversarial are not. |
| Transparency | **PARTIAL** | Provenance is complete for module runs; one cited claim has no backing artifact. |
| Privacy | **SUPPORTED** | Scans executed over 734 files, zero findings, no personal data held. |

**There is no composite score, on purpose.** Averaging a measured explainability figure
against an unmeasured fairness figure produces a number that means nothing, and a single
headline figure is the one thing a reader would quote. `scorecard.build()` returns
`composite_score: None` and says why.

---

## Explainability — FAILED SANITY CHECK

Eleven attribution methods, a faithfulness/stability/agreement benchmark and a three-check
sanity suite are implemented and executed.

| Check | Statistic | Threshold | Passed |
|---|---:|---:|---|
| attribution sparsity | 0.998 | 0.25 | yes |
| model randomisation | 0.013 | 0.50 | yes |
| **sign consistency** | **0.780** | **0.800** | **no** |

The failure is retained rather than tuned away (N-01). Its meaning: LIME attributions do
not agree on the *sign* of a feature's contribution often enough across seeds to be relied
on at the feature level. Modality-level attribution is more stable than feature-level.

A second bound: attributions are computed on a single-model surrogate, because KernelSHAP
and LIME need one `f(x)` over a flat feature vector. The surrogate reaches AUPRC 0.9355
against the fused model's 0.9412, and that gap bounds how far any explanation describes the
model actually deployed.

**Not measured:** stability across market regimes; stability across modalities.

## Fairness — NOT MEASURED

Deliberately not a pass, and deliberately not fabricated.

**Demographic fairness is NOT APPLICABLE.** The data describes instruments, not people.
There is no demographic attribute anywhere, and inventing one so that a fairness section
could be filled in would be fabrication. Saying "fairness tested" on the back of a
manufactured attribute is worse than saying nothing.

**What is legitimately testable** and has *not* yet been run: performance and calibration
parity across instruments, regimes, liquidity bands and time periods. Every grouping
variable is already in the dataset.

A difference across groups would not automatically be unfairness. It would first have to
be statistically meaningful, and then checked against a data-distribution explanation —
an instrument with three episodes and one with forty are not comparable samples.

## Robustness — PARTIAL

Measured: leave-one-out modality arms, with a withheld modality's coverage flag zeroed as
well as its columns cleared so a stale flag cannot let it vote; temporal misalignment
sensitivity across six offsets per modality.

Not measured: feature noise, input corruption, induced missingness, reduced training data,
and whether uncertainty rises appropriately as evidence degrades.

**Adversarial robustness is a separate property and is NOT RUN.** Passing a random-noise
test would not license an adversarial claim, and the two must never be reported as one.

## Transparency — PARTIAL

Every module run records module id, status, adapter, canonical implementation, git commit,
environment snapshot and elapsed time. Every figure and table carries an experiment id, a
caption and a file hash. The claim ledger's guard rejects claims stated beyond their scope.

The gap is specific and documented: **CLAIM-12 quotes p50/p95 latency figures that no
artifact backs, and its page counts are stale** (KI-01, KI-02). Until the deployment
benchmark produces the artifact, that one claim is not traceable and is recorded as such
rather than quietly corrected.

## Privacy — SUPPORTED

The one principle evaluable in full today, because it is a property of what the repository
stores rather than of a model that has not been fitted. Evaluated by **running scans**, not
by writing a policy.

| Check | Result |
|---|---|
| Credential patterns in tracked source | CLEAN |
| `NEXT_PUBLIC_` applied to a secret-shaped name | CLEAN |
| Committed `.env` | CLEAN |
| PII in published artifacts and exported bundles | CLEAN |
| Credentials in provenance logs | CLEAN |

734 files scanned, 0 findings. **Personal data held: NONE.**

Two honest qualifications. First, the strongest control here is *absence*: the project
processes market data and generated text, so there is little to protect. That stops holding
the moment real speech or interview media are ingested (L-06), which would need a lawful
basis, retention limits, access control and a deletion path — none of which exists today.
Second, the scanners are pattern-based and cannot prove the absence of a secret that
matches no known credential shape.

The scanners were calibrated against two real false-positive classes rather than left
noisy: a placeholder connection string in `.env.example`, and digit runs inside SHA-256
artifact hashes. Both suppressions are narrow and documented in the code.

---

## Reading rules

- **SUPPORTED** requires a named artifact carrying the measurement. `PrincipleCard`
  raises if a card claims SUPPORTED with no artifact, so the shortcut is unavailable.
- **NOT MEASURED** means the evaluation has not been run. It is not a mild pass.
- No principle is ever labelled *trusted* or *safe*. Those are conclusions.
- Having SHAP installed is not explainability. Having input validation is not robustness.
  Having a privacy policy is not privacy.

## Where it lives

| Component | Path |
|---|---|
| Principles, statuses | `research/trust/__init__.py` |
| Privacy scanners and inventory | `research/trust/privacy.py` |
| Scorecard assembly | `research/trust/scorecard.py` |
| Affective audit | `research/affective/audit.py` |
| Runner | `scripts/run_trust.py` |
| Tests | `tests/unit/test_trustworthy_ai.py` |
| Research Mode page | `/research/trustworthy-ai` |

It is an evaluation layer over existing infrastructure, not a second framework: it reads
the XAI sanity table, the missing-modality table, the module manifest and the provenance
logs, and re-implements no metric.
