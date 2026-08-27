"""Resolve a module, validate the request, invoke the canonical code, shape the response.

The whole of the backend's decision-making is here, and it is deliberately small: this
layer decides *which* canonical function runs and *what shape* comes back, never *what it
computes*.

Execution goes down one of two paths and the response says which:

* the module declares a live analysis adapter → the adapter runs now, on the caller's
  validated inputs, and returns numbers that did not exist before the request;
* it does not → the verified artifact is replayed through a traceable endpoint, with the
  commit and run time that produced it, and the reason live execution is unavailable.

A protected module refuses. ``force`` is not a parameter of any endpoint and there is no
code path from a request to one.
"""
from __future__ import annotations

import importlib
import inspect
import json
import time
from datetime import UTC, datetime

from backend import (
    ARTIFACT,
    FAILED,
    INVALID_INPUT,
    LIVE,
    OK,
    PROTECTED,
    UNKNOWN_MODULE,
)
from backend import contract as ct
from backend import registry as reg
from backend.registry import REPO_ROOT, ModuleSpec, ValidationError

#: Where a replayed artifact may be read from. Anything outside this list is not served,
#: which is what stops a path in the manifest becoming a filesystem read primitive.
ARTIFACT_ROOTS = ("outputs", "research_artifacts", "public/data", "logs")


# ------------------------------------------------------------------ helpers ----

def _resolve(dotted: str):
    mod_name, _, func_name = dotted.partition(":")
    return getattr(importlib.import_module(mod_name), func_name)


def _rel(path: str) -> str:
    """Repository-relative, forward-slashed. Absolute paths never leave this process."""
    text = str(path).replace("\\", "/")
    root = REPO_ROOT.as_posix()
    return text[len(root) + 1:] if text.startswith(root + "/") else text


def _safe_read(rel_path: str) -> dict | None:
    """Read a JSON artifact from the allowlist, or return None."""
    clean = _rel(rel_path).lstrip("/")
    if ".." in clean or not any(clean.startswith(r) for r in ARTIFACT_ROOTS):
        return None
    p = REPO_ROOT / clean
    if not p.exists() or p.suffix != ".json":
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _limitations(spec: ModuleSpec) -> list[dict]:
    from research.limitations import registry as lr
    out = []
    for lid in spec.limitations:
        entry = lr.by_id(lid)
        out.append({"id": lid,
                    "title": entry.title if entry else "unknown limitation",
                    "scope_note": entry.scope_note if entry else "",
                    "status": entry.current_status.value if entry else "UNKNOWN"})
    return out


def _last_run(spec: ModuleSpec) -> dict | None:
    log = REPO_ROOT / "logs" / spec.category.lower() / (
        "%s.jsonl" % spec.id.lower().replace("-", "_"))
    if not log.exists():
        return None
    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return None
    try:
        last = json.loads(lines[-1])
    except ValueError:
        return None
    return {"at": last.get("ts"), "status": last.get("status"),
            "message": last.get("message"), "elapsed_s": last.get("elapsed_s"),
            "git_commit": last.get("git_commit"), "runs_recorded": len(lines)}


def _base_provenance(spec: ModuleSpec) -> dict:
    from research.core.manifest import git_commit
    return {
        "module_id": spec.id,
        "adapter": spec.adapter,
        "canonical": list(spec.canonical),
        "wrapper_status": spec.wrapper_status,
        "research_status": spec.status,
        "experiment_id": spec.experiment_id,
        "git_commit": git_commit(),
        "requested_at": datetime.now(UTC).isoformat(),
        "declared_inputs": list(spec.inputs),
        "declared_outputs": [_rel(o) for o in spec.outputs],
        "regenerate_with": "python scripts/run_module.py --module %s" % spec.id,
    }


def describe(module_id: str) -> dict:
    """Everything the interface needs to render a module's controls before running it."""
    spec = reg.module(module_id)
    if spec is None:
        return {"status": UNKNOWN_MODULE, "module_id": module_id}
    d = spec.to_dict()
    d["last_run"] = _last_run(spec)
    d["limitations"] = _limitations(spec)
    d["inputs_present"] = [
        {"path": _rel(i), "exists": (REPO_ROOT / i).exists()} for i in spec.inputs
    ]
    d["outputs_present"] = [
        {"path": _rel(o), "exists": (REPO_ROOT / o).exists()} for o in spec.outputs
    ]
    return d


