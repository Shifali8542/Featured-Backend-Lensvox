"""
Pydantic schemas for label scanning input and parsed output.
These are the API contracts for the label-parsing layer.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enumerations ──────────────────────────────────────────────────────────────

class LabelType(str, Enum):
    """
    Case A – Structured GS1 barcode or QR code (Application Identifiers).
    Case B – Plain/normal product barcode (EAN-13, UPC-A, Code-128 …).
    Case C – Supplier-specific QR code (non-GS1, proprietary JSON/CSV).
    Case D – No barcode; employee does manual product/SKU search.
    Case E – Damaged/unreadable code; employee types the printed number.
    Case F – Unknown barcode; not linked to any product yet.
    """
    GS1 = "GS1"                      # Case A
    PLAIN_BARCODE = "PLAIN_BARCODE"  # Case B
    SUPPLIER_QR = "SUPPLIER_QR"      # Case C
    MANUAL = "MANUAL"                # Case D
    DAMAGED = "DAMAGED"              # Case E
    UNKNOWN = "UNKNOWN"              # Case F


class ParseStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"       # some fields parsed, others need manual fill
    NOT_FOUND = "NOT_FOUND"   # no matching product
    NEEDS_LINK = "NEEDS_LINK" # Case F – catalogue action required


# ── Request Schemas ───────────────────────────────────────────────────────────

class ScanLabelRequest(BaseModel):
    """
    Payload sent by the mobile app when a label is scanned or entered.

    The `raw_data` field holds whatever the scanner / camera read.
    For Case D (manual) it is empty; `manual_product_ref` is used instead.
    For Case E (damaged) `raw_data` holds the digits the employee typed.
    """
    raw_data: str | None = Field(
        default=None,
        description="Raw string from the scanner/camera. Null for Case D.",
        examples=["0101234567890128171231101ABC123"],
    )
    label_type_hint: LabelType | None = Field(
        default=None,
        description=(
            "Optional hint from the client about which case this is. "
            "If omitted the backend auto-detects."
        ),
    )
    # Case D / E fallbacks
    manual_product_ref: str | None = Field(
        default=None,
        description="Product name, SKU or internal code for manual entry (Case D/E).",
        examples=["PROD-00123", "Paracetamol 500mg"],
    )
    # Case D – manual batch + expiry
    manual_batch: str | None = Field(
        default=None,
        description="Batch / lot number entered manually.",
        examples=["BATCH-2024-001"],
    )
    manual_expiry: date | None = Field(
        default=None,
        description="Expiry date entered manually (ISO 8601).",
        examples=["2025-12-31"],
    )
    # Context
    po_id: str | None = Field(
        default=None,
        description="Purchase Order ID if already known from the session.",
    )

    model_config = {"json_schema_extra": {
        "examples": [
            {
                "summary": "Case A – GS1 barcode",
                "value": {
                    "raw_data": "0101234567890128171231101ABC123",
                    "label_type_hint": "GS1",
                },
            },
            {
                "summary": "Case B – Plain EAN-13",
                "value": {"raw_data": "5901234123457"},
            },
            {
                "summary": "Case C – Supplier QR",
                "value": {
                    "raw_data": '{"sku":"SUP-999","batch":"L44","exp":"2025-06"}',
                    "label_type_hint": "SUPPLIER_QR",
                },
            },
            {
                "summary": "Case D – Manual entry",
                "value": {
                    "manual_product_ref": "PROD-00123",
                    "manual_batch": "BATCH-2024-001",
                    "manual_expiry": "2025-12-31",
                    "po_id": "PO-2024-0001",
                },
            },
            {
                "summary": "Case E – Damaged code",
                "value": {
                    "raw_data": "5901234123457",
                    "label_type_hint": "DAMAGED",
                },
            },
            {
                "summary": "Case F – Unknown barcode",
                "value": {"raw_data": "UNKNOWN999BARCODE"},
            },
        ]
    }}


# ── Parsed Result Schema ──────────────────────────────────────────────────────

class ParsedLabelData(BaseModel):
    """
    The structured output of the label parser, regardless of input case.
    Fields that cannot be determined are None.
    """
    label_type: LabelType
    parse_status: ParseStatus

    # Product identity
    gtin: str | None = None          # GS1 Global Trade Item Number
    barcode: str | None = None       # any raw barcode / code
    product_id: str | None = None    # internal DB product UUID (if matched)
    product_name: str | None = None
    sku: str | None = None

    # Batch / lot / expiry
    batch_number: str | None = None
    lot_number: str | None = None
    expiry_date: date | None = None
    manufacture_date: date | None = None

    # Quantities & serial
    quantity: float | None = None
    serial_number: str | None = None

    # GS1-specific extras
    gs1_ais: dict[str, Any] | None = None  # raw AI → value map

    # Case F metadata
    unlinked_code: str | None = None  # original code that needs catalogue action

    # Human-readable notes / warnings
    notes: list[str] = []
