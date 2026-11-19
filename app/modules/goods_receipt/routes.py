"""
Goods Receipt API endpoints.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.modules.goods_receipt.schemas import (
    AddGRLineRequest,
    FinaliseGRRequest,
    GoodsReceiptCreate,
    GoodsReceiptResponse,
    GRLineResponse,
    GRSummaryResponse,
)
from app.modules.goods_receipt.service import GoodsReceiptService
from app.utils.response import ok

router = APIRouter(prefix="/goods-receipts", tags=["Goods Receipts"])


@router.post(
    "",
    response_model=dict,
    status_code=201,
    summary="Create a new Goods Receipt",
    description=(
        "Creates a GR header and processes all scanned lines in a single transaction. "
        "Each line is matched against an open PO, validated for shortages and expiry, "
        "and discrepancies are automatically flagged."
    ),
)
async def create_goods_receipt(
    payload: GoodsReceiptCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = GoodsReceiptService(db)
    gr = await svc.create_goods_receipt(payload)
    gr_full = await svc.get_gr(gr.id)
    return ok(
        data=GoodsReceiptResponse.model_validate(gr_full).model_dump(),
        message="Goods Receipt created.",
    )


@router.get(
    "/{gr_id}",
    response_model=dict,
    summary="Get a Goods Receipt by ID",
)
async def get_goods_receipt(
    gr_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = GoodsReceiptService(db)
    gr = await svc.get_gr(gr_id)
    return ok(data=GoodsReceiptResponse.model_validate(gr).model_dump())


@router.post(
    "/{gr_id}/lines",
    response_model=dict,
    status_code=201,
    summary="Add a scanned line to an existing GR",
)
async def add_gr_line(
    gr_id: uuid.UUID,
    payload: AddGRLineRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    payload.gr_id = gr_id
    svc = GoodsReceiptService(db)
    line = await svc.add_line(payload)
    return ok(
        data=GRLineResponse.model_validate(line).model_dump(),
        message="Line added to Goods Receipt.",
    )


@router.post(
    "/{gr_id}/finalise",
    response_model=dict,
    summary="Finalise a Goods Receipt",
    description=(
        "Locks the GR, updates inventory stock levels, and marks PO lines as received. "
        "Cannot be undone."
    ),
)
async def finalise_goods_receipt(
    gr_id: uuid.UUID,
    payload: FinaliseGRRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = GoodsReceiptService(db)
    gr = await svc.finalise(gr_id, payload.notes)
    return ok(
        data={"id": str(gr.id), "gr_number": gr.gr_number, "status": gr.status},
        message="Goods Receipt finalised and inventory updated.",
    )


@router.get(
    "/{gr_id}/summary",
    response_model=dict,
    summary="Get a GR summary with discrepancy overview",
)
async def get_gr_summary(
    gr_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = GoodsReceiptService(db)
    summary = await svc.get_summary(gr_id)
    return ok(data=summary.model_dump())
