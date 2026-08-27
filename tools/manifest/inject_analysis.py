"""Insert `analysis:` blocks into research_modules.yaml from fragment files.

The manifest is hand-maintained YAML with explanatory comments, and a round-trip through
`yaml.dump` would delete every one of them. So fragments are inserted verbatim as text at
the end of the module's block, and the result is parsed back to prove it is still valid
and that the fragment landed on the module it was named for.

Usage:  python tools/manifest/inject_analysis.py tools/manifest/analysis/*.yaml
        python tools/manifest/inject_analysis.py --replace tools/manifest/analysis/*.yaml

Each fragment file is named `<MODULE-ID>.yaml` and is already indented four spaces.
Without `--replace`, a module that already declares an analysis block is refused rather
than silently overwritten.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "research_modules.yaml"


def inject(lines: list[str], module_id: str, fragment: str,
           replace: bool = False) -> list[str]:
    start = next((i for i, ln in enumerate(lines)
                  if ln.rstrip() == "  - id: %s" % module_id), None)
    if start is None:
        raise SystemExit("module %s not found in the manifest" % module_id)
    end = next((i for i in range(start + 1, len(lines))
                if lines[i].startswith("  - id: ")), len(lines))
    block = lines[start:end]
    existing = next((i for i, ln in enumerate(block)
                     if ln.rstrip() == "    analysis:"), None)
    if existing is not None:
        if not replace:
            raise SystemExit("%s already declares an analysis block; pass --replace"
                             % module_id)
        # Drop the old block: from `analysis:` to the next key at the same indent.
        stop = next((i for i in range(existing + 1, len(block))
                     if block[i].startswith("    ") and not block[i].startswith("     ")
                     and block[i].strip()), len(block))
        lines = lines[:start + existing] + lines[start + stop:end] + lines[end:]
        end = end - (stop - existing)
    while end > start and not lines[end - 1].strip():
        end -= 1
    frag = fragment.rstrip("\n").split("\n")
    return lines[:end] + frag + [""] + lines[end:]


def main(argv: list[str]) -> int:
    replace = "--replace" in argv
    paths = [a for a in argv if not a.startswith("--")]
    lines = MANIFEST.read_text(encoding="utf-8").split("\n")
    done = []
    for p in paths:
        path = Path(p)
        module_id = path.stem
        lines = inject(lines, module_id, path.read_text(encoding="utf-8"), replace)
        done.append(module_id)

    text = "\n".join(lines)
    parsed = yaml.safe_load(text)
    by_id = {m["id"]: m for m in parsed["modules"]}
    for module_id in done:
        if "analysis" not in by_id[module_id]:
            raise SystemExit("%s: fragment did not land on the module" % module_id)
        if not by_id[module_id]["analysis"].get("mode"):
            raise SystemExit("%s: analysis block declares no mode" % module_id)
    MANIFEST.write_text(text, encoding="utf-8")
    print("injected analysis into: %s" % ", ".join(done))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
