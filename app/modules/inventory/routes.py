"""
Inventory API endpoints.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.modules.inventory.schemas import (
    InventoryRecordResponse,
    StockAdjustmentRequest,
    StockMovementResponse,
)
from app.modules.inventory.service import InventoryService
from app.modules.inventory.models import MovementType
from app.utils.response import ok

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("/products/{product_id}", response_model=dict)
async def get_stock_level(
    product_id: uuid.UUID,
    batch_number: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = InventoryService(db)
    records = await svc.get_stock_level(product_id, batch_number)
    return ok(
        data=[InventoryRecordResponse.model_validate(r).model_dump() for r in records]
    )


@router.get("/products/{product_id}/movements", response_model=dict)
async def get_stock_movements(
    product_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = InventoryService(db)
    movements = await svc.get_movements(product_id, limit)
    return ok(
        data=[StockMovementResponse.model_validate(m).model_dump() for m in movements]
    )


@router.post("/adjust", response_model=dict, status_code=201)
async def adjust_stock(
    payload: StockAdjustmentRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = InventoryService(db)
    record = await svc.update_stock(
        product_id=payload.product_id,
        batch_number=payload.batch_number,
        expiry_date=None,
        quantity_delta=payload.quantity_delta,
        storage_location=payload.storage_location,
        movement_type=payload.movement_type,
        reference="MANUAL_ADJUSTMENT",
    )
    return ok(
        data=InventoryRecordResponse.model_validate(record).model_dump(),
        message="Stock adjusted.",
    )
