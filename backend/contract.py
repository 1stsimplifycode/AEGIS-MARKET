"""The response contract every module endpoint returns, and the rules it must satisfy.

One shape for every module, so the interface has one renderer rather than forty. The
fields a reader needs in order to judge a number — where it came from, whether it was
computed or replayed, what bounds it — are required fields rather than optional extras,
because an optional provenance field is one that eventually goes missing.

:meth:`Response.check` is run before every response leaves the service. It refuses:

* a successful response with no provenance;
* a ``LIVE_COMPUTATION`` that names a prior run identifier, which would mean a replay
  wearing a live label;
* a ``VERIFIED_ARTIFACT`` with no artifact path, which would mean a live computation
  wearing a replay label;
* an absolute filesystem path anywhere in the payload.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend import (
    ARTIFACT,
    BACKEND_VERSION,
    LIVE,
    MODE_LABEL,
    MODE_MEANING,
    OK,
    REFUSALS,
)


@dataclass
class Metric:
    """One number the interface renders, with everything needed to render it honestly."""

    key: str
    label: str
    value: float | int | str | bool | None
    display: str
    format: str = "float4"
    note: str = ""
    #: Repository-relative artifact this value was read from, when it was read rather
    #: than computed. Empty for a live computation, which is itself informative.
    source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Series:
    """A named series the interface can chart, as columns rather than as a picture."""

    key: str
    label: str
    columns: list[str]
    rows: list[list[Any]]
    note: str = ""
    truncated: bool = False
    total_rows: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ContractError:
    code: str
    reason: str
    #: What the caller can actually do about it. An error with no remedy is a dead end.
    remedy: str = ""
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Response:
    module_id: str
    category: str
    name: str
    status: str
    mode: str
    week: int | None = None
    experiment_id: str | None = None
    dataset: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)
    metrics: list[Metric] = field(default_factory=list)
    series: list[Series] = field(default_factory=list)
    uncertainty: dict = field(default_factory=dict)
    observations: list[str] = field(default_factory=list)
    figures: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)
    limitations: list[dict] = field(default_factory=list)
    message: str = ""
    elapsed_s: float = 0.0
    error: ContractError | None = None

    # -- the rules -----------------------------------------------------------------

    def check(self) -> list[str]:
        problems: list[str] = []
        if self.mode not in (LIVE, ARTIFACT):
            problems.append("mode %r is outside the declared scale" % self.mode)
        if self.status == OK:
            if not self.provenance:
                problems.append("a successful response with no provenance")
            if not self.metrics and not self.series:
                problems.append("a successful response with nothing in it")
        if self.status not in REFUSALS and self.status != OK and self.error is None:
            problems.append("status %s with no error record" % self.status)
        if self.status in REFUSALS and self.error is None:
            problems.append("a refusal with no reason a caller could act on")

        if self.mode == LIVE and self.provenance.get("replayed_run_id"):
            problems.append("a live computation carrying a replayed run identifier")
        if self.mode == ARTIFACT and self.status == OK \
                and not self.provenance.get("artifacts"):
            problems.append("a verified-artifact response naming no artifact")

        for path in _all_strings(self.to_dict()):
            if _looks_absolute(path):
                problems.append("an absolute filesystem path in the payload: %s" % path)
                break
        return problems

    def to_dict(self) -> dict:
        return {
            "backend_version": BACKEND_VERSION,
            "module_id": self.module_id,
            "week": self.week,
            "category": self.category,
            "name": self.name,
            "status": self.status,
            "mode": self.mode,
            "mode_label": MODE_LABEL.get(self.mode, self.mode),
            "mode_meaning": MODE_MEANING.get(self.mode, ""),
            "experiment_id": self.experiment_id,
            "dataset": self.dataset,
            "inputs": self.inputs,
            "metrics": [m.to_dict() for m in self.metrics],
            "series": [s.to_dict() for s in self.series],
            "uncertainty": self.uncertainty,
            "observations": list(self.observations),
            "figures": list(self.figures),
            "tables": list(self.tables),
            "provenance": self.provenance,
            "limitations": list(self.limitations),
            "message": self.message,
            "elapsed_s": round(self.elapsed_s, 3),
            "error": self.error.to_dict() if self.error else None,
        }


def _all_strings(node: Any, depth: int = 0):
    if depth > 8:
        return
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _all_strings(v, depth + 1)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _all_strings(v, depth + 1)


def _looks_absolute(text: str) -> bool:
    """A Windows drive path or a POSIX home path. Repository-relative paths are fine."""
    if len(text) > 4096:
        return False
    lowered = text.lower()
    return (len(text) > 2 and text[1] == ":" and text[2] in "\\/") \
        or lowered.startswith("/home/") or lowered.startswith("/users/")
