"""Paper-quality consolidation: audit the claims, trace every number, score the whole.

    python scripts/consolidate_paper.py

This script adds no experiment, no model and no dataset. It reads what the pipeline
already produced and emits the documents a reviewer needs in order to check it:

  claim_ledger        every claim with its evidence, test, artifact, figure and table
  evidence_matrix     the same ledger reduced to one verdict per claim, with the gaps
  dataset_accounting  the corpus stated in the only vocabulary the data supports
  reproducibility_map paper number -> table/figure -> artifact -> experiment -> code
  scorecard           eleven properties, each SUPPORTED, QUALIFIED or NOT SUPPORTED
  figure_map          every figure, its caption, its source artifact and its claims
  table_map           every table, its caption, its source artifact and its claims

Two rules it enforces mechanically, because both failures are silent:

* **A claim without an openable artifact is a finding, not a footnote.** Any claim whose
  ``evidence_artifact`` does not exist on disk is reported in ``unsupported_claims`` and
  the script exits non-zero.
* **The corpus size is never stated as an observation count.** ``1,304,458`` counts
  traceable sample instances over 58,728 independent units. The phrasing guard in
  :mod:`research.claims.ledger` carries the forbidden variants through L-19, and this
  script writes the sanctioned phrasing into every document it emits.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

from research.claims import ledger as cl  # noqa: E402
from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import environment_snapshot, git_commit  # noqa: E402
from research.limitations import registry as reg  # noqa: E402
from research.trust import PRINCIPLES  # noqa: E402
from research.trust import scorecard as sc  # noqa: E402

OUT = paths.REPO_ROOT / "outputs" / "paper"
R = paths.REPO_ROOT

#: The three-value scale the paper reports. The project's own nine-value vocabulary is
#: finer, and collapsing it loses information -- so both are carried, and this mapping is
#: written down rather than applied by eye. NOT MEASURED collapses to NOT SUPPORTED
#: deliberately: absence of evidence is not support.
VERDICT = {
    "SUPPORTED": "SUPPORTED",
    "PARTIAL": "QUALIFIED",
    "OPEN QUESTION": "QUALIFIED",
    "OPEN_QUESTION": "QUALIFIED",
    "FUTURE VALIDATION": "QUALIFIED",
    "FUTURE_VALIDATION": "QUALIFIED",
    "BLOCKED": "QUALIFIED",
    "MEASURED": "QUALIFIED",
    "NOT SUPPORTED": "NOT SUPPORTED",
    "NOT_SUPPORTED": "NOT SUPPORTED",
    "NOT MEASURED": "NOT SUPPORTED",
    "NOT_MEASURED": "NOT SUPPORTED",
    "NOT RUN": "NOT SUPPORTED",
    "NOT_RUN": "NOT SUPPORTED",
    "FAILED SANITY CHECK": "NOT SUPPORTED",
    "FAILED_SANITY_CHECK": "NOT SUPPORTED",
}

#: The sanctioned phrasing for the corpus size, written once and reused everywhere so a
#: reviewer reads the same sentence in every document.
SCALE_PHRASE = ("1,304,458 traceable sample instances over 58,728 independent units "
                "(design effect 22.2)")


def _json(*parts):
    p = R.joinpath(*parts)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _emit(name: str, frame: pd.DataFrame, title: str, note: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT / ("%s.csv" % name), index=False)
    md = ["# %s" % title, "", note, "",
          frame.to_markdown(index=False), ""]
    (OUT / ("%s.md" % name)).write_text("\n".join(md), encoding="utf-8")
    progress.log("      %-26s %d rows" % (name, len(frame)))


# ------------------------------------------------------------------ claim ledger ----

def claim_ledger() -> tuple[pd.DataFrame, list[str]]:
    """The single source of truth for the paper, and the list of claims that fail it."""
    rows, broken = [], []
    for c in cl.CLAIMS:
        missing = [a for a in c.evidence_artifact if not (R / a).exists()]
        if missing:
            broken.append("%s: artifact not on disk: %s" % (c.id, ", ".join(missing)))
        lims = []
        for lid in c.limitations:
            entry = reg.by_id(lid)
            lims.append("%s (%s)" % (lid, entry.title) if entry else lid)
        rows.append({
            "CLAIM_ID": c.id,
            "CLAIM": c.claim,
            "METRIC": c.metric,
            "EVIDENCE": c.evidence,
            "EVIDENCE_ARTIFACT": "; ".join(c.evidence_artifact),
            "DATASET": c.dataset,
            "EXPERIMENT": c.experiment,
            "STATISTICAL_TEST": c.statistical_test,
            "FIGURE": "; ".join(c.figure_ids) or "-",
            "TABLE": "; ".join(c.table_ids) or "-",
            "SCOPE": cl.SCOPE_LABEL[c.scope],
            "STATUS": c.status.value,
            "VERDICT": VERDICT[c.status.value],
            "LIMITATION": "; ".join(lims) or "-",
            "ARTIFACTS_ON_DISK": not missing,
        })
    return pd.DataFrame(rows), broken


def evidence_matrix(ledger: pd.DataFrame) -> pd.DataFrame:
    """One row per claim, one column per kind of evidence, ticked or named.

    A matrix rather than prose because the useful reading is the column of blanks: a
    claim with no figure is fine, a claim with no artifact is not.
    """
    rows = []
    for r in ledger.to_dict("records"):
        rows.append({
            "CLAIM_ID": r["CLAIM_ID"],
            "VERDICT": r["VERDICT"],
            "has_dataset": bool(r["DATASET"].strip()),
            "has_experiment": bool(r["EXPERIMENT"].strip()),
            "has_metric": bool(r["METRIC"].strip()),
            "has_statistical_test": bool(r["STATISTICAL_TEST"].strip()),
            "has_artifact": bool(r["EVIDENCE_ARTIFACT"].strip()),
            "artifact_exists": bool(r["ARTIFACTS_ON_DISK"]),
            "has_figure": r["FIGURE"] != "-",
            "has_table": r["TABLE"] != "-",
            "bounded_by_limitation": r["LIMITATION"] != "-",
            "claim": r["CLAIM"][:110] + ("..." if len(r["CLAIM"]) > 110 else ""),
        })
    return pd.DataFrame(rows)


# ------------------------------------------------------------ dataset accounting ----

def dataset_accounting() -> dict:
    rep = _json("outputs", "corpus", "corpus_report.json")
    if not rep:
        return {"status": "NOT AVAILABLE",
                "reason": "outputs/corpus/corpus_report.json absent; "
                          "run scripts/build_corpus.py --all"}
    comp = rep["composition"]
    eff = rep["effective_sample_size"]
    return {
        "scale_phrase": SCALE_PHRASE,
        "forbidden_phrase": "1,304,458 independent observations",
        "why": ("Rows from one instrument-day series are repeated measurements of the "
                "same unit. Reporting them as independent observations would license "
                "intervals the data does not support, which is why every interval in "
                "this study comes from a cluster bootstrap over units, a "
                "leave-one-actor-out fold structure, or a seed noise floor."),
        "traceable_sample_instances": comp["total_samples"],
        "real": comp["real_samples"],
        "synthetic": comp["synthetic_samples"],
        "synthetic_percentage": comp["synthetic_percentage"],
        "independent_units": eff["n_independent_units"],
        "design_effect": eff["design_effect"],
        "rows_per_unit_max": eff["rows_per_unit_max"],
        "unit_disjoint_splits": eff["unit_disjoint_splits"],
        "units_shared_between_splits": eff["units_shared_between_splits"],
        "splits": {
            "train": comp["train_count"], "validation": comp["validation_count"],
            "test": comp["test_count"], "holdout": comp["holdout_count"],
        },
        "test_is_real_only": comp["test_is_real_only"],
        "synthetic_rows_in_test": comp["synthetic_test_count"],
        "source_datasets": comp["source_datasets"],
        "modalities": comp["modalities"],
        "unique_source_ids": comp["unique_source_ids"],
        "corpus_version": rep.get("corpus_version"),
        "generated_at": rep.get("generated_at"),
        "git_commit": rep.get("git_commit"),
        "bounded_by": ["L-19", "L-04", "N-09"],
    }


# --------------------------------------------------------- reproducibility map ----

#: Artifacts that carry a result the paper quotes: the result file, the file that carries
#: its provenance stamp, and the command that regenerates it. The stamp lives in a
#: separate file whenever the result is a CSV, because a CSV has nowhere to put a commit
#: hash. Naming the stamp file explicitly is what keeps "this CSV has no provenance" from
#: being indistinguishable from "this CSV's provenance is one directory over".
TRACE_SOURCES: list[tuple[str, tuple[str, ...], tuple[str, ...] | None, str]] = [
    ("corpus composition", ("outputs", "corpus", "corpus_report.json"), None,
     "python scripts/build_corpus.py --all"),
    ("corpus quality", ("outputs", "corpus", "02_corpus_quality", "quality.json"), None,
     "python scripts/run_module.py --module CORPUS-02"),
    ("real vs synthetic", ("outputs", "corpus", "real_vs_synthetic.json"), None,
     "python scripts/run_real_vs_synthetic.py"),
    ("synthetic share sweep", ("outputs", "corpus", "synthetic_ratio_sweep.json"), None,
     "python scripts/run_real_vs_synthetic.py --ratio-sweep"),
    ("synthetic degradation diagnosis",
     ("outputs", "corpus", "05_synthetic_degradation", "diagnosis.json"), None,
     "python scripts/diagnose_synthetic_degradation.py"),
    ("speech affect", ("outputs", "human_affect", "experiments", "speech_emotion.json"),
     ("outputs", "human_affect", "experiments", "run.json"),
     "python scripts/run_human_affect_experiments.py"),
    ("facial affect", ("outputs", "human_affect", "experiments", "face_emotion.json"),
     ("outputs", "human_affect", "experiments", "run.json"),
     "python scripts/run_human_affect_experiments.py"),
    ("text affect", ("outputs", "human_affect", "experiments", "text_affect.json"),
     ("outputs", "human_affect", "experiments", "run.json"),
     "python scripts/run_human_affect_experiments.py"),
    ("multimodal multi-seed",
     ("outputs", "human_affect", "11_multimodal_multiseed", "multiseed.json"), None,
     "python scripts/run_multimodal_multiseed.py"),
    ("fusion strategies",
     ("outputs", "human_affect", "12_fusion_strategies", "fusion_strategies.json"), None,
     "python scripts/run_fusion_strategies.py"),
    ("multimodal robustness",
     ("outputs", "human_affect", "13_multimodal_robustness", "robustness.json"), None,
     "python scripts/run_multimodal_robustness.py"),
    ("xai, calibration, representation",
     ("outputs", "human_affect", "14_xai_calibration_representation", "xai.json"), None,
     "python scripts/run_multimodal_xai_fairness.py"),
    ("vision-language family comparison",
     ("outputs", "human_affect", "15_vlm_family_comparison", "family_comparison.json"),
     None, "python scripts/run_vlm_family_comparison.py --all"),
    ("financial domain transfer",
     ("outputs", "human_affect", "16_financial_domain_transfer", "transfer.json"), None,
     "python scripts/run_module.py --module HUMAN_AFFECT-16"),
    ("stats multi-seed significance",
     ("outputs", "stats", "16_multiseed_significance", "seed_summary.csv"),
     ("outputs", "stats", "16_multiseed_significance", "significance.json"),
     "python scripts/run_multiseed.py"),
    ("stats robustness and transfer",
     ("outputs", "stats", "15_robustness_generalization", "robustness.csv"),
     ("outputs", "stats", "15_robustness_generalization", "run.json"),
     "python scripts/run_robustness_generalization.py"),
    ("ablation statistics",
     ("research_artifacts", "experiments", "ablation_statistics.csv"),
     ("research_artifacts", "manifests", "dataset_build.json"),
     "python scripts/run_experiments.py"),
    ("scenario comparison",
     ("outputs", "scenario", "scenario_comparison.csv"),
     ("outputs", "scenario", "scenario_results.json"),
     "python scripts/run_scenarios.py"),
    ("scenario uncertainty",
     ("outputs", "scenario", "scenario_uncertainty.csv"),
     ("outputs", "scenario", "scenario_results.json"),
     "python scripts/run_scenarios.py"),
    ("scenario currency figures",
     ("outputs", "scenario", "scenario_money.csv"),
     ("outputs", "scenario", "scenario_results.json"),
     "python scripts/run_scenarios.py"),
    ("scenario ablation",
     ("outputs", "scenario", "scenario_ablation.csv"),
     ("outputs", "scenario", "scenario_results.json"),
     "python scripts/run_scenarios.py"),
    ("scenario robustness",
     ("outputs", "scenario", "scenario_robustness.csv"),
     ("outputs", "scenario", "scenario_results.json"),
     "python scripts/run_scenarios.py"),
    ("transaction corpus search",
     ("outputs", "scenario", "transaction_corpus_search.json"), None,
     "python scripts/run_module.py --module SCENARIO-08"),
]


def reproducibility_map() -> pd.DataFrame:
    """paper number -> artifact -> experiment -> dataset -> code, with the stamp."""
    tables = _json("outputs", "paper_tables", "tables.json") or {}
    figures = _json("outputs", "research_figures", "figures.json") or {}
    ha_figures = _json("outputs", "human_affect", "figures", "figures.json") or {}

    #: artifact path -> the claims that quote it, so a reviewer can go either direction.
    by_artifact: dict[str, list[str]] = {}
    for c in cl.CLAIMS:
        for a in c.evidence_artifact:
            by_artifact.setdefault(a, []).append(c.id)

    rows = []
    for label, parts, stamp_parts, command in TRACE_SOURCES:
        rel = "/".join(parts)
        p = R.joinpath(*parts)
        payload = _json(*parts) if rel.endswith(".json") else None
        stamp = _json(*stamp_parts) if stamp_parts else payload
        env = (stamp or {}).get("environment") or {}
        seeds = (stamp or {}).get("seeds")
        if seeds is None:
            seeds = (stamp or {}).get("seed")
        consumers = sorted(
            t["table"] for t in tables.get("tables", []) if rel in t.get("source", ""))
        fig_consumers = sorted(
            f["figure"] for f in
            (figures.get("figures", []) + ha_figures.get("figures", []))
            if rel in (f.get("source_data") or ""))
        rows.append({
            "result": label,
            "artifact_path": rel,
            "exists": p.exists(),
            "provenance_from": "/".join(stamp_parts) if stamp_parts else rel,
            "git_commit": (stamp or {}).get("git_commit") or env.get("git_commit")
                          or "not stamped",
            "run_at": (stamp or {}).get("run_at")
                      or (stamp or {}).get("generated_at") or "not stamped",
            "seed_or_seeds": json.dumps(seeds) if seeds is not None else "-",
            "python": env.get("python", "").split(" ")[0] or "-",
            "platform": env.get("platform", "-"),
            "regenerate_with": command,
            "tables": "; ".join(consumers) or "-",
            "figures": "; ".join(fig_consumers) or "-",
            "claims": "; ".join(by_artifact.get(rel, [])) or "-",
        })
    return pd.DataFrame(rows)


# -------------------------------------------------------------------- scorecard ----

def scorecard() -> tuple[dict, pd.DataFrame]:
    card = sc.build()
    rows = []
    for name in PRINCIPLES:
        c = card["principles"][name]
        rows.append({
            "PROPERTY": name,
            "VERDICT": VERDICT[c["status"]],
            "PROJECT_STATUS": c["status"],
            "N_EVIDENCE": len(c["evidence"]),
            "N_LIMITATIONS": len(c["limitations"]),
            "N_ARTIFACTS": len(c["artifacts"]),
            "READING": c["summary"],
        })
    frame = pd.DataFrame(rows)
    card["paper_verdicts"] = {r["PROPERTY"]: r["VERDICT"] for r in rows}
    card["verdict_counts"] = frame["VERDICT"].value_counts().to_dict()
    card["verdict_mapping"] = VERDICT
    card["verdict_mapping_note"] = (
        "The project's nine-value vocabulary is finer than the paper's three-value one. "
        "Both are carried. NOT MEASURED maps to NOT SUPPORTED because absence of "
        "evidence is not support, and FAILED SANITY CHECK maps to NOT SUPPORTED because "
        "a check that fails is a result, not a pending task.")
    return card, frame


# ------------------------------------------------------------- figure and table ----

def figure_map() -> pd.DataFrame:
    by_figure: dict[str, list[str]] = {}
    for c in cl.CLAIMS:
        for f in c.figure_ids:
            by_figure.setdefault(f, []).append(c.id)

    rows = []
    for manifest, directory in (
        (_json("outputs", "research_figures", "figures.json"),
         "outputs/research_figures"),
        (_json("outputs", "human_affect", "figures", "figures.json"),
         "outputs/human_affect/figures"),
    ):
        for f in (manifest or {}).get("figures", []):
            name = f["figure"]
            rows.append({
                "figure": name,
                "path": "%s/%s.png" % (directory, name),
                "exists": (R / directory / ("%s.png" % name)).exists(),
                "caption": f["caption"],
                "source_artifact": f.get("source_data", "-"),
                "claims": "; ".join(by_figure.get(name, [])) or "-",
                "git_commit": (manifest or {}).get("git_commit", "-"),
            })
    return pd.DataFrame(rows)


def table_map() -> pd.DataFrame:
    by_table: dict[str, list[str]] = {}
    for c in cl.CLAIMS:
        for t in c.table_ids:
            by_table.setdefault(t, []).append(c.id)

    manifest = _json("outputs", "paper_tables", "tables.json") or {}
    rows = []
    for t in manifest.get("tables", []):
        name = t["table"]
        rows.append({
            "table": name,
            "path": "outputs/paper_tables/%s.csv" % name,
            "exists": (R / "outputs" / "paper_tables" / ("%s.csv" % name)).exists(),
            "rows": t["rows"],
            "caption": t["caption"],
            "source_artifact": t["source"],
            "claims": "; ".join(by_table.get(name, [])) or "-",
            "git_commit": manifest.get("git_commit", "-"),
        })
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------ main ----

def check_currency() -> list[str]:
    """No rupee figure may be shown without saying it is simulated.

    The one number a reader will lift out of this project and quote is a currency
    figure. Every row of the money table therefore has to carry its caveat and declare
    itself unobserved, and this is where that is checked rather than hoped for.
    """
    path = R / "outputs" / "scenario" / "scenario_money.csv"
    if not path.exists():
        return []
    frame = pd.read_csv(path)
    problems = []
    for row in frame.to_dict("records"):
        sid = row.get("scenario_id", "?")
        if row.get("is_observed") not in (False, "False", 0):
            problems.append("%s: a currency figure not declared as simulated" % sid)
        caveat = str(row.get("caveat") or "")
        if len(caveat) < 40:
            problems.append("%s: currency figure with no caveat" % sid)
        if "recover" in caveat.lower():
            problems.append("%s: caveat uses recovery language" % sid)
    return problems


def main() -> int:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    progress.log("[paper consolidation]")

    guard_problems = cl.self_check()

    ledger, broken = claim_ledger()
    _emit("claim_ledger", ledger, "Claim ledger",
          "Every claim the project makes, with the evidence, the artifact, the "
          "statistical test, the figure, the table and the limitations that bound it. "
          "This is the single source of truth for the paper: a sentence that is not in "
          "this table is not a claim this project makes.")

    matrix = evidence_matrix(ledger)
    _emit("evidence_matrix", matrix, "Evidence matrix",
          "One row per claim. The useful reading is the column of `False` values: a "
          "claim with no figure is acceptable, a claim with no artifact is not.")

    accounting = dataset_accounting()
    jsonio.write(OUT / "dataset_accounting.json", accounting)
    progress.log("      dataset_accounting.json")

    repro = reproducibility_map()
    _emit("reproducibility_map", repro, "Reproducibility map",
          "For every result the paper quotes: the artifact holding it, the commit and "
          "environment that produced it, the seeds, the command that regenerates it, "
          "and the tables, figures and claims that consume it. A reviewer can read this "
          "in either direction.")

    card, card_frame = scorecard()
    jsonio.write(OUT / "scorecard.json", card)
    _emit("scorecard", card_frame, "Final scorecard",
          "Eleven properties, each SUPPORTED, QUALIFIED or NOT SUPPORTED. No composite "
          "score is produced: averaging a measured figure against an unmeasured one "
          "gives a number that means nothing, and a headline number is the one thing a "
          "reader would quote.")

    figs = figure_map()
    _emit("figure_map", figs, "Figure map",
          "Every generated figure, the artifact it was drawn from, and the claims it "
          "supports.")

    tabs = table_map()
    _emit("table_map", tabs, "Table map",
          "Every generated table, the artifact it was drawn from, and the claims it "
          "supports.")

    currency_problems = check_currency()
    missing_figs = figs[~figs["exists"]]["figure"].tolist()
    missing_tabs = tabs[~tabs["exists"]]["table"].tolist()
    untraced = repro[~repro["exists"]]["artifact_path"].tolist()
    unstamped = repro[repro["git_commit"] == "not stamped"]["artifact_path"].tolist()

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "environment": environment_snapshot(),
        "scale_phrase": SCALE_PHRASE,
        "n_claims": len(ledger),
        "claims_by_verdict": ledger["VERDICT"].value_counts().to_dict(),
        "claims_by_status": ledger["STATUS"].value_counts().to_dict(),
        "n_limitations": len(reg.LIMITATIONS),
        "n_negative_findings": len(reg.NEGATIVE_FINDINGS),
        "n_figures": len(figs),
        "n_tables": len(tabs),
        "scorecard_verdicts": card["paper_verdicts"],
        "verdict_counts": card["verdict_counts"],
        "problems": {
            "claim_guard": guard_problems,
            "claims_with_missing_artifacts": broken,
            "figures_missing_on_disk": missing_figs,
            "tables_missing_on_disk": missing_tabs,
            "artifacts_missing_on_disk": untraced,
            "artifacts_without_a_provenance_stamp": unstamped,
            "currency_figures_without_their_caveat": currency_problems,
        },
        "elapsed_s": round(time.time() - t0, 1),
    }
    jsonio.write(OUT / "consolidation.json", manifest)

    total_problems = sum(len(v) for v in manifest["problems"].values())
    progress.log("%d claims, %d figures, %d tables, %d problems"
                 % (len(ledger), len(figs), len(tabs), total_problems))
    for name, items in manifest["problems"].items():
        for item in items:
            progress.log("  PROBLEM %s: %s" % (name, item))
    return 1 if total_problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
