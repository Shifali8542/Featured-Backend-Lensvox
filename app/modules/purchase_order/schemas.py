"""
Pydantic schemas for Purchase Order module.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.modules.purchase_order.models import POStatus


# ── POLine ────────────────────────────────────────────────────────────────────

class POLineCreate(BaseModel):
    product_id: uuid.UUID
    line_number: int = Field(default=1, ge=1)
    quantity_ordered: float = Field(..., gt=0)
    unit_price: float | None = None
    unit_of_measure: str = Field(default="EA", max_length=50)


class POLineResponse(BaseModel):
    id: uuid.UUID
    purchase_order_id: uuid.UUID
    product_id: uuid.UUID
    line_number: int
    quantity_ordered: float
    quantity_received: float
    unit_price: float | None
    unit_of_measure: str
    is_fully_received: bool

    model_config = {"from_attributes": True}


# ── PurchaseOrder ─────────────────────────────────────────────────────────────

class PurchaseOrderCreate(BaseModel):
    po_number: str = Field(..., min_length=1, max_length=100)
    supplier_name: str = Field(..., min_length=1, max_length=255)
    supplier_code: str | None = None
    expected_delivery_date: date | None = None
    notes: str | None = None
    lines: list[POLineCreate] = Field(..., min_length=1)

    @field_validator("lines")
    @classmethod
    def lines_must_have_unique_products(cls, v: list[POLineCreate]) -> list[POLineCreate]:
        pids = [str(l.product_id) for l in v]
        if len(pids) != len(set(pids)):
            raise ValueError("Each PO line must reference a distinct product.")
        return v


class PurchaseOrderUpdate(BaseModel):
    supplier_name: str | None = None
    expected_delivery_date: date | None = None
    notes: str | None = None
    status: POStatus | None = None


class PurchaseOrderResponse(BaseModel):
    id: uuid.UUID
    po_number: str
    supplier_name: str
    supplier_code: str | None
    expected_delivery_date: date | None
    status: POStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime
    lines: list[POLineResponse] = []

    model_config = {"from_attributes": True}


# ── Open POs for product (mobile label scan) ──────────────────────────────────

class OpenPOForProductResponse(BaseModel):
    """
    One entry in the open-PO list returned to the mobile app when
    GET /purchase-orders/open?product_id=<uuid> is called after a scan.
    """
    po_id: uuid.UUID
    po_number: str
    supplier_name: str
    quantity_ordered: float
    quantity_received: float
    quantity_outstanding: float


# ── PO Match (used by GR service) ─────────────────────────────────────────────

class POMatchResult(BaseModel):
    po_id: uuid.UUID
    po_number: str
    po_line_id: uuid.UUID
    product_id: uuid.UUID
    quantity_ordered: float
    quantity_already_received: float
    quantity_outstanding: float
    is_shortage: bool
    shortage_quantity: float
    excess_quantity: float