# ------------------------------------------------------------------- running ----

def run_module(module_id: str, payload: dict | None = None) -> dict:
    """One module, one response.

    Never raises: a failure is a response, not a traceback.
    """
    started = time.perf_counter()
    spec = reg.module(module_id)
    if spec is None:
        return ct.Response(
            module_id=module_id, category="", name="", status=UNKNOWN_MODULE,
            mode=ARTIFACT,
            error=ct.ContractError(
                UNKNOWN_MODULE, "no module with id %r" % module_id,
                "Call GET /api/modules for the list of module identifiers."),
        ).to_dict()

    try:
        inputs = reg.validate(spec, payload)
    except ValidationError as exc:
        # The mode is the one this module *has*, not a stand-in. Reporting ARTIFACT on a
        # rejected request to a live module would say an artifact was served when nothing
        # was, and the interface would render a badge describing a replay that never
        # happened.
        return _finish(ct.Response(
            module_id=spec.id, category=spec.category, name=spec.name,
            week=spec.week, status=INVALID_INPUT,
            mode=LIVE if spec.analysis.is_live else ARTIFACT,
            inputs=dict(payload or {}),
            provenance=_base_provenance(spec),
            limitations=_limitations(spec),
            error=ct.ContractError(
                INVALID_INPUT, str(exc),
                "Correct the input and send the request again; the accepted schema is on "
                "GET /api/modules/%s." % spec.id),
        ), started)

    if spec.analysis.is_live:
        return _run_live(spec, inputs, started)
    return _replay_artifact(spec, inputs, started)


def _run_live(spec: ModuleSpec, inputs: dict, started: float) -> dict:
    try:
        fn = _resolve(spec.analysis.adapter)
    except Exception as exc:                     # noqa: BLE001 - reported, not raised
        return _finish(ct.Response(
            module_id=spec.id, category=spec.category, name=spec.name, week=spec.week,
            status=FAILED, mode=LIVE, inputs=inputs,
            provenance=_base_provenance(spec), limitations=_limitations(spec),
            error=ct.ContractError(
                FAILED, "the analysis adapter could not be imported: %s: %s"
                % (type(exc).__name__, exc),
                "This is a defect in the backend, not in your request."),
        ), started)

    try:
        result = fn(**inputs) if inspect.signature(fn).parameters else fn()
    except ValidationError as exc:
        return _finish(ct.Response(
            module_id=spec.id, category=spec.category, name=spec.name, week=spec.week,
            status=INVALID_INPUT, mode=LIVE, inputs=inputs,
            provenance=_base_provenance(spec), limitations=_limitations(spec),
            error=ct.ContractError(INVALID_INPUT, str(exc),
                                   "Adjust the selection and try again."),
        ), started)
    except Exception as exc:                     # noqa: BLE001 - reported, not raised
        return _finish(ct.Response(
            module_id=spec.id, category=spec.category, name=spec.name, week=spec.week,
            status=FAILED, mode=LIVE, inputs=inputs,
            provenance=_base_provenance(spec), limitations=_limitations(spec),
            error=ct.ContractError(
                FAILED, "%s: %s" % (type(exc).__name__, exc),
                "The canonical implementation raised. The request was not partially "
                "applied: this layer writes nothing."),
        ), started)

    return _finish(_from_analysis(spec, inputs, result), started)


