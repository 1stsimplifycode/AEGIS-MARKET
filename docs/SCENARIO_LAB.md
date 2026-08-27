# The Scenario Lab

An additive extension. It adds no model, no dataset and no metric: every scenario is
executed by the same fitting harness, the same perturbation primitives, the same exposure
policy and the same bootstrap machinery the headline results use, so a scenario number and
a headline number are the same kind of object.

The workflow it implements is

```
OBSERVE → DETECT → EXPLAIN → QUANTIFY UNCERTAINTY → SIMULATE → COMPARE
```

and it stops there. There is no execution path in this module and it must not acquire one.

---

## 1. Three simulation methods, and why the distinction is load-bearing

Every scenario carries a `SimulationMethod`, and it is the most important field on the
record.

| Method | Rows | What it supports | Count |
|---|---|---|---|
| `OBSERVED_STRATUM` | selected, never altered | model behaviour on rows that really occurred | 6 |
| `COUNTERFACTUAL` | altered under a stated assumption | model sensitivity to that assumption; **nothing here happened** | 6 |
| `POLICY_COUNTERFACTUAL` | identical; only a declared rule differs | the difference attributable to that rule, under that policy | 4 |

Reporting a counterfactual as an event, or a stratum as an intervention, is the mistake
this distinction exists to prevent. It is rendered as an Observed/Simulated badge on every
scenario in the interface and as a column in every table.

---

## 2. What was found

### NIFTY-50 market conditions

Baseline: all 3,855 validation instrument-days, mean estimate **0.2384**.

| Scenario | Method | Mean estimate | Δ | 95% CI | Reading |
|---|---|---|---|---|---|
| High realised volatility | observed | 0.1823 | −0.0561 | −0.0960 to −0.0097 | established |
| Liquidity stress | observed | 0.2280 | −0.0116 | −0.0600 to +0.0194 | **unresolved** |
| Sentiment shock (−2σ text) | counterfactual | 0.1950 | −0.0464 | −0.0503 to −0.0413 | established |
| Text channel offline | counterfactual | 0.2324 | −0.0064 | −0.0103 to −0.0018 | established |
| Market channel offline | counterfactual | 0.2464 | +0.0090 | +0.0004 to +0.0181 | established |
| Delayed processing | counterfactual | 0.2381 | −0.0004 | −0.0016 to +0.0009 | **unresolved** |

Two findings worth stating plainly:

**The estimate is not a volatility proxy.** On the most volatile fifth of sessions it
reads *lower*, not higher, and the sign holds in every seed and under all five modality
subsets. A risk score that rose with volatility would be measuring the wrong thing.

**The model leans on what the narrative says, not on whether it is there.** A two-sigma
shift moves the estimate roughly seven times as far as removing the channel entirely. That
is what a fusion layer that withholds an unavailable channel but weights an available one
looks like from the outside.

### Mitigation policies

Identical rows, identical model, identical scores; only the declared exposure rule differs.

| Policy | Simulated reduction in the daily 5% tail loss | 95% CI | Simulated return given up |
|---|---|---|---|
| Baseline cap (0.30 → 0.80) | ₹5.20 lakh | ₹2.82–7.82 lakh | 0.0164 |
| Tighter cap (0.20 → 0.60) | ₹6.68 lakh | ₹4.02–9.44 lakh | 0.0406 |
| Uncertainty penalty ×3 | ₹6.21 lakh | ₹3.62–9.14 lakh | 0.0486 |

On a **declared notional research base of ₹100,000,000**, in simulation, on historical
rows, under a hypothetical exposure policy that was never applied to anyone's capital. The
return column is not optional: a tail reduction reported without its opportunity cost is
half a result.

No policy is marked best. The table compares.

### Transaction risk

`BLOCKED`. Five corpora assessed against six requirements, none qualified (L-23), so the
track runs on a declared synthetic fixture. On that fixture:

