"""What the backend knows, all of it read from ``research_modules.yaml``.

The manifest is already the single source of truth for the modules; the week pairing, the
input schema and the execution mode are declared there too rather than in a second table
the backend keeps for itself. A second table is a second thing to drift.

Input validation lives here because it is the boundary: everything past this point is a
dict of primitives that has been range-checked against a declared schema. Nothing a caller
sends reaches a shell, a path join, or an ``eval``.
"""
from __future__ import annotations

import datetime as dt
import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "research_modules.yaml"

#: Categories the weekly programme pairs. SCENARIO, PRODUCT, HUMAN_AFFECT and CORPUS are
#: reachable as modules but are not part of the sixteen-week pairing.
WEEKLY_CATEGORIES = ("STATS", "MULTIMODAL")


class ValidationError(ValueError):
    """A caller's input did not satisfy the declared schema."""


@dataclass(frozen=True)
class InputSpec:
    name: str
    kind: str
    label: str
    default: Any = None
    note: str = ""
    options: list[str] = field(default_factory=list)
    minimum: Any = None
    maximum: Any = None
    max_items: int | None = None
    required: bool = False

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "label": self.label,
                "default": self.default, "note": self.note,
                "options": list(self.options), "minimum": self.minimum,
                "maximum": self.maximum, "max_items": self.max_items,
                "required": self.required}


@dataclass(frozen=True)
class Analysis:
    """How a module can be executed live, if it can be."""

    adapter: str | None
    mode: str
    typical_seconds: float
    summary: str
    inputs: tuple[InputSpec, ...] = ()
    #: Why this module cannot compute live, when it cannot. Shown to the caller verbatim.
    artifact_reason: str = ""

    @property
    def is_live(self) -> bool:
        return self.mode == "LIVE" and bool(self.adapter)

    def to_dict(self) -> dict:
        return {"mode": self.mode, "is_live": self.is_live,
                # The analysis adapter, which is deliberately not the module's
                # regenerating adapter: one reads and returns, the other writes.
                "adapter": self.adapter,
                "typical_seconds": self.typical_seconds, "summary": self.summary,
                "inputs": [i.to_dict() for i in self.inputs],
                "artifact_reason": self.artifact_reason}


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    index: int
    category: str
    slug: str
    name: str
    purpose: str
    research_question: str
    adapter: str
    wrapper_status: str
    status: str
    experiment_id: str | None
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    canonical: tuple[str, ...]
    limitations: tuple[str, ...]
    notes: str
    route: str
    icon: str
    #: What the product calls this module. The identifier stays the identifier.
    product_name: str
    analysis: Analysis
    week: int | None

    @property
    def is_protected(self) -> bool:
        return self.wrapper_status == "WRAPS_EXISTING_PROTECTED"

    def to_dict(self) -> dict:
        return {
            "module_id": self.id, "index": self.index, "category": self.category,
            "slug": self.slug, "name": self.name, "purpose": self.purpose,
            "research_question": self.research_question,
            "adapter": self.adapter, "wrapper_status": self.wrapper_status,
            "status": self.status, "experiment_id": self.experiment_id,
            "declared_inputs": list(self.inputs), "outputs": list(self.outputs),
            "canonical": list(self.canonical), "limitations": list(self.limitations),
            "notes": self.notes, "route": self.route, "icon": self.icon,
            "product_name": self.product_name or self.name,
            "week": self.week, "protected": self.is_protected,
            "analysis": self.analysis.to_dict(),
        }


@dataclass(frozen=True)
class WeekSpec:
    week: int
    title: str
    question: str
    stats_module: str
    multimodal_module: str
    summary: str
    #: What the week *shows*: the headline figures, the primary series, and the question
    #: it answers in a reader's words. Declared in the manifest rather than decided in a
    #: component, so a headline naming a metric the module stopped returning fails a test
    #: instead of rendering an empty card.
    feature: dict = field(default_factory=dict)
    #: When this week's capability becomes visible, and what to call it. Declared beside
    #: the modules it gates so the unlock order is readable in one place; `capability.py`
    #: is what enforces it.
    gate: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"week": self.week, "title": self.title, "question": self.question,
                "stats_module": self.stats_module,
                "multimodal_module": self.multimodal_module, "summary": self.summary,
                "feature": dict(self.feature), "gate": dict(self.gate)}


# ------------------------------------------------------------------- loading ----

