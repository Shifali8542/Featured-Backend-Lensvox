"""
CatalogueService – product and label code CRUD + Case F link/create.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.exceptions.base import (
    DuplicateEntryException,
    InsufficientPermissionForCatalogueException,
    NotFoundException,
    ProductNotFoundException,
)
from app.modules.catalogue.models import LabelCode, Product
from app.modules.catalogue.schemas import (
    LabelCodeCreate,
    LinkBarcodeRequest,
    ProductCreate,
    ProductUpdate,
)

logger = get_logger(__name__)


class CatalogueService:

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Products ──────────────────────────────────────────────────────────────

    async def create_product(self, data: ProductCreate) -> Product:
        existing = await self._db.execute(
            select(Product).where(Product.sku == data.sku)
        )
        if existing.scalars().first():
            raise DuplicateEntryException(f"Product with SKU '{data.sku}' already exists.")

        product = Product(**data.model_dump())
        self._db.add(product)
        await self._db.flush()
        logger.info("Created product SKU=%s", product.sku)
        return product

    async def get_product(self, product_id: uuid.UUID) -> Product:
        product = await self._db.get(Product, product_id)
        if not product:
            raise ProductNotFoundException(f"Product {product_id} not found.")
        return product

    async def search_products(
        self, query: str, page: int = 1, page_size: int = 20
    ) -> tuple[list[Product], int]:
        base = select(Product).where(
            or_(
                Product.sku.ilike(f"%{query}%"),
                Product.name.ilike(f"%{query}%"),
            )
        )
        total_result = await self._db.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = total_result.scalar_one()

        result = await self._db.execute(
            base.offset((page - 1) * page_size).limit(page_size)
        )
        return result.scalars().all(), total

    async def update_product(self, product_id: uuid.UUID, data: ProductUpdate) -> Product:
        product = await self.get_product(product_id)
        for field, value in data.model_dump(exclude_none=True).items():
            setattr(product, field, value)
        await self._db.flush()
        return product

    # ── Label Codes ───────────────────────────────────────────────────────────

    async def add_label_code(
        self, product_id: uuid.UUID, data: LabelCodeCreate
    ) -> LabelCode:
        await self.get_product(product_id)  # ensure product exists

        existing = await self._db.execute(
            select(LabelCode).where(LabelCode.code == data.code)
        )
        if existing.scalars().first():
            raise DuplicateEntryException(f"Code '{data.code}' is already linked to a product.")

        lc = LabelCode(
            product_id=product_id,
            code=data.code,
            code_type=data.code_type,
            is_primary=data.is_primary,
        )
        self._db.add(lc)
        await self._db.flush()
        return lc

    # ── Case F: Link unknown barcode ──────────────────────────────────────────

    async def link_unknown_barcode(
        self, req: LinkBarcodeRequest, user_id: uuid.UUID
    ) -> LabelCode:
        """
        Authorised catalogue users can:
        a) Link the unrecognised code to an existing product, or
        b) Create a new product and link it in one step.
        """
        if req.existing_product_id is None and req.new_product is None:
            raise ValueError("Provide either existing_product_id or new_product.")

        if req.existing_product_id:
            target_id = req.existing_product_id
            await self.get_product(target_id)  # validate
        else:
            assert req.new_product is not None
            new_prod = await self.create_product(req.new_product)
            target_id = new_prod.id

        lc = LabelCode(
            product_id=target_id,
            code=req.unlinked_code,
            code_type=req.code_type,
            is_primary=False,
            linked_by_user_id=user_id,
        )
        self._db.add(lc)
        await self._db.flush()
        logger.info(
            "Case F: code=%s linked to product_id=%s by user=%s",
            req.unlinked_code,
            target_id,
            user_id,
        )
        return lc
