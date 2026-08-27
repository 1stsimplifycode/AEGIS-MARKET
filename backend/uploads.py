"""Turning an uploaded document into a validated string, and nothing else.

The one thing this module does is decode a multipart body into text a caller can then send
as an ordinary run parameter. It does not execute anything, does not name a module, and
does not touch the filesystem.

**Nothing is written to disk.** The obvious design — save the upload to a temporary
directory, analyse it, delete it — has three failure modes this one does not have: a
crash between write and delete leaves the file behind, the temporary path is a filesystem
location a bug could widen into an arbitrary write, and "cleaned up" is a property that
has to be maintained rather than one that holds by construction. A document small enough
to score is small enough to hold in memory, so it is held in memory and the request ends.

**Text only.** The extractor this feeds is a lexicon over words. Accepting an image, an
audio clip or a video here would mean running affect extraction over a real person's face
or voice on request, which is the inference this project's affective guards exist to
refuse — see ``research/human_affect/guards.py`` and L-19. The refusal is explicit rather
than implicit: an upload of another kind is rejected with the reason.
"""
from __future__ import annotations

import re

#: Larger than any document worth scoring by lexicon match, small enough to hold.
MAX_UPLOAD_BYTES = 1024 * 1024

#: The extractor's own ceiling. Text beyond it is truncated, and the caller is told.
MAX_TEXT_CHARS = 20000

#: Extensions accepted. Anything else is refused by name rather than sniffed at.
ALLOWED_SUFFIXES = (".txt", ".md", ".csv", ".text", ".log")

#: Content types a browser sends for those. A type is checked as well as an extension
#: because either alone is trivially wrong.
ALLOWED_TYPES = ("text/plain", "text/markdown", "text/csv", "application/csv",
                 "text/x-log", "application/octet-stream", "")

_FILENAME = re.compile(r'filename="([^"]*)"')
_CONTENT_TYPE = re.compile(rb"Content-Type:\s*([^\r\n;]+)", re.IGNORECASE)


class UploadRejected(ValueError):
    """The upload did not satisfy the declared limits. Carries the remedy."""

    def __init__(self, reason: str, remedy: str):
        super().__init__(reason)
        self.reason = reason
        self.remedy = remedy


def safe_name(raw: str) -> str:
    """A display name, with everything path-like removed.

    The name is never used to open anything — it is echoed back so a reader knows which
    document they are looking at. It is still stripped, because a name containing
    ``../`` is a name that will eventually be joined to a path by someone.
    """
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._ -]", "", name).strip()
    return name[:120] or "document"


def parse_multipart(body: bytes, content_type: str) -> tuple[str, bytes, str]:
    """Return ``(filename, content, declared_type)`` for the first file part.

    A deliberately small parser: one part, no nesting, no encodings beyond the ones a
    file input produces. Anything it does not recognise is refused rather than guessed at.
    """
    match = re.search(r"boundary=([^;]+)", content_type or "", re.IGNORECASE)
    if not match:
        raise UploadRejected(
            "the request is not a multipart upload",
            "Send the file as multipart/form-data from a file input.")
    boundary = match.group(1).strip().strip('"').encode("utf-8")
    parts = body.split(b"--" + boundary)

    for part in parts:
        head, _, content = part.partition(b"\r\n\r\n")
        if not content or b"filename=" not in head:
            continue
        header = head.decode("utf-8", "replace")
        name_match = _FILENAME.search(header)
        type_match = _CONTENT_TYPE.search(head)
        declared = (type_match.group(1).decode("ascii", "replace").strip().lower()
                    if type_match else "")
        return (safe_name(name_match.group(1) if name_match else ""),
                content.rstrip(b"\r\n-"), declared)

    raise UploadRejected("the upload contains no file",
                         "Choose a file before submitting.")


def read_document(body: bytes, content_type: str) -> dict:
    """Validate an uploaded document and return it as text.

    Raises :class:`UploadRejected` with a reason and a remedy; never returns a partial
    result, and never reports success for something it could not decode.
    """
    if len(body) > MAX_UPLOAD_BYTES:
        raise UploadRejected(
            "the upload is larger than %d KB" % (MAX_UPLOAD_BYTES // 1024),
            "Choose a smaller document, or paste an excerpt instead.")

    filename, content, declared = parse_multipart(body, content_type)
    suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if suffix not in ALLOWED_SUFFIXES:
        raise UploadRejected(
            "%s is not a document this endpoint accepts" % (suffix or "a file with no "
                                                            "extension"),
            "Upload a text document: %s. This endpoint reads documents into module "
            "inputs and accepts nothing else; audio and video have their own "
            "capability-gated surface under /api/multimodal, which states what its "
            "models do and do not claim." % ", ".join(ALLOWED_SUFFIXES))
    if declared not in ALLOWED_TYPES:
        raise UploadRejected(
            "the browser described this file as %s" % declared,
            "Upload a plain-text document rather than a formatted one.")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError as exc:                  # pragma: no cover - defensive
            raise UploadRejected(
                "the file is not text this endpoint can decode",
                "Save it as UTF-8 plain text and upload it again.") from exc

    if not text.strip():
        raise UploadRejected("the document is empty",
                             "Upload a document with something in it.")

    truncated = len(text) > MAX_TEXT_CHARS
    return {
        "filename": filename,
        "bytes": len(content),
        "characters": min(len(text), MAX_TEXT_CHARS),
        "truncated": truncated,
        "text": text[:MAX_TEXT_CHARS],
        "note": ("The document was read into memory and not stored. "
                 + ("Only the first %d characters were kept, which is the extractor's "
                    "ceiling." % MAX_TEXT_CHARS if truncated
                    else "It was read in full.")),
    }
