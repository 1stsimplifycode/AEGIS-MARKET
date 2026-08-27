"""PRODUCT module adapters: local deployment of the Next.js application.

The research pipeline and the product are deliberately separate tracks that meet only at
``public/data/*.json``. These adapters drive the product half locally — install, check,
export, build, verify, serve — and never touch the research pipeline.

Every product module is a **declared command** in the manifest rather than bespoke Python,
so the manifest stays the single source of truth for what each module runs. The adapter's
only jobs are resolving the toolchain and reporting the outcome honestly.

Node resolution is the fiddly part on Windows. ``npm`` is frequently installed somewhere
that is on the *user* PATH but absent from the environment a shell inherits, so the
resolver checks an explicit override, then the PATH, then the standard winget and Program
Files locations, and reports BLOCKED with instructions rather than failing obscurely.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from research.core import jsonio, paths
from scripts.stages import BLOCKED, OK, StageResult

#: Locations to search when npm is not already on PATH. Ordered by how likely they are to
#: be the installation a developer actually uses.
NODE_SEARCH_GLOBS = [
    r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\OpenJS.NodeJS*\*",
    r"%ProgramFiles%\nodejs",
    r"%ProgramFiles(x86)%\nodejs",
    r"%LOCALAPPDATA%\Programs\nodejs",
    r"%APPDATA%\npm",
]


def _out(slug: str) -> Path:
    d = paths.REPO_ROOT / "outputs" / "product" / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_node_bin() -> Path | None:
    """Directory containing npm/node, or None when the toolchain is unavailable."""
    override = os.environ.get("AEGIS_NODE_BIN")
    if override and (Path(override) / "npm.cmd").exists():
        return Path(override)

    found = shutil.which("npm") or shutil.which("npm.cmd")
    if found:
        return Path(found).parent

    for pattern in NODE_SEARCH_GLOBS:
        expanded = os.path.expandvars(pattern)
        if "%" in expanded:            # an unset variable; nothing to search
            continue
        parts = Path(expanded).parts
        # Split at the first wildcard: everything before it is a real directory to glob
        # from, everything after is the glob. Globbing from the parent of the last
        # component only works when the wildcard is in that component, which is not the
        # case for the winget layout (.../OpenJS.NodeJS*/node-v*-win-x64).
        wild = next((i for i, p in enumerate(parts)
                     if any(ch in p for ch in "*?")), None)
        if wild is None:
            candidates = [Path(expanded)]
        else:
            root = Path(*parts[:wild])
            tail = "/".join(parts[wild:])
            if not root.exists():
                continue
            candidates = sorted(root.glob(tail))
        for c in candidates:
            if (c / "npm.cmd").exists() or (c / "npm").exists():
                return c
    return None


def _node_env() -> tuple[dict | None, str | None]:
    """An environment with npm on PATH, or a message explaining why there is none."""
    bin_dir = resolve_node_bin()
    if bin_dir is None:
        return None, (
            "Node.js was not found. Install it, or set AEGIS_NODE_BIN to the directory "
            "containing npm.cmd. Searched PATH and the standard winget and Program "
            "Files locations.")
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    return env, None


def run_command(force: bool = False, *, module: dict | None = None) -> StageResult:
    """Execute the command declared for this module in the manifest.

    ``module`` is injected by the dispatcher. Keeping the command in the manifest rather
    than in this file means the README, the run.bat header and the executed command can
    never disagree about what a module does.
    """
    if module is None:
        return StageResult(1, "no module spec was passed to the product adapter")

    command = module.get("command")
    if not command:
        return StageResult(1, "%s declares no command" % module["id"])

    needs_node = bool(module.get("needs_node", True))
    env = None
    if needs_node:
        env, problem = _node_env()
        if problem:
            return StageResult(BLOCKED, problem)

    slug = "%02d_%s" % (module["index"], module["slug"])
    out = _out(slug)
    long_running = bool(module.get("long_running"))

    if long_running:
        print("  this module runs in the foreground until you stop it with Ctrl-C")

    proc = subprocess.run(command, cwd=str(paths.REPO_ROOT), env=env, shell=True)
    record = {
        "module": module["id"],
        "command": command,
        "returncode": proc.returncode,
        "long_running": long_running,
        "node_bin": str(resolve_node_bin()) if needs_node else None,
    }
    jsonio.write(out / "run.json", record)

    if proc.returncode != 0:
        # A server stopped with Ctrl-C reports a non-zero code on Windows; that is the
        # user ending it, not a failure of the module.
        if long_running:
            return StageResult(OK, "server stopped (exit %d)" % proc.returncode,
                               outputs=[str(out / "run.json")], detail=record)
        return StageResult(1, "%s exited %d" % (command, proc.returncode),
                           outputs=[str(out / "run.json")], detail=record)
    return StageResult(OK, "%s" % command, outputs=[str(out / "run.json")],
                       detail=record)


def verify_routes(force: bool = False, *, module: dict | None = None) -> StageResult:
    """Confirm every route in the app directory was prerendered by the last build.

    Checks the build output rather than starting a server: a prerendered page that is
    missing from ``.next/server/app`` would be served dynamically at request time, which
    is the failure this project's static-artifact architecture exists to avoid.
    """
    app = paths.REPO_ROOT / "app"
    built = paths.REPO_ROOT / ".next" / "server" / "app"
    out = _out("%02d_%s" % (module["index"], module["slug"])) if module \
        else _out("06_verify_routes")

    if not built.exists():
        return StageResult(4, "no build output at .next/server/app; run the build module "
                              "first")

    pages = sorted(app.rglob("page.tsx"))
    rows, missing = [], []
    for p in pages:
        rel = p.parent.relative_to(app).as_posix()
        route = "/" if rel == "." else "/" + rel
        dynamic = "[" in rel
        if dynamic:
            # A dynamic segment prerenders one file per parameter, so presence of the
            # directory is the check rather than a single named file.
            ok = (built / rel.split("/[")[0]).exists()
        else:
            ok = (built / (rel + ".html")).exists() or (built / rel).exists() \
                if rel != "." else (built / "index.html").exists()
        rows.append({"route": route, "dynamic": dynamic, "prerendered": bool(ok)})
        if not ok:
            missing.append(route)

    html_files = list(built.rglob("*.html"))
    record = {"routes_declared": len(rows), "routes_missing": missing,
              "prerendered_html_files": len(html_files), "routes": rows}
    jsonio.write(out / "route_verification.json", record)

    if missing:
        return StageResult(1, "%d route(s) not prerendered: %s"
                           % (len(missing), ", ".join(missing[:5])),
                           outputs=[str(out / "route_verification.json")], detail=record)
    return StageResult(OK, "%d routes declared, %d prerendered HTML files present"
                       % (len(rows), len(html_files)),
                       outputs=[str(out / "route_verification.json")], detail=record)
