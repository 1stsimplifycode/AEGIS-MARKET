"""The HTTP surface of the backend: a small, explicit router over :mod:`backend.service`.

Standard library only. The project's ``requirements.txt`` is deliberately short and pinned
because every dependency is something a reader has to trust before they can trust a
number, and a web framework would be a large one to add for eight routes.

What this module is allowed to do is narrow by construction:

* it parses a path against a fixed table of routes and rejects anything else;
* it parses a JSON body, capped in size, and hands it to the service as a dict;
* it returns whatever the service returns, plus a status code.

It never touches the filesystem, never builds a command line, and never sees a module's
inputs before :func:`backend.registry.validate` has range-checked them. ``--force`` is not
a parameter of any route here, so there is no request that can regenerate a protected
artifact.

Run it with ``python -m backend.server`` (see ``run_dev.bat``).
"""
from __future__ import annotations

import json
import os
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from backend import (
    BACKEND_VERSION,
    INVALID_INPUT,
    OK,
    REFUSALS,
    UNKNOWN_MODULE,
    audio_analysis,
    capability,
    fusion_analysis,
    product,
    uploads,
    video_analysis,
)
from backend import service as svc

DEFAULT_PORT = 8787

#: Requests larger than this are refused unread. Nothing this API accepts is large: the
#: biggest legitimate body is a date range, a symbol list and a handful of numbers.
MAX_BODY_BYTES = 64 * 1024

#: An oversized body is drained up to this much so the caller can read the refusal.
#: Beyond it the connection is simply closed: reading further would be the denial of
#: service the size cap exists to refuse.
DRAIN_LIMIT_BYTES = 8 * 1024 * 1024

#: Browsers that may call this service. A wildcard would let any page a reader has open
#: drive their local backend, which is not a trade this project needs to make.
ALLOWED_ORIGINS = tuple(
    o.strip() for o in os.environ.get(
        "AEGIS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000").split(",") if o.strip()
)

#: Optional shared secret. Unset locally; set it when the service is reachable from
#: anywhere but the machine it runs on. The value is never echoed in a response.
AUTH_TOKEN = os.environ.get("AEGIS_BACKEND_TOKEN", "")

#: HTTP status per response status. A refusal is not a server error: the guard working is
#: a correct outcome, and 5xx would tell a client to retry something that will refuse
#: again for the same good reason.
HTTP_STATUS = {
    "OK": 200,
    "INVALID_INPUT": 400,
    "INSUFFICIENT_DATA": 422,
    "INPUTS_MISSING": 409,
    "PROTECTED": 200,
    "NOT_YET_EXECUTED": 501,
    "BLOCKED": 409,
    # Forbidden rather than 404: the route exists and the capability is real. Pretending
    # it is not found would misdescribe the situation to anyone reading a log.
    "FEATURE_NOT_ENABLED": 403,
    "UNKNOWN_MODULE": 404,
    "UNKNOWN_WEEK": 404,
    "TIMEOUT": 504,
    "FAILED": 500,
    "PARTIAL": 200,
}

MODULE_ID = r"(?P<module_id>[A-Za-z]+-\d{2})"
WEEK_NO = r"(?P<week>\d{1,2})"