def _from_analysis(spec: ModuleSpec, inputs: dict, result) -> ct.Response:
    """Shape an :class:`AnalysisResult` into the response contract."""
    provenance = _base_provenance(spec)
    provenance.update(result.provenance or {})
    provenance["computed"] = True
    provenance["execution"] = (
        "The canonical implementation named above ran during this request. No artifact "
        "was written and no stored result was read for the metrics below.")

    observations = list(result.observations)
    if spec.is_protected:
        provenance["protected_artifacts"] = [_rel(o) for o in spec.outputs]
        provenance["protection_note"] = (
            "This module's stored artifacts are protected. This analysis read the data "
            "and wrote nothing; the artifacts on disk are untouched, and regenerating "
            "them still requires a deliberate terminal command.")
        observations.append(
            "This module's published artifacts are protected. Nothing was overwritten: "
            "the analysis above wrote no file.")

    status = OK if result.ok else (result.status or FAILED)
    error = None
    if not result.ok:
        error = ct.ContractError(status, result.message,
                                 result.remedy or "See the module's declared inputs.")
    return ct.Response(
        module_id=spec.id, category=spec.category, name=spec.name, week=spec.week,
        status=status, mode=LIVE, experiment_id=spec.experiment_id,
        dataset=result.dataset, inputs=inputs,
        metrics=[ct.Metric(**m) for m in result.metrics],
        series=[ct.Series(**s) for s in result.series],
        uncertainty=result.uncertainty, observations=observations,
        figures=_figures_for(spec), tables=_tables_for(spec),
        provenance=provenance, limitations=_limitations(spec),
        message=result.message,
        error=error,
    )


def _replay_artifact(spec: ModuleSpec, inputs: dict, started: float) -> dict:
    """Serve the verified artifact, labelled as a replay and never as a computation."""
    provenance = _base_provenance(spec)
    provenance["computed"] = False

    present = [o for o in spec.outputs if (REPO_ROOT / o).exists()]
    if not present:
        reason = (spec.analysis.artifact_reason
                  or "this module computes nothing live and its artifact is absent")
        return _finish(ct.Response(
            module_id=spec.id, category=spec.category, name=spec.name, week=spec.week,
            status="INPUTS_MISSING", mode=ARTIFACT, inputs=inputs,
            provenance=provenance, limitations=_limitations(spec),
            error=ct.ContractError(
                "INPUTS_MISSING", reason,
                "Run `python scripts/run_module.py --module %s` to produce it."
                % spec.id),
        ), started)

    payloads = {}
    for rel_path in present:
        data = _safe_read(rel_path)
        if data is not None:
            payloads[_rel(rel_path)] = data

    run = _last_run(spec)
    provenance["artifacts"] = [_rel(o) for o in present]
    provenance["replayed_run_id"] = (run or {}).get("at") or "unknown"
    provenance["replayed_commit"] = (run or {}).get("git_commit")
    provenance["execution"] = (
        "Nothing was computed for this request. The values below were read from the "
        "artifact listed above, which was produced by the run identified here.")

    metrics, series = _artifact_view(spec, payloads)
    if not metrics and not series:
        # Some modules produce media directories or model bundles rather than JSON and
        # CSV. Replaying one has nothing to tabulate, but "nothing" is the wrong answer:
        # what exists on disk, how large it is and which run wrote it are exactly what a
        # reader wants from a module that cannot be re-run on request.
        metrics = _artifact_inventory(spec, present)
    status = OK
    error = None
    if spec.is_protected:
        # Not a failure: the guard working. Regeneration would overwrite an artifact the
        # claim ledger cites, and no request can authorise that.
        error = ct.ContractError(
            PROTECTED,
            "This module regenerates artifacts the claim ledger and the documentation "
            "already cite, so it will not re-run on request.",
            "The verified result is served above. Regenerating requires "
            "`python scripts/run_module.py --module %s --force` at a terminal, "
            "deliberately." % spec.id,
            {"outputs": [_rel(o) for o in spec.outputs]})

    return _finish(ct.Response(
        module_id=spec.id, category=spec.category, name=spec.name, week=spec.week,
        status=status, mode=ARTIFACT, experiment_id=spec.experiment_id,
        dataset={"source": "verified artifact", "paths": provenance["artifacts"]},
        inputs=inputs, metrics=metrics, series=series,
        uncertainty=_replay_uncertainty(provenance["artifacts"]),
        observations=[o for o in ([run.get("message")] if run else []) if o],
        figures=_figures_for(spec), tables=_tables_for(spec),
        provenance=provenance, limitations=_limitations(spec),
        message=spec.analysis.artifact_reason
        or "Verified experiment result, replayed from its artifact.",
        error=error,
    ), started)


