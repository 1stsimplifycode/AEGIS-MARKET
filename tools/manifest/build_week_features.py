"""Declare what each week *shows*, as a `feature:` block on the weekly registry.

A weekly page that renders two module panels side by side is a report, not a feature. What
turns it into one is a decision about which two or three numbers lead, which series is the
picture, and what question the pair answers together — and that decision belongs in the
manifest beside the modules it describes, not inside a React component where it cannot be
validated.

So each week declares:

``product_question``  what the week lets a reader find out, in their words
``story``             one sentence on what the two modules do together
``headline``          three or four figures, each naming a module and a metric key
``primary_visual``    the series the page leads with, and which columns to plot
``secondary_visual``  an optional second, usually the multimodal half

Every key here was read off a live run of the module it names — see the collection step in
the commit that introduced this file. `tests/unit/test_week_features.py` re-checks them
against live output, so a declaration that stops matching its module fails the suite
rather than rendering an empty card.

    python tools/manifest/build_week_features.py
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / "research_modules.yaml"


def visual(module: str, series: str, label: str, value: str, kind: str = "bars",
           caption: str = "") -> dict:
    return {"module": module, "series": series, "label_column": label,
            "value_column": value, "kind": kind, "caption": caption}


def figure(module: str, metric: str, label: str) -> dict:
    return {"module": module, "metric": metric, "label": label}


FEATURES: dict[int, dict] = {
    1: {
        "product_question": "What is every other number here built on?",
        "story": ("Profiles the rows behind the analysis and reads the text stream that "
                  "accompanies them, so the size and completeness of the evidence base "
                  "is known before anything is concluded from it."),
        "headline": [
            figure("STATS-01", "rows", "Instrument-sessions"),
            figure("STATS-01", "instruments", "Instruments"),
            figure("MULTIMODAL-01", "documents", "Documents"),
            figure("STATS-01", "positive_rate", "Sessions inside an episode"),
        ],
        "primary_visual": visual(
            "STATS-01", "block_coverage", "block", "mean_non_null_fraction",
            caption="How completely each kind of evidence is present on these rows."),
        "secondary_visual": visual(
            "MULTIMODAL-01", "affect_dimensions", "dimension", "mean",
            caption="What the text extractor found across the documents it scored."),
    },
    2: {
        "product_question": "Which instruments does the analysis actually cover?",
        "story": ("Reconstructs which instruments were in the sample at each point in "
                  "time, and reads the tone of the text written about them."),
        "headline": [
            figure("STATS-02", "ever", "Instruments ever covered"),
            figure("STATS-02", "always", "Covered throughout"),
            figure("STATS-02", "rebalances", "Reconstitutions"),
            figure("MULTIMODAL-02", "scored", "Documents scored"),
        ],
        "primary_visual": visual(
            "STATS-02", "churn", "rebalance_date", "members", kind="line",
            caption="How many instruments were in the sample at each reconstitution."),
        "secondary_visual": visual(
            "MULTIMODAL-02", "dimensions", "dimension", "mean",
            caption="Tone dimensions across the documents scored."),
    },
    3: {
        "product_question": "How do the underlying measurements behave?",
        "story": ("Describes every feature on the selected rows and names the ones that "
                  "cannot vary there, alongside how completely the text block is "
                  "populated."),
        "headline": [
            figure("STATS-03", "features", "Features described"),
            figure("STATS-03", "degenerate", "Constant on this slice"),
            figure("STATS-03", "mean_fill", "Average completeness"),
            figure("MULTIMODAL-03", "present", "Text features present"),
        ],
        "primary_visual": visual(
            "STATS-03", "features", "feature", "non_null_fraction",
            caption="How completely each feature is populated, widest variation first."),
        "secondary_visual": visual(
            "MULTIMODAL-03", "features", "feature", "non_null_fraction",
            caption="The text block, feature by feature."),
    },
    4: {
        "product_question": "What were trading conditions like, and what does a chart of "
                            "them contain?",
        "story": ("Reads the liquidity and microstructure proxies on the selected rows, "
                  "and renders a chart from the same window to read back what a picture "
                  "of it carries."),
        "headline": [
            figure("STATS-04", "market_features", "Market measures"),
            figure("STATS-04", "proxy_features", "Liquidity proxies"),
            figure("STATS-04", "not_measured", "Recorded as unmeasurable"),
            figure("MULTIMODAL-04", "sessions", "Sessions rendered"),
        ],
        "primary_visual": visual(
            "MULTIMODAL-04", "visual_affect", "dimension", "value",
            caption="What the image pipeline read back from the chart it rendered."),
    },
    5: {
        "product_question": "What kind of market was this, and how much visual evidence "
                            "existed under it?",
        "story": ("Shows how the selected sessions distribute across market regimes, "
                  "with the completeness of the image evidence beside them."),
        "headline": [
            figure("STATS-05", "regimes", "Regimes present"),
            figure("STATS-05", "largest_share", "Largest regime"),
            figure("STATS-05", "smallest_rows", "Smallest regime, sessions"),
            figure("MULTIMODAL-05", "present", "Image features present"),
        ],
        "primary_visual": visual(
            "STATS-05", "occupancy", "regime_id", "share",
            caption="How the selected sessions divide between regimes."),
        "secondary_visual": visual(
            "MULTIMODAL-05", "features", "feature", "non_null_fraction",
            caption="The image block, feature by feature."),
    },
    6: {
        "product_question": "Did these instruments move together, and what does that "
                            "sound like?",
        "story": ("Measures contemporaneous co-movement between the instruments you "
                  "select, and sonifies the same window so the state can be heard as "
                  "well as read."),
        "headline": [
            figure("STATS-06", "pairs", "Instrument pairs measured"),
            figure("STATS-06", "median_abs_corr", "Typical association"),
            figure("STATS-06", "sessions", "Sessions measured"),
            figure("MULTIMODAL-06", "duration", "Seconds of audio"),
        ],
        "primary_visual": visual(
            "STATS-06", "pairs", "instrument_b", "correlation",
            caption="The strongest associations on the sessions selected."),
        "secondary_visual": visual(
            "MULTIMODAL-06", "audio_affect", "dimension", "value",
            caption="Acoustic dimensions of the sonified window."),
    },
    7: {
        "product_question": "How extreme did moves get?",
        "story": ("Measures the tails of the realised next-session return over the "
                  "selected window, with the acoustic evidence available beside it."),
        "headline": [
            figure("STATS-07", "n", "Returns measured"),
            figure("STATS-07", "cvar", "Average loss in the worst 5%"),
            figure("STATS-07", "vol_annual", "Annualised volatility"),
            figure("STATS-07", "max_drawdown", "Deepest drawdown"),
        ],
        "primary_visual": visual(
            "STATS-07", "tail", "statistic", "value",
            caption="Tail statistics over the sessions selected."),
        "secondary_visual": visual(
            "MULTIMODAL-07", "features", "feature", "non_null_fraction",
            caption="The audio block, feature by feature."),
    },
    8: {
        "product_question": "What unusual periods are in this data, and how were they "
                            "constructed?",
        "story": ("Summarises the injected episodes overlapping the window, with the "
                  "video generation stage that renders them."),
        "headline": [
            figure("STATS-08", "episodes", "Episodes in this window"),
            figure("STATS-08", "instruments", "Instruments affected"),
            figure("STATS-08", "label_rows", "Labelled sessions"),
            figure("STATS-08", "intensity", "Mean injected intensity"),
        ],
        "primary_visual": visual(
            "STATS-08", "episode_summary", "quantity", "value",
            caption="What the episode labels record."),
    },
    9: {
        "product_question": "Could the analysis have seen the future?",
        "story": ("Runs the timing-integrity suite now and reports what it found, with "
                  "the completeness of the video evidence beside it."),
        "headline": [
            figure("STATS-09", "passed", "Checks passed"),
            figure("STATS-09", "failed", "Checks failed"),
            figure("MULTIMODAL-09", "present", "Video features present"),
            figure("MULTIMODAL-09", "mean_fill", "Average completeness"),
        ],
        "primary_visual": visual(
            "MULTIMODAL-09", "features", "feature", "non_null_fraction",
            caption="The video block, feature by feature."),
    },
    10: {
        "product_question": "How accurate is the signal, and may the media behind it be "
                            "shared?",
        "story": ("Reports the confusion matrix at a threshold you choose, and "
                  "classifies a media reference against the licence rules."),
        "headline": [
            figure("STATS-10", "n", "Sessions assessed"),
            figure("STATS-10", "balanced_accuracy", "Balanced accuracy"),
            figure("STATS-10", "mcc", "Matthews correlation"),
            figure("STATS-10", "threshold", "Threshold applied"),
        ],
        "primary_visual": visual(
            "STATS-10", "per_class", "class_name", "f1",
            caption="How well each class is recovered at this threshold."),
    },
    11: {
        "product_question": "How confident should the signal be taken to be?",
        "story": ("Draws the reliability curve at a binning you choose, and measures "
                  "what happens when one kind of evidence arrives late."),
        "headline": [
            figure("STATS-11", "ece", "Calibration error"),
            figure("STATS-11", "bins", "Bins"),
            figure("STATS-11", "n", "Sessions assessed"),
            figure("MULTIMODAL-11", "loss", "Cost of a delay"),
        ],
        "primary_visual": visual(
            "STATS-11", "reliability", "mean_pred", "observed", kind="line",
            caption="Predicted score against observed rate. A calibrated score would "
                    "track the diagonal."),
        "secondary_visual": visual(
            "MULTIMODAL-11", "offsets", "offset_sessions", "auprc", kind="line",
            caption="What delaying one kind of evidence costs."),
    },
    12: {
        "product_question": "Where does the signal get it wrong?",
        "story": ("Classifies every mistake by kind, diagnosing missing evidence before "
                  "model error, with the completeness of the assembled panel beside it."),
        "headline": [
            figure("STATS-12", "wrong", "Sessions misclassified"),
            figure("STATS-12", "error_rate", "Error rate"),
            figure("STATS-12", "classes", "Distinct failure modes"),
            figure("MULTIMODAL-12", "complete_share", "Sessions with every kind of "
                                                      "evidence"),
        ],
        "primary_visual": visual(
            "STATS-12", "taxonomy", "error_class", "rows",
            caption="What kind of mistake, and how often."),
        "secondary_visual": visual(
            "MULTIMODAL-12", "blocks", "block", "row_share",
            caption="How often each kind of evidence was present at all."),
    },
    13: {
        "product_question": "Is this better than something simpler, and does the "
                            "combination method actually work?",
        "story": ("Replays the verified baseline comparison, and re-runs the proof that "
                  "one way of combining evidence collapses into a simpler one."),
        "headline": [
            figure("MULTIMODAL-13", "max_diff", "Difference between the two methods"),
            figure("MULTIMODAL-13", "rows", "Rows constructed"),
            figure("MULTIMODAL-13", "modalities", "Kinds of evidence"),
            figure("MULTIMODAL-13", "regime_sd", "Regime term made this large"),
        ],
        "primary_visual": visual(
            "MULTIMODAL-13", "proof", "quantity", "value",
            caption="What the proof reports at the parameters chosen."),
    },
    14: {
        "product_question": "What is each part of the system actually contributing?",
        "story": ("Recomputes each configuration's quality on the rows you select, and "
                  "decomposes how much each kind of evidence uniquely adds."),
        "headline": [
            figure("STATS-14", "arms", "Configurations compared"),
            figure("STATS-14", "best_auprc", "Best quality"),
            figure("STATS-14", "spread", "Spread across configurations"),
            figure("MULTIMODAL-14", "top_unique", "Largest unique contribution"),
        ],
        "primary_visual": visual(
            "STATS-14", "arms", "arm", "auprc",
            caption="Detection quality per configuration, on the rows selected."),
        "secondary_visual": visual(
            "MULTIMODAL-14", "decomposition", "modality", "unique",
            caption="What each kind of evidence contributes that nothing else does."),
    },
    15: {
        "product_question": "What happens when the data gets worse?",
        "story": ("Degrades the inputs one named failure mode at a time, and takes a "
                  "whole kind of evidence offline, measuring both."),
        "headline": [
            figure("STATS-15", "clean_auprc", "Quality on clean data"),
            figure("STATS-15", "degraded_auprc", "Quality when degraded"),
            figure("STATS-15", "relative", "Share of quality lost"),
            figure("MULTIMODAL-15", "loss", "Cost of losing a whole channel"),
        ],
        "primary_visual": visual(
            "STATS-15", "conditions", "condition", "auprc",
            caption="Clean against degraded, measured the same way."),
        "secondary_visual": visual(
            "MULTIMODAL-15", "conditions", "condition", "auprc",
            caption="With every kind of evidence, against one taken offline."),
    },
    16: {
        "product_question": "Which differences are real, and can the system explain "
                            "itself?",
        "story": ("Measures how much of the difference between configurations is just "
                  "the random seed, and replays the explanation benchmark."),
        "headline": [
            figure("STATS-16", "floor", "Noise floor"),
            figure("STATS-16", "pairs", "Comparisons tested"),
            figure("STATS-16", "resolved", "Comparisons resolved"),
            figure("STATS-16", "seeds", "Seeds per configuration"),
        ],
        "primary_visual": visual(
            "STATS-16", "per_arm", "arm", "auprc_mean",
            caption="Average quality per configuration across seeds."),
    },
}


def render(feature: dict) -> list[str]:
    lines = ["    feature:"]
    lines.append("      product_question: >-")
    lines.extend(wrap(feature["product_question"], 8))
    lines.append("      story: >-")
    lines.extend(wrap(feature["story"], 8))
    lines.append("      headline:")
    for h in feature["headline"]:
        lines.append("        - module: %s" % h["module"])
        lines.append("          metric: %s" % h["metric"])
        lines.append("          label: %s" % h["label"])
    for name in ("primary_visual", "secondary_visual"):
        v = feature.get(name)
        if not v:
            continue
        lines.append("      %s:" % name)
        lines.append("        module: %s" % v["module"])
        lines.append("        series: %s" % v["series"])
        lines.append("        label_column: %s" % v["label_column"])
        lines.append("        value_column: %s" % v["value_column"])
        lines.append("        kind: %s" % v["kind"])
        if v.get("caption"):
            lines.append("        caption: >-")
            lines.extend(wrap(v["caption"], 10))
    return lines


def wrap(text: str, indent: int, width: int = 88) -> list[str]:
    pad = " " * indent
    out, line = [], pad
    for word in text.split():
        if len(line) + len(word) + 1 > width and line.strip():
            out.append(line.rstrip())
            line = pad + word
        else:
            line = line + (" " if line.strip() else "") + word
    if line.strip():
        out.append(line.rstrip())
    return out


def main() -> int:
    lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    current: int | None = None
    in_feature = False
    added = 0

    for line in lines:
        match = re.match(r"^  - week: (\d+)\s*$", line)
        if match:
            current = int(match.group(1))
            in_feature = False
        if line.rstrip() == "    feature:":
            in_feature = True
            continue
        if in_feature:
            # Drop the previous run's block: everything indented under `feature:`.
            indented = line.startswith("      ")
            if indented or not line.strip():
                if line.strip():
                    continue
            else:
                in_feature = False
        out.append(line)
        # `summary:` is the last key of a week entry, so the feature lands after it.
        if line.startswith("    summary:") and current in FEATURES:
            pass

    # Insert after each week's block, before the next `  - week:` or `modules:`.
    final: list[str] = []
    current = None
    for line in out:
        match = re.match(r"^  - week: (\d+)\s*$", line)
        boundary = line.startswith("  - week: ") or line.startswith("modules:")
        if boundary and current in FEATURES:
            while final and not final[-1].strip():
                final.pop()
            final.extend(render(FEATURES[current]))
            final.append("")
            added += 1
        if match:
            current = int(match.group(1))
        elif line.startswith("modules:"):
            current = None
        final.append(line)

    text = "\n".join(final) + "\n"
    import yaml
    parsed = yaml.safe_load(text)
    weeks = {w["week"]: w for w in parsed["weeks"]}
    for number, spec in FEATURES.items():
        got = weeks[number].get("feature")
        if not got:
            raise SystemExit("week %d received no feature block" % number)
        if len(got["headline"]) != len(spec["headline"]):
            raise SystemExit("week %d headline did not land" % number)
    MANIFEST.write_text(text, encoding="utf-8")
    print("declared features for %d weeks" % added)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
