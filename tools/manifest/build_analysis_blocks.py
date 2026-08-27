"""Render the `analysis:` fragment for every module that declares one.

The fragments are generated rather than hand-written because thirty of them share the same
four or five controls, and thirty hand-copied date ranges would drift within a week. What
is *not* shared is the prose: each module's summary and each parameter's note say what
that module actually does with the value, because a note reading "the date range" on
every module teaches a reader nothing.

Run it, then inject:

    python tools/manifest/build_analysis_blocks.py
    python tools/manifest/inject_analysis.py tools/manifest/analysis/STATS-02.yaml ...
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent / "analysis"

#: `typical_seconds` is measured, not estimated: it is what the button promises, and the
#: end-to-end suite uses it to decide which modules are too slow for the default run.
#: Re-measure with a loop over `service.run_module(id, {})` after changing an adapter.

#: The span the panel and the corpus actually cover. Every date control is bounded by it,
#: so a caller cannot ask for a window no data exists in.
FIRST, LAST = "2015-01-01", "2026-08-14"

INSTRUMENT_NOTE = "leave empty for every instrument in the range"
SPLIT_OPTIONS = ["all", "train", "validation", "holdout"]
ARMS = [
    "FULL", "NO_TEXT", "NO_IMAGE", "NO_AUDIO", "NO_VIDEO", "NO_MARKET",
    "NO_MICROSTRUCTURE", "NO_REGIME", "NO_PROPAGATION", "NO_AFFECTIVE",
    "NO_UNCERTAINTY", "TEXT_ONLY", "IMAGE_ONLY", "AUDIO_ONLY", "VIDEO_ONLY",
    "MARKET_ONLY", "MARKET_MICRO", "ALL_MEDIA", "ALL_MEDIA_MARKET",
    "FUSION_STATIC", "FUSION_EARLY", "FUSION_LATE", "FUSION_UNCERTAINTY",
    "FUSION_REGIME_INHERITED", "FUSION_REGIME_CORRECTED",
]
BLOCKS = ["text", "image", "audio", "video", "market", "microstructure", "regime",
          "propagation"]
MODALITIES = ["text", "image", "audio", "video", "market", "microstructure", "regime",
              "propagation"]


def date(name: str, label: str, default: str, note: str) -> dict:
    return {"name": name, "kind": "date", "label": label, "default": default,
            "minimum": FIRST, "maximum": LAST, "note": note}


def instruments(note: str = INSTRUMENT_NOTE) -> dict:
    return {"name": "instruments", "kind": "symbols", "label": "Instruments",
            "default": [], "max_items": 60, "note": note}


def split(note: str) -> dict:
    return {"name": "split", "kind": "select", "label": "Split", "default": "all",
            "options": SPLIT_OPTIONS, "note": note}


def select(name, label, default, options, note) -> dict:
    return {"name": name, "kind": "select", "label": label, "default": default,
            "options": options, "note": note}


def number(name, label, default, lo, hi, note, kind="int") -> dict:
    return {"name": name, "kind": kind, "label": label, "default": default,
            "minimum": lo, "maximum": hi, "note": note}


def multiselect(name, label, default, options, note, max_items=40) -> dict:
    return {"name": name, "kind": "multiselect", "label": label, "default": default,
            "options": options, "max_items": max_items, "note": note}


def window(from_default: str, to_default: str, from_note: str, to_note: str) -> list:
    return [date("date_from", "From", from_default, from_note),
            date("date_to", "To", to_default, to_note)]


LIVE: dict[str, dict] = {}


def live(module_id, adapter, seconds, summary, inputs):
    LIVE[module_id] = {"adapter": adapter, "mode": "LIVE",
                       "typical_seconds": seconds, "summary": summary,
                       "inputs": inputs}


def artifact(module_id, reason, summary):
    LIVE[module_id] = {"adapter": None, "mode": "ARTIFACT", "typical_seconds": 0.5,
                       "summary": summary, "artifact_reason": reason, "inputs": []}


# ------------------------------------------------------------------------ STATS ----

live("STATS-02", "scripts.stages.stats:analyse_universe", 0.6,
     "Reconstructs membership and churn across the rebalances inside your window. "
     "Survivorship is a property of a window rather than of a dataset, so the answer "
     "changes with the window and is computed for the one you choose.",
     window("2018-01-01", "2024-12-31",
            "first rebalance included",
            "last rebalance included"))

live("STATS-03", "scripts.stages.stats:analyse_distributions", 1.5,
     "Describes every numeric feature on the rows you select, and names the ones that "
     "are constant there. A feature that cannot vary on this slice cannot inform "
     "anything computed from it, however useful it is elsewhere.",
     [*window("2022-01-01", "2024-12-31", "first session described",
              "last session described"),
      instruments(),
      select("block", "Feature block", "all", ["all", *BLOCKS],
             "restrict the description to one modality block"),
      split("the frozen holdout is described but never scored")])

live("STATS-04", "scripts.stages.stats:analyse_microstructure", 1.2,
     "Coverage and dispersion of the market and microstructure-proxy features on your "
     "rows, beside the register of order-book quantities daily bars cannot express at "
     "all. The second list is the boundary of the first.",
     [*window("2022-01-01", "2024-12-31", "first session described",
              "last session described"),
      instruments()])

live("STATS-05", "scripts.stages.stats:analyse_regimes", 1.2,
     "How the rows you selected distribute across regimes, and the episode rate inside "
     "each. A regime holding thirty rows supports very little on its own, so the row "
     "count is reported beside every share.",
     [*window("2022-01-01", "2024-12-31", "first session included",
              "last session included"),
      instruments(),
      split("regime occupancy can differ between splits, which is worth checking")])

live("STATS-06", "scripts.stages.stats:analyse_dependence", 9.0,
     "Contemporaneous co-movement between the instruments you select, measured on their "
     "return series over the sessions you choose, beside the propagation feature block. "
     "Association only: nothing here identifies which instrument moved first.",
     [*window("2022-01-01", "2024-12-31", "first session correlated",
              "last session correlated"),
      instruments("choose a handful; every pair among them is measured"),
      number("top_n", "Pairs to show", 15, 5, 60,
             "how many of the strongest associations to list")])

live("STATS-07", "scripts.stages.stats:analyse_tail_risk", 2.0,
     "Tail statistics of the realised next-session return over your slice, computed by "
     "the same function the exposure gate reads. This is the input distribution, not "
     "the result of acting on it, and no position size is produced anywhere.",
     [*window("2022-01-01", "2024-12-31", "first session in the return series",
              "last session in the return series"),
      instruments(),
      number("alpha", "Tail probability", 0.05, 0.01, 0.25,
             "the quantile VaR and CVaR are measured at", kind="float")])

live("STATS-08", "scripts.stages.stats:analyse_episodes", 1.0,
     "Summarises the injected episodes overlapping your window: how many, on which "
     "instruments, at what intensity. These are a construction with known parameters, "
     "not observed market manipulation.",
     [*window("2022-01-01", "2024-12-31", "first labelled session",
              "last labelled session"),
      instruments()])

live("STATS-09", "scripts.stages.stats:analyse_leakage", 10.0,
     "Runs the L1-L6 leakage suite now and reports what it found. No parameters: a "
     "leakage check whose scope the requester can narrow is not a leakage check.",
     [])

live("STATS-10", "scripts.stages.stats:analyse_validation", 2.0,
     "The confusion matrix and its metrics at a threshold you choose. The default is "
     "the threshold selected on the training split; override it and the response says "
     "so, because a threshold picked by looking at evaluation metrics is not a "
     "selection procedure.",
     [select("arm", "Arm", "FULL", ARMS,
             "which experimental arm's per-row scores to read"),
      number("threshold", "Threshold", None, 0.0, 1.0,
             "leave empty to use the training-selected threshold", kind="float"),
      *window("2019-01-01", "2026-08-14", "first scored session",
              "last scored session"),
      instruments()])

live("STATS-11", "scripts.stages.stats:analyse_calibration", 2.0,
     "The reliability curve at a binning you choose. Expected calibration error depends "
     "on the bin count, so the control is exposed rather than fixed: an ECE quoted "
     "without its binning is a number nobody can check.",
     [select("arm", "Arm", "FULL", ARMS, "whose scores to assess"),
      number("bins", "Bins", 10, 2, 50,
             "few bins hide miscalibration inside them; many put too few rows in each"),
      *window("2019-01-01", "2026-08-14", "first scored session",
              "last scored session"),
      instruments()])

live("STATS-12", "scripts.stages.stats:analyse_errors", 2.0,
     "Where the scoring goes wrong on your rows and how, with data problems diagnosed "
     "before model problems. A row with no evidence under it is not a model failure and "
     "is not counted as one.",
     [select("arm", "Arm", "FULL", ARMS, "whose scores to examine"),
      number("threshold", "Threshold", None, 0.0, 1.0,
             "leave empty to use the training-selected threshold", kind="float"),
      select("segment_by", "Segment by", "error_class",
             ["error_class", "risk_state", "state", "symbol"],
             "cross the failure modes against another column"),
      *window("2019-01-01", "2026-08-14", "first scored session",
              "last scored session"),
      instruments()])

artifact("STATS-13",
         "Regenerating the baseline comparison refits every arm and overwrites artifacts "
         "the claim ledger cites, which no request may do.",
         "The verified baseline comparison, replayed from the artifact the experiment "
         "runner produced, with the run identifier and commit that produced it.")

live("STATS-14", "scripts.stages.stats:analyse_ablation", 3.0,
     "Recomputes each arm's detection metrics on the rows you select. The arms were "
     "fitted once by the experiment runner and are not refitted here, because refitting "
     "on request would let an arm ranking be chosen after seeing the evaluation data.",
     [multiselect("arms", "Arms", ["FULL", "NO_TEXT", "NO_MARKET", "TEXT_ONLY"], ARMS,
                  "two or more arms to compare on the same rows"),
      select("reference", "Reference arm", "FULL", ARMS,
             "every difference is reported against this arm"),
      *window("2019-01-01", "2026-08-14", "first scored session",
              "last scored session")])

live("STATS-15", "scripts.stages.stats:analyse_robustness", 65.0,
     "One perturbation condition, run now: the model is fitted on clean data and scored "
     "on degraded inputs. Fitting once is the point — refitting on corrupted data asks "
     "whether the learner adapts, which is not what a degraded feed does to a deployed "
     "model.",
     [select("corruption", "Failure mode", "gaussian",
             ["gaussian", "dropout", "stale", "outliers"],
             "stale is a delayed feed, which is more common in production than noise "
             "and invisible to a null check"),
      number("severity", "Severity", 0.10, 0.01, 0.50,
             "the fraction of values affected, or the noise scale", kind="float"),
      select("modality", "Applied to", "all", ["all", *MODALITIES],
             "degrade every feature, or only one block's"),
      number("seed", "Seed", 20260818, 1, 99999999,
             "changing it changes which values are hit")])

live("STATS-16", "scripts.stages.stats:analyse_seed_noise", 50.0,
     "Derives the seed noise floor over the arms you select and tests every pair against "
     "it. A difference smaller than the floor is not a small effect: it is not "
     "distinguishable from rerunning the same arm with a different seed.",
     [multiselect("arms", "Arms", [], ARMS,
                  "leave empty to use every arm with completed seed fits"),
      number("alpha", "Alpha", 0.05, 0.01, 0.20,
             "the level the Benjamini-Hochberg correction controls at", kind="float")])


# ------------------------------------------------------------------ MULTIMODAL ----

live("MULTIMODAL-02", "scripts.stages.multimodal:analyse_text_affect", 2.0,
     "Runs the canonical extractor over your slice and shows how one dimension varies "
     "across groups. A dimension named for an emotion is a lexicon match count under "
     "that name, over text this project generated.",
     [*window("2022-01-01", "2022-12-31", "first publication date",
              "last publication date"),
      instruments(),
      select("dimension", "Dimension in focus", "narrative_intensity",
             ["narrative_intensity", "fear", "urgency", "uncertainty", "optimism",
              "anger", "trust", "confusion", "speculation", "credibility"],
             "the dimension broken out by group below"),
      select("group_by", "Group by", "doc_kind", ["doc_kind", "symbol"],
             "what to compare that dimension across"),
      number("sample_size", "Documents to score", 600, 50, 2000,
             "scored live; the sample is drawn with a fixed seed"),
      {"name": "supplied_text", "kind": "document", "label": "Or score your own text",
       "default": "",
       "note": "paste a paragraph or upload a plain-text document; when this is filled "
               "the corpus controls above are ignored and only this text is scored. "
               "Nothing is stored: the document is read into memory and the request "
               "ends"}])

live("MULTIMODAL-03", "scripts.stages.multimodal:analyse_text_block", 1.2,
     "Per-feature presence and dispersion for the text block on the rows you select, so "
     "a text result is never read without knowing how many rows carried text at all.",
     [*window("2022-01-01", "2024-12-31", "first session described",
              "last session described"),
      instruments(), split("which split to describe")])

live("MULTIMODAL-04", "scripts.stages.multimodal:analyse_image_render", 2.5,
     "Rasterises the price window with the canonical chart generator and reads the "
     "result back through the canonical image pipeline. The whole modality in one "
     "request — and a demonstration that the image carries nothing the prices did not.",
     [{"name": "symbol", "kind": "symbols", "label": "Instrument",
       "default": ["RELIANCE"], "max_items": 1,
       "note": "one instrument; the chart is rendered from its price history"},
      date("as_of", "As of", "2024-06-28",
           "the window ends on the last session on or before this date"),
      number("lookback", "Sessions in the window", 60, 20, 250,
             "how much history the chart draws")])

live("MULTIMODAL-05", "scripts.stages.multimodal:analyse_image_block", 1.2,
     "Per-feature presence and dispersion for the image block on the rows you select. "
     "Every one of these features is computed from a chart rendered from market data.",
     [*window("2022-01-01", "2024-12-31", "first session described",
              "last session described"),
      instruments(), split("which split to describe")])

live("MULTIMODAL-06", "scripts.stages.multimodal:analyse_sonification", 4.0,
     "Sonifies the market window and extracts acoustic features from the waveform, both "
     "during this request. The waveform contains no speech: features named for prosody "
     "describe an oscillator driven by prices.",
     [{"name": "symbol", "kind": "symbols", "label": "Instrument",
       "default": ["RELIANCE"], "max_items": 1,
       "note": "one instrument; its prices drive the oscillator"},
      date("as_of", "As of", "2024-06-28",
           "the window ends on the last session on or before this date"),
      number("lookback", "Sessions to sonify", 60, 20, 250,
             "each session becomes one note")])

live("MULTIMODAL-07", "scripts.stages.multimodal:analyse_audio_block", 1.2,
     "Per-feature presence and dispersion for the audio block on the rows you select. "
     "These are proxies computed from sonified market data, not from recorded speech.",
     [*window("2022-01-01", "2024-12-31", "first session described",
              "last session described"),
      instruments(), split("which split to describe")])

artifact("MULTIMODAL-08",
         "Video generation renders and encodes clips, which takes minutes rather than "
         "seconds and writes to the media directory; it is not run from a request.",
         "The verified video generation record, replayed from the artifact the media "
         "pipeline produced.")

live("MULTIMODAL-09", "scripts.stages.multimodal:analyse_video_block", 1.2,
     "Per-feature presence and dispersion for the video block on the rows you select. "
     "The clips behind these features were rendered by this project; no broadcast "
     "footage is downloaded or analysed anywhere in the system.",
     [*window("2022-01-01", "2024-12-31", "first session described",
              "last session described"),
      instruments(), split("which split to describe")])

live("MULTIMODAL-10", "scripts.stages.multimodal:analyse_media_licence", 0.5,
     "Classifies a media reference against the licence rules, offline. The URL is never "
     "fetched: the question is whether the material may be redistributed, and its host "
     "cannot answer that.",
     [{"name": "source_url", "kind": "text", "label": "Media reference",
       "default": "https://www.reuters.com/markets/",
       "required": True,
       "note": "the full address of the reference you want classified"},
      {"name": "publisher", "kind": "text", "label": "Publisher", "default": "",
       "note": "optional; recorded with the verdict"},
      {"name": "licence_name", "kind": "text", "label": "Declared licence",
       "default": "",
       "note": "optional; a declaration alone never upgrades a status without evidence"}])

live("MULTIMODAL-11", "scripts.stages.multimodal:analyse_alignment", 42.0,
     "Fits the model now, then scores it with one modality shifted forward in time. "
     "Forward is the only realistic direction: media arrives later than market data, "
     "never earlier.",
     [select("modality", "Modality to delay", "text", MODALITIES,
             "whose feature block is shifted"),
      number("max_offset", "Largest delay", 10, 1, 20,
             "in sessions; every smaller offset in the standard set is measured too"),
      number("seed", "Seed", 20260818, 1, 99999999,
             "the fit is seeded, so the same seed reproduces the curve")])

live("MULTIMODAL-12", "scripts.stages.multimodal:analyse_assembly", 1.5,
     "How completely the modality blocks joined on the rows you select. The figure that "
     "matters is how many rows carry every block at once, because a result computed on "
     "rows with three blocks is a different claim from one computed on rows with seven.",
     [*window("2022-01-01", "2024-12-31", "first session described",
              "last session described"),
      instruments(), split("which split to describe")])

live("MULTIMODAL-13", "scripts.stages.multimodal:analyse_degeneracy", 1.0,
     "Runs the degeneracy proof at parameters you choose. The claim is algebraic, so it "
     "should survive any parameterisation: turn the regime term up and the difference "
     "stays at machine precision.",
     [number("n_rows", "Rows", 500, 50, 5000, "how many rows to construct"),
      number("n_modalities", "Modalities", 8, 2, 32,
             "how many modality logits enter the softmax"),
      number("n_regimes", "Regimes", 4, 2, 16, "how many regimes to draw from"),
      number("regime_term_sd", "Regime term spread", 25.0, 0.1, 100.0,
             "how large to make the term that is supposed to matter", kind="float"),
      number("seed", "Seed", 20260818, 1, 99999999, "the construction is seeded")])

live("MULTIMODAL-14", "scripts.stages.multimodal:analyse_decomposition", 3.0,
     "Unique, shared and synergistic contribution per modality, recomputed from the "
     "stored per-arm scores. A modality needs both a stand-alone and a leave-one-out arm "
     "to be decomposed; one without both is reported as unavailable rather than guessed.",
     [multiselect("modalities", "Modalities", ["text", "image", "audio", "video",
                                               "market", "microstructure"],
                  MODALITIES, "which modalities to decompose", max_items=8),
      *window("2019-01-01", "2026-08-14", "first scored session",
              "last scored session")])

live("MULTIMODAL-15", "scripts.stages.multimodal:analyse_missingness", 55.0,
     "Takes one modality offline for part of the evaluation rows — columns and coverage "
     "flag together — and refits nothing. Clearing the flag matters: a modality whose "
     "columns are blank but whose flag still reads present keeps voting with nothing "
     "behind it.",
     [select("modality", "Modality to take offline", "text", MODALITIES,
             "whose block is blanked"),
      number("fraction", "Rows affected", 0.5, 0.05, 1.0,
             "the share of evaluation rows that lose the modality", kind="float"),
      number("seed", "Seed", 20260818, 1, 99999999,
             "which rows lose it is a random draw")])

artifact("MULTIMODAL-16",
         "The explanation benchmark needs a fitted model and a fitted surrogate, and "
         "producing both takes minutes; it runs from the paper-artifact pipeline rather "
         "than from a request.",
         "The verified explanation benchmark and sanity suite, replayed from the "
         "artifacts the paper pipeline produced.")


# ---------------------------------------------------------------- rendering ----

def render_scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    if text == "" or any(c in text for c in ":#{}[]&*!|>%@`") or text.strip() != text:
        return "'%s'" % text.replace("'", "''")
    return "'%s'" % text if text[0].isdigit() else text


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


def render(module_id: str, spec: dict) -> str:
    lines = ["    analysis:"]
    if spec["adapter"]:
        lines.append("      adapter: %s" % spec["adapter"])
    lines.append("      mode: %s" % spec["mode"])
    lines.append("      typical_seconds: %s" % spec["typical_seconds"])
    lines.append("      summary: >-")
    lines.extend(wrap(spec["summary"], 8))
    if spec.get("artifact_reason"):
        lines.append("      artifact_reason: >-")
        lines.extend(wrap(spec["artifact_reason"], 8))
    if not spec["inputs"]:
        lines.append("      inputs: []")
        return "\n".join(lines) + "\n"

    lines.append("      inputs:")
    for i in spec["inputs"]:
        lines.append("        - name: %s" % i["name"])
        lines.append("          kind: %s" % i["kind"])
        lines.append("          label: %s" % render_scalar(i["label"]))
        if "default" in i:
            default = i["default"]
            if isinstance(default, list):
                lines.append("          default: [%s]"
                             % ", ".join(render_scalar(v) for v in default))
            else:
                lines.append("          default: %s" % render_scalar(default))
        for key in ("minimum", "maximum", "max_items"):
            if i.get(key) is not None:
                lines.append("          %s: %s" % (key, render_scalar(i[key])))
        if i.get("required"):
            lines.append("          required: true")
        if i.get("options"):
            lines.append("          options:")
            lines.extend("            - %s" % render_scalar(o) for o in i["options"])
        if i.get("note"):
            lines.append("          note: >-")
            lines.extend(wrap(i["note"], 12))
    return "\n".join(lines) + "\n"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for module_id, spec in LIVE.items():
        (OUT / ("%s.yaml" % module_id)).write_text(render(module_id, spec),
                                                   encoding="utf-8")
    print("wrote %d analysis fragments to %s" % (len(LIVE), OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
