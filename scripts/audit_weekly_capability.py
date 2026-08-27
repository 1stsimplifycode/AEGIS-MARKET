"""Audit all sixteen weekly vertical slices, end to end, and refuse to guess.

The capability gate proves the sixteen weeks can be *exposed* progressively. It proves
nothing about whether each week is actually a working slice, and those are easy to
confuse: a gate that correctly refuses week 8 looks identical whether week 8 is finished
or empty.

So this runs them. For every week it starts from the manifest declaration a page renders,
follows it through the backend service into the adapter and out the other side into the
canonical research implementation, and then checks that what came back is what the page
would draw. The things it will not accept:

* a headline the module does not return — the page would render a dash;
* a chart column that is not in the series, or a series with no rows;
* a metric value that also appears as a literal in the frontend source, which is what a
  hardcoded result looks like from outside;
* a response whose provenance does not name the canonical code it claims to have run;
* advisory language anywhere in a response.

Every verdict is PASS, FAIL, NOT_APPLICABLE or BLOCKED, and the last two carry a reason.
NOT_APPLICABLE is used where a check genuinely does not apply — fifteen of the sixteen
weeks implement no attribution method, and recording XAI as PASS for them would be a
fabrication. It is never used to make a failure disappear.

    python scripts/audit_weekly_capability.py                 all sixteen
    python scripts/audit_weekly_capability.py --weeks 1,4,8   a subset
    python scripts/audit_weekly_capability.py --no-launchers  skip the launcher smoke

Writes ``research_artifacts/weekly_capability_audit.{json,csv}`` and prints the summary.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend import capability as cap  # noqa: E402
from backend import registry as reg  # noqa: E402
from backend import service as svc  # noqa: E402

OUT_DIR = REPO_ROOT / "research_artifacts"

# The summary table uses tick and cross marks, and the default Windows console codepage
# cannot encode them. Reconfiguring is better than falling back to ASCII: the same table
# is meant to be readable in a terminal, in a log and in the artifacts, and three
# renderings of one table is two too many.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS = "PASS"
FAIL = "FAIL"
NOT_APPLICABLE = "NOT_APPLICABLE"
BLOCKED = "BLOCKED"

#: Frontend source that could hold a hardcoded number.
FRONTEND_DIRS = ("app", "components", "lib")

#: A value distinctive enough that finding it in the frontend means something. "0" and "2"
#: appear in every stylesheet; "5,027" and "0.4847" do not.
DISTINCTIVE = re.compile(r"^(?=.*\d)(?=.*[.,%])[\d.,%\s-]{4,}$")


def advisory_patterns() -> list[re.Pattern]:
    """The forbidden vocabulary, loaded from the test that owns it.

    Imported rather than copied: a second list is a second thing to drift, and the policy
    has one home.
    """
    path = REPO_ROOT / "tests" / "unit" / "test_non_advisory.py"
    spec = importlib.util.spec_from_file_location("_non_advisory", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return [re.compile(p, re.I) for p in module.FORBIDDEN]


# ------------------------------------------------------------------- helpers ----

def verdict(ok: bool, reason_if_not: str = "") -> dict:
    return {"status": PASS if ok else FAIL, "reason": "" if ok else reason_if_not}


def not_applicable(reason: str) -> dict:
    return {"status": NOT_APPLICABLE, "reason": reason}


def blocked(reason: str) -> dict:
    return {"status": BLOCKED, "reason": reason}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def waits_for(url: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(0.5)
    return False


# ---------------------------------------------------------------- the checks ----

def check_route(week: int) -> dict:
    """One page renders every week; the route is a parameter, not sixteen files."""
    page = REPO_ROOT / "app" / "weeks" / "[week]" / "page.tsx"
    if not page.exists():
        return verdict(False, "app/weeks/[week]/page.tsx is missing")
    per_week = list((REPO_ROOT / "app" / "weeks").glob("[0-9]*"))
    if per_week:
        return verdict(False, "per-week route directories exist: %s" % per_week)
    return verdict(True)


def check_launcher_contract(week: int) -> dict:
    """Both modes, one page, and this week's active week — read off the file."""
    bat = REPO_ROOT / "weeks" / ("week_%d" % week) / "run.bat"
    if not bat.exists():
        return verdict(False, "weeks/week_%d/run.bat is missing" % week)
    text = bat.read_text(encoding="utf-8")
    wants = {
        "product URL": "/weeks/%d?mode=product" % week,
        "research URL": "/weeks/%d?mode=research" % week,
        "research argument": '"%~1"=="research"',
        "active week": "set AEGIS_ACTIVE_WEEK=%d" % week,
        "backend": "backend.server",
        "interface": "npm run dev",
    }
    missing = [name for name, token in wants.items() if token not in text]
    if missing:
        return verdict(False, "run.bat does not carry: %s" % ", ".join(missing))
    if ("/weeks/%d/research" % week) in text or ("/weeks/%d/product" % week) in text:
        return verdict(False, "the launcher points at a separate per-mode route")
    return verdict(True)