| Referral threshold | Elevated value covered | Cases referred |
|---|---|---|
| 0.75 (baseline) | 46.2% | 330 |
| 0.60 | 82.2% | 809 |
| 0.45 | 95.3% | 1,359 |

The trade-off is the finding. Nothing here models what a reviewer would find, because the
fixture contains no review outcome and inventing an effectiveness rate is exactly how a
simulation becomes a recovery claim.

One genuine result even on a fixture: taking the counterparty enrichment service offline
leaves the *score* unchanged (Δ +0.0009, interval spans zero) while raising the per-row
uncertainty from 0.000 to 0.161. The evidence behind the score degrades without the score
moving, which is the case a confidence number exists to catch.

### Ablation and robustness

**Ablation** (RQ-S4): the whole catalogue re-run under five modality subsets, 40 cells. The
direction of the effect survives in 38. The two exceptions are the same scenario — taking
the market channel offline raises the estimate on the full stack and lowers it once the
text channel has already gone — so that conclusion depends on which other channel is
present. Cells where the scenario shocks a block the subset removed are marked
`mechanically_zero` and are not counted as sign flips.

**Robustness** (RQ-S5): every scenario keeps the sign of its effect in all three seeds.
Eight of fourteen exceed 1.96× their own seed spread; the rest are smaller than what
re-seeding alone produces and are reported that way.

---

## 3. What the Scenario Lab refuses

Enforced in code, exercised by `tests/unit/test_scenario.py`, not promised in prose.

**No execution.** `assert_no_execution` refuses any purpose naming an action rather than an
analysis — placing an order, blocking a payment, freezing an account, approving or
rejecting a transaction, contacting a customer, or producing advice. Every trigger is
tested against the guard so a mangled entry fails a test rather than passing forever.

**No observed-outcome language.** `assert_outcome_language` refuses *recovered*, *profit
generated*, *guaranteed savings*, *loss prevented*, *AI decided*, *intervention caused* and
their neighbours, in scenario text and in every currency caveat.

**No bare currency figure.** A `CurrencyEstimate` carries its notional, its interval and
its caveat in the same record, and `consolidate_paper.py` fails if any row of the money
table does not declare itself unobserved.

**No advisory language, anywhere.** The existing product-surface scan covers the new
routes, and the claim guard that checks the paper text is run over the scenario module copy
too. It found four overclaims in the first draft of that copy and they were rewritten.

---

## 4. Reproducing it

```bash
python scripts/run_scenarios.py            # ~15 min: catalogue, ablation, robustness
python scripts/generate_paper_tables.py    # tables 14-17
python scripts/generate_research_figures.py  # figures S01-S06
python scripts/export_modules.py           # the interface over all of it
```

`--quick` runs one seed and skips the ablation and robustness sweeps. Individual modules
report the run rather than repeating it:

```bash
python scripts/run_module.py --module SCENARIO-01   # the catalogue, executes in place
python scripts/run_module.py --module SCENARIO-08   # corpus search, executes in place
python scripts/run_module.py --module SCENARIO-04   # reports the executed run
```

Artifacts land in `outputs/scenario/`; every one carries its commit, its environment and
its seeds.

---

## 5. Where it sits

| | |
|---|---|
| Package | `research/scenario/` — contract, spec, engine, market catalogue, transaction track, money |
| Modules | `SCENARIO-01` … `SCENARIO-08`, declared in `research_modules.yaml` |
| Routes | `/scenario` and `/scenario/[slug]`, both experiences in one page |
| Claims | CLAIM-25 … CLAIM-29 |
| Limitations | L-23 (no transaction corpus), L-24 (counterfactual ≠ causal) |
| Tables | table14 comparison, table15 uncertainty, table16 money, table17 transaction provenance |
| Figures | figS01 … figS06 |

Nothing in the existing 32 modules changed. NIFTY-50 remains the primary empirical
foundation; the Scenario Lab demonstrates that the same risk-intelligence architecture
answers a second class of question on it, and shows exactly what is missing before it could
answer that question on transaction data.
