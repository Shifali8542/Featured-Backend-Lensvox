"""
Pydantic schemas for the Inventory module.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.modules.inventory.models import MovementType


class InventoryRecordResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    batch_number: str | None
    expiry_date: date | None
    storage_location: str
    quantity_on_hand: float
    unit_of_measure: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class StockMovementResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    batch_number: str | None
    movement_type: MovementType
    quantity: float
    reference: str | None
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class StockAdjustmentRequest(BaseModel):
    product_id: uuid.UUID
    batch_number: str | None = None
    storage_location: str = "DEFAULT"
    quantity_delta: float = Field(..., description="Positive to add, negative to remove")
    movement_type: MovementType = MovementType.ADJUSTMENT_POSITIVE
    notes: str | None = None
