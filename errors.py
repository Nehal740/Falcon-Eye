"""Friendly, consistent error responses.

Every error returned by the API has this shape::

    {"error": {"code": "...", "message": "What happened",
               "hint": "What you can do about it", "fields": [...]},
     "detail": "What happened"}

Stack traces and raw exceptions are written to the server log only.
"""

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("falcon_eye")


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str,
                 hint: str | None = None, headers: dict | None = None,
                 fields: list | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.hint = hint
        self.headers = headers or {}
        self.fields = fields


def error_response(status_code: int, code: str, message: str,
                   hint: str | None = None, headers: dict | None = None,
                   fields: list | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "hint": hint}, "detail": message}
    if fields:
        body["error"]["fields"] = fields
    return JSONResponse(status_code=status_code, content=body, headers=headers)


_DEFAULTS = {
    400: ("bad_request", "That request could not be understood.",
          "Check the information you entered and try again."),
    401: ("not_signed_in", "You are not signed in, or your session has expired.",
          "Please sign in again."),
    403: ("not_allowed", "You do not have permission to do that.",
          "Ask a workspace owner or admin to change your role if you need access."),
    404: ("not_found", "We could not find what you were looking for.",
          "It may have been removed, or the link may be wrong."),
    405: ("method_not_allowed", "That action is not supported here.", None),
    409: ("conflict", "That conflicts with the current state.",
          "Refresh the page and try again."),
    413: ("too_large", "That request is too large.", "Send less data and try again."),
    429: ("rate_limited", "Too many requests in a short time.",
          "Wait a moment and try again."),
}


def _friendly_field(loc) -> str:
    parts = [str(p) for p in loc if p not in ("body", "query", "path")]
    return ".".join(parts) or "request"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError):
        return error_response(exc.status_code, exc.code, exc.message,
                              exc.hint, exc.headers, exc.fields)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException):
        code, message, hint = _DEFAULTS.get(
            exc.status_code, ("error", "Something went wrong.", None))
        return error_response(exc.status_code, code, message, hint,
                              getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError):
        fields = []
        for err in exc.errors():
            message = str(err.get("msg", "Invalid value")).replace("Value error, ", "")
            fields.append({"field": _friendly_field(err.get("loc", ())), "message": message})
        first = fields[0] if fields else None
        message = (f"Please check '{first['field']}': {first['message']}"
                   if first else "Some information is missing or invalid.")
        return error_response(
            422, "validation_error", message,
            "Fix the highlighted information and try again.", fields=fields)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        reference = uuid4().hex[:10]
        logger.exception("Unhandled error [%s] on %s %s", reference,
                         request.method, request.url.path)
        return error_response(
            500, "server_error",
            "Something went wrong on our side.",
            f"Please try again. If it keeps happening, tell your administrator "
            f"the reference {reference}.")
