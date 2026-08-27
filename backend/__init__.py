"""The AEGIS-Market backend: an orchestration layer over the canonical research code.

This package defines **no statistic, feature, model or metric**. It resolves a module id
to the adapter the manifest already names, validates the caller's inputs against the
schema the manifest already declares, invokes the canonical implementation, and shapes
what comes back into one response contract. Deleting this package would leave the research
pipeline exactly as it was, which is the same rule ``scripts/stages/`` follows.

Two execution modes, and the difference is reported on every response rather than left for
a reader to infer:

``LIVE_COMPUTATION``   the canonical analysis ran, now, on data the caller selected. The
                       numbers in the response did not exist before the request.
``VERIFIED_ARTIFACT``  a previously executed, provenance-stamped artifact is being
                       replayed through a traceable endpoint. Nothing was computed.

Labelling a replay as a computation is the failure this distinction exists to prevent, and
:func:`backend.contract.Response.check` refuses a response that tries.

Three things this layer will not do:

* **Run a shell.** Inputs reach an adapter as validated primitives in a dict. There is no
  path from a request to a command line, and :mod:`backend.service` never builds one.
* **Expose the filesystem.** Artifact paths are returned repository-relative, and the file
  endpoints serve only from a fixed allowlist of directories.
* **Bypass the protected-artifact guard.** A protected module returns ``PROTECTED`` with
  the reason; ``force`` is not reachable from the network.
"""
from __future__ import annotations

BACKEND_VERSION = "backend-v1"

#: How a result was obtained. Rendered verbatim in the interface.
LIVE = "LIVE_COMPUTATION"
ARTIFACT = "VERIFIED_ARTIFACT"

MODE_LABEL = {
    LIVE: "Live computation",
    ARTIFACT: "Verified experiment result",
}

MODE_MEANING = {
    LIVE: ("The canonical implementation ran when you asked for it, on the data you "
           "selected. These numbers did not exist before this request."),
    ARTIFACT: ("A previously executed experiment, replayed from its provenance-stamped "
               "artifact. Nothing was computed for this request; the run identifier and "
               "commit below are the ones that produced these numbers."),
}

#: Response statuses. The first six mirror the module exit codes so a backend status and a
#: `run.bat` exit code cannot mean different things.
OK = "OK"
FAILED = "FAILED"
BLOCKED = "BLOCKED"
INPUTS_MISSING = "INPUTS_MISSING"
PROTECTED = "PROTECTED"
NOT_YET_EXECUTED = "NOT_YET_EXECUTED"
INVALID_INPUT = "INVALID_INPUT"
UNKNOWN_MODULE = "UNKNOWN_MODULE"
TIMEOUT = "TIMEOUT"
#: The selection was valid but left too little data to analyse. Distinct from
#: INPUTS_MISSING, which means a required file is not on disk: here the file is
#: present and the caller simply asked about a window that holds almost nothing.
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
#: The capability exists and works, but this demonstration is running with an earlier
#: active week and does not expose it yet. Distinct from every other refusal here: nothing
#: is missing, nothing failed, and nothing is protected. See `backend/capability.py`.
FEATURE_NOT_ENABLED = "FEATURE_NOT_ENABLED"

#: Statuses a caller should render as an explained refusal rather than a failure. A
#: protected module refusing to regenerate a cited artifact is the guard working.
REFUSALS = {PROTECTED, INPUTS_MISSING, NOT_YET_EXECUTED, INVALID_INPUT, BLOCKED,
            INSUFFICIENT_DATA, FEATURE_NOT_ENABLED}

STATUS_FROM_CODE = {
    0: OK,
    1: FAILED,
    3: BLOCKED,
    4: INPUTS_MISSING,
    5: PROTECTED,
    6: NOT_YET_EXECUTED,
}
