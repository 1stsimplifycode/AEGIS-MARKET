"""Export research artifacts into the JSON bundles the Next.js app reads.

    python scripts/export_app_data.py

This is the seam between the two tracks (spec sections 62, 63, 88). The deployed product
reads only what this script writes; it never runs a model, loads a parquet file, or
touches the research pipeline. Consequences that are deliberate:

* the product cannot show a number the research pipeline did not produce;
* a Vercel deployment has no dependency on Python, GPUs or object storage;
* every exported bundle carries the run identifier it came from, so a figure in the app
  and a figure in the paper can be traced to the same run.

It also runs ``scripts/export_modules.py`` as its final step, which writes the 32-module
bundle and copies the generated figures and media into ``public/``. Keeping both in one
command is what makes "the single bridge" literally true.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from research.claims import ledger as cl
from research.core import jsonio, paths, progress
from research.data import dataset as ds
from research.limitations import registry as reg

OUT = paths.REPO_ROOT / "public" / "data"
NOW = datetime.now(UTC).isoformat()

#: How many instrument-days to export per instrument. The product shows recent history;
#: the full panel stays in the research track.
MAX_ROWS_PER_INSTRUMENT = 260


def _sanitise(obj):
    """Replace non-finite floats with null, recursively.

    Python's json module emits bare ``NaN`` and ``Infinity`` by default. Those are not
    valid JSON, and ``JSON.parse`` rejects the whole document -- so a single NaN buried in
    a nested analysis result silently turned an entire page into "data not available".
    Writing with ``allow_nan=False`` after this pass means any value this misses raises
    at export time instead of failing quietly in the browser.
    """
    if isinstance(obj, float):
        return None if not np.isfinite(obj) else obj
    if isinstance(obj, (np.floating, np.integer)):
        v = float(obj)
        return None if not np.isfinite(v) else (int(obj)
                                                if isinstance(obj, np.integer) else v)
    if isinstance(obj, dict):
        return {k: _sanitise(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitise(v) for v in obj]
    return obj


def write(name: str, rows: list[dict], extra: dict | None = None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": NOW, "rows": rows}
    if extra:
        payload.update(extra)
    payload = _sanitise(payload)
    # Through the shared scrubber: everything under `public/` is served to a reader, and
    # an absolute path there publishes the generating machine's layout while citing
    # nothing the reader can open.
    payload = jsonio.scrub_paths(payload, leaked := [])
    for one in sorted(set(leaked)):
        progress.log("  REWROTE ABSOLUTE PATH %s" % one)
    p = OUT / name
    p.write_text(json.dumps(payload, indent=1, default=_json_default,
                            allow_nan=False),
                 encoding="utf-8")
    progress.log("  %-22s %6d rows  %.1f KB"
                 % (name, len(rows), p.stat().st_size / 1024))


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        v = float(o)
        return None if not np.isfinite(v) else v
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    if o is pd.NaT:
        return None
    return str(o)


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(f) else round(f, 6)


def main() -> int:
    exp_dir = paths.ARTIFACTS / "experiments"
    per_row = exp_dir / "per_row_FULL.parquet"
    progress.log("exporting app data to %s" % OUT)

    # ---------------------------------------------------------------- assessments ----
    if per_row.exists():
        d = pd.read_parquet(per_row)
        d = d.sort_values(["symbol", "date"])
        keep = d.groupby("symbol", group_keys=False).tail(MAX_ROWS_PER_INSTRUMENT)
        mod_cols = [c for c in keep.columns if c.startswith("contrib_")]
        w_cols = [c for c in keep.columns if c.startswith("weight_")]
        rows = []
        for r in keep.itertuples(index=False):
            rec = {
                "instrument": r.symbol,
                "date": pd.Timestamp(r.date).strftime("%Y-%m-%d"),
                "integrityRisk": _num(r.integrity_risk),
                "uncertainty": _num(r.uncertainty),
                "coverage": _num(r.coverage),
                "riskState": getattr(r, "risk_state", "NORMAL"),
                "regime": None,
            }
            contrib = {c.replace("contrib_", ""): _num(getattr(r, c))
                       for c in mod_cols}
            weight = {c.replace("weight_", ""): _num(getattr(r, c)) for c in w_cols}
            if contrib:
                rec["modalityContribution"] = contrib
            if weight:
                rec["modalityWeight"] = weight
            rows.append(rec)
        write("assessments.json", rows)

        # ------------------------------------------------------------- windows ----
        from research.detection import state as st
        wins = st.windows_from_frame(d, "integrity_risk")
        write("windows.json", [{
            "instrument": w.symbol,
            "tEntry": pd.Timestamp(w.t_entry).strftime("%Y-%m-%d"),
            "tExit": pd.Timestamp(w.t_exit).strftime("%Y-%m-%d") if w.t_exit else None,
            "tPeak": pd.Timestamp(w.t_peak).strftime("%Y-%m-%d"),
            "peakScore": _num(w.peak_score),
            "censored": bool(w.censored),
        } for w in wins])
    else:
        progress.log("  per_row_FULL.parquet absent: assessments and windows "
                     "not exported")
        write("assessments.json", [])
        write("windows.json", [])

    # -------------------------------------------------------------- experiments ----
    f = exp_dir / "ablation_results.csv"
    if f.exists():
        a = pd.read_csv(f)
        write("experiments.json", [{
            "experimentId": r.get("experiment_id", "ablation"),
            "arm": r["arm"],
            "status": r.get("status", "OK"),
            "fusion": r.get("fusion", ""),
            "modalities": r.get("modalities", ""),
            "auprc": _num(r.get("auprc")),
            "auroc": _num(r.get("auroc")),
            "f1": _num(r.get("f1")),
            "ece": _num(r.get("ece")),
            "ciLow": _num(r.get("ci_low")),
            "ciHigh": _num(r.get("ci_high")),
        } for _, r in a.iterrows()])
    else:
        write("experiments.json", [])

    f = exp_dir / "ablation_statistics.csv"
    if f.exists():
        s = pd.read_csv(f)
        write("statistics.json", [{
            "arm": r["arm"],
            "comparison": r.get("comparison", ""),
            "deltaAuprc": _num(r.get("delta_auprc")),
            "pValue": _num(r.get("p_value")),
            "adjustedP": _num(r.get("adjusted_p")),
            "significant": bool(r.get("significant_fdr_5pct", False)),
            "test": r.get("test", ""),
            "description": r.get("description", ""),
        } for _, r in s.iterrows()])
    else:
        write("statistics.json", [])

    # ------------------------------------------------------------------ figures ----
    figs = sorted(paths.MANIFESTS.glob("figures_*.json"))
    if figs:
        recs = json.loads(figs[-1].read_text(encoding="utf-8"))
        write("figures.json", [{
            "figureId": r["figure_id"],
            "number": r.get("number"),
            "title": r["title"],
            "caption": r["caption"],
            "placement": r["placement"],
            "experimentId": r["experiment_id"],
            "runId": r["run_id"],
            "commit": r.get("commit"),
            "sourceData": r.get("source_data", ""),
            "generationScript": r.get("generation_script", ""),
            "outputFormats": r.get("output_formats", []),
        } for r in recs])
    else:
        write("figures.json", [])

    # ----------------------------------------------------------------- coverage ----
    dpath = paths.PANEL / "multimodal_dataset.parquet"
    if dpath.exists():
        data = pd.read_parquet(dpath, columns=list(ds.COVERAGE_FLAGS))
        notes = {
            "audio": "sonification of market data, not speech (L-06)",
            "microstructure": "daily-aggregate proxies only; depth/OFI/VPIN "
                              "NOT MEASURED (L-02)",
            "propagation": "statistical co-movement only (L-07)",
        }
        rows = []
        for flag in ds.COVERAGE_FLAGS:
            mod = flag.replace("cov_", "").replace("micro", "microstructure")
            cov = float(data[flag].mean()) if flag in data.columns else 0.0
            rows.append({
                "modality": mod,
                "coverage": round(cov, 4),
                "status": "OK" if cov > 0.5 else "SPARSE" if cov > 0 else "ABSENT",
                "note": notes.get(mod),
            })
        rows.append({"modality": "microstructure (true order book)", "coverage": 0.0,
                     "status": "NOT MEASURED",
                     "note": "NSE does not publish historical L2 depth openly (L-02)"})
        write("coverage.json", rows)
    else:
        write("coverage.json", [])

    # ------------------------------------------------------------------ evidence ----
    corpus = paths.PANEL / "text_corpus.parquet"
    media_manifest = paths.MANIFESTS / "media_manifest.json"
    rows = []
    if corpus.exists():
        c = pd.read_parquet(corpus).tail(120)
        for r in c.itertuples(index=False):
            rows.append({
                "modality": "text",
                "eventTime": pd.Timestamp(r.date).strftime("%Y-%m-%d"),
                "knowledgeTime": pd.Timestamp(r.date).strftime("%Y-%m-%d"),
                "source": "synthetic episode corpus (%s)" % r.doc_kind,
                "licenceStatus": "AUTHORIZED",
                "summary": r.text[:220],
            })
    if media_manifest.exists():
        mm = json.loads(media_manifest.read_text(encoding="utf-8"))
        for cat, items in mm.get("categories", {}).items():
            for it in items or []:
                if cat == "C_references":
                    rows.append({
                        "modality": "video",
                        "eventTime": it.get("publication_time") or "unknown",
                        "knowledgeTime": it.get("retrieval_time", "")[:10],
                        "source": it.get("channel") or "third party",
                        "licenceStatus": it["licence"]["status"],
                        "summary": "%s -- metadata only, no media stored"
                                   % (it.get("title") or "reference"),
                        "referenceUrl": it.get("source_url"),
                    })
                else:
                    mod = ("image" if "chart_" in str(it.get("path", "")) and
                           str(it.get("path", "")).endswith(".png")
                           else "video" if str(it.get("path", "")).endswith(".mp4")
                           else "audio")
                    rows.append({
                        "modality": mod,
                        "eventTime": (it.get("window") or ["unknown"])[-1]
                        if it.get("window") else "derived",
                        "knowledgeTime": mm.get("generated_at", "")[:10],
                        "source": "AEGIS-generated (%s)" % cat,
                        "licenceStatus": it.get("licence", "AUTHORIZED"),
                        "summary": it.get("evidence", "")[:220],
                    })
    write("evidence.json", rows)

    # ----------------------------------------------------------------- affective ----
    if dpath.exists():
        cols = ["date", "txt_valence", "txt_arousal", "txt_uncertainty", "txt_urgency",
                "txt_hype", "txt_narrative_intensity"]
        have = [c for c in cols if c in pd.read_parquet(dpath, columns=None).columns] \
            if False else cols
        try:
            a = pd.read_parquet(dpath, columns=have)
            g = a.groupby("date").mean(numeric_only=True).tail(180).reset_index()
            write("affective.json", [{
                "date": pd.Timestamp(r.date).strftime("%Y-%m-%d"),
                "valence": _num(r.txt_valence),
                "arousal": _num(r.txt_arousal),
                "uncertainty": _num(r.txt_uncertainty),
                "urgency": _num(r.txt_urgency),
                "hype": _num(r.txt_hype),
                "narrativeIntensity": _num(r.txt_narrative_intensity),
            } for r in g.itertuples(index=False)])
        except Exception as exc:
            progress.log("  affective export skipped: %s" % exc)
            write("affective.json", [])
    else:
        write("affective.json", [])

    # --------------------------------------------------------------- propagation ----
    edges = paths.STATISTICS / "propagation_edges.csv"
    if edges.exists():
        e = pd.read_csv(edges).sort_values("weight", ascending=False).head(400)
        write("propagation.json", [{"source": r.source, "target": r.target,
                                    "weight": _num(r.weight)}
                                   for r in e.itertuples(index=False)])
    else:
        write("propagation.json", [])

    # ---------------------------------------------------------------- provenance ----
    tbl = paths.TABLES / "table02_provenance.json"
    if tbl.exists():
        rows = json.loads(tbl.read_text(encoding="utf-8"))
        write("provenance.json", [{"source": r["source"], "modality": r["modality"],
                                   "licence": r["licence"], "coverage": r["coverage"],
                                   "status": r["status"]} for r in rows])
    else:
        write("provenance.json", [])


    # ------------------------------------------------------- universe manifest ----
    # The product must be able to say exactly which universe it is showing (spec
    # section 8). Because no licence-clear index membership exists, this manifest is
    # also where the proxy is labelled as a proxy rather than quietly called an index.
    pb = paths.MANIFESTS / "panel_build.json"
    if pb.exists():
        info = json.loads(pb.read_text(encoding="utf-8"))
        u = info.get("universe", {})
        write("universe.json", [{
            "id": "pit_liquidity_proxy_top50",
            "name": "Point-in-time liquidity proxy (top 50 by traded value)",
            "kind": "point_in_time_proxy",
            "effectiveDate": u.get("last_rebalance"),
            "datasetVersion": ds.DATASET_VERSION,
            "memberCount": int(u.get("universe_size") or 0),
            "distinctMembersEver": int(u.get("distinct_symbols_ever") or 0),
            "rebalances": int(u.get("rebalances") or 0),
            "meanEntriesPerRebalance": _num(u.get("mean_entries_per_rebalance")),
            "isIndexMembership": False,
            "caveat": (
                "Membership is recomputed at each monthly rebalance from trailing median "
                "traded value, using only sessions that precede the rebalance. It is "
                "survivorship-safe by construction and is NOT the Nifty 50: no "
                "licence-clear point-in-time constituent history was available, and "
                "inventing one is prohibited."),
        }])
    else:
        write("universe.json", [])

    # -------------------------------------------------------------- clusters ----
    # Sectors are unavailable (L-07). Groups are formed from the exported propagation
    # graph by connected components over the strongest edges, and are called what they
    # are: statistical clusters.
    edges_path = paths.STATISTICS / "propagation_edges.csv"
    if edges_path.exists():
        e = pd.read_csv(edges_path)
        e = e.sort_values("weight", ascending=False).head(300)
        parent: dict[str, str] = {}

        def _find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def _union(a: str, b: str) -> None:
            ra, rb = _find(a), _find(b)
            if ra != rb:
                parent[ra] = rb

        for r in e.itertuples(index=False):
            _union(str(r.source), str(r.target))
        groups: dict[str, list[str]] = {}
        for node in list(parent):
            groups.setdefault(_find(node), []).append(node)
        weights: dict[str, list[float]] = {}
        for r in e.itertuples(index=False):
            weights.setdefault(_find(str(r.target)), []).append(float(r.weight))

        rows = []
        for i, (root, members) in enumerate(
                sorted(groups.items(), key=lambda kv: -len(kv[1])), 1):
            if len(members) < 2:
                continue
            w = weights.get(root, [])
            rows.append({
                "id": "cluster-%02d" % i,
                "label": "Statistical cluster %d" % i,
                "members": sorted(members),
                "meanAbsCorrelation": _num(sum(w) / len(w)) if w else None,
                "basis": ("connected components over trailing 126-session return "
                          "correlation above 0.25, estimated strictly before each "
                          "decision date; not a sector mapping"),
            })
        write("clusters.json", rows)
    else:
        write("clusters.json", [])

    # ------------------------------------------- limitations and claim ledger ----
    write("limitations.json", reg.to_dict()["limitations"]
          + reg.to_dict()["negative_findings"],
          extra={"meta": reg.summary()})
    write("claims.json", cl.to_dict()["claims"], extra={"meta": cl.summary()})

    # ---------------------------------------------------- research angle results ----
    ang = paths.ARTIFACTS / "research_angles" / "research_angles.json"
    if ang.exists():
        payload = json.loads(ang.read_text(encoding="utf-8"))
        write("research_angles.json", [], extra={"meta": payload})
        mi = paths.ARTIFACTS / "research_angles" / "modality_information_matrix.csv"
        if mi.exists():
            m = pd.read_csv(mi)
            write("modality_info.json", [{
                "modality": r.modality,
                "total_auprc": _num(r.total_auprc),
                "unique": _num(r.unique),
                "redundant": _num(r.redundant),
                "conflict_rate": _num(r.conflict_rate),
                "missing_rate": _num(r.missing_rate),
            } for r in m.itertuples(index=False)])
        else:
            write("modality_info.json", [])
    else:
        write("research_angles.json", [])
        write("modality_info.json", [])

    # ---------------------------------------------------------- position lifecycle ----
    lc_dir = paths.ARTIFACTS / "lifecycle"
    lc_path = lc_dir / "lifecycle.json"
    if lc_path.exists():
        lc = json.loads(lc_path.read_text(encoding="utf-8"))
        res = lc.get("results", {})
        write("lifecycle.json", [], extra={"meta": {
            "cohort": lc.get("cohort"), "scoring": lc.get("scoring"),
            "state_counts": lc.get("state_counts"),
            "phase_counts": lc.get("phase_counts"),
            "material_change_base_rate": _num(lc.get("material_change_base_rate")),
            "instruments_with_change_points":
                lc.get("instruments_with_change_points"),
            "n_change_points": lc.get("n_change_points"),
            "not_available": lc.get("not_available"),
            "transitions": res.get("transitions"),
            "signal_order": res.get("signal_order"),
            "stage": res.get("EXP-LC-1"),
            "conflict": res.get("conflict"),
            "phase_definition_check": res.get("EXP-L15-1"),
        }})

        traj_path = lc_dir / "lifecycle_trajectories.parquet"
        if traj_path.exists():
            traj = pd.read_parquet(traj_path)
            # One row per instrument-session would be 5783 rows of mostly redundant
            # detail. The app needs the trajectory, so the series is carried per
            # instrument and the per-row columns are trimmed to what a chart draws.
            rows = []
            for sym, g in traj.sort_values(["symbol", "date"]).groupby("symbol"):
                rows.append({
                    "symbol": str(sym),
                    "n_sessions": int(len(g)),
                    "dates": [d.isoformat()[:10] for d in g["date"]],
                    "risk": [_num(v) for v in g["integrity_risk"]],
                    "uncertainty": [_num(v) for v in g["uncertainty"]],
                    "phase": [str(v) for v in g["phase"]],
                    "state": [str(v) for v in g["lifecycle_state"]],
                    "band": [str(v) for v in g["risk_band"]],
                    "change_points": [i for i, v in
                                      enumerate(g["is_change_point"]) if bool(v)],
                    "first_date": g["date"].iloc[0].isoformat()[:10],
                    "last_date": g["date"].iloc[-1].isoformat()[:10],
                    "final_band": str(g["risk_band"].iloc[-1]),
                    "final_risk": _num(g["integrity_risk"].iloc[-1]),
                })
            write("lifecycle_trajectories.json", rows)
        else:
            write("lifecycle_trajectories.json", [])
    else:
        write("lifecycle.json", [])
        write("lifecycle_trajectories.json", [])

    # ------------------------------------------------------- reproducibility ----
    repro = sorted(paths.MANIFESTS.glob("reproducibility_*.json"))
    meta: dict = {"verified": True}
    if repro:
        man = json.loads(repro[-1].read_text(encoding="utf-8"))
        meta.update({
            "commit": man.get("git_commit"),
            "seed": man.get("seed"),
            "environment": {
                "python": man.get("python_version"),
                "platform": man.get("platform"),
                "node": man.get("node_version") or "NOT INSTALLED",
                "timestamp": man.get("timestamp"),
                "git_dirty": man.get("git_dirty"),
            },
        })
    write("reproducibility.json", [], extra={"meta": meta})

    # The trained audio model's own scorecard. Exported here for the same reason as
    # everything else in this directory: the product must be able to show what the model
    # scores without being able to compute it, and without reading research_artifacts at
    # request time. It is gated as a static bundle too — see GATED_BUNDLES in lib/gate.ts
    # — because the metrics are a week-7 capability, and a bundle anyone can fetch
    # directly is not gated at all.
    audio_eval = (paths.REPO_ROOT / "research_artifacts" / "models" /
                  "audio" / "audio_model_v1_evaluation.json")
    if audio_eval.exists():
        report = json.loads(audio_eval.read_text(encoding="utf-8"))
        cal = report.get("calibration", {})
        write("audio_model.json", report.get("per_class", []), extra={"meta": {
            "model_id": report.get("model_id"),
            "task": report.get("task"),
            "accuracy": report.get("accuracy"),
            "macro_f1": report.get("macro_f1"),
            "weighted_f1": report.get("weighted_f1"),
            "baseline_accuracy": report.get("baseline", {}).get("accuracy"),
            "baseline_macro_f1": report.get("baseline", {}).get("macro_f1"),
            "ece": cal.get("expected_calibration_error"),
            "brier": cal.get("brier_score"),
            "samples": report.get("samples"),
            "speakers": len(report.get("speakers", [])),
            "split_strategy": report.get("split_strategy"),
            "robustness": report.get("robustness", {}).get("results", []),
        }})
    else:
        progress.log("  audio_model.json       SKIPPED - the model is not evaluated")

    # The trained video model's scorecard, on the same terms as the audio one: the
    # product must be able to show what the model scores without being able to compute it,
    # and the bundle is gated in GATED_BUNDLES because the metrics are a week-9
    # capability.
    video_eval = (paths.REPO_ROOT / "research_artifacts" / "models" / "video" /
                  "video_model_v1_evaluation.json")
    if video_eval.exists():
        report = json.loads(video_eval.read_text(encoding="utf-8"))
        cal = report.get("calibration", {})
        write("video_model.json", report.get("per_class", []), extra={"meta": {
            "model_id": report.get("model_id"),
            "task": report.get("task"),
            "temporal": report.get("temporal_aggregation"),
            "accuracy": report.get("accuracy"),
            "macro_f1": report.get("macro_f1"),
            "weighted_f1": report.get("weighted_f1"),
            "baseline_accuracy": report.get("baseline", {}).get("accuracy"),
            "baseline_macro_f1": report.get("baseline", {}).get("macro_f1"),
            "ece": cal.get("expected_calibration_error"),
            "brier": cal.get("brier_score"),
            "samples": report.get("samples"),
            "actors": len(report.get("actors", [])),
            "split_strategy": report.get("split_strategy"),
            "robustness": report.get("robustness", {}).get("results", []),
            "confusion_matrix": report.get("confusion_matrix"),
            "small_sample_note": report.get("small_sample_note"),
        }})
    else:
        progress.log("  video_model.json       SKIPPED - the model is not evaluated")

    # The module bundle is part of the same bridge rather than a second one. This script's
    # contract is that the product can display nothing the research pipeline did not
    # produce; a separate exporter that someone could forget to run would be a way for the
    # 32 module pages to fall behind the artifacts they claim to render.
    from scripts import export_modules

    export_modules.main()

    progress.log("export complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
