"""
LabelParserService – the central dispatch for all 6 label cases.

Receives a ScanLabelRequest, auto-detects or uses the hint to pick the
right parsing strategy, queries the catalogue for a product match, and
returns a ParsedLabelData ready for the GR service to consume.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.exceptions.base import InvalidLabelException, UnknownBarcodeException
from app.modules.label_parser.gs1_parser import extract_label_fields, _looks_like_gs1
from app.modules.label_parser.schemas import (
    LabelType,
    ParseStatus,
    ParsedLabelData,
    ScanLabelRequest,
)
from app.modules.label_parser.supplier_qr_parser import parse_supplier_qr

logger = get_logger(__name__)


class LabelParserService:
    """Stateless service – create once per request (or as a singleton)."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def parse(self, req: ScanLabelRequest) -> ParsedLabelData:
        """
        Main entry point.  Returns a ParsedLabelData regardless of case.
        """
        label_type = req.label_type_hint or self._detect_type(req)
        logger.info("LabelParser: detected type=%s raw_len=%s", label_type, len(req.raw_data or ""))

        match label_type:
            case LabelType.GS1:
                return await self._handle_gs1(req)
            case LabelType.PLAIN_BARCODE:
                return await self._handle_plain_barcode(req)
            case LabelType.SUPPLIER_QR:
                return await self._handle_supplier_qr(req)
            case LabelType.MANUAL:
                return await self._handle_manual(req)
            case LabelType.DAMAGED:
                return await self._handle_damaged(req)
            case LabelType.UNKNOWN:
                return await self._handle_unknown(req)
            case _:
                raise InvalidLabelException(f"Unsupported label type: {label_type}")

    # ─────────────────────────────────────────────────────────────────────────
    # Auto-detection
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_type(self, req: ScanLabelRequest) -> LabelType:
        raw = (req.raw_data or "").strip()

        if not raw and req.manual_product_ref:
            return LabelType.MANUAL

        if not raw:
            return LabelType.MANUAL

        # GS1: starts with known AI, all numeric or FNC1-delimited
        if _looks_like_gs1(raw):
            return LabelType.GS1

        # JSON or key=value pipe → supplier QR
        if (raw.startswith("{") and raw.endswith("}")) or re.search(r"\w+=\S+[|;]", raw):
            return LabelType.SUPPLIER_QR

        # Pure numeric EAN/UPC/Code-128 style → plain barcode
        if re.fullmatch(r"\d{6,20}", raw):
            return LabelType.PLAIN_BARCODE

        # Alphanumeric – could be a plain code-128 or unknown
        if re.fullmatch(r"[A-Za-z0-9\-_./ ]{4,50}", raw):
            return LabelType.PLAIN_BARCODE

        return LabelType.UNKNOWN

    # ─────────────────────────────────────────────────────────────────────────
    # Case A – GS1
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_gs1(self, req: ScanLabelRequest) -> ParsedLabelData:
        try:
            fields = extract_label_fields(req.raw_data or "")
        except ValueError as e:
            raise InvalidLabelException(str(e)) from e

        notes: list[str] = []
        product_id, product_name, sku = await self._lookup_product(
            gtin=fields.get("gtin"), barcode=None, notes=notes
        )

        status = ParseStatus.SUCCESS if product_id else ParseStatus.NOT_FOUND

        return ParsedLabelData(
            label_type=LabelType.GS1,
            parse_status=status,
            gtin=fields.get("gtin"),
            product_id=product_id,
            product_name=product_name,
            sku=sku,
            batch_number=fields.get("batch_number"),
            serial_number=fields.get("serial_number"),
            expiry_date=fields.get("expiry_date"),
            manufacture_date=fields.get("manufacture_date"),
            quantity=fields.get("quantity"),
            gs1_ais=fields.get("gs1_ais"),
            notes=notes,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Case B – Plain barcode
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_plain_barcode(self, req: ScanLabelRequest) -> ParsedLabelData:
        barcode = (req.raw_data or "").strip()
        notes: list[str] = []
        product_id, product_name, sku = await self._lookup_product(
            gtin=None, barcode=barcode, notes=notes
        )

        if not product_id:
            # Could not find – treat as unknown
            return ParsedLabelData(
                label_type=LabelType.PLAIN_BARCODE,
                parse_status=ParseStatus.NOT_FOUND,
                barcode=barcode,
                notes=notes + ["Product not found for this barcode."],
            )

        return ParsedLabelData(
            label_type=LabelType.PLAIN_BARCODE,
            parse_status=ParseStatus.PARTIAL,  # batch/expiry still needed
            barcode=barcode,
            product_id=product_id,
            product_name=product_name,
            sku=sku,
            notes=notes + ["Batch number and expiry date must be entered manually."],
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Case C – Supplier-specific QR
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_supplier_qr(self, req: ScanLabelRequest) -> ParsedLabelData:
        raw = (req.raw_data or "").strip()
        fields = parse_supplier_qr(raw)

        if fields is None:
            raise InvalidLabelException("Could not parse supplier QR code.")

        notes: list[str] = []
        product_id, product_name, sku = await self._lookup_product(
            gtin=fields.get("gtin"),
            barcode=fields.get("sku"),
            notes=notes,
        )

        status = ParseStatus.SUCCESS if product_id else ParseStatus.NOT_FOUND

        return ParsedLabelData(
            label_type=LabelType.SUPPLIER_QR,
            parse_status=status,
            gtin=fields.get("gtin"),
            barcode=fields.get("sku"),
            product_id=product_id,
            product_name=product_name or fields.get("product_name"),
            sku=fields.get("sku") or sku,
            batch_number=fields.get("batch_number"),
            expiry_date=fields.get("expiry_date"),
            quantity=fields.get("quantity"),
            serial_number=fields.get("serial_number"),
            notes=notes,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Case D – Manual entry
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_manual(self, req: ScanLabelRequest) -> ParsedLabelData:
        notes: list[str] = ["Label scanned manually by employee."]
        product_id, product_name, sku = None, None, None

        if req.manual_product_ref:
            product_id, product_name, sku = await self._lookup_product_by_ref(
                req.manual_product_ref, notes
            )

        status = ParseStatus.SUCCESS if product_id else ParseStatus.NOT_FOUND

        return ParsedLabelData(
            label_type=LabelType.MANUAL,
            parse_status=status,
            product_id=product_id,
            product_name=product_name,
            sku=sku,
            batch_number=req.manual_batch,
            expiry_date=req.manual_expiry,
            notes=notes,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Case E – Damaged / unreadable code
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_damaged(self, req: ScanLabelRequest) -> ParsedLabelData:
        """
        Employee types the digits printed below the barcode.
        We try to look it up as a plain barcode first; fall through to manual.
        """
        notes: list[str] = ["Damaged label – typed digits used for lookup."]
        typed = (req.raw_data or "").strip()

        product_id, product_name, sku = await self._lookup_product(
            gtin=None, barcode=typed, notes=notes
        )

        if product_id:
            return ParsedLabelData(
                label_type=LabelType.DAMAGED,
                parse_status=ParseStatus.PARTIAL,
                barcode=typed,
                product_id=product_id,
                product_name=product_name,
                sku=sku,
                notes=notes + ["Batch and expiry must be entered manually."],
            )

        # Fallback: treat as manual search
        notes.append("Could not find product via typed code – manual search required.")
        return ParsedLabelData(
            label_type=LabelType.DAMAGED,
            parse_status=ParseStatus.NOT_FOUND,
            barcode=typed,
            notes=notes,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Case F – Unknown barcode
    # ─────────────────────────────────────────────────────────────────────────

    async def _handle_unknown(self, req: ScanLabelRequest) -> ParsedLabelData:
        """
        Barcode exists but no product is linked to it.
        Returns NEEDS_LINK status so the frontend can invoke the catalogue flow.
        """
        code = (req.raw_data or "").strip()
        return ParsedLabelData(
            label_type=LabelType.UNKNOWN,
            parse_status=ParseStatus.NEEDS_LINK,
            unlinked_code=code,
            notes=[
                "This barcode is not linked to any product. "
                "An authorised catalogue user can link it to an existing product "
                "or create a new product."
            ],
        )

    # ─────────────────────────────────────────────────────────────────────────
    # DB helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _lookup_product(
        self,
        gtin: str | None,
        barcode: str | None,
        notes: list[str],
    ) -> tuple[str | None, str | None, str | None]:
        """
        Look up a product by GTIN or barcode via the LabelCode table.
        Returns (product_id, product_name, sku) or (None, None, None).
        """
        # Import here to avoid circular imports at module load time
        from app.modules.catalogue.models import LabelCode, Product

        result = None
        if gtin:
            result = await self._db.execute(
                select(LabelCode).where(LabelCode.code == gtin).limit(1)
            )
            lc = result.scalars().first()
            if lc:
                prod = await self._db.get(Product, lc.product_id)
                if prod:
                    return str(prod.id), prod.name, prod.sku

        if barcode:
            result = await self._db.execute(
                select(LabelCode).where(LabelCode.code == barcode).limit(1)
            )
            lc = result.scalars().first()
            if lc:
                prod = await self._db.get(Product, lc.product_id)
                if prod:
                    return str(prod.id), prod.name, prod.sku

        notes.append("Product not found in catalogue for the given code.")
        return None, None, None

    async def _lookup_product_by_ref(
        self, ref: str, notes: list[str]
    ) -> tuple[str | None, str | None, str | None]:
        """Search by SKU or partial name match."""
        from app.modules.catalogue.models import Product
        from sqlalchemy import or_, func

        result = await self._db.execute(
            select(Product).where(
                or_(
                    Product.sku.ilike(ref),
                    Product.name.ilike(f"%{ref}%"),
                )
            ).limit(5)
        )
        products = result.scalars().all()

        if len(products) == 1:
            p = products[0]
            return str(p.id), p.name, p.sku
        if len(products) > 1:
            names = ", ".join(p.name for p in products[:3])
            notes.append(f"Multiple products matched '{ref}': {names}. Please select one.")
            return None, None, None

        notes.append(f"No product found for reference '{ref}'.")
        return None, None, None
