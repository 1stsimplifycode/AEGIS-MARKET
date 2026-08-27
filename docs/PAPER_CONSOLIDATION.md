# AEGIS-Market — paper consolidation

The implementation is frozen. This document is the reading order for the evidence: what
the project claims, what backs each claim, and what each claim is not entitled to say.

Everything below is generated or checked by code. The machine-readable versions live in
`outputs/paper/` and are rebuilt by:

```
python scripts/run_scenarios.py              # the Scenario Lab
python scripts/generate_paper_tables.py      # 19 tables
python scripts/generate_research_figures.py  # 25 figures, incl. 3 consolidated + 6 scenario
python scripts/consolidate_paper.py          # ledger, matrix, map, scorecard
python scripts/export_modules.py             # the interface over all of it
```

`consolidate_paper.py` exits non-zero if any claim cites an artifact that is not on disk,
any figure or table is missing, or any quoted result carries no provenance stamp. It
currently reports **zero problems**.

---

## 1. The central narrative

The paper is not "we built a large system". It is seven questions, each with an
experiment and an answer the experiment actually supports.

**1. A large corpus is not automatically a large sample.** The corpus holds 1,304,458
traceable sample instances over 58,728 independent units — a design effect of 22.2, and
3,832 on the daily market shard. Every interval in the study comes from a cluster
bootstrap over units, a leave-one-actor-out fold structure, or a seed noise floor.
(CLAIM-13, L-19, Table 1, Figures figR01/figR02/figR11.)

**2. Synthetic augmentation is not universally beneficial, and distributional distance
does not predict when it is.** Real-only AUPRC 0.9390 against 0.3870 with 40,000
generated rows added, a difference of −0.5521 against a 0.0088 seed noise floor. Six
mechanisms were measured; five are not supported. The one that is: a tree ensemble
separates real from generated rows at AUC 0.9639 while a linear model reaches 0.4952.
The generated rows are marginally correct and interaction-free. Harmless at or below a
25% share. (CLAIM-14, N-09, Tables 9 and 9b, Figure figC01.)

**3. Multimodal fusion helps, and depends on temporal correspondence far more than on
signal quality.** AUDIO+FACE beats the best unimodal arm by 0.0823 against a 0.0217
noise floor — that clears. Permuting the audio-video pairing within actor, which
preserves speaker and label distribution and destroys only the correspondence, costs
0.2661 balanced accuracy; the heaviest additive audio noise costs 0.0278. Missing audio
costs 0.3741. (CLAIM-15, CLAIM-17, Table 8, Figure figC02.)

**4. Vision-language models produce useful visual representations and unsupported visual
claims, and the two families fail in opposite directions.** SmolVLM-256M asserted a face
in 15 of 15 faceless stimuli and identified 2 of 3 real faces; BLIP-VQA-base asserted a
face in 0 of 15 and identified 3 of 3 — while returning the same eyebrow answer for all
80 clips. Neither is called superior. (CLAIM-18, L-17, L-20, Table 4, Figures
figR16/figR08.)

**5. Calibration and accuracy are separate axes.** The best-calibrated arm (VLM, ECE
0.0954) has accuracy 0.2375; the most accurate arm (FULL, accuracy 0.3958) has the worst
ECE, 0.1635. The most overconfident arm is TEXT, which carries the least predictive
signal. (CLAIM-20, L-18, Table 7, Figure figC03.)

**6. Model behaviour under a stated condition is knowable; what would have happened is
not.** The Scenario Lab reports what the fitted model would have estimated under sixteen
declared conditions. On the most volatile fifth of sessions the estimate reads 0.0561
*lower*, not higher, with an interval excluding zero and the same sign in every seed and
every modality subset — the score is not a volatility proxy. A two-sigma shift in the
narrative channel moves it roughly seven times as far as removing that channel entirely.
None of this is causal: L-24 records why, and every counterfactual carries the assumption
it rests on. (CLAIM-25, CLAIM-26, CLAIM-27, CLAIM-28, Tables 14–16, Figures figS01–figS06.)