@functools.lru_cache(maxsize=1)
def _manifest() -> dict:
    import yaml
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def _analysis_of(raw: dict) -> Analysis:
    a = raw.get("analysis") or {}
    specs = tuple(
        InputSpec(
            name=i["name"], kind=i["kind"], label=i["label"],
            default=i.get("default"), note=i.get("note", ""),
            options=list(i.get("options") or []),
            minimum=i.get("minimum"), maximum=i.get("maximum"),
            max_items=i.get("max_items"), required=bool(i.get("required", False)),
        )
        for i in (a.get("inputs") or [])
    )
    return Analysis(
        adapter=a.get("adapter"),
        mode=a.get("mode", "ARTIFACT"),
        typical_seconds=float(a.get("typical_seconds", 0.0)),
        summary=a.get("summary", ""),
        inputs=specs,
        artifact_reason=a.get("artifact_reason", ""),
    )


@functools.lru_cache(maxsize=1)
def weeks() -> tuple[WeekSpec, ...]:
    raw = _manifest().get("weeks") or []
    return tuple(WeekSpec(week=int(w["week"]), title=w["title"], question=w["question"],
                          stats_module=w["stats_module"],
                          multimodal_module=w["multimodal_module"],
                          summary=w.get("summary", ""),
                          feature=dict(w.get("feature") or {}),
                          gate=dict(w.get("gate") or {}))
                 for w in sorted(raw, key=lambda w: int(w["week"])))


@functools.lru_cache(maxsize=1)
def modules() -> dict[str, ModuleSpec]:
    week_of: dict[str, int] = {}
    for w in weeks():
        week_of[w.stats_module] = w.week
        week_of[w.multimodal_module] = w.week

    out: dict[str, ModuleSpec] = {}
    for raw in _manifest()["modules"]:
        ui = raw.get("ui") or {}
        out[raw["id"]] = ModuleSpec(
            id=raw["id"], index=int(raw["index"]), category=raw["category"],
            slug=raw["slug"], name=raw["name"],
            purpose=(raw.get("purpose") or "").strip(),
            research_question=(raw.get("research_question") or "").strip(),
            adapter=raw["adapter"], wrapper_status=raw["wrapper_status"],
            status=raw["status"], experiment_id=raw.get("experiment_id"),
            inputs=tuple(raw.get("inputs") or []),
            outputs=tuple(raw.get("outputs") or []),
            canonical=tuple(raw.get("canonical") or []),
            limitations=tuple(raw.get("limitations") or []),
            notes=(raw.get("notes") or "").strip(),
            route=ui.get("route", ""), icon=ui.get("icon", ""),
            product_name=ui.get("product_name", "") or raw["name"],
            analysis=_analysis_of(raw),
            week=week_of.get(raw["id"]),
        )
    return out


def module(module_id: str) -> ModuleSpec | None:
    return modules().get((module_id or "").strip().upper())


def week(number: int) -> WeekSpec | None:
    return next((w for w in weeks() if w.week == number), None)


def weekly_modules(number: int) -> list[ModuleSpec]:
    w = week(number)
    if w is None:
        return []
    return [m for m in (module(w.stats_module), module(w.multimodal_module)) if m]


#: The response envelope every module run returns, whatever it computed. Declared once
#: here so a week can publish its output schema without a second copy going stale.
OUTPUT_SCHEMA = (
    "backend_version", "module_id", "week", "category", "name", "status", "mode",
    "mode_label", "mode_meaning", "experiment_id", "dataset", "inputs", "metrics",
    "series", "uncertainty", "observations", "figures", "tables", "provenance",
    "limitations", "message", "elapsed_s", "error",
)


def week_payload(number: int) -> dict | None:
    """A week as the interface consumes it.

    Routes, schemas, views and artifact sources are *derived* from the two named modules
    rather than restated in the manifest. Restating them would let a week advertise an
    endpoint, a parameter or an artifact its modules do not have, and the first person to
    notice would be a user looking at an empty panel.
    """
    w = week(number)
    if w is None:
        return None
    mods = weekly_modules(number)
    out = w.to_dict()
    out["backend_routes"] = {
        "week": "/api/weeks/%d" % w.week,
        "run_week": "/api/weeks/%d/run" % w.week,
        "modules": {m.id: "/api/modules/%s" % m.id for m in mods},
        "run_module": {m.id: "/api/modules/%s/run" % m.id for m in mods},
    }
    out["input_schema"] = {
        m.id: [i.to_dict() for i in m.analysis.inputs] for m in mods
    }
    out["output_schema"] = list(OUTPUT_SCHEMA)
    out["product_view"] = {m.id: "%s?mode=product" % m.route for m in mods if m.route}
    out["research_view"] = {m.id: "%s?mode=research" % m.route for m in mods if m.route}
    out["route"] = "/weeks/%d" % w.week
    out["artifact_sources"] = {m.id: list(m.outputs) for m in mods}
    out["execution"] = {
        m.id: {"mode": m.analysis.mode, "is_live": m.analysis.is_live,
               "protected": m.is_protected,
               "typical_seconds": m.analysis.typical_seconds,
               "artifact_reason": m.analysis.artifact_reason}
        for m in mods
    }
    out["modules"] = [m.to_dict() for m in mods]
    return out


