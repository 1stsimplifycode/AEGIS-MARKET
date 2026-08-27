"""The audio analysis surface: offer clips, run the trained model on one, return the run.

Everything here goes through `research.models.audio.inference`, which loads
AUDIO_MODEL_V1 from its checkpoint. There is no stored result to serve and no branch that
returns a canned answer - if the checkpoint is missing the endpoint says so and returns
nothing else.

**What may be analysed.** Two inputs, and both are bounded:

* a clip the backend offers, named by an identifier that must appear in the offered
  list. The identifier is matched against that list rather than joined onto a path,
  so no request can reach a file the corpus does not contain.
* an uploaded WAV, size-limited and decoded here. Nothing about the upload reaches a
  filesystem path or a shell.

The offered clips come from the **held-out test split** - speakers the model never
trained on. Offering training clips would let the demonstration show the model
recognising something it had memorised, which would flatter it and teach a reader the
wrong thing.

Each offered clip carries the annotation the dataset gives it, so a reader can see when
the model is wrong rather than only being told what it decided.
"""
from __future__ import annotations

import base64
import binascii
import io
from functools import lru_cache

MAX_UPLOAD_BYTES = 4 * 1024 * 1024
CAPABILITY = "audio-evidence"


class AudioRefused(Exception):
    """A request this surface will not serve, with the reason and the way forward."""

    def __init__(self, code: str, reason: str, remedy: str) -> None:
        super().__init__(reason)
        self.code, self.reason, self.remedy = code, reason, remedy


def _payload(exc: AudioRefused) -> dict:
    return {"status": exc.code,
            "error": {"code": exc.code, "reason": exc.reason, "remedy": exc.remedy}}


@lru_cache(maxsize=1)
def _offered() -> dict[str, dict]:
    """The clips this surface will run on, keyed by identifier."""
    from research.models.audio import dataset as ds

    if not ds.available():
        return {}
    offered = {}
    for row in ds.meta("test"):
        offered[row["clip"]] = {
            "id": row["clip"],
            "speaker": row["speaker"],
            "annotated_as": row["emotion"],
            "intensity": row["intensity"],
            "spoken_text": row["statement"],
            "path": row["path"],
        }
    return offered


def model_available() -> bool:
    from research.models.audio import inference

    return inference.available()


def samples() -> dict:
    """The clips on offer, without running anything."""
    from research.models.audio import dataset as ds
    from research.models.audio import inference

    offered = _offered()
    if not offered:
        raise AudioRefused(
            "INPUTS_MISSING",
            "the speech corpus has not been prepared in this checkout",
            "Run: python -m research.datasets.acquire_ravdess, then "
            "python -m research.models.audio.dataset")

    manifest = ds.manifest()
    return {
        "status": "OK",
        "capability": CAPABILITY,
        "model_id": inference.MODEL_ID,
        "model_available": inference.available(),
        "task": inference.TASK,
        "classes": list(ds.CLASSES),
        "note": inference.NOTE,
        "source": {
            "dataset": "RAVDESS_SPEECH",
            "licence": "CC BY-NC-SA 4.0",
            "split": "test",
            "split_strategy": "speaker-disjoint",
            "speakers": manifest["splits"]["test"]["speakers"],
            "why_these": ("these are held-out speakers the model never trained on, so a "
                          "correct answer here is generalisation rather than recall"),
        },
        "samples": [{k: v for k, v in row.items() if k != "path"}
                    for row in offered.values()],
    }


def _decode_upload(encoded: str, filename: str | None) -> tuple[object, int]:
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AudioRefused("INVALID_INPUT", "the audio is not valid base64",
                           "Send the file's bytes base64-encoded.") from exc
    if len(raw) > MAX_UPLOAD_BYTES:
        raise AudioRefused(
            "INVALID_INPUT",
            "the upload is larger than %d KB" % (MAX_UPLOAD_BYTES // 1024),
            "Send a shorter clip.")
    if not raw:
        raise AudioRefused("INVALID_INPUT", "the upload is empty",
                           "Choose an audio file with contents.")
    try:
        import soundfile as sf
        audio, rate = sf.read(io.BytesIO(raw), dtype="float64", always_2d=True)
    except Exception as exc:                                   # noqa: BLE001
        raise AudioRefused(
            "INVALID_INPUT",
            "the upload could not be decoded as audio",
            "Send a WAV or FLAC file. %s" % (filename or "")) from exc
    if audio.size == 0:
        raise AudioRefused("INVALID_INPUT", "the audio contains no samples",
                           "Choose a clip with audible content.")
    return audio.mean(axis=1), int(rate)


def analyse(body: dict) -> dict:
    """Run AUDIO_MODEL_V1 over one clip. No stored result is ever returned from here."""
    from research.models.audio import inference

    if not inference.available():
        raise AudioRefused(
            "NOT_YET_EXECUTED",
            "%s has not been trained in this checkout" % inference.MODEL_ID,
            "Run: python -m research.models.audio.train")

    clip = body.get("clip")
    encoded = body.get("audio_base64")
    if clip and encoded:
        raise AudioRefused("INVALID_INPUT",
                           "send either a clip identifier or an upload, not both",
                           "Choose one input.")

    explain = bool(body.get("explain", True))
    if clip:
        if not isinstance(clip, str):
            raise AudioRefused("INVALID_INPUT", "clip must be a string",
                               "Use an identifier from "
                               "GET /api/multimodal/audio/samples.")
        offered = _offered()
        entry = offered.get(clip)
        if entry is None:
            # Membership, not path arithmetic. There is no way to name a file that is not
            # on this list.
            raise AudioRefused(
                "INVALID_INPUT", "no offered clip is called %r" % clip[:64],
                "GET /api/multimodal/audio/samples lists the ones on offer.")
        from research.models.audio import checkpoint as ckpt

        result = inference.predict_file(ckpt.REPO_ROOT / entry["path"], explain=explain)
        result["input"].update({
            "clip": entry["id"],
            "speaker": entry["speaker"],
            "annotated_as": entry["annotated_as"],
            "spoken_text": entry["spoken_text"],
            "origin": "held-out test clip offered by this service",
        })
        result["agreement_with_annotation"] = (
            result["predicted"] == entry["annotated_as"])
        return {"status": "OK", "capability": CAPABILITY, **result}

    if encoded:
        if not isinstance(encoded, str):
            raise AudioRefused("INVALID_INPUT", "audio_base64 must be a string",
                               "Send the file's bytes base64-encoded.")
        filename = body.get("filename")
        audio, rate = _decode_upload(
            encoded, filename if isinstance(filename, str) else None)
        result = inference.predict_waveform(
            audio, rate, explain=explain,
            source={"filename": str(filename)[:120] if filename else "uploaded audio",
                    "origin": "uploaded by the user",
                    "source_sample_rate": rate})
        return {"status": "OK", "capability": CAPABILITY, **result}

    raise AudioRefused(
        "INPUTS_MISSING", "no audio was supplied",
        "Send {\"clip\": \"...\"} or {\"audio_base64\": \"...\"}.")


def handle(name: str, body: dict) -> tuple[int, dict]:
    """Dispatch, translating a refusal into the status code that states it."""
    codes = {"INPUTS_MISSING": 400, "INVALID_INPUT": 400, "NOT_YET_EXECUTED": 409}
    try:
        if name == "audio_samples":
            return 200, samples()
        if name == "audio_analyse":
            return 200, analyse(body)
    except AudioRefused as refused:
        return codes.get(refused.code, 400), _payload(refused)
    raise KeyError(name)