def run_launcher(week: int, timeout: float = 150.0) -> dict:
    """Start this week's launcher for real and see whether the services come up.

    The launcher is the thing a mentor types, so reading it is not the same as running it.
    `AEGIS_NO_BROWSER=1` suppresses the page-open step only; everything else — the
    backend,
    active week it enforces, the interface — happens exactly as it would.
    """
    bat = REPO_ROOT / "weeks" / ("week_%d" % week) / "run.bat"
    if not bat.exists():
        return blocked("weeks/week_%d/run.bat is missing" % week)

    backend_port, frontend_port = free_port(), free_port()
    env = {
        **os.environ,
        "AEGIS_NO_BROWSER": "1",
        "AEGIS_BACKEND_PORT": str(backend_port),
        "AEGIS_FRONTEND_PORT": str(frontend_port),
        "AEGIS_BACKEND_URL": "http://127.0.0.1:%d" % backend_port,
        # Its own build directory: a dev server sharing `.next` with a production build
        # leaves the two interleaved, and the failure reads as an application bug.
        "AEGIS_DIST_DIR": ".next-audit/next",
        "NEXT_TELEMETRY_DISABLED": "1",
    }
    log_dir = REPO_ROOT / ".next-audit"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / ("launcher-week-%d.log" % week)
    log = log_path.open("w", encoding="utf-8")

    proc = subprocess.Popen(
        ["cmd", "/c", str(bat)] if os.name == "nt" else ["sh", str(bat)],
        cwd=str(REPO_ROOT), stdout=log, stderr=subprocess.STDOUT,
        env=env, stdin=subprocess.DEVNULL,
    )
    try:
        backend_up = waits_for(
            "http://127.0.0.1:%d/api/health" % backend_port, timeout * 0.5)
        active = None
        if backend_up:
            try:
                with urllib.request.urlopen(
                        "http://127.0.0.1:%d/api/capabilities" % backend_port,
                        timeout=10) as r:
                    active = json.loads(r.read().decode("utf-8")).get("active_week")
            except Exception as error:            # noqa: BLE001 - reported, not raised
                return blocked("backend started but did not answer: %s" % error)
        frontend_up = waits_for("http://127.0.0.1:%d/" % frontend_port, timeout * 0.5)
    finally:
        _kill_tree(proc)
        log.close()

    if not backend_up:
        return blocked("the backend did not answer; see %s" % log_path.name)
    if active != week:
        return verdict(False, "the launcher started the backend at week %s, not %d"
                       % (active, week))
    if not frontend_up:
        return blocked("the interface did not answer; see %s" % log_path.name)
    return verdict(True)


def _kill_tree(proc: subprocess.Popen) -> None:
    """Take the children with it.

    `npm run dev` is a shell that spawns node, which spawns more node. Killing only the
    process we started leaves a dev server holding the port, and the next week's launcher
    then fails for a reason that has nothing to do with that week.
    """
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/pid", str(proc.pid), "/T", "/F"],
                       capture_output=True, check=False)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()


