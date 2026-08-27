"""Generate and validate the STATS / MULTIMODAL execution structure.

    python scripts/validate_structure.py --write     # regenerate from the manifest
    python scripts/validate_structure.py             # validate, exit 1 on any problem

The manifest ``research_modules.yaml`` is the single source of truth. Module directories,
``run.bat`` files, module ``README.md`` files and the three master runners are all derived
from it, so they cannot drift: this script regenerates them and, in validation mode,
reports any hand-edit as drift.

What validation checks (spec section 96):

* ``STATS/`` and ``MULTIMODAL/`` exist and contain exactly 16 module directories each
* every module directory has ``run.bat`` and ``README.md``
* every generated file matches what the manifest would produce
* the three master runners exist
* manifest ids are unique, indices are 1..16 per category, and folder names match slugs
* every ``adapter:`` resolves to a callable
* every ``canonical:`` path that names a file actually exists
* every ``depends_on:`` names a module that exists, with no cycles
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

MANIFEST = REPO_ROOT / "research_modules.yaml"
BANNER = "GENERATED FROM research_modules.yaml - edit the manifest, not this file"


def load() -> dict:
    import yaml
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def folder_name(m: dict) -> str:
    return "%02d_%s" % (m["index"], m["slug"])


def module_dir(m: dict) -> Path:
    return REPO_ROOT / m["category"] / folder_name(m)


# --------------------------------------------------------------- generation ----

def render_run_bat(m: dict) -> str:
    return "\n".join([
        "@echo off",
        "REM %s" % BANNER,
        "REM %s  %s" % (m["id"], m["name"]),
        "REM Canonical implementation: %s" % (", ".join(m["canonical"]) or "(none yet)"),
        "REM",
        "REM This file is an EXECUTION INTERFACE. It contains no research logic: it",
        "REM forwards to the shared runner, which calls the adapter named in the",
        "REM manifest, which calls the canonical implementation above.",
        "setlocal",
        'for %%I in ("%~dp0..\\..") do set "AEGIS_ROOT=%%~fI"',
        'call "%AEGIS_ROOT%\\tools\\aegis_module.bat" ' + m["id"] + " %*",
        "exit /b %ERRORLEVEL%",
        "",
    ])


def render_readme(m: dict) -> str:
    canonical = m["canonical"] or []
    inputs = m.get("inputs") or []
    outputs = m.get("outputs") or []
    deps = m.get("depends_on") or []
    lims = m.get("limitations") or []

    wrapper_note = {
        "WRAPS_EXISTING":
            "This module wraps code that already exists. It defines no new statistic, "
            "feature or model.",
        "WRAPS_EXISTING_PROTECTED":
            "This module wraps existing code, but regenerating its outputs would "
            "overwrite artifacts that the claim ledger and documentation already cite. "
            "It refuses to run without `--force` and exits with code 5 instead.",
        "INFRASTRUCTURE_ONLY":
            "The canonical implementation for this module does not exist yet. The "
            "module, its runner and its output contract exist so the scientific work "
            "can land as a separate change. Running it reports NOT YET EXECUTED, "
            "writes nothing, and substitutes no value.",
    }[m["wrapper_status"]]

    lines = [
        "<!-- %s -->" % BANNER,
        "# %s — %s" % (m["id"], m["name"]),
        "",
        "| | |",
        "|---|---|",
        "| Category | `%s` |" % m["category"],
        "| Wrapper status | `%s` |" % m["wrapper_status"],
        "| Research status | `%s` |" % m["status"],
        "| Experiment | %s |" % (("`%s`" % m["experiment_id"]) if m.get("experiment_id")
                                 else "—"),
        "| Limitations | %s |" % (", ".join("`%s`" % x for x in lims) or "—"),
        "",
        "## Purpose",
        "",
        m["purpose"].strip(),
        "",
        "## Research question",
        "",
        "> %s" % m["research_question"].strip(),
        "",
        "## Inputs",
        "",
    ]
    lines += ["- `%s`" % i for i in inputs] or ["- none (this module needs no data)"]
    lines += ["", "## Processing", "",
              "Adapter: `%s`" % m["adapter"], "",
              "Canonical implementation:", ""]
    lines += ["- `%s`" % c for c in canonical] or [
        "- none yet — see the wrapper status below"]
    if m.get("will_consume"):
        lines += ["", "Existing machinery the missing implementation will consume:", ""]
        lines += ["- `%s`" % c for c in m["will_consume"]]
    lines += ["", wrapper_note, "", "## Outputs", ""]
    lines += ["- `%s`" % o for o in outputs] or ["- none"]
    lines += ["", "## Dependencies", ""]
    lines += ["- `%s`" % d for d in deps] or ["- none"]
    lines += [
        "", "## How to run", "",
        "```bat",
        "REM from anywhere",
        "%s\\%s\\run.bat" % (m["category"], folder_name(m)),
        "```", "",
        "```bash",
        "# equivalently, without the .bat layer",
        "python scripts/run_module.py --module %s%s"
        % (m["id"], " --force" if m["wrapper_status"] == "WRAPS_EXISTING_PROTECTED"
           else ""),
        "```", "",
        "Verify the wiring without executing anything:", "",
        "```bash",
        "python scripts/run_module.py --module %s --check" % m["id"],
        "```", "",
        "## Reproducibility", "",
        "Every run appends a record to `logs/%s/%s.jsonl` carrying the module id, "
        "status, message, outputs, adapter, canonical implementation, git commit, "
        "environment snapshot and elapsed time." % (m["category"].lower(),
                                        m["id"].lower().replace("-", "_")),
        "",
        "## Limitations", "",
    ]
    notes = (m.get("notes") or "").strip()
    lines += [notes or "None recorded beyond those listed in the table above."]
    if lims:
        lines += ["", "See `docs/LIMITATIONS.md` for %s."
                  % ", ".join("**%s**" % x for x in lims)]
    lines += ["", "## Status", "",
              "`%s` / `%s`" % (m["wrapper_status"], m["status"]), ""]
    return "\n".join(lines)


def render_master(manifest: dict, category: str) -> str:
    mods = sorted([m for m in manifest["modules"] if m["category"] == category],
                  key=lambda m: m["index"])
    n = len(mods)
    label = {"STATS": "STATISTICS", "MULTIMODAL": "MULTIMODAL",
             "PRODUCT": "PRODUCT"}.get(category, category)
    out = [
        "@echo off",
        "REM %s" % BANNER,
        "REM Master runner for the %d %s modules, in dependency-safe order."
        % (n, category),
        "setlocal EnableDelayedExpansion",
        'for %%I in ("%~dp0..") do set "AEGIS_ROOT=%%~fI"',
        "",
        "set /a PASS=0",
        "set /a FAIL=0",
        "set /a SKIP=0",
        "set /a BLOCK=0",
        "set /a PENDING=0",
        'set "FAILED_LIST="',
        "",
        "echo ============================================================",
        "echo  %s PIPELINE  (%d modules)" % (label, n),
        "echo ============================================================",
        "",
    ]
    for i, m in enumerate(mods, start=1):
        folder = folder_name(m)
        out += [
            "echo.",
            "echo [%02d/%d] %s  %s" % (i, n, m["id"], m["name"]),
            'call "%%AEGIS_ROOT%%\\%s\\%s\\run.bat" %%*' % (category, folder),
            'set "RC=!ERRORLEVEL!"',
            'if "!RC!"=="0" ( set /a PASS+=1 ) else if "!RC!"=="5" ( set /a SKIP+=1 ) '
            'else if "!RC!"=="6" ( set /a PENDING+=1 ) '
            'else if "!RC!"=="3" ( set /a BLOCK+=1 ) '
            'else ( set /a FAIL+=1 & set "FAILED_LIST=!FAILED_LIST! %s" )' % m["id"],
            "",
        ]
    out += [
        "echo.",
        "echo ============================================================",
        "echo  %s PIPELINE SUMMARY" % label,
        "echo ============================================================",
        "echo   Successful          : !PASS!",
        "echo   Failed              : !FAIL!",
        "echo   Skipped (protected) : !SKIP!",
        "echo   Blocked             : !BLOCK!",
        "echo   Not yet executed    : !PENDING!",
        'if not "!FAILED_LIST!"=="" echo   Failed modules      :!FAILED_LIST!',
        "echo ============================================================",
        "",
        "REM A pipeline with any failed module never reports success. Skipped and",
        "REM not-yet-executed modules are expected states, not failures.",
        'if !FAIL! GTR 0 ( echo [aegis] %s PIPELINE: FAILED & exit /b 1 )' % label,
        "echo [aegis] %s PIPELINE: OK" % label,
        "exit /b 0",
        "",
    ]
    return "\n".join(out)


def render_root_master() -> str:
    return "\n".join([
        "@echo off",
        "REM %s" % BANNER,
        "REM Full research pipeline: statistics, then multimodal.",
        "REM",
        "REM Local Windows research tool only. This is NOT part of the Vercel build:",
        "REM the deployed product consumes exported artifacts and never runs this.",
        "setlocal EnableDelayedExpansion",
        'for %%I in ("%~dp0.") do set "AEGIS_ROOT=%%~fI"',
        "",
        "echo ############################################################",
        "echo  AEGIS-MARKET FULL RESEARCH PIPELINE",
        "echo ############################################################",
        "",
        'call "%AEGIS_ROOT%\\STATS\\run_all_stats.bat" %*',
        'set "RC_STATS=!ERRORLEVEL!"',
        "",
        'call "%AEGIS_ROOT%\\MULTIMODAL\\run_all_multimodal.bat" %*',
        'set "RC_MM=!ERRORLEVEL!"',
        "",
        "echo.",
        "echo ############################################################",
        "echo  FULL RESEARCH PIPELINE SUMMARY",
        "echo ############################################################",
        'if "!RC_STATS!"=="0" ( echo   STATS      : OK )'
        ' else ( echo   STATS      : FAILED )',
        'if "!RC_MM!"=="0" ( echo   MULTIMODAL : OK )'
        ' else ( echo   MULTIMODAL : FAILED )',
        "echo ############################################################",
        "",
        "REM Success requires both pipelines. One failing half is not a success.",
        'if not "!RC_STATS!"=="0" ( echo [aegis] FULL PIPELINE: FAILED & exit /b 1 )',
        'if not "!RC_MM!"=="0" ( echo [aegis] FULL PIPELINE: FAILED & exit /b 1 )',
        "echo [aegis] FULL PIPELINE: OK",
        "exit /b 0",
        "",
    ])


def render_product_entry(manifest: dict) -> str:
    """Root convenience runner for local product deployment.

    Ordered so that a fresh clone reaches a served page in one command: install, export
    the bundles the app reads, build, verify every route prerendered, then serve. The
    export step is protected, so this runner passes --force to it deliberately and says
    so; nothing else here can touch a research artifact.
    """
    return "\n".join([
        "@echo off",
        "REM %s" % BANNER,
        "REM Local product deployment: install -> export -> build -> verify -> serve.",
        "REM",
        "REM This is a LOCAL server. No Vercel deployment has been performed (L-03).",
        "setlocal EnableDelayedExpansion",
        'for %%I in ("%~dp0.") do set "AEGIS_ROOT=%%~fI"',
        "",
        "echo ############################################################",
        "echo  AEGIS-MARKET LOCAL PRODUCT DEPLOYMENT",
        "echo ############################################################",
        "",
        r'call "%AEGIS_ROOT%\PRODUCT\01_install_dependencies\run.bat" || exit /b 1',
        "REM --force: the exporter rewrites public/data, which is a protected output.",
        r'call "%AEGIS_ROOT%\PRODUCT\04_export_app_data\run.bat" --force || exit /b 1',
        r'call "%AEGIS_ROOT%\PRODUCT\05_build\run.bat" || exit /b 1',
        r'call "%AEGIS_ROOT%\PRODUCT\06_verify_routes\run.bat" || exit /b 1',
        "",
        "echo.",
        "echo [aegis] build verified. Starting the local production server.",
        "echo [aegis] open http://localhost:3000  (Ctrl-C to stop)",
        "echo.",
        r'call "%AEGIS_ROOT%\PRODUCT\08_start_server\run.bat"',
        "exit /b %ERRORLEVEL%",
        "",
    ])


def app_routes() -> list[tuple[str, str]]:
    """(route path, folder slug) for every page and API route in the app directory."""
    app = REPO_ROOT / "app"
    out: list[tuple[str, str]] = []
    for pattern in ("page.tsx", "route.ts"):
        for f in sorted(app.rglob(pattern)):
            rel = f.parent.relative_to(app).as_posix()
            route = "/" if rel == "." else "/" + rel
            slug = "root" if rel == "." else rel.replace("/", "__").replace(
                "[", "_").replace("]", "_")
            out.append((route, slug))
    return sorted(set(out), key=lambda t: t[0])


def render_route_bat(route: str, slug: str) -> str:
    """A runner that serves the product and opens this one route.

    Every route gets its own entry point so a reviewer can go straight to the page they
    care about. Each one starts the same dev server -- Next.js serves the whole
    application, a single route cannot be served in isolation -- and then opens the
    browser at this route. Saying that plainly in the header matters: a file called
    run.bat inside a route folder would otherwise imply the route runs on its own.
    """
    api = route.startswith("/api/")
    return "\n".join([
        "@echo off",
        "REM %s" % BANNER,
        "REM Route: %s" % route,
        "REM",
        "REM Starts the development server for the WHOLE application and opens this",
        "REM route. Next.js serves the app as a unit; no single route runs alone.",
        "REM Stop the server with Ctrl-C.",
        "setlocal",
        r'for %%I in ("%~dp0..\..\..") do set "AEGIS_ROOT=%%~fI"',
        "set \"AEGIS_ROUTE=%s\"" % route,
        "echo [aegis] route  : %AEGIS_ROUTE%",
        "echo [aegis] opening: http://localhost:3000%AEGIS_ROUTE%",
        ("echo [aegis] note   : this is an API route; it returns JSON." if api
         else "echo [aegis] note   : the server serves every route, not only this."),
        "start \"\" http://localhost:3000%AEGIS_ROUTE%",
        r'call "%AEGIS_ROOT%\PRODUCT\07_dev_server\run.bat"',
        "exit /b %ERRORLEVEL%",
        "",
    ])


def render_route_readme(route: str) -> str:
    return "\n".join([
        "<!-- %s -->" % BANNER,
        "# Route `%s`" % route,
        "",
        "`run.bat` here starts the development server for the whole application",
        "and opens this route in a browser. Next.js serves the app as a unit, so this",
        "is a shortcut to one page rather than an isolated server for it.",
        "",
        "Equivalent commands:",
        "",
        "```bat",
        "PRODUCT\07_dev_server\run.bat        REM dev server, hot reload",
        "run_product.bat                       REM install, export, build, verify, serve",
        "```",
        "",
        "The page renders from the exported bundles in `public/data/`. No model runs in",
        "the request path.",
        "",
    ])


# ------------------------------------------------------------ the weekly tree ----
#
# `weeks/week_1 .. weeks/week_16`, generated from the `weeks:` block the same way
# `STATS/` and `MULTIMODAL/` are generated from `modules:`. The folder is a launcher and
# a contract, not a copy of the interface: the page itself is one Next.js route
# (`app/weeks/[week]/page.tsx`) because sixteen copies of it would be sixteen things to
# keep in agreement.
#
# One run.bat per week, and it brings up the whole vertical slice: the Python analysis
# service, the interface, and a browser on that week's page. Both experiences live in
# that one page and the toggle switches between them, so there is no second runner for
# "the research view" -- a second runner would imply a second page, which would be the
# thing the two-mode design exists to avoid.


def week_dir(week: int) -> Path:
    return REPO_ROOT / "weeks" / ("week_%d" % week)


def _week_payloads() -> list[dict]:
    """Every week as the backend derives it. Deterministic: no timestamps, no paths."""
    from backend import registry as reg

    return [reg.week_payload(w.week) for w in reg.weeks()]


def render_week_bat(week: dict) -> str:
    """Start the analysis backend, the interface, and this week's page.

    Three things happen and each is stated in the window, because a runner that silently
    starts two servers is one nobody can debug:

    * the backend is started only if nothing is already listening on its port, so running
      two weeks in a row does not leave two services fighting over it;
    * the interface runs in the foreground of this window, so Ctrl-C stops it;
    * the browser is opened by a detached waiter that polls until the interface answers,
      rather than immediately -- opening a page before the server is up shows a
      connection error and teaches the reader that the tool is broken.
    """
    number = week["week"]
    ids = [week["stats_module"], week["multimodal_module"]]
    lines = [
        "@echo off",
        "REM %s" % BANNER,
        "REM Week %d - %s" % (number, week["title"]),
        "REM",
    ]
    for module_id in ids:
        spec = next(m for m in week["modules"] if m["module_id"] == module_id)
        mode = ("live computation, about %gs"
                % spec["analysis"]["typical_seconds"] if spec["analysis"]["is_live"]
                else "verified artifact replay")
        lines.append("REM   %-14s %-42s (%s)"
                     % (module_id, spec["name"][:42], mode))
    lines += [
        "REM",
        "REM Starts the analysis backend and the interface, then opens this week's page.",
        "REM Both the product and the research view are in that one page; the toggle in",
        "REM the masthead switches between them without leaving it.",
        "REM",
        "REM   run.bat            open in product mode",
        "REM   run.bat research   open in research mode",
        "REM   run.bat product    same as no argument",
        "REM",
        "REM Set AEGIS_NO_BROWSER=1 to start the services without opening a page. That",
        "REM is what lets the capability audit run this file for real rather than",
        "REM reading it: sixteen launchers can be started and checked without sixteen",
        "REM browser windows. It changes nothing else.",
        "REM",
        "REM The whole system is in this repository. AEGIS_ACTIVE_WEEK decides how",
        "REM much of it this run exposes: week %d enables %s and gates"
        % (number, "week 1 only" if number == 1 else "weeks 1 to %d" % number),
        "REM the rest, in the interface and in the backend both. Nothing is deleted,",
        "REM stubbed or hidden - a gated week answers with FEATURE_NOT_ENABLED and",
        "REM says which week would show it.",
        "setlocal",
        r'for %%I in ("%~dp0..\..") do set "AEGIS_ROOT=%%~fI"',
        "",
        "REM -- what this demonstration exposes ---------------------------------------",
        "set AEGIS_ACTIVE_WEEK=%d" % number,
        "",
        'if "%AEGIS_BACKEND_PORT%"=="" set AEGIS_BACKEND_PORT=8787',
        'if "%AEGIS_FRONTEND_PORT%"=="" set AEGIS_FRONTEND_PORT=3000',
        'if "%AEGIS_BACKEND_URL%"=="" set '
        "AEGIS_BACKEND_URL=http://127.0.0.1:%AEGIS_BACKEND_PORT%",
        "",
        'set "AEGIS_PY=%AEGIS_ROOT%\\.venv\\Scripts\\python.exe"',
        'if not exist "%AEGIS_PY%" set "AEGIS_PY=python"',
        "",
        # Batch expands %VAR% itself, so the percent signs stay literal here: these
        # lines are assembled by concatenation rather than by `%`-formatting, which
        # would try to read `%AEGIS_...` as a format specifier.
        'set "AEGIS_WEEK_URL=http://localhost:%AEGIS_FRONTEND_PORT%/weeks/'
        + str(number) + '?mode=product"',
        'if /I "%~1"=="research" set "AEGIS_WEEK_URL=http://localhost:'
        '%AEGIS_FRONTEND_PORT%/weeks/' + str(number) + '?mode=research"',
        "",
        "echo [week %d] %s" % (number, week["title"]),
        "echo [week %d] modules : %s" % (number, " + ".join(ids)),
        "echo [week %d] page    : %%AEGIS_WEEK_URL%%" % number,
        "echo [week %d] backend : %%AEGIS_BACKEND_URL%%" % number,
        "echo [week %d] exposing: %s of 16 (AEGIS_ACTIVE_WEEK=%d)"
        % (number, "week 1" if number == 1 else "weeks 1-%d" % number, number),
        "echo.",
        "",
        "REM -- the analysis backend, only if nothing is already serving it ------------",
        'powershell -NoProfile -Command "try{$c=New-Object Net.Sockets.TcpClient;'
        "$c.Connect('127.0.0.1',$env:AEGIS_BACKEND_PORT);$c.Close();exit 0}"
        'catch{exit 1}" >nul 2>&1',
        "if errorlevel 1 (",
        "  echo [week %d] starting the analysis backend on port "
        "%%AEGIS_BACKEND_PORT%%" % number,
        # The active week is written out rather than passed through as
        # %%AEGIS_ACTIVE_WEEK%%. `start` inherits the environment anyway, so a
        # pass-through would be a no-op that reads like a safeguard; the literal says
        # what the backend will actually enforce and can be checked by reading the file.
        '  start "aegis backend" /d "%AEGIS_ROOT%" cmd /k "set '
        'AEGIS_ACTIVE_WEEK=' + str(number) + ' && "%AEGIS_PY%" '
        '-m backend.server --port %AEGIS_BACKEND_PORT%"',
        ") else (",
        "  echo [week %d] analysis backend already listening on port "
        "%%AEGIS_BACKEND_PORT%%" % number,
        ")",
        "",
        "REM -- open the page once the interface answers, not before -------------------",
        'if not "%AEGIS_NO_BROWSER%"=="1" (',
        '  start "" /min powershell -NoProfile -Command "for($i=0;$i -lt 90;$i++){'
        "try{$c=New-Object Net.Sockets.TcpClient;"
        "$c.Connect('127.0.0.1',$env:AEGIS_FRONTEND_PORT);$c.Close();"
        "Start-Process $env:AEGIS_WEEK_URL;break}"
        'catch{Start-Sleep -Seconds 1}}"',
        ") else (",
        "  echo [week %d] AEGIS_NO_BROWSER=1, so no page will be opened" % number,
        ")",
        "",
        "REM -- the interface, in this window, so Ctrl-C stops it ----------------------",
        'pushd "%AEGIS_ROOT%"',
        # The port is passed through rather than left to the default: it is the port the
        # URL above names and the port the waiter polls, and three places that must agree
        # are three places that can disagree.
        "call npm run dev -- --port %AEGIS_FRONTEND_PORT%",
        "popd",
        "exit /b %ERRORLEVEL%",
        "",
    ]
    return "\n".join(lines)


def render_week_readme(week: dict) -> str:
    number = week["week"]
    ids = [week["stats_module"], week["multimodal_module"]]
    rows = []
    for module_id in ids:
        spec = next(m for m in week["modules"] if m["module_id"] == module_id)
        analysis = spec["analysis"]
        rows.append("| `%s` | %s | %s | `%s` |"
                    % (module_id, spec["name"],
                       ("live, about %gs" % analysis["typical_seconds"])
                       if analysis["is_live"] else "verified artifact",
                       # The analysis adapter, not the regenerating one: naming the
                       # writing path beside a live module would point a reader at the
                       # code this page is built never to reach.
                       analysis["adapter"] if analysis["is_live"] else "replay"))

    inputs = []
    for module_id in ids:
        for i in week["input_schema"].get(module_id, []):
            bounds = (" \\| ".join(i["options"]) if i["options"]
                      else " … ".join(str(b) for b in (i["minimum"], i["maximum"])
                                      if b is not None)
                      or ("at most %d" % i["max_items"] if i["max_items"] else "—"))
            default = i["default"]
            shown = ("(none)" if default in (None, "", [])
                     else ", ".join(str(v) for v in default)
                     if isinstance(default, list) else str(default))
            inputs.append("| `%s` | `%s` | %s | %s | `%s` |"
                          % (module_id, i["name"], i["kind"], bounds, shown))

    artifacts = []
    for module_id in ids:
        for path in week["artifact_sources"].get(module_id, []):
            artifacts.append("| `%s` | `%s` |" % (module_id, path))

    live = [m for m in ids if week["execution"][m]["is_live"]]
    replayed = [m for m in ids if not week["execution"][m]["is_live"]]

    lines = [
        "<!-- %s -->" % BANNER,
        "# Week %d — %s" % (number, week["title"]),
        "",
        week["question"].strip(),
        "",
        week["summary"].strip(),
        "",
        "## Run it",
        "",
        "```bat",
        "run.bat            REM backend + interface + this week's page, product view",
        "run.bat research   REM the same page, opened in research view",
        "```",
        "",
        "One page holds both experiences and the masthead toggle switches between",
        "them: the numbers are identical, the depth of presentation is not. Product",
        "mode leads with what was found; research mode adds the tables, the slice that",
        "was read, the inputs the service accepted and the provenance of what ran.",
        "",
        "The backend is started only if nothing is already listening on its port, so",
        "running a second week does not leave two services competing for it. Ctrl-C in",
        "this window stops the interface; close the backend window to stop that.",
        "",
        "## The two halves",
        "",
        "| Module | Name | Execution | Adapter |",
        "|---|---|---|---|",
        *rows,
        "",
    ]
    if replayed:
        lines += [
            "`%s` does not compute on request: %s"
            % (replayed[0], week["execution"][replayed[0]]["artifact_reason"]),
            "Its stored, provenance-stamped result is served instead and is labelled",
            "as a replay, never as something computed for the request.",
            "",
        ]
    if live:
        lines += [
            ("`%s` runs the canonical implementation over the slice you choose and "
             "writes nothing." % live[0]) if len(live) == 1 else
            ("`%s` and `%s` both run the canonical implementation over the slice you "
             "choose, and neither writes anything." % (live[0], live[1])),
            "",
        ]

    lines += [
        "## What you can change",
        "",
        "| Module | Parameter | Kind | Accepted | Default |",
        "|---|---|---|---|---|",
        *inputs,
        "",
        "These are the same declarations `backend/registry.py` validates against, so",
        "a control that appears here is a value the service accepts. Anything outside",
        "the accepted range comes back as a refusal with a reason and a remedy, rather",
        "than as a silently substituted default.",
        "",
        "## Where the numbers come from",
        "",
        "```",
        "the page            app/weeks/[week]/page.tsx  ->  /weeks/%d" % number,
        "the request         POST %s" % week["backend_routes"]["run_week"],
        "validation          backend/registry.py",
        "dispatch            backend/service.py",
        "the adapters        scripts/stages/  (dispatch only, no research logic)",
        "the implementation  research/",
        "```",
        "",
        "## Artifacts these modules own",
        "",
        "| Module | Path |",
        "|---|---|",
        *artifacts,
        "",
        "Nothing reachable from this page can overwrite them. Regenerating an artifact",
        "is a deliberate terminal command against the module's own runner under",
        "`STATS/` or `MULTIMODAL/`.",
        "",
        "## Without a backend",
        "",
        "The page still renders and still shows results — the stored ones, labelled",
        "*Verified experiment result*, with a notice saying the inputs on the form were",
        "not applied and nothing was computed. A stored number is never shown under a",
        "live label.",
        "",
    ]
    return "\n".join(lines)


def render_weeks_readme(weeks: list[dict]) -> str:
    rows = []
    for w in weeks:
        ids = [w["stats_module"], w["multimodal_module"]]
        live = sum(1 for m in ids if w["execution"][m]["is_live"])
        rows.append("| [`week_%d`](week_%d/) | %s | `%s` + `%s` | %s |"
                    % (w["week"], w["week"], w["title"], ids[0], ids[1],
                       "both live" if live == 2
                       else "one live, one replayed" if live == 1 else "both replayed"))
    return "\n".join([
        "<!-- %s -->" % BANNER,
        "# The sixteen weeks",
        "",
        "One folder per week. Each holds a `run.bat` that brings up the analysis",
        "backend, the interface and that week's page, and a `README.md` naming its two",
        "modules, the parameters they accept and the artifacts they own.",
        "",
        "A week is a pairing rather than a unit of code: the statistical treatment and",
        "the modality it is applied to were designed together and are read together.",
        "The implementation lives where it always did — `research/` for the science,",
        "`scripts/stages/` for the adapters, and `app/weeks/[week]/page.tsx` for the",
        "one page that renders any of them. These folders are entry points, not copies.",
        "",
        "| Folder | What the week asks | Modules | Execution |",
        "|---|---|---|---|",
        *rows,
        "",
        "```bat",
        "weeks\\week_1\\run.bat            REM product view of week 1",
        "weeks\\week_1\\run.bat research   REM research view of the same page",
        "run_dev.bat                     REM backend + interface, no particular week",
        "```",
        "",
        "Both experiences are in the one page. Switching between them is a change of",
        "depth, not of place: the toggle never navigates away, and never changes a",
        "number.",
        "",
        "Generated from the `weeks:` block of `research_modules.yaml` by",
        "`python scripts/validate_structure.py --write`. Editing a file here by hand is",
        "reported as drift on the next validation run.",
        "",
    ])


def render_week_wrapper(week: int) -> str:
    """A one-line delegation to the canonical launcher.

    The canonical weekly launcher is ``weeks\\week_N\\run.bat``: it sits next to
    that week's README and its exported payload, which is where someone looking for week
    N looks. These root wrappers exist because the run_week_NN.bat name was asked for and
    is easier to type from the repository root. They carry no logic of their own, so there
    is nothing in them that can disagree with the launcher they call.
    """
    inner = "weeks\\week_%d\\run.bat" % week
    return "\n".join([
        "@echo off",
        "REM %s" % BANNER,
        "REM Week %d, from the repository root." % week,
        "REM",
        "REM   run_week_%02d.bat            product view" % week,
        "REM   run_week_%02d.bat research   research view of the same page" % week,
        "REM",
        "REM This is a wrapper. The launcher is %s, and every argument" % inner,
        "REM is passed straight to it.",
        'call "%~dp0' + inner + '" %*',
        "exit /b %ERRORLEVEL%",
        "",
    ])


def generated_files(manifest: dict) -> dict[Path, str]:
    files: dict[Path, str] = {}
    for m in manifest["modules"]:
        d = module_dir(m)
        files[d / "run.bat"] = render_run_bat(m)
        files[d / "README.md"] = render_readme(m)
    for cat, meta in manifest["categories"].items():
        master = REPO_ROOT / meta["master"]
        files[master] = render_master(manifest, cat)
    files[REPO_ROOT / "run_all_research.bat"] = render_root_master()
    files[REPO_ROOT / "run_product.bat"] = render_product_entry(manifest)
    for route, slug in app_routes():
        d = REPO_ROOT / "PRODUCT" / "routes" / slug
        files[d / "run.bat"] = render_route_bat(route, slug)
        files[d / "README.md"] = render_route_readme(route)

    weeks = _week_payloads()
    for week in weeks:
        d = week_dir(week["week"])
        files[d / "run.bat"] = render_week_bat(week)
        files[d / "README.md"] = render_week_readme(week)
        files[d / "week.json"] = json.dumps(week, indent=2, sort_keys=True) + chr(10)
        files[REPO_ROOT / ("run_week_%02d.bat" % week["week"])] = render_week_wrapper(
            week["week"])
    files[REPO_ROOT / "weeks" / "README.md"] = render_weeks_readme(weeks)
    return files


def write(manifest: dict) -> int:
    files = generated_files(manifest)
    written = 0
    for path, body in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        # CRLF: these are Windows batch files and .md files sitting beside them.
        payload = body.replace("\r\n", "\n").replace("\n", "\r\n")
        if path.exists() and path.read_bytes() == payload.encode("utf-8"):
            continue
        path.write_bytes(payload.encode("utf-8"))
        written += 1
    for sub in ("logs/stats", "logs/multimodal", "outputs/stats", "outputs/multimodal"):
        (REPO_ROOT / sub).mkdir(parents=True, exist_ok=True)
    print("wrote/updated %d of %d generated files" % (written, len(files)))
    return 0


# --------------------------------------------------------------- validation ----

def validate_weeks(manifest: dict) -> list[str]:
    """The weekly tree must be exactly the weeks the manifest declares.

    A folder with no week behind it is the failure this checks for: it would carry a
    runner pointing at a page that does not exist, and nothing else would notice.
    """
    problems: list[str] = []
    declared = manifest.get("weeks") or []
    if not declared:
        return ["the manifest declares no weeks: block"]

    numbers = sorted(int(w["week"]) for w in declared)
    if numbers != list(range(1, len(numbers) + 1)):
        problems.append("week numbers are %s, expected 1..%d"
                        % (numbers, len(numbers)))

    ids = {m["id"] for m in manifest["modules"]}
    for w in declared:
        for key in ("stats_module", "multimodal_module"):
            if w[key] not in ids:
                problems.append("week %s names unknown module %s" % (w["week"], w[key]))

    root = REPO_ROOT / "weeks"
    if not root.is_dir():
        problems.append("weeks/ does not exist")
        return problems

    on_disk = sorted(p.name for p in root.iterdir()
                     if p.is_dir() and not p.name.startswith("."))
    expected = sorted("week_%d" % n for n in numbers)
    if on_disk != expected:
        problems.append("weeks/ directories %s do not match the manifest %s"
                        % (on_disk, expected))

    for n in numbers:
        d = week_dir(n)
        for required in ("run.bat", "README.md", "week.json"):
            if not (d / required).is_file():
                problems.append("week_%d: missing %s" % (n, required))
    return problems


def validate(manifest: dict) -> list[str]:
    problems: list[str] = []
    mods = manifest["modules"]

    ids = [m["id"] for m in mods]
    if len(set(ids)) != len(ids):
        problems.append("duplicate module ids in the manifest")

    for cat, meta in manifest["categories"].items():
        root = REPO_ROOT / meta["directory"]
        if not root.is_dir():
            problems.append("%s/ does not exist" % cat)
            continue
        cat_mods = [m for m in mods if m["category"] == cat]
        # The research categories are fixed at 16 by the approved mapping; a category may
        # declare its own count, which is how PRODUCT coexists without changing it.
        expected_n = int(meta.get("expected_modules", 16))
        if len(cat_mods) != expected_n:
            problems.append("%s declares %d modules, expected exactly %d"
                            % (cat, len(cat_mods), expected_n))
        idx = sorted(m["index"] for m in cat_mods)
        if idx != list(range(1, expected_n + 1)):
            problems.append("%s indices are %s, expected 1..%d" % (cat, idx, expected_n))
        on_disk = sorted(p.name for p in root.iterdir()
                         if p.is_dir() and not p.name.startswith(".")
                         and p.name != "routes")
        expected = sorted(folder_name(m) for m in cat_mods)
        if on_disk != expected:
            problems.append("%s/ directories %s do not match the manifest %s"
                            % (cat, on_disk, expected))
        master = REPO_ROOT / meta["master"]
        if not master.is_file():
            problems.append("missing master runner %s" % master.relative_to(REPO_ROOT))

    if not (REPO_ROOT / "run_all_research.bat").is_file():
        problems.append("missing run_all_research.bat")

    problems.extend(validate_weeks(manifest))

    for m in mods:
        d = module_dir(m)
        for required in ("run.bat", "README.md"):
            if not (d / required).is_file():
                problems.append("%s: missing %s" % (m["id"], required))

        try:
            mod_name, _, func = m["adapter"].partition(":")
            fn = getattr(importlib.import_module(mod_name), func)
            if not callable(fn):
                problems.append("%s: adapter %s is not callable"
                                % (m["id"], m["adapter"]))
        except Exception as exc:
            problems.append("%s: adapter %s not importable (%s: %s)"
                            % (m["id"], m["adapter"], type(exc).__name__, exc))

        for c in list(m["canonical"]) + list(m.get("will_consume") or []):
            file_part = c.split("::", 1)[0]
            if not (REPO_ROOT / file_part).exists():
                problems.append("%s: canonical path %s does not exist"
                                % (m["id"], file_part))

        for dep in m.get("depends_on") or []:
            if dep not in ids:
                problems.append("%s: depends_on unknown module %s" % (m["id"], dep))

        if m["wrapper_status"] == "INFRASTRUCTURE_ONLY" and m["canonical"]:
            problems.append("%s: marked INFRASTRUCTURE_ONLY but names canonical code"
                            % m["id"])
        if m["wrapper_status"] != "INFRASTRUCTURE_ONLY" and not m["canonical"]:
            problems.append("%s: claims to wrap existing code but names none" % m["id"])

    # Dependency cycles.
    graph = {m["id"]: list(m.get("depends_on") or []) for m in mods}
    state: dict[str, int] = {}

    def visit(node: str, trail: list[str]) -> None:
        if state.get(node) == 2:
            return
        if state.get(node) == 1:
            problems.append("dependency cycle: %s" % " -> ".join([*trail, node]))
            return
        state[node] = 1
        for nxt in graph.get(node, []):
            visit(nxt, [*trail, node])
        state[node] = 2

    for node in graph:
        visit(node, [])

    # Drift: generated files must match what the manifest would produce.
    for path, body in generated_files(manifest).items():
        if not path.exists():
            continue
        want = body.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")
        if path.read_bytes() != want:
            problems.append("%s has drifted from the manifest; re-run with --write"
                            % path.relative_to(REPO_ROOT).as_posix())
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="regenerate the structure from the manifest")
    args = ap.parse_args()

    manifest = load()
    if args.write:
        write(manifest)

    problems = validate(manifest)
    n_mods = len(manifest["modules"])
    print("structural validation over %d modules" % n_mods)
    if problems:
        print("FAILED: %d problem(s)" % len(problems))
        for p in problems:
            print("  - %s" % p)
        return 1
    shape = ", ".join("%d %s" % (sum(1 for m in manifest["modules"]
                                      if m["category"] == c), c)
                      for c in manifest["categories"])
    print("OK: %s; every run.bat and README present, every adapter importable, every "
          "canonical path exists, no cycles, no drift" % shape)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
