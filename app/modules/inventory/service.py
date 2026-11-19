"""
InventoryService – stock level management and movement audit log.
Called by GoodsReceiptService.finalise() to update on-hand quantities.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.modules.inventory.models import (
    InventoryRecord,
    MovementType,
    StockMovement,
)

logger = get_logger(__name__)


class InventoryService:

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def update_stock(
        self,
        product_id: uuid.UUID,
        batch_number: str | None,
        expiry_date: date | None,
        quantity_delta: float,
        reference: str | None = None,
        storage_location: str = "DEFAULT",
        movement_type: MovementType = MovementType.GOODS_RECEIPT,
    ) -> InventoryRecord:
        """
        Atomically update (or create) an inventory record and log the movement.
        """
        result = await self._db.execute(
            select(InventoryRecord).where(
                InventoryRecord.product_id == product_id,
                InventoryRecord.batch_number == batch_number,
                InventoryRecord.storage_location == storage_location,
            ).limit(1).with_for_update()
        )
        record: InventoryRecord | None = result.scalars().first()

        if record is None:
            record = InventoryRecord(
                product_id=product_id,
                batch_number=batch_number,
                expiry_date=expiry_date,
                storage_location=storage_location,
                quantity_on_hand=0,
            )
            self._db.add(record)

        record.quantity_on_hand = float(record.quantity_on_hand) + quantity_delta
        if expiry_date and not record.expiry_date:
            record.expiry_date = expiry_date

        movement = StockMovement(
            product_id=product_id,
            batch_number=batch_number,
            movement_type=movement_type,
            quantity=quantity_delta,
            reference=reference,
        )
        self._db.add(movement)
        await self._db.flush()

        logger.info(
            "Stock updated: product=%s batch=%s delta=%.4f new_qty=%.4f",
            product_id,
            batch_number,
            quantity_delta,
            record.quantity_on_hand,
        )
        return record

    async def get_stock_level(
        self, product_id: uuid.UUID, batch_number: str | None = None
    ) -> list[InventoryRecord]:
        query = select(InventoryRecord).where(InventoryRecord.product_id == product_id)
        if batch_number:
            query = query.where(InventoryRecord.batch_number == batch_number)
        result = await self._db.execute(query)
        return result.scalars().all()

    async def get_movements(
        self, product_id: uuid.UUID, limit: int = 50
    ) -> list[StockMovement]:
        result = await self._db.execute(
            select(StockMovement)
            .where(StockMovement.product_id == product_id)
            .order_by(StockMovement.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