def _routes() -> list[tuple[str, re.Pattern, str]]:
    return [
        ("GET", re.compile(r"^/api/health$"), "health"),
        # What this demonstration exposes. Readable by anyone: knowing that week 8 exists
        # and is switched off is not the same as being able to see week 8's result.
        ("GET", re.compile(r"^/api/capabilities$"), "capabilities"),
        # One analysis section, gated by its own capability. The interface renders from
        # the server components, but the result has to be refusable through the API too,
        # or the gate is only as strong as the page that happens to render it.
        ("GET", re.compile(r"^/api/analysis/(?P<capability>[a-z0-9-]{1,48})$"),
         "analysis_section"),
        # The multimodal inference surface. These run a trained checkpoint at request
        # time; both are gated by the audio-evidence capability, which the manifest
        # already places at week 7.
        ("GET", re.compile(r"^/api/multimodal/audio/samples$"), "audio_samples"),
        ("GET", re.compile(r"^/api/multimodal/video/samples$"), "video_samples"),
        ("GET", re.compile(r"^/api/multimodal/fusion/samples$"), "fusion_samples"),
        ("POST", re.compile(r"^/api/multimodal/analyze$"),
         "multimodal_analyse"),
        ("GET", re.compile(r"^/api/catalogue$"), "catalogue"),
        ("GET", re.compile(r"^/api/modules$"), "modules"),
        ("GET", re.compile(r"^/api/modules/%s$" % MODULE_ID), "module"),
        ("POST", re.compile(r"^/api/modules/%s/run$" % MODULE_ID), "run_module"),
        ("GET", re.compile(r"^/api/weeks$"), "weeks"),
        ("GET", re.compile(r"^/api/weeks/%s$" % WEEK_NO), "week"),
        ("POST", re.compile(r"^/api/weeks/%s/run$" % WEEK_NO), "run_week"),
        ("POST", re.compile(r"^/api/uploads/text$"), "upload_text"),
        # The operational surface. Simulated, persistent, audited — see backend/store.py
        # for why a simulation exists at all and what it refuses to pretend.
        ("GET", re.compile(r"^/api/account$"), "account"),
        ("GET", re.compile(r"^/api/funds$"), "funds"),
        ("POST", re.compile(r"^/api/funds/adjust$"), "funds_adjust"),
        ("GET", re.compile(r"^/api/orders$"), "orders"),
        ("POST", re.compile(r"^/api/orders/preview$"), "order_preview"),
        ("POST", re.compile(r"^/api/orders/place$"), "order_place"),
        ("GET", re.compile(r"^/api/orders/(?P<order_id>[A-Z]{3}-[A-Z0-9]{10})$"),
         "order_detail"),
        ("POST", re.compile(r"^/api/orders/(?P<order_id>[A-Z]{3}-[A-Z0-9]{10})/fill$"),
         "order_fill"),
        ("POST", re.compile(r"^/api/orders/(?P<order_id>[A-Z]{3}-[A-Z0-9]{10})/cancel$"),
         "order_cancel"),
        ("GET", re.compile(r"^/api/portfolio$"), "portfolio"),
        ("GET", re.compile(r"^/api/notifications$"), "notifications"),
        ("POST", re.compile(r"^/api/notifications/read$"), "notifications_read"),
        ("GET", re.compile(r"^/api/audit$"), "audit"),
        ("GET", re.compile(r"^/api/watchlists$"), "watchlists"),
        ("POST", re.compile(r"^/api/watchlists$"), "watchlist_create"),
        ("POST", re.compile(r"^/api/watchlists/watch$"), "watchlist_watch"),
        ("POST", re.compile(r"^/api/watchlists/unwatch$"), "watchlist_unwatch"),
        ("POST", re.compile(r"^/api/watchlists/rename$"), "watchlist_rename"),
        ("POST", re.compile(r"^/api/watchlists/delete$"), "watchlist_delete"),
        # The product surface. These serve read models rather than modules: nothing
        # here runs an analysis, and each block in the response carries its own
        # provenance so a stored score cannot be mistaken for a fresh one.
        ("GET", re.compile(r"^/api/market/overview$"), "market_overview"),
        ("GET", re.compile(r"^/api/market/attention$"), "market_attention"),
        ("GET", re.compile(r"^/api/market/search$"), "market_search"),
        ("GET", re.compile(r"^/api/instruments/(?P<symbol>[A-Za-z0-9&-]{1,24})$"),
         "instrument"),
        ("GET", re.compile(r"^/api/indices$"), "indices"),
        ("GET", re.compile(r"^/api/indices/(?P<index_id>[A-Za-z0-9^_-]{1,24})$"),
         "index_detail"),
        ("GET", re.compile(r"^/api/indices/(?P<index_id>[A-Za-z0-9^_-]{1,24})/series$"),
         "index_series"),
        ("GET", re.compile(r"^/api/indices/(?P<index_id>[A-Za-z0-9^_-]{1,24})/context$"),
         "index_context"),
        ("GET", re.compile(r"^/api/alignment$"), "alignment_matrix"),
        ("GET", re.compile(r"^/api/alignment/pair$"), "alignment_pair"),
        ("GET", re.compile(r"^/api/alignment/gate$"), "alignment_gate"),
        ("GET", re.compile(r"^/api/evidence/(?P<index_id>[A-Za-z0-9^_-]{1,24})$"),
         "evidence_summary"),
    ]


ROUTES = _routes()


