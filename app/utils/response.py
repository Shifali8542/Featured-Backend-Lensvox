"""
Standard API response envelope helpers.
Every successful response uses SuccessResponse; every error goes through
the exception handlers in app/exceptions/handlers.py.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class SuccessResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "OK"
    data: T | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    success: bool = True
    message: str = "OK"
    data: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


def ok(data: Any = None, message: str = "OK") -> dict[str, Any]:
    return {"success": True, "message": message, "data": data}


def paginated(
    items: list[Any],
    total: int,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    import math
    return {
        "success": True,
        "message": "OK",
        "data": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if page_size else 0,
    }
