"""
Seed test data for Goods Receipt IMS.
Run from the backend directory:

    cd /home/claude/goods_receipt_backend
    python seed_test_data.py

This script is idempotent — running it multiple times is safe.
It inserts (or upserts) the following:

  Product:  TEST-001 / "Test Product Alpha"
            Barcodes: 1234567890128  (EAN-13)
                      TEST-SKU-001   (plain SKU code)

  PO:       PO-2024-001 | status = APPROVED | 100 units outstanding
              → scanning 90 units will trigger a SHORTAGE of 10

  PO:       PO-2024-002 | status = APPROVED | 50 units of a second product
              → for multi-line receipt testing

  Product:  TEST-002 / "Test Product Beta"
            Barcode: 9876543210987
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import text, select

# ---------------------------------------------------------------------------
# Config — matches .env
# ---------------------------------------------------------------------------
DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/goods_receipt_db"

# ---------------------------------------------------------------------------
# Lazy imports of ORM models
# ---------------------------------------------------------------------------
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.modules.catalogue.models import Product, LabelCode
from app.modules.purchase_order.models import PurchaseOrder, POLine, POStatus
from app.database.base import Base


engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession,
                                        expire_on_commit=False, autocommit=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def upsert_product(db: AsyncSession, sku: str, name: str, description: str) -> Product:
    result = await db.execute(select(Product).where(Product.sku == sku))
    product = result.scalar_one_or_none()
    if product is None:
        product = Product(
            id=uuid.uuid4(),
            sku=sku,
            name=name,
            description=description,
            unit_of_measure="EA",
            is_active=True,
        )
        db.add(product)
        await db.flush()
        print(f"  ✓ Created product: {sku} — {name}")
    else:
        print(f"  ⟳ Product already exists: {sku} — {name}")
    return product


async def upsert_label_code(
    db: AsyncSession,
    code: str,
    product_id: uuid.UUID,
    code_type: str = "EAN13",
    is_primary: bool = False,
) -> None:
    result = await db.execute(select(LabelCode).where(LabelCode.code == code))
    lc = result.scalar_one_or_none()
    if lc is None:
        lc = LabelCode(
            id=uuid.uuid4(),
            code=code,
            product_id=product_id,
            code_type=code_type,
            is_primary=is_primary,
        )
        db.add(lc)
        print(f"    ↳ Linked barcode: {code}  [{code_type}]")
    else:
        print(f"    ⟳ Barcode already linked: {code}")


async def upsert_po(
    db: AsyncSession,
    po_number: str,
    supplier_name: str,
    status: POStatus,
    expected_delivery_date: date | None,
    lines: list[dict],  # [{product_id, quantity_ordered, quantity_received}]
) -> PurchaseOrder:
    result = await db.execute(select(PurchaseOrder).where(PurchaseOrder.po_number == po_number))
    po = result.scalar_one_or_none()
    if po is None:
        po = PurchaseOrder(
            id=uuid.uuid4(),
            po_number=po_number,
            supplier_name=supplier_name,
            status=status,
            expected_delivery_date=expected_delivery_date,
            is_active=True,
        )
        db.add(po)
        await db.flush()
        print(f"  ✓ Created PO: {po_number} [{status.value}]")
    else:
        # Update status in case it was seeded as DRAFT before
        old_status = po.status
        po.status = status
        await db.flush()
        if old_status != status:
            print(f"  ✎ Updated PO status: {po_number} {old_status.value} → {status.value}")
        else:
            print(f"  ⟳ PO already exists: {po_number} [{status.value}]")

    # Upsert lines
    for i, line_data in enumerate(lines, start=1):
        result2 = await db.execute(
            select(POLine).where(
                POLine.purchase_order_id == po.id,
                POLine.product_id == line_data["product_id"],
            )
        )
        existing_line = result2.scalar_one_or_none()
        if existing_line is None:
            po_line = POLine(
                id=uuid.uuid4(),
                purchase_order_id=po.id,
                product_id=line_data["product_id"],
                line_number=i,
                quantity_ordered=line_data["quantity_ordered"],
                quantity_received=line_data.get("quantity_received", 0),
                unit_of_measure="EA",
            )
            db.add(po_line)
            print(f"    ↳ Line {i}: {line_data['quantity_ordered']} units ordered, {line_data.get('quantity_received', 0)} received")
        else:
            print(f"    ⟳ PO line already exists for product")

    return po


# ---------------------------------------------------------------------------
# Main seed
# ---------------------------------------------------------------------------

async def seed() -> None:
    async with AsyncSessionLocal() as db:
        print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(" Seeding test data into goods_receipt_db")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        # ── Product 1 ─────────────────────────────────────────────────────────
        print("📦  Products")
        p1 = await upsert_product(db, "TEST-001", "Test Product Alpha",
                                   "Main test product — scan barcode 1234567890128")
        await upsert_label_code(db, "1234567890128", p1.id, code_type="EAN13",  is_primary=True)
        await upsert_label_code(db, "TEST-SKU-001",  p1.id, code_type="MANUAL", is_primary=False)

        # ── Product 2 ─────────────────────────────────────────────────────────
        p2 = await upsert_product(db, "TEST-002", "Test Product Beta",
                                   "Second test product — scan barcode 9876543210987")
        await upsert_label_code(db, "9876543210987", p2.id, code_type="EAN13",  is_primary=True)
        await upsert_label_code(db, "TEST-SKU-002",  p2.id, code_type="MANUAL", is_primary=False)

        print()
        print("🛒  Purchase Orders")

        # ── PO 1 — APPROVED, 100 units → scan 90 → triggers SHORTAGE of 10 ───
        await upsert_po(
            db,
            po_number="PO-2024-001",
            supplier_name="Test Supplier Ltd",
            status=POStatus.APPROVED,
            expected_delivery_date=date(2024, 12, 31),
            lines=[
                {
                    "product_id": p1.id,
                    "quantity_ordered": 100,
                    "quantity_received": 0,
                },
            ],
        )

        # ── PO 2 — APPROVED, multi-product ───────────────────────────────────
        await upsert_po(
            db,
            po_number="PO-2024-002",
            supplier_name="Test Supplier Ltd",
            status=POStatus.APPROVED,
            expected_delivery_date=date(2024, 12, 31),
            lines=[
                {
                    "product_id": p1.id,
                    "quantity_ordered": 50,
                    "quantity_received": 0,
                },
                {
                    "product_id": p2.id,
                    "quantity_ordered": 200,
                    "quantity_received": 0,
                },
            ],
        )

        await db.commit()

        print()
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("✅  Seed complete!\n")
        print("Test scenarios:")
        print()
        print("  Scan barcode:  1234567890128   (EAN-13 for Test Product Alpha)")
        print("  Search by SKU: TEST-001  or  Test Product Alpha")
        print()
        print("  Quantity 90  → PO-2024-001 matched, SHORTAGE of 10 flagged")
        print("  Quantity 100 → PO-2024-001 matched, no shortage")
        print("  Quantity 110 → PO-2024-001 matched, EXCESS flagged")
        print()
        print("  Scan barcode:  9876543210987   (Test Product Beta)")
        print("  Search by SKU: TEST-002")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


if __name__ == "__main__":
    asyncio.run(seed())