**7. A generated rationale is not a validated explanation.** Modality attribution
measured by intervention on the model's own inputs assigns the signal to the acoustic and
facial blocks (0.1458 each) against 0.0042 for the vision-language block. A
vision-language sentence about a face is a generated rationale for which no faithfulness
evaluation exists in this study, and it is never reported as an explanation of the
classifier. (CLAIM-21, Figure figR15.)

Together these say that trustworthy multimodal financial AI needs evidence,
uncertainty, provenance, robustness, scenario analysis and modality-aware validation —
because each of the seven results above is a way the naive version of the claim fails.

---

## 2. Claim ledger

29 claims: 19 SUPPORTED, 4 NOT SUPPORTED, 4 PARTIAL, 2 BLOCKED.

Every claim carries a metric, a statistical test, an artifact path that exists on disk,
the dataset, the experiment, the figures and tables that show it, and the limitations
that bound it. A claim with prose and no artifact is a finding, and the consolidation
script fails on one.

- Machine-readable: `outputs/paper/claim_ledger.csv` and `.md`
- Source of truth: `research/claims/ledger.py`
- Guard: `research.claims.ledger.self_check()` — the ledger passes its own scope rule,
  and every listed overclaim example is caught by the guard rather than merely written
  down.

| Claim | Subject | Status |
|---|---|---|
| CLAIM-01 | Affective text representation vs sentiment polarity | SUPPORTED |
| CLAIM-02 | Regime term cancels under softmax normalisation | SUPPORTED (analytic) |
| CLAIM-03 | Corrected regime fusion vs static attention | NOT SUPPORTED |
| CLAIM-04 | Detection lags episode onset at every threshold | SUPPORTED |
| CLAIM-05 | Calibration error grows with reported uncertainty | SUPPORTED |
| CLAIM-06 | Uncertainty-weighted fusion and selective risk | PARTIAL |
| CLAIM-07 | The microstructure null is uninformative, not zero | SUPPORTED |
| CLAIM-08 | Rendered image/audio/video carry no unique information | SUPPORTED |
| CLAIM-09 | LIME stability and its disagreement with occlusion | SUPPORTED |
| CLAIM-10 | Exposure cap reduces CVaR on the evaluation sample | SUPPORTED |
| CLAIM-11 | The pipeline reproduces bit-identically from a seed | SUPPORTED |
| CLAIM-12 | The product serves every route from exported artifacts | SUPPORTED |
| CLAIM-13 | Corpus scale, units and design effect | SUPPORTED |
| CLAIM-14 | Synthetic augmentation degrades above a 25% share | NOT SUPPORTED |
| CLAIM-15 | AUDIO+FACE beats the best unimodal arm | SUPPORTED |
| CLAIM-16 | No fusion rule is established as superior | NOT SUPPORTED |
| CLAIM-17 | Temporal correspondence dominates signal quality | SUPPORTED |
| CLAIM-18 | Cross-model vision-language reliability | SUPPORTED |
| CLAIM-19 | Vision-language contribution beyond the facial block | NOT SUPPORTED |
| CLAIM-20 | Calibration and accuracy order the arms differently | SUPPORTED |
| CLAIM-21 | Attribution by intervention; rationale is not explanation | PARTIAL |
| CLAIM-22 | Group-wise differences unestablished at this sample size | PARTIAL |
| CLAIM-23 | Financial-domain affect transfer is blocked | BLOCKED |
| CLAIM-24 | Speech, facial and linguistic affect above chance | SUPPORTED |
| CLAIM-25 | Risk reads lower on genuinely volatile sessions | SUPPORTED |
| CLAIM-26 | Estimate responds to what the text says, not whether it is there | SUPPORTED |
| CLAIM-27 | A tighter declared cap reduces the simulated tail further | PARTIAL |
| CLAIM-28 | Every scenario effect keeps its sign across seeds | SUPPORTED |
| CLAIM-29 | Transaction-risk corpus blocked; interface runs on a fixture | BLOCKED |

---

## 3. Final scorecard

