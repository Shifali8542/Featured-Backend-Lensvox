"""
Purchase Order API endpoints.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.modules.purchase_order.models import POStatus
from app.modules.purchase_order.schemas import (
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    PurchaseOrderUpdate,
)
from app.modules.purchase_order.service import PurchaseOrderService
from app.utils.response import ok, paginated

router = APIRouter(prefix="/purchase-orders", tags=["Purchase Orders"])


@router.post("", response_model=dict, status_code=201)
async def create_purchase_order(
    payload: PurchaseOrderCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = PurchaseOrderService(db)
    po = await svc.create_po(payload)
    po_with_lines = await svc.get_po(po.id)
    return ok(
        data=PurchaseOrderResponse.model_validate(po_with_lines).model_dump(),
        message="Purchase Order created.",
    )


@router.get("", response_model=dict)
async def list_open_purchase_orders(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = PurchaseOrderService(db)
    pos, total = await svc.list_open_pos(page, page_size)
    return paginated(
        items=[PurchaseOrderResponse.model_validate(po).model_dump() for po in pos],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/open", response_model=dict, summary="List open POs containing a product")
async def list_open_pos_for_product(
    product_id: uuid.UUID = Query(..., description="Product UUID from a label scan"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Returns all open Purchase Orders (status: approved, open, partially received)
    that contain the given product.  Used by the mobile app after a label scan
    when several POs match, so the warehouse operator can choose the right one.
    """
    svc = PurchaseOrderService(db)
    items = await svc.list_open_pos_for_product(product_id)
    return ok(data=items, message=f"{len(items)} open PO(s) found for this product.")


@router.get("/{po_id}", response_model=dict)
async def get_purchase_order(
    po_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = PurchaseOrderService(db)
    po = await svc.get_po(po_id)
    return ok(data=PurchaseOrderResponse.model_validate(po).model_dump())


@router.patch("/{po_id}/status", response_model=dict)
async def update_po_status(
    po_id: uuid.UUID,
    status: POStatus,
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = PurchaseOrderService(db)
    po = await svc.update_po_status(po_id, status)
    return ok(data={"id": str(po.id), "status": po.status}, message="PO status updated.")