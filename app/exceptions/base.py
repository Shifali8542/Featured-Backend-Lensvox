"""
Centralised exception hierarchy.
Every application-level exception inherits from AppException so the
global handler can produce a consistent JSON error response.
"""

from __future__ import annotations

from http import HTTPStatus


class AppException(Exception):
    """Base class for all application exceptions."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, **context: object) -> None:
        self.message = message or self.__class__.message
        self.context = context
        super().__init__(self.message)


# ── 400 Bad Request ───────────────────────────────────────────────────────────

class ValidationException(AppException):
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    error_code = "VALIDATION_ERROR"
    message = "Input validation failed."


class InvalidLabelException(AppException):
    status_code = HTTPStatus.BAD_REQUEST
    error_code = "INVALID_LABEL"
    message = "The scanned label could not be parsed."


class DuplicateEntryException(AppException):
    status_code = HTTPStatus.CONFLICT
    error_code = "DUPLICATE_ENTRY"
    message = "A record with this identifier already exists."


# ── 401 / 403 ────────────────────────────────────────────────────────────────

class AuthenticationException(AppException):
    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "AUTHENTICATION_FAILED"
    message = "Authentication required."


class PermissionDeniedException(AppException):
    status_code = HTTPStatus.FORBIDDEN
    error_code = "PERMISSION_DENIED"
    message = "You do not have permission to perform this action."


# ── 404 Not Found ─────────────────────────────────────────────────────────────

class NotFoundException(AppException):
    status_code = HTTPStatus.NOT_FOUND
    error_code = "NOT_FOUND"
    message = "The requested resource was not found."


class ProductNotFoundException(NotFoundException):
    error_code = "PRODUCT_NOT_FOUND"
    message = "Product not found."


class PurchaseOrderNotFoundException(NotFoundException):
    error_code = "PO_NOT_FOUND"
    message = "Purchase Order not found."


class GoodsReceiptNotFoundException(NotFoundException):
    error_code = "GR_NOT_FOUND"
    message = "Goods Receipt not found."


# ── Business Rule Exceptions ─────────────────────────────────────────────────

class POAlreadyClosedException(AppException):
    status_code = HTTPStatus.CONFLICT
    error_code = "PO_ALREADY_CLOSED"
    message = "This Purchase Order is already closed."


class GRAlreadyFinalised(AppException):
    status_code = HTTPStatus.CONFLICT
    error_code = "GR_ALREADY_FINALISED"
    message = "This Goods Receipt has already been finalised."


class UnknownBarcodeException(AppException):
    status_code = HTTPStatus.NOT_FOUND
    error_code = "UNKNOWN_BARCODE"
    message = "No product is linked to this barcode. An authorised user may link it."


class InsufficientPermissionForCatalogueException(PermissionDeniedException):
    error_code = "CATALOGUE_PERMISSION_REQUIRED"
    message = "Only catalogue managers can link or create products."
