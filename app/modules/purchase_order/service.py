"""
PurchaseOrderService – CRUD + PO matching logic used by the GR service.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.exceptions.base import (
    DuplicateEntryException,
    POAlreadyClosedException,
    PurchaseOrderNotFoundException,
)
from app.modules.purchase_order.models import POLine, POStatus, PurchaseOrder
from app.modules.purchase_order.schemas import (
    POMatchResult,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
)

logger = get_logger(__name__)


class PurchaseOrderService:

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── CRUD ──────────────────────────────────────────────────────────────────

    async def create_po(self, data: PurchaseOrderCreate) -> PurchaseOrder:
        existing = await self._db.execute(
            select(PurchaseOrder).where(PurchaseOrder.po_number == data.po_number)
        )
        if existing.scalars().first():
            raise DuplicateEntryException(
                f"Purchase Order '{data.po_number}' already exists."
            )

        po = PurchaseOrder(
            po_number=data.po_number,
            supplier_name=data.supplier_name,
            supplier_code=data.supplier_code,
            expected_delivery_date=data.expected_delivery_date,
            notes=data.notes,
            status=POStatus.DRAFT,
        )
        self._db.add(po)
        await self._db.flush()

        for idx, line_data in enumerate(data.lines, start=1):
            line = POLine(
                purchase_order_id=po.id,
                product_id=line_data.product_id,
                line_number=idx,
                quantity_ordered=line_data.quantity_ordered,
                unit_price=line_data.unit_price,
                unit_of_measure=line_data.unit_of_measure,
            )
            self._db.add(line)

        await self._db.flush()
        logger.info("Created PO %s with %d lines", po.po_number, len(data.lines))
        return po

    async def get_po(self, po_id: uuid.UUID) -> PurchaseOrder:
        result = await self._db.execute(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == po_id)
            .options(selectinload(PurchaseOrder.lines))
        )
        po = result.scalars().first()
        if not po:
            raise PurchaseOrderNotFoundException(f"PO {po_id} not found.")
        return po

    async def get_po_by_number(self, po_number: str) -> PurchaseOrder:
        result = await self._db.execute(
            select(PurchaseOrder)
            .where(PurchaseOrder.po_number == po_number)
            .options(selectinload(PurchaseOrder.lines))
        )
        po = result.scalars().first()
        if not po:
            raise PurchaseOrderNotFoundException(f"PO '{po_number}' not found.")
        return po

    async def list_open_pos(self, page: int = 1, page_size: int = 20) -> tuple[list[PurchaseOrder], int]:
        open_statuses = [POStatus.OPEN, POStatus.APPROVED, POStatus.PARTIALLY_RECEIVED]
        base = (
            select(PurchaseOrder)
            .where(PurchaseOrder.status.in_(open_statuses))
            .options(selectinload(PurchaseOrder.lines))
        )
        count_result = await self._db.execute(
            select(func.count()).select_from(
                select(PurchaseOrder).where(PurchaseOrder.status.in_(open_statuses)).subquery()
            )
        )
        total = count_result.scalar_one()
        result = await self._db.execute(
            base.offset((page - 1) * page_size).limit(page_size)
        )
        return result.scalars().all(), total

    async def update_po_status(self, po_id: uuid.UUID, status: POStatus) -> PurchaseOrder:
        po = await self.get_po(po_id)
        if po.status in (POStatus.CLOSED, POStatus.CANCELLED):
            raise POAlreadyClosedException()
        po.status = status
        await self._db.flush()
        return po

    # ── PO Matching (called by GR service) ────────────────────────────────────

    async def match_product_to_po(
        self,
        product_id: uuid.UUID,
        po_id: uuid.UUID | None,
        quantity_to_receive: float,
    ) -> POMatchResult:
        """
        Find the open PO line for `product_id`.
        If `po_id` is provided, search within that PO only.
        Returns a POMatchResult with shortage / excess analysis.
        """
        query = (
            select(POLine)
            .join(PurchaseOrder, POLine.purchase_order_id == PurchaseOrder.id)
            .where(
                POLine.product_id == product_id,
                PurchaseOrder.status.in_(
                    [POStatus.OPEN, POStatus.APPROVED, POStatus.PARTIALLY_RECEIVED]
                ),
            )
        )
        if po_id:
            query = query.where(POLine.purchase_order_id == po_id)

        result = await self._db.execute(query.limit(1))
        line: POLine | None = result.scalars().first()

        if not line:
            raise PurchaseOrderNotFoundException(
                f"No open PO line found for product {product_id}."
            )

        po = await self._db.get(PurchaseOrder, line.purchase_order_id)
        outstanding = float(line.quantity_ordered) - float(line.quantity_received)
        shortage = max(0.0, outstanding - quantity_to_receive)
        excess = max(0.0, quantity_to_receive - outstanding)

        return POMatchResult(
            po_id=line.purchase_order_id,
            po_number=po.po_number,  # type: ignore[union-attr]
            po_line_id=line.id,
            product_id=line.product_id,
            quantity_ordered=float(line.quantity_ordered),
            quantity_already_received=float(line.quantity_received),
            quantity_outstanding=outstanding,
            is_shortage=shortage > 0,
            shortage_quantity=shortage,
            excess_quantity=excess,
        )

    async def list_open_pos_for_product(
        self, product_id: uuid.UUID
    ) -> list[dict]:
        """
        Return all open PO lines that contain the given product.
        Used by the mobile app to let the user choose a PO when several match.
        """
        from app.modules.purchase_order.schemas import OpenPOForProductResponse

        open_statuses = [POStatus.OPEN, POStatus.APPROVED, POStatus.PARTIALLY_RECEIVED]
        result = await self._db.execute(
            select(POLine)
            .join(PurchaseOrder, POLine.purchase_order_id == PurchaseOrder.id)
            .where(
                POLine.product_id == product_id,
                PurchaseOrder.status.in_(open_statuses),
            )
            .order_by(PurchaseOrder.expected_delivery_date.asc().nullsfirst())
        )
        lines = result.scalars().all()

        output = []
        for line in lines:
            po = await self._db.get(PurchaseOrder, line.purchase_order_id)
            if po is None:
                continue
            outstanding = float(line.quantity_ordered) - float(line.quantity_received)
            output.append(
                OpenPOForProductResponse(
                    po_id=po.id,
                    po_number=po.po_number,
                    supplier_name=po.supplier_name,
                    quantity_ordered=float(line.quantity_ordered),
                    quantity_received=float(line.quantity_received),
                    quantity_outstanding=outstanding,
                )
            )
        return [item.model_dump() for item in output]

    async def update_po_line_received(
        self, po_line_id: uuid.UUID, quantity_received: float
    ) -> None:
        """Increment received qty on the PO line and mark fully received if appropriate."""
        line = await self._db.get(POLine, po_line_id)
        if not line:
            return
        line.quantity_received = float(line.quantity_received) + quantity_received
        line.is_fully_received = float(line.quantity_received) >= float(line.quantity_ordered)
        await self._db.flush()

        # Recalculate PO status
        po = await self.get_po(line.purchase_order_id)
        all_lines_received = all(l.is_fully_received for l in po.lines)
        any_line_received = any(float(l.quantity_received) > 0 for l in po.lines)

        if all_lines_received:
            po.status = POStatus.FULLY_RECEIVED
        elif any_line_received:
            po.status = POStatus.PARTIALLY_RECEIVED

        await self._db.flush()