"""Give every weekly module a name a reader recognises, in the manifest.

`STATS-11` is a precise identifier and a useless label. It is the right thing to cite in
research mode and the wrong thing to put in front of someone who wants to know how
confident a signal is — so each module carries both: `name` stays the research name and
the canonical id stays the id, while `product_name` is what the product experience shows.

Written into `research_modules.yaml` under each module's `ui:` block so the two names
cannot drift apart, and so the exporter carries them to the interface together.

    python tools/manifest/product_names.py
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "research_modules.yaml"

#: What each module answers, said the way someone would ask it.
NAMES: dict[str, str] = {
    "STATS-01": "What the data contains",
    "STATS-02": "Which instruments are covered",
    "STATS-03": "How the numbers behave",
    "STATS-04": "Liquidity and trading conditions",
    "STATS-05": "Market regimes",
    "STATS-06": "How instruments move together",
    "STATS-07": "Extreme moves",
    "STATS-08": "Unusual market events",
    "STATS-09": "Timing integrity",
    "STATS-10": "How accurate the signal is",
    "STATS-11": "How confident the signal is",
    "STATS-12": "Where the signal gets it wrong",
    "STATS-13": "Compared with simpler methods",
    "STATS-14": "What each component contributes",
    "STATS-15": "What happens when data degrades",
    "STATS-16": "What counts as a real difference",
    "MULTIMODAL-01": "The financial text stream",
    "MULTIMODAL-02": "Tone in financial text",
    "MULTIMODAL-03": "Text evidence coverage",
    "MULTIMODAL-04": "Chart imagery",
    "MULTIMODAL-05": "Visual evidence coverage",
    "MULTIMODAL-06": "Market sound",
    "MULTIMODAL-07": "Acoustic evidence",
    "MULTIMODAL-08": "Market video",
    "MULTIMODAL-09": "Video evidence coverage",
    "MULTIMODAL-10": "Media rights and provenance",
    "MULTIMODAL-11": "When evidence arrives late",
    "MULTIMODAL-12": "How the evidence is joined",
    "MULTIMODAL-13": "How evidence is combined",
    "MULTIMODAL-14": "What each kind of evidence adds",
    "MULTIMODAL-15": "When evidence goes missing",
    "MULTIMODAL-16": "Why the model said that",
    "SCENARIO-01": "The scenario catalogue",
    "SCENARIO-02": "Real market conditions",
    "SCENARIO-03": "What if the evidence differed",
    "SCENARIO-04": "Transaction risk",
    "SCENARIO-05": "Mitigation conditions",
    "SCENARIO-06": "Which conditions matter",
    "SCENARIO-07": "How stable the comparison is",
    "SCENARIO-08": "How much is uncertain",
}


def main() -> int:
    lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    current: str | None = None
    added = replaced = 0
    skip_next = False

    for line in lines:
        if skip_next:
            # The previous line was an `icon:` whose module already carried a name; this
            # is that name, and it is being rewritten rather than duplicated.
            skip_next = False
            if line.startswith("      product_name:"):
                continue
        match = re.match(r"^  - id: ([A-Za-z]+-\d{2})\s*$", line)
        if match:
            current = match.group(1)
        if line.startswith("      product_name:"):
            continue                       # drop any earlier run's line; it is rewritten
        out.append(line)
        if line.startswith("      icon:") and current in NAMES:
            out.append("      product_name: %s" % NAMES[current])
            added += 1

    text = chr(10).join(out) + chr(10)
    import yaml
    parsed = yaml.safe_load(text)
    named = {m["id"]: (m.get("ui") or {}).get("product_name")
             for m in parsed["modules"]}
    missing = [k for k in NAMES if k in named and not named[k]]
    if missing:
        raise SystemExit("no product name landed on: %s" % ", ".join(missing))
    for module_id, name in named.items():
        if name and module_id in NAMES and name != NAMES[module_id]:
            raise SystemExit("%s carries %r, expected %r"
                             % (module_id, name, NAMES[module_id]))

    MANIFEST.write_text(text, encoding="utf-8")
    print("named %d modules (%d rewritten)" % (added, replaced))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
