"""
Application factory – creates and configures the FastAPI app.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import v1_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.exceptions.base import AppException
from app.exceptions.handlers import (
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)

settings = get_settings()
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Starting %s v%s [%s]", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT)
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url=settings.DOCS_URL,
        redoc_url=settings.REDOC_URL,
        openapi_url="/openapi.json",
        description=(
            "## Goods Receipt IMS Backend\n\n"
            "Mobile-first API for scanning product labels, matching Purchase Orders, "
            "recording Goods Receipts, and managing inventory.\n\n"
            "### Label Cases Supported\n"
            "- **Case A** – GS1 barcode / QR (Application Identifiers)\n"
            "- **Case B** – Plain product barcode (EAN-13, UPC-A, Code-128)\n"
            "- **Case C** – Supplier-specific QR (non-GS1)\n"
            "- **Case D** – No barcode (manual product / SKU search)\n"
            "- **Case E** – Damaged / unreadable code (typed digits)\n"
            "- **Case F** – Unknown barcode (catalogue link / create)\n"
        ),
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_HOSTS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception Handlers ───────────────────────────────────────────────────
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # ── Routes ───────────────────────────────────────────────────────────────
    app.include_router(v1_router, prefix=settings.API_V1_PREFIX)

    # ── Health check ─────────────────────────────────────────────────────────
    @app.get("/health", tags=["Health"], summary="Health check")
    async def health() -> dict:
        return {"status": "ok", "version": settings.APP_VERSION}

    return app


app = create_app()
