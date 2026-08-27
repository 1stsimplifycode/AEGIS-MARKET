"""The video analysis surface: offer takes, run the trained model on one, return the run.

Everything here goes through `research.models.video.inference`, which loads
VIDEO_MODEL_V1
from its checkpoint. There is no stored result to serve and no branch that returns a
canned answer - if the checkpoint is missing the endpoint says so and returns nothing
else.

**What may be analysed.** Two inputs, both bounded:

* a take the backend offers, named by an identifier that must appear in the offered list.
  The identifier is matched against that list rather than joined onto a path, so no
  request can reach a file the corpus does not contain.
* an uploaded video, sent as multipart and size-limited here. It is written to a temporary
  file because a decoder needs a path, and that file is deleted in a `finally` whatever
  happens next.

Uploads are deliberately *not* accepted through the JSON body. The JSON limit is 64 KB
and raising it for every route so that one route could take a video would weaken a
control that protects all of them.

The offered takes come from the **held-out test split** - actors the model never trained
on. Offering training takes would let the demonstration show the model recognising
something it had memorised.

Each offered take carries the annotation the dataset gives it, so a reader can see when
the model is wrong rather than only being told what it decided.
"""
from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path

MAX_UPLOAD_BYTES = 48 * 1024 * 1024
ALLOWED_SUFFIXES = (".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv")
ALLOWED_TYPES = ("video/mp4", "video/quicktime", "video/x-m4v", "video/x-msvideo",
                 "video/webm", "video/x-matroska", "application/octet-stream")
CAPABILITY = "video-evidence"


class VideoRefused(Exception):
    """A request this surface will not serve, with the reason and the way forward."""

    def __init__(self, code: str, reason: str, remedy: str) -> None:
        super().__init__(reason)
        self.code, self.reason, self.remedy = code, reason, remedy


def _payload(exc: VideoRefused) -> dict:
    return {"status": exc.code,
            "error": {"code": exc.code, "reason": exc.reason, "remedy": exc.remedy}}


@lru_cache(maxsize=1)
def _offered() -> dict[str, dict]:
    """The takes this surface will run on, keyed by identifier."""
    from research.models.video import dataset as ds

    if not ds.available():
        return {}
    offered = {}
    for row in ds.meta("test"):
        offered[row["clip"]] = {
            "id": row["clip"],
            "actor": row["actor"],
            "annotated_as": row["emotion"],
            "intensity": row["intensity"],
            "spoken_text": row["statement"],
            "path": row["path"],
        }
    return offered


def model_available() -> bool:
    from research.models.video import inference

    return inference.available()


def samples() -> dict:
    """The takes on offer, without running anything."""
    from research.models.video import dataset as ds
    from research.models.video import inference

    offered = _offered()
    if not offered:
        raise VideoRefused(
            "INPUTS_MISSING",
            "the video corpus has not been prepared in this checkout",
            "Run: python -m research.models.video.dataset")

    manifest = ds.manifest()
    return {
        "status": "OK",
        "capability": CAPABILITY,
        "modality": "video",
        "model_id": inference.MODEL_ID,
        "model_available": inference.available(),
        "task": inference.TASK,
        "classes": list(ds.CLASSES),
        "note": inference.NOTE,
        "upload": {
            "accepted": list(ALLOWED_SUFFIXES),
            "max_bytes": MAX_UPLOAD_BYTES,
            "how": "multipart/form-data to POST /api/multimodal/analyze",
        },
        "source": {
            "dataset": "RAVDESS_SPEECH_VIDEO",
            "licence": "CC BY-NC-SA 4.0",
            "split": "test",
            "split_strategy": "actor-disjoint",
            "actors": manifest["splits"]["test"]["actors"],
            "why_these": ("these are held-out actors the model never trained on, so a "
                          "correct answer here is generalisation rather than recall"),
        },
        "samples": [{k: v for k, v in row.items() if k != "path"}
                    for row in offered.values()],
    }


