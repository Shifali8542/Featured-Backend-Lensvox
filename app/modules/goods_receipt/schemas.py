"""
Pydantic schemas for the Goods Receipt module.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.modules.goods_receipt.models import DiscrepancyType, GRStatus
from app.modules.label_parser.schemas import ParsedLabelData


# ── Create GR (scan workflow) ─────────────────────────────────────────────────

class GRLineCreate(BaseModel):
    """
    One line is created per scan.
    The `parsed_label` comes from the label parser endpoint.
    """
    parsed_label: ParsedLabelData
    quantity_received: float = Field(..., gt=0)
    unit_of_measure: str = Field(default="EA", max_length=50)
    po_id: uuid.UUID | None = None  # optional PO context


class GoodsReceiptCreate(BaseModel):
    purchase_order_id: uuid.UUID | None = None
    received_date: date | None = None
    notes: str | None = None
    lines: list[GRLineCreate] = Field(..., min_length=1)


# ── Add single line to existing GR ───────────────────────────────────────────

class AddGRLineRequest(BaseModel):
    gr_id: uuid.UUID
    parsed_label: ParsedLabelData
    quantity_received: float = Field(..., gt=0)
    unit_of_measure: str = Field(default="EA", max_length=50)
    po_id: uuid.UUID | None = None


# ── Response schemas ──────────────────────────────────────────────────────────

class DiscrepancyResponse(BaseModel):
    id: uuid.UUID
    gr_line_id: uuid.UUID
    discrepancy_type: DiscrepancyType
    expected_value: str | None
    actual_value: str | None
    description: str | None
    is_resolved: bool

    model_config = {"from_attributes": True}


class GRLineResponse(BaseModel):
    id: uuid.UUID
    goods_receipt_id: uuid.UUID
    product_id: uuid.UUID
    # Denormalised from Product — populated by the service layer join
    product_name: str | None = None
    product_sku: str | None = None
    po_line_id: uuid.UUID | None
    label_type: str
    barcode: str | None
    gtin: str | None
    batch_number: str | None
    serial_number: str | None
    expiry_date: date | None
    manufacture_date: date | None
    quantity_received: float
    unit_of_measure: str
    has_discrepancy: bool
    discrepancies: list[DiscrepancyResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class GoodsReceiptResponse(BaseModel):
    id: uuid.UUID
    gr_number: str
    purchase_order_id: uuid.UUID | None
    received_date: date
    status: GRStatus
    notes: str | None
    has_discrepancies: bool
    lines: list[GRLineResponse] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Finalise request ──────────────────────────────────────────────────────────

class FinaliseGRRequest(BaseModel):
    notes: str | None = None


# ── Summary ───────────────────────────────────────────────────────────────────

class GRSummaryResponse(BaseModel):
    gr_id: uuid.UUID
    gr_number: str
    po_number: str | None
    total_lines: int
    lines_with_discrepancies: int
    total_quantity_received: float
    discrepancy_types: list[str]
    status: GRStatus