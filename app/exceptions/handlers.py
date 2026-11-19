"""
FastAPI exception handlers – registered in main.py.
All handlers emit the same JSON envelope so clients have a stable contract.
"""

from __future__ import annotations

import traceback

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.exceptions.base import AppException

logger = get_logger(__name__)


def _error_envelope(
    error_code: str,
    message: str,
    status_code: int,
    details: object = None,
) -> JSONResponse:
    body: dict = {"success": False, "error": {"code": error_code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return JSONResponse(status_code=status_code, content=body)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning(
        "AppException: %s | %s | path=%s",
        exc.error_code,
        exc.message,
        request.url.path,
    )
    return _error_envelope(exc.error_code, exc.message, exc.status_code)


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return _error_envelope("HTTP_ERROR", exc.detail or "HTTP error", exc.status_code)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        {"field": " → ".join(str(l) for l in e["loc"]), "msg": e["msg"]}
        for e in exc.errors()
    ]
    return _error_envelope("VALIDATION_ERROR", "Input validation failed.", 422, details)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception on %s\n%s", request.url.path, traceback.format_exc()
    )
    return _error_envelope("INTERNAL_ERROR", "An unexpected error occurred.", 500)
