"""The multimodal analysis surface: offer paired samples, run the fusion model, return it.

Everything goes through `research.models.fusion.inference`, which loads FUSION_MODEL_V1
and both encoders from their checkpoints. There is no stored result and no branch that
returns a canned answer.

**Which modalities.** A request names the pair and, optionally, which modalities to use.
Asking for one of them is not a degraded request - it is the comparison the experiment
is about, and it is how a person can see for themselves that audio alone does better
here. The response always states which modalities were actually present.

**What the response carries with the prediction.** The measured finding that this fusion
model scored *below* audio alone on held-out actors, with the interval that says so. An
interface that showed the fusion answer without it would be presenting the weaker model
as the product's best answer.

The offered pairs come from the held-out test split - actors neither encoder trained on.
"""
from __future__ import annotations

from functools import lru_cache

CAPABILITY = "contribution-analysis"
MODALITIES = ("audio", "video")


class FusionRefused(Exception):
    """A request this surface will not serve, with the reason and the way forward."""

    def __init__(self, code: str, reason: str, remedy: str) -> None:
        super().__init__(reason)
        self.code, self.reason, self.remedy = code, reason, remedy


def _payload(exc: FusionRefused) -> dict:
    return {"status": exc.code,
            "error": {"code": exc.code, "reason": exc.reason, "remedy": exc.remedy}}


@lru_cache(maxsize=1)
def _offered() -> dict[str, dict]:
    from research.models.fusion import dataset as ds

    if not ds.available():
        return {}
    offered = {}
    for row in ds.meta("test"):
        offered[row["pair_id"]] = {
            "id": row["pair_id"],
            "actor": row["actor_id"],
            "annotated_as": row["emotion_label"],
            "intensity": row["intensity"],
            "spoken_text": row["statement"],
            "audio_path": row["audio_path"],
            "video_path": row["video_path"],
        }
    return offered


def _engine():
    """The newest fusion model on disk, and its module.

    Newest wins because each version was kept only after beating the one before it on
    the same held-out actors, and the older ones stay loadable so a checkout missing the
    newer artifacts still works rather than failing. The response always says which
    version answered, so a reader is never left guessing which model produced a number.
    """
    from research.models.fusion import inference as v1
    from research.models.fusion import inference_v2 as v2
    from research.models.fusion import inference_v3 as v3

    for module, version in ((v3, "v3"), (v2, "v2"), (v1, "v1")):
        if module.available():
            return module, version
    return v1, "v1"


def model_available() -> bool:
    engine, _version = _engine()
    return engine.available()


def samples() -> dict:
    """The paired samples on offer, and what the experiment measured about them."""
    from research.models.fusion import dataset as ds

    inference, version = _engine()
    offered = _offered()
    if not offered:
        raise FusionRefused(
            "INPUTS_MISSING",
            "the paired corpus has not been prepared in this checkout",
            "Run: python -m research.models.fusion.pairing, then "
            "python -m research.models.fusion.dataset")

    manifest = ds.manifest()
    return {
        "status": "OK",
        "capability": CAPABILITY,
        "modality": "fusion",
        "model_id": inference.MODEL_ID,
        "model_version": version,
        "model_available": inference.available(),
        "task": inference.TASK,
        "classes": list(ds.CLASSES),
        "note": inference.NOTE,
        "measured_finding": inference.FINDING,
        "headline_metrics": inference.headline_metrics(),
        "alignment": manifest["alignment"],
        "alignment_note": manifest["alignment_note"],
        "source": {
            "dataset": "RAVDESS_AV_V1",
            "licence": "CC BY-NC-SA 4.0",
            "split": "test",
            "split_strategy": manifest["split_strategy"],
            "actors": manifest["splits"]["test"]["actors"],
            "why_these": ("held-out actors that neither encoder trained on, so a correct "
                          "answer is generalisation rather than recall"),
        },
        "samples": [{k: v for k, v in row.items()
                     if k not in ("audio_path", "video_path")}
                    for row in offered.values()],
    }


def analyse(body: dict) -> dict:
    """Run FUSION_MODEL_V1 over one offered pair, using the modalities requested."""
    from research.models.fusion import checkpoint as ckpt

    inference, _version = _engine()
    if not inference.available():
        raise FusionRefused(
            "NOT_YET_EXECUTED",
            "%s has not been trained in this checkout" % inference.MODEL_ID,
            "Run: python -m research.models.fusion.evaluate_v2")

    pair = body.get("pair")
    if pair is None:
        raise FusionRefused(
            "INPUTS_MISSING", "no paired sample was supplied",
            "Send {\"modality\": \"fusion\", \"pair\": \"PAIR-...\"}.")
    if not isinstance(pair, str):
        raise FusionRefused("INVALID_INPUT", "pair must be a string",
                            "Use an identifier from "
                            "GET /api/multimodal/fusion/samples.")
    entry = _offered().get(pair)
    if entry is None:
        # Membership, not path arithmetic.
        raise FusionRefused(
            "INVALID_INPUT", "no offered pair is called %r" % pair[:64],
            "GET /api/multimodal/fusion/samples lists the ones on offer.")

    requested = body.get("use", list(MODALITIES))
    if not isinstance(requested, list) or not requested:
        raise FusionRefused("INVALID_INPUT", "use must be a non-empty list",
                            "Send {\"use\": [\"audio\", \"video\"]}.")
    unknown = [m for m in requested if m not in MODALITIES]
    if unknown:
        raise FusionRefused(
            "INVALID_INPUT", "unknown modality %r" % unknown[0],
            "The modalities are audio and video.")

    result = inference.predict(
        audio_path=(ckpt.REPO_ROOT / entry["audio_path"]) if "audio" in requested
        else None,
        video_path=(ckpt.REPO_ROOT / entry["video_path"]) if "video" in requested
        else None,
        explain=bool(body.get("explain", True)),
        source={"pair": entry["id"], "actor": entry["actor"],
                "annotated_as": entry["annotated_as"],
                "spoken_text": entry["spoken_text"],
                "origin": "held-out paired sample offered by this service"})
    result["agreement_with_annotation"] = result["predicted"] == entry["annotated_as"]
    return {"status": "OK", "capability": CAPABILITY, "modality": "fusion", **result}


def handle(name: str, body: dict) -> tuple[int, dict]:
    """Dispatch, translating a refusal into the status code that states it."""
    codes = {"INPUTS_MISSING": 400, "INVALID_INPUT": 400, "NOT_YET_EXECUTED": 409}
    try:
        if name == "fusion_samples":
            return 200, samples()
        if name == "fusion_analyse":
            return 200, analyse(body)
    except FusionRefused as refused:
        return codes.get(refused.code, 400), _payload(refused)
    raise KeyError(name)
