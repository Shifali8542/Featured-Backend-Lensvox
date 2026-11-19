"""
Catalogue API – products and label code management (including Case F).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_db
from app.modules.catalogue.schemas import (
    LabelCodeCreate,
    LabelCodeResponse,
    LinkBarcodeRequest,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from app.modules.catalogue.service import CatalogueService
from app.utils.response import ok, paginated

router = APIRouter(prefix="/catalogue", tags=["Catalogue"])


# ── Products ──────────────────────────────────────────────────────────────────

@router.post("/products", response_model=dict, status_code=201)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = CatalogueService(db)
    product = await svc.create_product(payload)
    return ok(data=ProductResponse.model_validate(product).model_dump(), message="Product created.")


@router.get("/products/{product_id}", response_model=dict)
async def get_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = CatalogueService(db)
    product = await svc.get_product(product_id)
    return ok(data=ProductResponse.model_validate(product).model_dump())


@router.get("/products", response_model=dict)
async def search_products(
    q: str = Query(..., min_length=1, description="Search by SKU or name"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = CatalogueService(db)
    products, total = await svc.search_products(q, page, page_size)
    return paginated(
        items=[ProductResponse.model_validate(p).model_dump() for p in products],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/products/{product_id}", response_model=dict)
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = CatalogueService(db)
    product = await svc.update_product(product_id, payload)
    return ok(data=ProductResponse.model_validate(product).model_dump(), message="Product updated.")


# ── Label Codes ───────────────────────────────────────────────────────────────

@router.post("/products/{product_id}/codes", response_model=dict, status_code=201)
async def add_label_code(
    product_id: uuid.UUID,
    payload: LabelCodeCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    svc = CatalogueService(db)
    lc = await svc.add_label_code(product_id, payload)
    return ok(data=LabelCodeResponse.model_validate(lc).model_dump(), message="Code linked.")


@router.post("/barcodes/link", response_model=dict, status_code=201)
async def link_unknown_barcode(
    payload: LinkBarcodeRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Case F: Link an unrecognised barcode to an existing product or create a new one.
    Requires catalogue manager permission (enforced by auth middleware in production).
    """
    # TODO: inject real user_id from JWT token
    mock_user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    svc = CatalogueService(db)
    lc = await svc.link_unknown_barcode(payload, mock_user_id)
    return ok(
        data=LabelCodeResponse.model_validate(lc).model_dump(),
        message="Barcode linked successfully.",
    )
