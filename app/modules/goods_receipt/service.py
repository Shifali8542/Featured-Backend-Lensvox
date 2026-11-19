"""
GoodsReceiptService – the core GR workflow.

Flow:
  1. Create GR header (with optional PO reference).
  2. For each scanned line:
     a. Match product to a PO line.
     b. Run validators (shortage, expiry, product match).
     c. Persist GR line + discrepancy records.
     d. Update PO line received quantity.
  3. Finalise GR → update inventory.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.exceptions.base import GoodsReceiptNotFoundException, GRAlreadyFinalised
from app.modules.catalogue.models import Product
from app.modules.goods_receipt.models import (
    GRDiscrepancy,
    GRLine,
    GRStatus,
    GoodsReceipt,
)
from app.modules.goods_receipt.schemas import (
    AddGRLineRequest,
    GoodsReceiptCreate,
    GRSummaryResponse,
)
from app.modules.goods_receipt.validators import DiscrepancyFlag, run_all_validators
from app.modules.inventory.service import InventoryService
from app.modules.purchase_order.service import PurchaseOrderService

logger = get_logger(__name__)

_GR_COUNTER_PREFIX = "GR"


def _generate_gr_number() -> str:
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{_GR_COUNTER_PREFIX}-{ts}"


class GoodsReceiptService:

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._po_svc = PurchaseOrderService(db)
        self._inv_svc = InventoryService(db)

    # ─────────────────────────────────────────────────────────────────────────
    # Create GR
    # ─────────────────────────────────────────────────────────────────────────

    async def create_goods_receipt(self, data: GoodsReceiptCreate) -> GoodsReceipt:
        gr = GoodsReceipt(
            gr_number=_generate_gr_number(),
            purchase_order_id=data.purchase_order_id,
            received_date=data.received_date or datetime.now(tz=timezone.utc).date(),
            status=GRStatus.IN_PROGRESS,
            notes=data.notes,
        )
        self._db.add(gr)
        await self._db.flush()

        for line_data in data.lines:
            await self._process_line(gr, line_data.parsed_label, line_data.quantity_received,
                                     line_data.unit_of_measure, line_data.po_id)

        # Mark header if any line has a discrepancy
        gr.has_discrepancies = any(l.has_discrepancy for l in gr.lines)
        await self._db.flush()

        logger.info("Created GR %s with %d lines (discrepancies=%s)", gr.gr_number,
                    len(gr.lines), gr.has_discrepancies)
        return gr

    # ─────────────────────────────────────────────────────────────────────────
    # Add a single scanned line to an existing GR
    # ─────────────────────────────────────────────────────────────────────────

    async def add_line(self, req: AddGRLineRequest) -> GRLine:
        gr = await self.get_gr(req.gr_id)
        if gr.status == GRStatus.FINALISED:
            raise GRAlreadyFinalised()

        line = await self._process_line(
            gr, req.parsed_label, req.quantity_received, req.unit_of_measure, req.po_id
        )
        gr.has_discrepancies = gr.has_discrepancies or line.has_discrepancy
        await self._db.flush()
        return line

    # ─────────────────────────────────────────────────────────────────────────
    # Finalise GR
    # ─────────────────────────────────────────────────────────────────────────

    async def finalise(self, gr_id: uuid.UUID, notes: str | None = None) -> GoodsReceipt:
        gr = await self.get_gr(gr_id)
        if gr.status == GRStatus.FINALISED:
            raise GRAlreadyFinalised()

        # Update inventory for each received line
        for line in gr.lines:
            await self._inv_svc.update_stock(
                product_id=line.product_id,
                batch_number=line.batch_number,
                expiry_date=line.expiry_date,
                quantity_delta=float(line.quantity_received),
                reference=gr.gr_number,
            )

        gr.status = GRStatus.FINALISED
        if notes:
            gr.notes = (gr.notes or "") + f"\n[Finalised] {notes}"
        await self._db.flush()

        logger.info("GR %s finalised", gr.gr_number)
        return gr

    # ─────────────────────────────────────────────────────────────────────────
    # Retrieval
    # ─────────────────────────────────────────────────────────────────────────

    async def get_gr(self, gr_id: uuid.UUID) -> GoodsReceipt:
        result = await self._db.execute(
            select(GoodsReceipt)
            .where(GoodsReceipt.id == gr_id)
            .options(
                selectinload(GoodsReceipt.lines).selectinload(GRLine.discrepancies)
            )
        )
        gr = result.scalars().first()
        if not gr:
            raise GoodsReceiptNotFoundException(f"GR {gr_id} not found.")

        # Enrich each line with product name + SKU so the UI can display them
        if gr.lines:
            product_ids = list({line.product_id for line in gr.lines})
            products_result = await self._db.execute(
                select(Product).where(Product.id.in_(product_ids))
            )
            product_map: dict[uuid.UUID, Product] = {
                p.id: p for p in products_result.scalars().all()
            }
            for line in gr.lines:
                prod = product_map.get(line.product_id)
                # Attach as transient attributes — Pydantic reads them via from_attributes
                line.product_name = prod.name if prod else None  # type: ignore[attr-defined]
                line.product_sku = prod.sku if prod else None    # type: ignore[attr-defined]

        return gr

    async def get_summary(self, gr_id: uuid.UUID) -> GRSummaryResponse:
        gr = await self.get_gr(gr_id)

        po_number: str | None = None
        if gr.purchase_order_id:
            try:
                po = await self._po_svc.get_po(gr.purchase_order_id)
                po_number = po.po_number
            except Exception:
                pass

        all_disc_types: list[str] = []
        for line in gr.lines:
            for d in line.discrepancies:
                if d.discrepancy_type.value not in all_disc_types:
                    all_disc_types.append(d.discrepancy_type.value)

        return GRSummaryResponse(
            gr_id=gr.id,
            gr_number=gr.gr_number,
            po_number=po_number,
            total_lines=len(gr.lines),
            lines_with_discrepancies=sum(1 for l in gr.lines if l.has_discrepancy),
            total_quantity_received=sum(float(l.quantity_received) for l in gr.lines),
            discrepancy_types=all_disc_types,
            status=gr.status,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _process_line(
        self, gr: GoodsReceipt, parsed_label, quantity_received: float,
        unit_of_measure: str, po_id: uuid.UUID | None
    ) -> GRLine:
        """
        Core per-scan processing:
          1. Match to PO line.
          2. Validate (shortage, expiry, product match).
          3. Persist GRLine + GRDiscrepancy records.
          4. Update PO line received qty.
        """
        product_id_str = parsed_label.product_id
        po_line_id: uuid.UUID | None = None
        quantity_outstanding: float | None = None
        po_product_id_str: str | None = None
        flags: list[DiscrepancyFlag] = []

        # ── PO matching ──────────────────────────────────────────────────────
        if product_id_str:
            product_uuid = uuid.UUID(product_id_str)
            context_po_id = po_id or gr.purchase_order_id
            try:
                match = await self._po_svc.match_product_to_po(
                    product_uuid, context_po_id, quantity_received
                )
                po_line_id = match.po_line_id
                quantity_outstanding = match.quantity_outstanding
                po_product_id_str = str(match.product_id)

                # Update PO line
                await self._po_svc.update_po_line_received(po_line_id, quantity_received)
            except Exception as e:
                logger.warning("PO match failed for product %s: %s", product_id_str, e)
                flags.append(DiscrepancyFlag(
                    discrepancy_type=__import__(
                        "app.modules.goods_receipt.models", fromlist=["DiscrepancyType"]
                    ).DiscrepancyType.WRONG_PRODUCT,
                    expected_value=None,
                    actual_value=product_id_str,
                    description=f"No open PO line found: {e}",
                ))

        # ── Validators ───────────────────────────────────────────────────────
        flags.extend(
            run_all_validators(
                quantity_received=quantity_received,
                quantity_outstanding=quantity_outstanding,
                expiry_date=parsed_label.expiry_date,
                scanned_product_id=product_id_str,
                po_product_id=po_product_id_str,
            )
        )

        # ── Persist GR line ──────────────────────────────────────────────────
        gr_line = GRLine(
            goods_receipt_id=gr.id,
            product_id=uuid.UUID(product_id_str) if product_id_str else uuid.uuid4(),
            po_line_id=po_line_id,
            label_type=parsed_label.label_type.value,
            barcode=parsed_label.barcode,
            gtin=parsed_label.gtin,
            batch_number=parsed_label.batch_number,
            serial_number=parsed_label.serial_number,
            expiry_date=parsed_label.expiry_date,
            manufacture_date=parsed_label.manufacture_date,
            quantity_received=quantity_received,
            unit_of_measure=unit_of_measure,
            has_discrepancy=len(flags) > 0,
        )
        self._db.add(gr_line)
        await self._db.flush()

        # ── Persist discrepancies ─────────────────────────────────────────────
        for flag in flags:
            disc = GRDiscrepancy(
                gr_line_id=gr_line.id,
                discrepancy_type=flag.discrepancy_type,
                expected_value=flag.expected_value,
                actual_value=flag.actual_value,
                description=flag.description,
            )
            self._db.add(disc)

        await self._db.flush()
        return gr_line