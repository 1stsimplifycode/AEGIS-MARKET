"""Which of the sixteen weeks this run of the product is allowed to expose.

The repository holds the whole system. What a given demonstration *shows* is a smaller,
cumulative slice of it, chosen by one number: ``AEGIS_ACTIVE_WEEK``. Week 1 exposes week
1; week 5 exposes weeks 1 through 5; week 16 exposes everything. The implementations
never move, are never stubbed and are never duplicated — only the answer to "may this
caller see it" changes.

Three properties this file exists to guarantee:

**The gate is cumulative, and derived.** A week is enabled when its declared
``enabled_from_week`` is at or below the active week. Nothing keeps a hand-maintained
list of what is on: the manifest declares the unlock point beside the modules it
unlocks, and everything else — navigation, progress marks, route access, API
authorisation — is computed from that one comparison.

**The gate is server-side.** Hiding a link is a courtesy to the reader; it is not a
control. Every route that could return a future week's result asks this module first, so
a caller who types the URL, or curls the API, or edits a cookie, gets the same refusal as
a caller who never saw the link.

**The gate is not a research restriction.** It governs what the *product* exposes. The
test suite, the research runners, the artifact checks and the structural validators all
operate on the complete repository, which is why the default is the full system: absent
the variable, nothing is gated. A demonstration opts *into* a smaller surface; nothing
has to opt out of the gate to do ordinary work.

Non-weekly capabilities — the NIFTY 50 index, evidence alignment, the product read
models, Scenario Lab, the affective and corpus modules — are market context and
infrastructure rather than weekly deliverables. They are available from week 1 onward,
which is what makes week 1 a product rather than a fragment.
"""
from __future__ import annotations

import functools
import os
import re
from dataclasses import dataclass

from backend import registry as reg

#: The variable a launcher sets. Absent or unparseable means the complete system.
ENV_VAR = "AEGIS_ACTIVE_WEEK"

#: Weekly module identifiers carry their week in their number: STATS-08 belongs to week 8.
#: Categories outside this set are not part of the pairing and are never gated.
_WEEKLY_ID = re.compile(r"^(STATS|MULTIMODAL)-(\d{2})$")

#: The status a gated request comes back with. It is a refusal, not a failure: the caller
#: asked for something real that this demonstration has not switched on yet.
FEATURE_NOT_ENABLED = "FEATURE_NOT_ENABLED"


class NotEnabled(Exception):
    """A caller asked for a capability the active week does not expose."""

    def __init__(self, required_week: int, what: str, kind: str = "week") -> None:
        self.required_week = required_week
        self.what = what
        #: "week" or "module". A week refusal and a module refusal are the same rule but
        #: read differently, and "week 8 is part of week 8" is not a sentence.
        self.kind = kind
        super().__init__("%s requires week %d" % (what, required_week))


@dataclass(frozen=True)
class WeekGate:
    week: int
    capability: str
    enabled_from_week: int
    title: str
    product_name: str
    modules: tuple[str, ...]
    route: str

    def enabled_at(self, active: int) -> bool:
        return self.enabled_from_week <= active

    def to_dict(self, active: int) -> dict:
        return {
            "week": self.week,
            "capability": self.capability,
            "enabled_from_week": self.enabled_from_week,
            "title": self.title,
            "product_name": self.product_name,
            "modules": list(self.modules),
            "routes": [self.route] + [_module_route(m) for m in self.modules],
            "enabled": self.enabled_at(active),
        }


def _module_route(module_id: str) -> str:
    match = _WEEKLY_ID.match(module_id)
    if not match:
        return ""
    return "/%s/%s" % (match.group(1).lower(), match.group(2))


@functools.lru_cache(maxsize=1)
def gates() -> tuple[WeekGate, ...]:
    """Every week's gate, read from the manifest.

    Cached because the manifest is read-only at runtime and this is asked on every
    request. A week that declares no ``gate:`` block unlocks at its own number, which is
    the only sensible default and keeps an older manifest working.
    """
    out = []
    for spec in reg.weeks():
        gate = dict(getattr(spec, "gate", {}) or {})
        feature = spec.feature or {}
        out.append(
            WeekGate(
                week=spec.week,
                capability=str(gate.get("capability") or "week-%02d" % spec.week),
                enabled_from_week=int(gate.get("enabled_from_week") or spec.week),
                title=spec.title,
                product_name=str(feature.get("product_question") or spec.title),
                modules=(spec.stats_module, spec.multimodal_module),
                route="/weeks/%d" % spec.week,
            )
        )
    return tuple(out)


