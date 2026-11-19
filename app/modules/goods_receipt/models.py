"""
Goods Receipt DB models.

GoodsReceipt – receipt header (links to a PO)
GRLine       – one line per scanned product batch
GRDiscrepancy – shortage / excess / expiry / damage flags per GR line
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class GRStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FINALISED = "FINALISED"
    CANCELLED = "CANCELLED"


class DiscrepancyType(str, enum.Enum):
    SHORTAGE = "SHORTAGE"             # received < ordered
    EXCESS = "EXCESS"                 # received > ordered
    WRONG_PRODUCT = "WRONG_PRODUCT"
    DAMAGED = "DAMAGED"
    NEAR_EXPIRY = "NEAR_EXPIRY"       # expiry within configured threshold
    EXPIRED = "EXPIRED"
    BATCH_MISMATCH = "BATCH_MISMATCH"


class GoodsReceipt(Base):
    __tablename__ = "goods_receipts"
    __table_args__ = (
        Index("ix_gr_po_id", "purchase_order_id"),
        Index("ix_gr_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    gr_number: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=True,  # a receipt can exist without a PO (unplanned delivery)
    )
    received_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    received_date: Mapped[date] = mapped_column(
        Date, nullable=False, default=lambda: datetime.now(tz=timezone.utc).date()
    )
    status: Mapped[GRStatus] = mapped_column(
        SAEnum(GRStatus, name="gr_status_enum"),
        default=GRStatus.DRAFT,
        nullable=False,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_discrepancies: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    # Relationships
    lines: Mapped[list["GRLine"]] = relationship(
        "GRLine", back_populates="goods_receipt", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<GoodsReceipt gr_number={self.gr_number!r} status={self.status}>"


class GRLine(Base):
    __tablename__ = "gr_lines"
    __table_args__ = (
        Index("ix_gr_lines_gr_id", "goods_receipt_id"),
        Index("ix_gr_lines_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("goods_receipts.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    po_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("po_lines.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # Label data as captured
    label_type: Mapped[str] = mapped_column(String(50), nullable=False, default="UNKNOWN")
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gtin: Mapped[str | None] = mapped_column(String(50), nullable=True)
    batch_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    manufacture_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Quantities
    quantity_received: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String(50), nullable=False, default="EA")

    # Flags
    has_discrepancy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Relationships
    goods_receipt: Mapped["GoodsReceipt"] = relationship("GoodsReceipt", back_populates="lines")
    discrepancies: Mapped[list["GRDiscrepancy"]] = relationship(
        "GRDiscrepancy", back_populates="gr_line", cascade="all, delete-orphan"
    )


class GRDiscrepancy(Base):
    """
    One record per flag on a GR line.
    A single line can have multiple discrepancy types
    (e.g. SHORTAGE + NEAR_EXPIRY at the same time).
    """

    __tablename__ = "gr_discrepancies"
    __table_args__ = (Index("ix_disc_gr_line_id", "gr_line_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    gr_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gr_lines.id", ondelete="CASCADE"),
        nullable=False,
    )
    discrepancy_type: Mapped[DiscrepancyType] = mapped_column(
        SAEnum(DiscrepancyType, name="discrepancy_type_enum"), nullable=False
    )
    expected_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actual_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    gr_line: Mapped["GRLine"] = relationship("GRLine", back_populates="discrepancies")
