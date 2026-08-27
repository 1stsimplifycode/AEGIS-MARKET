"""Export the 32 module pages the product and the research workbench both read.

    python scripts/export_modules.py

One bundle, ``public/data/modules.json``, and one copy of every figure into
``public/figures/``. Product mode and Research mode read the same records from it, which
is the property that makes them incapable of disagreeing: the difference between the two
experiences is which fields are rendered and at what depth, never which numbers exist.

Nothing here computes a research quantity. Every value is resolved from an artifact the
pipeline already wrote, through a small expression grammar declared per module in
``research_modules.yaml``:

    json:<path>#a.b.c                     a scalar at a dotted path
    json:<path>#a.b[key=value].c          a scalar inside a list, selected by a field
    csv:<path>#rows                       row count
    csv:<path>#cell:<col>=<val>:<out>     one cell, selected by a key column
    csv:<path>#count:<col>=<val>          how many rows match
    csv:<path>#agg:<col>:mean|min|max|sum a summary of one column

Formats are named per metric: ``int``, ``pct``, ``bool``, ``text``, ``count``, ``sci``,
``floatN``, and ``inr`` for a rupee figure, which is rendered in lakh and crore the way a
reader in India reads it. A currency figure never travels without the caveat its module
carries beside it.

``agg`` is the only expression that reduces anything, and it reduces a column of an
artifact for display. Everything else is a lookup. A value that cannot be resolved is
emitted as ``null`` with the reason attached, so the interface shows "not available" and
says why rather than rendering a plausible number.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from research.claims import ledger as cl  # noqa: E402
from research.core import jsonio, paths, progress  # noqa: E402
from research.core.manifest import git_commit  # noqa: E402
from research.limitations import registry as reg  # noqa: E402

R = paths.REPO_ROOT
OUT = R / "public" / "data"
FIGURE_OUT = R / "public" / "figures"
MANIFEST = R / "research_modules.yaml"

#: Categories whose modules get a page. PRODUCT, HUMAN_AFFECT and CORPUS are execution
#: layers rather than reader-facing capabilities, and their results reach the interface
#: through the modules that cite them rather than through pages of their own.
MODULE_CATEGORIES = ("STATS", "MULTIMODAL", "SCENARIO")

#: Where generated figures live. First match wins, so a figure regenerated into
#: outputs/ shadows an older copy in the paper package rather than the other way round.
FIGURE_DIRS = [
    R / "outputs" / "research_figures",
    R / "outputs" / "human_affect" / "figures",
    R / "research_artifacts" / "figures",
    R / "paper_package" / "figures",
    R / "paper_package" / "supplementary",
]

#: Module status vocabulary, translated for each audience. Product mode never sees
#: PARTIAL, because "partial" describes a research position rather than what a reader can
#: do with the module; research mode never sees VERIFIED, because that is a summary.
PRODUCT_STATUS = {
    "SUPPORTED": "VERIFIED",
    "PARTIAL": "LIMITED",
    "NOT_SUPPORTED": "LIMITED",
    "NOT SUPPORTED": "LIMITED",
    "NOT_RUN": "UNAVAILABLE",
    "NOT RUN": "UNAVAILABLE",
    "NOT_MEASURED": "UNAVAILABLE",
    "NOT MEASURED": "UNAVAILABLE",
    "BLOCKED": "UNAVAILABLE",
    "OPEN QUESTION": "EXPERIMENTAL",
    "FUTURE VALIDATION": "EXPERIMENTAL",
    "FAILED SANITY CHECK": "LIMITED",
}


class Unresolved(Exception):
    """Raised when an expression names something an artifact does not contain."""


# ------------------------------------------------------------------- resolution ----

_LIST_SELECTOR = re.compile(r"^(?P<name>[^\[]+)\[(?P<key>[^=]+)=(?P<val>[^\]]+)\]$")

_JSON_CACHE: dict[Path, object] = {}
_CSV_CACHE: dict[Path, pd.DataFrame] = {}


def _load_json(path: Path):
    if path not in _JSON_CACHE:
        if not path.exists():
            raise Unresolved("artifact not found: %s" % path.relative_to(R).as_posix())
        _JSON_CACHE[path] = json.loads(path.read_text(encoding="utf-8"))
    return _JSON_CACHE[path]


def _load_csv(path: Path) -> pd.DataFrame:
    if path not in _CSV_CACHE:
        if not path.exists():
            raise Unresolved("artifact not found: %s" % path.relative_to(R).as_posix())
        _CSV_CACHE[path] = pd.read_csv(path)
    return _CSV_CACHE[path]


def _walk_json(payload, dotted: str):
    node = payload
    for part in dotted.split("."):
        sel = _LIST_SELECTOR.match(part)
        if sel:
            name, key, val = sel["name"], sel["key"], sel["val"]
            if name:
                node = _index(node, name)
            if not isinstance(node, list):
                raise Unresolved("%s is not a list" % name)
            match = next((x for x in node
                          if isinstance(x, dict) and str(x.get(key)) == val), None)
            if match is None:
                raise Unresolved("no element with %s=%s" % (key, val))
            node = match
        else:
            node = _index(node, part)
    return node


def _index(node, key: str):
    if isinstance(node, dict):
        if key not in node:
            raise Unresolved("key %r absent" % key)
        return node[key]
    raise Unresolved("cannot index %s with %r" % (type(node).__name__, key))


def _resolve_csv(path: Path, expr: str):
    frame = _load_csv(path)
    if expr == "rows":
        return int(len(frame))
    if expr.startswith("cell:"):
        selector, out_col = expr[len("cell:"):].rsplit(":", 1)
        col, val = selector.split("=", 1)
        if col not in frame.columns or out_col not in frame.columns:
            raise Unresolved("column %r or %r absent" % (col, out_col))
        hit = frame[frame[col].astype(str) == val]
        if hit.empty:
            raise Unresolved("no row with %s=%s" % (col, val))
        return hit.iloc[0][out_col]
    if expr.startswith("count:"):
        col, val = expr[len("count:"):].split("=", 1)
        if col not in frame.columns:
            raise Unresolved("column %r absent" % col)
        return int((frame[col].astype(str) == val).sum())
    if expr.startswith("agg:"):
        col, how = expr[len("agg:"):].split(":", 1)
        if col not in frame.columns:
            raise Unresolved("column %r absent" % col)
        series = pd.to_numeric(frame[col], errors="coerce").dropna()
        if series.empty:
            raise Unresolved("column %r has no numeric values" % col)
        return float(getattr(series, how)())
    raise Unresolved("unknown csv expression %r" % expr)


def resolve(expression: str):
    """Return (value, source) for one declared expression."""
    kind, rest = expression.split(":", 1)
    rel, expr = rest.split("#", 1)
    path = R / rel
    if kind == "json":
        return _walk_json(_load_json(path), expr), rel
    if kind == "csv":
        return _resolve_csv(path, expr), rel
    raise Unresolved("unknown expression kind %r" % kind)


def _numeric(value):
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out and abs(out) != float("inf") else None


def render(value, fmt: str) -> str:
    """Format for display. The raw value travels beside it, so nothing is lost."""
    if fmt == "count":
        return str(len(value)) if isinstance(value, (list, dict)) else str(value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if fmt == "bool":
        return "yes" if value else "no"
    if fmt == "text":
        return str(value)
    num = _numeric(value)
    if num is None:
        return str(value)
    if fmt == "int":
        return "{:,}".format(int(round(num)))
    if fmt == "pct":
        return "%.1f%%" % (num * 100)
    if fmt == "sci":
        return "%.2e" % num
    if fmt == "inr":
        from research.scenario.money import inr
        return inr(num)
    if fmt.startswith("float"):
        return "%.*f" % (int(fmt[5:] or 3), num)
    return str(value)


def metric(spec: dict) -> dict:
    """Resolve one declared metric into a record both experiences render."""
    out = {"label": spec["label"], "format": spec["format"],
           "note": spec.get("note"), "expression": spec["value"]}
    try:
        value, source = resolve(spec["value"])
    except Unresolved as exc:
        out.update({"value": None, "display": None, "source": None,
                    "unavailable": str(exc)})
        return out
    if isinstance(value, (list, dict)) and spec["format"] != "count":
        out.update({"value": None, "display": None, "source": source,
                    "unavailable": "expression resolved to a container, not a value"})
        return out
    display = render(value, spec["format"])
    raw = value if not isinstance(value, (list, dict)) else len(value)
    out.update({"value": _numeric(raw) if not isinstance(raw, str) else raw,
                "display": display, "source": source, "unavailable": None})
    return out


# ------------------------------------------------------------------- assembling ----

def last_run(module_id: str, category: str, index: int) -> dict | None:
    log = R / "logs" / category.lower() / ("%s_%02d.jsonl" % (category.lower(), index))
    if not log.exists():
        return None
    entries = [json.loads(line) for line in
               log.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not entries:
        return None
    last = entries[-1]
    return {
        "at": last.get("ts"),
        "status": last.get("status"),
        "message": last.get("message"),
        "elapsed_s": last.get("elapsed_s"),
        "git_commit": last.get("git_commit"),
        "runs_recorded": len(entries),
    }


def limitation_records(ids: list[str]) -> list[dict]:
    out = []
    for lid in ids or []:
        entry = reg.by_id(lid)
        out.append({
            "id": lid,
            "title": entry.title if entry else "unknown limitation",
            "scope_note": entry.scope_note if entry else "",
            "status": entry.current_status.value if entry else "UNKNOWN",
            "description": entry.description if entry else "",
        })
    return out


def claims_for(module_id: str, figures: list[str], tables: list[str]) -> list[dict]:
    """Claims this module's evidence appears in, matched by figure, table or experiment.

    Matching on the artifacts rather than on a hand-maintained list, so a claim that
    starts citing a figure automatically starts appearing on the module that produced it.
    """
    out = []
    for c in cl.CLAIMS:
        hit = (set(c.figure_ids) & set(figures)) or (set(c.table_ids) & set(tables)) \
            or module_id in c.experiment
        if not hit:
            continue
        out.append({
            "id": c.id, "claim": c.claim, "status": c.status.value,
            "scope": cl.SCOPE_LABEL[c.scope], "evidence": c.evidence,
            "statistical_test": c.statistical_test, "metric": c.metric,
            "dataset": c.dataset, "experiment": c.experiment,
            "artifacts": c.evidence_artifact,
            "limitations": c.limitations,
        })
    return out


def figure_records(names: list[str], index: dict[str, dict]) -> list[dict]:
    out = []
    for name in names:
        rec = index.get(name)
        out.append(rec if rec else {
            "figure": name, "available": False, "url": None,
            "caption": "Not present in the generated figure set.",
            "source_data": None,
        })
    return out


def table_records(names: list[str], index: dict[str, dict]) -> list[dict]:
    out = []
    for name in names:
        rec = index.get(name)
        out.append(rec if rec else {
            "table": name, "available": False, "caption":
            "Not present in the generated table set.", "source": None, "rows": None,
        })
    return out


def build_figure_index() -> dict[str, dict]:
    """Copy every generated figure into public/ and index it by name."""
    FIGURE_OUT.mkdir(parents=True, exist_ok=True)
    captions: dict[str, dict] = {}
    for rel in ("outputs/research_figures/figures.json",
                "outputs/human_affect/figures/figures.json"):
        p = R / rel
        if not p.exists():
            continue
        payload = json.loads(p.read_text(encoding="utf-8"))
        for f in payload.get("figures", []):
            captions[f["figure"]] = {"caption": f.get("caption"),
                                     "source_data": f.get("source_data"),
                                     "git_commit": payload.get("git_commit")}

    index: dict[str, dict] = {}
    for directory in FIGURE_DIRS:
        if not directory.exists():
            continue
        for png in sorted(directory.glob("*.png")):
            if png.stem in index:
                continue
            shutil.copyfile(png, FIGURE_OUT / png.name)
            meta = captions.get(png.stem, {})
            index[png.stem] = {
                "figure": png.stem,
                "available": True,
                "url": "/figures/%s" % png.name,
                "caption": meta.get("caption")
                           or "Generated figure; caption recorded in the paper package.",
                "source_data": meta.get("source_data"),
                "source_dir": directory.relative_to(R).as_posix(),
                "git_commit": meta.get("git_commit"),
                "bytes": png.stat().st_size,
            }
    return index


def build_table_index() -> dict[str, dict]:
    index: dict[str, dict] = {}
    for rel, directory in (("outputs/paper_tables/tables.json", "outputs/paper_tables"),):
        p = R / rel
        if not p.exists():
            continue
        payload = json.loads(p.read_text(encoding="utf-8"))
        for t in payload.get("tables", []):
            csv_path = R / directory / ("%s.csv" % t["table"])
            index[t["table"]] = {
                "table": t["table"], "available": csv_path.exists(),
                "caption": t.get("caption"), "source": t.get("source"),
                "rows": t.get("rows"),
                "path": "%s/%s.csv" % (directory, t["table"]),
                "git_commit": payload.get("git_commit"),
                "columns": list(pd.read_csv(csv_path).columns) if csv_path.exists()
                           else [],
            }
    # Stream A tables live as loose CSVs beside their captions.
    tdir = R / "research_artifacts" / "tables"
    if tdir.exists():
        for csv_path in sorted(tdir.glob("*.csv")):
            if csv_path.stem in index:
                continue
            # The sidecar is sometimes the table's own rows and sometimes a metadata
            # object; only the second carries a caption.
            meta_path = csv_path.with_suffix(".json")
            caption = None
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    meta = None
                if isinstance(meta, dict):
                    caption = meta.get("caption")
            index[csv_path.stem] = {
                "table": csv_path.stem, "available": True, "caption": caption,
                "source": "research_artifacts/tables", "rows": None,
                "path": csv_path.relative_to(R).as_posix(), "git_commit": None,
                "columns": list(pd.read_csv(csv_path).columns),
            }
    return index


def preview(rel: str, limit: int = 60) -> dict | None:
    """A bounded preview of a tabular artifact, for the research table view."""
    path = R / rel
    if not path.exists() or path.suffix != ".csv":
        return None
    frame = pd.read_csv(path)
    head = frame.head(limit)
    return {
        "columns": [str(c) for c in head.columns],
        "rows": json.loads(head.to_json(orient="values")),
        "total_rows": int(len(frame)),
        "truncated": bool(len(frame) > limit),
        "path": rel,
    }


MEDIA_TYPES = {".png": "image", ".jpg": "image", ".jpeg": "image",
               ".wav": "audio", ".mp3": "audio", ".mp4": "video", ".webm": "video"}


def copy_media() -> dict[str, list[dict]]:
    """Copy the generated media assets into public/ and index them by source directory.

    Only assets this project generated. Nothing third-party is copied: where
    redistribution is not permitted the pipeline stores reference metadata instead of
    media, and those reference files stay where they are.
    """
    src_root = R / "data" / "media"
    out_root = R / "public" / "media"
    index: dict[str, list[dict]] = {}
    if not src_root.exists():
        return index
    for sub in sorted(src_root.iterdir()):
        if not sub.is_dir() or sub.name == "references":
            continue
        target = out_root / sub.name
        target.mkdir(parents=True, exist_ok=True)
        rows = []
        for asset in sorted(sub.iterdir()):
            kind = MEDIA_TYPES.get(asset.suffix.lower())
            if not kind:
                continue
            shutil.copyfile(asset, target / asset.name)
            rows.append({
                "name": asset.name, "kind": kind,
                "url": "/media/%s/%s" % (sub.name, asset.name),
                "bytes": asset.stat().st_size,
                "source": asset.relative_to(R).as_posix(),
            })
        if rows:
            index[sub.as_posix().replace(R.as_posix() + "/", "")] = rows
    return index


def module_record(mod: dict, figures: dict, tables: dict, media: dict) -> dict:
    ui = mod["ui"]
    fig_names = ui.get("figures") or []
    tab_names = ui.get("tables") or []
    outputs = list(mod.get("outputs") or [])

    # Preview the module's own outputs, and also the tables its metrics read from. A
    # module whose declared output is a parquet still has a story to tell, and it is the
    # story its own metric expressions already point at.
    referenced = [m["value"].split(":", 1)[1].split("#", 1)[0]
                  for m in (ui.get("product_metrics") or [])
                  + (ui.get("research_metrics") or [])
                  if m["value"].startswith("csv:")]
    seen, ordered = set(), []
    for rel in outputs + referenced:
        if rel not in seen:
            seen.add(rel)
            ordered.append(rel)
    previews = [p for p in (preview(rel) for rel in ordered) if p]

    module_media = [asset for out in outputs for asset in media.get(out, [])]

    product_metrics = [metric(m) for m in ui.get("product_metrics") or []]
    research_metrics = [metric(m) for m in ui.get("research_metrics") or []]
    unavailable = [m for m in product_metrics + research_metrics if m["unavailable"]]

    run = last_run(mod["id"], mod["category"], mod["index"])
    status = mod["status"]
    product_status = PRODUCT_STATUS.get(status, "EXPERIMENTAL")
    if not any((R / o).exists() for o in outputs):
        product_status = "UNAVAILABLE"

    return {
        "id": mod["id"],
        "category": mod["category"],
        "index": mod["index"],
        "slug": mod["slug"],
        "name": mod["name"],
        # Both names travel. The research name is what a citation uses; the product name
        # is what someone who has never read the manifest can act on. Neither replaces
        # the other, and the id stays the id.
        "product_name": ui.get("product_name") or mod["name"],
        "route": ui["route"],
        "icon": ui["icon"],

        "product": {
            "headline": ui["product_headline"],
            "question": ui["product_question"],
            "actions": ui.get("product_actions") or [],
            "observation": ui["product_observation"],
            "risk": ui["product_risk"],
            "confidence": ui["confidence"],
            "status": product_status,
            "visual": ui["visual"],
            "metrics": product_metrics,
            "inputs": ui.get("inputs") or [],
            "media": module_media,
        },

        "research": {
            "status": status,
            "wrapper_status": mod["wrapper_status"],
            "purpose": mod["purpose"].strip(),
            "research_question": mod["research_question"].strip(),
            "notes": (mod.get("notes") or "").strip(),
            "experiment_id": mod.get("experiment_id"),
            "adapter": mod["adapter"],
            "canonical": mod.get("canonical") or [],
            "inputs": mod.get("inputs") or [],
            "outputs": outputs,
            "depends_on": mod.get("depends_on") or [],
            "metrics": research_metrics,
            "previews": previews,
            "limitations": limitation_records(mod.get("limitations") or []),
            "claims": claims_for(mod["id"], fig_names, tab_names),
            "last_run": run,
        },

        "figures": figure_records(fig_names, figures),
        "tables": table_records(tab_names, tables),
        "unavailable_metrics": [
            {"label": m["label"], "reason": m["unavailable"],
             "expression": m["expression"]} for m in unavailable
        ],
    }


# ------------------------------------------------------------------ scenario lab ----

SCENARIO_DIR = ("outputs", "scenario")


def _scenario_rows(name: str) -> list[dict]:
    frame = _CSV_CACHE.get(R.joinpath(*SCENARIO_DIR, name))
    if frame is None:
        path = R.joinpath(*SCENARIO_DIR, name)
        if not path.exists():
            return []
        frame = pd.read_csv(path)
        _CSV_CACHE[path] = frame
    return json.loads(frame.to_json(orient="records"))


def build_scenarios() -> dict:
    """The Scenario Lab bundle: the catalogue, the outcomes, and the caveats.

    Product mode and Research mode read this same record, exactly as the module pages do.
    The catalogue travels with the results rather than beside them, because a scenario
    outcome shown without its assumption is the one thing this whole track exists to
    prevent.
    """
    catalogue = _safe_json(*SCENARIO_DIR, "scenario_catalogue.json")
    results = _safe_json(*SCENARIO_DIR, "scenario_results.json")
    corpus = _safe_json(*SCENARIO_DIR, "transaction_corpus_search.json")

    specs = {s["scenario_id"]: s for s in (catalogue or {}).get("scenarios", [])}
    comparison = _scenario_rows("scenario_comparison.csv")
    for row in comparison:
        row["spec"] = specs.get(row.get("scenario_id"))

    return {
        "available": bool(catalogue and comparison),
        "scenario_version": (catalogue or {}).get("scenario_version"),
        "run_at": (results or {}).get("run_at"),
        "git_commit": (results or {}).get("git_commit"),
        "seeds": (results or {}).get("seeds", []),
        "notional": (results or {}).get("notional", {}),
        "catalogue": list(specs.values()),
        "comparison": comparison,
        "uncertainty": _scenario_rows("scenario_uncertainty.csv"),
        "money": _scenario_rows("scenario_money.csv"),
        "ablation": _scenario_rows("scenario_ablation.csv"),
        "robustness": _scenario_rows("scenario_robustness.csv"),
        "transaction_corpus": corpus,
        "n_failed": (results or {}).get("n_failed", 0),
        "problems": (results or {}).get("problems", []),
        "reading": (
            "Three simulation methods, and they mean different things. An observed "
            "stratum selects rows that occurred. A counterfactual alters rows under a "
            "stated assumption and nothing in it happened. A policy comparison changes a "
            "declared rule on identical evidence. Every currency figure is a simulated "
            "quantity on a declared notional base; none of it is money that moved."),
        "not_available_note": (
            "Run python scripts/run_scenarios.py, then python "
            "scripts/export_modules.py, to populate the Scenario Lab."),
    }


def _safe_json(*parts) -> dict | None:
    p = R.joinpath(*parts)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


# ------------------------------------------------------------------------ main ----

def build_weeks(generated_at: str) -> dict:
    """Export the weekly registry so the interface can render controls without Python.

    The schema a form draws itself from and the schema the backend validates against have
    to be the same schema, or a caller can be shown a field the service will reject. Both
    come from :func:`backend.registry.week_payload`, and this file is written from it
    rather than restated by hand.

    Only the schema travels. Running still requires the backend; a deployment without one
    can render the controls and say plainly that execution is unavailable, which is a
    different thing from pretending a stored number was just computed.
    """
    from backend import registry as reg

    rows = [reg.week_payload(w.week) for w in reg.weeks()]
    live = sum(1 for r in rows for e in r["execution"].values() if e["is_live"])
    return {
        "generated_at": generated_at,
        "git_commit": git_commit(),
        "meta": {
            "n_weeks": len(rows),
            "n_live_capable": live,
            "n_artifact_only": sum(len(r["execution"]) for r in rows) - live,
            "output_schema": list(reg.OUTPUT_SCHEMA),
        },
        "rows": rows,
    }


def write_bundle(path: Path, payload: dict) -> None:
    """Write an exported bundle through the shared no-absolute-paths writer."""
    jsonio.write_public(path, payload, log=progress.log)


def main() -> int:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    progress.log("[module export]")

    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    figures = build_figure_index()
    tables = build_table_index()
    media = copy_media()
    progress.log("      %d figures copied, %d tables indexed, %d media directories"
                 % (len(figures), len(tables), len(media)))

    records = [module_record(m, figures, tables, media) for m in manifest["modules"]
               if m["category"] in MODULE_CATEGORIES and "ui" in m]
    records.sort(key=lambda r: (r["category"], r["index"]))

    unresolved = [(r["id"], u) for r in records for u in r["unavailable_metrics"]]
    for mid, u in unresolved:
        progress.log("      UNRESOLVED %s %s: %s" % (mid, u["label"], u["reason"]))

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit(),
        "meta": {
            "n_modules": len(records),
            "by_category": {c: sum(1 for r in records if r["category"] == c)
                            for c in MODULE_CATEGORIES},
            "n_figures": len(figures),
            "n_tables": len(tables),
            "n_media_assets": sum(len(v) for v in media.values()),
            "n_unresolved_metrics": len(unresolved),
            "manifest_version": manifest["version"],
        },
        "rows": records,
    }
    write_bundle(OUT / "modules.json", payload)

    write_bundle(OUT / "figures_index.json", {
        "generated_at": payload["generated_at"],
        "meta": {"n": len(figures)},
        "rows": sorted(figures.values(), key=lambda f: f["figure"]),
    })
    scenarios = build_scenarios()
    write_bundle(OUT / "scenarios.json", {
        "generated_at": payload["generated_at"],
        # Nested under `meta` because that is the field the app's bundle reader keeps;
        # a sibling key would be silently dropped on the way in.
        "meta": {"available": scenarios["available"],
                 "n_scenarios": len(scenarios["catalogue"]),
                 "n_compared": len(scenarios["comparison"]),
                 "run_at": scenarios["run_at"],
                 "scenario_lab": scenarios},
        "rows": scenarios["comparison"],
    })
    progress.log("      scenario lab: %d scenarios, %d compared"
                 % (len(scenarios["catalogue"]), len(scenarios["comparison"])))

    write_bundle(OUT / "weeks.json", build_weeks(payload["generated_at"]))

    # A listing of the modules, carrying no result of any kind.
    #
    # `modules.json` holds every module's exported metrics and series, which is what the
    # module pages need. A page that only lists what exists does not, and reading the full
    # bundle to build a list of names puts every module's numbers into that page's payload
    # — including the weeks the demonstration has not reached.
    write_bundle(OUT / "module_index.json", {
        "generated_at": payload["generated_at"],
        "rows": [
            {"id": m["id"], "index": m["index"], "category": m["category"],
             "name": m["name"], "slug": m["slug"], "route": m["route"],
             "icon": m.get("icon"),
             "product_name": m.get("product_name"),
             "product_question": ((m.get("product") or {}).get("question")
                                  or m.get("product_question") or "")}
            for m in payload["rows"]
        ],
    })

    # Week names only — no feature declarations, no metric keys, no series.
    #
    # The gated page has to name a week it is withholding. Reading the full weekly
    # registry to do that means the development server streams that whole file into the
    # page's own payload, so a page whose entire job is to withhold week 16 ends up
    # carrying week 16's headline metrics and visual declarations. Production does not
    # do this, but the weekly launcher runs the development server, which is where the
    # demonstration happens. A separate small bundle removes the possibility rather
    # than relying on the bundler to drop it.
    write_bundle(OUT / "week_titles.json", {
        "generated_at": payload["generated_at"],
        "rows": [
            {"week": w["week"], "title": w["title"], "question": w["question"],
             "route": "/weeks/%d" % w["week"]}
            for w in build_weeks(payload["generated_at"])["rows"]
        ],
    })

    # The product's own vocabulary, and when each part joins the demonstration. Exported
    # with no active week baked in: which of these are locked depends on the week a run is
    # started at, and that is decided per request rather than at build time.
    from backend import capability as cap
    write_bundle(OUT / "capabilities.json", {
        "generated_at": payload["generated_at"],
        "last_week": cap.last_week(),
        # `rows`, like every other bundle: one envelope means one reader and one test.
        "rows": [
            {"id": c.id, "name": c.name, "href": c.href,
             "enabled_from_week": c.enabled_from_week, "summary": c.summary,
             "surfaces": list(c.surfaces)}
            for c in cap.product_capabilities()
        ],
    })

    write_bundle(OUT / "tables_index.json", {
        "generated_at": payload["generated_at"],
        "meta": {"n": len(tables)},
        "rows": sorted(tables.values(), key=lambda t: t["table"]),
    })

    progress.log("wrote %d modules, %d unresolved metrics"
                 % (len(records), len(unresolved)))
    progress.log("elapsed %.1fs" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