def last_week() -> int:
    """The highest week the manifest declares: the complete system."""
    return max((g.week for g in gates()), default=0)


def active_week(raw: str | None = None) -> int:
    """The active week, clamped into the range the manifest actually declares.

    Reading the environment on every call rather than once at import is deliberate: the
    test suite sets the variable per case, and a value captured at import time would make
    the sixteen gating tests silently test the same state sixteen times.
    """
    if raw is None:
        raw = os.environ.get(ENV_VAR)
    top = last_week()
    if raw is None or str(raw).strip() == "":
        return top
    try:
        value = int(str(raw).strip())
    except ValueError:
        return top
    return max(1, min(top, value))


def enabled_weeks(active: int | None = None) -> tuple[int, ...]:
    a = active_week() if active is None else active
    return tuple(g.week for g in gates() if g.enabled_at(a))


def is_week_enabled(week: int, active: int | None = None) -> bool:
    a = active_week() if active is None else active
    gate = next((g for g in gates() if g.week == week), None)
    return gate is not None and gate.enabled_at(a)


def required_week_for_module(module_id: str) -> int | None:
    """The week a module belongs to, or None when it is not part of the pairing.

    Derived from the manifest's week table rather than from the identifier, so a module
    that is ever re-paired moves with its week instead of with its number.
    """
    upper = (module_id or "").upper()
    for gate in gates():
        if upper in gate.modules:
            return gate.enabled_from_week
    return None


def is_module_enabled(module_id: str, active: int | None = None) -> bool:
    required = required_week_for_module(module_id)
    if required is None:
        return True  # not a weekly module: market context and infrastructure
    a = active_week() if active is None else active
    return required <= a


def require_week(week: int, active: int | None = None) -> None:
    """Raise unless this week is exposed. The one call every weekly route makes.

    A week the manifest does not contain is *not* gated, and this returns quietly so the
    caller reaches its own unknown-week handling. The distinction is worth the extra line:
    "week 99 is not enabled in this demonstration build" tells a reader that week 99 is a
    real capability they could switch on, which is a lie about the shape of the programme.
    Absent is absent; gated is built-but-not-shown.
    """
    gate = next((g for g in gates() if g.week == week), None)
    if gate is None:
        return
    if not gate.enabled_at(active_week() if active is None else active):
        raise NotEnabled(gate.enabled_from_week, "Week %d" % week, kind="week")


def require_module(module_id: str, active: int | None = None) -> None:
    """Raise unless this module is exposed."""
    if not is_module_enabled(module_id, active):
        required = required_week_for_module(module_id)
        raise NotEnabled(int(required or 0), module_id.upper(), kind="module")


def refusal(error: NotEnabled, active: int | None = None) -> dict:
    """The response body for a gated request.

    It says what was asked for, which week would expose it, which week is active, and how
    to change that — and it carries no part of the result. A reader who hits this has
    found a real capability that is switched off, not a broken page, and the difference
    should be legible without reading the source.
    """
    a = active_week() if active is None else active
    return {
        "status": FEATURE_NOT_ENABLED,
        "active_week": a,
        "required_week": error.required_week,
        "error": {
            "code": FEATURE_NOT_ENABLED,
            "reason": "%s %s" % (
                ("%s is not enabled in this demonstration build." % error.what)
                if error.kind == "week"
                else ("%s becomes available in week %d of the capstone progression."
                      % (error.what, error.required_week)),
                ("Week 1 is available; weeks 2 to %d are not."
                 % last_week()) if a == 1 else
                ("Weeks 1 to %d are available; weeks %d to %d are not."
                 % (a, a + 1, last_week())) if a < last_week() else
                "Every week is available.",
            ),
            "remedy": (
                "Set %s=%d — locally, weeks\\week_%d\\run.bat does "
                "that for you." % (ENV_VAR, error.required_week, error.required_week)
            ),
        },
    }


def state(active: int | None = None) -> dict:
    """The whole gate, for anything that needs to render it.

    Progress marks, navigation and the gated page all read this rather than each deriving
    the rule again. One computation, one place it can be wrong.
    """
    a = active_week() if active is None else active
    rows = [g.to_dict(a) for g in gates()]
    return {
        "active_week": a,
        "last_week": last_week(),
        "complete": a >= last_week(),
        "enabled_weeks": [r["week"] for r in rows if r["enabled"]],
        "gated_weeks": [r["week"] for r in rows if not r["enabled"]],
        "weeks": rows,
        "capabilities": [c.to_dict(a) for c in product_capabilities()],
        "env_var": ENV_VAR,
        "note": (
            "The repository contains every week. This value decides how many of them the "
            "product exposes; it does not decide what is implemented."
        ),
    }