Eleven properties, each SUPPORTED, QUALIFIED or NOT SUPPORTED. No composite score is
produced: averaging a measured figure against an unmeasured one produces a number that
means nothing, and a headline number is the one thing a reader would quote.

| Property | Verdict | Why |
|---|---|---|
| Explainability | NOT SUPPORTED | Eleven attribution methods run; the sanity suite fails sign consistency at 0.780 against a pre-declared 0.80 (N-01). |
| Fairness | QUALIFIED | Group-wise robustness and representation analysis over four groupings, one person-level; no difference established. Not a demographic fairness audit (L-21). |
| Robustness | QUALIFIED | Missing modality, misalignment, noise, dropout, input degradation and reduced training data all measured. Adversarial robustness NOT RUN. |
| Transparency | QUALIFIED | Every module run records commit, environment, adapter and canonical implementation. One documented gap: latency figures with no backing artifact. |
| Privacy | SUPPORTED | 1,329 files scanned, 0 findings. No personal data is held anywhere. |
| Calibration | QUALIFIED | Measured for every arm under one declared definition, and it disagrees with accuracy. 80 clips bound a 10-bin estimate (L-18, L-20). |
| Generalization | QUALIFIED | Forward-in-time and disjoint-instrument transfer measured; speaker-disjoint throughout Stream B. Holdout frozen (L-11); financial-domain transfer blocked (L-16). |
| Multimodal validity | QUALIFIED | Fusion beats the best unimodal arm above the noise floor. Rule choice and vision-language contribution are not established, and the gain is contingent on pairing. |
| VLM reliability | NOT SUPPORTED | Two families failed the same battery in opposite directions. Neither result supports treating a description as evidence about a frame. |
| Synthetic-data validity | NOT SUPPORTED | Degrades real-data AUPRC far beyond the seed noise floor at the configured share; the mechanism is measured, not guessed. |
| Reproducibility | SUPPORTED | Every executed artifact carries its commit and environment; every figure and table names the artifact it came from; a missing input yields NOT GENERATED rather than a placeholder. |

Machine-readable: `outputs/paper/scorecard.json`, `outputs/paper/scorecard.csv`.

---

## 4. Dataset accounting

**1,304,458 traceable sample instances over 58,728 independent units (design effect
22.2).** That phrasing is used everywhere the size is reported, and the alternative —
stating the row count as an observation count — is forbidden by L-19 and scanned for by
`tests/unit/test_paper_consolidation.py`.

| | |
|---|---|
| Real | 1,224,458 (93.9%) |
| Generated | 80,000 (6.1%) |
| Independent units | 58,728 |
| Design effect | 22.2 rows per unit; 3,832 on the daily market shard |
| Test split | 41,305 rows, 0 of them generated |
| Splits unit-disjoint | no — 159 units in both train and validation, 3 in both test and train |
| Sources | 8 datasets across 9 shards |

Machine-readable: `outputs/paper/dataset_accounting.json`. Provenance for every source
including the five rejected financial candidates: Table 11.

---

## 5. Financial-domain transfer

**General-domain affective validation: COMPLETED. Financial-affect domain transfer:
LIMITATION.**

Five candidates were assessed against six acceptance requirements and none qualified.
Nothing is fabricated and no general-domain corpus is relabelled financial. The full
assessment, requirement by requirement, is L-16 in `docs/LIMITATIONS.md` and
`outputs/human_affect/16_financial_domain_transfer/transfer.json`. The transfer module is
implemented and runs unchanged the day a qualifying corpus exists.

---

## 6. Limitations that must not be lost

These are registered as structured objects, cited by at least one claim each, and
enforced by `tests/unit/test_paper_consolidation.py`.

| ID | Limitation |
|---|---|
| L-16 | No licence-clear affect-annotated financial audiovisual corpus |
| L-17 | Vision-language descriptions include claims the image does not support |
| L-18 | Calibration and predictive accuracy are separate axes |
| L-19 | Row count overstates the effective sample size |
| L-20 | Vision-language evidence is bounded to small CPU-class models |
| L-21 | Group-wise analysis is representation analysis, not a fairness audit |
| L-22 | Affect labels are acted portrayals, not internal states |
| L-23 | No licence-clear, labelled, feature-interpretable transaction corpus |
| L-24 | Counterfactual simulation is not causal inference |
| N-08 | No fusion rule is established as superior to the others |
| N-09 | Synthetic augmentation degrades real-data performance |
| N-10 | The vision-language block adds no measurable predictive information |