def _replay_uncertainty(artifacts: list[str]) -> dict:
    """Say what a replay can and cannot tell you about its own precision.

    Every live module answers this: it either reports an interval or states why there
    isn't one — a count is not an estimate. A replay was answering nothing at all, so
    three of the thirty-two halves showed a reader figures with silence beside them,
    which reads identically to "this result has no uncertainty".

    It does not, and inventing one here would be worse than the silence. What this can say
    truthfully is where the answer lives: the run that produced these numbers computed
    whatever it computed, and that is in the artifacts named in the provenance rather than
    summarised for this request. `research_artifacts/statistics/uncertainty_bins.csv` is
    exactly such a file, and pointing at it is more use than an empty block.
    """
    return {
        "kind": "replayed",
        "reading": (
            "Nothing was computed for this request, so no interval was estimated for it. "
            "These are the figures the recorded run produced; whatever precision it "
            "established is in the artifacts named below (%s) rather than summarised "
            "here." % ", ".join(artifacts[:3]) if artifacts else
            "Nothing was computed for this request, so no interval was estimated for it."
        ),
    }


def _artifact_view(spec: ModuleSpec, payloads: dict) -> tuple[list, list]:
    """Turn replayed artifacts into the same metric/series shapes a live run produces."""
    from scripts.stages import fmt_value

    metrics: list[ct.Metric] = []
    series: list[ct.Series] = []
    for rel_path, data in payloads.items():
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if isinstance(value, (int, float, bool)) and not isinstance(value, bool):
                metrics.append(ct.Metric(
                    key=key, label=key.replace("_", " "), value=value,
                    display=fmt_value(value), format="auto",
                    note="read from the artifact", source=rel_path))
            elif isinstance(value, str) and len(value) < 400:
                metrics.append(ct.Metric(
                    key=key, label=key.replace("_", " "), value=value,
                    display=value, format="text",
                    note="read from the artifact", source=rel_path))
        if len(metrics) > 40:
            break

    for rel_path in spec.outputs:
        clean = _rel(rel_path)
        if not clean.endswith(".csv"):
            continue
        p = REPO_ROOT / clean
        if not p.exists() or not any(clean.startswith(r) for r in ARTIFACT_ROOTS):
            continue
        import pandas as pd
        frame = pd.read_csv(p)
        head = frame.head(50)
        series.append(ct.Series(
            key=clean, label=clean.rsplit("/", 1)[-1],
            columns=[str(c) for c in head.columns],
            rows=json.loads(head.to_json(orient="values")),
            note="read from the artifact", truncated=len(frame) > 50,
            total_rows=int(len(frame))))
    return metrics, series


def _artifact_inventory(spec: ModuleSpec, present: list[str]) -> list[ct.Metric]:
    """What the module's artifacts are, when they are not numbers to read."""
    from scripts.stages import fmt_value

    metrics = [ct.Metric(
        key="artifacts", label="Artifacts on disk", value=len(present),
        display=fmt_value(len(present), "int"), format="int",
        note="declared outputs this module has produced", source="")]
    total_files = total_bytes = 0
    for rel_path in present:
        target = REPO_ROOT / rel_path
        files = ([target] if target.is_file()
                 else [p for p in target.rglob("*") if p.is_file()])
        total_files += len(files)
        total_bytes += sum(p.stat().st_size for p in files)
        metrics.append(ct.Metric(
            key=_rel(rel_path), label=_rel(rel_path).rsplit("/", 1)[-1],
            value=len(files), display="%s file(s)" % fmt_value(len(files), "int"),
            format="int",
            note="directory" if target.is_dir() else "file",
            source=_rel(rel_path)))
    metrics.append(ct.Metric(
        key="total_files", label="Files", value=total_files,
        display=fmt_value(total_files, "int"), format="int",
        note="across every artifact above", source=""))
    metrics.append(ct.Metric(
        key="total_mb", label="Size on disk", value=total_bytes / 1e6,
        display="%.1f MB" % (total_bytes / 1e6), format="float1",
        note="what the last run of this module produced", source=""))
    return metrics