def check_execution(week: int, result: dict) -> dict:
    """Did both halves actually run, and does the provenance name what ran?"""
    if result.get("status") not in ("OK", "PARTIAL"):
        return verdict(False, "the week returned %s" % result.get("status"))
    spec = reg.week(week)
    out = {}
    for module_id in (spec.stats_module, spec.multimodal_module):
        half = (result.get("results") or {}).get(module_id)
        if half is None:
            out[module_id] = verdict(False, "the response carries no %s" % module_id)
            continue
        if half.get("status") != "OK":
            out[module_id] = verdict(
                False, "%s returned %s" % (module_id, half.get("status")))
            continue
        prov = half.get("provenance") or {}
        declared = list(reg.module(module_id).canonical or [])
        if half.get("mode") == "LIVE_COMPUTATION":
            if not prov.get("computed"):
                out[module_id] = verdict(
                    False, "labelled live but provenance says nothing was computed")
                continue
            if not prov.get("canonical_called"):
                out[module_id] = verdict(
                    False, "provenance names no canonical implementation as called")
                continue
            out[module_id] = {"status": PASS, "reason": "",
                              "mode": "LIVE_COMPUTATION",
                              "canonical": declared,
                              "called": list(prov.get("canonical_called") or [])}
        else:
            reason = (reg.module(module_id).analysis.artifact_reason
                      if reg.module(module_id).analysis else "")
            out[module_id] = {
                "status": PASS, "reason": "",
                "mode": "VERIFIED_ARTIFACT",
                "artifact_reason": reason or "declared artifact-only in the manifest",
                "canonical": declared,
                "called": list(prov.get("canonical_called") or []),
            }
    return out


def check_metrics(week: int, result: dict) -> dict:
    """Every declared headline must be a key the module actually returned."""
    feature = reg.week(week).feature or {}
    declared = feature.get("headline") or []
    if not declared:
        return verdict(False, "the week declares no headline figures")
    missing, empty = [], []
    for item in declared:
        half = (result.get("results") or {}).get(item["module"]) or {}
        found = next((m for m in half.get("metrics", [])
                      if m.get("key") == item["metric"]), None)
        if found is None:
            missing.append("%s.%s" % (item["module"], item["metric"]))
        elif str(found.get("display", "")).strip() in ("", "-", "—"):
            empty.append("%s.%s" % (item["module"], item["metric"]))
    if missing:
        return verdict(False, "declared but not returned: %s" % ", ".join(missing))
    if empty:
        return verdict(False, "returned with nothing to show: %s" % ", ".join(empty))
    return {"status": PASS, "reason": "", "verified": len(declared)}


def check_charts(week: int, result: dict) -> dict:
    """Declared series must exist, carry the declared columns, and have rows."""
    feature = reg.week(week).feature or {}
    problems, checked = [], 0
    for name in ("primary_visual", "secondary_visual"):
        visual = feature.get(name)
        if not visual:
            if name == "primary_visual":
                problems.append("no primary visual is declared")
            continue
        checked += 1
        half = (result.get("results") or {}).get(visual["module"]) or {}
        series = next((s for s in half.get("series", [])
                       if s.get("key") == visual["series"]), None)
        if series is None:
            problems.append("%s names series %r, which the module did not return"
                            % (name, visual["series"]))
            continue
        columns = series.get("columns") or []
        for column in (visual["label_column"], visual["value_column"]):
            if column not in columns:
                problems.append("%s wants column %r; the series has %s"
                                % (name, column, columns))
        rows = series.get("rows") or []
        if not rows:
            problems.append("%s resolves to a series with no rows" % name)
            continue
        # A chart of blanks is a chart nobody can read, so the values have to be numbers.
        at = columns.index(visual["value_column"]) if visual["value_column"] in columns \
            else None
        if at is not None:
            numeric = sum(1 for row in rows
                          if isinstance(row[at], (int, float))
                          or _looks_numeric(row[at]))
            if numeric == 0:
                problems.append("%s has rows but no numeric values to plot" % name)
    if problems:
        return verdict(False, "; ".join(problems))
    return {"status": PASS, "reason": "", "visuals": checked}