# ------------------------------------------------------ what the product offers ----
#
# Three presentation states, and the distinction between the middle one and the last is
# the whole point of this section.
#
#   ENABLED      enabled_from_week <= active_week
#   LOCKED       the capability exists and works; this demonstration starts earlier
#   UNAVAILABLE  there is no such capability
#
# LOCKED is not "unimplemented", "not started" or "backend unavailable" — every one of
# those is false about this repository, and telling a reader any of them would misdescribe
# finished work. It is also not UNAVAILABLE: week 8 is a real capability behind a switch,
# and week 99 is not a capability at all. Conflating those two is how a demonstration ends
# up promising something that will never arrive.

ENABLED = "ENABLED"
LOCKED = "LOCKED"
UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class ProductCapability:
    id: str
    name: str
    href: str
    enabled_from_week: int
    summary: str
    #: Where this capability appears: "nav" for the primary navigation, "analysis" for a
    #: section of /analysis. One registry serves both, because a second list of weeks is
    #: a second thing to drift out of step with the first.
    surfaces: tuple[str, ...] = ("nav",)

    def state_at(self, active: int) -> str:
        return ENABLED if self.enabled_from_week <= active else LOCKED

    def to_dict(self, active: int) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "href": self.href,
            "enabled_from_week": self.enabled_from_week,
            "summary": self.summary,
            "surfaces": list(self.surfaces),
            "state": self.state_at(active),
        }


@functools.lru_cache(maxsize=1)
def product_capabilities() -> tuple[ProductCapability, ...]:
    """The product's own vocabulary for its parts, read from the manifest.

    Named for what a reader does rather than for the week that built it: "Event detection"
    is a capability, "Week 8" is a fact about the construction order. The navigation is
    generated from this, so adding a capability is a manifest edit and never a component
    edit.
    """
    raw = reg._manifest().get("product_capabilities") or []
    return tuple(
        ProductCapability(
            id=str(item["id"]),
            name=str(item["name"]),
            href=str(item["href"]),
            enabled_from_week=int(item.get("enabled_from_week") or 1),
            summary=str(item.get("summary") or ""),
            surfaces=tuple(item.get("surfaces") or ("nav",)),
        )
        for item in raw
    )


def capabilities_on(surface: str, active: int | None = None) -> list[dict]:
    """Every capability that appears on one surface, with its state.

    The caller renders what this returns and asks nothing else. In particular it does not
    read the data behind a locked capability in order to decide not to show it — the point
    is that a locked result never leaves the server.
    """
    a = active_week() if active is None else active
    return [c.to_dict(a) for c in product_capabilities() if surface in c.surfaces]


def capability_state(capability_id: str, active: int | None = None) -> str:
    """ENABLED, LOCKED or UNAVAILABLE — never guessed from a name."""
    a = active_week() if active is None else active
    found = next((c for c in product_capabilities() if c.id == capability_id), None)
    return found.state_at(a) if found else UNAVAILABLE


def week_state(week: int, active: int | None = None) -> str:
    """The same three states for a week of the programme.

    A week the manifest does not contain is UNAVAILABLE, not LOCKED. That is what keeps
    `/weeks/99` a genuine 404 while `/weeks/8` is a capability worth telling
    someone about.
    """
    a = active_week() if active is None else active
    gate = next((g for g in gates() if g.week == week), None)
    if gate is None:
        return UNAVAILABLE
    return ENABLED if gate.enabled_at(a) else LOCKED


class UnknownCapability(Exception):
    """A caller asked for a capability this product does not declare."""


def require_capability(capability_id: str,
                       active: int | None = None) -> ProductCapability:
    """Return the capability, or raise for the two ways it can be unavailable.

    `UnknownCapability` and `NotEnabled` are different answers to different questions and
    both are needed: one means no such thing exists, the other means it exists and this
    demonstration has not reached it. A caller that collapsed them would either promise a
    capability that is never coming or deny one that is finished.
    """
    found = next((c for c in product_capabilities() if c.id == capability_id), None)
    if found is None:
        raise UnknownCapability(capability_id)
    a = active_week() if active is None else active
    if found.state_at(a) != ENABLED:
        raise NotEnabled(found.enabled_from_week, found.name, kind="capability")
    return found