def _figures_for(spec: ModuleSpec) -> list[dict]:
    bundle = _safe_read("public/data/modules.json") or {}
    for row in bundle.get("rows", []):
        if row.get("id") == spec.id:
            return row.get("figures") or []
    return []


def _tables_for(spec: ModuleSpec) -> list[dict]:
    bundle = _safe_read("public/data/modules.json") or {}
    for row in bundle.get("rows", []):
        if row.get("id") == spec.id:
            return row.get("tables") or []
    return []


def _finish(response: ct.Response, started: float) -> dict:
    response.elapsed_s = time.perf_counter() - started
    problems = response.check()
    if problems:
        # A contract violation is a backend defect and is reported as one rather than
        # silently shipped: a response that breaks its own rules is worse than an error.
        response.status = FAILED
        response.error = ct.ContractError(
            FAILED, "the backend produced a response that violates its own contract",
            "This is a defect in the backend, not in your request.",
            {"problems": problems})
    return response.to_dict()


# ---------------------------------------------------------------- weekly view ----

def run_week(number: int, payload: dict | None = None) -> dict:
    """Orchestrate one week: its STATS module and its MULTIMODAL module, together.

    Inputs are addressed per module (``{"STATS-01": {...}, "MULTIMODAL-01": {...}}``) so
    the two halves of a week can take different parameters, which they generally do.
    Shared keys at the top level are applied to both, because a date range usually is
    shared and making the caller repeat it would be noise.
    """
    started = time.perf_counter()
    spec = reg.week(number)
    if spec is None:
        return {"status": "UNKNOWN_WEEK", "week": number,
                "error": {"code": "UNKNOWN_WEEK",
                          "reason": "no week %s in the registry" % number,
                          "remedy": "Weeks 1 to %d are defined." % len(reg.weeks())}}

    payload = dict(payload or {})
    shared = {k: v for k, v in payload.items() if not k.startswith(("STATS", "MULTI"))}
    results = {}
    for module_id in (spec.stats_module, spec.multimodal_module):
        module_spec = reg.module(module_id)
        declared = {i.name for i in module_spec.analysis.inputs} if module_spec else set()
        merged = {k: v for k, v in shared.items() if k in declared}
        merged.update(payload.get(module_id) or {})
        results[module_id] = run_module(module_id, merged)

    statuses = [r["status"] for r in results.values()]
    return {
        "backend_version": __import__("backend").BACKEND_VERSION,
        "week": spec.week,
        "title": spec.title,
        "question": spec.question,
        "summary": spec.summary,
        "stats_module": spec.stats_module,
        "multimodal_module": spec.multimodal_module,
        "status": OK if all(s == OK for s in statuses) else "PARTIAL",
        "modes": {k: v["mode"] for k, v in results.items()},
        "results": results,
        "elapsed_s": round(time.perf_counter() - started, 3),
        "reading": (
            "One week is one vertical slice: a statistical view and a modality view of "
            "the same question, executed through the same canonical implementations the "
            "research pipeline uses. Each half reports whether it computed or replayed."),
    }


def catalogue() -> dict:
    """Every module and every week, for the interface to render its navigation."""
    return {
        "backend_version": __import__("backend").BACKEND_VERSION,
        "weeks": [w.to_dict() for w in reg.weeks()],
        "modules": [m.to_dict() for m in reg.modules().values()],
        "counts": {
            "weeks": len(reg.weeks()),
            "modules": len(reg.modules()),
            "live_capable": sum(1 for m in reg.modules().values()
                                if m.analysis.is_live),
            "artifact_only": sum(1 for m in reg.modules().values()
                                 if not m.analysis.is_live),
        },
    }


def health() -> dict:
    from research.core.manifest import git_commit
    live = [m for m in reg.modules().values() if m.analysis.is_live]
    return {
        "status": "OK",
        "backend_version": __import__("backend").BACKEND_VERSION,
        "git_commit": git_commit(),
        "weeks": len(reg.weeks()),
        "modules": len(reg.modules()),
        "live_capable_modules": len(live),
        "checked_at": datetime.now(UTC).isoformat(),
    }