def _looks_numeric(value) -> bool:
    try:
        float(str(value).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return False
    return True


def check_not_hardcoded(result: dict, frontend_text: str) -> dict:
    """A backend number that also appears in the frontend source is a hardcoded result.

    Only distinctive values are looked for. "1" appears in every stylesheet; "0.4847" does
    not, and if it did the page would be showing a stored answer while claiming to
    compute it.
    """
    hits = []
    for half in (result.get("results") or {}).values():
        for metric in half.get("metrics", []):
            display = str(metric.get("display", "")).strip()
            if not DISTINCTIVE.match(display):
                continue
            if display in frontend_text:
                hits.append("%s = %s" % (metric.get("key"), display))
    if hits:
        return verdict(False, "found in frontend source: %s"
                       % "; ".join(sorted(set(hits))))
    return verdict(True)


def check_evidence(week: int, result: dict) -> dict:
    """Provenance a reader can act on: what ran, from what commit, over what."""
    required = ("module_id", "adapter", "canonical", "git_commit", "requested_at")
    problems = []
    for module_id, half in (result.get("results") or {}).items():
        prov = half.get("provenance") or {}
        missing = [k for k in required if not prov.get(k)]
        if missing:
            problems.append("%s provenance lacks %s" % (module_id, ", ".join(missing)))
        if not (half.get("dataset") or {}).get("source"):
            problems.append("%s does not say what it read" % module_id)
    if problems:
        return verdict(False, "; ".join(problems))
    return verdict(True)


def check_uncertainty(week: int, result: dict) -> dict:
    """Shown where applicable, and where it is not, the module has to say why.

    A count is not an estimate and carries no interval. That is a legitimate
    NOT_APPLICABLE — but only when the module states it, which is what separates a
    considered answer from a missing one.
    """
    stated, silent = [], []
    for module_id, half in (result.get("results") or {}).items():
        u = half.get("uncertainty") or {}
        if u.get("kind") and u.get("kind") != "none":
            stated.append(module_id)
        elif u.get("reading"):
            stated.append(module_id)          # says why there is no interval
        else:
            silent.append(module_id)
    if silent:
        return verdict(False, "no uncertainty and no explanation from: %s"
                       % ", ".join(silent))
    return {"status": PASS, "reason": "", "stated_by": stated}


def check_xai(week: int, result: dict) -> dict:
    """Only where attribution is genuinely implemented.

    One weekly module reaches `research/xai/`. Recording the other fifteen as PASS would
    be a fabrication, and recording them as FAIL would be a fabrication of a different
    kind — they never claimed to explain anything.
    """
    spec = reg.week(week)
    with_xai = [m for m in (spec.stats_module, spec.multimodal_module)
                if any("xai" in c.lower() or "attribution" in c.lower()
                       for c in (reg.module(m).canonical or []))]
    if not with_xai:
        return not_applicable(
            "no module in this week implements an attribution method; the XAI work lives "
            "in MULTIMODAL-16 and the research-only human-affect modules")
    problems = []
    for module_id in with_xai:
        half = (result.get("results") or {}).get(module_id) or {}
        blob = json.dumps(half).lower()
        if not any(word in blob for word in ("attribution", "faithful", "deletion",
                                             "saliency", "importance")):
            problems.append("%s claims attribution but returns none" % module_id)
    if problems:
        return verdict(False, "; ".join(problems))
    return {"status": PASS, "reason": "", "modules": with_xai}


def check_limitations(week: int, result: dict) -> dict:
    """What the manifest declares must reach the response."""
    problems, shown = [], []
    for module_id, half in (result.get("results") or {}).items():
        declared = set(reg.module(module_id).limitations or [])
        returned = {limit.get("id") for limit in half.get("limitations", [])}
        shown.extend(sorted(returned))
        missing = declared - returned
        if missing:
            problems.append("%s declares %s but the response omits them"
                            % (module_id, sorted(missing)))
    if problems:
        return verdict(False, "; ".join(problems))
    if not shown:
        return not_applicable("neither module declares a limitation for this week")
    return {"status": PASS, "reason": "", "shown": sorted(set(shown))}


def check_advisory(result: dict, patterns: list[re.Pattern]) -> dict:
    """No transactional language anywhere in what the page will render."""
    blob = json.dumps(result)
    hits = sorted({m.group(0) for p in patterns for m in p.finditer(blob)})
    if hits:
        return verdict(False, "advisory vocabulary in the response: %s" % ", ".join(hits))
    return verdict(True)


def check_index_context(result: dict) -> dict:
    """NIFTY 50 is the market context, and the proxy is never given its name.

    The distinction has to survive a naive scan. Limitation L-01 reads
    "point-in-time liquidity proxy, *not* the Nifty 50" -- the two names sit four
    words apart precisely because the sentence is separating them, and a proximity
    match alone calls that a violation. It is the opposite of one, so the negation is
    cut before the scan rather than the pattern being loosened.
    """
    blob = json.dumps(result)
    separated = re.sub(
        r"\bnot\s+(the\s+)?nifty[\s_-]*50\b", " ", blob, flags=re.I)
    confused = re.search(
        r"(liquidity|universe)\s+proxy[^\"]{0,40}nifty"
        r"|nifty[^\"]{0,25}\bproxy\b",
        separated, re.I)
    if confused:
        return verdict(False, "a response equates the proxy with the index: %r"
                       % confused.group(0)[:80])
    return verdict(True)


def check_alignment(index_id: str = "NIFTY50") -> dict:
    """The alignment layer answers per source, and refuses what it cannot support."""
    try:
        from scripts.stages import product_views as pv
        summary = pv.evidence_summary(index_id)
        states = {s.get("source_id"): s.get("alignment_status")
                  for s in summary.get("sources", [])}
        if not states:
            return blocked("the evidence summary returned no sources")
        gate = pv.combined_analysis_permitted(
            index_id, "MODEL_EVIDENCE", "a combined figure")
        if gate.get("permitted") is not False:
            return verdict(
                False,
                "a pair sharing no sessions was permitted; the gate is not refusing")
        return {"status": PASS, "reason": "", "states": states,
                "refuses_unsupported": True}
    except Exception as error:                    # noqa: BLE001 - reported, not raised
        return blocked("the alignment layer raised %s: %s"
                       % (type(error).__name__, error))


def check_gate(week: int) -> dict:
    """Cumulative, and refused server-side at every active week."""
    wrong = []
    for active in range(1, cap.last_week() + 1):
        expected = week <= active
        if cap.is_week_enabled(week, active) is not expected:
            wrong.append(active)
        for module_id in (reg.week(week).stats_module, reg.week(week).multimodal_module):
            if cap.is_module_enabled(module_id, active) is not expected:
                wrong.append("%d/%s" % (active, module_id))
    if wrong:
        return verdict(False, "the gate is wrong at: %s" % wrong)
    return {"status": PASS, "reason": "",
            "enabled_from": reg.week(week).gate.get("enabled_from_week", week)}


def check_modes() -> dict:
    """Two views of one page, switched by an attribute — not two implementations."""
    page = (REPO_ROOT / "app" / "weeks" / "[week]" / "page.tsx").read_text(
        encoding="utf-8")
    chrome = (REPO_ROOT / "components" / "ui" / "Chrome.tsx").read_text(encoding="utf-8")
    problems = []
    if "modeOnly--product" not in page or "modeOnly--research" not in page:
        problems.append("the weekly page does not render both registers")
    if "modeToggle" not in chrome:
        problems.append("no mode toggle in the masthead")
    if list((REPO_ROOT / "app" / "weeks").glob("*/research")):
        problems.append("a separate research route exists")
    if problems:
        return verdict(False, "; ".join(problems))
    return verdict(True)


def check_product_not_a_notebook(week: int, result: dict) -> dict:
    """Product mode leads with a reader's question, not with the module's vocabulary."""
    feature = reg.week(week).feature or {}
    question = feature.get("product_question") or ""
    if not question:
        return verdict(False, "no product question is declared")
    jargon = [w for w in ("STATS-", "MULTIMODAL-", "AUPRC", "parquet", "adapter",
                          "p-value")
              if w in question]
    if jargon:
        return verdict(False, "the product question uses %s" % ", ".join(jargon))
    if not feature.get("story"):
        return verdict(False, "no plain-language basis is declared for this week")
    return verdict(True)


# --------------------------------------------------------------------- audit ----

def audit_week(week: int, frontend_text: str, patterns: list[re.Pattern],
               alignment: dict, modes: dict, launchers: bool) -> dict:
    spec = reg.week(week)
    started = time.perf_counter()

    try:
        result = svc.run_week(week)
    except Exception as error:                    # noqa: BLE001 - reported, not raised
        result = None
        execution = blocked("running the week raised %s: %s"
                            % (type(error).__name__, error))
    else:
        execution = check_execution(week, result)

    def when_run(fn, *args):
        if result is None:
            return blocked("the week did not run, so this could not be checked")
        return fn(*args)

    checks = {
        "weekly_route": check_route(week),
        "launcher_contract": check_launcher_contract(week),
        "launcher_starts": (run_launcher(week) if launchers
                            else not_applicable("--no-launchers was passed")),
        "both_modes_one_page": modes,
        "execution": execution,
        "metrics_verified": when_run(check_metrics, week, result),
        "charts_verified": when_run(check_charts, week, result),
        "no_hardcoded_result": when_run(check_not_hardcoded, result, frontend_text),
        "evidence_verified": when_run(check_evidence, week, result),
        "uncertainty_verified": when_run(check_uncertainty, week, result),
        "xai_verified": when_run(check_xai, week, result),
        "limitations_verified": when_run(check_limitations, week, result),
        "advisory_guard": when_run(check_advisory, result, patterns),
        "index_context": when_run(check_index_context, result),
        "alignment_verified": alignment,
        "gate_enforced": check_gate(week),
        "product_register": when_run(check_product_not_a_notebook, week, result),
    }

    statuses = []
    for name, value in checks.items():
        if name == "execution" and isinstance(value, dict) and "status" not in value:
            statuses.extend(v.get("status") for v in value.values())
        else:
            statuses.append(value.get("status"))

    if FAIL in statuses:
        status = FAIL
    elif BLOCKED in statuses:
        status = BLOCKED
    else:
        status = PASS

    modules = {}
    for module_id in (spec.stats_module, spec.multimodal_module):
        half = ((result or {}).get("results") or {}).get(module_id) or {}
        modules[module_id] = {
            "name": reg.module(module_id).name,
            "mode": half.get("mode"),
            "status": half.get("status"),
            "canonical": list(reg.module(module_id).canonical or []),
            "adapter": reg.module(module_id).adapter,
            "metrics": len(half.get("metrics", [])),
            "series": len(half.get("series", [])),
        }

    return {
        "week": week,
        "title": spec.title,
        "stats_module": spec.stats_module,
        "multimodal_module": spec.multimodal_module,
        "product_route": "/weeks/%d" % week,
        "modules": modules,
        "elapsed_s": round(time.perf_counter() - started, 2),
        "backend_status": (result or {}).get("status"),
        "backend_elapsed_s": (result or {}).get("elapsed_s"),
        "checks": checks,
        "limitations": sorted({limit.get("id")
                               for half in ((result or {}).get("results") or {}).values()
                               for limit in half.get("limitations", [])}),
        "status": status,
    }


def summarise(rows: list[dict]) -> str:
    def mark(row, key):
        value = row["checks"][key]
        status = value.get("status") if "status" in value else None
        if status is None:                       # the execution block, keyed by module
            status = FAIL if any(v.get("status") == FAIL for v in value.values()) \
                else PASS
        return {PASS: "✓", FAIL: "✗", NOT_APPLICABLE: "–", BLOCKED: "!"}.get(status, "?")

    def half_mark(row, module_id):
        value = row["checks"]["execution"]
        if "status" in value:
            return "✗" if value["status"] == FAIL else "!"
        return "✓" if value.get(module_id, {}).get("status") == PASS else "✗"

    lines = ["Week | STATS | MULTIMODAL | Backend | Product | Research | E2E | Status",
             "-----|-------|------------|---------|---------|----------|-----|-------"]
    for row in rows:
        lines.append(
            "%-4d | %-5s | %-10s | %-7s | %-7s | %-8s | %-3s | %s"
            % (row["week"],
               half_mark(row, row["stats_module"]),
               half_mark(row, row["multimodal_module"]),
               mark(row, "evidence_verified"),
               mark(row, "product_register"),
               mark(row, "both_modes_one_page"),
               mark(row, "launcher_starts"),
               row["status"]))
    return "\n".join(lines)


CSV_COLUMNS = [
    "week", "stats_module", "multimodal_module", "product_route", "research_mode",
    "backend_connected", "stats_executed", "multimodal_executed", "metrics_verified",
    "charts_verified", "evidence_verified", "xai_verified", "uncertainty_verified",
    "alignment_verified", "advisory_guard", "status", "limitations",
]


def csv_row(row: dict) -> dict:
    def st(key):
        value = row["checks"][key]
        return value.get("status", "?")

    def half(module_id):
        value = row["checks"]["execution"]
        if "status" in value:
            return value["status"]
        return value.get(module_id, {}).get("status", "?")

    return {
        "week": row["week"],
        "stats_module": row["stats_module"],
        "multimodal_module": row["multimodal_module"],
        "product_route": row["product_route"],
        "research_mode": st("both_modes_one_page"),
        "backend_connected": PASS if row["backend_status"] == "OK" else FAIL,
        "stats_executed": half(row["stats_module"]),
        "multimodal_executed": half(row["multimodal_module"]),
        "metrics_verified": st("metrics_verified"),
        "charts_verified": st("charts_verified"),
        "evidence_verified": st("evidence_verified"),
        "xai_verified": st("xai_verified"),
        "uncertainty_verified": st("uncertainty_verified"),
        "alignment_verified": st("alignment_verified"),
        "advisory_guard": st("advisory_guard"),
        "status": row["status"],
        "limitations": " ".join(row["limitations"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weeks", default="",
                        help="comma-separated subset, e.g. 1,4,8. Default: all.")
    parser.add_argument("--no-launchers", action="store_true",
                        help="skip starting each week's run.bat (much faster)")
    args = parser.parse_args()

    weeks = ([int(w) for w in args.weeks.split(",") if w.strip()]
             if args.weeks else [w.week for w in reg.weeks()])

    print("auditing %d weekly slices%s"
          % (len(weeks), "" if not args.no_launchers else " (launchers skipped)"))

    frontend_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for directory in FRONTEND_DIRS
        for path in (REPO_ROOT / directory).rglob("*")
        if path.suffix in (".ts", ".tsx") and path.is_file())
    patterns = advisory_patterns()
    alignment = check_alignment()
    modes = check_modes()

    rows = []
    for week in weeks:
        row = audit_week(week, frontend_text, patterns, alignment, modes,
                         launchers=not args.no_launchers)
        rows.append(row)
        print("  week %-2d  %-8s  %s" % (week, row["status"], row["title"][:52]))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "repository_weeks": len(reg.weeks()),
        "audited": len(rows),
        "passing": sum(1 for r in rows if r["status"] == PASS),
        "failing": sum(1 for r in rows if r["status"] == FAIL),
        "blocked": sum(1 for r in rows if r["status"] == BLOCKED),
        "with_limitations": sum(1 for r in rows if r["limitations"]),
        "note": (
            "Every value here was produced by running the week. NOT_APPLICABLE carries "
            "the reason it does not apply; BLOCKED carries what prevented the check. "
            "Neither is used to convert a failure into a pass."
        ),
        "weeks": rows,
    }
    (OUT_DIR / "weekly_capability_audit.json").write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")

    with (OUT_DIR / "weekly_capability_audit.csv").open(
            "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(csv_row(row))

    print()
    print(summarise(rows))
    print()
    print("audited %d · passing %d · failing %d · blocked %d · with limitations %d"
          % (payload["audited"], payload["passing"], payload["failing"],
             payload["blocked"], payload["with_limitations"]))
    for row in rows:
        if row["status"] == PASS:
            continue
        print("\n%s week %d:" % (row["status"], row["week"]))
        for name, value in row["checks"].items():
            statuses = ([value] if "status" in value else list(value.values()))
            for entry in statuses:
                if entry.get("status") in (FAIL, BLOCKED):
                    print("   %-22s %s  %s"
                          % (name, entry["status"], entry.get("reason", "")))
    print("\nwrote research_artifacts/weekly_capability_audit.{json,csv}")
    return 1 if payload["failing"] else 0


if __name__ == "__main__":
    sys.exit(main())