class Handler(BaseHTTPRequestHandler):
    server_version = "aegis-backend/%s" % BACKEND_VERSION
    protocol_version = "HTTP/1.1"

    # -- plumbing ----------------------------------------------------------------

    def log_message(self, fmt: str, *args) -> None:            # noqa: A002
        sys.stderr.write("[backend] %s %s\n" % (self.address_string(), fmt % args))

    def _origin_ok(self) -> str | None:
        origin = self.headers.get("Origin")
        if origin is None:
            return ""            # a non-browser client; nothing to allow or deny
        return origin if origin in ALLOWED_ORIGINS else None

    def _send(self, status_code: int, payload: dict) -> None:
        # Through the strict writer, not `json.dumps`. Python emits bare NaN and Infinity
        # by default and `json.loads` reads them back, so a Python-only test never
        # notices — but `JSON.parse` rejects the *whole document*, and the proxy then
        # reports the backend as unreachable and serves a stored artifact instead. The
        # analysis had succeeded; the reader was told it had not. `research/core/jsonio`
        # already existed for exactly this failure in the exported bundles; the live
        # response path simply never used it.
        from research.core import jsonio
        body = jsonio.dumps(payload, indent=None).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self._origin_ok()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status_code: int, code: str, reason: str, remedy: str) -> None:
        self._send(status_code, {
            "backend_version": BACKEND_VERSION,
            "status": code,
            "error": {"code": code, "reason": reason, "remedy": remedy},
        })

    def _body(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            # Refusing is not enough: a client that is still sending cannot read the
            # answer if the socket closes underneath it, and would see a dropped
            # connection instead of the reason. So the body is drained first — bounded,
            # because draining an unbounded one would be the very thing being refused.
            if length <= DRAIN_LIMIT_BYTES:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            else:
                self.close_connection = True
            self._error(413, INVALID_INPUT,
                        "request body is larger than %d bytes" % MAX_BODY_BYTES,
                        "Send only the declared inputs for this module.")
            return None
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._error(400, INVALID_INPUT, "the request body is not valid JSON",
                        "Send a JSON object of the module's declared inputs.")
            return None
        if not isinstance(parsed, dict):
            self._error(400, INVALID_INPUT, "the request body must be a JSON object",
                        "Send {\"date_from\": \"...\"} rather than a list or a string.")
            return None
        return parsed

    def _upload_text(self) -> None:
        """Read an uploaded document and hand back its text.

        Separate from :meth:`_body` because the payload is multipart rather than JSON, and
        separate from every other route because it invokes nothing: the caller receives a
        string and sends it back as an ordinary, revalidated run parameter. There is no
        path from an upload to an adapter that does not go through the same schema check
        as a typed one.
        """
        length = int(self.headers.get("Content-Length") or 0)
        if length > uploads.MAX_UPLOAD_BYTES:
            if length <= DRAIN_LIMIT_BYTES:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            else:
                self.close_connection = True
            self._error(413, INVALID_INPUT,
                        "the upload is larger than %d KB"
                        % (uploads.MAX_UPLOAD_BYTES // 1024),
                        "Choose a smaller document, or paste an excerpt instead.")
            return
        raw = self.rfile.read(length) if length else b""
        try:
            document = uploads.read_document(
                raw, self.headers.get("Content-Type", ""))
        except uploads.UploadRejected as exc:
            self._error(400, INVALID_INPUT, exc.reason, exc.remedy)
            return
        self._send(200, {"backend_version": BACKEND_VERSION, "status": "OK",
                         **document})

    def _analyse_upload(self) -> None:
        """Read an uploaded video and classify it.

        Separate from :meth:`_body` because the payload is multipart rather than JSON, and
        because a video does not fit inside the 64 KB JSON limit. Raising that limit for
        every route so this one could take a file would weaken a control that protects all
        of them, so the size bound lives here and applies only to this path.

        The capability is checked before a byte is read. Reading a 48 MB upload and then
        refusing it would do the work the refusal exists to avoid.
        """
        try:
            capability.require_capability(video_analysis.CAPABILITY)
        except capability.NotEnabled as gated:
            self.close_connection = True
            self._send(403, {**capability.refusal(gated),
                             "capability": video_analysis.CAPABILITY,
                             "modality": "video"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length > video_analysis.MAX_UPLOAD_BYTES:
            self.close_connection = True
            self._error(413, INVALID_INPUT,
                        "the upload is larger than %d MB"
                        % (video_analysis.MAX_UPLOAD_BYTES // (1024 * 1024)),
                        "Send a shorter clip.")
            return
        raw = self.rfile.read(length) if length else b""
        try:
            filename, content, declared = uploads.parse_multipart(
                raw, self.headers.get("Content-Type", ""))
        except uploads.UploadRejected as exc:
            self._error(400, INVALID_INPUT, exc.reason, exc.remedy)
            return
        try:
            payload = video_analysis.analyse_upload(filename, content, declared)
        except video_analysis.VideoRefused as refused:
            codes = {"INPUTS_MISSING": 400, "INVALID_INPUT": 400,
                     "NOT_YET_EXECUTED": 409}
            self._error(codes.get(refused.code, 400), refused.code, refused.reason,
                        refused.remedy)
            return
        self._send(200, payload)

    def _authorised(self) -> bool:
        if not AUTH_TOKEN:
            return True
        supplied = (self.headers.get("Authorization") or "").removeprefix("Bearer ")
        if supplied == AUTH_TOKEN:
            return True
        self._error(401, "UNAUTHORISED", "this backend requires a bearer token",
                    "Set the same token the service was started with.")
        return False

    # -- verbs -------------------------------------------------------------------

    def do_OPTIONS(self) -> None:                              # noqa: N802
        origin = self._origin_ok()
        self.send_response(204 if origin is not None else 403)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, "
                                                             "Authorization")
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:                                  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:                                 # noqa: N802
        self._dispatch("POST")

    # -- routing -----------------------------------------------------------------

    def _dispatch(self, verb: str) -> None:
        if self._origin_ok() is None:
            self._error(403, "FORBIDDEN_ORIGIN",
                        "this backend does not accept browser requests from that origin",
                        "Set AEGIS_ALLOWED_ORIGINS to include it, deliberately.")
            return
        if not self._authorised():
            return

        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        # Method first, then path. Matching on the path alone means a route that exists
        # under two verbs — `/api/watchlists` is GET to read and POST to create — answers
        # 405 for whichever verb happens to be declared second.
        candidates = [(m, pat, n) for (m, pat, n) in ROUTES if pat.match(path)]
        if candidates and not any(m == verb for (m, _p, _n) in candidates):
            allowed = ", ".join(sorted({m for (m, _p, _n) in candidates}))
            self._error(405, "METHOD_NOT_ALLOWED",
                        "%s is served over %s" % (path, allowed),
                        "Use %s for this route." % allowed)
            return
        for method, pattern, name in candidates:
            if method != verb:
                continue
            match = pattern.match(path)
            if name == "upload_text":
                self._upload_text()
                return
            if (name == "multimodal_analyse"
                    and self.headers.get("Content-Type", "").startswith(
                        "multipart/form-data")):
                # The one analyse route takes JSON for a chosen clip and multipart for an
                # uploaded file. Only video is uploaded this way.
                self._analyse_upload()
                return
            body = self._body() if verb == "POST" else _query(parsed.query)
            if body is None:
                return                     # _body already answered
            try:
                status_code, payload = self._handle(name, match.groupdict(), body)
            except Exception:              # noqa: BLE001 - reported, never leaked
                traceback.print_exc()
                self._error(500, "FAILED",
                            "the backend failed while handling this request",
                            "This is a defect in the backend, not in your request.")
                return
            self._send(status_code, payload)
            return

        self._error(404, "UNKNOWN_ROUTE", "no route matches %s" % path,
                    "GET /api/health lists the service; GET /api/catalogue lists "
                    "every module and week.")

    def _handle(self, name: str, params: dict, body: dict) -> tuple[int, dict]:
        # The gate runs before dispatch, not inside each branch. A route added later is
        # gated by being listed here once; a route gated inside its own handler is a route
        # somebody will add without the check.
        try:
            if name in ("week", "run_week"):
                capability.require_week(int(params["week"]))
            elif name in ("module", "run_module"):
                capability.require_module(params["module_id"].upper())
        except capability.NotEnabled as gated:
            return 403, capability.refusal(gated)

        if name == "capabilities":
            return 200, {"backend_version": BACKEND_VERSION, **capability.state()}
        if name == "analysis_section":
            return _analysis_section(params["capability"])
        if name in ("audio_samples", "video_samples", "fusion_samples",
                    "multimodal_analyse"):
            # Gated on the capability, before a model is loaded or a file is opened. A
            # refusal must not be a by-product of doing the work first.
            #
            # One analyse route serves both modalities, so which capability applies is
            # read from the request rather than from the path. Audio unlocks at week 7 and
            # video at week 9, and a week-7 demonstration must refuse video even though it
            # allows audio through the same endpoint.
            modality = _modality(name, body)
            if modality is None:
                return 400, {
                    "status": INVALID_INPUT,
                    "error": {"code": INVALID_INPUT,
                              "reason": ("modality must be \"audio\", \"video\" or "
                                         "\"fusion\""),
                              "remedy": "Send {\"modality\": \"fusion\", ...}."},
                }
            module = {"audio": audio_analysis, "video": video_analysis,
                      "fusion": fusion_analysis}[modality]
            try:
                capability.require_capability(module.CAPABILITY)
            except capability.NotEnabled as gated:
                return 403, {**capability.refusal(gated),
                             "capability": module.CAPABILITY, "modality": modality}
            if name == "audio_samples":
                return audio_analysis.handle("audio_samples", body)
            if name == "video_samples":
                return video_analysis.handle("video_samples", body)
            if name == "fusion_samples":
                return fusion_analysis.handle("fusion_samples", body)
            return module.handle("%s_analyse" % modality, body)
        if name in _OPERATIONAL:
            return _operational(name, params, body)
        if name == "health":
            return 200, svc.health()
        if name == "catalogue":
            return 200, svc.catalogue()
        if name == "modules":
            active = capability.active_week()
            return 200, {"backend_version": BACKEND_VERSION,
                         "active_week": active,
                         "modules": [{**m.to_dict(),
                                      "enabled": capability.is_module_enabled(
                                          m.id, active)}
                                     for m in svc.reg.modules().values()]}
        if name == "module":
            payload = svc.describe(params["module_id"].upper())
            if payload.get("status") == UNKNOWN_MODULE:
                return 404, payload
            return 200, payload
        if name == "run_module":
            payload = svc.run_module(params["module_id"].upper(), body)
            return _code_for(payload), payload
        if name == "weeks":
            active = capability.active_week()
            return 200, {"backend_version": BACKEND_VERSION,
                         "active_week": active,
                         "weeks": [{**w.to_dict(),
                                    "enabled": capability.is_week_enabled(w.week, active)}
                                   for w in svc.reg.weeks()]}
        if name == "week":
            payload = svc.reg.week_payload(int(params["week"]))
            if payload is None:
                return 404, {"status": "UNKNOWN_WEEK", "week": int(params["week"]),
                             "error": {"code": "UNKNOWN_WEEK",
                                       "reason": "no week %s" % params["week"],
                                       "remedy": "GET /api/weeks lists them."}}
            return 200, payload
        if name == "run_week":
            payload = svc.run_week(int(params["week"]), body)
            return _code_for(payload), payload

        if name in ("market_overview", "market_attention", "market_search",
                    "instrument", "indices", "index_detail",
                    "index_series", "index_context", "alignment_matrix",
                    "alignment_pair", "alignment_gate", "evidence_summary"):
            try:
                if name == "market_overview":
                    return 200, product.overview()
                if name == "indices":
                    return 200, product.indices()
                if name == "index_detail":
                    return 200, product.index_detail(params["index_id"],
                                                     body.get("window"))
                if name == "index_series":
                    return 200, product.index_series(params["index_id"],
                                                     body.get("from"),
                                                     body.get("to"))
                if name == "index_context":
                    return 200, product.index_context(params["index_id"])
                if name == "alignment_matrix":
                    return 200, product.alignment_matrix()
                if name == "alignment_pair":
                    return 200, product.alignment(body.get("a"), body.get("b"))
                if name == "evidence_summary":
                    return 200, product.evidence_summary(params["index_id"])
                if name == "alignment_gate":
                    return 200, product.alignment_gate(body.get("a"), body.get("b"),
                                                       body.get("what", ""))
                if name == "market_attention":
                    return 200, product.attention(body.get("limit"))
                if name == "market_search":
                    return 200, product.search(body.get("q", ""), body.get("limit"))
                return 200, product.instrument(params["symbol"], body.get("window"))
            except product.ProductError as exc:
                code = 404 if exc.code in ("UNKNOWN_INSTRUMENT",
                                           "INDEX_UNAVAILABLE") else 400
                return code, {"backend_version": BACKEND_VERSION, "status": exc.code,
                              "error": {"code": exc.code, "reason": exc.reason,
                                        "remedy": exc.remedy}}
        raise AssertionError("unrouted handler %r" % name)     # pragma: no cover


def _code_for(payload: dict) -> int:
    status = payload.get("status", "FAILED")
    return HTTP_STATUS.get(status, 200 if status in REFUSALS else 500)


#: The operational routes, handled together because they share one refusal shape.
_OPERATIONAL = {
    "account", "funds", "funds_adjust", "orders", "order_preview", "order_place",
    "order_detail", "order_fill", "order_cancel", "portfolio", "notifications",
    "notifications_read", "audit", "watchlists", "watchlist_create", "watchlist_watch",
    "watchlist_unwatch", "watchlist_rename", "watchlist_delete",
}


def _operational(name: str, params: dict, body: dict) -> tuple[int, dict]:
    """The simulated brokerage surface.

    Every refusal comes back as a code, a reason and a remedy — the same contract the
    research side uses — because "why was my order rejected" is a question the product has
    to answer with something a reader can act on, not a stack trace or a bare 400.
    """
    from backend import store, trading

    def refuse(error: trading.OrderError) -> tuple[int, dict]:
        return 400, {"status": error.code,
                     "error": {"code": error.code, "reason": error.reason,
                               "remedy": error.remedy}}

    try:
        if name == "account":
            account = store.ensure_account()
            return 200, {"status": OK, "account": account,
                         "funds": store.funds_state(),
                         "authentication": "DEMO",
                         "note": ("Demonstration account. There is no identity provider, "
                                  "no broker and no bank behind this product.")}
        if name == "funds":
            return 200, {"status": OK, **store.funds_state(),
                         "ledger": store.funds_ledger()}
        if name == "funds_adjust":
            state = store.adjust_funds(
                str(body.get("kind", "")).upper(),
                float(body.get("amount") or 0),
                str(body.get("reason") or "Simulated funds adjustment."))
            return 200, {"status": OK, **state}
        if name == "orders":
            return 200, trading.book()
        if name == "order_preview":
            return 200, trading.preview(**_order_args(body))
        if name == "order_place":
            return 200, trading.place(**_order_args(body))
        if name == "order_detail":
            return 200, trading.get(params["order_id"])
        if name == "order_fill":
            quantity = body.get("quantity")
            return 200, trading.fill(params["order_id"],
                                     int(quantity) if quantity else None)
        if name == "order_cancel":
            return 200, trading.cancel(
                params["order_id"],
                str(body.get("reason") or "Cancelled by the user."))
        if name == "portfolio":
            return 200, trading.portfolio()
        if name == "notifications":
            return 200, trading.notifications(
                unread_only=str(body.get("unread", "")).lower() in ("1", "true"))
        if name == "notifications_read":
            return 200, trading.mark_read(body.get("id") or None)
        if name == "watchlists":
            return 200, store.watchlists()
        if name == "watchlist_create":
            return 200, store.create_watchlist(str(body.get("name") or ""))
        if name == "watchlist_watch":
            return 200, store.watch(str(body.get("symbol") or ""),
                                    body.get("watchlist_id") or None)
        if name == "watchlist_unwatch":
            return 200, store.unwatch(str(body.get("symbol") or ""),
                                      body.get("watchlist_id") or None)
        if name == "watchlist_rename":
            return 200, store.rename_watchlist(str(body.get("watchlist_id") or ""),
                                               str(body.get("name") or ""))
        if name == "watchlist_delete":
            return 200, store.delete_watchlist(str(body.get("watchlist_id") or ""))
        if name == "audit":
            return 200, {"status": OK,
                         "events": store.audit_trail(
                             body.get("object_type") or None,
                             body.get("object_id") or None,
                             limit=int(body.get("limit") or 200))}
    except trading.OrderError as error:
        return refuse(error)
    except (ValueError, TypeError) as error:
        return 400, {"status": INVALID_INPUT,
                     "error": {"code": INVALID_INPUT, "reason": str(error),
                               "remedy": "Check the values sent with this request."}}
    return 404, {"status": "UNKNOWN_ROUTE",
                 "error": {"code": "UNKNOWN_ROUTE", "reason": "no handler for %s" % name,
                           "remedy": "See GET /api/health."}}


def _order_args(body: dict) -> dict:
    """Coerce a ticket, refusing anything that is not what it claims to be."""
    def number(key: str) -> float | None:
        raw = body.get(key)
        if raw in (None, ""):
            return None
        return float(raw)

    quantity = body.get("quantity")
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        quantity = -1
    return {
        "symbol": str(body.get("symbol") or "").strip().upper()[:24],
        "side": str(body.get("side") or "").strip().upper(),
        "quantity": quantity,
        "order_type": str(body.get("order_type") or "MARKET").strip().upper(),
        "limit_price": number("limit_price"),
        "trigger_price": number("trigger_price"),
        "validity": str(body.get("validity") or "DAY").strip().upper(),
    }


def _modality(name: str, body: dict) -> str | None:
    """Which modality a multimodal request is about.

    The samples routes carry it in the path. The analyse route carries it in the body, and
    defaults to audio when absent so that requests written before the other modalities
    existed keep meaning what they meant. Anything else is refused rather than guessed:
    guessing here would decide which capability gate applies, and the three modalities
    unlock in three different weeks.
    """
    if name == "audio_samples":
        return "audio"
    if name == "video_samples":
        return "video"
    if name == "fusion_samples":
        return "fusion"
    declared = body.get("modality")
    if declared is None:
        return "audio"
    if isinstance(declared, str) and declared.lower() in ("audio", "video", "fusion"):
        return declared.lower()
    return None


def _analysis_section(capability_id: str) -> tuple[int, dict]:
    """One section of /analysis, or the reason it is not being served.

    Three answers, and they are three different facts:

    * **404 UNKNOWN_CAPABILITY** — no such section exists.
    * **403 FEATURE_NOT_ENABLED** — it exists, works, and this demonstration starts
      earlier. Nothing of its result is in the response.
    * **200** — enabled, and the result is read only at that point.

    The read happens after the check, not before it. Reading first and filtering
    afterwards is how a locked result ends up in a payload that was meant to withhold it.
    """
    try:
        spec = capability.require_capability(capability_id)
    except capability.UnknownCapability:
        return 404, {
            "status": "UNKNOWN_CAPABILITY",
            "capability": capability_id,
            "error": {"code": "UNKNOWN_CAPABILITY",
                      "reason": "no analysis capability %r" % capability_id,
                      "remedy": "GET /api/capabilities lists them."},
        }
    except capability.NotEnabled as gated:
        return 403, {**capability.refusal(gated), "capability": capability_id}

    payload = product.analysis_section(spec.id)
    if payload is None:
        return 404, {
            "status": "UNKNOWN_CAPABILITY",
            "capability": capability_id,
            "error": {"code": "UNKNOWN_CAPABILITY",
                      "reason": "%r is enabled but serves no result of its own"
                                % capability_id,
                      "remedy": "It is a section of the page rather than a dataset."},
        }
    return 200, payload


def _query(raw: str) -> dict:
    """Query parameters as a flat dict; repeated keys become a list.

    Only GET routes use this, and none of them run anything, so the loose shape here
    cannot reach an adapter. Run requests carry a JSON body.
    """
    out: dict = {}
    for key, values in parse_qs(raw, keep_blank_values=False).items():
        out[key] = values[0] if len(values) == 1 else values
    return out


def serve(port: int = DEFAULT_PORT, host: str = "127.0.0.1") -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    counts = svc.health()
    sys.stderr.write(
        "[backend] aegis %s on http://%s:%d — %d weeks, %d modules, %d live-capable\n"
        % (BACKEND_VERSION, host, port, counts["weeks"], counts["modules"],
           counts["live_capable_modules"]))
    sys.stderr.write("[backend] origins allowed: %s\n" % ", ".join(ALLOWED_ORIGINS))
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\n[backend] stopped\n")
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    port = int(os.environ.get("AEGIS_BACKEND_PORT", DEFAULT_PORT))
    host = os.environ.get("AEGIS_BACKEND_HOST", "127.0.0.1")
    if "--port" in argv:
        port = int(argv[argv.index("--port") + 1])
    if "--host" in argv:
        host = argv[argv.index("--host") + 1]
    serve(port, host)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