def analyse_clip(clip: str, explain: bool = True) -> dict:
    """Run VIDEO_MODEL_V1 over one offered take."""
    from research.models.video import checkpoint as ckpt
    from research.models.video import inference

    _require_model()
    if not isinstance(clip, str):
        raise VideoRefused("INVALID_INPUT", "clip must be a string",
                           "Use an identifier from "
                           "GET /api/multimodal/video/samples.")
    entry = _offered().get(clip)
    if entry is None:
        # Membership, not path arithmetic. There is no way to name a file that is not on
        # this list.
        raise VideoRefused(
            "INVALID_INPUT", "no offered take is called %r" % clip[:64],
            "GET /api/multimodal/video/samples lists the ones on offer.")

    result = inference.predict_file(ckpt.REPO_ROOT / entry["path"], explain=explain)
    result["input"].update({
        "clip": entry["id"],
        "actor": entry["actor"],
        "annotated_as": entry["annotated_as"],
        "spoken_text": entry["spoken_text"],
        "origin": "held-out test take offered by this service",
    })
    result["agreement_with_annotation"] = result["predicted"] == entry["annotated_as"]
    return {"status": "OK", "capability": CAPABILITY, "modality": "video", **result}


def analyse_upload(filename: str, content: bytes, declared: str,
                   explain: bool = True) -> dict:
    """Run VIDEO_MODEL_V1 over an uploaded file."""
    from research.models.video import inference
    from research.models.video.preprocess import VideoUnreadable

    _require_model()
    if len(content) > MAX_UPLOAD_BYTES:
        raise VideoRefused(
            "INVALID_INPUT",
            "the upload is larger than %d MB" % (MAX_UPLOAD_BYTES // (1024 * 1024)),
            "Send a shorter clip.")
    if not content:
        raise VideoRefused("INVALID_INPUT", "the upload is empty",
                           "Choose a video file with contents.")

    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix not in ALLOWED_SUFFIXES:
        raise VideoRefused(
            "INVALID_INPUT",
            "%s is not a video format this endpoint accepts"
            % (suffix or "a file with no extension"),
            "Upload one of: %s." % ", ".join(ALLOWED_SUFFIXES))
    if declared and declared not in ALLOWED_TYPES:
        raise VideoRefused(
            "INVALID_INPUT",
            "the browser described this file as %s" % declared,
            "Upload a video file rather than another kind of document.")

    # A decoder needs a path, so the bytes go to a temporary file that is removed
    # however this ends.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(content)
        temporary = handle.name
    # Closed before decoding, because on Windows a second handle cannot open a file that
    # is still open here. Removed in the `finally` however this ends.
    try:
        result = inference.predict_file(temporary, explain=explain)
    except VideoUnreadable as exc:
        raise VideoRefused(
            "INVALID_INPUT", "the upload could not be decoded as video: %s" % exc,
            "The file may be corrupted or in a container this build cannot read. "
            "Try an mp4.") from exc
    finally:
        Path(temporary).unlink(missing_ok=True)

    result["input"].update({"filename": filename[:120], "origin": "uploaded by the user"})
    return {"status": "OK", "capability": CAPABILITY, "modality": "video", **result}


def _require_model() -> None:
    from research.models.video import inference

    if not inference.available():
        raise VideoRefused(
            "NOT_YET_EXECUTED",
            "%s has not been trained in this checkout" % inference.MODEL_ID,
            "Run: python -m research.models.video.train")


def handle(name: str, body: dict) -> tuple[int, dict]:
    """Dispatch, translating a refusal into the status code that states it."""
    codes = {"INPUTS_MISSING": 400, "INVALID_INPUT": 400, "NOT_YET_EXECUTED": 409}
    try:
        if name == "video_samples":
            return 200, samples()
        if name == "video_analyse":
            clip = body.get("clip")
            if clip is None:
                raise VideoRefused(
                    "INPUTS_MISSING", "no video was supplied",
                    "Send {\"modality\": \"video\", \"clip\": \"...\"}, or upload a file "
                    "as multipart/form-data.")
            return 200, analyse_clip(clip, explain=bool(body.get("explain", True)))
    except VideoRefused as refused:
        return codes.get(refused.code, 400), _payload(refused)
    raise KeyError(name)