Plus the fifteen Stream A limitations (L-01 to L-15) and seven earlier negative findings
(N-01 to N-07), unchanged.

---

## 7. Figures and tables

**25 research figures** (`outputs/research_figures/`) including three consolidated
figures and six scenario figures, **18 human-affective figures** (`outputs/human_affect/figures/`), and the Stream
A paper figures — 85 figure files in total, all copied into `public/figures/` and browsable
at `/research/figures` with the artifact each was drawn from.

| Consolidated figure | Carries |
|---|---|
| figC01_synthetic_augmentation | share sweep, distribution diagnostics, discriminator gap, paired result |
| figC02_alignment_degradation | all 24 conditions grouped into no corruption / noise / misalignment / missing modality |
| figC03_accuracy_vs_calibration | accuracy against ECE per arm, plus the overconfidence axis |

Six scenario figures (`figS01`–`figS06`) cover the comparison, the counterfactual
outcomes, the uncertainty forest faceted by quantity, the sensitivity tornado, the
ablation heatmap and the seed-spread plot. Every one keeps the simulation method visible
in its colour.

**19 paper tables** (`outputs/paper_tables/`), covering all twelve required
categories plus the Scenario Lab:

| # | Category | Table |
|---|---|---|
| 1 | Dataset composition | table01_dataset_composition |
| 2 | Dataset provenance | table11_dataset_provenance |
| 3 | Unimodal performance | table02_unimodal_results |
| 4 | Multimodal performance | table03_multimodal_results |
| 5 | Multi-seed performance | table06_multiseed |
| 6 | Fusion comparison | table12_fusion_comparison |
| 7 | VLM comparison | table04_vlm_comparison |
| 8 | Synthetic augmentation | table09_synthetic_augmentation, table09b_synthetic_mechanisms |
| 9 | Robustness | table08_robustness |
| 10 | Calibration | table07_calibration |
| 11 | XAI / modality contribution | table05_ablation |
| 12 | Statistical significance | table13_statistical_significance |
| — | Error analysis | table10_error_analysis, table10b_confidence_bands |
| — | Scenario comparison | table14_scenario_comparison |
| — | Scenario uncertainty | table15_scenario_uncertainty |
| — | Simulated currency figures | table16_scenario_money |
| — | Transaction corpus provenance | table17_transaction_provenance |

Full mappings, including which claims cite which: `outputs/paper/figure_map.csv` and
`outputs/paper/table_map.csv`.

---

## 8. Reproducibility

For every result the paper quotes: the artifact holding it, the commit and environment
that produced it, the seeds, the command that regenerates it, and the tables, figures and
claims that consume it — `outputs/paper/reproducibility_map.csv`.

A reviewer can traverse it in either direction:

```
paper number -> table/figure -> artifact -> experiment -> module -> canonical code
```

and, in reverse, from an artifact to every claim that rests on it.

The same chain is browsable in the application: `/research/artifacts` lists every file
with the modules on both sides of it, and each of the 32 module pages carries its own
experiment metadata, artifact paths and regeneration command in Research mode.

---

## 9. Where the interface fits

The 32 modules each have two experiences over one record. Product mode answers what the
module observed, how far the observation goes and what bounds it; Research mode answers
the same question with the experiment metadata, the artifact paths, the statistical test
and the limitations. Both read the same exported record in the same render, so neither
can show a number the other does not have.

Product mode is not permitted to state more than research mode supports. Where the
research position is "the spread is inside the seed noise floor", the product copy reads
"the ranking between them is not established" — and the claim guard that checks the paper
text is run over the interface text too, by
`tests/unit/test_module_ui.py::test_the_product_copy_passes_the_claim_guard`.
