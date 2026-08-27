"""Dispatcher for the 32 STATS / MULTIMODAL execution modules.

    python scripts/run_module.py --module STATS-02
    python scripts/run_module.py --module STATS-02 --check
    python scripts/run_module.py --module STATS-13 --force
    python scripts/run_module.py --list

One dispatcher rather than 32 shim scripts: the manifest already names each module's
adapter, so a second per-module file would only be a place for the two to drift apart.
Every ``run.bat`` calls this with its own module id.

**The protected-artifact guard.** Eight modules regenerate files that the claim ledger and
the documentation already quote. Running one of those by accident would silently change
numbers that are cited in prose, which is a worse failure than not running it at all. They
refuse with exit code 5 unless ``--force`` is passed.

Exit codes are the contract with the .bat layer:
  0 OK · 1 FAILED · 3 BLOCKED · 4 INPUTS MISSING · 5 SKIPPED (protected) ·
  6 NOT YET EXECUTED
"""
from __future__ import annotations

import argparse
import importlib
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from research.core import jsonio  # noqa: E402
from research.core.manifest import environment_snapshot, git_commit  # noqa: E402
from scripts.stages import (  # noqa: E402
    FAILED,
    OK,
    SKIPPED_PROTECTED,
    StageResult,
)

MANIFEST = REPO_ROOT / "research_modules.yaml"


def load_manifest() -> dict:
    import yaml
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def find_module(manifest: dict, module_id: str) -> dict | None:
    wanted = module_id.strip().upper()
    for m in manifest["modules"]:
        if m["id"].upper() == wanted:
            return m
    return None


def _resolve(adapter: str):
    """`scripts.stages.stats:universe_survivorship` -> the callable."""
    mod_name, _, func_name = adapter.partition(":")
    return getattr(importlib.import_module(mod_name), func_name)


def _log(entry: dict) -> Path:
    category = entry["category"].lower()
    d = REPO_ROOT / "logs" / ("stats" if category == "stats" else "multimodal")
    d.mkdir(parents=True, exist_ok=True)
    p = d / ("%s.jsonl" % entry["module_id"].lower().replace("-", "_"))
    # jsonio rather than json.dumps: an adapter can legitimately return a non-finite
    # value in its detail dict, and one bare NaN or Infinity makes the entire provenance
    # log unreadable to every strict parser. Caught by
    # tests/unit/test_module_structure.py::test_provenance_records_are_strict_json.
    with p.open("a", encoding="utf-8") as f:
        f.write(jsonio.dumps(entry, indent=None) + "\n")
    return p


def run(module_id: str, *, check: bool = False, force: bool = False,
        quiet: bool = False) -> int:
    manifest = load_manifest()
    spec = find_module(manifest, module_id)
    if spec is None:
        print("unknown module %r; try --list" % module_id, file=sys.stderr)
        return FAILED

    started = time.time()
    header = "%s  %s" % (spec["id"], spec["name"])
    if not quiet:
        print("=" * 74)
        print(header)
        print("  canonical : %s" % (", ".join(spec["canonical"]) or "(none yet)"))
        print("  adapter   : %s" % spec["adapter"])
        print("  wrapper   : %s" % spec["wrapper_status"])
        print("=" * 74)

    # --check verifies the contract without executing: is the adapter importable, are the
    # declared inputs present? This is what the structural validator uses so that
    # validating the pipeline can never mutate an artifact.
    if check:
        try:
            fn = _resolve(spec["adapter"])
        except Exception as exc:
            print("  ADAPTER NOT IMPORTABLE: %s: %s" % (type(exc).__name__, exc))
            return FAILED
        missing = [i for i in spec.get("inputs") or [] if not (REPO_ROOT / i).exists()]
        state = "OK" if callable(fn) else "NOT CALLABLE"
        if missing:
            state = "OK (adapter) / inputs missing: %s" % ", ".join(missing)
        if not quiet:
            print("  check: %s" % state)
        return OK if callable(fn) else FAILED

    if spec["wrapper_status"] == "WRAPS_EXISTING_PROTECTED" and not force:
        msg = ("refused: this module regenerates artifacts that the claim ledger and "
               "documentation already cite (%s). Pass --force to regenerate them "
               "deliberately." % ", ".join(spec.get("outputs") or []))
        print("  SKIPPED (protected): %s" % msg)
        _log({"ts": datetime.now(UTC).isoformat(), "module_id": spec["id"],
              "category": spec["category"], "status": "SKIPPED_PROTECTED",
              "code": SKIPPED_PROTECTED, "message": msg,
              "git_commit": git_commit(), "elapsed_s": 0.0})
        return SKIPPED_PROTECTED

    try:
        fn = _resolve(spec["adapter"])
        # Product adapters are manifest-driven: they execute the command declared in the
        # spec, so they need the spec itself. Research adapters do not take it, and
        # passing it unconditionally would break all thirty-two of them.
        import inspect
        if "module" in inspect.signature(fn).parameters:
            result: StageResult = fn(force=force, module=spec)
        else:
            result = fn(force=force)
    except Exception as exc:  # a module failure is reported, never swallowed
        import traceback
        traceback.print_exc()
        result = StageResult(FAILED, "%s: %s" % (type(exc).__name__, exc))

    elapsed = time.time() - started
    if not quiet:
        print("  %s  (%.1fs)" % (result.status, elapsed))
        if result.message:
            print("  %s" % result.message)
        for o in result.outputs:
            print("  -> %s" % o)

    _log({
        "ts": datetime.now(UTC).isoformat(),
        "module_id": spec["id"], "category": spec["category"], "name": spec["name"],
        "status": result.status, "code": result.code, "message": result.message,
        "outputs": result.outputs, "detail": result.detail,
        "wrapper_status": spec["wrapper_status"], "adapter": spec["adapter"],
        "canonical": spec["canonical"], "experiment_id": spec.get("experiment_id"),
        "limitations": spec.get("limitations"),
        "git_commit": git_commit(), "environment": environment_snapshot(),
        "forced": bool(force), "elapsed_s": round(elapsed, 2),
    })
    return result.code


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--module", help="module id, e.g. STATS-02 or MULTIMODAL-13")
    ap.add_argument("--check", action="store_true",
                    help="verify the adapter and inputs without executing")
    ap.add_argument("--force", action="store_true",
                    help="allow a module to regenerate protected artifacts")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--list", action="store_true", help="list every module and exit")
    args = ap.parse_args()

    if args.list:
        manifest = load_manifest()
        for m in manifest["modules"]:
            print("%-16s %-2d %-12s %-42s %s"
                  % (m["id"], m["index"], m["category"], m["name"], m["wrapper_status"]))
        return OK
    if not args.module:
        ap.error("--module is required unless --list is given")
    return run(args.module, check=args.check, force=args.force, quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
