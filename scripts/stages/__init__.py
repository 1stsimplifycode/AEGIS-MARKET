"""Thin execution adapters for the STATS and MULTIMODAL modules.

Every function here is a **wrapper**, not an implementation. Each one imports canonical
code that already exists in ``research/`` or ``scripts/`` and calls it. No statistical
method, feature definition, model or evaluation metric is defined in this package, and
none may be: when a module needs science that does not exist yet, the manifest marks it
``INFRASTRUCTURE_ONLY`` and the adapter returns NOT YET EXECUTED instead of inventing a
substitute.

That rule is what keeps the restructuring reversible. Deleting this package and the
``STATS``/``MULTIMODAL`` directories would leave the research pipeline exactly as it was.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Exit codes shared with ``scripts/run_module.py`` and the .bat runners. Kept as plain
#: integers because a .bat file compares ERRORLEVEL numerically.
OK = 0
FAILED = 1
BLOCKED = 3
INPUTS_MISSING = 4
SKIPPED_PROTECTED = 5
NOT_YET_EXECUTED = 6

STATUS_NAME = {
    OK: "OK",
    FAILED: "FAILED",
    BLOCKED: "BLOCKED",
    INPUTS_MISSING: "INPUTS MISSING",
    SKIPPED_PROTECTED: "SKIPPED (protected artifacts)",
    NOT_YET_EXECUTED: "NOT YET EXECUTED",
}


@dataclass
class StageResult:
    """What a module run reports back to the dispatcher."""
    code: int
    message: str = ""
    outputs: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> str:
        return STATUS_NAME.get(self.code, "UNKNOWN(%d)" % self.code)


def not_yet_executed(what: str, tracked_as: str) -> StageResult:
    """The honest return for a module whose science has not been written yet.

    Writes nothing. A module that produced a plausible-looking placeholder file would be
    indistinguishable from one that had actually run, which is the single most damaging
    thing this pipeline could do.
    """
    return StageResult(
        NOT_YET_EXECUTED,
        "%s is not implemented. Tracked as %s. No output was written and no value was "
        "substituted." % (what, tracked_as),
    )


def require(paths: list[str | Path]) -> StageResult | None:
    """Return an INPUTS MISSING result if any declared input is absent."""
    missing = [str(p) for p in paths if not Path(p).exists()]
    if missing:
        return StageResult(INPUTS_MISSING,
                           "missing input(s): %s" % ", ".join(missing))
    return None


# ---------------------------------------------------------------- live analysis ----
#
# A second, distinct operation from the one above.
#
# ``StageResult`` describes *regenerating a module's artifacts*: it writes files, the
# protected guard applies, and it is what ``run.bat`` invokes.
#
# ``AnalysisResult`` describes *running a module's analysis over a slice the caller
# chose*: it writes nothing, takes validated parameters, and is what the backend invokes
# when someone presses a button. Keeping them separate is what lets the product be
# interactive without any request being able to overwrite a cited artifact.
#
# Both call the same canonical code. Neither defines any.

def fmt_value(value, fmt: str = "auto") -> str:
    """Render a number the way the interface should show it.

    Formatting lives here rather than in the frontend so that a value and its rendering
    travel together: a metric that arrives as 0.9411660307392683 and is rounded in three
    different components is three chances to disagree about what the number is.
    """
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, str):
        return value
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if num != num or num in (float("inf"), float("-inf")):
        return "n/a"
    if fmt == "int":
        return "{:,}".format(int(round(num)))
    if fmt == "pct":
        return "%.1f%%" % (num * 100)
    if fmt == "sci":
        return "%.2e" % num
    if fmt.startswith("float"):
        return "%.*f" % (int(fmt[5:] or 4), num)
    if fmt == "inr":
        from research.scenario.money import inr
        return inr(num)
    # auto: integers as counts, everything else at four decimals.
    if isinstance(value, int) or float(num).is_integer():
        return "{:,}".format(int(num))
    return "%.4f" % num


def metric(key: str, label: str, value, fmt: str = "auto", note: str = "",
           source: str = "") -> dict:
    """One number, with everything the interface needs to render it honestly."""
    return {"key": key, "label": label, "value": value,
            "display": fmt_value(value, fmt), "format": fmt,
            "note": note, "source": source}


def series(key: str, label: str, columns: list[str], rows: list[list],
           note: str = "", total_rows: int | None = None) -> dict:
    """A named table the interface can chart, as columns rather than as a picture."""
    return {"key": key, "label": label, "columns": [str(c) for c in columns],
            "rows": rows, "note": note,
            "truncated": bool(total_rows is not None and total_rows > len(rows)),
            "total_rows": total_rows if total_rows is not None else len(rows)}


@dataclass
class AnalysisResult:
    """What a live analysis returns. Writes nothing; every field is for the caller."""

    ok: bool = True
    #: Set only when ``ok`` is false, using the backend's status vocabulary.
    status: str = ""
    message: str = ""
    #: What the caller can do about a refusal. An error with no remedy is a dead end.
    remedy: str = ""
    dataset: dict = field(default_factory=dict)
    metrics: list[dict] = field(default_factory=list)
    series: list[dict] = field(default_factory=list)
    uncertainty: dict = field(default_factory=dict)
    observations: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)


def insufficient(message: str, remedy: str) -> AnalysisResult:
    """The honest return when the caller's selection leaves nothing to analyse.

    A slice with three rows in it does not produce a small result; it produces a
    meaningless one. Saying so is the only correct behaviour.
    """
    return AnalysisResult(ok=False, status="INSUFFICIENT_DATA", message=message,
                          remedy=remedy)