# ---------------------------------------------------------------- validation ----

#: Upper bounds on anything a caller can ask for, so a request cannot become a denial of
#: service by asking for a hundred thousand documents.
LIMITS = {
    "sample_size": 5000,
    "instruments": 60,
    "bins": 50,
    "arms": 40,
    "text_length": 20000,
}


def validate(spec: ModuleSpec, payload: dict | None) -> dict:
    """Coerce and range-check a request against the module's declared input schema.

    Unknown keys are rejected rather than ignored: a caller who misspells a parameter
    should be told, not silently given the default.
    """
    payload = dict(payload or {})
    declared = {i.name: i for i in spec.analysis.inputs}
    unknown = sorted(set(payload) - set(declared))
    if unknown:
        raise ValidationError(
            "unknown input(s) %s; this module accepts %s"
            % (", ".join(unknown), ", ".join(sorted(declared)) or "no inputs"))

    out: dict = {}
    for name, i in declared.items():
        raw = payload.get(name, i.default)
        if raw is None or raw == "":
            if i.required:
                raise ValidationError("%s is required" % i.label)
            continue
        out[name] = _coerce(i, raw)
    return out


def _coerce(i: InputSpec, raw: Any) -> Any:      # noqa: C901 - one branch per kind
    kind = i.kind
    if kind == "date":
        value = _as_date(i, raw)
        if i.minimum and value < _as_date(i, i.minimum):
            raise ValidationError("%s is before the earliest available date %s"
                                  % (i.label, i.minimum))
        if i.maximum and value > _as_date(i, i.maximum):
            raise ValidationError("%s is after the latest available date %s"
                                  % (i.label, i.maximum))
        return value.isoformat()

    if kind in ("int", "float"):
        try:
            value = int(raw) if kind == "int" else float(raw)
        except (TypeError, ValueError) as exc:
            raise ValidationError("%s must be a number" % i.label) from exc
        if i.minimum is not None and value < i.minimum:
            raise ValidationError("%s must be at least %s" % (i.label, i.minimum))
        if i.maximum is not None and value > i.maximum:
            raise ValidationError("%s must be at most %s" % (i.label, i.maximum))
        return value

    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        if str(raw).lower() in ("true", "1", "yes"):
            return True
        if str(raw).lower() in ("false", "0", "no"):
            return False
        raise ValidationError("%s must be true or false" % i.label)

    if kind == "select":
        value = str(raw)
        if i.options and value not in i.options:
            raise ValidationError("%s must be one of: %s"
                                  % (i.label, ", ".join(i.options)))
        return value

    if kind == "multiselect":
        values = _as_list(i, raw)
        if i.options:
            bad = [v for v in values if v not in i.options]
            if bad:
                raise ValidationError("%s: unknown option(s) %s"
                                      % (i.label, ", ".join(bad)))
        cap = i.max_items or LIMITS["instruments"]
        if len(values) > cap:
            raise ValidationError("%s accepts at most %d values" % (i.label, cap))
        return values

    if kind == "symbols":
        values = _as_list(i, raw)
        cap = i.max_items or LIMITS["instruments"]
        if len(values) > cap:
            raise ValidationError("%s accepts at most %d instruments" % (i.label, cap))
        for v in values:
            if not v.replace("&", "").replace("-", "").isalnum() or len(v) > 24:
                raise ValidationError("%r is not a valid instrument symbol" % v)
        return [v.upper() for v in values]

    if kind in ("text", "document"):
        # `document` differs from `text` only in how the interface offers it: a file
        # picker beside the box. What arrives is a string either way, capped the same
        # way, because an upload that skipped the length check would be an upload that
        # skipped validation.
        value = str(raw)
        if len(value) > LIMITS["text_length"]:
            raise ValidationError("%s is longer than %d characters"
                                  % (i.label, LIMITS["text_length"]))
        return value

    raise ValidationError("unsupported input kind %r" % kind)


def _as_date(i: InputSpec, raw: Any) -> dt.date:
    try:
        return dt.date.fromisoformat(str(raw)[:10])
    except ValueError as exc:
        raise ValidationError("%s must be a date as YYYY-MM-DD" % i.label) from exc


def _as_list(i: InputSpec, raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [v.strip() for v in raw.split(",") if v.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(v).strip() for v in raw if str(v).strip()]
    raise ValidationError("%s must be a list" % i.label)
